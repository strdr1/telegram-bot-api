"""
category_handler.py - Обработчик показа категорий блюд
"""

import logging
import re
import random
from difflib import SequenceMatcher
from menu_cache import menu_cache
from handlers.utils import safe_send_message
from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)

async def handle_show_category_brief(category_name: str, user_id: int, bot):
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

        # 🟢 ПРЯМОЕ СОПОСТАВЛЕНИЕ (ПО ЗАПРОСУ)
        # Если ищут "горячее", сразу подменяем на точное название категории из menu_cache.json
        hot_variations = [
            'горячее', 'горячие', 'горячие блюда', 
            'что у вас из горячего', 'покажи горячее',
            'что у вас горячего', 'что есть из горячего',
            'меню горячее', 'горячее меню', 'горячего',
            'из горячего', 'по горячему'
        ]
        if category_name.lower().strip() in hot_variations:
            category_name = "🍖 ГОРЯЧИЕ БЛЮДА"
            logger.info(f"🔄 Переопределение категории: '{original_name}' -> '{category_name}'")
        
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
                    if item.get('weight'):
                        text += f" (⚖️ {item['weight']}г)"
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
                    if search_name in ['горячее', 'горячие блюда', 'второе', 'вторые блюда', 'основное', 'основные блюда']:
                        # Ищем совпадение с корнями слов
                        if any(root in cat_name for root in ['горяч', 'основн', 'втор']) or \
                           any(root in cat_display_name for root in ['горяч', 'основн', 'втор']):
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
                    
                    text = f"{emoji} <b>{category_title}</b>\n\n"
                    
                    # Убираем дубликаты по ID блюда
                    unique_items = {}
                    for item in items:
                        item_id = item.get('id')
                        if item_id not in unique_items:
                            unique_items[item_id] = item
                    
                    # Добавляем блюда в список
                    for item in unique_items.values():
                        text += f"• {item['name']} — {item['price']}₽\n"
                    
                    text += f"\n💡 <i>Спросите про конкретное блюдо, чтобы увидеть фото и подробное описание!</i>"
                    
                    await safe_send_message(bot, user_id, text, parse_mode="HTML")
                    
                    found = True
                    logger.info(f"Показал краткий список категории: {category_title} с {len(unique_items)} блюдами")
                    break

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
                
                text = f"{emoji} <b>{category_title}</b> (найдено по названию)\n\n"
                
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
                
                await safe_send_message(bot, user_id, text, parse_mode="HTML")
                
                found = True
                logger.info(f"Показал виртуальную категорию: {category_title} с {len(unique_items)} блюдами")
                return

        if not found:
            # Если категория не найдена, ищем похожие
            all_categories = []
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
                    if str(m_id) not in processed_ids:
                        menus_to_process.append((m_id, m_data))

            for menu_id, menu in menus_to_process:
                for cat_id, category in menu.get('categories', {}).items():
                    cat_name = category.get('name', '')
                    if cat_name:
                        all_categories.append(cat_name)

            # Ищем наиболее похожие категории
            similar = []
            for cat in all_categories:
                ratio = SequenceMatcher(None, category_name.lower(), cat.lower()).ratio()
                if ratio > 0.4:  # Порог похожести
                    similar.append((cat, ratio))

            similar.sort(key=lambda x: x[1], reverse=True)
            similar = similar[:3]  # Максимум 3 похожих

            if similar:
                text = f"Категория '{category_name}' не найдена. Возможно, вы имели в виду:\n\n"
                for cat_name, ratio in similar:
                    text += f"• {cat_name}\n"
                text += "\nПопробуйте уточнить запрос."
            else:
                text = f"Категория '{category_name}' не найдена."
                
                # Предлагаем 5 случайных категорий
                unique_categories = sorted(list(set(all_categories)))
                if unique_categories:
                    count = min(5, len(unique_categories))
                    random_cats = random.sample(unique_categories, count)
                    text += f"\n\nВозможно, вас заинтересуют эти разделы:\n"
                    for cat in random_cats:
                        text += f"• {cat}\n"
                
                text += "\nПопробуйте другой запрос."

            await safe_send_message(bot, user_id, text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки краткого списка категории '{category_name}': {e}")
        await safe_send_message(bot, user_id, "Произошла ошибка при показе категории. Попробуйте позже.", parse_mode="HTML")

async def handle_show_category(category_name: str, user_id: int, bot, intro_message: str = None):
    """
    Показывает всю категорию блюд с фото и описаниями
    """
    try:
        # Очищаем от эмодзи и лишних символов
        original_name = category_name
        
        # 🟢 ПРОВЕРКА НА ЧИСЛОВОЙ МУСОР
        if category_name.strip().isdigit() and len(category_name.strip()) < 3:
            logger.info(f"🛑 Игнорирую короткий числовой запрос (подробно): '{category_name}'")
            await safe_send_message(bot, user_id, "Пожалуйста, уточните запрос. Введите название блюда.", parse_mode="HTML")
            return

        # 🟢 ПРЯМОЕ СОПОСТАВЛЕНИЕ (ПО ЗАПРОСУ)
        hot_variations = [
            'горячее', 'горячие', 'горячие блюда', 
            'что у вас из горячего', 'покажи горячее',
            'что у вас горячего', 'что есть из горячего',
            'меню горячее', 'горячее меню', 'горячего',
            'из горячего', 'по горячему'
        ]
        if category_name.lower().strip() in hot_variations:
            category_name = "🍖 ГОРЯЧИЕ БЛЮДА"
            logger.info(f"🔄 Переопределение категории (подробно): '{original_name}' -> '{category_name}'")

        category_name = category_name.replace('🍕', '').replace('🥗', '').replace('🍳', '').replace('🧀', '').replace('🍖', '').replace('🥩', '').replace('🍗', '').replace('🥙', '').replace('🌮', '').replace('🌯', '').replace('🥪', '').replace('🍔', '').replace('🍟', '').replace('🍝', '').replace('🍜', '').replace('🍛', '').replace('🍱', '').replace('🍣', '').replace('🍤', '').replace('🍙', '').replace('🍚', '').replace('🍘', '').replace('🍥', '').replace('🥟', '').replace('🥠', '').replace('🥡', '').replace('🦀', '').replace('🦞', '').replace('🦐', '').replace('🦑', '').replace('🍦', '').replace('🍧', '').replace('🍨', '').replace('🍩', '').replace('🍪', '').replace('🎂', '').replace('🍰', '').replace('🧁', '').replace('🥧', '').replace('🍫', '').replace('🍬', '').replace('🍭', '').replace('🍮', '').replace('🍯', '').replace('🍼', '').replace('🥛', '').replace('☕', '').replace('🍵', '').replace('🍶', '').replace('🍾', '').replace('🍷', '').replace('🍸', '').replace('🍹', '').replace('🍺', '').replace('🍻', '').replace('🥂', '').replace('🥃', '').strip()
        category_name = category_name.replace('_', ' ').strip()
        logger.info(f"Показываю категорию (подробно): '{category_name}'")

        lower_name = category_name.lower()

        # 🟢 ОБРАБОТКА ЗАВТРАКОВ (МЕНЮ 90)
        # Список общих запросов завтраков
        breakfast_generics = ['завтрак', 'завтраки', 'меню завтраков', 'меню завтрак', 'breakfast', 'breakfasts']
        
        # Проверяем, является ли запрос общим
        is_generic_breakfast = lower_name in breakfast_generics or \
                             (lower_name.endswith('завтрак') and len(lower_name.split()) < 2) or \
                             (lower_name.endswith('завтраки') and len(lower_name.split()) < 2)

        if is_generic_breakfast:
            # Пользователь просил список как для пиццы или горячего
            # Перенаправляем на краткий список
            logger.info(f"🔄 Перенаправление запроса завтрака на краткий список")
            await handle_show_category_brief("завтрак", user_id, bot)
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
                cat_display_name = category.get('display_name', cat_name).lower().strip()
                search_name = category_name.lower().strip()

                # Нормализация для "горячие блюда" <-> "горячее"
                # Явная проверка ID 4822
                if str(cat_id) == '4822' and search_name in ['горячее', 'горячие', 'горячие блюда']:
                    is_match = True
                # Проверка по имени с учетом эмодзи
                elif search_name in ['горячее', 'горячие блюда'] and \
                     (cat_name in ['горячее', 'горячие блюда'] or \
                      any(x in cat_display_name for x in ['горячее', 'горячие блюда'])):
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
                    
                    # Отправляем каждое блюдо с фото
                    for item in unique_items.values():
                        try:
                            photo_url = item.get('image_url')
                            if photo_url:
                                caption = f"🍽️ <b>{item['name']}</b>\n\n"
                                caption += f"💰 Цена: {item['price']}₽\n"
                                if item.get('weight'):
                                    caption += f"⚖️ Вес: {item['weight']}г\n"
                                if item.get('calories'):
                                    caption += f"🔥 Калории: {item['calories']} ккал\n"
                                
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

                                await bot.send_photo(
                                    chat_id=user_id,
                                    photo=photo_url,
                                    caption=caption,
                                    parse_mode="HTML"
                                )
                            else:
                                # Если нет фото - отправляем текстом
                                text = f"🍽️ <b>{item['name']}</b>\n💰 Цена: {item['price']}₽"
                                if item.get('description'):
                                    text += f"\n{item['description']}"
                                await safe_send_message(bot, user_id, text, parse_mode="HTML")

                        except Exception as e:
                            logger.error(f"Ошибка отправки блюда {item.get('name', 'unknown')}: {e}")
                            continue

                    found = True
                    logger.info(f"Показал категорию (подробно): {category_title} с {len(unique_items)} блюдами")
                    break

            if found:
                break

        if not found:
            # Попытка 2: Ищем блюда по названию (виртуальная категория)
            virtual_items = []
            
            # Поддержка нескольких ключевых слов (разделенных запятой или пробелом)
            raw_search = category_name.lower().strip()
            # Если есть запятые, разбиваем по ним, иначе по пробелам
            if ',' in raw_search:
                search_keywords = [k.strip() for k in raw_search.split(',') if k.strip()]
            else:
                search_keywords = [k.strip() for k in raw_search.split() if k.strip()]
            
            # Если ключевых слов нет, используем исходную строку
            if not search_keywords:
                search_keywords = [raw_search]

            # Убираем окончание 'и' для каждого слова
            search_keywords = [k[:-1] if k.endswith('и') and len(k) > 3 else k for k in search_keywords]
            
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
                    if str(m_id) not in processed_ids:
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
                    
                    # 🛑 ИСКЛЮЧАЕМ АЛКОГОЛЬНЫЕ КАТЕГОРИИ по названию
                    if not is_alcohol_search and any(root in cat_name for root in alcohol_roots):
                        continue

                    for item in category.get('items', []):
                        item_name = item.get('name', '').lower()
                        item_desc = item.get('description', '').lower()
                        full_text = f"{item_name} {item_desc}"
                        
                        # Проверяем наличие ВСЕХ ключевых слов в названии или описании
                        match = True
                        for keyword in search_keywords:
                            if keyword not in full_text:
                                match = False
                                break
                        
                        if match:
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

                            virtual_items.append(item)

            if virtual_items:
                # Нашли блюда! Показываем их как КРАТКИЙ СПИСОК (без фото)
                category_title = category_name.capitalize()
                
                # Убираем дубликаты по ID блюда
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
                    if item.get('weight'):
                        text += f" (⚖️ {item['weight']}г)"
                    text += "\n"
                
                text += f"\n💡 <i>Спросите про конкретное блюдо, чтобы увидеть фото и подробное описание!</i>"

                await safe_send_message(bot, user_id, text, parse_mode="HTML")
                
                found = True
                logger.info(f"Показал виртуальную категорию (кратко): {category_title} с {len(unique_items)} блюдами")
                return

        if not found:
            # Если это был поисковый запрос от AI и ничего не найдено
            if intro_message:
                text = f"{intro_message}\n\nК сожалению, я не нашел блюд по запросу '{category_name}'."
                await safe_send_message(bot, user_id, text, parse_mode="HTML")
                return

            # Если категория не найдена, ищем похожие
            all_categories = []
            if menu_cache.all_menus_cache:
                for menu_id, menu in menu_cache.all_menus_cache.items():
                    for cat_id, category in menu.get('categories', {}).items():
                        cat_name = category.get('name', '')
                        if cat_name:
                            all_categories.append(cat_name)

            # Ищем наиболее похожие категории
            similar = []
            for cat in all_categories:
                ratio = SequenceMatcher(None, category_name.lower(), cat.lower()).ratio()
                if ratio > 0.4:  # Порог похожести
                    similar.append((cat, ratio))

            similar.sort(key=lambda x: x[1], reverse=True)
            similar = similar[:3]  # Максимум 3 похожих

            if similar:
                text = f"Категория '{category_name}' не найдена. Возможно, вы имели в виду:\n\n"
                for cat_name, ratio in similar:
                    text += f"• {cat_name}\n"
                text += "\nПопробуйте уточнить запрос."
            else:
                text = f"Категория '{category_name}' не найдена."
                
                # Предлагаем 5 случайных категорий
                unique_categories = sorted(list(set(all_categories)))
                if unique_categories:
                    count = min(5, len(unique_categories))
                    random_cats = random.sample(unique_categories, count)
                    text += f"\n\nВозможно, вас заинтересуют эти разделы:\n"
                    for cat in random_cats:
                        text += f"• {cat}\n"
                
                text += "\nПопробуйте другой запрос."

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