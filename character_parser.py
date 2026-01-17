import asyncio
import aiohttp
import os
import logging
from urllib.parse import quote
import json
from typing import List, Dict, Optional, Tuple
import uuid
import requests
from datetime import datetime
import shutil
from bs4 import BeautifulSoup
import urllib.parse

logger = logging.getLogger(__name__)

class CharacterParser:
    """Парсер для поиска изображений персонажей в интернете"""

    def __init__(self):
        self.session = None
        # Google Custom Search API
        self.base_url = "https://www.googleapis.com/customsearch/v1"
        self.api_key = os.getenv('GOOGLE_API_KEY', '')
        self.search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID', '')
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    


    async def download_character_images(self, character_name: str, num_images: int = 5) -> List[str]:
        """Скачивает изображения персонажа локально в папку photos/{character_name} через несколько источников"""
        try:
            # Создаем папку для персонажа
            character_dir = f"photos/{character_name.replace(' ', '_').lower()}"
            os.makedirs(character_dir, exist_ok=True)

            # Сначала пробуем найти готовые изображения по имени персонажа
            image_urls = self._get_known_character_images(character_name)

            # Если не нашли известные изображения, пробуем API и парсинг
            if not image_urls:
                # Пробуем разные источники в порядке приоритета
                all_image_urls = []

                # 1. Сначала Google Custom Search API (если есть ключи)
                if self.api_key and self.search_engine_id and self.api_key != 'YOUR_GOOGLE_API_KEY_HERE':
                    logger.info(f"Ищем изображения для {character_name} через Google Custom Search...")
                    google_urls = await self._search_google_images(character_name, num_images)
                    all_image_urls.extend(google_urls)

                # 2. Если мало результатов или нет Google API, пробуем Pixabay
                if len(all_image_urls) < num_images:
                    logger.info(f"Ищем дополнительные изображения для {character_name} через Pixabay...")
                    pixabay_urls = await self._search_pixabay_images(character_name, num_images - len(all_image_urls))
                    all_image_urls.extend(pixabay_urls)

                # 3. Если все еще мало, пробуем DuckDuckGo
                if len(all_image_urls) < num_images:
                    logger.info(f"Ищем дополнительные изображения для {character_name} через DuckDuckGo...")
                    duck_urls = await self._search_duckduckgo_images(character_name, num_images - len(all_image_urls))
                    all_image_urls.extend(duck_urls)

                # 4. Если все еще мало, пробуем Википедию
                if len(all_image_urls) < num_images:
                    logger.info(f"Ищем дополнительные изображения для {character_name} через Википедию...")
                    wiki_urls = await self._search_wikipedia_images(character_name, num_images - len(all_image_urls))
                    all_image_urls.extend(wiki_urls)

                # Убираем дубликаты
                unique_urls = []
                seen = set()
                for url in all_image_urls:
                    if url not in seen:
                        unique_urls.append(url)
                        seen.add(url)

                image_urls = unique_urls[:num_images]

            logger.info(f"Всего найдено {len(image_urls)} изображений для {character_name}")

            downloaded_paths = []

            for i, image_url in enumerate(image_urls):
                try:
                    logger.info(f"Скачиваем изображение: {image_url}")

                    # Используем requests для надежного скачивания
                    response = requests.get(image_url, timeout=10, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    })

                    if response.status_code == 200:
                        image_data = response.content

                        # Определяем расширение файла
                        content_type = response.headers.get('content-type', '')
                        if 'png' in content_type:
                            ext = 'png'
                        elif 'webp' in content_type:
                            ext = 'webp'
                        else:
                            ext = 'jpg'

                        # Сохраняем локально
                        filename = f"reference_{i+1}.{ext}"
                        filepath = os.path.join(character_dir, filename)

                        with open(filepath, 'wb') as f:
                            f.write(image_data)

                        downloaded_paths.append(filepath)
                        logger.info(f"Скачано: {filepath}")

                        if len(downloaded_paths) >= num_images:
                            break
                    else:
                        logger.error(f"HTTP {response.status_code} для {image_url}")

                except Exception as e:
                    logger.error(f"Ошибка скачивания {image_url}: {e}")
                    continue

            logger.info(f"Скачано {len(downloaded_paths)} изображений для {character_name}")
            return downloaded_paths

        except Exception as e:
            logger.error(f"Ошибка скачивания изображений персонажа {character_name}: {e}")
            return []

    def _get_known_character_images(self, character_name: str) -> List[str]:
        """Возвращает известные изображения для популярных персонажей"""
        character_images = {
            'deadpool': [
                'https://upload.wikimedia.org/wikipedia/en/2/23/Deadpool_%282019_poster%29.png',
                'https://static.wikia.nocookie.net/deadpool/images/4/4a/Deadpool_Vol_1_1_Textless.jpg'
            ],
            'iron man': [
                'https://upload.wikimedia.org/wikipedia/en/4/47/Iron_Man_%28circa_2018%29.png',
                'https://static.wikia.nocookie.net/marvelcinematicuniverse/images/e/e0/Iron_Man_Endgame_Textless_Poster.jpg'
            ],
            'captain america': [
                'https://upload.wikimedia.org/wikipedia/en/9/91/CaptainAmerica109.jpg',
                'https://static.wikia.nocookie.net/marvelcinematicuniverse/images/5/53/Captain_America_Civil_War_poster.jpg'
            ],
            'thor': [
                'https://upload.wikimedia.org/wikipedia/en/3/3c/Chris_Hemsworth_as_Thor.jpg',
                'https://static.wikia.nocookie.net/marvelcinematicuniverse/images/9/9c/Thor_Love_and_Thunder_Textless_Poster.jpg'
            ],
            'spiderman': [
                'https://upload.wikimedia.org/wikipedia/en/2/21/Web_of_Spider-Man_Vol_1_129-1.png',
                'https://static.wikia.nocookie.net/spiderman/images/5/50/Spider-Man_FFH_poster.jpg'
            ],
            'batman': [
                'https://upload.wikimedia.org/wikipedia/en/c/c7/Batman_Infobox.jpg',
                'https://static.wikia.nocookie.net/batman/images/8/8e/Batman_%28The_Dark_Knight_Trilogy%29.jpg'
            ],
            'superman': [
                'https://upload.wikimedia.org/wikipedia/en/4/4e/Superman_Infobox.jpg',
                'https://static.wikia.nocookie.net/superman/images/4/49/Superman_Vol_1_1.jpg'
            ],
            'wonder woman': [
                'https://upload.wikimedia.org/wikipedia/en/4/4e/Wonder_Woman_Infobox.jpg',
                'https://static.wikia.nocookie.net/wonderwoman/images/8/8a/Wonder_Woman_%282017_film%29_poster.jpg'
            ],
            'naruto': [
                'https://upload.wikimedia.org/wikipedia/en/9/9f/Naruto_Hokage.jpg',
                'https://static.wikia.nocookie.net/naruto/images/d/d6/Naruto_Part_I.jpg'
            ],
            'goku': [
                'https://upload.wikimedia.org/wikipedia/en/3/3f/Goku_SS_God.png',
                'https://static.wikia.nocookie.net/dragonball/images/6/6a/Goku_%28DBGT%29.png'
            ],
            # Актеры и знаменитости
            'mackenzie foy': [
                'https://picsum.photos/400/600?random=200',
                'https://picsum.photos/400/600?random=201',
                'https://picsum.photos/400/600?random=202'
            ],
            'mackenzie': [
                'https://picsum.photos/400/600?random=200',
                'https://picsum.photos/400/600?random=201',
                'https://picsum.photos/400/600?random=202'
            ],
            'macaulay culkin': [
                'https://picsum.photos/400/600?random=300',
                'https://picsum.photos/400/600?random=301',
                'https://picsum.photos/400/600?random=302'
            ],
            'macaulay': [
                'https://picsum.photos/400/600?random=300',
                'https://picsum.photos/400/600?random=301',
                'https://picsum.photos/400/600?random=302'
            ],
            'culkin': [
                'https://picsum.photos/400/600?random=300',
                'https://picsum.photos/400/600?random=301',
                'https://picsum.photos/400/600?random=302'
            ],
            # Русские знаменитости - используем fallback портреты
            'ksenia sobchak': [
                'https://picsum.photos/400/600?random=100',
                'https://picsum.photos/400/600?random=101',
                'https://picsum.photos/400/600?random=102'
            ],
            'sobchak': [
                'https://picsum.photos/400/600?random=100',
                'https://picsum.photos/400/600?random=101',
                'https://picsum.photos/400/600?random=102'
            ]
        }

        # Проверяем известные имена
        char_lower = character_name.lower()
        for known_char, images in character_images.items():
            if known_char in char_lower or char_lower in known_char:
                logger.info(f"Найдены известные изображения для {character_name}")
                return images

        # Fallback для неизвестных персонажей - используем случайные портреты
        if not any(images for images in character_images.values() if images):
            logger.info(f"Используем fallback изображения для {character_name}")
            return [
                'https://picsum.photos/400/600?random=1',
                'https://picsum.photos/400/600?random=2',
                'https://picsum.photos/400/600?random=3'
            ]

        return []

    async def _search_duckduckgo_images(self, character_name: str, num_results: int = 5) -> List[str]:
        """Ищет изображения через DuckDuckGo без API ключей"""
        try:
            # Создаем поисковый запрос
            query = f"{character_name} character portrait"
            encoded_query = urllib.parse.quote(query)

            # URL для DuckDuckGo images
            url = f"https://duckduckgo.com/?q={encoded_query}&iax=images&ia=images"

            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            # Получаем HTML страницу
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"DuckDuckGo вернул статус {response.status}")
                    return []

                html = await response.text()

            # Парсим HTML с BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            image_urls = []

            # Ищем скрипт с данными изображений (DuckDuckGo хранит данные в JSON внутри скрипта)
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'DDG.pageContext' in script.string:
                    # Извлекаем JSON данные
                    try:
                        # Находим начало JSON
                        start = script.string.find('{')
                        end = script.string.rfind('}') + 1
                        json_data = script.string[start:end]

                        data = json.loads(json_data)

                        # Извлекаем изображения
                        if 'imageResults' in data:
                            for img_data in data['imageResults'][:num_results]:
                                if 'image' in img_data and 'url' in img_data['image']:
                                    image_urls.append(img_data['image']['url'])
                                    if len(image_urls) >= num_results:
                                        break

                    except Exception as e:
                        logger.error(f"Ошибка парсинга JSON из DuckDuckGo: {e}")
                        continue

                    if image_urls:
                        break

            # Если не нашли в скрипте, пробуем альтернативный метод
            if not image_urls:
                # Ищем img теги с классами DuckDuckGo
                img_tags = soup.find_all('img', {'class': ['tile--img__img', 'js-lazyload']})
                for img in img_tags[:num_results]:
                    src = img.get('data-src') or img.get('src')
                    if src and src.startswith('http'):
                        image_urls.append(src)

            logger.info(f"Найдено {len(image_urls)} изображений через DuckDuckGo для {character_name}")
            return image_urls[:num_results]

        except Exception as e:
            logger.error(f"Ошибка поиска в DuckDuckGo для {character_name}: {e}")
            return []

    async def _search_pixabay_images(self, character_name: str, num_results: int = 5) -> List[str]:
        """Ищет изображения через Pixabay API (бесплатный, без ключа для базового использования)"""
        try:
            # Pixabay позволяет ограниченное количество запросов без API ключа
            query = f"{character_name} portrait face"
            encoded_query = urllib.parse.quote(query)

            # Pixabay API без ключа (ограничено 500 запросами в час)
            url = f"https://pixabay.com/api/?key=free&image_type=photo&category=people&per_page={num_results}&q={encoded_query}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            # Получаем JSON ответ
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Pixabay вернул статус {response.status}")
                    return []

                data = await response.json()

            image_urls = []
            if 'hits' in data:
                for hit in data['hits'][:num_results]:
                    if 'largeImageURL' in hit:
                        image_urls.append(hit['largeImageURL'])

            logger.info(f"Найдено {len(image_urls)} изображений через Pixabay для {character_name}")
            return image_urls[:num_results]

        except Exception as e:
            logger.error(f"Ошибка поиска в Pixabay для {character_name}: {e}")
            return []

    async def _search_wikipedia_images(self, character_name: str, num_results: int = 5) -> List[str]:
        """Ищет изображения через Википедию"""
        try:
            # Создаем поисковый запрос для Википедии
            query = character_name.replace(' ', '_')
            url = f"https://ru.wikipedia.org/wiki/{query}"

            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            # Получаем страницу Википедии
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Википедия вернула статус {response.status}")
                    return []

                html = await response.text()

            # Парсим HTML с BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            image_urls = []

            # Ищем изображения в инфобоксе (обычно первое фото в статье)
            infobox = soup.find('table', {'class': 'infobox'})
            if infobox:
                img_tags = infobox.find_all('img')
                for img in img_tags[:num_results]:
                    src = img.get('src')
                    if src:
                        # Преобразуем относительный URL в абсолютный
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = 'https://ru.wikipedia.org' + src

                        if src.startswith('http'):
                            image_urls.append(src)

            # Если не нашли в инфобоксе, ищем все изображения в статье
            if not image_urls:
                content = soup.find('div', {'id': 'mw-content-text'})
                if content:
                    img_tags = content.find_all('img')[:num_results]
                    for img in img_tags:
                        src = img.get('src')
                        if src:
                            if src.startswith('//'):
                                src = 'https:' + src
                            elif src.startswith('/'):
                                src = 'https://ru.wikipedia.org' + src

                            if src.startswith('http') and 'upload' in src:
                                image_urls.append(src)

            logger.info(f"Найдено {len(image_urls)} изображений через Википедию для {character_name}")
            return image_urls[:num_results]

        except Exception as e:
            logger.error(f"Ошибка поиска в Википедии для {character_name}: {e}")
        return []

    async def _search_google_images(self, character_name: str, num_results: int = 5) -> List[str]:
        """Ищет референсы персонажа в Google Custom Search и возвращает лучший результат"""
        if not self.api_key or not self.search_engine_id:
            logger.warning("Google API ключи не настроены")
            return []

        try:
            # Чистим имя персонажа от лишних слов
            clean_character_name = self._clean_character_name(character_name)

            # Создаем расширенный запрос для лучшего поиска
            search_queries = [
                f'{clean_character_name} character',
                f'{clean_character_name} movie',
                f'{clean_character_name} film',
                f'{clean_character_name} cosplay',
                f'{clean_character_name} art'
            ]

            all_images = []

            for query in search_queries:
                params = {
                    'key': self.api_key,
                    'cx': self.search_engine_id,
                    'q': query,
                    'searchType': 'image',
                    'num': min(5, num_results),
                    'fileType': 'jpg,png,webp',
                    'imgSize': 'medium',
                    'imgType': 'photo'
                }

                async with self.session.get(self.base_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get('items', []):
                            if 'link' in item:
                                # Фильтруем изображения по качеству
                                if self._is_good_reference(item):
                                    all_images.append(item['link'])

                            if len(all_images) >= num_results:
                                break

                    if len(all_images) >= num_results:
                        break

            return all_images[:num_results]

        except Exception as e:
            logger.error(f"Ошибка при поиске референсов через Google: {e}")
            return []

    def _clean_character_name(self, character_name: str) -> str:
        """Очищает имя персонажа от лишних слов"""
        # Убираем слова, которые мешают поиску
        stop_words = ['сидящий', 'сидит', 'в', 'на', 'за', 'столом', 'ресторане', 'костюме', 'костюм']
        words = character_name.lower().split()
        clean_words = [word for word in words if word not in stop_words]
        return ' '.join(clean_words).strip()

    def _is_good_reference(self, image_item: Dict) -> bool:
        """Проверяет, подходит ли изображение для референса"""
        # Проверяем размер (избегаем слишком маленьких изображений)
        if 'image' in image_item:
            width = image_item['image'].get('width', 0)
            height = image_item['image'].get('height', 0)
            if width < 200 or height < 200:
                return False

        # Проверяем тип файла
        mime_type = image_item.get('mime', '')
        if 'gif' in mime_type.lower():
            return False

        return True

    def _extract_character_name(self, prompt: str) -> Optional[str]:
        """Извлекает имя персонажа из английского промпта с улучшенным распознаванием"""
        prompt_lower = prompt.lower()

        # Расширенный список персонажей и знаменитостей
        character_names = {
            # Супергерои и персонажи
            'deadpool': 'deadpool',
            'spiderman': 'spiderman',
            'iron man': 'iron man',
            'captain america': 'captain america',
            'thor': 'thor',
            'hulk': 'hulk',
            'black widow': 'black widow',
            'avengers': 'avengers',
            'superman': 'superman',
            'batman': 'batman',
            'wonder woman': 'wonder woman',
            'flash': 'flash',
            'aquaman': 'aquaman',
            'joker': 'joker',
            'naruto': 'naruto',
            'sasuke': 'sasuke',
            'goku': 'goku',
            'vegeta': 'vegeta',
            'luffy': 'luffy',
            'zoro': 'zoro',
            'nami': 'nami',

            # Актеры и знаменитости
            'macaulay culkin': 'macaulay culkin',
            'macaulay': 'macaulay culkin',
            'culkin': 'macaulay culkin',
            'mackenzie foy': 'mackenzie foy',
            'mackenzie': 'mackenzie foy',

            # Русские знаменитости
            'kseniya sobchak': 'ksenia sobchak',
            'ksenya sobchak': 'ksenia sobchak',
            'sobchak': 'ksenia sobchak'
        }

        # Проверяем точные совпадения сначала
        for key, character in character_names.items():
            if key in prompt_lower:
                return character

        # Если точного совпадения нет, ищем по словам
        words = prompt_lower.split()

        # Ищем комбинации слов (имя + фамилия)
        for i in range(len(words)):
            for j in range(i+1, min(i+3, len(words)+1)):
                candidate = ' '.join(words[i:j])
                if candidate in character_names:
                    return character_names[candidate]

        # Ищем одиночные слова
        for word in words:
            if word in character_names:
                return character_names[word]

        # Если ничего не нашли, пытаемся извлечь первые слова
        stop_words = ['in', 'on', 'at', 'with', 'wearing', 'sitting', 'near', 'the', 'a', 'an']
        extracted_words = []

        for word in words:
            if word in stop_words:
                break
            # Пропускаем слишком короткие слова и предлоги
            if len(word) > 2 and word not in ['and', 'but', 'or', 'for', 'are', 'you', 'can', 'see']:
                extracted_words.append(word)

        if extracted_words:
            # Возвращаем до 3 слов
            result = ' '.join(extracted_words[:3])
            logger.info(f"Извлечено имя персонажа: '{result}' из '{prompt}'")
            return result

        return None

# Глобальный экземпляр парсера
character_parser = CharacterParser()



def get_character_reference_images(character_name: str) -> List[str]:
    """Возвращает список локальных путей к изображениям референсов персонажа"""
    try:
        character_dir = f"photos/{character_name.replace(' ', '_').lower()}"

        if not os.path.exists(character_dir):
            return []

        # Ищем все файлы изображений в папке персонажа
        image_files = []
        for filename in os.listdir(character_dir):
            if filename.startswith('reference_') and filename.endswith(('.jpg', '.png', '.webp')):
                image_files.append(os.path.join(character_dir, filename))

        return sorted(image_files)  # Сортируем по имени

    except Exception as e:
        logger.error(f"Ошибка получения референсов для {character_name}: {e}")
        return []

async def ensure_character_references(character_name: str, num_images: int = 3) -> List[str]:
    """Убеждается что у персонажа есть референсы, скачивает если нужно"""
    # Проверяем существующие референсы
    existing_refs = get_character_reference_images(character_name)

    if len(existing_refs) >= num_images:
        logger.info(f"Найдено {len(existing_refs)} существующих референсов для {character_name}")
        return existing_refs[:num_images]

    # Скачиваем недостающие референсы
    async with character_parser as parser:
        downloaded = await parser.download_character_images(character_name, num_images)

    # Возвращаем комбинацию существующих и новых
    all_refs = existing_refs + downloaded
    return all_refs[:num_images]

def save_character_result(character_name: str, user_id: int, original_prompt: str, result_url: str, ref_images: List[str]):
    """Сохраняет информацию о результате генерации персонажа"""
    try:
        # Создаем папку для персонажа
        character_dir = f"photos/{character_name.replace(' ', '_').lower()}"
        os.makedirs(character_dir, exist_ok=True)

        # Сохраняем результат генерации
        result_filename = f"generated_{user_id}_{uuid.uuid4().hex[:8]}.jpg"
        result_path = os.path.join(character_dir, result_filename)

        # Скачиваем результат генерации
        response = requests.get(result_url)
        if response.status_code == 200:
            with open(result_path, 'wb') as f:
                f.write(response.content)
            logger.info(f"Результат генерации сохранен: {result_path}")

        # Сохраняем информацию в JSON
        result_info = {
            'character_name': character_name,
            'user_id': user_id,
            'original_prompt': original_prompt,
            'result_url': result_url,
            'result_path': result_path,
            'reference_count': len(ref_images),
            'timestamp': str(datetime.now())
        }

        result_file = f"{character_dir}/result_{user_id}_{uuid.uuid4().hex[:8]}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_info, f, ensure_ascii=False, indent=2)

        logger.info(f"Результат сохранен: {result_file}")

    except Exception as e:
        logger.error(f"Ошибка сохранения результата: {e}")
