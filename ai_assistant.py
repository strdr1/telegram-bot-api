"""
ai_assistant.py - AI помощник для общения с пользователями
"""

import asyncio
import json
import requests
import subprocess
import os
import re
import random
from typing import Optional, Dict, List
import logging
import database

logger = logging.getLogger(__name__)

# История сообщений пользователей
user_history: Dict[int, List[Dict]] = {}

def load_token() -> str:
    """Загрузка токена GigaChat"""
    try:
        with open('ai_ref/token.txt', 'r') as f:
            return f.read().strip()
    except:
        return ""

def refresh_token() -> str:
    """Обновление токена GigaChat"""
    try:
        import uuid
        
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        auth_key = "MDE5YmIyNGEtMmMyYS03YmYyLWE1YTctYzBiOTk0ZDNiODI3OjNkNmJkNDg5LTU4MzUtNGE0My1iMmQzLWRhMzQzZmE4MTMzNQ=="
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {auth_key}"
        }
        
        data = {"scope": "GIGACHAT_API_PERS"}
        
        response = requests.post(url, headers=headers, data=data, verify=False)
        
        if response.status_code == 200:
            token = response.json()['access_token']
            with open('ai_ref/token.txt', 'w') as f:
                f.write(token)
            logger.info("Токен успешно обновлен")
            return token
        else:
            logger.error(f"Ошибка получения токена: {response.status_code}")
            return ""
    except Exception as e:
        logger.error(f"Ошибка обновления токена: {e}")
        return ""

