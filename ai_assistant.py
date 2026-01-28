"""
ai_assistant.py - AI помощник для общения с пользователями
"""

import asyncio
import json
import subprocess
import os
import re
import random
from typing import Optional, Dict, List, Any
import logging
import database
import cache_manager
import config

# Импорт requests
import requests

logger = logging.getLogger(__name__)

# 🛑 СПИСОК ЗАПРЕЩЕННЫХ КАТЕГОРИЙ (Blacklist) для AI
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

# История сообщений пользователей
user_history: Dict[int, List[Dict]] = {}

def _normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[–—-]+', ' ', s)
    s = re.sub(r'[\"\'“”„«».,?!:;()]', '', s) # Удаляем пунктуацию
    s = re.sub(r'\s+', ' ', s)
    s = s.replace('четыре', '4')
    s = s.replace('пять', '5')
    s = s.replace('шесть', '6')
    s = s.replace('семь', '7')
    s = s.replace('восемь', '8')
    s = s.replace('девять', '9')
    s = s.replace('десять', '10')
    s = s.strip()
    return s

def _specific_tokens(s: str) -> List[str]:
    s = _normalize_text(s)
    tokens = [t for t in re.split(r'[\s\-]+', s) if t]
    stop = {'пицца','суп','салат','десерт','напиток','напитки','вино','пиво','бургер','паста','и','в','на','про','что','какой','какая','какие','есть','для','с','по','у','из','от'}
    return [t for t in tokens if t not in stop and len(t) > 1]

def _stem_word(word: str) -> str:
    """Простой стемминг для русского языка (удаление окончаний)"""
    # Сортируем окончания по длине (сначала длинные)
    endings = ['ами', 'ями', 'ов', 'ев', 'ей', 'ом', 'ем', 'ах', 'ях', 'ую', 'юю', 'ая', 'яя', 'ое', 'ее', 'ый', 'ий', 'ые', 'ие', 'ой', 'ей', 'а', 'я', 'о', 'е', 'ы', 'и', 'у', 'ю']
    word_lower = word.lower()
    for end in endings:
        if word_lower.endswith(end) and len(word_lower) > len(end) + 1:
             return word_lower[:-len(end)]
    return word_lower

def _stem_text(text: str) -> str:
    words = re.split(r'[\s\-]+', _normalize_text(text))
    return ' '.join([_stem_word(w) for w in words if w])


def find_similar_dishes(menu_data: Dict, query: str) -> List[Dict]:
    results = []
    q_norm = _normalize_text(query)
    q_tokens = _specific_tokens(query)
    for menu_id, menu in menu_data.items():
        for category_id, category in menu.get('categories', {}).items():
            for item in category.get('items', []):
                name = item.get('name', '')
                n_norm = _normalize_text(name)
                n_tokens = _specific_tokens(name)
                score = 0
                if n_norm == q_norm:
                    score = 1000
                elif q_norm and (n_norm.startswith(q_norm) or q_norm in n_norm or n_norm in q_norm):
                    score = 900
                else:
                    inter = set(q_tokens) & set(n_tokens)
                    if inter:
                        score = 100 + 50 * len(inter)
                if score > 0:
                    results.append((item, score))
    results.sort(key=lambda x: x[1], reverse=True)
    return [item for item, score in results]

def load_token() -> str:
    """Загрузка токена AI (используем вшитый токен)"""
    return refresh_token()

def refresh_token() -> str:
    """Получение токена Polza AI (постоянный токен)"""
    # Постоянный токен Polza AI - вшитый в код
    polza_token = "ak_NYI27neWOiQniROZ1SkUDSwotl6XIUvY87fCjNnSvWw"
    logger.info("Polza AI токен загружен из кода")
    return polza_token

