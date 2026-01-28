"""
category_handler.py - Обработчик показа категорий блюд
"""

import logging
import re
import random
from difflib import SequenceMatcher
from menu_cache import menu_cache
from handlers.utils import safe_send_message
from aiogram import types
from aiogram.types import BufferedInputFile
from ai_assistant import get_ai_response

logger = logging.getLogger(__name__)

# 🛑 СПИСОК ЗАПРЕЩЕННЫХ КАТЕГОРИЙ (Blacklist)
# Эти категории никогда не должны показываться пользователю, даже если найдены поиском.
BLOCKED_CATEGORIES = [
    'добавки', 
    'добавки в пиццу', 
    'модификаторы', 
    'топпинги', 
    'с собой', 
    'упаковка',
    'прочее'
]

def is_category_blocked(category_name: str) -> bool:
    """Проверяет, является ли категория запрещенной"""
    name_lower = category_name.lower().strip()
    for blocked in BLOCKED_CATEGORIES:
        if blocked in name_lower:
            return True
    return False

def _to_float(val):
    try:
        return float(str(val).replace(',', '.'))
    except:
        return None

def _extract_weight_value(item: dict):
    m = re.search(r'[\d\\.]+', str(item.get('weight', '')))
    if m:
        try:
            return float(m.group(0))
        except:
            return None
    return None

def get_calorie_info(item: dict):
    total_cal = _to_float(item.get('calories'))
    if total_cal is None:
        weight_val = _extract_weight_value(item)
        cp100_val = _to_float(item.get('calories_per_100'))
        if weight_val is not None and cp100_val is not None:
            total_cal = cp100_val * weight_val / 100.0
    total_int = int(round(total_cal)) if total_cal is not None else None
    cp100_int = None
    cp100_val = _to_float(item.get('calories_per_100'))
    if cp100_val is not None:
        cp100_int = int(round(cp100_val))
    return total_int, cp100_int