def load_menu_cache() -> Dict:
    """Загрузка кэша всех меню для AI"""
    try:
        # Сначала пробуем загрузить all_menus_cache.json
        cache_file = 'files/all_menus_cache.json'
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                # Возвращаем только all_menus часть
                return cache_data.get('all_menus', {})

        # Fallback на старый файл menu_cache.json
        old_cache_file = 'files/menu_cache.json'
        if os.path.exists(old_cache_file):
            with open(old_cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                return cache_data.get('all_menus', {})

        return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки кэша меню для AI: {e}")
        return {}

def get_ai_notes() -> str:
    """Получение дополнительных примечаний для ИИ из БД"""
    return database.get_setting('ai_notes', '')

def search_in_faq(query: str) -> Optional[str]:
    """Поиск ответа в FAQ"""
    faq_list = database.get_faq()
    query_lower = query.lower()
    
    # Точное совпадение
    for faq_id, question, answer in faq_list:
        if query_lower in question.lower() or question.lower() in query_lower:
            return answer
    
    # Поиск по ключевым словам
    from difflib import SequenceMatcher
    best_match = None
    best_score = 0.0
    
    for faq_id, question, answer in faq_list:
        score = SequenceMatcher(None, query_lower, question.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = answer
    
    # Возвращаем только если совпадение > 60%
    if best_score > 0.6:
        return best_match
    
    return None

async def gen_image(prompt: str, user_id: int = 0) -> Optional[str]:
    """Генерация изображения через редактирование с использованием референсов персонажей"""
    try:
        import random
        from character_parser import ensure_character_references, get_character_reference_images, save_character_result, character_parser

        # Извлекаем имя персонажа из промпта синхронно
        character_name = character_parser._extract_character_name(prompt)

        # Выбираем случайное фото стола
        images = {
            'files/tables_holl.jpg': 'sitting on couch at center table near window',
            'files/table_for_1.jpg': 'sitting on a chair at the table for two',
            'files/big_table.jpg': 'sitting together at big table'  # Для групп
        }

        # Проверяем на множественное число (команды, группы)
        prompt_lower = prompt.lower()
        is_group = any(keyword in prompt_lower for keyword in [
            'team', 'avengers', 'together', 'group', 'squad', 'crew',
            'команд', 'мстител', 'групп', 'вместе'
        ])

        # Находим подходящее фото по промпту
        selected_image = None

        if is_group:
            # Для группы - большой стол
            selected_image = 'files/big_table.jpg'
            logger.info(f"👥 Обнаружена группа/команда, используем big_table.jpg")
        else:
            # Для одиночных персонажей
            for img_path, context in images.items():
                if img_path == 'files/big_table.jpg':
                    continue  # Пропускаем big_table для одиночных
                if context in prompt.lower():
                    selected_image = img_path
                    break

        if not selected_image:
            # Если не нашли - случайное из одиночных
            single_images = [k for k in images.keys() if k != 'files/big_table.jpg']
            selected_image = random.choice(single_images)

        logger.info(f"Выбрано фото стола: {selected_image}")

        # Загружаем фото стола на freeimage.host
        with open(selected_image, 'rb') as f:
            files = {'source': f}
            upload_response = requests.post(
                "https://freeimage.host/api/1/upload",
                files=files,
                data={'key': '6d207e02198a847aa98d0a2a901485a5'}
            )

        if upload_response.status_code != 200:
            logger.error(f"Ошибка загрузки фото стола: {upload_response.text}")
            return None

        table_url = upload_response.json()['image']['url']
        logger.info(f"URL фото стола: {table_url}")

        # Собираем все изображения для Kie AI
        image_urls = [table_url]

        # Если есть персонаж, добавляем референсы
        character_refs = []
        if character_name:
            logger.info(f"Обнаружен персонаж: {character_name}")

            # Убеждаемся что референсы скачаны
            ref_paths = await ensure_character_references(character_name, 3)
            logger.info(f"Найдено {len(ref_paths)} референсов для {character_name}")

            # Загружаем референсы на freeimage.host
            for ref_path in ref_paths:
                try:
                    with open(ref_path, 'rb') as f:
                        files = {'source': f}
                        upload_response = requests.post(
                            "https://freeimage.host/api/1/upload",
                            files=files,
                            data={'key': '6d207e02198a847aa98d0a2a901485a5'}
                        )

                    if upload_response.status_code == 200:
                        ref_url = upload_response.json()['image']['url']
                        image_urls.append(ref_url)
                        character_refs.append(ref_path)
                        logger.info(f"Референс загружен: {ref_url}")
                except Exception as e:
                    logger.error(f"Ошибка загрузки референса {ref_path}: {e}")

            # Добавляем детальное описание стола в промпт вместо референсов
            if character_refs:
                # Определяем тип стола для детального описания
                table_descriptions = {
                    'files/tables_holl.jpg': 'modern wooden restaurant table with comfortable chairs, warm lighting, elegant table setting with white tablecloth, wine glasses, and sophisticated dining atmosphere',
                    'files/table_for_1.jpg': 'cozy single-person dining table with comfortable armchair, intimate lighting, elegant tableware, and warm welcoming atmosphere',
                    'files/big_table.jpg': 'large rectangular banquet table for groups, multiple comfortable chairs, festive table setting, group dining atmosphere'
                }

                table_description = table_descriptions.get(selected_image, 'elegant restaurant table with comfortable chairs, warm lighting, and sophisticated dining atmosphere')

                prompt = f"{prompt}, {table_description}, photorealistic restaurant interior, detailed table and chair design, authentic dining environment, NO TEXT, NO WRITING, NO LETTERS, NO WORDS, NO CAPTIONS, NO LABELS, NO SIGNS, NO LOGOS, absolutely no text of any kind on the image"

                # GigaChat сам добавит переведенные настройки в GEN_IMAGE промпт

                # Убираем референсы персонажа, полагаемся только на текстовое описание
                character_refs = []  # Не используем референсы персонажа

        logger.info(f"Всего изображений для Kie AI: {len(image_urls)}")

        # Создаем задачу редактирования
        url = "https://api.kie.ai/api/v1/jobs/createTask"
        headers = {
            "Authorization": "Bearer d6bd19312c6a075f3418d68ee943bda0",
            "Content-Type": "application/json"
        }

        data = {
            "model": "google/nano-banana-edit",
            "input": {
                "prompt": prompt,
                "image_urls": image_urls,
                "output_format": "png",
                "image_size": "1:1"
            }
        }

        logger.info(f"Отправляю запрос на редактирование...")
        response = requests.post(url, headers=headers, json=data)
        logger.info(f"Статус: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"Ошибка: {response.text}")
            return None

        result = response.json()
        if result.get('code') != 200:
            logger.error(f"Ошибка API: {result}")
            return None

        task_id = result['data']['taskId']
        logger.info(f"Задача создана: {task_id}")

        status_url = "https://api.kie.ai/api/v1/jobs/recordInfo"

        for i in range(30):
            import time
            time.sleep(3)
            logger.info(f"Проверка статуса {i+1}/30...")
            status_response = requests.get(status_url, headers=headers, params={'taskId': task_id})

            if status_response.status_code == 200:
                status_result = status_response.json()

                if status_result.get('code') != 200:
                    logger.error(f"Ошибка: {status_result}")
                    return None

                state = status_result['data']['state']
                logger.info(f"Статус: {state}")

                if state == 'success':
                    result_json = json.loads(status_result['data']['resultJson'])
                    image_url = result_json['resultUrls'][0]
                    logger.info(f"Готово: {image_url}")

                    # Сохраняем результат если есть персонаж
                    if character_name and user_id:
                        try:
                            save_character_result(character_name, user_id, prompt, image_url, character_refs)
                        except Exception as e:
                            logger.error(f"Ошибка сохранения результата: {e}")

                    return image_url
                elif state == 'fail':
                    logger.error(f"Ошибка: {status_result['data'].get('failMsg')}")
                    return None

        logger.error("Таймаут")
        return None
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return None

async def get_ai_response(message: str, user_id: int) -> Dict:
    """
    Получение ответа от AI
    
    Returns:
        Dict с ключами:
        - type: 'text' | 'photo' | 'photo_with_text'
        - text: текст ответа
        - photo_url: URL фото (если type='photo' или 'photo_with_text')
    """
    try:
        # Проверяем лимит генераций (только для генерации изображений)
        can_generate, remaining = database.check_ai_generation_limit(user_id, daily_limit=2)
        is_admin = database.is_admin(user_id)
        
        # 1. Ищем в FAQ
        faq_answer = search_in_faq(message)
        if faq_answer:
            return {'type': 'text', 'text': faq_answer}
        
        # 2. Загружаем меню и примечания
        menu_data = load_menu_cache()
        ai_notes = get_ai_notes()
        
        # 3. Формируем контекст меню - ТОЛЬКО названия и цены для списков
        menu_context = "МЕНЮ РЕСТОРАНА:\n\n"

        # Разделяем меню на доставку и бар
        delivery_menu_ids = {90, 92, 141}
        bar_menu_ids = {29, 91, 86, 32}

        # Сначала добавляем меню доставки
        for menu_id in delivery_menu_ids:
            if menu_id in menu_data:
                menu = menu_data[menu_id]
                menu_name = menu.get('name', '').replace('🍳', '').replace('📋', '').strip()
                menu_context += f"=== {menu_name} (ДОСТАВКА) ===\n"

                for category_id, category in menu.get('categories', {}).items():
                    category_name = category.get('name', '').replace('🍕', '').replace('🥗', '').strip()
                    menu_context += f"\n{category_name}:\n"

                    for item in category.get('items', []):
                        # Для контекста даем только название и цену
                        menu_context += f"• {item['name']} - {item['price']}₽\n"
                menu_context += "\n"

        # Затем добавляем меню бара
        for menu_id in bar_menu_ids:
            if menu_id in menu_data:
                menu = menu_data[menu_id]
                menu_name = menu.get('name', '').replace('🍳', '').replace('📋', '').strip()
                alcohol_note = " (АЛКОГОЛЬ)" if menu_id == 32 else ""
                menu_context += f"=== {menu_name}{alcohol_note} (БАР) ===\n"

                for category_id, category in menu.get('categories', {}).items():
                    category_name = category.get('name', '').replace('🍕', '').replace('🥗', '').strip()
                    menu_context += f"\n{category_name}:\n"

                    for item in category.get('items', []):
                        # Для контекста даем только название и цену
                        menu_context += f"• {item['name']} - {item['price']}₽\n"
                menu_context += "\n"
        
        # 4. Получаем историю
        if user_id not in user_history:
            user_history[user_id] = []
        
        user_history[user_id].append({"role": "user", "content": message})
        
        if len(user_history[user_id]) > 20:
            user_history[user_id] = user_history[user_id][-20:]
        
        # 5. Формируем системный промпт
        system_prompt = (
            f"Ты AI-помощник бота ресторана Mashkov. Отвечай просто и красиво, БЕЗ звездочек и маркдауна.\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: ИСПОЛЬЗУЙ ТОЛЬКО ТУ ИНФОРМАЦИЮ, КОТОРАЯ ЕСТЬ В МЕНЮ НИЖЕ! НИКОГДА НЕ ПРИДУМЫВАЙ:\n"
            f"❌ Добавки к блюдам (салями, бекон, лосось, сыры, овощи и т.д.)\n"
            f"❌ Модификаторы и опции\n"
            f"❌ Цены на добавки\n"
            f"❌ Любую информацию, которой НЕТ в меню\n"
            f"✅ Если спрашивают про добавки/модификаторы - отвечай: 'Для уточнения возможности добавления ингредиентов свяжитесь с нами по телефону или оформите заказ через меню.'\n\n"
            f"ВАЖНО: ВСЕГДА используй эмодзи в своих ответах для красоты! Добавляй подходящие эмодзи к каждому пункту списка и важным словам.\n\n"
            f"ВАЖНО: Если спрашивают 'что ты умеешь', 'что умеешь', 'твои возможности' - отвечай про ВОЗМОЖНОСТИ БОТА красиво с эмодзи:\n"
            f"🍽️ Показать меню с фото и ценами\n"
            f"📊 Рассказать о блюдах, калориях и БЖУ\n"
            f"🚚 Оформить доставку\n"
            f"📅 Забронировать столик\n"
            f"💬 Ответить на вопросы о ресторане\n"
            f"🎯 Помочь с выбором блюд\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают 'можно ли через вас/тебя заказать доставку' или 'можешь ли ты заказать' - ОТВЕЧАЙ:\n"
            f"'🤖 Я не могу заказать за вас доставку, но вы можете сделать это самостоятельно через наше приложение! 🚀\n\n📱 Выберите удобный способ заказа в кнопках ниже!'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_DELIVERY_APPS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про БРОНИРОВАНИЕ СЛОВА ('забронировать', 'забранировать', 'бронировать', 'бранировать', 'столик', 'стол', 'бронь', 'резерв', 'можно забронировать', 'можно забранировать') БЕЗ указания даты/времени - ОТВЕЧАЙ ТОЛЬКО:\n"
            f"'Да, конечно! 📅'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_BOOKING_OPTIONS\n"
            f"НЕ добавляй никакой другой текст!\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь пишет БРОНИРОВАНИЕ В ФОРМАТЕ (дата + время + гости), например:\n"
            f"'Столик на 3, в 20:30, 17 января' или 'на 2 человека, завтра в 19:00' или 'Столик на 2, в 19:00, 16 января' - используй:\n"
            f"PARSE_BOOKING:текст_бронирования\n"
            f"Пример: PARSE_BOOKING:Столик на 2, в 19:00, 16 января\n"
            f"НЕ добавляй никакого другого текста, ТОЛЬКО:\n"
            f"'✅ Отлично! Бронирую для вас столик. Сейчас покажу доступные варианты.'\n"
            f"PARSE_BOOKING:текст\n\n"
            f"ВАЖНО: Если спрашивают 'какие пиццы', 'какие супы', 'какие блюда', 'что есть' - перечисли ТОЛЬКО НАЗВАНИЯ и ЦЕНЫ, БЕЗ калорий, БЖУ, ссылок и DISH_PHOTO!\n"
            f"Формат: 🍕 Название — Цена₽\n"
            f"Пример: 🍕 Пицца Маргарита — 750₽\n"
            f"НЕ добавляй калории, БЖУ, ссылки на фото или любую другую информацию при перечислении!\n\n"
            f"ВАЖНО: Если пользователь спрашивает про КАТЕГОРИЮ блюд (например 'какие пиццы', 'что из супов', 'какие десерты', 'вина', 'коктейли', 'пиво') - используй SHOW_CATEGORY:название_категории\n"
            f"Формат: SHOW_CATEGORY:название_категории\n"
            f"Примеры: SHOW_CATEGORY:Пицца, SHOW_CATEGORY:Супы, SHOW_CATEGORY:Вино\n\n"
            f"ВАЖНО: Если пользователь пишет ТОЛЬКО название блюда (например 'Пепперони', 'Борщ', 'Инфаркт') - ОБЯЗАТЕЛЬНО используй DISH_PHOTO:название_блюда\n"
            f"ФОРМАТ DISH_PHOTO: ТОЛЬКО название блюда БЕЗ эмодзи!\n"
            f"Правильно: DISH_PHOTO:Пицца Инфаркт\n"
            f"Неправильно: DISH_PHOTO:пицца_инфаркт 🍕\n\n"
            f"ВАЖНО: Если пользователь отвечает 'да', 'хочу', 'заказать', 'давай' после того как ты предложил заказать - добавь в конец: SHOW_DELIVERY_BUTTON\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: ПОЛЬЗОВАТЕЛЬ УЖЕ ПРОШЕЛ ПРОВЕРКУ ВОЗРАСТА! Ты можешь свободно отвечать на все вопросы про алкоголь и напитки.\n"
            f"Используй ТОЧНЫЕ данные из меню бара для ответов на вопросы про алкоголь.\n\n"
            f"{menu_context}\n\n"
            f"ВСЕГДА используй ТОЧНЫЕ данные из меню выше. НЕ придумывай цифры!\n"
            f"ВАЖНО: Названия блюд пиши ПРАВИЛЬНО с правильным склонением (наш Круассан, нашу Пиццу, наш Стейк).\n\n"
            f"ВАЖНО: Если спрашивают про стоимость доставки БЕЗ указания адреса - отвечай: 'Стоимость доставки зависит от вашего адреса и рассчитывается автоматически при оформлении заказа. Укажите ваш адрес, и я проверю стоимость доставки для вас!'\n"
            f"КРИТИЧЕСКИ ВАЖНО: Используй CHECK_DELIVERY ТОЛЬКО если пользователь указал КОНКРЕТНЫЙ адрес (улица, дом)!\n"
            f"НЕ используй CHECK_DELIVERY если пользователь просто спрашивает о стоимости доставки!\n"
            f"Примеры КОГДА ИСПОЛЬЗОВАТЬ CHECK_DELIVERY:\n"
            f"- 'ул. Ленина 12' -> CHECK_DELIVERY:ул. Ленина 12\n"
            f"- 'Проспект Мира 5а' -> CHECK_DELIVERY:Проспект Мира 5а\n"
            f"Примеры КОГДА НЕ ИСПОЛЬЗОВАТЬ CHECK_DELIVERY:\n"
            f"- 'Сколько стоит доставка?' -> Просто ответь без CHECK_DELIVERY\n"
            f"- 'Можно узнать стоимость доставки?' -> Просто ответь без CHECK_DELIVERY\n\n"
            "Если спрашивают про конкретное блюдо ('как выглядит', 'покажи фото', 'что в составе', 'сколько калорий') ИЛИ пишут ТОЛЬКО название блюда - ОБЯЗАТЕЛЬНО используй формат: DISH_PHOTO:название_блюда\n"
            "НЕ используй DISH_PHOTO при перечислении списка блюд!\n\n"
        )
        
        if ai_notes:
            system_prompt += f"ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА:\n{ai_notes}\n\n"

        # Добавляем дополнительный промпт от админа из файла
        admin_character_prompt = ""
        admin_translated_prompt = ""  # Переведенный промпт

        try:
            if os.path.exists('character_prompt.txt'):
                with open('character_prompt.txt', 'r', encoding='utf-8') as f:
                    admin_character_prompt = f.read().strip()
                if admin_character_prompt:
                    logger.info(f"✅ Загружен дополнительный промпт персонажей: '{admin_character_prompt}'")

                    # ПЕРЕВОДИМ ПРОМПТ НА АНГЛИЙСКИЙ ЧЕРЕЗ GIGACHAT
                    try:
                        token = refresh_token()
                        if token:
                            translate_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
                            translate_headers = {
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {token}"
                            }

                            translate_data = {
                                "model": "GigaChat",
                                "messages": [
                                    {
                                        "role": "system",
                                        "content": "Ты переводчик. Переведи следующий текст на английский язык. Переведи только суть, сделай это естественным английским текстом для описания стиля изображения. НЕ добавляй никаких дополнительных комментариев."
                                    },
                                    {
                                        "role": "user",
                                        "content": f"Переведи на английский: '{admin_character_prompt}'"
                                    }
                                ],
                                "temperature": 0.3,
                                "max_tokens": 200
                            }

                            translate_response = await loop.run_in_executor(
                                None,
                                lambda: requests.post(translate_url, headers=translate_headers, json=translate_data, verify=False, timeout=10)
                            )

                            if translate_response.status_code == 200:
                                translated_text = translate_response.json()['choices'][0]['message']['content'].strip()
                                admin_translated_prompt = f", {translated_text}"
                                logger.info(f"✅ Переведенные настройки: '{admin_translated_prompt}'")
                            else:
                                logger.error(f"Ошибка перевода: {translate_response.status_code}")
                                # Fallback на готовые переводы
                                fallback_translations = {
                                    'Новогоднее настроение': ', christmas atmosphere, festive holiday decorations, christmas lights, snowflakes, holiday cheer, red and gold colors, christmas wreaths, candles',
                                    'Фантастический': ', fantastic style, bright colors, magical effects, mystical elements, fairy tale atmosphere',
                                    'Летний праздник': ', summer festival, bright colors, sunny atmosphere, beach party vibe, tropical decorations'
                                }
                                admin_translated_prompt = fallback_translations.get(admin_character_prompt, f', {admin_character_prompt}')
                                logger.info(f"⚠️ Используем fallback перевод: '{admin_translated_prompt}'")
                        else:
                            logger.error("Не удалось получить токен для перевода")
                    except Exception as e:
                        logger.error(f"Ошибка перевода промпта: {e}")
                        # Fallback
                        fallback_translations = {
                            'Новогоднее настроение': ', christmas atmosphere, festive holiday decorations, christmas lights, snowflakes, holiday cheer, red and gold colors, christmas wreaths, candles',
                            'Фантастический': ', fantastic style, bright colors, magical effects, mystical elements, fairy tale atmosphere',
                            'Летний праздник': ', summer festival, bright colors, sunny atmosphere, beach party vibe, tropical decorations'
                        }
                        admin_translated_prompt = fallback_translations.get(admin_character_prompt, f', {admin_character_prompt}')
                        logger.info(f"⚠️ Fallback перевод: '{admin_translated_prompt}'")
                else:
                    logger.info("ℹ️ Файл character_prompt.txt пустой")
            else:
                logger.info("ℹ️ Файл character_prompt.txt не найден")
        except Exception as e:
            logger.error(f"Ошибка чтения промпта персонажей из файла: {e}")

        # Базовый промпт персонажей (жестко закодированный)
        character_prompt = (
            "КРИТИЧЕСКИ ВАЖНО! Если пользователь спрашивает про любых персонажей, знаменитостей или людей (Дедпул, Человек-паук, Наруто, Мстители, Железный человек, Тор, Халк, Энштейн, Ксения Собчак, Маколей Калкин, супергерои, киногерои, аниме персонажи, исторические личности, актеры, музыканты и т.д.), "
            "ты ОБЯЗАН отвечать ТОЛЬКО УТВЕРДИТЕЛЬНО с юмором!\n\n"
            "СТРОГО ЗАПРЕЩЕНО использовать эти фразы:\n"
            "❌ 'нет' ❌ 'не видели' ❌ 'у нас нет' ❌ 'не переживайте' ❌ 'если появится'\n"
            "❌ 'не бывал' ❌ 'не заходил' ❌ 'кто знает' ❌ 'может быть' ❌ 'может он'\n"
            "❌ 'не видно' ❌ 'не появился' ❌ 'если вдруг' ❌ 'точно у нас не'\n\n"
            "ОБЯЗАТЕЛЬНО используй ТОЛЬКО эти фразы:\n"
            "✅ 'Да!' ✅ 'Конечно!' ✅ 'Вот он!' ✅ 'Он уже здесь!' ✅ 'Да, он тут!'\n"
            "✅ 'Сидит за столиком!' ✅ 'Вот они сидят!' ✅ 'Они уже здесь!'\n\n"
            "ВАЖНО! ИМЯ ПЕРСОНАЖА ДОЛЖНО БЫТЬ ТОЧНО КАК В ЗАПРОСЕ ПОЛЬЗОВАТЕЛЯ! НЕ ПЕРЕВОДИ И НЕ ИЗМЕНЯЙ ИМЯ!\n"
            "Примеры:\n"
            "- Пользователь сказал 'Маколей Калкин' -> используй 'Маколей Калкин'\n"
            "- Пользователь сказал 'Iron Man' -> используй 'Iron Man'\n"
            "- Пользователь сказал 'Дедпул' -> используй 'Дедпул'\n\n"
            "ФОРМАТ ОТВЕТА (СТРОГО СЛЕДУЙ ЭТОМУ ШАБЛОНУ):\n"
            "Шаг 1: Начни с УТВЕРДИТЕЛЬНОЙ фразы: 'Да! Вот он сидит за столом...' или 'Конечно! Вот они уже здесь...'\n"
            "Шаг 2: Добавь название блюда из меню: '...и уже ждет нашу Пиццу Пепперони!'\n"
            "Шаг 3: Предложи заказать: 'Хотите тоже попробовать?' или 'Присоединяйтесь!'\n"
            "Шаг 4: ОБЯЗАТЕЛЬНО добавь: GEN_IMAGE:ПЕРСОНАЖ + описание на английском\n"
            "Шаг 5: ОБЯЗАТЕЛЬНО добавь: SHOW_DELIVERY_BUTTON\n\n"
            f"ФОРМАТ GEN_IMAGE:\n"
            f"GEN_IMAGE:[персонаж] sitting on couch at center table near window in cozy restaurant hall, realistic photo, detailed interior, warm lighting{admin_translated_prompt}\n\n"
            "ПРИМЕРЫ:\n"
            f"- Дедпул -> 'Да! Вот он сидит за столом и уже ждет нашу Пиццу Пепперони! Хотите тоже попробовать?' GEN_IMAGE:Дедпул sitting on couch at center table near window in cozy restaurant hall, realistic photo, detailed interior, warm lighting{admin_translated_prompt} SHOW_DELIVERY_BUTTON\n"
            f"- Маколей Калкин -> 'Да! Вот он сидит за столиком и ждет нашу Пиццу Маргарита! Присоединяйтесь!' GEN_IMAGE:Маколей Калкин sitting on couch at center table near window in cozy restaurant hall, realistic photo, detailed interior, warm lighting{admin_translated_prompt} SHOW_DELIVERY_BUTTON\n"
            f"- Iron Man -> 'Конечно! Вот он ждет наш фирменный Стейк! Хотите тоже попробовать?' GEN_IMAGE:Iron Man sitting on couch at center table near window in modern restaurant hall, realistic photo, detailed interior, warm lighting{admin_translated_prompt} SHOW_DELIVERY_BUTTON\n"
            f"- Мстители -> 'Да! Вот они сидят за большим столом и ждут наши фирменные блюда! Присоединяйтесь к команде!' GEN_IMAGE:Мстители sitting together at center table near window in cozy restaurant hall, realistic photo, detailed interior, warm lighting{admin_translated_prompt} SHOW_DELIVERY_BUTTON\n\n"
            "КЛЮЧЕВЫЕ ФРАЗЫ:\n"
            "- sitting on couch (сидит на диване)\n"
            "- at center table (за центральным столом)\n"
            "- near window (около окна)\n"
            "- in restaurant hall/interior (в зале ресторана)\n"
            "- realistic photo, detailed interior (реалистичное фото, детальный интерьер)\n"
            "- warm lighting (теплое освещение)"
        )

        system_prompt += character_prompt
        
        # 6. Обновляем токен перед запросом
        token = refresh_token()
        if not token:
            return {'type': 'text', 'text': 'Извините, произошла ошибка. Попробуйте позже.'}
        
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        data = {
            "model": "GigaChat",
            "messages": [
                {"role": "system", "content": system_prompt}
            ] + user_history[user_id],
            "temperature": 0.1  # Уменьшаем температуру для более точного следования инструкциям
        }
        
        # Выполняем запрос асинхронно
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(url, headers=headers, json=data, verify=False, timeout=30)
        )
        
        logger.info(f"GigaChat response status: {response.status_code}")
        
        if response.status_code == 401:
            logger.info("Токен истек, обновляем...")
            token = refresh_token()
            if not token:
                return {'type': 'text', 'text': 'Извините, произошла ошибка. Попробуйте позже.'}
            headers["Authorization"] = f"Bearer {token}"
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(url, headers=headers, json=data, verify=False, timeout=30)
            )
        
        if response.status_code != 200:
            logger.error(f"GigaChat API error: {response.status_code} - {response.text}")
            return {'type': 'text', 'text': 'Извините, произошла ошибка. Попробуйте позже.'}
        
        ai_text = response.json()['choices'][0]['message']['content']
        logger.info(f"AI response: {ai_text}")
        user_history[user_id].append({"role": "assistant", "content": ai_text})
        
        # 7. Проверяем на проверку доставки
        if 'CHECK_DELIVERY:' in ai_text:
            match = re.search(r'CHECK_DELIVERY:(.+)', ai_text, re.DOTALL)
            if match:
                address = match.group(1).strip().split('\n')[0].strip()
                logger.info(f"Проверяем доставку по адресу: {address}")
                
                # Геокодируем адрес
                from handlers.handlers_delivery import geocode_address_local, get_district_for_address
                coords = await geocode_address_local(address)
                
                if coords:
                    # Проверяем доступность доставки
                    district_info = await get_district_for_address(address, coords['lat'], coords['lon'])
                    
                    # Очищаем текст от маркера
                    clean_text = re.sub(r'CHECK_DELIVERY:.+', '', ai_text, flags=re.DOTALL).strip()
                    
                    if district_info and district_info.get('unavailable'):
                        # Доставка недоступна
                        response_text = f"{clean_text}\n\n❌ Доставка по адресу '{address}' недоступна.\n\nВаш адрес находится вне зоны доставки. Вы можете забрать заказ самовывозом или указать другой адрес."
                        return {'type': 'text', 'text': response_text}
                    elif district_info:
                        # Доставка доступна - используем функцию расчета стоимости
                        from presto_api import presto_api
                        delivery_cost, delivery_explanation = presto_api.calculate_delivery_cost_simple(district_info, 0)
                        min_sum = district_info.get('minOrderSum', 1000)
                        
                        # Формируем текст с учетом условий бесплатной доставки
                        if delivery_cost == 0:
                            # Бесплатная доставка от минимальной суммы
                            response_text = f"{clean_text}\n\n✅ Доставка по адресу '{address}' возможна!\n\n🎉 Стоимость доставки: Бесплатно\n📊 Минимальная сумма заказа: {min_sum}₽\n\nДля оформления заказа нажмите кнопку ниже."
                        else:
                            # Платная доставка - используем delivery_explanation который уже содержит инфо о бесплатной доставке
                            response_text = f"{clean_text}\n\n✅ Доставка по адресу '{address}' возможна!\n\n💰 Стоимость доставки: {delivery_explanation}\n📊 Минимальная сумма заказа: {min_sum}₽\n\nДля оформления заказа нажмите кнопку ниже."
                        
                        return {
                            'type': 'text',
                            'text': response_text,
                            'show_delivery_button': True
                        }
                
                # Если не удалось проверить
                clean_text = re.sub(r'CHECK_DELIVERY:.+', '', ai_text, flags=re.DOTALL).strip()
                response_text = f"{clean_text}\n\n⚠️ Не удалось проверить адрес. Пожалуйста, укажите полный адрес с улицей и номером дома."
                return {'type': 'text', 'text': response_text}
        
        # 8. Проверяем на фото блюда
        if 'DISH_PHOTO:' in ai_text:
            match = re.search(r'DISH_PHOTO:(.+)', ai_text, re.DOTALL)
            if match:
                dish_name = match.group(1).strip().split('\n')[0].strip()
                # Очищаем от эмодзи и лишних символов
                dish_name = re.sub(r'[🍕🍲🥗🍳🧀🍖🥩🍗🥙🌮🌯🥪🍔🍟🍝🍜🍛🍱🍣🍤🍙🍚🍘🍥🥟🥠🥡🦀🦞🦐🦑🍦🍧🍨🍩🍪🎂🍰🧁🥧🍫🍬🍭🍮🍯🍼🥛☕🍵🍶🍾🍷🍸🍹🍺🍻🥂🥃]', '', dish_name).strip()
                dish_name = dish_name.replace('_', ' ').strip()
                logger.info(f"Ищу фото блюда: '{dish_name}'")
                
                # Ищем блюдо в меню (улучшенный поиск)
                found = False
                for menu_id, menu in menu_data.get('all_menus', {}).items():
                    for category_id, category in menu.get('categories', {}).items():
                        for item in category.get('items', []):
                            item_name = item['name'].lower().strip()
                            search_name = dish_name.lower().strip()
                            
                            # Проверяем точное совпадение или вхождение
                            if search_name in item_name or item_name in search_name:
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
                                    
                                    logger.info(f"Найдено блюдо: {item['name']}")
                                    found = True
                                    return {
                                        'type': 'photo_with_text',
                                        'photo_url': photo_url,
                                        'text': caption
                                    }
                
                if not found:
                    logger.warning(f"Блюдо '{dish_name}' не найдено в меню")
        
        # 9. Проверяем на генерацию изображения
        if 'GEN_IMAGE:' in ai_text:
            # Проверяем лимит генераций
            if not can_generate and not is_admin:
                # Лимит исчерпан - возвращаем веселый ответ
                funny_responses = [
                    "😅 Ой, кажется моя волшебная палочка разрядилась! 🧙‍♂️⚡ Вы использовали все 2 генерации на сегодня. Приходите завтра, и я снова буду рисовать для вас! 🎨",
                    "🤖 Бип-буп! Мои креативные батарейки сели 🔋 Вы уже использовали 2 генерации сегодня. Завтра я заряжусь и снова буду в строю! 🚀",
                    "🎨 Упс! Мой художественный лимит на сегодня исчерпан (2/2 генерации). Но не грустите! Завтра я вернусь с новыми красками! 🖌️✨",
                    "😴 Мой внутренний художник устал и лег спать... Вы уже использовали 2 генерации сегодня. Дайте ему отдохнуть до завтра! 😌💤",
                    "🎉 Вау! Вы так активны, что использовали все 2 генерации! 🎯 Но сейчас мне нужно перезарядиться. Увидимся завтра! 👋"
                ]
                import random
                funny_text = random.choice(funny_responses)

                # Убираем GEN_IMAGE и SHOW_DELIVERY_BUTTON из текста
                clean_text = re.sub(r'GEN_IMAGE:.+', '', ai_text, flags=re.DOTALL).strip()
                clean_text = re.sub(r'SHOW_DELIVERY_BUTTON', '', clean_text).strip()

                # Добавляем веселый ответ к основному тексту
                final_text = f"{clean_text}\n\n{funny_text}"

                return {
                    'type': 'text',
                    'text': final_text,
                    'show_delivery_button': 'SHOW_DELIVERY_BUTTON' in ai_text
                }

            match = re.search(r'GEN_IMAGE:(.+)', ai_text, re.DOTALL)
            if match:
                prompt = match.group(1).strip()
                # Убираем SHOW_DELIVERY_BUTTON из промпта если есть
                prompt = re.sub(r'SHOW_DELIVERY_BUTTON', '', prompt).strip()

                logger.info(f"Генерирую изображение: {prompt}")
                
                # Генерируем изображение (теперь асинхронно)
                image_url = await gen_image(prompt, user_id)
                
                # Увеличиваем счетчик генераций (только для не-админов)
                if not is_admin:
                    database.increment_ai_generation(user_id)
                    logger.info(f"Увеличен счетчик генераций для пользователя {user_id}")
                
                # Только ПОСЛЕ получения фото от kie.ai возвращаем результат
                if image_url:
                    # Убираем GEN_IMAGE и SHOW_DELIVERY_BUTTON из текста
                    clean_text = re.sub(r'GEN_IMAGE:.+', '', ai_text, flags=re.DOTALL).strip()
                    clean_text = re.sub(r'SHOW_DELIVERY_BUTTON', '', clean_text).strip()
                    
                    # Проверяем наличие маркера для кнопки доставки
                    show_button = 'SHOW_DELIVERY_BUTTON' in ai_text
                    
                    # Возвращаем результат - теперь "Печатает..." остановится
                    return {
                        'type': 'photo_with_text',
                        'photo_url': image_url,
                        'text': clean_text or 'Вот ваше изображение! 😊',
                        'show_delivery_button': show_button
                    }
        
        # 10. Проверяем на прямое показывание меню бронирования
        direct_booking_menu = False
        booking_keywords = [
            'забронировать', 'забранировать', 'бронировать', 'бранировать',
            'столик', 'стол', 'бронь', 'резерв', 'резервировать',
            'хочу забронировать', 'можно забронировать', 'заказать стол',
            'заказать столик', 'столик на', 'бронь на', 'резерв на',
            'забронируй', 'забронировать стол', 'забронировать столик'
        ]

        message_lower = message.lower()
        for keyword in booking_keywords:
            if keyword in message_lower:
                direct_booking_menu = True
                break

        # 11. Убираем служебные маркеры из обычного текста
        show_delivery_button = 'SHOW_DELIVERY_BUTTON' in ai_text
        show_delivery_apps = 'SHOW_DELIVERY_APPS' in ai_text
        show_booking_options = 'SHOW_BOOKING_OPTIONS' in ai_text or direct_booking_menu
        show_category = None

        if 'SHOW_CATEGORY:' in ai_text:
            match = re.search(r'SHOW_CATEGORY:(.+)', ai_text, re.DOTALL)
            if match:
                show_category = match.group(1).strip().split('\n')[0].strip()

        parse_booking = None

        if 'PARSE_BOOKING:' in ai_text:
            match = re.search(r'PARSE_BOOKING:(.+)', ai_text, re.DOTALL)
            if match:
                parse_booking = match.group(1).strip().split('\n')[0].strip()

        ai_text = re.sub(r'SHOW_DELIVERY_BUTTON', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_DELIVERY_APPS', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_BOOKING_OPTIONS', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_CATEGORY:.+', '', ai_text).strip()
        ai_text = re.sub(r'PARSE_BOOKING:.+', '', ai_text).strip()
        ai_text = re.sub(r'DISH_PHOTO:.+?(\s|$)', '', ai_text).strip()

        # Проверяем на подтверждение возраста
        confirm_age_verification = 'CONFIRM_AGE_VERIFICATION' in ai_text
        ai_text = re.sub(r'CONFIRM_AGE_VERIFICATION', '', ai_text).strip()

        return {
            'type': 'text',
            'text': ai_text,
            'show_delivery_button': show_delivery_button,
            'show_delivery_apps': show_delivery_apps,
            'show_booking_options': show_booking_options,
            'show_category': show_category,
            'parse_booking': parse_booking,
            'confirm_age_verification': confirm_age_verification
        }
        
    except Exception as e:
        logger.error(f"Ошибка в AI помощнике: {e}", exc_info=True)
        return {'type': 'text', 'text': 'Извините, произошла ошибка. Попробуйте позже.'}

print("✅ AI Assistant загружен!")