def load_menu_cache() -> Dict:
    """Загрузка кэша всех меню для AI с приоритетом доставки"""
    try:
        all_menus = {}
        
        # 1. Сначала загружаем меню доставки (menu_cache.json) - ЭТО ПРИОРИТЕТ
        delivery_cache_file = 'files/menu_cache.json'
        if os.path.exists(delivery_cache_file):
            try:
                with open(delivery_cache_file, 'r', encoding='utf-8') as f:
                    delivery_data = json.load(f)
                    delivery_menus = delivery_data.get('all_menus', {})
                    if delivery_menus:
                        all_menus.update(delivery_menus)
                        logger.info(f"AI: Загружено {len(delivery_menus)} меню из кэша доставки")
            except Exception as e:
                logger.error(f"AI: Ошибка загрузки menu_cache.json: {e}")

        # 2. Затем загружаем общий кэш (all_menus_cache.json) и добавляем то, чего нет
        all_cache_file = 'files/all_menus_cache.json'
        if os.path.exists(all_cache_file):
            try:
                with open(all_cache_file, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
                    other_menus = all_data.get('all_menus', {})
                    
                    # Добавляем только те меню, которых еще нет (или обновляем существующие, если в общем кэше полнее? 
                    # Нет, пользователь просил приоритет menu_cache.json, значит не перезаписываем)
                    for m_id, m_data in other_menus.items():
                        if m_id not in all_menus:
                            all_menus[m_id] = m_data
                            
                    logger.info(f"AI: Догружено из общего кэша. Всего меню: {len(all_menus)}")
            except Exception as e:
                logger.error(f"AI: Ошибка загрузки all_menus_cache.json: {e}")

        return all_menus
    except Exception as e:
        logger.error(f"Ошибка загрузки кэша меню для AI: {e}")
        return {}

def get_ai_notes() -> str:
    """Получение дополнительных примечаний для ИИ из БД"""
    return database.get_setting('ai_notes', '')

def search_in_faq(query: str) -> Optional[str]:
    """Поиск ответа в FAQ с улучшенной логикой"""
    faq_list = database.get_faq()
    query_lower = query.lower().strip()

    kids_keywords = ['детск', 'детское меню', 'ребен', 'дети', 'детский']
    if any(kw in query_lower for kw in kids_keywords):
        for faq_id, question, answer in faq_list:
            ql = question.lower().strip()
            al = str(answer).lower().strip()
            if 'дет' in ql or 'детск' in al:
                return answer
        return "Да, у нас есть детское меню и высокие стульчики для малышей."

    # Ключевые слова, которые НЕ должны возвращать FAQ о доставке/парковке
    menu_keywords = ['пиво', 'водка', 'вино', 'вина', 'джин', 'ром', 'виски', 'текила', 'коньяк', 'ликер', 'коктейль', 'салат', 'суп', 'паста', 'пицца', 'бургер', 'стейк', 'рыба', 'мясо', 'десерт', 'торт', 'мороженое', 'кофе', 'чай', 'сок', 'вода']

    # Если запрос содержит ключевые слова меню - НЕ ищем в FAQ
    if any(keyword in query_lower for keyword in menu_keywords):
        return None

    # Точное совпадение (более строгое)
    for faq_id, question, answer in faq_list:
        question_lower = question.lower().strip()
        # Проверяем точное совпадение или очень близкое
        if query_lower == question_lower or question_lower in query_lower:
            return answer

    # Поиск по ключевым словам с фильтрацией
    from difflib import SequenceMatcher
    best_match = None
    best_score = 0.0

    for faq_id, question, answer in faq_list:
        question_lower = question.lower().strip()
        score = SequenceMatcher(None, query_lower, question_lower).ratio()

        # Фильтруем неподходящие совпадения
        if 'доставк' in answer.lower() and any(menu_word in query_lower for menu_word in menu_keywords):
            continue  # Не возвращаем доставку для вопросов о меню
        if 'парковк' in answer.lower() and any(menu_word in query_lower for menu_word in menu_keywords):
            continue  # Не возвращаем парковку для вопросов о меню

        if score > best_score:
            best_score = score
            best_match = answer

    # Возвращаем только если совпадение > 70% (более строго)
    if best_score > 0.7:
        return best_match

    return None

def check_existing_character_generation(character_name: str) -> Optional[Dict[str, Any]]:
    """Проверка существующих генераций персонажа"""
    try:
        with database.get_cursor() as cursor:
            cursor.execute('''
            SELECT character_name, dish_name, image_url, created_at
            FROM character_generations
            WHERE character_name = ?
            ORDER BY created_at DESC
            LIMIT 1
            ''', (character_name,))

            result = cursor.fetchone()
            if result:
                return {
                    'character_name': result[0],
                    'dish_name': result[1],
                    'image_url': result[2],
                    'created_at': result[3]
                }
        return None
    except Exception as e:
        logger.error(f"Ошибка проверки существующих генераций: {e}")
        return None

async def gen_image(character_name: str, user_id: int = 0, admin_prompt: str = "", forced_dish: Optional[Dict] = None) -> Optional[str]:
    """Генерация изображения через Kie AI"""
    try:
        import random
        from character_parser import ensure_character_references, get_character_reference_images, save_character_result, character_parser

        # Проверяем, есть ли уже сгенерированный персонаж
        existing_generation = check_existing_character_generation(character_name)
        if existing_generation:
            logger.info(f"🎯 Персонаж '{character_name}' уже генерировался ранее, используем существующие данные")
            logger.info(f"📸 Существующее изображение: {existing_generation['image_url']}")
            logger.info(f"🍽️ Блюдо из предыдущей генерации: {existing_generation['dish_name']}")

            # Возвращаем существующий URL вместо генерации нового
            return existing_generation['image_url']

        # Получаем меню для выбора случайного блюда
        random_dish = None
        if forced_dish:
            random_dish = forced_dish
            logger.info(f"🍽️ Используем предвыбранное блюдо: {random_dish['name']}")
        else:
            menu_data = load_menu_cache()
            random_dish = get_random_delivery_dish(menu_data)

        # Создаем базовый английский промпт - подчеркиваем реализм
        if random_dish:
            prompt = f"{character_name} sitting at a restaurant table with {random_dish['name'].lower()} on the table, character is eating the food, extremely photorealistic image, real people not cartoon, highly detailed facial features, professional photography, natural lighting, authentic restaurant atmosphere, food clearly visible on table"
        else:
            prompt = f"{character_name} sitting at a restaurant table with food on the table, extremely photorealistic image, real people not cartoon, highly detailed facial features, professional photography, natural lighting, authentic restaurant atmosphere"

        # Добавляем админский промпт если есть
        if admin_prompt:
            prompt += f", {admin_prompt}"

        # Выбираем фото стола: 2 для одиночных персонажей, 1 для компании
        single_character_images = [
            'files/tables_holl.jpg',  # диван у окна
            'files/table_for_1.jpg'   # столик на двоих
        ]
        company_image = 'files/big_table.jpg'  # большой стол для компании

        # Определяем через AI является ли персонаж одиночным или группой
        is_group = False  # Default to single

        # Проверяем на известные группы сначала (быстрый способ)
        group_keywords = [
            'черепашки ниндзя', 'teenage mutant ninja turtles', 'tmnt', 'ninja turtles',
            'мстители', 'avengers', 'avengers team',
            'команда', 'team', 'группа', 'group',
            'семья', 'family', 'банда', 'gang', 'отряд', 'squad',
            'герои', 'heroes', 'супергерои', 'superheroes',
            'мстители marvel', 'marvel avengers',
            'черепашки-ниндзя', 'черепашкининдзя'
        ]

        character_lower = character_name.lower()
        for keyword in group_keywords:
            if keyword in character_lower:
                is_group = True
                logger.info(f"🎯 Быстро определено как ГРУППА по ключевому слову '{keyword}': '{character_name}'")
                break

        # Если не нашли по ключевым словам, используем AI
        if not is_group:
            try:
                # Получаем токен Polza AI
                ai_token = refresh_token()
                if ai_token:
                    logger.info(f"🤖 Запрашиваем AI анализ для: '{character_name}'")

                    # Запрашиваем у AI определение типа персонажа
                    character_analysis_url = "https://api.polza.ai/api/v1/chat/completions"
                    character_analysis_data = {
                        "model": "google/gemini-2.5-flash-lite",
                        "messages": [
                            {
                                "role": "system",
                                "content": "Ты анализируешь имена персонажей. Определи: является ли это одиночным персонажем или группой/командой? Ответь ТОЛЬКО одним словом: 'single' или 'group'. Примеры: 'Дарт Вейдер' -> 'single', 'Мстители' -> 'group', 'Черепашки Ниндзя' -> 'group', 'Супермен' -> 'single', 'Бэтмен' -> 'single', 'Адам' -> 'single'."
                            },
                            {
                                "role": "user",
                                "content": f"Определи тип персонажа: {character_name}"
                            }
                        ],
                        "stream": False,
                        "max_tokens": 10,
                        "temperature": 0.1
                    }

                    character_response = requests.post(
                        character_analysis_url,
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {ai_token}"},
                        json=character_analysis_data,
                        timeout=10
                    )

                    if character_response.status_code == 201:
                        analysis_result = character_response.json()
                        ai_answer = analysis_result.get('choices', [{}])[0].get('message', {}).get('content', '').strip().lower()

                        logger.info(f"🤖 AI ответил: '{ai_answer}' для '{character_name}'")

                        if 'group' in ai_answer:
                            is_group = True
                            logger.info(f"🤖 AI определил '{character_name}' как ГРУППУ")
                        elif 'single' in ai_answer:
                            is_group = False
                            logger.info(f"🤖 AI определил '{character_name}' как ОДИНОЧНОГО ПЕРСОНАЖА")
                        else:
                            logger.warning(f"⚠️ AI вернул непонятный ответ: '{ai_answer}', считаем одиночным")
                            is_group = False
                    else:
                        logger.error(f"⚠️ Ошибка запроса к AI: {character_response.status_code}, считаем одиночным")
                        is_group = False
                else:
                    logger.warning("⚠️ Нет токена AI, используем fallback логику")
                    is_group = False
            except Exception as e:
                logger.error(f"Ошибка определения типа персонажа через AI: {e}, считаем одиночным")
                is_group = False

        if is_group:
            # Для группы/компании - используем большой стол
            selected_image = company_image
            logger.info(f"👥 Группа/команда '{character_name}', используем большой стол: {selected_image}")
        else:
            # Для одиночных персонажей - выбираем случайное из 2 вариантов
            selected_image = random.choice(single_character_images)
            logger.info(f"👤 Одиночный персонаж '{character_name}', случайно выбрана таблица: {selected_image}")

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

        # Собираем все изображения для генерации
        image_urls = [table_url]

        # Добавляем фото блюда если оно есть
        if random_dish and random_dish.get('image_url'):
            try:
                # Загружаем фото блюда на freeimage.host
                dish_response = requests.get(random_dish['image_url'], timeout=10)
                if dish_response.status_code == 200:
                    files = {'source': ('dish.jpg', dish_response.content, 'image/jpeg')}
                    upload_response = requests.post(
                        "https://freeimage.host/api/1/upload",
                        files=files,
                        data={'key': '6d207e02198a847aa98d0a2a901485a5'}
                    )

                    if upload_response.status_code == 200:
                        dish_url = upload_response.json()['image']['url']
                        image_urls.append(dish_url)
                        logger.info(f"Фото блюда загружено: {dish_url} ({random_dish['name']})")
                    else:
                        logger.warning(f"Не удалось загрузить фото блюда: {upload_response.status_code}")
                else:
                    logger.warning(f"Не удалось скачать фото блюда: {dish_response.status_code}")
            except Exception as e:
                logger.error(f"Ошибка загрузки фото блюда: {e}")

        # Если есть персонаж, решаем использовать ли референсы
        character_refs = []
        if character_name:
            logger.info(f"Обнаружен персонаж: {character_name}")

            # Определяем популярность персонажа - для известных не используем референсы
            popular_characters = [
                'мстители', 'avengers', 'супермен', 'superman', 'бэтмен', 'batman',
                'спайдермен', 'spiderman', 'человек-паук', 'spider-man', 'тор', 'thor',
                'железный человек', 'iron man', 'ironman', 'капитан америка', 'captain america',
                'халк', 'hulk', 'черная вдова', 'black widow', 'чудо-женщина', 'wonder woman',
                'флэш', 'flash', 'зеленый фонарь', 'green lantern', 'аквамэн', 'aquaman',
                'джокер', 'joker', 'дарт вейдер', 'darth vader', 'люк скайуокер', 'luke skywalker',
                'гарри поттер', 'harry potter', 'гермиона', 'hermione', 'рон', 'ron weasley',
                'человек-паук', 'spider-man', 'дедпул', 'deadpool', 'шрек', 'shrek',
                'гарфилд', 'garfield', 'ску би-ду', 'scooby-doo', 'симпсоны', 'simpsons',
                'миньоны', 'minions', 'гравити фолз', 'gravity falls'
            ]

            is_popular = any(popular_name.lower() in character_name.lower() or
                           character_name.lower() in popular_name.lower()
                           for popular_name in popular_characters)

            if not is_popular:
                # Для непопулярных персонажей используем 1 референс
                logger.info(f"Персонаж '{character_name}' не является популярным - используем 1 референс")
                ref_paths = await ensure_character_references(character_name, 1)
                if ref_paths:
                    # Загружаем только первый референс
                    ref_path = ref_paths[0]
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
            else:
                logger.info(f"Персонаж '{character_name}' является популярным - не используем референсы, полагаемся на текстовое описание")

            # Всегда добавляем детальное описание стола
            table_descriptions = {
                'files/tables_holl.jpg': 'modern wooden restaurant table with comfortable chairs, warm lighting, elegant table setting with white tablecloth, wine glasses, and sophisticated dining atmosphere',
                'files/table_for_1.jpg': 'cozy single-person dining table with comfortable armchair, intimate lighting, elegant tableware, and warm welcoming atmosphere',
                'files/big_table.jpg': 'large rectangular banquet table for groups, multiple comfortable chairs, festive table setting, group dining atmosphere'
            }

            table_description = table_descriptions.get(selected_image, 'elegant restaurant table with comfortable chairs, warm lighting, and sophisticated dining atmosphere')

            prompt = f"{prompt}, {table_description}, photorealistic restaurant interior, detailed table and chair design, authentic dining environment, NO TEXT, NO WRITING, NO LETTERS, NO WORDS, NO CAPTIONS, NO LABELS, NO SIGNS, NO LOGOS, absolutely no text of any kind on the image"

        logger.info(f"Подготовлено изображений для генерации: {len(image_urls)}")

        # Создаем задачу редактирования через Kie AI
        url = "https://api.kie.ai/api/v1/jobs/createTask"
        headers = {
            "Authorization": "Bearer d6bd19312c6a075f3418d68ee943bda0",
            "Content-Type": "application/json"
        }

        # Если есть только фото стола (без референсов), делаем запрос на добавление персонажа на стол
        if len(image_urls) == 1:
            # Для одиночных персонажей - добавляем персонажа на существующий стол
            table_image_url = image_urls[0]
            data = {
                "model": "google/nano-banana-edit",
                "input": {
                    "prompt": f"Add {character_name} sitting at the restaurant table. {prompt}. Keep the same table and restaurant interior, just add the character sitting at the table naturally.",
                    "image_urls": [table_image_url],
                    "output_format": "png",
                    "image_size": "1:1"
                }
            }
        else:
            # Если есть референсы - используем стандартный подход
            data = {
                "model": "google/nano-banana-edit",
                "input": {
                    "prompt": prompt,
                    "image_urls": image_urls,
                    "output_format": "png",
                    "image_size": "1:1"
                }
            }

        logger.info(f"Отправляю запрос на редактирование через Kie AI...")
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
                            await save_character_result(character_name, user_id, prompt, image_url, character_refs)
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

async def check_and_reset_ai_limit(user_id: int) -> None:
    """
    Проверяет изменение баланса бонусов и сбрасывает лимит генераций если баланс увеличился
    """
    try:
        # Получаем UUID пользователя
        user_data = database.get_user_complete_data(user_id)
        if not user_data or not user_data.get('presto_uuid'):
            return

        # Получаем текущий баланс бонусов
        from presto_api import presto_api
        current_balance = await presto_api.get_bonus_balance(user_data['presto_uuid'])

        if current_balance is None:
            return

        # Получаем последний известный баланс из БД
        last_balance_key = f'bonus_balance_{user_id}'
        last_balance = database.get_setting(last_balance_key, '0')

        try:
            last_balance = float(last_balance)
        except (ValueError, TypeError):
            last_balance = 0.0

        # Если баланс увеличился - сбрасываем счетчик генераций
        if current_balance > last_balance:
            logger.info(f"Баланс бонусов пользователя {user_id} увеличился: {last_balance}₽ → {current_balance}₽, сбрасываем лимит генераций")

            # Сбрасываем счетчик генераций в БД
            database.execute_query("UPDATE users SET ai_generations = 0 WHERE user_id = ?", (user_id,))

            # Сохраняем новый баланс
            database.update_setting(last_balance_key, str(current_balance))

            # Уведомляем пользователя
            try:
                from aiogram import Bot
                from config import BOT_TOKEN
                if BOT_TOKEN:
                    bot = Bot(token=BOT_TOKEN)
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"🎉 <b>Спасибо за заказ!</b>\n\n"
                             f"💰 Ваш баланс бонусов: {current_balance:.0f}₽\n"
                             f"🎨 Лимит генераций изображений сброшен!\n\n"
                             f"Теперь вы можете сгенерировать ещё 2 изображения персонажей сегодня!",
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о сбросе лимита: {e}")

        # Обновляем баланс в БД независимо от изменений
        database.update_setting(last_balance_key, str(current_balance))

    except Exception as e:
        logger.error(f"Ошибка проверки баланса бонусов для пользователя {user_id}: {e}")

def add_bot_message_to_history(user_id: int, message_text: str):
    """
    Manually adds a bot message to the user's history context.
    Useful when the bot sends a message via handlers (not AI generated) but we want AI to know about it.
    """
    if user_id not in user_history:
        user_history[user_id] = []
    
    user_history[user_id].append({"role": "assistant", "content": message_text})
    
    # Trim history if needed
    if len(user_history[user_id]) > 20:
        user_history[user_id] = user_history[user_id][-20:]
    
    logger.info(f"Manually added bot message to history for user {user_id}: {message_text[:50]}...")

async def get_ai_response(message: str, user_id: int) -> dict:
    """
    Получение ответа от AI

    Returns:
        Dict с ключами:
        - type: 'text' | 'photo' | 'photo_with_text'
        - text: текст ответа
        - photo_url: URL фото (если type='photo' или 'photo_with_text')
    """
    search_query_result = None
    try:
        message_lower = message.lower().strip()
        mac_greetings = ['мак', 'макс', 'привет мак', 'привет макс', 'мак,', 'макс,', 'мак!', 'макс!']

        # Если сообщение начинается с обращения к Маку
        is_mac_greeting = any(message_lower.startswith(greeting) for greeting in mac_greetings) or message_lower in mac_greetings

        faq_answer_fast = search_in_faq(message)
        if faq_answer_fast:
            return {'type': 'text', 'text': faq_answer_fast}

        recommendation_keywords = ['посоветуй', 'рекомендуй', 'что-то с', 'какое-нибудь', 'хочу', 'подскажи', 'есть ли', 'а есть', 'что есть', 'что взять', 'выбери', 'предложи']
        is_recommendation = any(keyword in message_lower for keyword in recommendation_keywords)

        # Проверка запроса списка завтраков (более расширенная)
        breakfast_queries = [
            'завтрак', 'завтраки', 'меню завтраков', 'меню завтрак', 'завтраки меню',
            'какие завтраки', 'какие завтраки?', 'какие завтраки есть', 'какие завтраки есть?',
            'что на завтрак', 'что на завтрак?', 'какие есть завтраки', 'какие есть завтраки?',
            'список завтраков', 'покажи завтраки', 'есть завтраки', 'есть завтраки?'
        ]
        
        # Очищаем сообщение от знаков препинания для проверки
        clean_message = re.sub(r'[^\w\s]', '', message_lower).strip()
        breakfast_clean = [re.sub(r'[^\w\s]', '', q).strip() for q in breakfast_queries]
        
        if clean_message in breakfast_clean or message_lower in breakfast_queries:
            assistant_text = '🍳 У нас есть отличные завтраки!'
            if user_id not in user_history:
                user_history[user_id] = []
            user_history[user_id].append({"role": "user", "content": message})
            user_history[user_id].append({"role": "assistant", "content": assistant_text})
            if len(user_history[user_id]) > 20:
                user_history[user_id] = user_history[user_id][-20:]
            return {
                'type': 'text',
                'text': assistant_text,
                'show_category_brief': 'завтраки'
            }

        # Проверка запроса списка салатов (более расширенная)
        salad_queries = [
            'салат', 'салаты', 'меню салатов', 'меню салат', 'салаты меню',
            'какие салаты', 'какие салаты?', 'какие салаты есть', 'какие салаты есть?',
            'какие салаты у вас есть', 'какие салаты у вас есть?', 'какие у вас салаты',
            'что за салаты', 'что за салаты?', 'какие есть салаты', 'какие есть салаты?',
            'список салатов', 'покажи салаты', 'есть салаты', 'есть салаты?'
        ]
        
        salad_clean = [re.sub(r'[^\w\s]', '', q).strip() for q in salad_queries]
        
        if clean_message in salad_clean or message_lower in salad_queries:
            return {
                'type': 'text',
                'text': '🥗 У нас есть отличные салаты!',
                'show_category_brief': 'салаты'
            }

        # Проверка запроса списка горячих блюд
        hot_dishes_queries = [
            'горячее', 'горячие', 'горячие блюда', 'горячие блюжа',
            'меню горячего', 'меню горячих', 'меню горячих блюд',
            'какие горячие', 'какие горячие?', 'какие горячие блюда', 'какие горячие блюда?',
            'какие горячие блюда у вас есть', 'какие горячие блюда у вас есть?', 'какие у вас горячие блюда',
            'что на горячее', 'что на горячее?', 'какие есть горячие', 'какие есть горячие блюда?',
            'список горячего', 'покажи горячее', 'есть горячее', 'есть горячее?',
            'что у вас из горячего', 'что у вас из горячего?'
        ]
        
        hot_dishes_clean = [re.sub(r'[^\w\s]', '', q).strip() for q in hot_dishes_queries]
        
        if clean_message in hot_dishes_clean or message_lower in hot_dishes_queries:
            return {
                'type': 'text',
                'text': '🍲 У нас есть отличные горячие блюда!',
                'show_category_brief': 'горячие блюда'
            }

        # Проверка запроса списка категорий
        categories_queries = [
            'какие категории', 'какие категории?', 'какие есть категории', 'какие есть категории?',
            'список категорий', 'категории меню', 'категории', 'покажи категории',
            'какие разделы', 'разделы меню', 'что есть поесть', 'что есть поесть?'
        ]
        
        if any(q in message_lower for q in categories_queries):
             return {
                'type': 'text',
                'text': '🍽️ Вот какие категории блюд у нас есть:',
                'show_all_categories': True
            }

        # Проверка запроса меню (точное совпадение, без ложных срабатываний на 'детское меню')
        menu_queries = [
            'покажи меню', 'меню', 'хочу меню', 'список меню', 'какое меню',
            'посмотреть меню', 'глянуть меню', 'меню ресторана', 'основное меню'
        ]
        menu_clean = [re.sub(r'[^\w\s]', '', q).strip() for q in menu_queries]
        if clean_message in menu_clean or message_lower in menu_queries:
            return {
                'type': 'text',
                'text': '🍽️ Вот наше меню! Выберите, что вас интересует:',
                'show_restaurant_menu': True
            }

        # Проверка запроса банкета
        banquet_queries = ['банкет', 'банкеты', 'свадьба', 'корпоратив', 'день рождения', 'праздник', 'юбилей']
        if any(q in message_lower for q in banquet_queries):
            return {
                'type': 'text',
                'text': '🎉 Да, мы проводим банкеты! У нас отличные условия для вашего праздника.',
                'show_banquet_options': True
            }

        second_phrases = ['а вторую', 'вторую', 'и вторую', 'а второе', 'второй', 'второе', 'а другая', 'другая', 'а другую', 'другую', 'еще одну', 'ещё одну', 'еще', 'ещё', 'другие', 'а другие', 'других', 'а других']
        if any(phrase in message_lower for phrase in second_phrases) and len(message_lower.split()) <= 5:
            base_query = None
            if user_id in user_history:
                for msg in reversed(user_history[user_id]):
                    if msg.get('role') == 'user':
                        prev_text = msg.get('content', '').strip()
                        if not prev_text:
                            continue
                        prev_lower = prev_text.lower().strip()
                        if any(p == prev_lower or p in prev_lower for p in second_phrases):
                            continue
                        # Очищаем служебные слова из предыдущего запроса
                        base_query = re.sub(r'^(покажи|покажите|хочу|расскажи|покажи фото|а покажи)\s+', '', prev_lower).strip()
                        base_query = re.sub(r'[!?.,:;]+$', '', base_query)
                        break
            if base_query:
                menu_data = load_menu_cache()
                candidates = find_similar_dishes(menu_data, base_query)
                if len(candidates) < 2:
                    tokens = base_query.split()
                    if tokens:
                        base_token = tokens[0]
                        candidates = find_similar_dishes(menu_data, base_token)
                if len(candidates) >= 2 or len(candidates) == 1:
                    idx = 1 if len(candidates) >= 2 else 0
                    dish = candidates[idx]
                    caption = f"🍽️ <b>{dish['name']}</b>\n\n"
                    caption += f"💰 Цена: {dish['price']}₽\n"
                    if dish.get('weight'):
                        caption += f"⚖️ Вес: {dish['weight']}\n"
                    if dish.get('calories'):
                        caption += f"🔥 Калории: {dish['calories']} ккал/100г\n"
                    if dish.get('protein') or dish.get('fat') or dish.get('carbohydrate') or dish.get('proteins') or dish.get('fats') or dish.get('carbs'):
                        caption += f"\n🧃 БЖУ:\n"
                        if dish.get('protein') is not None:
                            caption += f"• Белки: {dish['protein']}г\n"
                        elif dish.get('proteins'):
                            caption += f"• Белки: {dish['proteins']}г\n"
                        if dish.get('fat') is not None:
                            caption += f"• Жиры: {dish['fat']}г\n"
                        elif dish.get('fats'):
                            caption += f"• Жиры: {dish['fats']}г\n"
                        if dish.get('carbohydrate') is not None:
                            caption += f"• Углеводы: {dish['carbohydrate']}г\n"
                        elif dish.get('carbs'):
                            caption += f"• Углеводы: {dish['carbs']}г\n"
                    if dish.get('description'):
                        caption += f"\n{dish['description']}"
                    if dish.get('image_url'):
                        return {
                            'type': 'photo_with_text',
                            'photo_url': dish['image_url'],
                            'text': caption,
                            'show_delivery_button': True
                        }
                    else:
                        local_path = dish.get('image_local_path')
                        if not local_path and dish.get('image_filename'):
                            try:
                                local_path = os.path.join(config.MENU_IMAGES_DIR, dish['image_filename'])
                            except Exception:
                                local_path = None
                        if local_path:
                            return {
                                'type': 'photo_with_text',
                                'photo_path': local_path,
                                'text': caption,
                                'show_delivery_button': True
                            }
                        else:
                            return {
                                'type': 'text',
                                'text': caption,
                                'show_delivery_button': True
                            }

        # СПЕЦИАЛЬНАЯ ОБРАБОТКА ЗАПРОСОВ О КОНКРЕТНЫХ БЛЮДАХ (ДО AI)
        # Если сообщение похоже на запрос конкретного блюда - сразу показываем фото
        dish_keywords = ['что в составе', 'покажи фото', 'расскажи про', 'сколько калорий', 'калории в', 'фото', 'состав', 'ккал', 'цена', 'сколько стоит', 'стоимость', 'вес', 'бжу', 'белки', 'жиры', 'углеводы']
        
        # Ключевые слова для рекомендаций и вопросов о наличии - отправляем в AI
        recommendation_keywords = ['посоветуй', 'рекомендуй', 'что-то с', 'какое-нибудь', 'хочу', 'подскажи', 'есть ли', 'а есть', 'что есть', 'что взять', 'выбери', 'предложи']
        is_recommendation = any(keyword in message_lower for keyword in recommendation_keywords)
        
        is_dish_request = any(keyword in message_lower for keyword in dish_keywords)
        is_numeric = message.strip().isdigit()

        if is_recommendation:
            recent_messages = user_history.get(user_id, [])[-10:]
            has_breakfast_context = any(('завтрак' in (m.get('content', '').lower())) or ('завтраки' in (m.get('content', '').lower())) for m in recent_messages) or any(w in message_lower for w in ['завтрак', 'завтраки'])
            if has_breakfast_context:
                menu_data = load_menu_cache()
                breakfast_menu = menu_data.get('90') or menu_data.get(90)
                if breakfast_menu:
                    items = []
                    for category in breakfast_menu.get('categories', {}).values():
                        items.extend(category.get('items', []))
                    candidates = []
                    for item in items:
                        name_l = str(item.get('name', '')).lower()
                        if any(kw in name_l for kw in ['омлет', 'американ', 'сырник', 'круассан', 'каша', 'драник', 'блин']):
                            candidates.append(item)
                    with_image = [i for i in candidates if i.get('image_url') or i.get('image_local_path') or i.get('image_filename')]
                    pool = with_image if with_image else (candidates if candidates else items)
                    selected = []
                    seen_names = set()
                    for it in pool:
                        nm = it.get('name')
                        if nm and nm not in seen_names:
                            selected.append(it)
                            seen_names.add(nm)
                        if len(selected) >= 3:
                            break
                    if selected:
                        text_lines = ["🍳 Рекомендую на завтрак:\n"]
                        for it in selected:
                            line = f"• {it.get('name')}"
                            price = it.get('price')
                            weight = it.get('weight')
                            if price is not None:
                                line += f" — {price}₽"
                            if weight:
                                line += f" (⚖️ {weight})"
                            text_lines.append(line)
                        text_lines.append("\nСпросите про конкретное блюдо, чтобы увидеть фото и подробное описание!")
                        return {
                            'type': 'text',
                            'text': "\n".join(text_lines),
                            'show_category_brief': 'завтраки'
                        }
                return {
                    'type': 'text',
                    'text': '🍳 У нас есть отличные завтраки! Что вам ближе: что-то с яйцами, сладкое или легкое?',
                    'show_category_brief': 'завтраки'
                }

        # Логика решения: искать напрямую или через AI
        should_search = False
        if is_dish_request:
            should_search = True # Явный запрос характеристик
        elif is_recommendation:
            should_search = False # Запрос рекомендации/наличия -> AI
        elif len(message.split()) <= 5 and not is_numeric:
            should_search = True # Очень короткое сообщение (1-5 слов) без ключевых слов -> считаем названием блюда
            
        if should_search:
            # Формируем запрос для поиска
            dish_to_show = message.strip()
            
            # Очистка от вводных фраз для чистого поиска по названию (если вдруг попали сюда)
            clean_prefixes = ['а есть ', 'есть ', 'а ', 'скажи ', 'покажи ']
            lower_msg = message_lower
            for prefix in clean_prefixes:
                if lower_msg.startswith(prefix):
                    candidate = message[len(prefix):].strip()
                    if candidate:
                        dish_to_show = candidate
                    break

            # Если это явный запрос с ключевыми словами, пробуем их убрать для чистоты
            if is_dish_request:
                clean_query = message_lower
                # Сортируем ключевые слова по длине, чтобы сначала удалять длинные фразы
                for kw in sorted(dish_keywords, key=len, reverse=True):
                    clean_query = clean_query.replace(kw, '')
                # Также удаляем вопросительные слова и предлоги, если они остались
                clean_query = re.sub(r'\b(сколько|какой|какая|какие|где|почем|в|с|у|для|про)\b', '', clean_query)
                if clean_query.strip():
                    dish_to_show = clean_query.strip()

            logger.info(f"Прямая обработка запроса блюда: '{dish_to_show}' (original: '{message}')")

            # Ищем блюдо в меню
            menu_data = load_menu_cache()
            found_dish = None
            best_score = 0
            best_menu_id = None
            best_category_id = None
            search_results = []

            for menu_id, menu in menu_data.items():
                for category_id, category in menu.get('categories', {}).items():
                    for item in category.get('items', []):
                        item_name = item.get('name', '')
                        item_norm = _normalize_text(item_name)
                        search_norm = _normalize_text(dish_to_show)
                        
                        # Используем стемминг для нечеткого поиска
                        item_stem = _stem_text(item_name)
                        search_stem = _stem_text(dish_to_show)

                        # 🛑 FIX: Защита от ложного срабатывания "Паста" -> "Антипасти"
                        # Если искали "паст" (паста), но нашли "антипасти"
                        if 'паст' in dish_to_show.lower() and 'антипаст' not in dish_to_show.lower():
                            if 'антипаст' in item_name.lower():
                                continue

                        q_tokens = _specific_tokens(dish_to_show)
                        n_tokens = _specific_tokens(item_name)

                        score = 0
                        # 1. Точное совпадение нормализованных строк
                        if item_norm == search_norm:
                            score = 1000
                        # 2. Точное совпадение основ (стемминг)
                        elif item_stem == search_stem:
                            score = 950
                        # 3. Вхождение одной строки в другую (нормализованных)
                        elif search_norm and (item_norm.startswith(search_norm) or search_norm in item_norm or item_norm in search_norm):
                            score = 900
                        # 4. Вхождение основ (стемминг)
                        elif search_stem and (item_stem.startswith(search_stem) or search_stem in item_stem or item_stem in search_stem):
                            score = 850
                        # 5. Пересечение смысловых токенов
                        else:
                            inter = set(q_tokens) & set(n_tokens)
                            if inter:
                                score = 100 + 50 * len(inter)
                                # Бонус за совпадение основ токенов
                                q_stem_tokens = set([_stem_word(t) for t in q_tokens])
                                n_stem_tokens = set([_stem_word(t) for t in n_tokens])
                                stem_inter = q_stem_tokens & n_stem_tokens
                                if len(stem_inter) > len(inter):
                                    score += 50 * (len(stem_inter) - len(inter))

                        if score > 0:
                            search_results.append({
                                'name': item['name'],
                                'score': score,
                                'has_image': bool(item.get('image_url'))
                            })

                        if score > best_score:
                            best_score = score
                            found_dish = item
                            best_menu_id = menu_id
                            best_category_id = category_id

            logger.info(f"Результаты поиска для '{dish_to_show}': найдено {len(search_results)} блюд, лучший score: {best_score}")
            
            # Показываем блюдо только если есть достаточная уверенность
            # Для коротких сообщений без ключевых слов требуем более высокого совпадения
            threshold = 150
            if not is_dish_request:
                threshold = 800 # Для простых слов требуем почти точного совпадения или вхождения

            if found_dish and best_score >= threshold:
                logger.info(f"Выбрано блюдо: {found_dish['name']} (score: {best_score})")

                # Сохраняем сообщение пользователя в историю
                if user_id not in user_history:
                    user_history[user_id] = []
                user_history[user_id].append({"role": "user", "content": message})
                if len(user_history[user_id]) > 20:
                    user_history[user_id] = user_history[user_id][-20:]
                
                # Используем новый тип ответа для полноценной карточки
                return {
                    'type': 'show_dish_card',
                    'dish': found_dish,
                    'menu_id': best_menu_id,
                    'category_id': best_category_id,
                    'text': f"🍽️ Вот карточка блюда {found_dish['name']}:" # Fallback text
                }
            else:
                 logger.info(f"Блюдо не найдено или низкий score ({best_score} < {threshold}), передаем AI")

        # Специальная обработка вопросов про калории и легкие блюда (до обращения к AI)
        if any(word in message_lower for word in ['калори', 'ккал', 'калорийность']):
            specific_dishes = ['борщ', 'маргарита', '4 сыра', 'пепперони', 'инфаркт', 'том ям', 'цезарь']
            is_specific_dish = any(dish in message_lower for dish in specific_dishes)

            if not is_specific_dish:
                # Это вопрос про калории в категории - показываем КРАТКИЙ список с вопросом
                if any(word in message_lower for word in ['пицц', 'пиза']):
                    logger.info(f"🔍 Обнаружен вопрос про калории в пицце - показываем краткий список")
                    return {
                        'type': 'text',
                        'text': '🍕 У нас есть отличные пиццы! Смотря в какой именно вас интересуют калории:',
                        'show_category_brief': 'пицца'
                    }
                elif any(word in message_lower for word in ['суп', 'супа', 'супов']):
                    logger.info(f"🔍 Обнаружен вопрос про калории в супах - показываем краткий список")
                    return {
                        'type': 'text',
                        'text': '🍲 У нас есть отличные супы! Смотря в каком именно вас интересует калорийность:',
                        'show_category_brief': 'суп'
                    }
                elif any(word in message_lower for word in ['десерт', 'десерта', 'десертов']):
                    logger.info(f"🔍 Обнаружен вопрос про калории в десертах - показываем краткий список")
                    return {
                        'type': 'text',
                        'text': '🍰 У нас есть отличные десерты! Смотря в каком именно вас интересует калорийность:',
                        'show_category_brief': 'десерт'
                    }
                elif any(word in message_lower for word in ['салат', 'салата', 'салатов']):
                    logger.info(f"🔍 Обнаружен вопрос про калории в салатах - показываем краткий список")
                    return {
                        'type': 'text',
                        'text': '🥗 У нас есть отличные салаты! Смотря в каком именно вас интересуют калории:',
                        'show_category_brief': 'салаты'
                    }

        # Вопросы-контекст "что есть" и запросы легких блюд
        context_questions = ['какие есть', 'что есть', 'а какие', 'какие у вас', 'а какие есть', 'что у вас есть']
        if any(phrase in message_lower for phrase in context_questions):
            explicit_keywords = [
                'пицц', 'суп', 'супы', 'супов',
                'салат', 'салаты', 'салатов',
                'десерт', 'десерты', 'десертов',
                'напит', 'пив', 'вин', 'завтрак', 'мясо'
            ]
            if not any(keyword in message_lower for keyword in explicit_keywords):
                if user_id in user_history:
                    recent_messages = user_history[user_id][-10:]
                    for msg in reversed(recent_messages):
                        content = msg.get('content', '').lower()
                        if 'пицц' in content or 'калори' in content and 'пицц' in content:
                            logger.info(f"🔍 Обнаружен контекст пиццы в истории для вопроса '{message}', показываем пиццы")
                            return {
                                'type': 'text',
                                'text': '🍕 У нас есть отличные пиццы!',
                                'show_category_brief': 'пицца'
                            }
                        elif 'суп' in content or 'калори' in content and 'суп' in content:
                            logger.info(f"🔍 Обнаружен контекст супов в истории для вопроса '{message}', показываем супы")
                            return {
                                'type': 'text',
                                'text': '🍲 У нас есть отличные супы!',
                                'show_category_brief': 'суп'
                            }
                        elif 'десерт' in content or 'калори' in content and 'десерт' in content:
                            logger.info(f"🔍 Обнаружен контекст десертов в истории для вопроса '{message}', показываем десерты")
                            return {
                                'type': 'text',
                                'text': '🍰 У нас есть отличные десерты!',
                                'show_category_brief': 'десерт'
                            }
                        elif 'салат' in content or 'калори' in content and 'салат' in content:
                            logger.info(f"🔍 Обнаружен контекст салатов в истории для вопроса '{message}', показываем салаты")
                            return {
                                'type': 'text',
                                'text': '🥗 У нас есть отличные салаты!',
                                'show_category_brief': 'салаты'
                            }
                        elif 'пив' in content:
                            logger.info(f"🔍 Обнаружен контекст пива в истории для вопроса '{message}', показываем пиво")
                            return {
                                'type': 'text',
                                'text': '🍺 У нас есть отличное пиво!',
                                'show_category_brief': 'пиво'
                            }
                        elif 'вин' in content:
                            logger.info(f"🔍 Обнаружен контекст вина в истории для вопроса '{message}', показываем вино")
                            return {
                                'type': 'text',
                                'text': '🍷 У нас есть отличное вино!',
                                'show_category_brief': 'вино'
                            }

        # Запросы легких / низкокалорийных блюд после супов или салатов
        light_keywords = ['легк', 'низкокалор', 'мало калор', 'полегче']
        if any(kw in message_lower for kw in light_keywords):
            if user_id in user_history:
                recent_messages = user_history[user_id][-10:]
                last_bot_text = ''
                for msg in reversed(recent_messages):
                    if msg.get('role') == 'assistant':
                        last_bot_text = msg.get('content', '').lower()
                        break

                # Если до этого показывали супы или салаты - сразу ищем по калориям
                if '🍲 у нас есть отличные супы' in last_bot_text or '🍲 у нас есть отличные супы' in message_lower:
                    return {
                        'type': 'text',
                        'text': '🍲 Среди супов самые легкие обычно бульоны и прозрачные супы. Могу предложить куриный супчик или том ям, если любите поострее. Спросите про любое из них, и я покажу карточку с калориями!',
                        'show_category_brief': 'суп'
                    }
                if '🥗 у нас есть отличные салаты' in last_bot_text or '🥗 у нас есть отличные салаты' in message_lower:
                    return {
                        'type': 'text',
                        'text': '🥗 Из легких вариантов чаще всего подходят овощные салаты без майонеза. Спросите про конкретный салат, и я покажу карточку с калориями!',
                        'show_category_brief': 'салаты'
                    }


        if is_mac_greeting:
            # Убираем обращение из сообщения для дальнейшей обработки
            clean_message = message
            for greeting in ['мак,', 'макс,', 'мак!', 'макс!', 'мак ', 'макс ', 'привет мак', 'привет макс']:
                if message_lower.startswith(greeting.lower()):
                    clean_message = message[len(greeting):].strip()
                    break

            # Если после обращения есть вопрос - обрабатываем его через AI (НЕ рекурсивно!)
            if clean_message and len(clean_message) > 2:
                # Продолжаем обработку с очищенным сообщением, но НЕ вызываем рекурсивно
                message = clean_message  # Просто заменяем сообщение
                # Добавим флаг, что это обращение к Маку
                mac_greeting_prefix = "Привет! Да, это я — Мак, ваш помощник от ресторана Машков! 😊\n\n"
            else:
                # Если только обращение без вопроса
                return {
                    'type': 'text',
                    'text': '👋 Привет! Да, это я — Мак, ваш персональный помощник от ресторана Машков! 😊\n\nЧем могу помочь? Расскажу о меню, помогу забронировать столик или отвечу на любые вопросы о ресторане! 🍽️'
                }
        else:
            mac_greeting_prefix = ""

        # Проверяем лимит генераций (только для генерации изображений)
        can_generate, remaining = database.check_ai_generation_limit(user_id, daily_limit=2)
        is_admin = database.is_admin(user_id)

        # Генерация изображений персонажей обрабатывается через отдельные команды

        # Character photo generation is now handled by AI prompts, not automatic parsing

        # 2. Загружаем меню и примечания
        menu_data = load_menu_cache()
        ai_notes = get_ai_notes()

        # 3. Формируем структуру меню (JSON)
        menu_knowledge_base = []

        # Меню, которые нужно передать в контекст (по запросу: 29, 32, 90, 92, 141)
        target_menu_ids = [29, 32, 90, 92, 141]

        for menu_id in target_menu_ids:
            if menu_id in menu_data:
                menu = menu_data[menu_id]
                menu_name = menu.get('name', '').replace('🍳', '').replace('📋', '').strip()
                
                menu_section = {
                    "menu_name": menu_name,
                    "categories": []
                }

                for category_id, category in menu.get('categories', {}).items():
                    category_name = category.get('name', '').replace('🍕', '').replace('🥗', '').strip()
                    
                    # 🛑 Исключаем категории добавок, модификаторов и конструкторов из контекста AI
                    if any(bad_word in category_name.lower() for bad_word in ['добавки', 'модификаторы', 'топпинги', 'соусы к', 'дополнительно', 'конструктор']):
                        continue

                    category_data = {
                        "category_name": category_name,
                        "items": []
                    }

                    items = category.get('items', [])
                    # Фильтруем товары с ценой 0 (модификаторы, скрытые товары)
                    items = [item for item in items if float(item.get('price', 0)) > 0]
                    
                    # Берем первые 5 блюд из каждой категории для лучшего контекста
                    for item in items[:5]:
                        desc = item.get('description', '')
                        # Очищаем описание от HTML тегов если есть
                        if desc:
                            desc = re.sub(r'<[^>]+>', '', desc).strip()
                            
                        dish_info = {
                            "name": item['name'],
                            "price": item['price'],
                            "description": desc,
                            "calories": item.get('calories'),
                            "weight": item.get('weight'),
                            "protein": item.get('protein'),
                            "fat": item.get('fat'),
                            "carbohydrate": item.get('carbohydrate')
                        }
                        category_data["items"].append(dish_info)
                    
                    if len(items) > 5:
                        category_data["more_items_count"] = len(items) - 5
                        
                    menu_section["categories"].append(category_data)
                
                menu_knowledge_base.append(menu_section)

        # Сохраняем в файл menu_context.json (как просил пользователь "отдельно место в json")
        try:
            with open('menu_context.json', 'w', encoding='utf-8') as f:
                json.dump(menu_knowledge_base, f, ensure_ascii=False, indent=2)
            logger.info("✅ Menu context saved to menu_context.json")
        except Exception as e:
            logger.error(f"Failed to save menu_context.json: {e}")

        # Формируем строку JSON для контекста
        menu_context_json = json.dumps(menu_knowledge_base, ensure_ascii=False)

        # 4. Получаем историю
        if user_id not in user_history:
            user_history[user_id] = []
            logger.info(f"Создана новая история для пользователя {user_id}")
        else:
            logger.info(f"История пользователя {user_id}: {len(user_history[user_id])} сообщений")

        user_history[user_id].append({"role": "user", "content": message})
        logger.info(f"Добавлено сообщение пользователя в историю: {message[:50]}...")

        if len(user_history[user_id]) > 20:
            user_history[user_id] = user_history[user_id][-20:]
            logger.info(f"История обрезана до 20 сообщений")

        # 5. Формируем список всех категорий для промпта
        all_categories_list = set()
        for menu_id in target_menu_ids:
            if menu_id in menu_data:
                for cat in menu_data[menu_id].get('categories', {}).values():
                    cat_name = cat.get('name', '').strip()
                    
                    # 🛑 Исключаем категории добавок из списка подсказок
                    if any(bad_word in cat_name.lower() for bad_word in ['добавки', 'модификаторы', 'топпинги', 'соусы к', 'дополнительно', 'конструктор']):
                        continue

                    if cat_name:
                        all_categories_list.add(cat_name)
        
        categories_str = ", ".join(sorted(all_categories_list))

        # Pre-select a random dish for consistent storytelling
        context_dish = get_random_delivery_dish(menu_data)
        context_dish_info = ""
        if context_dish:
             context_dish_info = (
                f"CURRENT CONTEXT DISH: {context_dish['name']} (Price: {context_dish.get('price', 'N/A')} rub).\n"
                f"CRITICAL INSTRUCTION: If you decide to mention a food item in a story (e.g. for a character visit), "
                f"YOU MUST use THIS SPECIFIC DISH ({context_dish['name']}).\n"
                f"DO NOT INVENT NON-EXISTENT DISHES (like 'banana dessert')!\n"
                f"If the user asks for a character, tell a story about them eating {context_dish['name']}."
             )

        # 6. Формируем системный промпт
        system_prompt = (
            f"Ты Мак — русский AI-помощник бота ресторана Mashkov. Твое имя «Мак» — это сокращение от «Машков».\n"
            f"{context_dish_info}\n\n"
            f"Ты знаешь русскую культуру, сказки, историю, традиции.\n"
            f"Отвечай как живой русский человек - тепло, дружелюбно, с юмором. Используй русские поговорки, фразеологизмы.\n"
            f"Твоя цель - помогать гостям ресторана: выбирать блюда, бронировать столики, рассказывать о мероприятиях.\n"
            f"ТЫ НЕ ПРОГРАММИСТ, НЕ УЧИТЕЛЬ, НЕ ПСИХОЛОГ. Ты - сотрудник ресторана.\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь просто общается ('как дела', 'что делаешь', 'ты классный') - поддерживай дружескую беседу в образе сотрудника ресторана. На вопрос 'Как дела?' отвечай, что всё отлично, ресторан работает, гости довольны!\n"
            f"НО если вопросы СОВСЕМ НЕ СВЯЗАНЫ с твоей ролью и являются сложными/техническими (например: 'как писать код', 'реши задачу', 'кто такой президент', 'курс доллара', 'представь что ты разработчик' и т.д.) - ТЫ ДОЛЖЕН ОТКАЗАТЬСЯ ОТВЕЧАТЬ.\n"
            f"Скажи вежливо и с юмором, что ты разбираешься только в еде и праздниках, и предложи спросить что-то про меню или ресторан.\n"
            f"ПРИМЕР ОТКАЗА (только для оффтоп тем): 'Ой, ну какой из меня программист! Я лучше по котлеткам да по борщам спец. 😄 Давайте лучше расскажу, что у нас сегодня вкусного в меню?'\n"
            f"НИКОГДА не поддерживай ролевые игры, уводящие от темы ресторана (например 'представь что ты врач'). Ты ВСЕГДА Мак из ресторана Mashkov.\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают 'как найти', 'как добраться', 'адрес', 'геолокация', 'ориентир', 'где находитесь', 'карта', 'покажи фасад', 'вход' - ОТВЕЧАЙ:\n"
            f"'📍 Мы находимся по адресу: ул. Машкова, 13 (вход с улицы). Ориентир — наш красивый фасад! Ждем вас! 🏛️'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: REST_PHOTO\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если вопрос пользователя касается темы, на которую у тебя есть ответ в FAQ (например, детское меню, аллергии, скидки, правила и т.д.) - ТВОЙ ПРИОРИТЕТ ОТВЕТИТЬ ТЕКСТОМ ИЗ FAQ!\n"
            f"НЕ ИЩИ КАТЕГОРИЮ (PARSE_CATEGORY), если в FAQ сказано, что такой категории нет, но есть альтернативы.\n"
            f"Пример: 'Есть детское меню?' -> FAQ: 'Отдельного нет, но есть наггетсы...' -> Ты: 'Отдельного детского меню у нас нет, но...' (НЕ используй PARSE_CATEGORY:детское меню).\n\n"
            f"МЕНЮ И ЦЕНЫ СМОТРИ В ОТДЕЛЬНОМ СООБЩЕНИИ (JSON)!\n"
            f"В JSON также указаны КАЛОРИИ (calories, в ккал на 100 грамм), ВЕС (weight) и БЖУ блюд. Используй эти данные, если пользователя интересует калорийность, диетические предпочтения или состав.\n"
            f"⛔ СТРОЖАЙШИЙ ЗАПРЕТ: НИКОГДА не придумывай названия блюд, которых нет в JSON-меню. Если блюда нет в списке - так и скажи. Не выдумывай 'Пиццу Машков', 'Фирменный салат' и т.д., если их нет в JSON.\n"
            f"⛔ СТРОЖАЙШИЙ ЗАПРЕТ: НИКОГДА НЕ ПРЕДЛАГАЙ ДОБАВКИ В ПИЦЦУ (грибы, сыр, бекон и т.д.). В пиццу ничего добавлять нельзя! Это готовое блюдо.\n"
            f"Если пользователь просит добавить что-то в пиццу, отвечай: 'К сожалению, мы не можем изменять состав пиццы или добавлять ингредиенты. Но у нас есть много разных пицц на выбор!'\n"
            f"Рекомендуй ТОЛЬКО те блюда, которые реально существуют в переданном тебе меню.\n"
            f"ДОСТУПНЫЕ КАТЕГОРИИ МЕНЮ: {categories_str}\n"
            f"ВАЖНО: Используй ТОЧНЫЕ названия категорий из списка выше для PARSE_CATEGORY.\n\n"
            f"Знаешь русские сказки (Колобок, Репка, Курочка Ряба, Иван-царевич, Баба-яга, Кощей Бессмертный), "
            f"былины (Илья Муромец, Добрыня Никитич, Алёша Попович), русскую литературу (Пушкин, Толстой, Достоевский), "
            f"советские фильмы и мультфильмы (Ну погоди, Винни-Пух, Крокодил Гена, Чебурашка).\n\n"
            f"ВАЖНО: Если к тебе обращаются по имени ('Мак', 'мак', 'Макс', 'макс') - отвечай дружелюбно и представляйся!\n"
            f"Пример: 'Привет, Мак!' → 'Привет! Да, это я — Мак, ваш помощник от ресторана Машков! 😊 Чем могу помочь?'\n\n"
            f"Отвечай просто и красиво, БЕЗ звездочек и маркдауна. Используй живую русскую речь!\n\n"
            f"🚨 КРИТИЧЕСКИ ВАЖНО - ТЕХНИЧЕСКИЕ МАРКЕРЫ:\n"
            f"ВСЕГДА используй ТОЛЬКО АНГЛИЙСКИЕ БУКВЫ для технических маркеров:\n"
            f"✅ ПРАВИЛЬНО: PARSE_CATEGORY:пицца\n"
            f"✅ ПРАВИЛЬНО: PARSE_CATEGORY:паста (для запросов 'паста', 'пасту', 'хочу пасту')\n"
            f"❌ НЕПРАВИЛЬНО: PARSE_CATEGORY:Антипасти (если просят ПАСТУ - антипасти это другое!)\n"
            f"❌ НЕПРАВИЛЬНО: Парсе категорию: пицца\n"
            f"❌ НЕПРАВИЛЬНО: ПАРС_КАТЕГОРИЯ:пицца\n"
            f"❌ НЕПРАВИЛЬНО: Парсинг категории: пицца\n"
            f"НИКОГДА НЕ ПЕРЕВОДИ ТЕХНИЧЕСКИЕ МАРКЕРЫ НА РУССКИЙ ЯЗЫК!\n\n"
            f"🔍 ПОИСК БЛЮД ПО ИНГРЕДИЕНТАМ И НАЗВАНИЯМ:\n"
            f"Если пользователь ищет блюда с определенными ингредиентами (например: 'блюда с креветками', 'что есть с грибами') ИЛИ спрашивает про КОНКРЕТНОЕ блюдо ('расскажи про том ям', 'калорийность борща', 'состав пиццы пепперони'), используй маркер SEARCH:\n"
            f"✅ ПРАВИЛЬНО: SEARCH:креветки, том ям\n"
            f"✅ ПРАВИЛЬНО: SEARCH:грибы\n"
            f"✅ ПРАВИЛЬНО: SEARCH:Американский завтрак\n"
            f"✅ ПРАВИЛЬНО: SEARCH:креветки, лосось, кальмар, мидии, краб, гребешок (для запроса 'морепродукты')\n"
            f"ЕСЛИ ЧЕЛОВЕК ПИШЕТ 'МОРЕПРОДУКТЫ' ИЛИ СПРАШИВАЕТ ПРО МОРЕПРОДУКТЫ (КРЕВЕТКИ, МИДИИ, КАЛЬМАРЫ, ОСЬМИНОГА И Т.Д.), ВСЕГДА ИСПОЛЬЗУЙ ДЛЯ SEARCH КОРНИ СЛОВ: 'креветк', 'кальмар', 'миди', 'осьминог', 'гребешк', 'краб'.\n"
            f"ТЫ МОЖЕШЬ УКАЗЫВАТЬ НЕСКОЛЬКО КЛЮЧЕВЫХ СЛОВ ЧЕРЕЗ ЗАПЯТУЮ! Для запросов типа 'морепродукты', 'что-то с морепродуктами' обязательно указывай несколько разных морепродуктов через запятую.\n"
            f"ВАЖНО: Если у тебя нет точных данных о калориях или составе в контексте, НЕ ГОВОРИ 'Я не знаю' и НЕ ОТПРАВЛЯЙ К ОФИЦИАНТУ. Вместо этого скажи: 'Точных цифр сейчас не вижу, но вот карточка блюда с деталями:' и добавь SEARCH:название_блюда.\n"
            f"ВАЖНО: ИСКЛЮЧАЙ АЛКОГОЛЬ из поиска, если пользователь явно не попросил алкоголь!\n"
            f"Если спрашивают 'еду', не предлагай вино или пиво.\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь называет КОНКРЕТНОЕ блюдо или вино (например 'Вино Гевюрцтраминер Вайнхаус Каннис белое п/сухое', 'Пицца Пепперони', 'Борщ') - ОБЯЗАТЕЛЬНО используй маркер DISH_PHOTO:точное_название_блюда\n"
            f"Ты МОЖЕШЬ добавить краткий дружелюбный комментарий перед маркером (например: 'Отличный выбор! 🥣 DISH_PHOTO:Борщ'), чтобы ответ выглядел живым.\n"
            f"Но само описание блюда (цена, состав) НЕ пиши текстом - оно подтянется автоматически из базы!\n"
            f"Ты также можешь использовать этот маркер САМ, если хочешь предложить конкретное блюдо (например: 'Рекомендую попробовать Американский завтрак!' + DISH_PHOTO:Американский завтрак).\n\n"
            f"ВАЖНО: На приветствия ('привет', 'здравствуйте', 'добрый день') отвечай ОБЩИМ приветствием с представлением и предложением посмотреть меню, а НЕ показывай конкретные блюда!\n"
            f"Пример правильного ответа на 'Привет!':\n"
            f"'👋 Привет! Меня зовут Мак — ваш помощник от ресторана Машков! У нас богатое меню: пиццы, супы, салаты, горячие блюда, десерты и напитки! 🍽️ Что вас интересует?'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_DELIVERY_BUTTON\n\n"
            f"ВАЖНО: Если пользователь спрашивает 'что есть', 'какие есть', 'что у вас есть', 'а какие есть' В КОНТЕКСТЕ КОНКРЕТНОЙ КАТЕГОРИИ (после разговора о пиццах, супах и т.д.) - НЕ отвечай системным приветствием! ОБЯЗАТЕЛЬНО используй PARSE_CATEGORY для той категории, о которой шла речь в предыдущих сообщениях!\n"
            f"Примеры:\n"
            f"• Пользователь: 'Сколько калорий в пицце?' → Ты: 'В какой именно пицце?' → Пользователь: 'А какие есть?' → Ты: PARSE_CATEGORY:пицца\n"
            f"• Пользователь: 'У вас есть супы?' → Ты: 'Да!' → Пользователь: 'Какие есть?' → Ты: PARSE_CATEGORY:суп\n"
            f"• Пользователь: 'Десерты есть?' → Ты: 'Конечно!' → Пользователь: 'Что есть?' → Ты: PARSE_CATEGORY:десерт\n"
            f"ВСЕГДА АНАЛИЗИРУЙ ПРЕДЫДУЩИЕ СООБЩЕНИЯ В ИСТОРИИ! Если недавно говорили о категории - используй её!\n\n"
            f"СПЕЦИАЛЬНО ДЛЯ ЗАВТРАКОВ: Если пользователь спрашивает 'что посоветуешь' или 'что заказать' и в истории недавно (последние 3-5 сообщений) было упоминание завтрака ('завтрак', 'утро', 'с утра'), ОБЯЗАТЕЛЬНО предлагай блюда из категории ЗАВТРАКИ или используй PARSE_CATEGORY:завтрак.\n\n"
            f"СПЕЦИАЛЬНО ДЛЯ МОРЕПРОДУКТОВ: Если пользователь спрашивает 'что посоветуешь', 'а другие', 'еще' или 'что заказать' и в истории недавно (последние 3-5 сообщений) было упоминание морепродуктов ('морепродукты', 'креветки', 'мидии', 'кальмар', 'осьминог', 'гребешк', 'краб', 'рыба'), ОБЯЗАТЕЛЬНО предлагай блюда из категории МОРЕПРОДУКТЫ. Если ты УЖЕ показал список (SEARCH/текст), выбери 1-2 блюда из него и порекомендуй! Если списка не было - используй SEARCH:креветк, кальмар, миди, осьминог, гребешк, краб. НЕ ПРЕДЛАГАЙ мясо или десерты, если контекст про морепродукты!\n\n"
            f"ВАЖНО: Если пользователь просит 'А ещё?' или 'А ещё что-то?' после списка блюд (SEARCH), НЕ показывай тот же список снова! Предложи КОНКРЕТНОЕ блюдо из этой категории с помощью DISH_PHOTO или скажи, что это всё.\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: ИСПОЛЬЗУЙ ТОЛЬКО ТУ ИНФОРМАЦИЮ, КОТОРАЯ ЕСТЬ В МЕНЮ НИЖЕ! НИКОГДА НЕ ПРИДУМЫВАЙ:\n"
            f"❌ Добавки к блюдам (салями, бекон, лосось, сыры, овощи и т.д.)\n"
            f"❌ Модификаторы и опции\n"
            f"❌ Цены на добавки\n"
            f"❌ Любую информацию, которой НЕТ в меню\n"
            f"✅ Если спрашивают про добавки/модификаторы - отвечай: 'Для уточнения возможности добавления ингредиентов свяжитесь с нами по телефону или оформите заказ через меню.'\n\n"
            f"ВАЖНО: ВСЕГДА используй эмодзи в своих ответах для красоты! Добавляй подходящие эмодзи к каждому пункту списка и важным словам.\n\n"
            f"ВАЖНО: Если спрашивают 'что ты умеешь', 'что умеешь', 'твои возможности', 'как тебя зовут', 'кто ты' - отвечай:\n"
            f"'👋 Меня зовут Мак — я ваш персональный AI-помощник от ресторана Машков! 🤖\n\n"
            f"🎯 Вот что я умею:\n"
            f"🍽️ Показать меню с фото и ценами\n"
            f"📊 Рассказать о блюдах, калориях и БЖУ\n"
            f"🚚 Оформить доставку\n"
            f"📅 Забронировать столик\n"
            f"🎉 Зарегистрировать на мероприятия\n"
            f"💬 Ответить на вопросы о ресторане\n"
            f"🎯 Помочь с выбором блюд\n"
            f"📚 Поговорить о русской культуре и традициях\n\n"
            f"Можете обращаться ко мне просто «Мак»! 😊'\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают 'можно ли через вас/тебя заказать доставку' или 'можешь ли ты заказать' - ОТВЕЧАЙ:\n"
            f"'🤖 Я не могу заказать за вас доставку, но вы можете сделать это самостоятельно через наше приложение! 🚀\n\n📱 Выберите удобный способ заказа в кнопках ниже!'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_DELIVERY_APPS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про ОТЗЫВЫ ('отзывы', 'оставить отзыв', 'написать отзыв', 'почитать отзывы', 'рейтинг', 'оценки') - ОТВЕЧАЙ:\n"
            f"'⭐ У нас отличные отзывы! Вы можете прочитать их и оставить свой отзыв на Яндекс.Картах! 📱'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_REVIEWS\n\n"
                        f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про ПРИЛОЖЕНИЕ ('приложение', 'скачать', 'app store', 'google play', 'rustore', 'скачать приложение', 'мобильное приложение') - ОТВЕЧАЙ:\n"
            f"'📱 У нас есть удобное мобильное приложение для заказа! Скачайте его из любого магазина приложений! 🚀'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_APPS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про ФОТО ЗАЛА ('покажи зал', 'фото зала', 'как выглядит зал', 'хочу посмотреть зал', 'покажи фото зала', 'зал', 'интерьер') - ОТВЕЧАЙ:\n"
            f"'🏛️ Конечно! Вот фотографии нашего уютного зала! 📸'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_HALL_PHOTOS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про ФОТО БАРА ('покажи бар', 'фото бара', 'как выглядит бар', 'хочу посмотреть бар', 'покажи фото бара', 'бар') - ОТВЕЧАЙ:\n"
            f"'🍸 Конечно! Вот фотографии нашего стильного бара! 📸'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_BAR_PHOTOS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про ФОТО КАССЫ ('покажи кассу', 'фото кассы', 'как выглядит касса', 'хочу посмотреть кассу', 'покажи фото кассы', 'касса') - ОТВЕЧАЙ:\n"
            f"'💳 Конечно! Вот фотографии нашей кассы! 📸'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_KASSA_PHOTOS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про ФОТО ТУАЛЕТА ('покажи туалет', 'фото туалета', 'как выглядит туалет', 'хочу посмотреть туалет', 'покажи фото туалета', 'туалет', 'ваш туалет', 'wc') - ОТВЕЧАЙ:\n"
            f"'🚻 Конечно! Вот фотографии нашего туалета! 📸'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_WC_PHOTOS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про ЧАСТНЫЕ МЕРОПРИЯТИЯ ('день рождения', 'др', 'свадьба', 'корпоратив', 'юбилей', 'празднование', 'банкет', 'организовать мероприятие', 'провести праздник', 'можно отметить', 'забронировать на день рождения') - НИКОГДА НЕ СПРАШИВАЙ КОЛИЧЕСТВО ГОСТЕЙ ИЛИ ДАТУ!\n"
            f"СРАЗУ ВЫЗЫВАЙ ФУНКЦИЮ ПОКАЗА ОПЦИЙ!\n"
            f"ОТВЕЧАЙ: '🎉 Мы будем рады организовать ваш праздник! Посмотрите наши предложения для мероприятий! 👇'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_PRIVATE_EVENT_OPTIONS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь СОГЛАШАЕТСЯ ('да', 'хочу', 'давай', 'конечно') на твое предложение показать/сгенерировать фото или если контекст подразумевает желание увидеть визуализацию банкета/мероприятия - ИСПОЛЬЗУЙ МАРКЕР GEN_IMAGE:Имя_Персонажа\n"
            f"Пример: Пользователь 'Хочу банкет' -> Ты 'Показать, как это будет выглядеть?' -> Пользователь 'Да' -> Ты: 'GEN_IMAGE:Shrek'\n"
            f"ВСЕГДА используй Шрека (Shrek) как персонажа для примеров банкетов, если пользователь не попросил кого-то другого!\n"
            f"Формат: GEN_IMAGE:Name (ТОЛЬКО имя персонажа!)\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про МЕНЮ ЗАВТРАКОВ ('покажи меню завтраков', 'меню завтраков', 'завтраки', 'что на завтрак') - ОТВЕЧАЙ:\n"
            f"'🍳 Конечно! Вот наше меню ресторана с завтраками и другими блюдами!'\n"
            f"И ОБЯЗАТЕЛЬНО добавь ТОЛЬКО: SHOW_CATEGORY:завтраки\n"
            f"НЕ добавляй SHOW_RESTAURANT_MENU для завтраков!\n"
            f"НЕ добавляй SHOW_DELIVERY_BUTTON для завтраков!\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь просит ПОЗВОНИТЬ ЧЕЛОВЕКУ, ВЫЗВАТЬ ОПЕРАТОРА, ПОГОВОРИТЬ С ЧЕЛОВЕКОМ ('позвони человеку', 'вызови оператора', 'хочу поговорить с человеком', 'человек', 'оператор', 'менеджер', 'администратор', 'живой человек', 'настоящий человек') - ОТВЕЧАЙ:\n"
            f"'📞 Конечно! Сейчас позову человека, который поможет вам с вашим вопросом. Пожалуйста, подождите немного. 😊'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: CALL_HUMAN\n\n"
            f"'🎉 Да, конечно! Я могу забронировать дату под ваше мероприятие, могу многое рассказать и дать ответы на большинство вопросов, но лучше оставьте свой номер телефона и мы вам перезвоним в ближайшее время. Также я могу позвать человека и он ответит на ваши вопросы прямо здесь! 📞'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_PRIVATE_EVENT_OPTIONS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если спрашивают про МЕРОПРИЯТИЯ РЕСТОРАНА ('мероприятия', 'события', 'концерты', 'вечеринки', 'праздники', 'какие у вас бывают мероприятия', 'какие мероприятия') - ОТВЕЧАЙ:\n"
            f"'🎉 У нас часто проводятся различные мероприятия. Обычно мы публикуем анонсы в нашем приложении. Скачайте его и посмотрите ближайшие мероприятия в нем!'\n"
            f"И ОБЯЗАТЕЛЬНО добавь: SHOW_APPS\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь пишет БРОНИРОВАНИЕ В ФОРМАТЕ (дата + время + гости), например:\n"
            f"'Столик на 3, в 20:30, 17 января' или 'на 2 человека, завтра в 19:00' или 'Столик на 2, в 19:00, 16 января' - СНАЧАЛА определи количество гостей!\n"
            f"\n"
            f"ДЛЯ 1-4 ЧЕЛОВЕК (включительно):\n"
            f"'✅ Отлично! Бронирую для вас столик. Сейчас покажу доступные варианты.'\n"
            f"PARSE_BOOKING:текст_бронирования\n"
            f"\n"
            f"ДЛЯ 5 И БОЛЕЕ ЧЕЛОВЕК (5, 6, 7, 8, 9, 10+ человек):\n"
            f"'❌ Для компании от 5 человек автоматическое бронирование недоступно. Свяжитесь с оператором по телефону +7 (495) 123-45-67 или оформите несколько отдельных бронирований на 2-4 человека.'\n"
            f"НЕ ДОБАВЛЯЙ PARSE_BOOKING для групп 5+ человек!\n"
            f"\n"
            f"Примеры:\n"
            f"• 'Столик на 2, в 19:00, 16 января' -> ✅ Отлично! + PARSE_BOOKING\n"
            f"• 'Столик на 4, завтра в 20:00' -> ✅ Отлично! + PARSE_BOOKING\n"
            f"• '5 человек, завтра в 19:00' -> ❌ Для компании от 5 человек... (БЕЗ PARSE_BOOKING)\n"
            f"• '8 человек, 22 января, в 19:30' -> ❌ Для компании от 5 человек... (БЕЗ PARSE_BOOKING)\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь отвечает КОРОТКИМИ ОТВЕТАМИ ('да', 'хочу', 'конечно', 'ага', 'ок', 'ладно', 'согласен') - ОБЯЗАТЕЛЬНО АНАЛИЗИРУЙ КОНТЕКСТ ПРЕДЫДУЩИХ СООБЩЕНИЙ!\n"
            f"• Если в предыдущем сообщении ты предлагал показать/сгенерировать фото банкета/мероприятия - используй GEN_IMAGE:Shrek\n"
            f"• Если предыдущее сообщение бота содержало слова 'забронировать', 'бронирование', 'столик', 'бронь', 'резерв' - используй SHOW_BOOKING_OPTIONS\n"
            f"• Если предыдущее сообщение бота содержало слова 'пицца', 'пиццы', 'пиццей' - используй PARSE_CATEGORY:пицца\n"
            f"• Если предыдущее сообщение бота содержало слова 'суп', 'супы', 'супов' - используй PARSE_CATEGORY:суп\n"
            f"• Если предыдущее сообщение бота содержало слова 'десерт', 'десерты' - используй PARSE_CATEGORY:десерт\n"
            f"• Если предыдущее сообщение бота содержало слова 'напитки', 'напиток' - используй PARSE_CATEGORY:напитки\n\n"
            f"КРИТИЧЕСКИ ВАЖНО - УМНЫЙ ПОИСК БЛЮД:\n"
            f"Если пользователь ищет блюда не по категории, а по ИНГРЕДИЕНТАМ, ТИПУ или ОСОБЕННОСТЯМ (например: 'с овощами', 'мясное', 'без мяса', 'веганское', 'постное', 'острое', 'с грибами', 'с сыром', 'с рыбой', 'с картошкой') - ИСПОЛЬЗУЙ МАРКЕР SEARCH:запрос\n"
            f"ПРИМЕРЫ:\n"
            f"• 'Есть что-то с овощами?' -> 'Конечно! Вот что у нас есть с овощами:' + SEARCH:овощ\n"
            f"• 'Хочу мясное' -> 'Для любителей мяса у нас отличный выбор:' + SEARCH:мяс\n"
            f"• 'Что есть с грибами?' -> 'С грибами есть несколько вкусных блюд:' + SEARCH:гриб\n"
            f"• 'Что посоветуешь веганское?' -> 'У нас есть отличные варианты без мяса:' + SEARCH:веган\n"
            f"• 'Есть ли вегетарианские блюда?' -> 'Да, у нас есть блюда без мяса:' + SEARCH:вегетариан\n"
            f"• 'Что-то с сыром?' -> 'Любителям сыра рекомендую:' + SEARCH:сыр\n"
            f"• 'Есть что-то с рыбой?' -> 'Рыбные блюда:' + SEARCH:рыб\n"
            f"• 'Блюда с картошкой' -> 'Блюда с картофелем:' + SEARCH:картофел\n"
            f"• 'Хочу рис' -> 'Блюда с рисом:' + SEARCH:рис\n"
            f"• 'Есть что-то с бобами?' -> 'Блюда с бобами:' + SEARCH:боб\n"
            f"ВАЖНО: При использовании SEARCH НЕ перечисляй блюда сам! Просто напиши короткую подводку (например, 'Вот что я нашел:', 'Смотрите:', 'Отличный выбор:'). Список блюд добавит система автоматически.\n"
            f"ВАЖНО: НЕ пиши 'Ищу блюда по запросу...' или технические сообщения перед маркером SEARCH. Просто маркер или дружелюбный ответ.\n"
            f"НЕ ИСПОЛЬЗУЙ PARSE_CATEGORY для таких запросов (веган, сыр, грибы и т.д.), так как таких категорий НЕТ! Используй ТОЛЬКО SEARCH! В SEARCH пиши только КОРЕНЬ слова (веган, гриб, сыр, мяс, рыб) для лучшего поиска!\n"
            f"• Если предыдущее сообщение бота содержало слова 'пиво', 'пива' - используй PARSE_CATEGORY:пиво\n"
            f"• Если предыдущее сообщение бота содержало слова 'вино', 'вина' - используй PARSE_CATEGORY:вино\n"
            f"• Если предыдущее сообщение бота содержало слова 'коктейль', 'коктейли' - используй PARSE_CATEGORY:коктейль\n"
            f"• Если контекст неясен - спроси уточнение: 'Что именно вы имеете в виду?'\n"
            f"ВСЕГДА проверяй ИСТОРИЮ СООБЩЕНИЙ перед ответом на короткие фразы!\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: ИСПОЛЬЗУЙ ИНФОРМАЦИЮ ИЗ МЕНЮ (выше) ДЛЯ ОТВЕТА!\n"
            f"Если пользователь спрашивает о блюдах (например, 'есть ли вегетарианское?', 'что с мясом?', 'что посоветуешь?'):\n"
            f"1. Не перечисляй большие СПИСКИ блюд вручную и не пиши цены сам.\n"
            f"2. Для показа списков ВСЕГДА используй SEARCH:запрос или PARSE_CATEGORY:категория, чтобы система сама показала список.\n"
            f"3. Ты МОЖЕШЬ упоминать 1–3 конкретных блюда как рекомендацию, НО только из уже показанного пользователю списка (после SEARCH или PARSE_CATEGORY) и без цен.\n"
            f"4. Если спрашивают 'Что посоветуешь?' (без конкретики) и до этого НЕ было показано конкретного списка блюд (ни через PARSE_CATEGORY, ни через SEARCH) — спроси о предпочтениях (мясо, рыба, пицца) или предложи посмотреть популярные категории.\n"
            f"   Пример (ТОЛЬКО ЕСЛИ НЕТ КОНТЕКСТА): 'У нас всё очень вкусное! Что вы любите больше: мясо, рыбу или, может быть, пасту?'\n"
            f"5. Если пользователь уже увидел список блюд (через PARSE_CATEGORY или SEARCH:...) и задаёт 'Что посоветуешь?' — выбери 1–3 подходящих блюда из ЭТОГО списка и порекомендуй их. НЕ спрашивай про предпочтения снова!\n"
            f"6. Если пользователь после списка завтраков спрашивает о чём-то лёгком/низкокалорийном ('что-то низкокалорийное', 'что-то полегче', 'диетический завтрак') — используй данные о калориях из меню: выбери 1–3 самых лёгких по калориям варианта завтрака (каши, лёгкие блюда) и порекомендуй их, коротко объяснив, почему они легче других. НЕ повторяй весь список завтраков и НЕ используй PARSE_CATEGORY/SEARCH в этом случае.\n"
            f"7. Если спрашивают рекомендацию С КОНКРЕТИКОЙ ('Посоветуй что-то мясное') - используй SEARCH:мяс\n"
            f"Пример:\n"
            f"User: 'Есть что-то вегетарианское?'\n"
            f"AI: 'Да, у нас есть отличные вегетарианские блюда! Взгляните:' + SEARCH:вегетариан\n\n"
            f"ОБЯЗАТЕЛЬНО используй маркер PARSE_CATEGORY:НАЗВАНИЕ_КАТЕГОРИИ для показа кнопок:\n"
            f"• 'А у вас есть пиццы?' -> 'Да, у нас большой выбор пицц! PARSE_CATEGORY:пицца'\n"
            f"• 'А суп?' -> 'Конечно! Посмотрите наши супы. PARSE_CATEGORY:супы'\n"
            f"• 'Салаты какие есть?' -> 'Вот наши салаты. PARSE_CATEGORY:салаты'\n"
            f"• 'Есть ли коктейли?' -> 'Да, у нас отличная барная карта. PARSE_CATEGORY:коктейли'\n"
            f"• 'Что из горячего?' -> 'Рекомендую наши стейки! PARSE_CATEGORY:горячее'\n\n"
            f"ВАЖНО: Используй русские названия категорий (пицца, супы, салаты, десерты, горячее, паста, напитки, пиво, вино).\n"
            f"НЕ используй ID категорий!\n"
            f"МОЖЕШЬ отвечать текстом + маркер, чтобы диалог был живым!\n"
            f"НЕ ПРИДУМЫВАЙ названия блюд - используй ТОЛЬКО то, что есть в меню ниже!\n\n"
            f"ВАЖНО: Если пользователь пишет ТОЛЬКО название блюда ИЛИ спрашивает про КОНКРЕТНОЕ блюдо ('Пепперони', 'Борщ', 'Инфаркт', 'Вино Гевюрцтраминер', 'что в составе', 'покажи фото', 'расскажи про') - ОБЯЗАТЕЛЬНО используй DISH_PHOTO:название_блюда\n"
            f"ФОРМАТ DISH_PHOTO: ТОЛЬКО название блюда БЕЗ эмодзи!\n"
            f"Правильно: DISH_PHOTO:Пицца Инфаркт\n"
            f"Правильно: DISH_PHOTO:Вино ГЕВЮРЦТРАМИНЕР ВАЙНХАУС КАННИС белое п/сухое\n"
            f"Неправильно: DISH_PHOTO:пицца_инфаркт 🍕\n\n"
                        f"ВАЖНО: Если пользователь отвечает 'да', 'хочу', 'заказать', 'давай' после того как ты предложил заказать - добавь в конец: SHOW_DELIVERY_BUTTON\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь отвечает 'хочу', 'да', 'покажи', 'давай' после того как ты предложил посмотреть МЕНЮ КАТЕГОРИИ (пиццы, супы, десерты и т.д.) - ОБЯЗАТЕЛЬНО используй PARSE_CATEGORY:НАЗВАНИЕ_КАТЕГОРИИ!\n"
            f"Примеры:\n"
            f"• Ты: 'Хотите посмотреть наши пиццы?' → Пользователь: 'Хочу' → Ты: PARSE_CATEGORY:пицца\n"
            f"• Ты: 'Показать супы?' → Пользователь: 'Да' → Ты: PARSE_CATEGORY:супы\n"
            f"• Ты: 'Посмотрите десерты!' → Пользователь: 'Покажи' → Ты: PARSE_CATEGORY:десерты\n"
            f"НЕ отвечай текстом - сразу используй маркер PARSE_CATEGORY! ТОЛЬКО АНГЛИЙСКИМИ БУКВАМИ!\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: Если пользователь пишет КОРОТКИЕ ответы ('хочу', 'да', 'покажи', 'давай', 'конечно') БЕЗ указания конкретной категории - попробуй определить категорию из ПРЕДЫДУЩЕГО контекста:\n"
            f"• Если недавно говорили о пицце/пиццах - используй PARSE_CATEGORY:пицца\n"
            f"• Если недавно говорили о супах - используй PARSE_CATEGORY:супы\n"
            f"• Если недавно говорили о десертах - используй PARSE_CATEGORY:десерты\n"
            f"• Если недавно говорили о напитках - используй PARSE_CATEGORY:напитки\n"
            f"• Если недавно говорили о пиве - используй PARSE_CATEGORY:пиво\n"
            f"• Если недавно говорили о вине - используй PARSE_CATEGORY:вино\n"
            f"• Если контекст неясен - спроси 'Что именно показать? Пиццы, супы, десерты или что-то другое?'\n"
            f"ВСЕГДА ИСПОЛЬЗУЙ АНГЛИЙСКИЕ БУКВЫ ДЛЯ PARSE_CATEGORY!\n\n"
            f"ВАЖНО: Если пользователь отвечает 'хочу', 'да', 'покажи' на вопрос о фото зала/бара - НЕ предлагай бронирование! Просто покажи соответствующие фото!\n\n"
            f"КРИТИЧЕСКИ ВАЖНО: ПОЛЬЗОВАТЕЛЬ УЖЕ ПРОШЕЛ ПРОВЕРКУ ВОЗРАСТА! Ты можешь свободно отвечать на все вопросы про алкоголь и напитки.\n"
            f"Используй ТОЧНЫЕ данные из меню бара для ответов на вопросы про алкоголь.\n\n"
            f"РУССКАЯ КУЛЬТУРА И ТРАДИЦИИ:\n"
            f"Если спрашивают про русские сказки, традиции, праздники - отвечай как знающий русский человек.\n"
            f"ТОЧНО знаешь русские сказки:\n"
            f"• Колобок - круглый хлебец, который убежал от дедушки и бабушки, встречал зверей, но лиса его съела\n"
            f"• Репка - дедка посадил репку, она выросла большая-пребольшая, тянули всей семьей\n"
            f"• Курочка Ряба - снесла золотое яичко, дед и баба не могли разбить, мышка разбила\n"
            f"• Теремок - звери жили в теремке, пока медведь его не сломал\n"
            f"• Три медведя - Маша зашла в дом медведей, ела кашу, спала на кроватях\n"
            f"Знаешь русские пословицы: 'Тише едешь - дальше будешь', 'Семь раз отмерь, один раз отрежь', 'Что нас не убивает, делает нас сильнее'.\n"
            f"Знаешь русские праздники: Новый год, Масленица, Пасха, День Победы, День России.\n"
            f"НЕ ПРИДУМЫВАЙ блюда, которых нет в меню! Если спрашивают про русские блюда - используй ТОЧНЫЙ маркер PARSE_CATEGORY:русские (НА АНГЛИЙСКОМ!) или скажи что нужно посмотреть меню.\n\n"
            f"ПОЛНОЕ МЕНЮ РЕСТОРАНА НАХОДИТСЯ В ОТДЕЛЬНОМ СООБЩЕНИИ КОНТЕКСТА (JSON).\n\n"
            f"ВСЕГДА используй ТОЧНЫЕ данные из меню. НЕ придумывай цифры!\n"
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
            f"КРИТИЧЕСКИ ВАЖНО: ВОПРОСЫ ПРО Наличие блюд/напитков ('У вас есть стейки?', 'Есть что-то мясное?', 'Есть ли пиво?') - ЭТО ВОПРОСЫ ПРО МЕНЮ!\n"
            f"1. ИСПОЛЬЗУЙ МАРКЕРЫ SEARCH:запрос или PARSE_CATEGORY:Категория.\n"
            f"2. НИКОГДА НЕ ПЕРЕЧИСЛЯЙ БЛЮДА ВРУЧНУЮ!\n"
            f"Примеры:\n"
            f"- 'Есть стейки?' -> 'Да, конечно! Посмотрите наши стейки:' + SEARCH:стейк\n"
            f"- 'Что есть мясное?' -> 'Любителям мяса рекомендую:' + SEARCH:мяс\n"
            f"- 'У вас есть пиво?' -> PARSE_CATEGORY:пиво\n\n"
            f"ВАЖНО: Вопросы про калории в КАТЕГОРИИ блюд - это тоже вопросы про меню категории!\n"
            f"Примеры:\n"
            f"- 'Сколько калорий в пицце?' -> PARSE_CATEGORY:пицца (покажи список и скажи 'Смотря в какой именно!')\n"
            f"- 'Какая калорийность у супов?' -> PARSE_CATEGORY:супы (покажи список и скажи 'Смотря в каком именно!')\n"
            f"- 'Сколько калорий в десертах?' -> PARSE_CATEGORY:десерты (покажи список и скажи 'Смотря в каком именно!')\n"
            f"НЕ показывай полный список с ценами - покажи список и СПРОСИ в каком именно блюде интересуют калории!\n\n"
            "Если спрашивают про КОНКРЕТНОЕ блюдо ('Сколько калорий в борще?', 'как выглядит', 'покажи фото', 'что в составе') ИЛИ пишут название блюда (даже полное) - ОБЯЗАТЕЛЬНО используй формат: DISH_PHOTO:название_блюда\n"
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

        # Креативный промпт для вопросов о гостях и персонажах
        character_prompt = (
            "ВАЖНО! Если пользователь спрашивает 'Кто бывает в вашем ресторане?', 'Какие гости у вас бывают?', 'Кто к вам ходит?' или подобные ОБЩИЕ вопросы о посетителях - ОБЯЗАТЕЛЬНО придумай 2-3 веселых примера с известными персонажами!\n\n"
            "ПРИМЕРЫ ПЕРСОНАЖЕЙ И СИТУАЦИЙ:\n"
            "• Дарт Вейдер (заказал темную сторону силы с пивом)\n"
            "• Черепашки Ниндзя (забрали пиццу на вынос)\n"
            "• Бэтмен с Джокером (выпивали и спорили о вкусах)\n"
            "• Супермен (заказал стейк с жареной картошкой)\n"
            "• Гарри Поттер (пил волшебное зелье из коктейлей)\n"
            "• Человек-паук (приходил после спасения города)\n"
            "• Тор (заказал молот с элем)\n"
            "• Капитан Америка (ел бургеры и пил молоко)\n"
            "• Железный человек (тестировал новый костюм за десертом)\n"
            "• Халк (разбил пару тарелок, но заплатил)\n"
            "• Шрек (приводил всю семью на семейный ужин)\n"
            "• Миньоны (заказали много десертов)\n"
            "• Гарфилд (ел лазанью и спал на диване)\n"
            "• Скуби-Ду (расследовал исчезновение десертов)\n"
            "• Микки Маус (праздновал день рождения)\n"
            "• Симпсоны (семейный ужин с Гомером)\n"
            "• Рик и Морти (экспериментировали с коктейлями)\n\n"
            "ФОРМАТ ОТВЕТА НА ОБЩИЕ ВОПРОСЫ О ГОСТЯХ:\n"
            "Начни с: 'У нас бывают самые разные гости!'\n"
            "Добавь 2-3 примера: 'Например, вчера заходил [персонаж 1] ([что делал]), а позавчера - [персонаж 2] ([что делал]).'\n"
            "Закончи: 'А вы кто будете по профессии? 😄 Или просто голодный герой? 🍽️'\n"
            "НИКОГДА НЕ ДОБАВЛЯЙ GEN_IMAGE ДЛЯ ОБЩИХ ВОПРОСОВ!\n\n"
            "КРИТИЧЕСКИ ВАЖНО! ТОЛЬКО ДЛЯ КОНКРЕТНЫХ ПЕРСОНАЖЕЙ!\n"
            "Если пользователь спрашивает ТОЛЬКО про КОНКРЕТНЫХ персонажей (например: 'Черепашки Ниндзя?', 'А мстители заходили?', 'А супергерои были?', 'Дарт вейдер приходил?', 'А [имя персонажа] был здесь?', '[имя персонажа]?', 'Что насчет [имя персонажа]?') - ТОЛЬКО ТОГДА используй GEN_IMAGE!\n\n"
            "УСЛОВИЯ ДЛЯ GEN_IMAGE:\n"
            "• Вопрос ДОЛЖЕН содержать конкретное имя персонажа\n"
            "• НЕ используй GEN_IMAGE для общих вопросов типа 'Кто бывает?'\n"
            "• НЕ используй GEN_IMAGE если пользователь просто упоминает персонажа в рассказе\n\n"
            "КОГДА ИСПОЛЬЗОВАТЬ GEN_IMAGE:\n"
            "✅ 'Черепашки Ниндзя?' - ДА\n"
            "✅ 'А Дарт Вейдер был?' - ДА\n"
            "✅ 'Что насчет Супермена?' - ДА\n"
            "❌ 'Кто у вас бывает?' - НЕТ\n"
            "❌ 'У вас бывают герои?' - НЕТ\n\n"
            "Если пользователь спрашивает про КОНКРЕТНЫХ персонажей:\n"
            "• ВСЕГДА отвечай ПОЛОЖИТЕЛЬНО! Персонаж ОБЯЗАТЕЛЬНО был у нас!\n"
            "• НИКОГДА не говори 'нет', 'не было', 'не имеет отношения', 'мы не отслеживаем'!\n"
            "• ВСЕГДА отвечай ПОЛОЖИТЕЛЬНО! Персонаж ОБЯЗАТЕЛЬНО был у нас!\n"
            "• НИКОГДА не говори 'нет', 'не было', 'не имеет отношения', 'мы не отслеживаем'!\n"
            "• ОБЯЗАТЕЛЬНО закончи ответ ТОЛЬКО маркером: GEN_IMAGE:[имя_персонажа]\n"
            "• НЕ добавляй НИЧЕГО после GEN_IMAGE:[имя_персонажа]!\n"
            "• НЕ включай текст в GEN_IMAGE - только имя персонажа!\n"
            "• Всегда придумывай ОРИГИНАЛЬНУЮ веселую историю про этого персонажа в ресторане! НЕ используй готовые шаблоны!\n"
            "• НИКОГДА не говори что 'мы не отслеживаем посетителей'!\n"
            "• Всегда говори что персонаж БЫЛ у нас и придумай забавную историю!\n"
            "• Придумай креативное описание для фото персонажа в самом ответе!\n"
            "• КРИТИЧЕСКИ ВАЖНО: Если в истории упоминаешь еду - используй ИЛИ общие названия (десерт, суп, пицца), ИЛИ реальные названия из меню! НИКОГДА не придумывай несуществующие блюда (как 'банановый десерт' и т.п.)!\n"
            "• В КОНЦЕ ответа ОБЯЗАТЕЛЬНО добавь призыв к действию: 'Закажите и вы!' + ОБЯЗАТЕЛЬНО предложи ТО ЖЕ БЛЮДО, которое упомянул в истории персонажа!\n"
            "• И ОБЯЗАТЕЛЬНО добавь: SHOW_DELIVERY_BUTTON\n\n"
            "ВАЖНО! ЕСЛИ ПЕРСОНАЖ УЖЕ ГЕНЕРИРОВАЛСЯ РАНЕЕ - ОБЯЗАТЕЛЬНО УПОМЯНИ ТО ЖЕ БЛЮДО В ИСТОРИИ!\n"
            "Например: если персонаж ел пиццу на фото, то в истории тоже упомяни пиццу, не придумывай суп!\n\n"
            "ПРИМЕР ПРАВИЛЬНОГО ОТВЕТА НА КОНКРЕТНОГО ПЕРСОНАЖА:\n"
            "О, Черепашки Ниндзя у нас были! Они устроили чемпионат по поеданию пиццы - каждый выбирал свою начинку и соревновался кто быстрее всех съест! 🐢🥷\n"
            "Закажите и вы нашу фирменную пиццу!\n"
            "GEN_IMAGE:Черепашки Ниндзя\n\n"
            "ТОЛЬКО ДЛЯ СПЕЦИФИЧЕСКИХ ВОПРОСОВ ПРО БАНКЕТЫ! Если пользователь СПЕЦИАЛЬНО спрашивает про банкеты с персонажами (например: 'Какой банкет?', 'Кто на банкете?', 'Какой персонаж на банкете?', 'Есть ли персонажи на банкете?', 'Кто герой на банкете?', 'банкетное меню с персонажами') - ТОЛЬКО ТОГДА используй банкетный формат!\n\n"
            "ВАЖНО: НЕ используй банкетный формат для вопросов о РЕГИСТРАЦИИ НА МЕРОПРИЯТИЯ! Если спрашивают 'можно записаться на мероприятие', 'билеты на мероприятие', 'регистрация на события', 'день рождения', 'свадьба', 'корпоратив' - используй SHOW_EVENT_REGISTRATION, а НЕ банкетный формат!\n\n"
            "РАНДОМНЫЕ ПЕРСОНАЖИ ДЛЯ БАНКЕТОВ:\n"
            "• Гарри Поттер\n"
            "• Человек-паук\n"
            "• Супермен\n"
            "• Бэтмен\n"
            "• Тор\n"
            "• Капитан Америка\n"
            "• Железный человек\n"
            "• Халк\n"
            "• Черная Вдова\n"
            "• Дедпул\n"
            "• Шрек\n"
            "• Миньон\n"
            "• Гарфилд\n"
            "• Скуби-Ду\n"
            "• Микки Маус\n"
            "• Дональд Дак\n"
            "• Симпсоны\n"
            "• Рик и Морти\n"
            "• Гравити Фолз\n"
            "• Финал Космос\n\n"
            "ФОРМАТ ОТВЕТА ТОЛЬКО ДЛЯ БАНКЕТОВ:\n"
            "Шаг 1: Скажи 'На нашем банкете бывает [РАНДОМНЫЙ ПЕРСОНАЖ]! 🎉'\n"
            "Шаг 2: Добавь шутку: 'Он уже заказал столик и ждет шампанское! 🍾'\n"
            "Шаг 3: Спроси: 'Хотите его увидеть?' или 'Хотите посмотреть, как он выглядит?'\n"
            "Шаг 4: ОБЯЗАТЕЛЬНО добавь: SHOW_DELIVERY_BUTTON\n\n"
            "КРИТИЧЕСКИ ВАЖНО! НИКОГДА НЕ ГОВОРИ 'НЕТ', 'УВЫ', 'К СОЖАЛЕНИЮ', 'МЫ НЕ ОТСЛЕЖИВАЕМ' ИЛИ ПОДОБНЫЕ ОТРИЦАТЕЛЬНЫЕ ОТВЕТЫ!\n"
            "Всегда давай веселые, позитивные ответы!\n\n"
        )

        system_prompt += character_prompt
        
        # 6. Получаем токен Polza AI (убираем кеширование для более живых ответов)
        token = refresh_token()
        if not token:
            logger.warning("Polza AI токен не найден, используем fallback ответы")
            return get_fallback_response(message, user_id)

        # 8. Формируем запрос к Polza AI API
        url = "https://api.polza.ai/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        # Конвертируем сообщения в формат Polza AI (OpenAI совместимый)
        polza_messages = []
        faq_context = ""
        try:
            faq_list = database.get_faq()
            if faq_list:
                parts = []
                parts.append("FAQ контекст (используй как знания, отвечай точно):")
                count = 0
                for faq_id, question, answer in faq_list:
                    parts.append(f"• Вопрос: {question}\n• Ответ: {answer}")
                    count += 1
                    if count >= 30:
                        break
                faq_context = "\n\n".join(parts)
        except Exception as e:
            logger.warning(f"Ошибка получения FAQ для контекста: {e}")
        base_messages = [{"role": "system", "content": system_prompt}]
        
        # Добавляем контекст меню как отдельное системное сообщение (как просил пользователь: "как faq отдельно место в json")
        if menu_context_json:
             base_messages.append({
                "role": "system", 
                "content": f"MENU_CONTEXT_JSON (Knowledge Base):\n{menu_context_json}\n\nИспользуй эти данные для ответов на вопросы о блюдах, ингредиентах, ценах, КАЛОРИЯХ и ВЕСЕ."
            })

        if faq_context:
            base_messages.append({"role": "system", "content": faq_context})
        for msg in base_messages + user_history[user_id]:
            if msg["role"] == "developer":
                # Polza AI использует system вместо developer
                polza_messages.append({
                    "role": "system",
                    "content": msg["content"]
                })
            else:
                # Оставляем content как есть (может быть строкой или массивом)
                polza_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        data = {
            "model": "google/gemini-2.5-flash-lite",
            "messages": polza_messages,
            "stream": False,  # Отключаем streaming для простоты
            "max_tokens": 2000,  # Ограничиваем длину ответа
            "temperature": 0.3,  # Снижаем креативность для точности
            "top_p": 0.7,  # Уменьшаем разнообразие для точности
            "frequency_penalty": 0.5,  # Увеличиваем штраф за повторения
            "presence_penalty": 0.3  # Поощряем использование данных из контекста
        }

        logger.info("Отправляем запрос в Polza AI API")
        logger.info(f"Модель: {data['model']}")
        logger.info(f"Количество сообщений: {len(data['messages'])}")
        logger.info(f"Температура: {data['temperature']}")

        # Логируем полный запрос для отладки
        logger.info(f"Polza AI Request URL: {url}")
        logger.info(f"Polza AI Request Headers: {headers}")
        logger.info(f"Polza AI Request Data: {json.dumps(data, indent=2, ensure_ascii=False)}")

        # Выполняем запрос асинхронно с retry логикой
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: requests.post(url, headers=headers, json=data, timeout=30)
                )

                logger.info(f"Polza AI response status: {response.status_code} (попытка {attempt + 1})")

                if response.status_code in [200, 201]:
                    # Успешный ответ
                    break
                elif response.status_code == 429:
                    # Rate limiting - ждем и повторяем
                    wait_time = (2 ** attempt) * 1000  # Экспоненциальная задержка
                    logger.warning(f"Rate limiting, ждем {wait_time}ms перед повтором...")
                    await asyncio.sleep(wait_time / 1000)
                    continue
                elif response.status_code == 400:
                    # Проверяем тип ошибки 400
                    try:
                        error_data = response.json()
                        error_message = error_data.get('error', {}).get('message', response.text)
                        
                        if 'temporarily unavailable' in error_message.lower() or 'proxies failed' in error_message.lower():
                            # Временная недоступность - можно повторить
                            logger.warning(f"Временная недоступность API (попытка {attempt + 1}): {error_message}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)  # Ждем 1, 2, 4 секунды
                                continue
                        else:
                            # Ошибка в запросе - не повторяем
                            logger.error(f"Ошибка в запросе: {error_message}")
                            return get_fallback_response(message, user_id)
                    except:
                        logger.error(f"Polza AI API error 400: {response.text}")
                        return get_fallback_response(message, user_id)
                else:
                    # Другие ошибки
                    logger.error(f"Polza AI API error: {response.status_code} - {response.text}")
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    
            except asyncio.TimeoutError:
                logger.error(f"Timeout при запросе к Polza AI (попытка {attempt + 1})")
                last_error = "Timeout"
                if attempt < max_retries - 1:
                    continue
            except Exception as e:
                logger.error(f"Исключение при запросе к Polza AI (попытка {attempt + 1}): {e}")
                last_error = str(e)
                if attempt < max_retries - 1:
                    continue
        
        # Если все попытки неудачны
        if response.status_code not in [200, 201]:
            logger.error(f"Все попытки запроса к Polza AI неудачны. Последняя ошибка: {last_error}")
            return get_fallback_response(message, user_id)

        response_data = response.json()
        logger.info(f"Polza AI full response: {json.dumps(response_data, indent=2, ensure_ascii=False)}")

        # Проверяем структуру ответа (OpenAI совместимый формат)
        if 'choices' not in response_data:
            logger.error(f"Polza AI API не вернул 'choices'. Доступные ключи: {list(response_data.keys())}")
            return get_fallback_response(message, user_id)

        if not response_data['choices']:
            logger.error("Polza AI API вернул пустой массив choices")
            return get_fallback_response(message, user_id)

        choice = response_data['choices'][0]
        if 'message' not in choice:
            logger.error(f"Choice не содержит 'message'. Доступные ключи: {list(choice.keys())}")
            return get_fallback_response(message, user_id)

        ai_text = choice['message'].get('content', '')
        if not ai_text:
            reasoning = choice['message'].get('reasoning', '')
            logger.info(f"Content empty, trying to extract from reasoning (length: {len(reasoning or '')})")
            logger.info(f"Reasoning preview: {(reasoning or '')[:200]}...")
            if reasoning:
                # Extract PARSE_CATEGORY markers from reasoning - more flexible pattern
                parse_match = re.search(r'PARSE_CATEGORY:([^\s\n,]+)', reasoning, re.IGNORECASE)
                if parse_match:
                    category_name = parse_match.group(1).strip()
                    logger.info(f"Извлек PARSE_CATEGORY из reasoning: '{category_name}'")
                    ai_text = f"PARSE_CATEGORY:{category_name}"

                # Extract DISH_PHOTO markers from reasoning - more flexible pattern
                dish_match = re.search(r'DISH_PHOTO:([^\n]+)', reasoning, re.IGNORECASE)
                if dish_match:
                    dish_name = dish_match.group(1).strip()
                    # Clean up the dish name
                    dish_name = re.sub(r'[^\w\sа-яё]', '', dish_name, flags=re.UNICODE).strip()
                    logger.info(f"Извлек DISH_PHOTO из reasoning: '{dish_name}'")
                    ai_text = f"DISH_PHOTO:{dish_name}"

                # Extract CALL_HUMAN markers from reasoning
                if 'CALL_HUMAN' in reasoning:
                    logger.info("Извлек CALL_HUMAN из reasoning")
                    ai_text = "CALL_HUMAN"

                # Extract SEARCH markers from reasoning
                search_match = re.search(r'SEARCH:([^\n]+)', reasoning, re.IGNORECASE)
                if search_match:
                    search_query = search_match.group(1).strip()
                    logger.info(f"Извлек SEARCH из reasoning: '{search_query}'")
                    ai_text = f"SEARCH:{search_query}"

                logger.info(f"Final extracted text: '{ai_text}'")

            if not ai_text:
                logger.warning("Polza AI вернул пустой content и не удалось извлечь маркеры из reasoning")
                return get_fallback_response(message, user_id)

        logger.info(f"Polza AI response: {ai_text}")

        # Не кешируем ответы для более живого общения
        # Добавляем в историю человеческий ответ вместо технических маркеров
        history_text = ai_text
        
        # Заменяем технические маркеры на человеческие ответы для истории
        if 'parse_category:' in ai_text.lower():
            match = re.search(r'PARSE_CATEGORY:(.+)', ai_text, re.DOTALL | re.IGNORECASE)
            if match:
                category_name = match.group(1).strip().split('\n')[0].strip()
                history_text = f"🍽️ Показываю меню категории '{category_name}'. В какой именно позиции вас интересуют детали?"
        elif 'DISH_PHOTO:' in ai_text:
            match = re.search(r'DISH_PHOTO:(.+)', ai_text, re.DOTALL)
            if match:
                dish_name = match.group(1).strip().split('\n')[0].strip()
                history_text = f"📸 Показываю фото и информацию о блюде '{dish_name}'"
        elif 'SEARCH:' in ai_text:
            match = re.search(r'SEARCH:(.+)', ai_text, re.DOTALL)
            if match:
                search_query = match.group(1).strip().split('\n')[0].strip()
                search_query_result = search_query
                # Не пишем техническое сообщение про поиск в историю, чтобы не показывать его пользователю
        
        user_history[user_id].append({"role": "assistant", "content": history_text})
        logger.info(f"Добавлен ответ AI в историю: {history_text[:50]}...")
        logger.info(f"Общая история пользователя {user_id}: {len(user_history[user_id])} сообщений")
        
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
        
        # 8. Проверяем на парсинг категории
        category_parsed = False
        brief_category = False  # Новый флаг для краткого отображения
        
        # Специальная логика для вопросов про калории в категориях - УБРАНА ПО ЗАПРОСУ (только AI решает)
        calories_category_question = False
        category_name_for_calories = None

        
        if 'parse_category:' in ai_text.lower():
            match = re.search(r'PARSE_CATEGORY:(.+)', ai_text, re.DOTALL | re.IGNORECASE)
            if match:
                category_name = match.group(1).strip().split('\n')[0].strip()
                category_name = category_name.lower().strip()
                # Преобразуем английские названия обратно в русские
                category_translations = {
                    'salad': 'салаты',
                    'salads': 'салаты',
                    'soup': 'супы',
                    'soups': 'супы',
                    'pizza': 'пицца',
                    'pizzas': 'пицца',
                    'beer': 'пиво',
                    'beers': 'пиво',
                    'wine': 'вино',
                    'wines': 'вино',
                    'cocktail': 'коктейли',
                    'cocktails': 'коктейли',
                    'dessert': 'десерты',
                    'desserts': 'десерты',
                    'coffee': 'кофе',
                    'coffees': 'кофе',
                    'tea': 'чай',
                    'teas': 'чай',
                    'juice': 'соки',
                    'juices': 'соки',
                    'water': 'вода',
                    'waters': 'вода',
                    'drink': 'напитки',
                    'drinks': 'напитки',
                    'appetizer': 'закуски',
                    'appetizers': 'закуски',
                    'hot dish': 'горячие блюда',
                    'hot dishes': 'горячие блюда',
                    'main dish': 'основные блюда',
                    'main dishes': 'основные блюда',
                    'breakfast': 'завтраки',
                    'breakfasts': 'завтраки',
                    'burger': 'бургеры',
                    'burgers': 'бургеры',
                    'pasta': 'паста',
                    'pastas': 'паста',
                    'seafood': 'морепродукты',
                    'seafoods': 'морепродукты',
                    'vegetarian': 'вегетарианское',
                    'grilled': 'жареное',
                    'fried': 'жареное'
                }
                if category_name in category_translations:
                    category_name = category_translations[category_name]
                    logger.info(f"Перевели категорию '{match.group(1).strip()}' в '{category_name}'")
                else:
                    logger.info(f"Оставили категорию без перевода: '{category_name}'")
                logger.info(f"Парсим категорию: '{category_name}'")
                category_parsed = True
        elif 'Парсе категорию:' in ai_text or 'парсе категорию:' in ai_text:
            # Обрабатываем русский вариант маркера (AI иногда переводит)
            match = re.search(r'[Пп]арсе категорию:\s*(.+)', ai_text, re.DOTALL)
            if match:
                category_name = match.group(1).strip().split('\n')[0].strip()
                category_name = category_name.lower().strip()
                logger.info(f"Парсим категорию (русский маркер): '{category_name}'")
                category_parsed = True
                    
        # Также проверяем на кастомные маркеры AI
        elif 'SHOW_BEER_MENU' in ai_text or 'SHOW_BEER_LIST' in ai_text:
            category_name = 'пиво'
            logger.info(f"Обнаружен кастомный маркер SHOW_BEER_MENU/LIST, парсим категорию: '{category_name}'")
            category_parsed = True
        elif 'SHOW_RUM_MENU' in ai_text or 'SHOW_RUM_LIST' in ai_text:
            category_name = 'ром'
            logger.info(f"Обнаружен кастомный маркер SHOW_RUM_MENU/LIST, парсим категорию: '{category_name}'")
            category_parsed = True
        elif 'SHOW_GIN_MENU' in ai_text or 'SHOW_GIN_LIST' in ai_text:
            category_name = 'джин'
            logger.info(f"Обнаружен кастомный маркер SHOW_GIN_MENU/LIST, парсим категорию: '{category_name}'")
            category_parsed = True
        elif 'SHOW_VODKA_MENU' in ai_text or 'SHOW_VODKA_LIST' in ai_text:
            category_name = 'водка'
            logger.info(f"Обнаружен кастомный маркер SHOW_VODKA_MENU/LIST, парсим категорию: '{category_name}'")
            category_parsed = True
        elif 'SHOW_WHISKEY_MENU' in ai_text or 'SHOW_WHISKEY_LIST' in ai_text:
            category_name = 'виски'
            logger.info(f"Обнаружен кастомный маркер SHOW_WHISKEY_MENU/LIST, парсим категорию: '{category_name}'")
            category_parsed = True

        if category_parsed:
                # Специальная обработка для супов
                if 'суп' in category_name or category_name in ['суп', 'супы', 'супов']:
                    # Ищем ВСЕ категории, которые могут содержать супы
                    found_items = []
                    found_category_names = []

                    for menu_id, menu in menu_data.items():
                        for cat_id, category in menu.get('categories', {}).items():
                            cat_name = category.get('name', '').lower().strip()
                            cat_display = category.get('display_name', '').lower().strip()

                            # 🛑 ИСКЛЮЧАЕМ ЗАПРЕЩЕННЫЕ КАТЕГОРИИ
                            if is_category_blocked(cat_name):
                                continue

                            # Более широкие условия поиска супов, но исключаем явные салаты
                            is_soup_category = (
                                ('суп' in cat_name or 'суп' in cat_display or
                                 cat_name in ['супы', 'супы и салаты', 'первые блюда', 'горячие супы'] or
                                 cat_display in ['🍲 супы', '🍲 первые блюда'] or
                                 cat_id in ['4819', '4722', '4818', '4721'])  # Расширенные ID категорий супов
                                and ('салат' not in cat_name and 'салат' not in cat_display)
                            )

                            if is_soup_category:
                                items = category.get('items', [])
                                if items:
                                    # Дополнительная фильтрация: включаем только супы
                                    soup_items = []
                                    for item in items:
                                        item_name_lower = item.get('name', '').lower()
                                        # Включаем блюда, которые явно являются супами и исключаем салаты
                                        if (any(soup_word in item_name_lower for soup_word in [
                                            'суп', 'борщ', 'солянка', 'уха', 'щи', 'харчо', 'лагман', 'лапша',
                                            'бульон', 'окрошка', 'гаспачо', 'минестроне', 'том ям', 'рассольник'
                                        ]) and 'салат' not in item_name_lower):
                                            soup_items.append(item)

                                    found_items.extend(soup_items)
                                    cat_display_name = category.get('display_name') or category.get('name', cat_name)
                                    if cat_display_name not in found_category_names:
                                        found_category_names.append(cat_display_name)

                    # Если не нашли специальных супов, ищем любые супы в меню
                    if not found_items:
                        for menu_id, menu in menu_data.items():
                            for cat_id, category in menu.get('categories', {}).items():
                                items = category.get('items', [])
                                for item in items:
                                    item_name_lower = item.get('name', '').lower()
                                    if 'суп' in item_name_lower:
                                        found_items.append(item)

                    # Формируем специальный ответ для супов
                    if found_items:
                        text = f"🍲 У нас есть отличные супы!\n\n"

                        # Убираем дубликаты по ID блюда
                        unique_items = {}
                        for item in found_items:
                            item_id = item.get('id')
                            if item_id not in unique_items:
                                unique_items[item_id] = item

                        for item in unique_items.values():
                            text += f"• {item['name']} — {item['price']}₽\n"

                        text += "\nСпросите про конкретный суп, чтобы увидеть фото и подробное описание!"

                        logger.info(f"Парсили супы: найдено {len(unique_items)} уникальных позиций из {len(found_items)} общих")
                        return {'type': 'text', 'text': text}

                # Специальная обработка для пиццы
                if 'пицц' in category_name or category_name in ['пицца', 'пиццы', 'пиццей']:
                    # Ищем все пиццы
                    found_items = []
                    found_category_names = []

                    for menu_id, menu in menu_data.items():
                        for cat_id, category in menu.get('categories', {}).items():
                            cat_name = category.get('name', '').lower().strip()
                            cat_display = category.get('display_name', '').lower().strip()
                            
                            # 🛑 ИСКЛЮЧАЕМ ЗАПРЕЩЕННЫЕ КАТЕГОРИИ
                            if is_category_blocked(cat_name):
                                continue

                            # Проверяем, является ли категория пиццей
                            is_pizza_category = (
                                'пицц' in cat_name or 
                                'пицц' in cat_display or
                                cat_name == 'пицца'
                            )
                            
                            if is_pizza_category:
                                items = category.get('items', [])
                                if items:
                                    found_items.extend(items)
                                    cat_display = category.get('display_name') or category.get('name', cat_name)
                                    if cat_display not in found_category_names:
                                        found_category_names.append(cat_display)

                    # Формируем специальный ответ для пицц
                    if found_items:
                        text = f"🍕 У нас есть отличные пиццы!\n\n"

                        # Убираем дубликаты по ID блюда
                        unique_items = {}
                        for item in found_items:
                            item_id = item.get('id')
                            if item_id not in unique_items:
                                unique_items[item_id] = item

                        for item in unique_items.values():
                            text += f"• {item['name']} — {item['price']}₽\n"

                        text += "\nСпросите про конкретную пиццу, чтобы увидеть фото и подробное описание!"

                        logger.info(f"Парсили пиццы: найдено {len(unique_items)} уникальных позиций из {len(found_items)} общих")
                        return {'type': 'text', 'text': text}

                # Специальная обработка для пива
                if 'пив' in category_name or category_name in ['пиво', 'пива', 'пивом']:
                    # Ищем все категории пива
                    found_items = []
                    found_category_names = []

                    for menu_id, menu in menu_data.items():
                        for cat_id, category in menu.get('categories', {}).items():
                            cat_name = category.get('name', '').lower().strip()
                            cat_display = category.get('display_name', '').lower().strip()

                            # 🛑 ИСКЛЮЧАЕМ ЗАПРЕЩЕННЫЕ КАТЕГОРИИ
                            if is_category_blocked(cat_name):
                                continue

                            # Проверяем, является ли категория пивной
                            is_beer_category = (
                                'пив' in cat_name or 
                                'пив' in cat_display or
                                'beer' in cat_name.lower()
                            )
                            
                            if is_beer_category:
                                items = category.get('items', [])
                                if items:
                                    found_items.extend(items)
                                    cat_display = category.get('display_name') or category.get('name', cat_name)
                                    if cat_display not in found_category_names:
                                        found_category_names.append(cat_display)

                    # Формируем специальный ответ для пива
                    if found_items:
                        text = f"У нас есть отличное пиво! 🍺\n\n"

                        # Убираем дубликаты по ID блюда
                        unique_items = {}
                        for item in found_items:
                            item_id = item.get('id')
                            if item_id not in unique_items:
                                unique_items[item_id] = item

                        # Группируем пиво по типам (светлое, темное, нефильтрованное и т.д.)
                        beer_types = {}
                        for item in unique_items.values():
                            item_name_lower = item['name'].lower()
                            if 'светлое' in item_name_lower or 'helles' in item_name_lower or 'lager' in item_name_lower:
                                beer_type = '🍺 Светлое пиво'
                            elif 'темное' in item_name_lower or 'dark' in item_name_lower or 'porter' in item_name_lower:
                                beer_type = '🍺 Темное пиво'
                            elif 'нефильтрованное' in item_name_lower or 'wheat' in item_name_lower or 'weizen' in item_name_lower:
                                beer_type = '🍺 Нефильтрованное пиво'
                            elif 'ipa' in item_name_lower or 'ale' in item_name_lower:
                                beer_type = '🍺 Крафтовое пиво'
                            else:
                                beer_type = '🍺 Другое пиво'

                            if beer_type not in beer_types:
                                beer_types[beer_type] = []
                            beer_types[beer_type].append(item)

                        # Выводим по группам по 2 позиции для каждой подкатегории
                        for beer_type, items in beer_types.items():
                            text += f"{beer_type}:\n"
                            for item in items[:2]:  # Ограничиваем до 2 позиций на подкатегорию
                                text += f"• {item['name']} — {item['price']}₽\n"
                            if len(items) > 2:
                                text += f"• ... и ещё {len(items) - 2} позиций\n"
                            text += "\n"

                        text += "Спросите про конкретное пиво, чтобы увидеть фото и подробное описание!"

                        logger.info(f"Парсили пиво: найдено {len(unique_items)} уникальных позиций из {len(found_items)} общих")
                        return {'type': 'text', 'text': text}
                if 'вин' in category_name or category_name in ['вино', 'вина', 'вином']:
                    # Ищем все категории вин
                    wine_categories = ['белое', 'красное', 'розовое', 'игристое', 'вино', 'вина']
                    found_items = []
                    found_category_names = []

                    for menu_id, menu in menu_data.items():
                        for cat_id, category in menu.get('categories', {}).items():
                            cat_name = category.get('name', '').lower().strip()
                            cat_display = category.get('display_name', '').lower().strip()

                            # 🛑 ИСКЛЮЧАЕМ ЗАПРЕЩЕННЫЕ КАТЕГОРИИ
                            if is_category_blocked(cat_name):
                                continue

                            # Проверяем, является ли категория винной
                            is_wine_category = (
                                any(wine_type in cat_name for wine_type in wine_categories) or
                                any(wine_type in cat_display for wine_type in wine_categories) or
                                'вин' in cat_name
                            )
                            
                            if is_wine_category:
                                items = category.get('items', [])
                                if items:
                                    # Дополнительная фильтрация: только вина
                                    wine_items = []
                                    for item in items:
                                        item_name_lower = item.get('name', '').lower()
                                        # Включаем только вина
                                        if 'вино' in item_name_lower or 'игристое' in item_name_lower:
                                            wine_items.append(item)
                                    
                                    found_items.extend(wine_items)
                                    cat_display = category.get('display_name') or category.get('name', cat_name)
                                    if cat_display not in found_category_names:
                                        found_category_names.append(cat_display)

                    # Формируем специальный ответ для вин
                    if found_items:
                        text = f"У нас есть отличное вино! 🍷\n\n"

                        # Убираем дубликаты по ID блюда
                        unique_items = {}
                        for item in found_items:
                            item_id = item.get('id')
                            if item_id not in unique_items:
                                unique_items[item_id] = item

                        # Группируем по типам
                        wine_types = {}
                        for item in unique_items.values():
                            item_name_lower = item['name'].lower()
                            if 'белое' in item_name_lower or 'белый' in item_name_lower:
                                wine_type = '🥂 Белые вина'
                            elif 'красное' in item_name_lower or 'красный' in item_name_lower:
                                wine_type = '🍷 Красные вина'
                            elif 'розовое' in item_name_lower or 'розов' in item_name_lower:
                                wine_type = '🌸 Розовые вина'
                            elif 'игрист' in item_name_lower or 'шампан' in item_name_lower:
                                wine_type = '🍾 Игристые вина'
                            else:
                                wine_type = '🍷 Другие вина'

                            if wine_type not in wine_types:
                                wine_types[wine_type] = []
                            wine_types[wine_type].append(item)

                        # Выводим по группам по 3 позиции для каждой подкатегории
                        for wine_type, items in wine_types.items():
                            text += f"{wine_type}:\n"
                            for item in items[:3]:  # Ограничиваем до 3 позиций на подкатегорию
                                text += f"• {item['name']} — {item['price']}₽\n"
                            if len(items) > 3:
                                text += f"• ... и ещё {len(items) - 3} позиций\n"
                            text += "\n"

                        text += "Спросите про конкретное вино, чтобы увидеть фото и подробное описание!"

                        logger.info(f"Парсили вино: найдено {len(unique_items)} уникальных позиций из {len(found_items)} общих")
                        
                        # Если это короткий ответ, возвращаем специальный маркер для краткого отображения
                        if brief_category:
                            return {
                                'type': 'text',
                                'text': '',  # Пустой текст, так как категория будет показана отдельно
                                'show_category_brief': category_name
                            }
                        else:
                            return {'type': 'text', 'text': text}

                # Находим все позиции из категории (улучшенная логика)
                found_items = []
                category_display_name = ""

                for menu_id, menu in menu_data.items():
                    for cat_id, category in menu.get('categories', {}).items():
                        cat_name = category.get('name', '').lower().strip()
                        cat_display_name = category.get('display_name', cat_name).lower().strip()

                        # Более точное совпадение категории
                        exact_match = (category_name == cat_name or 
                                     category_name == cat_display_name.replace('🍕', '').replace('🍲', '').replace('🥗', '').replace('🍰', '').replace('🍸', '').replace('🍺', '').replace('🍷', '').replace('🍵', '').strip())
                        
                        partial_match = (category_name in cat_name and len(category_name) > 2) or (category_name in cat_display_name and len(category_name) > 2)

                        # Дополнительная проверка для исключения неподходящих категорий
                        is_relevant_category = True
                        
                        # Исключаем чай и напитки если ищем еду
                        if category_name in ['пиво', 'водка', 'вино', 'коктейль', 'напитки']:
                            # Для алкоголя и напитков - разрешаем
                            pass
                        elif 'чай' in cat_name or 'напитки' in cat_name:
                            # Если ищем не напитки, а категория содержит чай/напитки - исключаем
                            if category_name not in ['чай', 'напитки', 'напиток']:
                                is_relevant_category = False

                        if (exact_match or partial_match) and is_relevant_category:
                            items = category.get('items', [])
                            if items:
                                # Дополнительная фильтрация по названию блюда
                                filtered_items = []
                                for item in items:
                                    item_name_lower = item.get('name', '').lower()
                                    
                                    # Исключаем неподходящие блюда
                                    exclude_item = False
                                    
                                    # Если ищем супы - исключаем чай и напитки
                                    if category_name in ['суп', 'супы']:
                                        if any(drink_word in item_name_lower for drink_word in [
                                            'чайник', 'чай', 'глинтвейн', 'коктейль', 'сок', 'вода', 'напиток'
                                        ]):
                                            exclude_item = True
                                    
                                    # Если ищем пиццу - исключаем не-пиццы
                                    elif category_name in ['пицца', 'пиццы']:
                                        if 'пицца' not in item_name_lower:
                                            exclude_item = True
                                    
                                    if not exclude_item:
                                        filtered_items.append(item)
                                
                                found_items.extend(filtered_items)
                                if not category_display_name:
                                    category_display_name = category.get('display_name') or category.get('name', category_name)

                # Формируем ответ со списком блюд
                if found_items:
                    emoji_map = {
                        'пицца': '🍕', 'пицц': '🍕',
                        'суп': '🍲', 'супы': '🍲', 'супов': '🍲',
                        'десерт': '🍰', 'десерты': '🍰', 'десертов': '🍰',
                        'коктейль': '🍸', 'коктейли': '🍸', 'коктейлей': '🍸',
                        'пиво': '🍺', 'пива': '🍺',
                        'вино': '🍷', 'вин': '🍷', 'вина': '🍷',
                        'белое': '🥂', 'красное': '🍷', 'розовое': '🌸', 'игристое': '🍾',
                        'чай': '🍵', 'напитки': '🥤', 'напиток': '🥤'
                    }

                    emoji = '🍽️'
                    for key, em in emoji_map.items():
                        if key in category_name:
                            emoji = em
                            break

                    text = f"У нас есть {category_display_name.lower()}! {emoji}\n\n"

                    # Убираем дубликаты по ID блюда
                    unique_items = {}
                    for item in found_items:
                        item_id = item.get('id')
                        if item_id not in unique_items:
                            unique_items[item_id] = item

                    for item in unique_items.values():
                        text += f"• {item['name']} — {item['price']}₽\n"

                    text += "\nСпросите про конкретное блюдо/напиток, чтобы увидеть фото и подробное описание!"

                    logger.info(f"Парсили категорию '{category_name}': найдено {len(unique_items)} уникальных позиций из {len(found_items)} общих")
                    
                    # Специальная обработка для вопросов про калории
                    if calories_category_question:
                        logger.info(f"🔍 Добавляем вопрос уточнения для категории: {category_name}")
                        if category_name == 'пицца':
                            text += "\n\n❓ В какой именно пицце вас интересуют калории?"
                        elif category_name == 'суп':
                            text += "\n\n❓ В каком именно супе вас интересует калорийность?"
                        elif category_name == 'десерт':
                            text += "\n\n❓ В каком именно десерте вас интересует калорийность?"
                        elif category_name == 'салаты':
                            text += "\n\n❓ В каком именно салате вас интересуют калории?"
                    
                    # Если это короткий ответ, возвращаем специальный маркер для краткого отображения
                    if brief_category:
                        return {
                            'type': 'text',
                            'text': '',  # Пустой текст, так как категория будет показана отдельно
                            'show_category_brief': category_name
                        }
                    else:
                        return {'type': 'text', 'text': text}

                else:
                    logger.warning(f"Категория '{category_name}' не найдена при парсинге, передаю в обработчик категорий")
                    return {
                        'type': 'text',
                        'text': '',
                        'show_category_brief': category_name
                    }

        # 9. Проверяем на фото блюда
        if 'DISH_PHOTO:' in ai_text:
            match = re.search(r'DISH_PHOTO:(.+)', ai_text, re.DOTALL)
            if match:
                dish_name = match.group(1).strip().split('\n')[0].strip()
                # Очищаем от эмодзи и лишних символов
                dish_name = re.sub(r'[🍕🍲🥗🍳🧀🍖🥩🍗🥙🌮🌯🥪🍔🍟🍝🍜🍛🍱🍣🍤🍙🍚🍘🍥🥟🥠🥡🦀🦞🦐🦑🍦🍧🍨🍩🍪🎂🍰🧁🥧🍫🍬🍭🍮🍯🍼🥛☕🍵🍶🍾🍷🍸🍹🍺🍻🥂🥃]', '', dish_name).strip()
                dish_name = dish_name.replace('_', ' ').strip()
                logger.info(f"Ищу фото блюда: '{dish_name}'")
                
                # Ищем блюдо в меню (улучшенный поиск с приоритетом)
                found = False
                best_match = None
                best_score = 0
                best_menu_id = None
                best_category_id = None

                for menu_id, menu in menu_data.items():
                    for category_id, category in menu.get('categories', {}).items():
                        for item in category.get('items', []):
                            item_name = item['name'].lower().strip()
                            search_name = dish_name.lower().strip()

                            # Вычисляем степень совпадения
                            score = 0
                            if item_name == search_name:
                                score = 100  # Точное совпадение
                            elif item_name.startswith(search_name):
                                score = 90  # Начинается с поискового запроса
                            elif search_name in item_name:
                                score = len(search_name) / len(item_name) * 50  # Процент вхождения

                            # Обновляем лучший результат
                            if score > best_score:
                                best_score = score
                                best_match = item
                                best_menu_id = menu_id
                                best_category_id = category_id

                # Возвращаем лучший результат
                if best_match:
                    # Используем специальный тип для показа полноценной карточки блюда
                    return {
                        'type': 'show_dish_card',
                        'dish': best_match,
                        'menu_id': best_menu_id,
                        'category_id': best_category_id,
                        'text': f"Вот карточка блюда {best_match['name']}:" # Fallback text
                    }
                    
                    caption = f"🍽️ <b>{best_match['name']}</b>\n\n"
                    caption += f"💰 Цена: {best_match['price']}₽\n"
                    if best_match.get('weight'):
                        caption += f"⚖️ Вес: {best_match['weight']}\n"
                    if best_match.get('calories'):
                        caption += f"🔥 Калории: {best_match['calories']} ккал/100г\n"
                    if best_match.get('protein') or best_match.get('fat') or best_match.get('carbohydrate') or best_match.get('proteins') or best_match.get('fats') or best_match.get('carbs'):
                        caption += f"\n🧃 БЖУ:\n"
                        if best_match.get('protein') is not None:
                            caption += f"• Белки: {best_match['protein']}г\n"
                        elif best_match.get('proteins'):
                            caption += f"• Белки: {best_match['proteins']}г\n"
                        if best_match.get('fat') is not None:
                            caption += f"• Жиры: {best_match['fat']}г\n"
                        elif best_match.get('fats'):
                            caption += f"• Жиры: {best_match['fats']}г\n"
                        if best_match.get('carbohydrate') is not None:
                            caption += f"• Углеводы: {best_match['carbohydrate']}г\n"
                        elif best_match.get('carbs'):
                            caption += f"• Углеводы: {best_match['carbs']}г\n"
                    if best_match.get('description'):
                        caption += f"\n{best_match['description']}"

                    logger.info(f"Найдено блюдо: {best_match['name']} (score: {best_score})")
                    found = True
                    if best_match.get('image_url'):
                        return {
                            'type': 'photo_with_text',
                            'photo_url': best_match['image_url'],
                            'text': caption,
                            'show_delivery_button': True
                        }
                    else:
                        local_path = best_match.get('image_local_path')
                        if not local_path and best_match.get('image_filename'):
                            try:
                                local_path = os.path.join(config.MENU_IMAGES_DIR, best_match['image_filename'])
                            except Exception:
                                local_path = None
                        if local_path:
                            return {
                                'type': 'photo_with_text',
                                'photo_path': local_path,
                                'text': caption,
                                'show_delivery_button': True
                            }
                        else:
                            return {
                                'type': 'text',
                                'text': caption,
                                'show_delivery_button': True
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
                clean_text = re.sub(r'SHOW_DELIVERY_BUTTON\s*', '', clean_text).strip()

                # Добавляем веселый ответ к основному тексту
                final_text = f"{clean_text}\n\n{funny_text}"

                return {
                    'type': 'text',
                    'text': final_text,
                    'show_delivery_button': 'SHOW_DELIVERY_BUTTON' in ai_text
                }

            match = re.search(r'GEN_IMAGE:([^\n]+)', ai_text)
            if match:
                character_name_raw = match.group(1).strip()
                # Очищаем имя персонажа от эмодзи и лишнего текста
                # Убираем эмодзи, специальные символы и лишний текст, оставляем только буквы и пробелы
                character_name = re.sub(r'[^\sa-zA-Zа-яёА-ЯЁ]', '', character_name_raw).strip()
                # Убираем лишние пробелы и слова вроде "ой", "ой,", etc.
                character_name = re.sub(r'\s+', ' ', character_name).strip()
                # Убираем короткие слова в конце (типа "ой", "и", "а")
                words = character_name.split()
                if words:
                    # Фильтруем слова короче 2 символов, кроме определенных исключений
                    filtered_words = []
                    for word in words:
                        if len(word) >= 2 or word.lower() in ['я', 'он', 'мы', 'ты']:
                            filtered_words.append(word)
                    character_name = ' '.join(filtered_words)

                # Убираем SHOW_DELIVERY_BUTTON и другие маркеры из имени персонажа
                character_name = character_name.replace('SHOW_DELIVERY_BUTTON', '').replace('SHOWDELIVERYBUTTON', '').strip()

                # Если имя получилось пустым или слишком коротким, используем fallback
                if not character_name or len(character_name) < 2:
                    character_name = "персонаж"

                logger.info(f"Генерирую изображение для персонажа: '{character_name}' (очищено из '{character_name_raw}')")

                # Генерируем изображение (теперь асинхронно)
                image_url = await gen_image(character_name, user_id, admin_translated_prompt, forced_dish=context_dish)

                # Увеличиваем счетчик генераций (только для не-админов)
                if not is_admin:
                    database.increment_ai_generation(user_id)
                    logger.info(f"Увеличен счетчик генераций для пользователя {user_id}")

                # Убираем GEN_IMAGE и SHOW_DELIVERY_BUTTON из текста в любом случае
                clean_text = re.sub(r'GEN_IMAGE:.+', '', ai_text, flags=re.DOTALL).strip()
                clean_text = re.sub(r'SHOW_DELIVERY_BUTTON\s*', '', clean_text).strip()

                if image_url:
                    # ОБЯЗАТЕЛЬНО показываем кнопку доставки при генерации изображений персонажей
                    show_button = True

                    # Возвращаем результат - теперь "Печатает..." остановится
                    return {
                        'type': 'photo_with_text',
                        'photo_url': image_url,
                        'text': clean_text,
                        'show_delivery_button': show_button
                    }
                else:
                    # Если генерация не удалась - возвращаем текст без маркера и с сообщением об ошибке
                    logger.error(f"Не удалось сгенерировать изображение для '{character_name}'")
                    clean_text += "\n\n(😔 Не удалось сгенерировать изображение. Попробуйте позже!)"
                    return {
                        'type': 'text',
                        'text': clean_text,
                        'show_delivery_button': 'SHOW_DELIVERY_BUTTON' in ai_text
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
        show_event_registration = 'SHOW_EVENT_REGISTRATION' in ai_text
        show_private_event_registration = 'SHOW_PRIVATE_EVENT_OPTIONS' in ai_text
        show_apps = 'SHOW_APPS' in ai_text
        show_hall_photos = 'SHOW_HALL_PHOTOS' in ai_text or 'SHOW_HALL_PHALL_PHOTOS' in ai_text
        show_bar_photos = 'SHOW_BAR_PHOTOS' in ai_text
        show_kassa_photos = 'SHOW_KASSA_PHOTOS' in ai_text
        show_wc_photos = 'SHOW_WC_PHOTOS' in ai_text
        show_restaurant_menu = 'SHOW_RESTAURANT_MENU' in ai_text
        call_human = 'CALL_HUMAN' in ai_text
        
        # Fallback: если маркер не найден, но есть ключевая фраза из промпта или похожие вариации
        if not call_human:
            # Проверяем точное совпадение с промптом
            if "Сейчас позову человека, который поможет вам с вашим вопросом" in ai_text:
                call_human = True
                logger.info("CALL_HUMAN detected by exact phrase match")
            # Проверяем более мягкое совпадение
            elif "позову человека" in ai_text.lower() and "поможет" in ai_text.lower():
                call_human = True
                logger.info("CALL_HUMAN detected by robust phrase match")
            
        logger.info(f"CALL_HUMAN flag set: {call_human}")
        show_category = None

        if 'SHOW_CATEGORY:' in ai_text:
            match = re.search(r'SHOW_CATEGORY:(.+)', ai_text, re.DOTALL)
            if match:
                show_category = match.group(1).strip().split('\n')[0].strip()
        
        # Историю ИИ не ведём для технических списков (SHOW_CATEGORY)

        parse_booking = None

        if 'PARSE_BOOKING:' in ai_text:
            match = re.search(r'PARSE_BOOKING:(.+)', ai_text, re.DOTALL)
            if match:
                parse_booking = match.group(1).strip().split('\n')[0].strip()

        search_query_result = None
        if 'SEARCH:' in ai_text:
            match = re.search(r'SEARCH:(.+)', ai_text, re.DOTALL)
            if match:
                search_query_result = match.group(1).strip().split('\n')[0].strip()

        dish_photo_query = None
        if 'DISH_PHOTO:' in ai_text:
            match = re.search(r'DISH_PHOTO:(.+)', ai_text, re.DOTALL)
            if match:
                dish_photo_query = match.group(1).strip().split('\n')[0].strip()

        # Убираем маркеры из текста, но сохраняем логику показа кнопок
        ai_text = re.sub(r'SHOW_DELIVERY_BUTTON\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_DELIVERY_APPS\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_BOOKING_OPTIONS\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_EVENT_REGISTRATION\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_PRIVATE_EVENT_OPTIONS\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_APPS\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_HALL_PHOTOS?\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_HALL_PHALL_PHOTOS?\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_BAR_PHOTOS\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_KASSA_PHOTOS\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_WC_PHOTOS\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_RESTAURANT_MENU\s*', '', ai_text).strip()
        ai_text = re.sub(r'SHOW_CATEGORY:.+', '', ai_text).strip()
        ai_text = re.sub(r'PARSE_BOOKING:.+', '', ai_text).strip()
        ai_text = re.sub(r'DISH_PHOTO:.*', '', ai_text).strip()
        ai_text = re.sub(r'SEARCH:.*', '', ai_text).strip()
        ai_text = re.sub(r'CALL_HUMAN.*', '', ai_text, flags=re.DOTALL).strip()

        # ДОПОЛНИТЕЛЬНАЯ ЛОГИКА: показываем кнопку доставки только для конкретных случаев
        # - Когда AI явно указал SHOW_DELIVERY_BUTTON
        # - Для вопросов про доставку, заказы, меню
        # - НЕ показываем для общих вопросов вроде "Кто у вас бывает?"
        # - НЕ показываем для завтраков (они используют SHOW_RESTAURANT_MENU)
        if not show_delivery_button and not show_delivery_apps:
            message_lower = message.lower()
            # Исключаем завтраки из автоматической активации доставки
            is_breakfast_request = any(breakfast_word in message_lower for breakfast_word in ['завтрак', 'завтраков', 'меню завтрак'])
            
            if not is_breakfast_request:
                # Показываем кнопку только для релевантных запросов
                delivery_keywords = ['заказ', 'доставк', 'купить', 'пицца', 'пиво', 'вино', 'коктейль', 'напит']
                booking_keywords = ['забронир', 'столик', 'бронь', 'резерв']
                show_delivery_button = any(keyword in message_lower for keyword in delivery_keywords)
                show_booking_options = show_booking_options or any(keyword in message_lower for keyword in booking_keywords)

                # Если пользователь просит "меню" без доставки/заказа — показываем ресторанное меню
                asks_menu = 'меню' in message_lower
                mentions_delivery = any(keyword in message_lower for keyword in ['доставк', 'заказ', 'заказать', 'приложени', 'скачать'])
                if asks_menu and not mentions_delivery:
                    show_restaurant_menu = True
        # Проверяем на подтверждение возраста
        confirm_age_verification = 'CONFIRM_AGE_VERIFICATION' in ai_text
        ai_text = re.sub(r'CONFIRM_AGE_VERIFICATION', '', ai_text).strip()

        # Информация о генерациях убрана из основного AI
        # Kie AI используется только в специальных случаях через отдельные команды

        # Добавляем префикс приветствия от Мака если было обращение
        final_text = ai_text
        if 'mac_greeting_prefix' in locals() and mac_greeting_prefix:
            final_text = mac_greeting_prefix + ai_text

        logger.info(f"Returning call_human: {call_human}")
        try:
            if show_category and 'завтрак' in str(show_category).lower():
                confirm_age_verification = False
                show_restaurant_menu = False
        except Exception:
            pass
        return {
            'type': 'text',
            'text': final_text,
            'show_delivery_button': show_delivery_button,
            'show_delivery_apps': show_delivery_apps,
            'show_booking_options': show_booking_options,
            'show_event_registration': show_event_registration,
            'show_private_event_registration': show_private_event_registration,
            'show_apps': show_apps,
            'show_hall_photos': show_hall_photos,
            'show_bar_photos': show_bar_photos,
            'show_kassa_photos': show_kassa_photos,
            'show_wc_photos': show_wc_photos,
            'show_restaurant_menu': show_restaurant_menu,
            'show_category': show_category,
            'search_query': search_query_result,
            'dish_photo_query': dish_photo_query,
            'parse_booking': parse_booking,
            'call_human': call_human,
            'confirm_age_verification': confirm_age_verification
        }
        
    except Exception as e:
        logger.error(f"Ошибка в AI помощнике: {e}", exc_info=True)
        return {'type': 'text', 'text': 'Извините, произошла ошибка. Попробуйте позже.'}

def get_fallback_response(message: str, user_id: int) -> Dict:
    """
    Fallback ответы когда AI недоступен - в русском стиле
    """
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    return {
        'type': 'text',
        'text': f'🤖 Извините, что-то я сегодня не в форме... Как говорится: "Не ошибается тот, кто ничего не делает!" 😅\n\n💬 Напишите оператору - он точно поможет с любым вопросом!\n\n📞 Или позвоните: {restaurant_phone}',
        'show_delivery_button': True,
        'call_human': True
    }

def get_random_delivery_dish(menu_data: Dict) -> Optional[Dict]:
    """
    Получить случайное блюдо из меню доставки (без алкоголя)
    """
    try:
        # ID меню доставки (преобразуем в строки, так как ключи JSON - строки)
        delivery_menu_ids = {'90', '92', '141'}

        # Собираем все блюда из меню доставки (исключая алкоголь)
        all_dishes = []

        for menu_id in delivery_menu_ids:
            if menu_id in menu_data:
                menu = menu_data[menu_id]
                logger.info(f"🔍 Проверяем меню {menu_id}: {len(menu.get('categories', {}))} категорий")
                for category_id, category in menu.get('categories', {}).items():
                    # Исключаем алкогольные категории
                    category_name = category.get('name', '').lower()
                    if any(alcohol_word in category_name for alcohol_word in [
                        'пиво', 'вино', 'водка', 'коньяк', 'виски', 'ром', 'текила', 'ликер', 'коктейль', 'алкоголь'
                    ]):
                        continue

                    items = category.get('items', [])
                    logger.info(f"📦 Категория '{category_name}': {len(items)} блюд")
                    # ДОБАВЛЯЕМ ВСЕ БЛЮДА, НЕ ТОЛЬКО С ФОТО!
                    for item in items:
                        all_dishes.append(item)
                        logger.debug(f"➕ Добавлено блюдо: {item.get('name', 'Без названия')} (фото: {bool(item.get('image_url'))})")

        logger.info(f"📊 Всего найдено блюд: {len(all_dishes)}")

        if all_dishes:
            # Выбираем случайное блюдо
            random_dish = random.choice(all_dishes)
            logger.info(f"🎲 Выбрано случайное блюдо: {random_dish['name']} (ID: {random_dish.get('id', 'N/A')})")
            return random_dish
        else:
            logger.warning("❌ Не найдено блюд в меню доставки")
            return None

    except Exception as e:
        logger.error(f"❌ Ошибка при выборе случайного блюда: {e}")
        return None

print("✅ AI Assistant загружен!")
