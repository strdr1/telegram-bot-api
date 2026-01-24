"""
services.py
Сервисы: парсинг отзывов с Яндекс Карт (только для админки)
"""

import database
import config
from datetime import datetime
import asyncio
import logging
import re
logger = logging.getLogger(__name__)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return get_quality_fallback_reviews_sync()

def _run_selenium_sync():
    """Синхронная функция для парсинга отзывов с Яндекс Карт"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager
        import time
        import re
        
        # Настройка Chrome
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.page_load_strategy = 'eager'
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Используем webdriver-manager с правильной версией для Windows
        import platform
        import os

        system = platform.system().lower()

        if system == "windows":
            # Для Windows исправляем путь webdriver-manager
            try:
                chrome_driver_manager = ChromeDriverManager()
                reported_path = chrome_driver_manager.install()

                # webdriver-manager возвращает путь к THIRD_PARTY_NOTICES.chromedriver,
                # но нам нужен chromedriver.exe в той же директории
                driver_dir = os.path.dirname(reported_path)
                actual_driver_path = os.path.join(driver_dir, 'chromedriver.exe')

                if os.path.exists(actual_driver_path):
                    driver_path = actual_driver_path
                    logger.info(f"Используем исправленный путь: {driver_path}")
                else:
                    # Если не нашли, используем reported_path (на всякий случай)
                    driver_path = reported_path
                    logger.warning(f"Не найден chromedriver.exe, используем: {driver_path}")

                service = Service(driver_path)
            except Exception as e:
                logger.warning(f"Ошибка с webdriver-manager: {e}, пробуем альтернативный метод")
                # Альтернативный метод - поиск существующего chromedriver
                possible_paths = [
                    'chromedriver.exe',
                    'C:\\Windows\\chromedriver.exe',
                    os.path.join(os.getcwd(), 'chromedriver.exe'),
                    os.path.join(os.path.dirname(__file__), 'chromedriver.exe')
                ]

                driver_path = None
                for path in possible_paths:
                    if os.path.exists(path):
                        driver_path = path
                        break

                if driver_path:
                    service = Service(driver_path)
                    logger.info(f"Найден chromedriver по пути: {driver_path}")
                else:
                    raise Exception("Не удалось найти chromedriver")
        else:
            # Для других ОС используем стандартный менеджер
            chrome_driver_manager = ChromeDriverManager()
            service = Service(chrome_driver_manager.install())
        
        driver = None
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(20)
            
            start_time = time.time()
            
            # ШАГ 1: Открываем страницу с параметрами сортировки по новизне
            base_url = config.YANDEX_REVIEWS_URL.rstrip('/')
            sorted_url = f"{base_url}?l=review&sort=date"
            
            logger.info(f"Открываем страницу с сортировкой по новизне: {sorted_url}")
            
            try:
                driver.get(sorted_url)
                time.sleep(3)
            except Exception as e:
                logger.warning(f"Ошибка загрузки страницы с сортировкой: {e}")
                # Пробуем оригинальный URL
                driver.get(config.YANDEX_REVIEWS_URL)
                time.sleep(3)
            
            # ШАГ 2: Проверяем, что отзывы загрузились
            try:
                reviews_check = driver.find_elements(By.CSS_SELECTOR, 'div.business-review-view')
                logger.info(f"Найдено отзывов на странице: {len(reviews_check)}")
                
                if len(reviews_check) == 0:
                    logger.warning("Отзывы не найдены, используем fallback")
                    return get_quality_fallback_reviews_sync()
                    
            except:
                logger.warning("Не удалось проверить отзывы, используем fallback")
                return get_quality_fallback_reviews_sync()
            
            # ШАГ 3: Прокручиваем для загрузки всех отзывов
            logger.info("Прокрутка для загрузки отзывов...")
            
            # Плавная прокрутка
            scroll_steps = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]
            for step in scroll_steps:
                driver.execute_script(f"window.scrollTo(0, {step});")
                time.sleep(0.5)
            
            # Прокрутка до конца
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # ШАГ 4: Собираем все отзывы
            logger.info("Сбор отзывов...")
            
            # Находим контейнер
            reviews_container = None
            try:
                reviews_container = driver.find_element(By.CSS_SELECTOR, 'div.business-reviews-card-view__reviews-container')
            except:
                reviews_container = driver
            
            # Находим все элементы отзывов
            review_elements = []
            try:
                review_elements = reviews_container.find_elements(By.CSS_SELECTOR, 'div.business-review-view')
                logger.info(f"Всего найдено элементов отзывов: {len(review_elements)}")
            except:
                logger.warning("Не удалось найти элементы отзывов")
                return get_quality_fallback_reviews_sync()
            
            # ШАГ 5: Парсим отзывы и собираем их с датами
            all_reviews_data = []
            
            for i, element in enumerate(review_elements):
                try:
                    # Проверяем рейтинг (только 5 звезд)
                    is_five_stars = False
                    try:
                        # Метод 1: По aria-label
                        stars_elements = element.find_elements(By.CSS_SELECTOR, '.business-rating-badge-view__stars')
                        for stars_element in stars_elements:
                            aria_label = stars_element.get_attribute('aria-label')
                            if aria_label and 'Оценка 5 Из 5' in aria_label:
                                is_five_stars = True
                                break
                        
                        # Метод 2: По подсчету звезд
                        if not is_five_stars:
                            star_count = len(element.find_elements(By.CSS_SELECTOR, '.business-rating-badge-view__star._full'))
                            if star_count >= 5:
                                is_five_stars = True
                    except:
                        pass
                    
                    if not is_five_stars:
                        continue
                    
                    # Автор
                    author = "Гость"
                    try:
                        author_elements = element.find_elements(By.CSS_SELECTOR, 'span[itemprop="name"]')
                        for author_element in author_elements:
                            text = author_element.text.strip()
                            if text:
                                author = text[:30]
                                break
                    except:
                        pass
                    
                    # Дата (важно для сортировки)
                    date_text = ""
                    date_obj = None
                    try:
                        date_elements = element.find_elements(By.CSS_SELECTOR, '[class*="date"], time')
                        for date_element in date_elements:
                            text = date_element.text.strip()
                            if text:
                                date_text = text
                                
                                # Парсим дату в объект datetime для сортировки
                                try:
                                    date_lower = text.lower()
                                    
                                    # Месяцы
                                    months = {
                                        'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'мая': 5, 'июн': 6,
                                        'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
                                    }
                                    
                                    # Год
                                    year_match = re.search(r'(\d{4})', text)
                                    year = int(year_match.group(1)) if year_match else 2025
                                    
                                    # Месяц
                                    month = 1
                                    for m_name, m_num in months.items():
                                        if m_name in date_lower:
                                            month = m_num
                                            break
                                    
                                    # День
                                    day_match = re.search(r'(\d{1,2})', text)
                                    day = int(day_match.group(1)) if day_match else 1
                                    
                                    date_obj = datetime(year, month, day)
                                except:
                                    # Если не удалось распарсить, используем текущую дату
                                    date_obj = datetime(2025, 1, 1)
                                
                                break
                    except:
                        pass
                    
                    if not date_text:
                        continue  # Пропускаем отзывы без даты
                    
                    # Текст отзыва
                    review_text = ""
                    try:
                        # Основной текст
                        body_elements = element.find_elements(By.CSS_SELECTOR, '.business-review-view__body')
                        for body_element in body_elements:
                            text = body_element.text.strip()
                            if text and len(text) > 20:
                                review_text = text
                                break
                        
                        # Альтернативные селекторы
                        if not review_text:
                            alt_selectors = ['.business-review-view__text', '.spoiler-view__text']
                            for selector in alt_selectors:
                                try:
                                    elements = element.find_elements(By.CSS_SELECTOR, selector)
                                    for elem in elements:
                                        text = elem.text.strip()
                                        if text and len(text) > 20:
                                            review_text = text
                                            break
                                    if review_text:
                                        break
                                except:
                                    continue
                    except:
                        pass
                    
                    # Обрезаем длинный текст
                    if len(review_text) > 120:
                        review_text = review_text[:117] + "..."
                    
                    # Добавляем отзыв если есть текст
                    if review_text and len(review_text) > 10:
                        all_reviews_data.append({
                            'author': author,
                            'rating': 5,
                            'text': review_text,
                            'date': date_text[:20],
                            'date_obj': date_obj
                        })
                    
                except Exception as e:
                    logger.debug(f"Ошибка парсинга отзыва {i+1}: {e}")
                    continue
            
            logger.info(f"Собрано 5-звездочных отзывов: {len(all_reviews_data)}")
            
            # ШАГ 6: Сортируем по дате и возвращаем результат
            if all_reviews_data:
                # Сортируем по дате (самые новые первыми)
                all_reviews_data.sort(key=lambda x: x['date_obj'], reverse=True)
                
                # Берем 10 самых свежих
                fresh_reviews = all_reviews_data[:10]
                
                # Убираем временный объект даты
                for review in fresh_reviews:
                    del review['date_obj']
                
                # Логируем результат
                logger.info("Топ-5 самых свежих отзывов:")
                for i, review in enumerate(fresh_reviews[:5]):
                    logger.info(f"  {i+1}. {review['date']} - {review['author']} - '{review['text'][:50]}...'")
                
                elapsed_time = time.time() - start_time
                logger.info(f"Парсинг завершен за {elapsed_time:.1f} секунд")
                
                return fresh_reviews
            
            # Если не нашли отзывов, используем fallback
            logger.warning("Не найдено 5-звездочных отзывов, используем тестовые данные")
            return get_quality_fallback_reviews_sync()
            
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.info("Браузер закрыт")
                except:
                    pass
                    
    except Exception as e:
        logger.error(f"Ошибка в парсинге: {e}")
        return get_quality_fallback_reviews_sync()

def parse_yandex_reviews_sync():
    """Синхронный парсинг отзывов с Яндекс Карт"""
    try:
        logger.info("Запускаем парсинг отзывов с Яндекс Карт...")
        
        # Проверяем доступность Selenium
        try:
            from selenium import webdriver
            logger.info("Selenium доступен, начинаем парсинг...")
        except ImportError as e:
            logger.warning(f"Selenium не установлен: {e}")
            return get_quality_fallback_reviews_sync()
        
        # Запускаем парсинг
        reviews = _run_selenium_sync()
        
        if len(reviews) < 1:  # Минимум 1 отзыв
            logger.warning(f"Найдено только {len(reviews)} отзывов, используем тестовые")
            return get_quality_fallback_reviews_sync()
        
        logger.info(f"Успешно спарсено {len(reviews)} отзывов")
        return reviews  # Возвращаем ВСЕ что нашли, а не только 3!
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return get_quality_fallback_reviews_sync()

async def parse_yandex_reviews_fast():
    """Асинхронная обертка для парсинга"""
    # Запускаем в отдельном потоке, чтобы не блокировать event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, parse_yandex_reviews_sync)

def get_quality_fallback_reviews_sync():
    """Синхронная версия качественных тестовых отзывов"""
    return [
        {
            'author': 'Таисия Тимошина',
            'rating': 5,
            'text': 'Это просто чудесная кофейня-ресторан, которая стала местом многих замечательных воспоминаний. Ходим сюда уже четвёртый год.',
            'date': '23 сентября 2025'
        },
        {
            'author': 'Наталия С.',
            'rating': 5,
            'text': 'Небольшое уютное кафе с хорошей кухней и внимательным персоналом. Особенно понравились десерты и кофе.',
            'date': '18 июля 2025'
        },
        {
            'author': 'Элен',
            'rating': 5,
            'text': 'Маленький ресторан, играет приятная музыка. Хорошие позиции в меню, особенно рекомендую борщ и гренки.',
            'date': '18 октября 2025'
        }
    ]

async def parse_yandex_reviews():
    """Основная асинхронная функция парсинга"""
    return await parse_yandex_reviews_fast()

def init_database():
    """Инициализация базы данных"""
    database.init_database()

def get_bot_stats():
    """Получение статистики бота"""
    return database.get_stats()
