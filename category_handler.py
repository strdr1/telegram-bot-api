"""
category_handler.py - Обработчик показа категорий блюд
"""

import logging
import re
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
        category_name = category_name.replace('🍕', '').replace('🥗', '').replace('🍳', '').replace('🧀', '').replace('🍖', '').replace('🥩', '').replace('🍗', '').replace('🥙', '').replace('🌮', '').replace('🌯', '').replace('🥪', '').replace('🍔', '').replace('🍟', '').replace('🍝', '').replace('🍜', '').replace('🍛', '').replace('🍱', '').replace('🍣', '').replace('🍤', '').replace('🍙', '').replace('🍚', '').replace('🍘', '').replace('🍥', '').replace('🥟', '').replace('🥠', '').replace('🥡', '').replace('🦀', '').replace('🦞', '').replace('🦐', '').replace('🦑', '').replace('🍦', '').replace('🍧', '').replace('🍨', '').replace('🍩', '').replace('🍪', '').replace('🎂', '').replace('🍰', '').replace('🧁', '').replace('🥧', '').replace('🍫', '').replace('🍬', '').replace('🍭', '').replace('🍮', '').replace('🍯', '').replace('🍼', '').replace('🥛', '').replace('☕', '').replace('🍵', '').replace('🍶', '').replace('🍾', '').replace('🍷', '').replace('🍸', '').replace('🍹', '').replace('🍺', '').replace('🍻', '').replace('🥂', '').replace('🥃', '').strip()
        category_name = category_name.replace('_', ' ').strip()
        logger.info(f"Показываю краткий список категории: '{category_name}'")

        lower_name = category_name.lower()

        # Список общих запросов завтраков, для которых показываем полный список
        breakfast_generics = ['завтрак', 'завтраки', 'меню завтраков', 'меню завтрак', 'breakfast', 'breakfasts']
        
        # Проверяем, является ли запрос общим (точное совпадение или очень близкое)
        is_generic_breakfast = lower_name in breakfast_generics or \
                             (lower_name.endswith('завтрак') and len(lower_name.split()) < 2) or \
                             (lower_name.endswith('завтраки') and len(lower_name.split()) < 2)

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
                menu_title = re.sub(r'\s*\(.*?\)\s*', '', menu_title_raw).strip()
                emoji = '🍳'
                if emoji in menu_title:
                    menu_title = menu_title.replace(emoji, '').strip()
                
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
        for menu_id, menu in menu_cache.all_menus_cache.items():
            for cat_id, category in menu.get('categories', {}).items():
                cat_name = category.get('name', '').lower().strip()
                cat_display_name = category.get('display_name', cat_name).lower().strip()
                search_name = category_name.lower().strip()

                # Проверяем точное совпадение или вхождение
                if (search_name in cat_name or cat_name in search_name or
                    search_name in cat_display_name or cat_display_name in search_name):
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
            
            for menu_id, menu in menu_cache.all_menus_cache.items():
                for cat_id, category in menu.get('categories', {}).items():
                    for item in category.get('items', []):
                        if search_term in item.get('name', '').lower():
                            virtual_items.append(item)

            if virtual_items:
                # Нашли блюда! Показываем их
                category_title = category_name.capitalize()
                await safe_send_message(bot, user_id, f"🍽️ <b>{category_title}</b> (найдено по названию)\n\nВот что я нашел:", parse_mode="HTML")
                
                # Убираем дубликаты по ID блюда
                unique_items = {}
                for item in virtual_items:
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
                logger.info(f"Показал виртуальную категорию (подробно): {category_title} с {len(unique_items)} блюдами")

        if not found:
            # Попытка 2: Ищем блюда по названию (виртуальная категория)
            # Это нужно для случаев, когда нет отдельной категории (например "Завтраки"), но есть блюда
            virtual_items = []
            search_term = category_name.lower().strip()
            # Убираем окончание 'и' для лучшего поиска (завтраки -> завтрак)
            if search_term.endswith('и'):
                search_term = search_term[:-1]
            
            for menu_id, menu in menu_cache.all_menus_cache.items():
                for cat_id, category in menu.get('categories', {}).items():
                    for item in category.get('items', []):
                        if search_term in item.get('name', '').lower():
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
            for menu_id, menu in menu_cache.all_menus_cache.items():
                for cat_id, category in menu.get('categories', {}).items():
                    cat_name = category.get('name', '')
                    if cat_name:
                        all_categories.append(cat_name)

            # Ищем наиболее похожие категории
            from difflib import SequenceMatcher
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
                text = f"Категория '{category_name}' не найдена. Попробуйте другой запрос."

            await safe_send_message(bot, user_id, text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки краткого списка категории '{category_name}': {e}")
        await safe_send_message(bot, user_id, "Произошла ошибка при показе категории. Попробуйте позже.", parse_mode="HTML")

async def handle_show_category(category_name: str, user_id: int, bot):
    """
    Показывает всю категорию блюд с фото и описаниями
    """
    try:
        # Очищаем от эмодзи и лишних символов
        category_name = category_name.replace('🍕', '').replace('🥗', '').replace('🍳', '').replace('🧀', '').replace('🍖', '').replace('🥩', '').replace('🍗', '').replace('🥙', '').replace('🌮', '').replace('🌯', '').replace('🥪', '').replace('🍔', '').replace('🍟', '').replace('🍝', '').replace('🍜', '').replace('🍛', '').replace('🍱', '').replace('🍣', '').replace('🍤', '').replace('🍙', '').replace('🍚', '').replace('🍘', '').replace('🍥', '').replace('🥟', '').replace('🥠', '').replace('🥡', '').replace('🦀', '').replace('🦞', '').replace('🦐', '').replace('🦑', '').replace('🍦', '').replace('🍧', '').replace('🍨', '').replace('🍩', '').replace('🍪', '').replace('🎂', '').replace('🍰', '').replace('🧁', '').replace('🥧', '').replace('🍫', '').replace('🍬', '').replace('🍭', '').replace('🍮', '').replace('🍯', '').replace('🍼', '').replace('🥛', '').replace('☕', '').replace('🍵', '').replace('🍶', '').replace('🍾', '').replace('🍷', '').replace('🍸', '').replace('🍹', '').replace('🍺', '').replace('🍻', '').replace('🥂', '').replace('🥃', '').strip()
        category_name = category_name.replace('_', ' ').strip()
        logger.info(f"Ищу категорию: '{category_name}'")

        lower_name = category_name.lower()

        # Список общих запросов завтраков
        breakfast_generics = ['завтрак', 'завтраки', 'меню завтраков', 'меню завтрак', 'breakfast', 'breakfasts']
        is_generic_breakfast = lower_name in breakfast_generics or \
                             (lower_name.endswith('завтрак') and len(lower_name.split()) < 2) or \
                             (lower_name.endswith('завтраки') and len(lower_name.split()) < 2)

        if is_generic_breakfast:
            # Для ОБЩИХ запросов завтраков показываем краткий список
            await handle_show_category_brief(category_name, user_id, bot)
            return

        found = False
        for menu_id, menu in menu_cache.all_menus_cache.items():
            for cat_id, category in menu.get('categories', {}).items():
                cat_name = category.get('name', '').lower().strip()
                cat_display_name = category.get('display_name', cat_name).lower().strip()
                search_name = category_name.lower().strip()

                # Проверяем точное совпадение или вхождение
                if (search_name in cat_name or cat_name in search_name or
                    search_name in cat_display_name or cat_display_name in search_name):
                    # Получаем все блюда категории
                    items = category.get('items', [])
                    if not items:
                        await safe_send_message(bot, user_id, f"В категории '{category.get('name', category_name)}' пока нет блюд.", parse_mode="HTML")
                        return

                    # Отправляем заголовок категории
                    category_title = category.get('display_name') or category.get('name', category_name)
                    await safe_send_message(bot, user_id, f"🍽️ <b>{category_title}</b>\n\nВот что у нас есть:", parse_mode="HTML")

                    # Отправляем каждое блюдо с фото
                    for item in items:
                        try:
                            photo_url = item.get('image_url')
                            if photo_url:
                                caption = f"🍽️ <b>{item['name']}</b>\n\n"
                                caption += f"💰 Цена: {item['price']}₽\n"
                                if item.get('calories'):
                                    caption += f"🔥 Калории: {item['calories']} ккал\n"
                                if item.get('proteins') or item.get('fats') or item.get('carbs'):
                                    caption += f"\n🧃 БЖУ:\n"
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
                    logger.info(f"Показал категорию: {category_title} с {len(items)} блюдами")

                    # Историю ИИ не ведём для технических списков

                    break

            if found:
                break

        if not found:
            # Если категория не найдена, ищем похожие
            all_categories = []
            for menu_id, menu in menu_cache.all_menus_cache.items():
                for cat_id, category in menu.get('categories', {}).items():
                    cat_name = category.get('name', '')
                    if cat_name:
                        all_categories.append(cat_name)

            # Ищем наиболее похожие категории
            from difflib import SequenceMatcher
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
                text = f"Категория '{category_name}' не найдена. Попробуйте другой запрос."

            await safe_send_message(bot, user_id, text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка обработки категории '{category_name}': {e}")
        await safe_send_message(bot, user_id, "Произошла ошибка при показе категории. Попробуйте позже.", parse_mode="HTML")
