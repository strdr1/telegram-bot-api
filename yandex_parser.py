"""
yandex_parser.py
Парсер отзывов с Яндекс.Карт
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import logging
import database as db

logger = logging.getLogger(__name__)

class YandexReviewsParser:
    def __init__(self):
        self.base_url = "https://yandex.ru/maps/org/mashkov/202266309008/reviews/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    async def parse_reviews(self):
        """Парсить отзывы с Яндекс.Карт"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, headers=self.headers) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка при получении страницы: {response.status}")
                        return False
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Ищем отзывы (это примерный селектор, может потребоваться настройка)
                    reviews = soup.find_all('div', class_='business-review-view__body')
                    
                    # Если не нашли по этому классу, пробуем другие
                    if not reviews:
                        reviews = soup.find_all('div', {'class': lambda x: x and 'review' in x.lower()})
                    
                    parsed_count = 0
                    for review in reviews[:10]:  # Берем первые 10 отзывов
                        try:
                            # Имя автора
                            author_elem = review.find('span', class_='business-review-view__author')
                            if not author_elem:
                                author_elem = review.find('div', {'class': lambda x: x and 'author' in x.lower()})
                            
                            author_name = author_elem.text.strip() if author_elem else "Аноним"
                            
                            # Рейтинг
                            rating_elem = review.find('span', class_='business-rating-badge-view__stars')
                            if not rating_elem:
                                rating_elem = review.find('div', {'class': lambda x: x and 'rating' in x.lower() or 'star' in x.lower()})
                            
                            rating = 5  # По умолчанию
                            if rating_elem:
                                # Пробуем извлечь рейтинг из разных мест
                                rating_text = rating_elem.text.strip()
                                if rating_text:
                                    try:
                                        rating = int(rating_text[0])
                                    except:
                                        pass
                            
                            # Текст отзыва
                            text_elem = review.find('span', class_='business-review-view__body-text')
                            if not text_elem:
                                text_elem = review.find('div', {'class': lambda x: x and 'text' in x.lower()})
                            
                            review_text = text_elem.text.strip() if text_elem else ""
                            
                            # Дата
                            date_elem = review.find('span', class_='business-review-view__date')
                            if not date_elem:
                                date_elem = review.find('div', {'class': lambda x: x and 'date' in x.lower()})
                            
                            date = date_elem.text.strip() if date_elem else ""
                            
                            if review_text:  # Сохраняем только если есть текст
                                db.save_yandex_review(author_name, rating, review_text, date)
                                parsed_count += 1
                                
                        except Exception as e:
                            logger.error(f"Ошибка при парсинге отзыва: {e}")
                            continue
                    
                    logger.info(f"Спаршено {parsed_count} отзывов")
                    return parsed_count > 0
                    
        except Exception as e:
            logger.error(f"Ошибка при парсинге: {e}")
            return False
    
    def get_parsed_reviews(self, limit=10):
        """Получить спарсенные отзывы"""
        return db.get_yandex_reviews(limit)

# Глобальный экземпляр парсера
parser = YandexReviewsParser()

async def update_reviews():
    """Задача для периодического обновления отзывов"""
    logger.info("Начинаю парсинг отзывов...")
    success = await parser.parse_reviews()
    if success:
        logger.info("Парсинг отзывов завершен успешно")
    else:
        logger.warning("Парсинг отзывов не удался")
    return success