def find_dishes_by_name(raw_search: str, limit: int = 20) -> list:
    """
    Ищет блюда по названию (нечеткий поиск).
    Возвращает список найденных блюд (словарей с menu_id и category_id).
    """
    virtual_items = []
    
    raw_search = raw_search.lower().strip()
    if ',' in raw_search:
        raw_tokens = [k.strip() for k in raw_search.split(',') if k.strip()]
    else:
        raw_tokens = [k.strip() for k in raw_search.split() if k.strip()]
    
    search_keywords = []
    for k in raw_tokens:
        k = k.strip()
        if not k: continue
        
        # Простой стемминг для русского языка
        # Убираем окончания падежей и множественного числа
        if len(k) > 4:
            if k.endswith('ами'): k = k[:-3]
            elif k.endswith('ями'): k = k[:-3]
            elif k.endswith('ов'): k = k[:-2]
            elif k.endswith('ев'): k = k[:-2]
            elif k.endswith('ей'): k = k[:-2]
            elif k.endswith('и'): k = k[:-1]
            elif k.endswith('ы'): k = k[:-1]
            elif k.endswith('а'): k = k[:-1]
            elif k.endswith('я'): k = k[:-1]
            elif k.endswith('е'): k = k[:-1]
            elif k.endswith('у'): k = k[:-1]
            elif k.endswith('ю'): k = k[:-1]
        
        search_keywords.append(k)

    if not search_keywords:
        search_keywords = [raw_search]
    
    # Расширение поисковых ключевых слов по синонимам для ингредиентов
    synonyms_map = {
        'мёд': ['мёд', 'мед', 'медов'],
        'мед': ['мёд', 'мед', 'медов'],
        'арахис': ['арахис', 'арахисов', 'арахисовая', 'землян', 'peanut'],
    }
    expanded_keywords = list(search_keywords)
    for k in search_keywords:
        for base, syns in synonyms_map.items():
            if base in k:
                for s in syns:
                    if s not in expanded_keywords:
                        expanded_keywords.append(s)
    search_keywords = expanded_keywords
    seafood_search = False
    if any('морепродукт' in k for k in search_keywords) or 'морепродукт' in raw_search:
        seafood_search = True
        search_keywords = [
            'креветк',
            'кальмар',
            'миди',
            'осьминог',
            'гребешк',
            'краб',
            'лангустин'
        ]
    
    # Также используем приоритетный порядок поиска: delivery -> all
    menus_to_process = []
    processed_ids = set()
    
    # 1. Добавляем меню из кэша доставки
    if menu_cache.delivery_menus_cache:
        for m_id, m_data in menu_cache.delivery_menus_cache.items():
            menus_to_process.append((m_id, m_data))
            processed_ids.add(str(m_id))
            
    # 2. Добавляем остальные меню из общего кэша
    if menu_cache.all_menus_cache:
        for m_id, m_data in menu_cache.all_menus_cache.items():
            # Пропускаем, если уже обработали
            if str(m_id) in processed_ids:
                continue
                
            # 🛑 ФИЛЬТРАЦИЯ ПО РАЗРЕШЕННЫМ ID
            # Гарантируем, что не ищем в мусорных меню
            try:
                if int(m_id) not in ALLOWED_MENU_IDS:
                    continue
            except:
                continue
                
            menus_to_process.append((m_id, m_data))

    # Список корней слов, указывающих на мясные/рыбные ингредиенты
    forbidden_meat_roots = [
        'брискет', 'говядин', 'свинин', 'куриц', 'цыплен', 'бекон', 'пастрам', 
        'фарш', 'мяс', 'стейк', 'колбас', 'ветчин', 'лосос', 'форел', 'рыб', 
        'креветк', 'кальмар', 'судак', 'треск', 'ребр', 'крыль', 'утка', 'индейк'
    ]
    
    # Ключевые слова, требующие строгой фильтрации мяса
    dietary_roots = ['овощ', 'веган', 'постн', 'вегет', 'без мяс']

    # 🛑 СТОП-СЛОВА ДЛЯ АЛКОГОЛЯ (исключаем из поиска, если не запрошено явно)
    alcohol_roots = ['вино', 'винн', 'пиво', 'пивн', 'алкоголь', 'коктейль', 'водка', 'виски', 'ром', 'текила']
    # Проверяем, ищет ли пользователь алкоголь явно
    is_alcohol_search = any(root in raw_search for root in alcohol_roots)

    for menu_id, menu in menus_to_process:
        # 🛑 ИСКЛЮЧАЕМ АЛКОГОЛЬНЫЕ МЕНЮ (ID 29, 32 - Бар), если не ищем алкоголь явно
        if not is_alcohol_search and str(menu_id) in ['29', '32']:
            continue

        for cat_id, category in menu.get('categories', {}).items():
            cat_name = category.get('name', '').lower()
            
            # 🛑 ИСКЛЮЧАЕМ ЗАПРЕЩЕННЫЕ КАТЕГОРИИ
            if is_category_blocked(cat_name):
                continue

            # 🛑 ИСКЛЮЧАЕМ АЛКОГОЛЬНЫЕ КАТЕГОРИИ по названию
            if not is_alcohol_search and any(root in cat_name for root in alcohol_roots):
                continue

            for item in category.get('items', []):
                item_name = item.get('name', '').lower()
                item_desc = item.get('description', '').lower()
                full_text = f"{item_name} {item_desc}"

                if seafood_search or ',' in raw_search:
                    match = False
                    for keyword in search_keywords:
                        if keyword in full_text:
                            match = True
                            break
                else:
                    match = True
                    for keyword in search_keywords:
                        if keyword not in full_text:
                            match = False
                            break
                
                if match:
                    # 🛑 FIX: Защита от ложного срабатывания "Паста" -> "Антипасти"
                    # Если искали "паст" (паста), но нашли "антипасти" и не искали "антипаст" специально
                    if 'паст' in search_keywords and 'антипаст' not in search_keywords:
                        if 'антипаст' in item_name.lower():
                            logger.info(f"🛑 Filtered out Antipasti for Pasta query: {item_name}")
                            continue
                        else:
                            # Debug: why wasn't it filtered if it looks like antipasti?
                            if 'анти' in item_name.lower():
                                logger.info(f"⚠️ Suspicious item passed filter: {item_name} (keywords: {search_keywords})")

                    # 🛑 ДОПОЛНИТЕЛЬНАЯ ФИЛЬТРАЦИЯ ДЛЯ ДИЕТИЧЕСКИХ ЗАПРОСОВ
                    # Если ищем овощи/веганское, исключаем явные мясные блюда
                    is_dietary_search = any(root in raw_search for root in dietary_roots)
                    
                    if is_dietary_search:
                        # Проверяем, не запросил ли пользователь мясо явно (напр. "мясо с овощами")
                        user_asked_meat = any(meat in raw_search for meat in forbidden_meat_roots)
                        
                        if not user_asked_meat:
                            # Ищем запрещенные слова в названии или описании
                            has_forbidden = False
                            for bad_word in forbidden_meat_roots:
                                if bad_word in item_name or bad_word in item_desc:
                                    has_forbidden = True
                                    break
                            
                            if has_forbidden:
                                continue

                    # Add menu_id and category_id to item if not present
                    item_copy = item.copy()
                    item_copy['menu_id'] = menu_id
                    item_copy['category_id'] = cat_id
                    virtual_items.append(item_copy)
    
    # Remove duplicates
    unique_items = {}
    for item in virtual_items:
        item_id = item.get('id')
        if item_id not in unique_items:
            unique_items[item_id] = item
            
    return list(unique_items.values())[:limit]

