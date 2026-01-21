"""
config.py
Конфигурация бота с настройками производительности
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ===== ОБЯЗАТЕЛЬНЫЕ НАСТРОЙКИ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "090909")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен в переменных окружения!")

# ===== НАСТРОЙКИ РЕСТОРАНА =====
RESTAURANT_NAME = "Рестобар Mashkov"
RESTAURANT_ADDRESS = "бул. Академика Ландау, 1, Москва"
RESTAURANT_PHONE = "+7 (903) 748-80-80"
RESTAURANT_HOURS = "Ежедневно с 08:00 до 22:00"

# Описание
HOW_TO_GET = "📍 Метро «Физтех», выход №1 → 15 минут пешком\n🚗 Бесплатная парковка у входа"
CONCEPT_DESCRIPTION = "Mashkov — уютный ресторан с европейской кухней и атмосферой загородного дома."
START_MESSAGE = "🎭 <b>Добро пожаловать в консьерж-сервис рестобара Mashkov!</b>\n\n👋 <b>Привет! Меня зовут Мак</b> — я ваш персональный AI-помощник от ресторана Машков, готовый помочь 24/7! 🤖\n\n━━━━━━━━━━━━━━━━━━━━\n<b>🎯 Что я умею:</b>\n\n🍽️ <b>Меню и заказы</b>\n   • Показать актуальное меню с фото\n   • Рассказать о блюдах и калориях\n   • Оформить доставку за 2 минуты\n\n📅 <b>Бронирование</b>\n   • Забронировать столик онлайн\n   • Выбрать удобное время\n   • Организовать банкет\n\n🎉 <b>Мероприятия</b>\n   • Зарегистрировать на события\n   • Узнать о предстоящих мероприятиях\n   • Подать заявку на участие\n\n💬 <b>Консультации</b>\n   • Ответить на любые вопросы\n   • Помочь с выбором блюд\n   • Рассказать о ресторане\n\n📱 <b>Дополнительно</b>\n   • Скачать мобильное приложение\n   • Оставить отзыв\n   • Узнать как добраться\n━━━━━━━━━━━━━━━━━━━━\n\n<b>💡 Просто напишите ваш вопрос, и я помогу!</b>\n<i>Можете обращаться ко мне просто «Мак» 😊</i>\n\n📌 <i>Список команд находится около скрепки - синяя кнопка «Меню»</i>"

# ===== ССЫЛКИ =====
# Приложения
APP_IOS = "https://apps.apple.com/ru/app/рестобар-mashkov/id6739469772"
APP_ANDROID = "https://play.google.com/store/apps/details?id=ru.saby.clients.brand.mashkov"
APP_RUSTORE = "https://www.rustore.ru/catalog/app/ru.saby.clients.brand.mashkov"
TELEGRAM_CHANNEL = "https://t.me/Mashkov_rest"

# Отзывы
YANDEX_REVIEWS_URL = "https://yandex.ru/maps/org/mashkov/202266309008/reviews/"
YANDEX_ADD_REVIEW_URL = "https://yandex.ru/maps/org/mashkov/202266309008/reviews/add/"
YANDEX_PLACE_ID = "202266309008"

# Соглашения
USER_AGREEMENT_URL = "https://mashkov.rest/orders/"
PRIVACY_POLICY_URL = "https://mashkov.rest/about/"

# ===== НАСТРОЙКИ ДОСТАВКИ =====
DELIVERY_COST = 200
FREE_DELIVERY_MIN = 1500
DELIVERY_TIME = "45–60 минут"

# ===== НАСТРОЙКИ PRESTO API =====
PRESTO_CONNECTION_ID = os.getenv("PRESTO_CONNECTION_ID", "2442001473040410")
PRESTO_SECRET_KEY = os.getenv("PRESTO_SECRET_KEY", "IR9K96TJIRNJSRIL3EW0JVE0")
# PRESTO_POINT_ID будет определен динамически

# ===== ПУТИ ДЛЯ МЕНЮ =====
MENU_IMAGES_DIR = "files/imagesMenu"
MENU_CACHE_FILE = "files/menu_cache.json"
CART_CACHE_FILE = "files/cart_cache.json"

# ===== НАСТРОЙКИ ПРОИЗВОДИТЕЛЬНОСТИ =====
# Таймауты (в секундах)
REQUEST_TIMEOUT = 30  # Таймаут запросов к Telegram API
MESSAGE_TIMEOUT = 10  # Таймаут отправки сообщений
PARSE_TIMEOUT = 120    # Таймаут парсинга
# Таймаут для выполнения обработчиков команд (сек)
COMMAND_HANDLER_TIMEOUT = 5
# DaData API ключи для геокодирования
DADATA_API_KEY = "22c61b595d7df2dc0e8dfbd23d75507df6f42241"
DADATA_SECRET_KEY = "65e28890350e73f6b12621df299e6d89380869e2"
# Попытки
MAX_RETRIES = 5       # Максимальное количество попыток отправки (увеличено для нестабильного интернета)
RETRY_DELAY = 2       # Задержка между попытками (сек) - увеличено для стабильности

# Рассылки
NEWSLETTER_BATCH_SIZE = 30    # Размер батча для рассылок
NEWSLETTER_DELAY = 0.5        # Задержка между батчами (сек)
MAX_NEWSLETTER_RETRIES = 3    # Максимальное количество повторных попыток
NEWSLETTER_TIMEOUT = 30       # Таймаут для отправки одной пачки

# База данных
DB_CACHE_TTL = 300            # Время жизни кэша (сек)
DB_POOL_SIZE = 10             # Размер пула соединений

# ===== НАСТРОЙКИ БАНКЕТА =====
BANQUET_PREPAYMENT = 50  # процент предоплаты
BANQUET_MIN_DAYS = 5     # дней до мероприятия

# ===== НАСТРОЙКИ БЕЗОПАСНОСТИ =====
MAX_MESSAGE_LENGTH = 4096     # Максимальная длина сообщения
MAX_PHOTO_SIZE_MB = 10        # Максимальный размер фото в MB
ALLOWED_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']  # Разрешенные типы фото

# ===== ЛОГГИРОВАНИЕ =====
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

PRESTO_ACCESS_TOKEN = os.getenv("PRESTO_ACCESS_TOKEN", "aT9ATVJhVWc9NnpSOmR2RzszKmE7NnclOlVWTmJsOls6LWZyTX5OZCgufnUdV89bVlsLT5LMlZT14tWzN0MTIwMjYtMDEtMDQgMTQ6NDU6NDYuOTMwOTY2")

print("Конфигурация загружена")
print(f"Режим админа: {'включен' if ADMIN_PASSWORD else 'выключен'}")
print(f"Токен бота: {BOT_TOKEN[:10]}...")
print(f"API Presto: подключение {PRESTO_CONNECTION_ID[:10]}...")