"""
selenium_parser.py
Отдельный процесс для парсинга отзывов с Selenium
"""

import time
import re
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def parse_reviews():
    """Основная функция парсинга"""
    reviews = []
    
    try:
        # Настройка Chrome
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        try:
            # Открываем страницу
            url = "https://yandex.ru/maps/org/mashkov/202266309008/reviews/"
            driver.get(url)
            time.sleep(5)
            
            # Прокручиваем страницу
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.8);")
                time.sleep(2)
            
            time.sleep(3)
            
            # Ищем отзывы
            review_elements = driver.find_elements(By.CLASS_NAME, 'business-review-view__body')
            
            for element in review_elements[:10]:
                try:
                    # Автор
                    author = "Гость"
                    try:
                        author_elem = element.find_element(By.CLASS_NAME, 'business-review-view__author')
                        author = author_elem.text.strip()
                    except:
                        pass
                    
                    # Рейтинг
                    rating = 5
                    try:
                        rating_elem = element.find_element(By.CLASS_NAME, 'business-rating-badge-view__stars')
                        stars = rating_elem.find_elements(By.CSS_SELECTOR, '[class*="_full"]')
                        if stars:
                            rating = len(stars)
                    except:
                        pass
                    
                    # Дата
                    date = datetime.now().strftime("%d.%m.%Y")
                    try:
                        date_elem = element.find_element(By.CLASS_NAME, 'business-review-view__date')
                        date_text = date_elem.text.strip()
                        if date_text:
                            date = date_text
                    except:
                        pass
                    
                    # Текст
                    text = ""
                    try:
                        text_container = element.find_element(By.CLASS_NAME, 'business-review-view__body-text')
                        
                        # Проверяем спойлер
                        try:
                            spoiler_container = text_container.find_element(By.CLASS_NAME, 'spoiler-view__text-container')
                            
                            # Пробуем раскрыть спойлер
                            try:
                                spoiler_button = text_container.find_element(By.CLASS_NAME, 'spoiler-view__toggle')
                                driver.execute_script("arguments[0].click();", spoiler_button)
                                time.sleep(1)
                            except:
                                pass
                            
                            text = spoiler_container.text.strip()
                        except:
                            text = text_container.text.strip()
                            
                    except:
                        # Альтернативный способ
                        try:
                            all_text = element.text
                            lines = all_text.split('\n')
                            for line in lines:
                                if len(line) > 50 and not any(phrase in line.lower() for phrase in ['оцените', 'еда', 'положительный']):
                                    text = line.strip()
                                    break
                        except:
                            pass
                    
                    # Очистка текста
                    if text:
                        # Убираем мусор
                        text = re.sub(r'Оцените это место\.\.\.', '', text)
                        text = re.sub(r'Еда.*\d+%.*положительный', '', text)
                        text = re.sub(r'Знаток города.*\d+ уровня', '', text)
                        text = re.sub(r'Подписаться', '', text)
                        text = re.sub(r'Показать полностью|Читать дальше|Скрыть', '', text)
                        text = text.strip()
                        
                        # Проверяем что это реальный отзыв
                        if len(text) > 50 and not any(phrase in text.lower() for phrase in ['оцените', 'еда', 'положительный']):
                            # Очищаем автора
                            clean_author = re.sub(r'Знаток города.*\d+ уровня', '', author)
                            clean_author = re.sub(r'Подписаться', '', clean_author)
                            clean_author = clean_author.strip()
                            if not clean_author:
                                clean_author = "Гость"
                            
                            reviews.append({
                                'author': clean_author[:50],
                                'rating': rating,
                                'text': text[:800],
                                'date': date[:20]
                            })
                            
                except Exception as e:
                    continue
                    
        finally:
            driver.quit()
            
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
    
    return reviews

if __name__ == "__main__":
    # Запускаем парсинг и выводим результат как JSON
    result = parse_reviews()
    print(json.dumps(result, ensure_ascii=False))