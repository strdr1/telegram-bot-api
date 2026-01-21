#!/usr/bin/env python3
"""
character_parser.py - Парсер персонажей для генерации изображений
"""

import asyncio
import aiohttp
import json
import os
import re
import logging
from typing import Dict, List, Optional, Any
import requests
from datetime import datetime
import database

logger = logging.getLogger(__name__)

class CharacterParser:
    """Парсер персонажей для генерации изображений"""

    def __init__(self):
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def parse_character_references(self, character_name: str, max_refs: int = 3) -> Dict[str, Any]:
        """Парсинг референсов персонажа через Google Images"""
        try:
            logger.info(f"Парсинг референсов для персонажа: {character_name}")

            # Получаем API ключи из переменных окружения
            google_api_key = os.getenv('GOOGLE_API_KEY')
            search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

            if not google_api_key or not search_engine_id:
                logger.error("Google API ключи не найдены в переменных окружения")
                return {
                    'ref_images': [],
                    'success': False,
                    'message': 'Google API ключи не настроены'
                }

            # Формируем поисковый запрос для персонажа
            query = f"{character_name} character official artwork high quality"
            logger.info(f"Поисковый запрос: {query}")

            # Параметры для Google Custom Search API
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': google_api_key,
                'cx': search_engine_id,
                'q': query,
                'searchType': 'image',
                'num': max_refs,
                'imgSize': 'large',
                'imgType': 'photo',
                'safe': 'active'
            }

            # Делаем запрос к Google Custom Search API
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ошибка Google API: {response.status} - {error_text}")
                    return {
                        'ref_images': [],
                        'success': False,
                        'message': f'Ошибка Google API: {response.status}'
                    }

                data = await response.json()

                # Извлекаем URLs изображений
                ref_images = []
                if 'items' in data:
                    for item in data['items'][:max_refs]:
                        if 'link' in item:
                            ref_images.append(item['link'])
                            logger.info(f"Найден референс: {item['link']}")

                if ref_images:
                    logger.info(f"Найдено {len(ref_images)} референсов для {character_name}")
                    return {
                        'ref_images': ref_images,
                        'success': True,
                        'message': f'Найдено {len(ref_images)} референсов'
                    }
                else:
                    logger.warning(f"Не найдено референсов для {character_name}")
                    return {
                        'ref_images': [],
                        'success': False,
                        'message': 'Референсы не найдены'
                    }

        except Exception as e:
            logger.error(f"Ошибка парсинга референсов: {e}")
            return {
                'ref_images': [],
                'success': False,
                'message': f'Ошибка: {str(e)}'
            }

    async def generate_character_prompt(self, character_desc: str, ref_images: List[str] = None) -> str:
        """Генерация промпта для персонажа"""
        try:
            # Простая генерация промпта на основе описания
            prompt = f"{character_desc}, realistic photo, detailed face, high quality, professional photography"

            # Добавляем информацию о столе
            prompt += ", sitting at restaurant table, cozy restaurant interior, warm lighting"

            # Добавляем дополнительные стили
            admin_prompt = database.get_setting('character_system_prompt', '')
            if admin_prompt:
                prompt += f", {admin_prompt}"

            return prompt

        except Exception as e:
            logger.error(f"Ошибка генерации промпта: {e}")
            return f"{character_desc}, realistic photo"

    async def save_ai_result(self, character_name: str, user_id: int, ai_result: str, prompt: str) -> str:
        """Сохранение результата генерации AI"""
        try:
            # Создаем директорию для фото персонажей
            photos_dir = f"photos/{character_name.lower().replace(' ', '_')}"
            os.makedirs(photos_dir, exist_ok=True)

            # Сохраняем информацию о генерации
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{character_name}_{timestamp}.txt"
            filepath = os.path.join(photos_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Персонаж: {character_name}\n")
                f.write(f"Пользователь: {user_id}\n")
                f.write(f"Время: {datetime.now()}\n")
                f.write(f"Промпт: {prompt}\n")
                f.write(f"Результат: {ai_result}\n")

            logger.info(f"Результат сохранен: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Ошибка сохранения результата: {e}")
            return ""

# Глобальный экземпляр парсера
character_parser = CharacterParser()

async def ensure_character_references(character_name: str, max_refs: int = 3) -> List[str]:
    """Обеспечение наличия референсов персонажа"""
    try:
        async with character_parser as parser:
            result = await parser.parse_character_references(character_name, max_refs)

            if result['success'] and result['ref_images']:
                # Сохраняем референсы локально
                refs_dir = f"photos/{character_name.lower().replace(' ', '_')}_refs"
                os.makedirs(refs_dir, exist_ok=True)

                saved_refs = []
                for i, img_url in enumerate(result['ref_images'][:max_refs]):
                    try:
                        # Скачиваем изображение
                        async with aiohttp.ClientSession() as session:
                            async with session.get(img_url) as response:
                                if response.status == 200:
                                    img_data = await response.read()
                                    ext = 'jpg'  # По умолчанию
                                    if 'png' in response.headers.get('content-type', ''):
                                        ext = 'png'

                                    filename = f"ref_{i+1}.{ext}"
                                    filepath = os.path.join(refs_dir, filename)

                                    with open(filepath, 'wb') as f:
                                        f.write(img_data)

                                    saved_refs.append(filepath)
                                    logger.info(f"Референс сохранен: {filepath}")
                    except Exception as e:
                        logger.error(f"Ошибка скачивания референса {img_url}: {e}")
                        continue

                return saved_refs
            else:
                logger.warning(f"Не удалось получить референсы для {character_name}: {result.get('message', 'Неизвестная ошибка')}")
                return []

    except Exception as e:
        logger.error(f"Ошибка в ensure_character_references: {e}")
        return []

def get_character_reference_images(character_name: str, max_refs: int = 3) -> List[str]:
    """Получение путей к референсным изображениям персонажа"""
    try:
        refs_dir = f"photos/{character_name.lower().replace(' ', '_')}_refs"

        if not os.path.exists(refs_dir):
            return []

        # Получаем все файлы изображений
        image_files = []
        for file in os.listdir(refs_dir):
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                image_files.append(os.path.join(refs_dir, file))

        # Сортируем по имени и возвращаем нужное количество
        image_files.sort()
        return image_files[:max_refs]

    except Exception as e:
        logger.error(f"Ошибка получения референсов: {e}")
        return []

async def save_character_result(character_name: str, user_id: int, prompt: str, image_url: str, ref_paths: List[str] = None, dish_name: str = None) -> bool:
    """Сохранение результата генерации персонажа"""
    try:
        async with character_parser as parser:
            result_path = await parser.save_ai_result(character_name, user_id, image_url, prompt)

            if result_path:
                # Сохраняем в базу данных
                database.save_character_generation(user_id, character_name, dish_name, prompt, image_url, ref_paths or [])
                logger.info(f"Генерация персонажа сохранена в БД: {character_name} (блюдо: {dish_name})")
                return True
            else:
                logger.error("Не удалось сохранить результат генерации")
                return False

    except Exception as e:
        logger.error(f"Ошибка сохранения генерации персонажа: {e}")
        return False

# Для обратной совместимости
def generate_character_prompt(character_desc: str, ref_images: List[str] = None) -> str:
    """Синхронная версия генерации промпта"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Если цикл уже запущен, создаем задачу
            return loop.run_until_complete(character_parser.generate_character_prompt(character_desc, ref_images))
        else:
            # Иначе запускаем в текущем цикле
            return asyncio.run(character_parser.generate_character_prompt(character_desc, ref_images))
    except Exception as e:
        logger.error(f"Ошибка в синхронной генерации промпта: {e}")
        return f"{character_desc}, realistic photo"

def save_ai_result(character_name: str, user_id: int, ai_result: str, prompt: str) -> str:
    """Синхронная версия сохранения результата"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Создаем задачу для асинхронного выполнения
            task = loop.create_task(character_parser.save_ai_result(character_name, user_id, ai_result, prompt))
            # Ждем завершения (это может заблокировать, но необходимо для совместимости)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, task)
                return future.result()
        else:
            return asyncio.run(character_parser.save_ai_result(character_name, user_id, ai_result, prompt))
    except Exception as e:
        logger.error(f"Ошибка в синхронном сохранении результата: {e}")
        return ""

print("✅ Character Parser загружен!")