async def handle_show_category_brief(category_name: str, user_id: int, bot, intro_message: str = None):
    """
    Показывает краткий список категории блюд (только названия и цены)
    """
    try:
        # Очищаем от эмодзи и лишних символов
        original_name = category_name  # Сохраняем оригинал для логирования
        
        # 🟢 ПРОВЕРКА НА ЧИСЛОВОЙ МУСОР (для краткого списка)
        if category_name.strip().isdigit() and len(category_name.strip()) < 3:
            logger.info(f"🛑 Игнорирую короткий числовой запрос (кратко): '{category_name}'")
            await safe_send_message(bot, user_id, "Пожалуйста, уточните запрос. Введите название блюда.", parse_mode="HTML")
            return

        category_name = category_name.replace('🍕', '').replace('🥗', '').replace('🍳', '').replace('🧀', '').replace('🍖', '').replace('🥩', '').replace('🍗', '').replace('🥙', '').replace('🌮', '').replace('🌯', '').replace('🥪', '').replace('🍔', '').replace('🍟', '').replace('🍝', '').replace('🍜', '').replace('🍛', '').replace('🍱', '').replace('🍣', '').replace('🍤', '').replace('🍙', '').replace('🍚', '').replace('🍘', '').replace('🍥', '').replace('🥟', '').replace('🥠', '').replace('🥡', '').replace('🦀', '').replace('🦞', '').replace('🦐', '').replace('🦑', '').replace('🍦', '').replace('🍧', '').replace('🍨', '').replace('🍩', '').replace('🍪', '').replace('🎂', '').replace('🍰', '').replace('🧁', '').replace('🥧', '').replace('🍫', '').replace('🍬', '').replace('🍭', '').replace('🍮', '').replace('🍯', '').replace('🍼', '').replace('🥛', '').replace('☕', '').replace('🍵', '').replace('🍶', '').replace('🍾', '').replace('🍷', '').replace('🍸', '').replace('🍹', '').replace('🍺', '').replace('🍻', '').replace('🥂', '').replace('🥃', '').strip()
        category_name = category_name.replace('_', ' ').strip()
        logger.info(f"Показываю краткий список категории: '{category_name}'")

        lower_name = category_name.lower()

        # Список общих запросов завтраков, для которых показываем полный список
        breakfast_generics = [
            'завтрак', 'завтраки', 'меню завтраков', 'меню завтрак', 'breakfast', 'breakfasts',
            'с утра', 'поесть с утра', 'утреннее', 'утреннее меню', 'на завтрак'
        ]
        
        # Проверяем, является ли запрос общим (точное совпадение или очень близкое)
        is_generic_breakfast = lower_name in breakfast_generics or \
                             'завтрак' in lower_name or \
                             'с утра' in lower_name or \
                             (lower_name.endswith('завтрак') and len(lower_name.split()) < 3) or \
                             (lower_name.endswith('завтраки') and len(lower_name.split()) < 3)

        if is_generic_breakfast:
            menu = menu_cache.all_menus_cache.get("90") or menu_cache.all_menus_cache.get(90)
            if menu:
                items = []
                for category in menu.get('categories', {}).values():
                    items.extend(category.get('items', []))

                if not items:
                    await safe_send_message(bot, user_id, "В меню завтраков пока нет блюд.", parse_mode="HTML")
                    return

                menu_title_raw = menu.get('name') or category_name
                
                # Замена заголовка для завтраков
                menu_title = "Завтраки (пн-пт до 13:00, сб-вс до 16:00)"
                
                emoji = '🍳'
                
                text = f"{emoji} <b>{menu_title}</b>\n\n"

                unique_items = {}
                for item in items:
                    item_id = item.get('id')
                    if item_id not in unique_items:
                        unique_items[item_id] = item

                for item in unique_items.values():
                    text += f"• {item['name']} — {item['price']}₽"
                    
                    details = []
                    if item.get('weight'):
                        details.append(f"⚖️ {item['weight']}г")
                    total_int, cp100_int = get_calorie_info(item)
                    if total_int is not None:
                        details.append(f"{total_int} ккал")
                    if cp100_int is not None:
                        details.append(f"{cp100_int} ккал/100г")
                    
                    if details:
                        text += f" ({', '.join(details)})"
                    
                    text += "\n"

                text += f"\n💡 <i>Спросите про конкретное блюдо, чтобы увидеть фото и подробное описание!</i>"

                await safe_send_message(bot, user_id, text, parse_mode="HTML")

                # Историю ИИ не ведём для технических списков

                return

        found = False
        
        # Определяем порядок поиска: сначала меню доставки, потом бар
        # Меню доставки: 90, 92, 141
        # Барные меню: 32, 29
        
        target_priority_ids = [90, 92, 141, 32, 29]
        menus_to_process = []
        processed_ids = set()
        
        for m_id in target_priority_ids:
            # Ищем меню по ID (как строка или число)
            m_data = menu_cache.all_menus_cache.get(str(m_id)) or menu_cache.all_menus_cache.get(m_id)
            
            if m_data and str(m_id) not in processed_ids:
                menus_to_process.append((m_id, m_data))
                processed_ids.add(str(m_id))

        for menu_id, menu in menus_to_process:
            for cat_id, category in menu.get('categories', {}).items():
                # 🛑 ИСКЛЮЧАЕМ ЗАПРЕЩЕННЫЕ КАТЕГОРИИ
                if is_category_blocked(category.get('name', '')):
                    continue

                is_match = False
                # Проверка по ID (строгое совпадение)
                if str(cat_id) == str(category_name):
                    is_match = True
                else:
                    # Проверка по имени (если ID не совпал)
                    cat_name = category.get('name', '').lower().strip()
                    cat_display_name = category.get('display_name', cat_name).lower().strip()
                    search_name = str(category_name).lower().strip()
                    
                    # Нормализация для "горячие блюда" <-> "горячее"
                    # Если ищем "горячие блюда", а категория "горячее" -> совпадение
                    
                    # Проверяем, является ли запрос поиском горячих блюд
                    is_hot_search = any(root in search_name for root in ['горяч', 'основн', 'втор'])
                    # Проверяем, является ли запрос поиском салатов
                    is_salad_search = 'салат' in search_name

                    if is_hot_search:
                        # Ищем совпадение с корнями слов в названии категории
                        if any(root in cat_name for root in ['горяч', 'основн', 'втор']) or \
                           any(root in cat_display_name for root in ['горяч', 'основн', 'втор']):
                            is_match = True
                    elif is_salad_search:
                        # Для салатов ищем корень "салат"
                        if 'салат' in cat_name or 'салат' in cat_display_name:
                             is_match = True
                    else:
                        # Проверяем точное совпадение или вхождение
                        is_match = (search_name in cat_name or cat_name in search_name or
                                    search_name in cat_display_name or cat_display_name in search_name)
                    
                    # Если нет точного совпадения, пробуем нечеткое
                    if not is_match:
                        ratio_name = SequenceMatcher(None, search_name, cat_name).ratio()
                        ratio_display = SequenceMatcher(None, search_name, cat_display_name).ratio()
                        if ratio_name > 0.8 or ratio_display > 0.8:
                            is_match = True
                            logger.info(f"Нечеткое совпадение категории: '{search_name}' ~ '{cat_name}' (ratio: {max(ratio_name, ratio_display):.2f})")

                if is_match:
                    # Получаем все блюда категории
                    items = category.get('items', [])
                    if not items:
                        await safe_send_message(bot, user_id, f"В категории '{category.get('name', category_name)}' пока нет блюд.", parse_mode="HTML")
                        return

                    # Формируем краткий список
                    category_title = category.get('display_name') or category.get('name', category_name)
                    
                    # Определяем эмодзи для категории
                    emoji_map = {
                        'пицца': '🍕', 'пицц': '🍕',
                        'суп': '🍲', 'супы': '🍲', 'супов': '🍲',
                        'десерт': '🍰', 'десерты': '🍰', 'десертов': '🍰',
                        'коктейль': '🍸', 'коктейли': '🍸', 'коктейлей': '🍸',
                        'пиво': '🍺', 'пива': '🍺',
                        'вино': '🍷', 'вин': '🍷', 'вина': '🍷',
                        'салат': '🥗', 'салаты': '🥗', 'салатов': '🥗',
                        'завтрак': '🍳', 'завтраки': '🍳', 'завтраков': '🍳'
                    }
                    
                    emoji = '🍽️'
                    for key, em in emoji_map.items():
                        if key in category_name.lower():
                            emoji = em
                            break
                    
                    text = ""
                    if intro_message:
                        text += f"{intro_message}\n\n"
                    text += f"{emoji} <b>{category_title}</b>\n\n"
                    
                    # Убираем дубликаты по ID блюда
                    unique_items = {}
                    for item in items:
                        item_id = item.get('id')
                        if item_id not in unique_items:
                            unique_items[item_id] = item
                    
                    # Добавляем блюда в список
                    for item in unique_items.values():
                        text += f"• {item['name']} — {item['price']}₽"
                        
                        details = []
                        if item.get('weight'):
                            details.append(f"⚖️ {item['weight']}г")
                        total_int, cp100_int = get_calorie_info(item)
                        if total_int is not None:
                            details.append(f"{total_int} ккал")
                        if cp100_int is not None:
                            details.append(f"{cp100_int} ккал/100г")
                        
                        if details:
                            text += f" ({', '.join(details)})"
                        
                        text += "\n"
                    
                    text += f"\n💡 <i>Спросите про конкретное блюдо, чтобы увидеть фото и подробное описание!</i>"
                    
                    kb = types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))]
                    ])
    
                    await safe_send_message(bot, user_id, text, parse_mode="HTML", reply_markup=kb)
                    
                    found = True
                    logger.info(f"Показал краткий список категории: {category_title} с {len(unique_items)} блюдами")
                    return text

            if found:
                break

        if not found:
            # Попытка 2: Ищем блюда по названию (виртуальная категория)
            virtual_items = []
            search_term = category_name.lower().strip()
            # Убираем окончание 'и' для лучшего поиска (завтраки -> завтрак)
            if search_term.endswith('и'):
                search_term = search_term[:-1]
            
            # Также используем приоритетный порядок поиска
            delivery_ids = {90, 92, 141}
            sorted_menu_items = sorted(
                menu_cache.all_menus_cache.items(),
                key=lambda item: 0 if int(item[0]) in delivery_ids else 1
            )
            
            for menu_id, menu in sorted_menu_items:
                for cat_id, category in menu.get('categories', {}).items():
                    for item in category.get('items', []):
                        if search_term in item.get('name', '').lower() or search_term in item.get('description', '').lower():
                            virtual_items.append(item)

            if virtual_items:
                # Нашли блюда! Формируем виртуальную категорию
                category_title = category_name.capitalize()
                
                # Определяем эмодзи
                emoji_map = {
                    'пицца': '🍕', 'пицц': '🍕',
                    'суп': '🍲', 'супы': '🍲', 'супов': '🍲',
                    'десерт': '🍰', 'десерты': '🍰', 'десертов': '🍰',
                    'коктейль': '🍸', 'коктейли': '🍸', 'коктейлей': '🍸',
                    'пиво': '🍺', 'пива': '🍺',
                    'вино': '🍷', 'вин': '🍷', 'вина': '🍷',
                    'салат': '🥗', 'салаты': '🥗', 'салатов': '🥗',
                    'завтрак': '🍳', 'завтраки': '🍳', 'завтраков': '🍳', 'омлет': '🍳', 'яичниц': '🍳'
                }
                
                emoji = '🍽️'
                for key, em in emoji_map.items():
                    if key in category_name.lower():
                        emoji = em
                        break
                
                text = ""
                if intro_message:
                    text += f"{intro_message}\n\n"
                text += f"{emoji} <b>{category_title}</b> (найдено по названию)\n\n"
                
                # Убираем дубликаты по ID блюда
                unique_items = {}
                for item in virtual_items:
                    item_id = item.get('id')
                    if item_id not in unique_items:
                        unique_items[item_id] = item
                
                # Добавляем блюда в список
                for item in unique_items.values():
                    text += f"• {item['name']} — {item['price']}₽"
                    if item.get('weight'):
                        text += f" (⚖️ {item['weight']}г)"
                    text += "\n"
                
                text += f"\n💡 <i>Спросите про конкретное блюдо, чтобы увидеть фото, БЖУ, вес и подробное описание!</i>"
                
                kb = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))]
                ])
                
                await safe_send_message(bot, user_id, text, parse_mode="HTML", reply_markup=kb)
                
                found = True
                logger.info(f"Показал виртуальную категорию: {category_title} с {len(unique_items)} блюдами")
                return text

        if not found:
            text = f"К сожалению, я не нашел категорию или блюдо '{category_name}' в нашем меню. 😔\n\nПопробуйте спросить по-другому или опишите, какое блюдо вы ищете."
            await safe_send_message(bot, user_id, text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки краткого списка категории '{category_name}': {e}")
        await safe_send_message(bot, user_id, "Произошла ошибка при показе категории. Попробуйте позже.", parse_mode="HTML")

async def handle_show_category(category_name: str, user_id: int, bot, intro_message: str = None, is_search: bool = False):
    """
    Показывает всю категорию блюд с фото и описаниями
    :param is_search: Является ли это поисковым запросом (для показа fallback с доставкой)
    """
    try:
        # Очищаем от эмодзи и лишних символов
        original_name = category_name
        
        # 🟢 ПРОВЕРКА НА ЧИСЛОВОЙ МУСОР
        if category_name.strip().isdigit() and len(category_name.strip()) < 3:
            logger.info(f"🛑 Игнорирую короткий числовой запрос (подробно): '{category_name}'")
            await safe_send_message(bot, user_id, "Пожалуйста, уточните запрос. Введите название блюда.", parse_mode="HTML")
            return

        category_name = category_name.replace('🍕', '').replace('🥗', '').replace('🍳', '').replace('🧀', '').replace('🍖', '').replace('🥩', '').replace('🍗', '').replace('🥙', '').replace('🌮', '').replace('🌯', '').replace('🥪', '').replace('🍔', '').replace('🍟', '').replace('🍝', '').replace('🍜', '').replace('🍛', '').replace('🍱', '').replace('🍣', '').replace('🍤', '').replace('🍙', '').replace('🍚', '').replace('🍘', '').replace('🍥', '').replace('🥟', '').replace('🥠', '').replace('🥡', '').replace('🦀', '').replace('🦞', '').replace('🦐', '').replace('🦑', '').replace('🍦', '').replace('🍧', '').replace('🍨', '').replace('🍩', '').replace('🍪', '').replace('🎂', '').replace('🍰', '').replace('🧁', '').replace('🥧', '').replace('🍫', '').replace('🍬', '').replace('🍭', '').replace('🍮', '').replace('🍯', '').replace('🍼', '').replace('🥛', '').replace('☕', '').replace('🍵', '').replace('🍶', '').replace('🍾', '').replace('🍷', '').replace('🍸', '').replace('🍹', '').replace('🍺', '').replace('🍻', '').replace('🥂', '').replace('🥃', '').strip()
        category_name = category_name.replace('_', ' ').strip()
        logger.info(f"Показываю категорию (подробно): '{category_name}'")

        lower_name = category_name.lower()

        # 🟢 ОБРАБОТКА ЗАВТРАКОВ (МЕНЮ 90)
        # Ранее общий запрос завтраков перенаправлялся на краткий список.
        # По требованию — всегда показываем полную категорию (без перенаправления).
        
        # Список общих запросов завтраков
        breakfast_generics = [
            'завтрак', 'завтраки', 'меню завтраков', 'меню завтрак', 'breakfast', 'breakfasts',
            'с утра', 'поесть с утра', 'утреннее', 'утреннее меню', 'на завтрак'
        ]
        
        # Проверяем, является ли запрос общим
        is_generic_breakfast = lower_name in breakfast_generics or \
                             'завтрак' in lower_name or \
                             'с утра' in lower_name or \
                             (lower_name.endswith('завтрак') and len(lower_name.split()) < 3) or \
                             (lower_name.endswith('завтраки') and len(lower_name.split()) < 3)

        if is_generic_breakfast:
            # Пытаемся получить меню 90 напрямую, игнорируя временные ограничения доставки
            menu = menu_cache.all_menus_cache.get("90") or menu_cache.all_menus_cache.get(90)
            if menu:
                items = []
                for category in menu.get('categories', {}).values():
                    items.extend(category.get('items', []))

                if not items:
                    await safe_send_message(bot, user_id, "В меню завтраков пока нет блюд.", parse_mode="HTML")
                    return

                menu_title = "Завтраки (пн-пт до 13:00, сб-вс до 16:00)"
                emoji = '🍳'
                
                text = f"{emoji} <b>{menu_title}</b>\n\n"

                unique_items = {}
                for item in items:
                    item_id = item.get('id')
                    if item_id not in unique_items:
                        unique_items[item_id] = item

                for item in unique_items.values():
                    text += f"• {item['name']} — {item['price']}₽"
                    
                    details = []
                    if item.get('weight'):
                        details.append(f"⚖️ {item['weight']}г")
                    total_int, cp100_int = get_calorie_info(item)
                    if total_int is not None:
                        details.append(f"{total_int} ккал")
                    if cp100_int is not None:
                        details.append(f"{cp100_int} ккал/100г")
                    
                    if details:
                        text += f" ({', '.join(details)})"
                    
                    text += "\n"

                text += f"\n💡 <i>Спросите про конкретное блюдо, чтобы увидеть фото и подробное описание!</i>"

                await safe_send_message(bot, user_id, text, parse_mode="HTML")
                
                # Логируем
                logger.info(f"Показал меню завтраков (полный список, {len(unique_items)} блюд)")
                return

        found = False
        
        # Определяем порядок поиска: сначала меню доставки (menu_cache.json), потом остальные
        # menu_cache.json в приоритете!
        
        menus_to_process = []
        processed_ids = set()
        
        # 1. Добавляем меню из кэша доставки
        if menu_cache.delivery_menus_cache:
            for m_id, m_data in menu_cache.delivery_menus_cache.items():
                menus_to_process.append((m_id, m_data))
                processed_ids.add(str(m_id))
                
        # 2. Добавляем остальные меню из общего кэша, ТОЛЬКО если не нашли меню доставки
        if not menus_to_process and menu_cache.all_menus_cache:
            delivery_ids_set = {90, 92, 141}
            for m_id, m_data in menu_cache.all_menus_cache.items():
                if str(m_id) not in processed_ids and int(m_id) in delivery_ids_set:
                    menus_to_process.append((m_id, m_data))

        for menu_id, menu in menus_to_process:
            if not menu: continue
            for cat_id, category in menu.get('categories', {}).items():
                cat_name = category.get('name', '').lower().strip()
                
                # 🛑 ИСКЛЮЧАЕМ ЗАПРЕЩЕННЫЕ КАТЕГОРИИ
                if is_category_blocked(cat_name):
                    continue

                cat_display_name = category.get('display_name', cat_name).lower().strip()
                search_name = category_name.lower().strip()

                # Проверяем точное совпадение или вхождение
                is_match = (search_name in cat_name or cat_name in search_name or
                            search_name in cat_display_name or cat_display_name in search_name)
                
                # Если нет точного совпадения, пробуем нечеткое
                if not is_match:
                    ratio_name = SequenceMatcher(None, search_name, cat_name).ratio()
                    ratio_display = SequenceMatcher(None, search_name, cat_display_name).ratio()
                    if ratio_name > 0.8 or ratio_display > 0.8:
                        is_match = True
                        logger.info(f"Нечеткое совпадение категории (подробно): '{search_name}' ~ '{cat_name}' (ratio: {max(ratio_name, ratio_display):.2f})")

                if is_match:
                    # Получаем все блюда категории
                    items = category.get('items', [])
                    if not items:
                        await safe_send_message(bot, user_id, f"В категории '{category.get('name', category_name)}' пока нет блюд.", parse_mode="HTML")
                        return

                    # Отправляем вступительное сообщение
                    category_title = category.get('display_name') or category.get('name', category_name)
                    
                    # Определяем эмодзи для категории
                    emoji_map = {
                        'пицца': '🍕', 'пицц': '🍕',
                        'суп': '🍲', 'супы': '🍲', 'супов': '🍲',
                        'десерт': '🍰', 'десерты': '🍰', 'десертов': '🍰',
                        'коктейль': '🍸', 'коктейли': '🍸', 'коктейлей': '🍸',
                        'пиво': '🍺', 'пива': '🍺',
                        'вино': '🍷', 'вин': '🍷', 'вина': '🍷',
                        'салат': '🥗', 'салаты': '🥗', 'салатов': '🥗',
                        'завтрак': '🍳', 'завтраки': '🍳', 'завтраков': '🍳'
                    }
                    
                    emoji = '🍽️'
                    for key, em in emoji_map.items():
                        if key in category_name.lower():
                            emoji = em
                            break
                            
                    header_text = f"{emoji} <b>{category_title}</b>\n\nВот что у нас есть:"
                    if intro_message:
                        header_text = f"{intro_message}\n\n{emoji} <b>{category_title}</b>"
                    
                    await safe_send_message(bot, user_id, header_text, parse_mode="HTML")
                    
                    # Убираем дубликаты по ID блюда
                    unique_items = {}
                    for item in items:
                        item_id = item.get('id')
                        if item_id not in unique_items:
                            unique_items[item_id] = item
                    
                    # 🟢 ЗАЩИТА ОТ СПАМА: Если блюд слишком много (> 5), показываем краткий список
                    # ИСКЛЮЧЕНИЕ: Завтраки всегда показываем полностью (по просьбе пользователя)
                    is_breakfast = any(x in category_name.lower() for x in ['завтрак', 'breakfast'])
                    
                    if len(unique_items) > 5 and not is_breakfast:
                        logger.info(f"Слишком много блюд в категории '{category_title}' ({len(unique_items)}). Переключаюсь на краткий список.")
                        return await handle_show_category_brief(category_name, user_id, bot, intro_message)

                    # Отправляем каждое блюдо с фото
                    for item in unique_items.values():
                        try:
                            photo_url = item.get('image_url')
                            if photo_url:
                                caption = f"🍽️ <b>{item['name']}</b>\n\n"
                                caption += f"💰 Цена: {item['price']}₽\n"
                                if item.get('weight'):
                                    caption += f"⚖️ Вес: {item['weight']}г\n"
                                total_int, cp100_int = get_calorie_info(item)
                                if total_int is not None:
                                    caption += f"🔥 Калории (блюдо): {total_int} ккал\n"
                                if cp100_int is not None:
                                    caption += f"🔥 Калории (100г): {cp100_int} ккал/100г\n"
                                
                                # БЖУ
                                if item.get('proteins') or item.get('fats') or item.get('carbs'):
                                    caption += "\n📊 БЖУ:\n"
                                    if item.get('proteins'):
                                        caption += f"• Белки: {item['proteins']}г\n"
                                    if item.get('fats'):
                                        caption += f"• Жиры: {item['fats']}г\n"
                                    if item.get('carbs'):
                                        caption += f"• Углеводы: {item['carbs']}г\n"
                                if item.get('description'):
                                    caption += f"\n{item['description']}"

                                # Кнопка доставки (WebApp)
                                kb = types.InlineKeyboardMarkup(inline_keyboard=[
                                    [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))]
                                ])

                                await bot.send_photo(
                                    chat_id=user_id,
                                    photo=photo_url,
                                    caption=caption,
                                    parse_mode="HTML",
                                    reply_markup=kb
                                )
                            else:
                                # Если нет фото - отправляем текстом
                                text = f"🍽️ <b>{item['name']}</b>\n💰 Цена: {item['price']}₽"
                                if item.get('description'):
                                    text += f"\n{item['description']}"
                                    
                                kb = types.InlineKeyboardMarkup(inline_keyboard=[
                                    [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))]
                                ])
                                
                                await safe_send_message(bot, user_id, text, parse_mode="HTML", reply_markup=kb)

                        except Exception as e:
                            logger.error(f"Ошибка отправки блюда {item.get('name', 'unknown')}: {e}")
                            continue
                    
                    # Кнопка возврата к доставке в конце списка (убрана по просьбе, заменена на кнопки у блюд)
                    # back_kb = types.InlineKeyboardMarkup(inline_keyboard=[
                    #     [types.InlineKeyboardButton(text="◀️ Доставка", callback_data="menu_delivery")]
                    # ])
                    # await safe_send_message(bot, user_id, "Вернуться в меню:", reply_markup=back_kb)

                    found = True
                    logger.info(f"Показал категорию (подробно): {category_title} с {len(unique_items)} блюдами")
                    
                    # Form summary for AI context
                    shown_dishes = [item['name'] for item in unique_items.values()]
                    summary = f"Показана категория {category_title}. Блюда: {', '.join(shown_dishes)}"
                    return summary

            if found:
                break

        if not found:
            # Попытка 2: Ищем блюда по названию (виртуальная категория)
            # Используем централизованную функцию поиска
            try:
                virtual_items = find_dishes_by_name(category_name, limit=20)
            except Exception as e:
                logger.error(f"Ошибка при поиске блюд по названию '{category_name}': {e}")
                virtual_items = []

            if virtual_items:
                # Нашли блюда, показываем КРАТКИЙ СПИСОК (без фото).
                # Даже если результат один — карточку блюда НЕ показываем автоматически.
                category_title = category_name.capitalize()
                
                # Убираем дубликаты по ID блюда (find_dishes_by_name уже возвращает уникальные, но на всякий случай)
                unique_items = {}
                for item in virtual_items:
                    item_id = item.get('id')
                    if item_id not in unique_items:
                        unique_items[item_id] = item
                
                # Ограничиваем количество результатов (например, 20), чтобы не спамить
                limit = 20
                items_list = list(unique_items.values())
                
                text = ""
                if intro_message:
                    text += f"{intro_message}\n\n"

                if len(items_list) > limit:
                    text += f"🍽️ <b>{category_title}</b> (найдено по названию, показаны первые {limit}):\n\n"
                    items_list = items_list[:limit]
                else:
                    text += f"🍽️ <b>{category_title}</b> (найдено по названию):\n\n"
                
                for item in items_list:
                    text += f"• {item['name']} — {item['price']}₽"
                    
                    details = []
                    if item.get('weight'):
                        details.append(f"⚖️ {item['weight']}г")
                    total_int, cp100_int = get_calorie_info(item)
                    if total_int is not None:
                        details.append(f"{total_int} ккал")
                    if cp100_int is not None:
                        details.append(f"{cp100_int} ккал/100г")

                    if details:
                        text += f" ({', '.join(details)})"
                    
                    text += "\n"
                
                text += f"\n💡 <i>Спросите про конкретное блюдо, чтобы увидеть фото и подробное описание!</i>"

                await safe_send_message(bot, user_id, text, parse_mode="HTML")
                
                found = True
                logger.info(f"Показал виртуальную категорию (кратко): {category_title} с {len(unique_items)} блюдами")
                return text

        if not found:
            if is_search or ',' in category_name:
                logger.warning(f"Не найдено блюд по запросу: '{category_name}'")

            # Если это поисковый запрос по ингридиентам/ключевым словам,
            # не используем intro_message вообще — только честное сообщение «не нашел»
            if is_search:
                text = f"Простите, я не нашел блюд по запросу '{category_name}'. Но вы можете сами посмотреть наше актуальное меню в приложении доставки."
                try:
                    from aiogram import types
                    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))]
                    ])
                    await safe_send_message(bot, user_id, text, reply_markup=keyboard, parse_mode="HTML")
                except Exception:
                    await safe_send_message(bot, user_id, text, parse_mode="HTML")
                return

            # Обычный fallback для запросов категорий
            # 🟢 ВМЕСТО СТАНДАРТНОЙ ОТБИВКИ - СПРАШИВАЕМ AI
            logger.info(f"Категория '{category_name}' не найдена, передаю запрос в AI")
            try:
                ai_response = await get_ai_response(f"У меня нет категории '{category_name}', что посоветуешь похожее?", user_id)
                if ai_response and ai_response.get('text'):
                     await safe_send_message(bot, user_id, ai_response['text'], parse_mode="HTML")
                else:
                    text = f"К сожалению, я не нашел категорию или блюдо '{category_name}' в нашем меню. 😔\n\nПопробуйте спросить по-другому или опишите, какое блюдо вы ищете."
                    await safe_send_message(bot, user_id, text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка при запросе к AI из category_handler: {e}")
                text = f"К сожалению, я не нашел категорию или блюдо '{category_name}' в нашем меню. 😔\n\nПопробуйте спросить по-другому или опишите, какое блюдо вы ищете."
                await safe_send_message(bot, user_id, text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки категории '{category_name}': {e}")
        await safe_send_message(bot, user_id, "Произошла ошибка при показе категории. Попробуйте позже.", parse_mode="HTML")

async def handle_show_all_categories(user_id: int, bot):
    """
    Показывает список всех доступных категорий
    """
    try:
        categories = set()
        
        # Собираем все категории из кэша
        for menu_id, menu in menu_cache.all_menus_cache.items():
            for cat_id, category in menu.get('categories', {}).items():
                cat_name = category.get('display_name') or category.get('name')
                if cat_name:
                    # Очищаем имя
                    clean_name = cat_name.strip()
                    categories.add(clean_name)
        
        if not categories:
            await safe_send_message(bot, user_id, "Категории меню пока не загружены.", parse_mode="HTML")
            return

        # Сортируем
        sorted_categories = sorted(list(categories))
        
        text = "🍽️ <b>Категории нашего меню:</b>\n\n"
        
        emoji_map = {
            'пицца': '🍕', 'пицц': '🍕',
            'суп': '🍲', 'супы': '🍲',
            'десерт': '🍰', 'десерты': '🍰',
            'коктейль': '🍸', 'коктейли': '🍸',
            'пиво': '🍺', 'пива': '🍺',
            'вино': '🍷', 'вин': '🍷',
            'салат': '🥗', 'салаты': '🥗',
            'завтрак': '🍳', 'завтраки': '🍳',
            'паста': '🍝', 'бургер': '🍔',
            'закуски': '🥓', 'рыба': '🐟',
            'мясо': '🥩', 'гриль': '🔥',
            'напитки': '🥤', 'чай': '🫖', 'кофе': '☕'
        }

        for cat in sorted_categories:
            emoji = '▫️'
            cat_lower = cat.lower()
            for key, em in emoji_map.items():
                if key in cat_lower:
                    emoji = em
                    break
            
            text += f"{emoji} {cat}\n"
            
        text += "\n💡 <i>Напишите название категории или блюда, чтобы увидеть подробности!</i>"
        
        await safe_send_message(bot, user_id, text, parse_mode="HTML")
        logger.info(f"Показал список всех категорий пользователю {user_id}")

    except Exception as e:
        logger.error(f"Ошибка показа всех категорий: {e}")
        await safe_send_message(bot, user_id, "Произошла ошибка при получении списка категорий.", parse_mode="HTML")
