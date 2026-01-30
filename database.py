"""
database.py - База данных для хранения всех данных с оптимизациями и адресами
"""

import sqlite3
from datetime import datetime, timedelta
import threading
import time
import atexit
from typing import Dict, List, Optional, Any, Tuple
import contextlib
import logging

logger = logging.getLogger(__name__)

# Глобальные переменные для кэша с использованием LRU
_settings_cache: Dict[str, str] = {}
_settings_cache_time: float = 0
_settings_cache_lock = threading.Lock()
SETTINGS_CACHE_TTL = 30  # секунд

_reviews_cache: Optional[List] = None
_reviews_cache_time: float = 0
REVIEWS_CACHE_TTL = 300  # 5 минут

_faq_cache: Optional[List] = None
_faq_cache_time: float = 0
FAQ_CACHE_TTL = 300  # 5 минут

_user_addresses_cache: Dict[int, List[Dict]] = {}
_user_addresses_cache_time: Dict[int, float] = {}
ADDRESSES_CACHE_TTL = 600  # 10 минут

# Пул соединений с ограничением по размеру
MAX_POOL_SIZE = 20
_connection_pool: Dict[int, sqlite3.Connection] = {}
_pool_lock = threading.Lock()

# Кэш для быстрых проверок админов и регистраций
_admin_cache: Dict[int, Tuple[bool, float]] = {}
_user_reg_cache: Dict[int, Tuple[str, float]] = {}
_cache_ttl = 300  # 5 минут
_cache_cleanup_interval = 60  # очистка кэша каждые 60 секунд
_last_cache_cleanup = time.time()

@contextlib.contextmanager
def get_cursor():
    """Контекстный менеджер для работы с курсором"""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()

def get_connection() -> sqlite3.Connection:
    """Получение соединения из пула с оптимизацией"""
    thread_id = threading.get_ident()
    
    with _pool_lock:
        # Очищаем старые соединения если пул слишком большой
        if len(_connection_pool) > MAX_POOL_SIZE:
            cleanup_old_connections()
        
        if thread_id not in _connection_pool:
            # Создаем новое соединение с оптимизациями
            conn = sqlite3.connect(
                'restaurant.db',
                check_same_thread=False,
                timeout=5,
                isolation_level=None  # Автокоммит
            )
            # Включаем оптимизации SQLite
            try:
                conn.execute('PRAGMA journal_mode=DELETE')
            except sqlite3.OperationalError as e:
                logger.warning(f"SQLite PRAGMA journal_mode=DELETE failed: {e}")
                try:
                    conn.execute('PRAGMA journal_mode=WAL')
                except sqlite3.OperationalError as e2:
                    logger.warning(f"SQLite PRAGMA journal_mode=WAL failed: {e2}")
            try:
                conn.execute('PRAGMA synchronous=NORMAL')
            except sqlite3.OperationalError as e:
                logger.debug(f"SQLite PRAGMA synchronous failed: {e}")
            try:
                conn.execute('PRAGMA cache_size=-2000')  # Кэш 2MB
            except sqlite3.OperationalError as e:
                logger.debug(f"SQLite PRAGMA cache_size failed: {e}")
            try:
                conn.execute('PRAGMA temp_store=MEMORY')  # Временные таблицы в памяти
            except sqlite3.OperationalError as e:
                logger.debug(f"SQLite PRAGMA temp_store failed: {e}")
            try:
                conn.execute('PRAGMA mmap_size=268435456')  # 256MB mmap
            except sqlite3.OperationalError as e:
                logger.debug(f"SQLite PRAGMA mmap_size failed: {e}")
            conn.row_factory = sqlite3.Row
            _connection_pool[thread_id] = conn
        
        return _connection_pool[thread_id]

def cleanup_old_connections():
    """Очистка старых соединений из пула"""
    global _connection_pool
    current_time = time.time()
    
    # Удаляем соединения, которые не использовались 10+ минут
    threads_to_remove = []
    for thread_id, conn in list(_connection_pool.items()):
        # Проверяем активность потока
        try:
            # Если поток завершился, закрываем соединение
            import threading as th
            for thread in th.enumerate():
                if thread.ident == thread_id:
                    break
            else:
                threads_to_remove.append(thread_id)
        except:
            threads_to_remove.append(thread_id)
    
    for thread_id in threads_to_remove:
        try:
            _connection_pool[thread_id].close()
        except:
            pass
        del _connection_pool[thread_id]

def cleanup_cache():
    """Очистка устаревших записей в кэшах"""
    global _admin_cache, _user_reg_cache, _faq_cache, _faq_cache_time, _last_cache_cleanup

    current_time = time.time()

    # Очищаем каждые cache_cleanup_interval секунд
    if current_time - _last_cache_cleanup > _cache_cleanup_interval:
        # Очищаем старые записи в кэше админов
        expired_keys = []
        for user_id, (_, timestamp) in _admin_cache.items():
            if current_time - timestamp > _cache_ttl:
                expired_keys.append(user_id)

        for key in expired_keys:
            del _admin_cache[key]

        # Очищаем старые записи в кэше регистрации
        expired_keys = []
        for user_id, (_, timestamp) in _user_reg_cache.items():
            if current_time - timestamp > _cache_ttl:
                expired_keys.append(user_id)

        for key in expired_keys:
            del _user_reg_cache[key]

    # Очищаем старые записи в кэше адресов
    expired_keys = []
    for user_id, timestamp in list(_user_addresses_cache_time.items()):
        if current_time - timestamp > ADDRESSES_CACHE_TTL:
            expired_keys.append(user_id)

    for user_id in expired_keys:
        if user_id in _user_addresses_cache:
            del _user_addresses_cache[user_id]
        if user_id in _user_addresses_cache_time:
            del _user_addresses_cache_time[user_id]

    # Очищаем старые записи в кэше FAQ
    if _faq_cache and (current_time - _faq_cache_time) > FAQ_CACHE_TTL:
        _faq_cache = None
        _faq_cache_time = 0

        _last_cache_cleanup = current_time

def close_all_connections():
    """Закрытие всех соединений"""
    with _pool_lock:
        for conn in _connection_pool.values():
            try:
                conn.close()
            except:
                pass
        _connection_pool.clear()

# Регистрируем закрытие соединений при выходе
atexit.register(close_all_connections)

def init_database():
    """Инициализация базы данных с улучшенной схемой"""
    with get_cursor() as cursor:
        # Пользователи с улучшенной структурой
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            presto_uuid TEXT,
            registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP,
            session_count INTEGER DEFAULT 0,
            agreement_accepted INTEGER DEFAULT 0,
            age_verified INTEGER DEFAULT 0,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Добавляем поле age_verified если его нет (для существующих БД)
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN age_verified INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            # Поле уже существует
            pass
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            description TEXT,
            discount_percent INTEGER DEFAULT 0,
            discount_amount REAL DEFAULT 0,
            min_order_amount REAL DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_first_order_only INTEGER DEFAULT 0,
            once_per_user INTEGER DEFAULT 1,
            valid_from TEXT,
            valid_to TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        # Адреса пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            address TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            apartment TEXT DEFAULT '',
            entrance TEXT DEFAULT '',
            floor TEXT DEFAULT '',
            door_code TEXT DEFAULT '',
            is_default INTEGER DEFAULT 0,
            last_used TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        ''')
        
        # Бронирования с индексами
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            phone TEXT NOT NULL,
            guests INTEGER DEFAULT 2,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        ''')
        
        # Заказы с оптимизированной структурой
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            items TEXT NOT NULL,
            total_amount REAL DEFAULT 0,
            delivery_address TEXT,
            phone TEXT NOT NULL,
            status TEXT DEFAULT 'new',
            delivery_cost REAL DEFAULT 0,
            promocode TEXT,
            discount_amount REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        ''')
        
        # Промокоды пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_promocodes (
            user_id INTEGER NOT NULL,
            promocode TEXT NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            order_id INTEGER,
            discount_amount REAL DEFAULT 0,
            PRIMARY KEY (user_id, promocode),
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE SET NULL
        )
        ''')
        
        # Таблица промокодов (пустая таблица)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            description TEXT,
            discount_percent INTEGER DEFAULT 0,
            discount_amount REAL DEFAULT 0,
            min_order_amount REAL DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_first_order_only INTEGER DEFAULT 0,
            valid_from TEXT,
            valid_to TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Рассылки
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS newsletters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            message_text TEXT NOT NULL,
            message_type TEXT DEFAULT 'text',
            photo_id TEXT,
            sent_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Статистика с компрессией данных
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            details TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        ''')
        
        # Отзывы
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT,
            rating INTEGER,
            text TEXT,
            date TEXT,
            source TEXT DEFAULT 'yandex',
            parsed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # FAQ вопросы
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            answer TEXT,
            category TEXT DEFAULT 'general',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(question)
        )
        ''')
        
        # Админы
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Лимиты AI генераций
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_generations (
            user_id INTEGER NOT NULL,
            generation_date TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, generation_date)
        )
        ''')

        # Генерации персонажей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            character_name TEXT NOT NULL,
            dish_name TEXT,
            prompt TEXT,
            image_url TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        ''')

        # Добавляем dish_name колонку если её нет
        try:
            cursor.execute('ALTER TABLE character_generations ADD COLUMN dish_name TEXT')
        except sqlite3.OperationalError:
            # Колонка уже существует
            pass

        # Референсы персонажей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generation_id INTEGER NOT NULL,
            ref_path TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (generation_id) REFERENCES character_generations (id) ON DELETE CASCADE
        )
        ''')
        
        # Чаты для миниаппа админа
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            chat_status TEXT DEFAULT 'active',
            last_message TEXT,
            last_message_time TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        ''')

        # Сообщения чатов
        cursor.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            sender TEXT NOT NULL, -- 'user' or 'admin'
            message_text TEXT NOT NULL,
            message_time TEXT DEFAULT CURRENT_TIMESTAMP,
            sent INTEGER DEFAULT 0, -- 0 = не отправлено, 1 = отправлено
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
        )''')

        # Добавляем поле sent если его нет (для существующих БД)
        try:
            cursor.execute('ALTER TABLE chat_messages ADD COLUMN sent INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            # Поле уже существует
            pass

        # Добавляем поле file_path если его нет (для файлов)
        try:
            cursor.execute('ALTER TABLE chat_messages ADD COLUMN file_path TEXT')
        except sqlite3.OperationalError:
            # Поле уже существует
            pass

        # Настройки бота
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Создаем индексы для ускорения запросов
        indexes = [
            ('idx_users_last_active', 'users(last_active)'),
            ('idx_user_addresses_user', 'user_addresses(user_id)'),
            ('idx_user_addresses_default', 'user_addresses(user_id, is_default)'),
            ('idx_bookings_user_date', 'bookings(user_id, date)'),
            ('idx_bookings_status', 'bookings(status)'),
            ('idx_orders_user_status', 'orders(user_id, status)'),
            ('idx_orders_created', 'orders(created_at)'),
            ('idx_user_promocodes_user', 'user_promocodes(user_id)'),
            ('idx_user_promocodes_promo', 'user_promocodes(promocode)'),
            ('idx_promocodes_code', 'promocodes(code)'),
            ('idx_promocodes_active', 'promocodes(is_active)'),
            ('idx_stats_user_action', 'stats(user_id, action)'),
            ('idx_stats_time', 'stats(timestamp)'),
            ('idx_reviews_date', 'reviews(date DESC, created_at DESC)'),
            ('idx_reviews_author', 'reviews(author)'),
            ('idx_faq_category', 'faq(category)'),
            ('idx_newsletters_status', 'newsletters(status)')
        ]
        
        for idx_name, idx_sql in indexes:
            cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_sql}')
        
        # Добавляем настройки по умолчанию
        default_settings = [
            ('restaurant_name', 'Рестобар Mashkov'),
            ('restaurant_address', 'бул. Академика Ландау, 1, Москва'),
            ('restaurant_phone', '+7 (903) 748-80-80'),
            ('restaurant_hours', 'Ежедневно с 08:00 до 22:00'),
            ('how_to_get', '📍 Метро «Физтех», выход №1 → 15 минут пешком\n🚗 Бесплатная парковка у входа'),
            ('concept_description', 'Mashkov — уютный ресторан с европейской кухней и атмосферой загородного дома.'),
            ('start_message', 'Добро пожаловать в наш ресторан! Я помогу вам:\n• Посмотреть меню и сделать заказ\n• Забронировать столик\n• Узнать информацию о нас\n• Посмотреть отзывы\n• Ответить на ваши вопросы'),
            ('delivery_cost', '200'),
            ('free_delivery_min', '1500'),
            ('delivery_time', '45–60 минут'),
            ('agreement_url', 'https://mashkov.rest/orders/'),
            ('privacy_url', 'https://mashkov.rest/about/'),
            ('menu_change_threshold', '15')
        ]
        
        for key, value in default_settings:
            cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
        
        # Добавляем FAQ по умолчанию батчем
        cursor.execute('SELECT COUNT(*) FROM faq')
        if cursor.fetchone()[0] == 0:
            default_faq = [
                ('Какие часы работы ресторана?', 'Мы работаем ежедневно с 08:00 до 22:00.'),
                ('Есть ли у вас доставка?', 'Да, мы осуществляем доставку. Стоимость доставки 200 рублей, бесплатно от 1500 рублей. Время доставки 45-60 минут.'),
                ('Можно ли забронировать столик?', 'Да, вы можете забронировать столик через нашего бота или по телефону +7 (903) 748-80-80.'),
                ('Какие способы оплаты вы принимаете?', 'Мы принимаем наличные, банковские карты и бесконтактную оплату.'),
                ('Есть ли у вас вегетарианские блюда?', 'Да, в нашем меню есть раздел с вегетарианскими блюдами.'),
                ('Можно ли забронировать банкетный зал?', 'Да, мы предоставляем банкетные залы для мероприятий. Для уточнения деталей свяжитесь с нашим менеджером.'),
                ('Есть ли парковка?', 'Да, у ресторана есть бесплатная парковка для гостей.'),
                ('Можно ли прийти с детьми?', 'Да, у нас есть детское меню и высокие стульчики для малышей.'),
            ]
            
            for question, answer in default_faq:
                try:
                    cursor.execute('INSERT INTO faq (question, answer) VALUES (?, ?)', (question, answer))
                except sqlite3.IntegrityError:
                    pass
# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С АДРЕСАМИ =====

def save_user_address(user_id: int, address: str, 
                      latitude: Optional[float] = None, 
                      longitude: Optional[float] = None,
                      apartment: str = '', entrance: str = '', 
                      floor: str = '', door_code: str = '',
                      is_default: bool = True) -> int:
    """
    Сохранение адреса пользователя
    Возвращает ID сохраненного адреса
    """
    try:
        with get_cursor() as cursor:
            # Если делаем этот адрес дефолтным, снимаем флаг с других адресов
            if is_default:
                cursor.execute('''
                UPDATE user_addresses 
                SET is_default = 0 
                WHERE user_id = ? AND is_default = 1
                ''', (user_id,))
            
            # Сохраняем адрес
            cursor.execute('''
            INSERT INTO user_addresses 
            (user_id, address, latitude, longitude, apartment, 
             entrance, floor, door_code, is_default, last_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, address, latitude, longitude, apartment, 
                  entrance, floor, door_code, 1 if is_default else 0))
            
            address_id = cursor.lastrowid
            
            # Инвалидируем кэш адресов
            if user_id in _user_addresses_cache:
                del _user_addresses_cache[user_id]
            if user_id in _user_addresses_cache_time:
                del _user_addresses_cache_time[user_id]
            
            return address_id
            
    except Exception as e:
        logger.error(f"Ошибка сохранения адреса: {e}")
        return 0

def get_user_addresses(user_id: int, limit: int = 10) -> List[Dict]:
    """Получение адресов пользователя с кэшированием"""
    global _user_addresses_cache, _user_addresses_cache_time
    
    # Очищаем кэш
    cleanup_cache()
    
    # Проверяем кэш
    current_time = time.time()
    if (user_id in _user_addresses_cache and 
        user_id in _user_addresses_cache_time and
        current_time - _user_addresses_cache_time[user_id] < ADDRESSES_CACHE_TTL):
        return _user_addresses_cache[user_id].copy()
    
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT id, address, latitude, longitude, apartment, 
                   entrance, floor, door_code, is_default, last_used
            FROM user_addresses 
            WHERE user_id = ?
            ORDER BY is_default DESC, last_used DESC
            LIMIT ?
            ''', (user_id, limit))
            
            results = cursor.fetchall() or []
            addresses = [
                {
                    'id': row[0],
                    'address': row[1],
                    'latitude': row[2],
                    'longitude': row[3],
                    'apartment': row[4] or '',
                    'entrance': row[5] or '',
                    'floor': row[6] or '',
                    'door_code': row[7] or '',
                    'is_default': bool(row[8]),
                    'last_used': row[9]
                }
                for row in results
            ]
            
            # Сохраняем в кэш
            _user_addresses_cache[user_id] = addresses.copy()
            _user_addresses_cache_time[user_id] = current_time
            
            return addresses
            
    except Exception as e:
        logger.error(f"Ошибка получения адресов: {e}")
        return []

def get_user_default_address(user_id: int) -> Optional[Dict]:
    """Получение адреса по умолчанию пользователя"""
    addresses = get_user_addresses(user_id)
    for address in addresses:
        if address.get('is_default'):
            return address
    return addresses[0] if addresses else None

def update_address_last_used(address_id: int) -> bool:
    """Обновление времени последнего использования адреса"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE user_addresses 
            SET last_used = CURRENT_TIMESTAMP 
            WHERE id = ?
            ''', (address_id,))
            
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления адреса: {e}")
        return False

def delete_user_address(address_id: int, user_id: int) -> bool:
    """Удаление адреса пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM user_addresses WHERE id = ? AND user_id = ?', 
                         (address_id, user_id))
            
            # Инвалидируем кэш
            if user_id in _user_addresses_cache:
                del _user_addresses_cache[user_id]
            if user_id in _user_addresses_cache_time:
                del _user_addresses_cache_time[user_id]
            
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка удаления адреса: {e}")
        return False

def set_default_address(address_id: int, user_id: int) -> bool:
    """Установка адреса по умолчанию"""
    try:
        with get_cursor() as cursor:
            # Снимаем флаг со всех адресов
            cursor.execute('''
            UPDATE user_addresses 
            SET is_default = 0 
            WHERE user_id = ?
            ''', (user_id,))
            
            # Устанавливаем новый дефолтный
            cursor.execute('''
            UPDATE user_addresses 
            SET is_default = 1 
            WHERE id = ? AND user_id = ?
            ''', (address_id, user_id))
            
            # Инвалидируем кэш
            if user_id in _user_addresses_cache:
                del _user_addresses_cache[user_id]
            if user_id in _user_addresses_cache_time:
                del _user_addresses_cache_time[user_id]
            
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка установки адреса по умолчанию: {e}")
        return False

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С ПРОМОКОДАМИ =====

def add_promocode(code: str, discount_percent: int = 0, discount_amount: float = 0,
                  description: str = '', min_order_amount: float = 0,
                  max_uses: int = 1, is_first_order_only: bool = False,
                  once_per_user: bool = True,  # <-- ДОБАВЬТЕ ЭТОТ ПАРАМЕТР
                  valid_from: str = None, valid_to: str = None) -> bool:
    """Добавление нового промокода"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT INTO promocodes 
            (code, description, discount_percent, discount_amount, min_order_amount, 
             max_uses, is_first_order_only, once_per_user, valid_from, valid_to, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (code.upper(), description, discount_percent, discount_amount,
                  min_order_amount, max_uses, 1 if is_first_order_only else 0,
                  1 if once_per_user else 0,  # <-- СОХРАНЯЕМ
                  valid_from, valid_to))
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления промокода: {e}")
        return False

def get_promocode(code: str) -> Optional[Dict]:
    """Получение информации о промокоде"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT id, code, description, discount_percent, discount_amount,
                   min_order_amount, max_uses, used_count, is_active,
                   is_first_order_only, once_per_user, valid_from, valid_to  
            FROM promocodes 
            WHERE code = ?
            ''', (code.upper(),))
            
            result = cursor.fetchone()
            if result:
                return {
                    'id': result[0],
                    'code': result[1],
                    'description': result[2],
                    'discount_percent': result[3],
                    'discount_amount': result[4],
                    'min_order_amount': result[5],
                    'max_uses': result[6],
                    'used_count': result[7],
                    'is_active': bool(result[8]),
                    'is_first_order_only': bool(result[9]),
                    'once_per_user': result[10],  
                    'valid_from': result[11],
                    'valid_to': result[12]
                }
        return None
    except Exception as e:
        logger.error(f"Ошибка получения промокода: {e}")
        return None

def get_all_promocodes() -> List[Dict]:
    """Получение всех промокодов"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT id, code, description, discount_percent, discount_amount,
                   min_order_amount, max_uses, used_count, is_active,
                   is_first_order_only, once_per_user, valid_from, valid_to, created_at
            FROM promocodes 
            ORDER BY created_at DESC
            ''')
            
            results = cursor.fetchall() or []
            return [
                {
                    'id': row[0],
                    'code': row[1],
                    'description': row[2],
                    'discount_percent': row[3],
                    'discount_amount': row[4],
                    'min_order_amount': row[5],
                    'max_uses': row[6],
                    'used_count': row[7],
                    'is_active': bool(row[8]),
                    'is_first_order_only': bool(row[9]),
                    'once_per_user': row[10],  # <-- ДОБАВЬ
                    'valid_from': row[11],
                    'valid_to': row[12],
                    'created_at': row[13]
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Ошибка получения промокодов: {e}")
        return []

def validate_promocode_for_user(promocode: str, user_id: int, order_amount: float = 0) -> Dict:
    """
    Проверка промокода для пользователя
    Возвращает: {
        'valid': bool,
        'message': str,
        'discount_percent': int,
        'discount_amount': float,
        'type': 'percent' or 'amount'
    }
    """
    try:
        promo_data = get_promocode(promocode)
        
        if not promo_data:
            return {
                'valid': False,
                'message': 'Промокод не найден'
            }
        
        # Проверка активности
        if not promo_data['is_active']:
            return {
                'valid': False,
                'message': 'Промокод неактивен'
            }
        
        # Проверка минимальной суммы заказа
        if order_amount < promo_data['min_order_amount']:
            return {
                'valid': False,
                'message': f'Минимальная сумма заказа для промокода: {promo_data["min_order_amount"]}₽'
            }
        
        # Проверка дат действия
        now = datetime.now().date()
        if promo_data['valid_from']:
            try:
                valid_from = datetime.strptime(promo_data['valid_from'], '%Y-%m-%d').date()
                if now < valid_from:
                    return {
                        'valid': False,
                        'message': f'Промокод будет действителен с {promo_data["valid_from"]}'
                    }
            except:
                pass
        
        if promo_data['valid_to']:
            try:
                valid_to = datetime.strptime(promo_data['valid_to'], '%Y-%m-%d').date()
                if now > valid_to:
                    return {
                        'valid': False,
                        'message': f'Срок действия промокода истек'
                    }
            except:
                pass
        
        # Проверка общего лимита использований
        if promo_data['max_uses'] > 0 and promo_data['used_count'] >= promo_data['max_uses']:
            return {
                'valid': False,
                'message': 'Лимит использований промокода исчерпан'
            }
        
        # Проверка "только первый заказ"
        if promo_data['is_first_order_only']:
            user_orders = get_user_orders(user_id)
            if user_orders and len(user_orders) > 0:
                return {
                    'valid': False,
                    'message': 'Промокод доступен только для первого заказа'
                }
        
        # === ВАЖНОЕ ИСПРАВЛЕНИЕ ===
        # Проверка, не использовал ли уже пользователь этот промокод (если once_per_user = True)
        if promo_data.get('once_per_user', 1) == 1:  # По умолчанию только один раз
            user_promos = get_user_used_promocodes(user_id)
            for promo in user_promos:
                if promo['promocode'] == promocode.upper():
                    return {
                        'valid': False,
                        'message': 'Вы уже использовали этот промокод'
                    }
        
        # Рассчитываем скидку
        discount_amount = 0
        discount_type = 'percent' if promo_data['discount_percent'] > 0 else 'amount'
        
        if discount_type == 'percent':
            discount_amount = (order_amount * promo_data['discount_percent']) / 100
        else:  # 'amount'
            discount_amount = min(promo_data['discount_amount'], order_amount)  # Не больше суммы заказа
        
        return {
            'valid': True,
            'message': 'Промокод действителен',
            'discount_percent': promo_data['discount_percent'],
            'discount_amount': discount_amount,
            'code': promo_data['code'],
            'type': discount_type,
            'original_discount_amount': promo_data.get('discount_amount', 0),
            'once_per_user': promo_data.get('once_per_user', 1)  # Добавляем в ответ
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки промокода: {e}")
        return {
            'valid': False,
            'message': 'Ошибка проверки промокода'
        }

def mark_promocode_used(promocode: str) -> bool:
    """Отметка промокода как использованного"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE promocodes 
            SET used_count = used_count + 1 
            WHERE code = ?
            ''', (promocode.upper(),))
        return True
    except Exception as e:
        logger.error(f"Ошибка отметки промокода: {e}")
        return False

def get_all_promocodes() -> List[Dict]:
    """Получение всех промокодов"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT id, code, description, discount_percent, discount_amount,
                   min_order_amount, max_uses, used_count, is_active,
                   valid_from, valid_to, created_at
            FROM promocodes 
            ORDER BY created_at DESC
            ''')
            
            results = cursor.fetchall() or []
            return [
                {
                    'id': row[0],
                    'code': row[1],
                    'description': row[2],
                    'discount_percent': row[3],
                    'discount_amount': row[4],
                    'min_order_amount': row[5],
                    'max_uses': row[6],
                    'used_count': row[7],
                    'is_active': bool(row[8]),
                    'valid_from': row[9],
                    'valid_to': row[10],
                    'created_at': row[11]
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Ошибка получения промокодов: {e}")
        return []

def update_promocode_status(promocode_id: int, is_active: bool) -> bool:
    """Обновление статуса промокода"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE promocodes 
            SET is_active = ? 
            WHERE id = ?
            ''', (1 if is_active else 0, promocode_id))
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления промокода: {e}")
        return False

# ===== ОСТАВШИЕСЯ ФУНКЦИИ (существующие) =====

def save_user_promocode(user_id: int, promocode: str, order_id: Optional[int] = None, discount_amount: float = 0) -> bool:
    """Сохраняет использованный промокод пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT OR REPLACE INTO user_promocodes (user_id, promocode, order_id, discount_amount)
            VALUES (?, ?, ?, ?)
            ''', (user_id, promocode, order_id, discount_amount))
            
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения промокода: {e}")
        return False

def get_user_used_promocodes(user_id: int) -> List[Dict[str, Any]]:
    """Получает список использованных промокодов пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT promocode, used_at, order_id, discount_amount 
            FROM user_promocodes 
            WHERE user_id = ?
            ORDER BY used_at DESC
            ''', (user_id,))
            
            results = cursor.fetchall() or []
            return [
                {
                    'promocode': row[0],
                    'used_at': row[1],
                    'order_id': row[2],
                    'discount_amount': row[3]
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Ошибка получения промокодов: {e}")
        return []

def has_user_used_promocode(user_id: int, promocode: str) -> bool:
    """Проверяет использовал ли пользователь конкретный промокод"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT 1 FROM user_promocodes 
            WHERE user_id = ? AND promocode = ?
            ''', (user_id, promocode))
            
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка проверки промокода: {e}")
        return False

def get_user_first_order_promocode_status(user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Проверяет статус промокода для первого заказа
    Возвращает (может_использовать, использованный_промокод)
    """
    try:
        with get_cursor() as cursor:
            # Проверяем есть ли у пользователя заказы
            cursor.execute('SELECT COUNT(*) FROM orders WHERE user_id = ?', (user_id,))
            order_count = cursor.fetchone()[0] or 0
            
            if order_count == 0:
                # Если заказов нет, может использовать промокод на первый заказ
                return True, None
            
            # Ищем использовал ли уже промокод на первый заказ
            cursor.execute('''
            SELECT promocode FROM user_promocodes 
            WHERE user_id = ? AND promocode IN ('FIRSTORDER20', 'FIRSTORDER', 'FIRST')
            ''', (user_id,))
            
            result = cursor.fetchone()
            if result:
                return False, result[0]
            
            return False, None
            
    except Exception as e:
        logger.error(f"Ошибка проверки статуса промокода: {e}")
        return False, None

def update_order_with_promocode(order_id: int, promocode: str, discount_amount: float):
    """Обновляет заказ информацией о примененном промокоде"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE orders 
            SET promocode = ?, discount_amount = ?
            WHERE id = ?
            ''', (promocode, discount_amount, order_id))
    except Exception as e:
        logger.error(f"Ошибка обновления заказа промокодом: {e}")

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Получение настройки с кэшированием"""
    global _settings_cache, _settings_cache_time
    
    current_time = time.time()
    
    # Проверяем, нужно ли обновить кэш
    if not _settings_cache or (current_time - _settings_cache_time) > SETTINGS_CACHE_TTL:
        with _settings_cache_lock:
            # Двойная проверка
            if not _settings_cache or (current_time - _settings_cache_time) > SETTINGS_CACHE_TTL:
                with get_cursor() as cursor:
                    cursor.execute('SELECT key, value FROM settings')
                    rows = cursor.fetchall()
                    _settings_cache = {row[0]: row[1] for row in rows}
                    _settings_cache_time = current_time
    
    # Добавляем ai_notes по умолчанию
    if key == 'ai_notes' and key not in _settings_cache:
        return ''
    
    return _settings_cache.get(key, default)

def update_setting(key: str, value: str):
    """Обновление настройки с инвалидацией кэша"""
    global _settings_cache, _settings_cache_time

    with get_cursor() as cursor:
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))

    # Инвалидируем кэш
    with _settings_cache_lock:
        _settings_cache = {}
        _settings_cache_time = 0

def save_setting(key: str, value: str):
    """Алиас для update_setting (для совместимости)"""
    return update_setting(key, value)

def delete_setting(key: str) -> bool:
    """Удаление настройки с инвалидацией кэша"""
    global _settings_cache, _settings_cache_time

    try:
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM settings WHERE key = ?', (key,))

        # Инвалидируем кэш
        with _settings_cache_lock:
            _settings_cache = {}
            _settings_cache_time = 0

        return True
    except Exception as e:
        logger.error(f"Ошибка удаления настройки: {e}")
        return False

def fast_log_action(user_id: int, action: str, details: Optional[str] = None):
    """Быстрое логирование действий пользователей"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT INTO stats (user_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
            ''', (user_id, action, details, datetime.now().isoformat()))
    except Exception as e:
        logger.error(f"Ошибка логирования: {e}")

def bulk_log_actions(actions: List[Tuple[int, str, Optional[str]]]):
    """Массовое логирование действий"""
    if not actions:
        return
    
    try:
        with get_cursor() as cursor:
            cursor.executemany('''
            INSERT INTO stats (user_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
            ''', [(user_id, action, details, datetime.now().isoformat()) for user_id, action, details in actions])
    except Exception as e:
        logger.error(f"Ошибка массового логирования: {e}")

def add_or_update_user(user_id: int, username: Optional[str] = None, full_name: Optional[str] = None) -> bool:
    """Добавление/обновление пользователя одной операцией"""
    try:
        current_time = datetime.now().isoformat()
        
        with get_cursor() as cursor:
            # Используем UPSERT для атомарной операции
            cursor.execute('''
            INSERT INTO users (user_id, username, full_name, registered_at, last_active, session_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = COALESCE(excluded.full_name, full_name),
                last_active = excluded.last_active,
                session_count = session_count + 1,
                last_updated = excluded.last_active
            ''', (user_id, username, full_name, current_time, current_time))
            
            # Очищаем кэш регистрации для этого пользователя
            if user_id in _user_reg_cache:
                del _user_reg_cache[user_id]
        
        # Гарантируем создание чата сразу при добавлении пользователя
        # Это важно для отображения в админ-панели
        try:
            get_or_create_chat(user_id, full_name or username)
        except Exception as e:
            logger.error(f"Не удалось создать чат при добавлении пользователя {user_id}: {e}")
            
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя: {e}")
        return False

def update_user_phone(user_id: int, phone: str) -> bool:
    """Обновление телефона пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE users 
            SET phone = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''', (phone, user_id))
            
            # Очищаем кэш регистрации
            if user_id in _user_reg_cache:
                del _user_reg_cache[user_id]
            
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления телефона: {e}")
        return False

def update_user_name(user_id: int, name: str, accept_agreement: bool = True) -> bool:
    """Обновление имени пользователя и согласия"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE users 
            SET full_name = ?,
                agreement_accepted = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''', (name, 1 if accept_agreement else 0, user_id))
            
            # Также обновляем имя в чате, чтобы админ видел актуальное
            cursor.execute('''
            UPDATE chats
            SET user_name = ?
            WHERE user_id = ?
            ''', (name, user_id))
            
            # Очищаем кэш регистрации
            if user_id in _user_reg_cache:
                del _user_reg_cache[user_id]
            
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления имени: {e}")
        return False

def check_user_registration_fast(user_id: int) -> str:
    """Сверхбыстрая проверка регистрации пользователя с кэшированием"""
    global _user_reg_cache
    
    # Очищаем старый кэш периодически
    cleanup_cache()
    
    # Проверяем кэш
    if user_id in _user_reg_cache:
        status, timestamp = _user_reg_cache[user_id]
        if time.time() - timestamp < _cache_ttl:
            return status
    
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT phone FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result or not result[0]:
                status = 'not_registered'
            else:
                status = 'completed'
            
            # Сохраняем в кэш
            _user_reg_cache[user_id] = (status, time.time())
            return status
            
    except Exception as e:
        logger.error(f"Ошибка проверки регистрации: {e}")
        return 'not_registered'

def get_user_phone(user_id: int) -> Optional[str]:
    """Получить телефон пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT phone FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
    except Exception as e:
        logger.error(f"Ошибка при получении телефона пользователя: {e}")
        return None

def get_user_data(user_id: int) -> Optional[Dict[str, Any]]:
    """Получение данных пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT phone, full_name, username FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            if result:
                return {
                    'phone': result[0],
                    'full_name': result[1],
                    'username': result[2]
                }
            return None
    except Exception as e:
        logger.error(f"Ошибка получения данных пользователя: {e}")
        return None

def get_stats() -> Dict[str, Any]:
    """Получение статистики с кэшированием"""
    # Создаем локальный кэш для функции
    if not hasattr(get_stats, '_cache'):
        get_stats._cache = None
        get_stats._cache_time = 0
    
    current_time = time.time()
    
    # Проверяем кэш (30 секунд)
    if get_stats._cache and (current_time - get_stats._cache_time) < 30:
        return get_stats._cache.copy()
    
    stats = {
        'total_users': 0,
        'active_today': 0,
        'bookings_today': 0,
        'orders_today': 0,
        'popular_actions': [],
    }
    
    try:
        with get_cursor() as cursor:
            # Все запросы выполняем в одной транзакции
            cursor.execute('SELECT COUNT(*) FROM users')
            stats['total_users'] = cursor.fetchone()[0] or 0
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE date(last_active) = date("now")')
            stats['active_today'] = cursor.fetchone()[0] or 0
            
            cursor.execute('SELECT COUNT(*) FROM bookings WHERE date(created_at) = date("now")')
            stats['bookings_today'] = cursor.fetchone()[0] or 0
            
            cursor.execute('SELECT COUNT(*) FROM orders WHERE date(created_at) = date("now")')
            stats['orders_today'] = cursor.fetchone()[0] or 0
            
            cursor.execute('''
            SELECT action, COUNT(*) as count 
            FROM stats 
            WHERE timestamp > datetime('now', '-1 day')
            GROUP BY action 
            ORDER BY count DESC 
            LIMIT 5
            ''')
            stats['popular_actions'] = cursor.fetchall() or []
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
    
    # Сохраняем в кэш
    get_stats._cache = stats.copy()
    get_stats._cache_time = current_time
    
    return stats

def save_order(user_id: int, items: str, total_amount: float, phone: str, 
               delivery_address: Optional[str] = None, notes: Optional[str] = None,
               promocode: Optional[str] = None, discount_amount: float = 0) -> Optional[int]:
    """Сохранение заказа"""
    try:
        # Добавляем промокод в заметки если есть
        full_notes = notes or ""
        if promocode:
            full_notes += f"\nПромокод: {promocode} (скидка: {discount_amount}₽)" if full_notes else f"Промокод: {promocode} (скидка: {discount_amount}₽)"
        
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT INTO orders (user_id, items, total_amount, phone, delivery_address, promocode, discount_amount, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, items, total_amount, phone, delivery_address, promocode, discount_amount, full_notes.strip()))
            
            order_id = cursor.lastrowid
            
            # Сохраняем промокод если есть
            if promocode and order_id:
                save_user_promocode(user_id, promocode, order_id, discount_amount)
            
            return order_id
    except Exception as e:
        logger.error(f"Ошибка сохранения заказа: {e}")
        return None

def get_user_orders(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Получение заказов пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT id, items, total_amount, status, created_at, notes, promocode, discount_amount
            FROM orders 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            ''', (user_id, limit))
            
            results = cursor.fetchall() or []
            return [
                {
                    'id': row[0],
                    'items': row[1],
                    'total_amount': row[2],
                    'status': row[3],
                    'created_at': row[4],
                    'notes': row[5] or '',
                    'promocode': row[6] or '',
                    'discount_amount': row[7] or 0
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Ошибка получения заказов: {e}")
        return []

def get_all_orders(limit: int = 50) -> List:
    """Получение всех заказов"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT o.id, u.full_name, o.items, o.total_amount, o.status, 
                   o.created_at, o.notes, o.promocode, o.discount_amount
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.user_id
            ORDER BY o.created_at DESC
            LIMIT ?
            ''', (limit,))
            
            return cursor.fetchall() or []
    except Exception as e:
        logger.error(f"Ошибка получения всех заказов: {e}")
        return []

def create_newsletter(admin_id: int, message_text: str, 
                      message_type: str = 'text', photo_id: Optional[str] = None) -> Optional[int]:
    """Создание рассылки"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT INTO newsletters (admin_id, message_text, message_type, photo_id)
            VALUES (?, ?, ?, ?)
            ''', (admin_id, message_text, message_type, photo_id))
            
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Ошибка создания рассылки: {e}")
        return None

def get_pending_newsletters(limit: int = 5) -> List:
    """Получение ожидающих рассылок"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT id, message_text, message_type, photo_id
            FROM newsletters 
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
            ''', (limit,))
            
            return cursor.fetchall() or []
    except Exception as e:
        logger.error(f"Ошибка получения рассылок: {e}")
        return []

def update_newsletter_status(newsletter_id: int, status: str, sent_count: int = 0) -> bool:
    """Обновление статуса рассылки"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE newsletters 
            SET status = ?, sent_count = ?
            WHERE id = ?
            ''', (status, sent_count, newsletter_id))
            
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления рассылки: {e}")
        return False

def delete_user(user_id: int) -> bool:
    """Полное удаление пользователя и его данных"""
    try:
        with get_cursor() as cursor:
            # Удаляем адреса
            cursor.execute('DELETE FROM user_addresses WHERE user_id = ?', (user_id,))
            
            # Удаляем пользователя
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            
            # Очищаем кэш
            clear_user_cache(user_id)
            
            return True
    except Exception as e:
        logger.error(f"Ошибка удалении пользователя {user_id}: {e}")
        return False

def get_all_users(limit: int = 1000) -> List:
    """Получение всех активных пользователей"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT user_id, full_name, username, phone, last_active
            FROM users 
            WHERE last_active > datetime('now', '-30 days')
            ORDER BY last_active DESC
            LIMIT ?
            ''', (limit,))
            
            return cursor.fetchall() or []
    except Exception as e:
        logger.error(f"Ошибка получения пользователей: {e}")
        return []

def save_review(author: str, rating: int, text: str, date: str) -> bool:
    """Сохранение отзыва в БД с инвалидацией кэша"""
    global _reviews_cache, _reviews_cache_time
    
    try:
        # Пробуем распарсить дату из Яндекс формата
        parsed_date = ""
        if date:
            try:
                # Яндекс формат: "13 января 2024"
                month_map = {
                    'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
                    'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
                    'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
                }
                
                for ru_month, num_month in month_map.items():
                    if ru_month in date:
                        parts = date.split()
                        if len(parts) >= 3:
                            day = parts[0].zfill(2)
                            year = parts[2]
                            parsed_date = f"{year}-{num_month}-{day}"
                            break
            except:
                parsed_date = date
        
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT OR IGNORE INTO reviews (author, rating, text, date)
            VALUES (?, ?, ?, ?)
            ''', (author, rating, text, parsed_date if parsed_date else date))
            
            # Инвалидируем кэш отзывов
            _reviews_cache = None
            _reviews_cache_time = 0
            
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения отзыва: {e}")
        return False

def get_all_reviews() -> List:
    """Получение всех отзывов с кэшированием - СНАЧАЛА САМЫЕ СВЕЖИЕ!"""
    global _reviews_cache, _reviews_cache_time
    
    current_time = time.time()
    
    # Проверяем кэш
    if _reviews_cache and (current_time - _reviews_cache_time) < REVIEWS_CACHE_TTL:
        return _reviews_cache.copy()
    
    try:
        with get_cursor() as cursor:
            # Сначала сортируем по дате отзыва (date), если нет, то по created_at
            cursor.execute('''
            SELECT id, author, rating, text, date, created_at 
            FROM reviews 
            ORDER BY 
                CASE WHEN date != '' AND date IS NOT NULL THEN date ELSE created_at END DESC,
                created_at DESC
            LIMIT 50
            ''')
            
            reviews = cursor.fetchall() or []
            
            # Сохраняем в кэш
            _reviews_cache = reviews.copy()
            _reviews_cache_time = current_time
            
            return reviews
    except Exception as e:
        logger.error(f"Ошибка получения отзывов: {e}")
        return []

def get_reviews(limit: int = 10) -> List:
    """Получение отзывов для показа"""
    reviews = get_all_reviews()
    return reviews[:limit] if reviews else []

def save_booking(user_id: int, date: str, time: str, phone: str, guests: int) -> Optional[int]:
    """Сохранение бронирования"""
    try:
        with get_cursor() as cursor:
            # Отменяем старые активные брони этого пользователя
            cursor.execute('''
            UPDATE bookings 
            SET status = 'cancelled' 
            WHERE user_id = ? AND status = 'active' AND date = ?
            ''', (user_id, date))
            
            # Создаем новую бронь
            cursor.execute('''
            INSERT INTO bookings (user_id, date, time, phone, guests)
            VALUES (?, ?, ?, ?, ?)
            ''', (user_id, date, time, phone, guests))
            
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Ошибка сохранения брони: {e}")
        return None

def save_faq(question: str, answer: str, category: str = 'general') -> bool:
    """Сохранение FAQ с инвалидацией кэша"""
    global _faq_cache, _faq_cache_time
    
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT OR REPLACE INTO faq (question, answer, category, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (question, answer, category))
            
            # Инвалидируем кэш
            _faq_cache = None
            _faq_cache_time = 0
            
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения FAQ: {e}")
        return False

def get_faq() -> List:
    """Получение FAQ с кэшированием"""
    global _faq_cache, _faq_cache_time
    
    current_time = time.time()
    
    # Проверяем кэш
    if _faq_cache and (current_time - _faq_cache_time) < FAQ_CACHE_TTL:
        return _faq_cache.copy()
    
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT id, question, answer FROM faq ORDER BY id DESC')
            faq = cursor.fetchall() or []
            
            # Сохраняем в кэш
            _faq_cache = faq.copy()
            _faq_cache_time = current_time
            
            return faq
    except Exception as e:
        logger.error(f"Ошибка получения FAQ: {e}")
        return []

def delete_faq(faq_id: int) -> bool:
    """Удаление FAQ с инвалидацией кэша"""
    global _faq_cache, _faq_cache_time
    
    try:
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM faq WHERE id = ?', (faq_id,))
            
            # Инвалидируем кэш
            _faq_cache = None
            _faq_cache_time = 0
            
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления FAQ: {e}")
        return False

def add_admin(user_id: int) -> bool:
    """Добавление админа с инвалидацией кэша"""
    try:
        with get_cursor() as cursor:
            cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))
            
            # Очищаем кэш для этого пользователя
            if user_id in _admin_cache:
                del _admin_cache[user_id]
                
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления админа: {e}")
        return False


def remove_admin(user_id: int) -> bool:
    """Удаление админа и инвалидация кэша"""
    try:
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            if user_id in _admin_cache:
                del _admin_cache[user_id]
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления админа: {e}")
        return False

def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь админом с кэшированием"""
    global _admin_cache
    
    # Очищаем старый кэш периодически
    cleanup_cache()
    
    # Проверяем кэш
    if user_id in _admin_cache:
        result, timestamp = _admin_cache[user_id]
        if time.time() - timestamp < _cache_ttl:
            return result
    
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
            result = cursor.fetchone() is not None
            
            # Сохраняем в кэш
            _admin_cache[user_id] = (result, time.time())
            
            return result
    except Exception as e:
        logger.error(f"Ошибка проверки админа: {e}")
        return False

def clear_admin_cache(user_id: Optional[int] = None):
    """Очистка кэша админа"""
    global _admin_cache
    
    if user_id:
        if user_id in _admin_cache:
            del _admin_cache[user_id]
    else:
        _admin_cache.clear()

def clear_user_cache(user_id: int):
    """Очистка кэша пользователя"""
    global _user_reg_cache, _user_addresses_cache, _user_addresses_cache_time
    
    if user_id in _user_reg_cache:
        del _user_reg_cache[user_id]
    
    if user_id in _user_addresses_cache:
        del _user_addresses_cache[user_id]
    
    if user_id in _user_addresses_cache_time:
        del _user_addresses_cache_time[user_id]
    
    clear_admin_cache(user_id)

def get_all_settings() -> Dict[str, str]:
    """Получение всех настроек"""
    # Обновляем кэш если пустой
    if not _settings_cache:
        get_setting('temp')  # Это обновит кэш
    
    return _settings_cache.copy()

def bulk_update_settings(settings: Dict[str, str]):
    """Массовое обновление настроек"""
    global _settings_cache, _settings_cache_time
    
    try:
        with get_cursor() as cursor:
            for key, value in settings.items():
                cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        
        # Инвалидируем кэш
        with _settings_cache_lock:
            _settings_cache = {}
            _settings_cache_time = 0
    except Exception as e:
        logger.error(f"Ошибка массового обновления настроек: {e}")

def delete_review(review_id: int) -> bool:
    """Удаление отзыва"""
    global _reviews_cache, _reviews_cache_time
    
    try:
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM reviews WHERE id = ?', (review_id,))
            
            # Инвалидируем кэш
            _reviews_cache = None
            _reviews_cache_time = 0
            
            return True
    except Exception as e:
        logger.error(f"Ошибка удаления отзыва: {e}")
        return False

def delete_all_reviews() -> int:
    """Удаление всех отзывов"""
    global _reviews_cache, _reviews_cache_time
    
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM reviews')
            count_before = cursor.fetchone()[0] or 0
            
            cursor.execute('DELETE FROM reviews')
            
            cursor.execute('SELECT COUNT(*) FROM reviews')
            count_after = cursor.fetchone()[0] or 0
            
            deleted_count = count_before - count_after
            
            # Инвалидируем кэш
            _reviews_cache = None
            _reviews_cache_time = 0
            
            return deleted_count
    except Exception as e:
        logger.error(f"Ошибка удаления всех отзывов: {e}")
        return 0

def get_newsletter_by_id(newsletter_id: int) -> Optional[Dict[str, Any]]:
    """Получение рассылки по ID"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT id, admin_id, message_text, message_type, photo_id, status, sent_count, created_at
            FROM newsletters 
            WHERE id = ?
            ''', (newsletter_id,))
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
    except Exception as e:
        logger.error(f"Ошибка получения рассылки: {e}")
        return None

def get_promocode_stats(code: str) -> Dict[str, Any]:
    """Получение статистики по промокоду"""
    try:
        with get_cursor() as cursor:
            # Получаем базовую информацию
            cursor.execute('''
                SELECT code, discount_percent, discount_amount, used_count, 
                       max_uses, valid_from, valid_to, is_active, created_at
                FROM promocodes 
                WHERE code = ?
            ''', (code.upper(),))
            
            result = cursor.fetchone()
            if not result:
                return None
            
            # Получаем детальную статистику использования
            cursor.execute('''
                SELECT up.user_id, up.used_at, up.discount_amount, 
                       u.full_name, u.phone, o.total_amount
                FROM user_promocodes up
                LEFT JOIN users u ON up.user_id = u.user_id
                LEFT JOIN orders o ON up.order_id = o.id
                WHERE up.promocode = ?
                ORDER BY up.used_at DESC
            ''', (code.upper(),))
            
            usage_data = cursor.fetchall()
            
            # Получаем статистику по категориям/блюдам если есть
            cursor.execute('''
                SELECT value FROM settings 
                WHERE key LIKE ?
            ''', (f'promocode_{code.upper()}_%',))
            
            settings = cursor.fetchall()
            
            stats = {
                'code': result[0],
                'discount_percent': result[1],
                'discount_amount': result[2],
                'used_count': result[3],
                'max_uses': result[4],
                'valid_from': result[5],
                'valid_to': result[6],
                'is_active': bool(result[7]),
                'created_at': result[8],
                'usage': [],
                'settings': {}
            }
            
            for row in usage_data:
                stats['usage'].append({
                    'user_id': row[0],
                    'used_at': row[1],
                    'discount_amount': row[2],
                    'full_name': row[3],
                    'phone': row[4],
                    'order_total': row[5]
                })
            
            for row in settings:
                key = row[0]
                value = row[1]
                stats['settings'][key] = value
            
            return stats
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики промокода: {e}")
        return None

def get_promocodes_for_dish(dish_id: int) -> List[Dict]:
    """Получение промокодов для конкретного блюда"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
                SELECT p.id, p.code, p.description, p.discount_percent, 
                       p.discount_amount, p.min_order_amount, p.max_uses,
                       p.used_count, p.is_active, p.valid_from, p.valid_to
                FROM promocodes p
                INNER JOIN settings s ON s.key = CONCAT('promocode_', p.code, '_dish_', ?)
                WHERE p.is_active = 1 
                AND (p.valid_to IS NULL OR p.valid_to >= date('now'))
            ''', (dish_id,))
            
            results = cursor.fetchall() or []
            return [
                {
                    'id': row[0],
                    'code': row[1],
                    'description': row[2],
                    'discount_percent': row[3],
                    'discount_amount': row[4],
                    'min_order_amount': row[5],
                    'max_uses': row[6],
                    'used_count': row[7],
                    'is_active': bool(row[8]),
                    'valid_from': row[9],
                    'valid_to': row[10]
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Ошибка получения промокодов для блюда: {e}")
        return []

def get_promocodes_for_category(category_id: int) -> List[Dict]:
    """Получение промокодов для категории"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
                SELECT p.id, p.code, p.description, p.discount_percent, 
                       p.discount_amount, p.min_order_amount, p.max_uses,
                       p.used_count, p.is_active, p.valid_from, p.valid_to
                FROM promocodes p
                INNER JOIN settings s ON s.key = CONCAT('promocode_', p.code, '_category_', ?)
                WHERE p.is_active = 1 
                AND (p.valid_to IS NULL OR p.valid_to >= date('now'))
            ''', (category_id,))
            
            results = cursor.fetchall() or []
            return [
                {
                    'id': row[0],
                    'code': row[1],
                    'description': row[2],
                    'discount_percent': row[3],
                    'discount_amount': row[4],
                    'min_order_amount': row[5],
                    'max_uses': row[6],
                    'used_count': row[7],
                    'is_active': bool(row[8]),
                    'valid_from': row[9],
                    'valid_to': row[10]
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Ошибка получения промокодов для категории: {e}")
        return []

def get_all_promocode_stats() -> Dict[str, Any]:
    """Получение общей статистики по всем промокодам"""
    try:
        with get_cursor() as cursor:
            # Общая статистика
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                    SUM(used_count) as total_uses,
                    SUM(CASE WHEN is_active = 1 AND (valid_to IS NULL OR valid_to >= date('now')) THEN 1 ELSE 0 END) as currently_active
                FROM promocodes
            ''')
            
            total_stats = cursor.fetchone()
            
            # Статистика по дням
            cursor.execute('''
                SELECT date(up.used_at) as use_date, COUNT(*) as count, SUM(up.discount_amount) as total_discount
                FROM user_promocodes up
                WHERE up.used_at >= date('now', '-30 days')
                GROUP BY date(up.used_at)
                ORDER BY use_date DESC
                LIMIT 30
            ''')
            
            daily_stats = cursor.fetchall()
            
            # Самые популярные промокоды
            cursor.execute('''
                SELECT p.code, p.description, p.used_count, 
                       p.discount_percent, p.discount_amount,
                       COUNT(up.promocode) as unique_users
                FROM promocodes p
                LEFT JOIN user_promocodes up ON p.code = up.promocode
                GROUP BY p.code
                ORDER BY p.used_count DESC
                LIMIT 10
            ''')
            
            popular_promos = cursor.fetchall()
            
            return {
                'total': total_stats[0] or 0,
                'active': total_stats[1] or 0,
                'total_uses': total_stats[2] or 0,
                'currently_active': total_stats[3] or 0,
                'daily_stats': daily_stats,
                'popular_promos': popular_promos
            }
            
    except Exception as e:
        logger.error(f"Ошибка получения общей статистики: {e}")
        return {}

def get_all_admins():
    """Получает список ID всех админов"""
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT user_id FROM admins')
            admins = [row[0] for row in cursor.fetchall() or []]
        return admins
    except Exception as e:
        logger.error(f"Ошибка получения списка админов: {e}")
        return []


def update_user_presto_uuid(user_id: int, presto_uuid: str) -> bool:
    """Обновление Presto UUID пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE users 
            SET presto_uuid = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''', (presto_uuid, user_id))
            
            if user_id in _user_reg_cache:
                del _user_reg_cache[user_id]
            
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления Presto UUID: {e}")
        return False

def get_user_presto_uuid(user_id: int) -> Optional[str]:
    """Получение Presto UUID пользователя"""
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT presto_uuid FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
    except Exception as e:
        logger.error(f"Ошибка получения Presto UUID: {e}")
        return None

def check_ai_generation_limit(user_id: int, daily_limit: int = 2) -> Tuple[bool, int]:
    """
    Проверка лимита AI генераций для пользователя
    Возвращает (можно_генерировать, оставшиеся_генерации)
    """
    try:
        # Админы имеют безлимит
        if is_admin(user_id):
            return True, 999
        
        today = datetime.now().date().isoformat()
        
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT count FROM ai_generations 
            WHERE user_id = ? AND generation_date = ?
            ''', (user_id, today))
            
            result = cursor.fetchone()
            current_count = result[0] if result else 0
            
            remaining = daily_limit - current_count
            can_generate = remaining > 0
            
            return can_generate, max(0, remaining)
    except Exception as e:
        logger.error(f"Ошибка проверки лимита AI: {e}")
        return True, daily_limit  # В случае ошибки разрешаем

def increment_ai_generation(user_id: int) -> bool:
    """
    Увеличение счетчика AI генераций для пользователя
    """
    try:
        today = datetime.now().date().isoformat()
        
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT INTO ai_generations (user_id, generation_date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, generation_date) 
            DO UPDATE SET count = count + 1
            ''', (user_id, today))
            
        return True
    except Exception as e:
        logger.error(f"Ошибка увеличения счетчика AI: {e}")
        return False

def get_ai_generation_stats(user_id: int) -> Dict[str, Any]:
    """
    Получение статистики AI генераций пользователя
    """
    try:
        with get_cursor() as cursor:
            # Сегодняшние генерации
            today = datetime.now().date().isoformat()
            cursor.execute('''
            SELECT count FROM ai_generations 
            WHERE user_id = ? AND generation_date = ?
            ''', (user_id, today))
            
            result = cursor.fetchone()
            today_count = result[0] if result else 0
            
            # Всего генераций
            cursor.execute('''
            SELECT SUM(count) FROM ai_generations 
            WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            total_count = result[0] if result and result[0] else 0
            
            return {
                'today': today_count,
                'total': total_count,
                'is_admin': is_admin(user_id)
            }
    except Exception as e:
        logger.error(f"Ошибка получения статистики AI: {e}")
        return {'today': 0, 'total': 0, 'is_admin': False}

def get_user_complete_data(user_id: int) -> Optional[Dict[str, Any]]:
    """Получение полных данных пользователя для ЛК"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT user_id, username, full_name, phone, presto_uuid,
                   registered_at, last_active, session_count,
                   agreement_accepted
            FROM users
            WHERE user_id = ?
            ''', (user_id,))

            result = cursor.fetchone()
            if result:
                return {
                    'user_id': result[0],
                    'username': result[1],
                    'full_name': result[2],
                    'phone': result[3],
                    'presto_uuid': result[4],
                    'registered_at': result[5],
                    'last_active': result[6],
                    'session_count': result[7],
                    'agreement_accepted': bool(result[8])
                }
            return None
    except Exception as e:
        logger.error(f"Ошибка получения полных данных пользователя: {e}")
        return None

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С ЧАТАМИ МИНИАППА =====

def get_or_create_chat(user_id: int, user_name: str = None) -> int:
    """Получение или создание чата для пользователя"""
    try:
        with get_cursor() as cursor:
            # Проверяем существует ли чат
            cursor.execute('SELECT id FROM chats WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()

            if result:
                return result[0]

            # Создаем новый чат
            cursor.execute('''
                    INSERT INTO chats (user_id, user_name, chat_status)
                    VALUES (?, ?, 'active')
                    ''', (user_id, user_name or f'User {user_id}'))

            chat_id = cursor.lastrowid
            return chat_id

    except Exception as e:
        logger.error(f"Ошибка создания/получения чата для {user_id}: {e}")
        return 0

def save_menu_snapshot(menu_data_json: str, items_count: int, change_percent: float, is_significant: bool) -> bool:
    """Сохранение снимка меню в БД"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            INSERT INTO menu_snapshots (menu_data, items_count, change_percent, is_significant)
            VALUES (?, ?, ?, ?)
            ''', (menu_data_json, items_count, change_percent, 1 if is_significant else 0))
            return True
    except Exception as e:
        logger.error(f"Ошибка сохранения снимка меню: {e}")
        return False

def get_last_menu_snapshot() -> Optional[Dict]:
    """Получение последнего снимка меню"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT id, version_date, items_count, menu_data, change_percent, is_significant
            FROM menu_snapshots
            ORDER BY id DESC
            LIMIT 1
            ''')
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'version_date': row[1],
                    'items_count': row[2],
                    'menu_data': row[3],
                    'change_percent': row[4],
                    'is_significant': bool(row[5])
                }
            return None
    except Exception as e:
        logger.error(f"Ошибка получения последнего снимка меню: {e}")
        return None

def get_significant_menu_changes(days: int = 30) -> List[Dict]:
    """Получение значимых изменений меню за период"""
    try:
        # SQLite modifier for days
        date_modifier = f'-{days} days'
        with get_cursor() as cursor:
            cursor.execute(f'''
            SELECT id, version_date, items_count, change_percent
            FROM menu_snapshots
            WHERE is_significant = 1 AND version_date >= datetime('now', ?)
            ORDER BY version_date DESC
            ''', (date_modifier,))
            
            rows = cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'version_date': row[1],
                    'items_count': row[2],
                    'change_percent': row[3]
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Ошибка получения изменений меню: {e}")
        return []

def ensure_all_chats_exist() -> None:
    """Гарантирует, что для каждого пользователя создан чат (для миниаппа)"""
    try:
        with get_cursor() as cursor:
            # Оптимизированный запрос: вставляем только отсутствующие чаты одним запросом
            cursor.execute('''
            INSERT INTO chats (user_id, user_name, chat_status)
            SELECT user_id, COALESCE(full_name, 'User ' || user_id), 'active'
            FROM users u
            WHERE NOT EXISTS (SELECT 1 FROM chats c WHERE c.user_id = u.user_id)
            ''')
            
            if cursor.rowcount > 0:
                logger.info(f"Создано новых чатов: {cursor.rowcount}")
                
    except Exception as e:
        logger.error(f"Ошибка при создании чатов для всех пользователей: {e}")

def save_chat_message(chat_id: int, sender: str, message_text: str, file_path: str = None) -> bool:
    """Сохранение сообщения в чат"""
    try:
        with get_cursor() as cursor:
            # Сообщения от админа сохраняем как неотправленные (sent=0)
            # Сообщения от пользователей уже отправлены (sent=1)
            sent_status = 0 if sender == 'admin' else 1

            cursor.execute('''
            INSERT INTO chat_messages (chat_id, sender, message_text, file_path, sent)
            VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, sender, message_text, file_path, sent_status))

            # Обновляем последнее сообщение и время в чате
            cursor.execute('''
            UPDATE chats
            SET last_message = ?, last_message_time = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', (message_text[:100], chat_id))  # Ограничиваем длину последнего сообщения

            return True
    except Exception as e:
        logger.error(f"Ошибка сохранения сообщения в чат {chat_id}: {e}")
        return False

def get_all_chats_for_admin() -> List[Dict[str, Any]]:
    """Получение всех чатов для админ-панели"""
    try:
        # Перед выборкой гарантируем наличие записей чатов для всех пользователей
        ensure_all_chats_exist()
        
        with get_cursor() as cursor:
            # Оптимизированный запрос с JOIN и агрегацией
            cursor.execute('''
            SELECT 
                c.id, 
                c.user_id, 
                COALESCE(u.full_name, c.user_name, 'User ' || c.user_id) as display_name, 
                c.chat_status,
                c.last_message, 
                c.last_message_time, 
                c.created_at,
                COUNT(cm.id) as message_count
            FROM chats c
            LEFT JOIN users u ON c.user_id = u.user_id
            LEFT JOIN chat_messages cm ON c.id = cm.chat_id
            GROUP BY c.id
            ORDER BY c.last_message_time DESC, c.id DESC
            ''')

            chats = cursor.fetchall() or []
            result = []
            
            for chat in chats:
                result.append({
                    'id': chat[0],
                    'user_id': chat[1],
                    'user_name': chat[2],
                    'chat_status': chat[3] or 'active',
                    'last_message': chat[4] or '',
                    'last_message_time': chat[5],
                    'created_at': chat[6],
                    'message_count': chat[7]
                })
            
            logger.info(f"Найдено чатов для админки: {len(result)}")
            return result
            
    except Exception as e:
        logger.error(f"Ошибка получения чатов: {e}")
        return []

def get_chat_by_id(chat_id: int) -> Optional[Dict[str, Any]]:
    """Получение информации о чате по ID"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT c.id, c.user_id, c.user_name, c.chat_status,
                   c.last_message, c.last_message_time, c.created_at,
                   COUNT(cm.id) as message_count
            FROM chats c
            LEFT JOIN chat_messages cm ON c.id = cm.chat_id
            WHERE c.id = ?
            GROUP BY c.id
            ''', (chat_id,))

            result = cursor.fetchone()
            if result:
                return {
                    'id': result[0],
                    'user_id': result[1],
                    'user_name': result[2] or f'User {result[1]}',
                    'chat_status': result[3],
                    'last_message': result[4] or '',
                    'last_message_time': result[5],
                    'created_at': result[6],
                    'message_count': result[7]
                }
            return None
    except Exception as e:
        logger.error(f"Ошибка получения чата {chat_id}: {e}")
        return None

def get_chat_messages(chat_id: int, limit: int = 50, filter_type: str = 'all') -> List[Dict[str, Any]]:
    """
    Получение сообщений чата
    filter_type: 'all', 'messages' (exclude CMD:), 'actions' (only CMD:)
    """
    try:
        with get_cursor() as cursor:
            # Проверяем, есть ли поле sent в таблице
            cursor.execute("PRAGMA table_info(chat_messages)")
            columns = cursor.fetchall()
            has_sent_column = any(col[1] == 'sent' for col in columns)

            query = '''
            SELECT id, sender, message_text, message_time''' + (', sent' if has_sent_column else '') + '''
            FROM chat_messages
            WHERE chat_id = ?
            '''
            params = [chat_id]

            if filter_type == 'messages':
                query += " AND message_text NOT LIKE 'CMD:%'"
            elif filter_type == 'actions':
                query += " AND message_text LIKE 'CMD:%'"

            query += '''
            ORDER BY message_time DESC
            LIMIT ?
            '''
            params.append(limit)

            cursor.execute(query, params)
            results = cursor.fetchall() or []
            # Reverse to show chronological order
            results.reverse()
            
            return [
                {
                    'id': row[0],
                    'sender': row[1],
                    'text': row[2],
                    'time': row[3],
                    'sent': bool(row[4]) if has_sent_column and len(row) > 4 else False
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Ошибка получения сообщений чата {chat_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Ошибка получения сообщений чата {chat_id}: {e}")
        return []

def get_recent_chat_messages(chat_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """Получение последних сообщений чата в обратном порядке (новые сначала)"""
    try:
        with get_cursor() as cursor:
            # Проверяем, есть ли поле sent в таблице
            cursor.execute("PRAGMA table_info(chat_messages)")
            columns = cursor.fetchall()
            has_sent_column = any(col[1] == 'sent' for col in columns)

            if has_sent_column:
                cursor.execute('''
                SELECT id, sender, message_text, message_time, sent
                FROM chat_messages
                WHERE chat_id = ?
                ORDER BY message_time DESC
                LIMIT ?
                ''', (chat_id, limit))

                results = cursor.fetchall() or []
                return [
                    {
                        'id': row[0],
                        'sender': row[1],
                        'message': row[2],
                        'time': row[3],
                        'sent': bool(row[4]) if len(row) > 4 else False
                    }
                    for row in results
                ]
            else:
                # Если поля sent нет, получаем без него
                cursor.execute('''
                SELECT id, sender, message_text, message_time
                FROM chat_messages
                WHERE chat_id = ?
                ORDER BY message_time DESC
                LIMIT ?
                ''', (chat_id, limit))

                results = cursor.fetchall() or []
                return [
                    {
                        'id': row[0],
                        'sender': row[1],
                        'message': row[2],
                        'time': row[3],
                        'sent': False  # По умолчанию считаем не отправленным
                    }
                    for row in results
                ]
    except Exception as e:
        logger.error(f"Ошибка получения последних сообщений чата {chat_id}: {e}")
        return []

def update_chat_status(chat_id: int, status: str) -> bool:
    """Обновление статуса чата"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE chats
            SET chat_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', (status, chat_id))

            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка обновления статуса чата {chat_id}: {e}")
        return False

def get_unsent_admin_messages() -> List[Dict[str, Any]]:
    """Получение неотправленных сообщений от админа"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            SELECT cm.id, cm.chat_id, cm.message_text, cm.message_time, cm.file_path,
                   c.user_id, c.user_name
            FROM chat_messages cm
            JOIN chats c ON cm.chat_id = c.id
            WHERE cm.sender = 'admin' AND (cm.sent IS NULL OR cm.sent = 0)
            ORDER BY cm.message_time ASC
            LIMIT 10
            ''')

            results = cursor.fetchall() or []
            return [
                {
                    'id': row[0],
                    'chat_id': row[1],
                    'message_text': row[2],
                    'message_time': row[3],
                    'file_path': row[4],
                    'user_id': row[5],
                    'user_name': row[6] or f'User {row[5]}'
                }
                for row in results
            ]
    except Exception as e:
        logger.error(f"Ошибка получения неотправленных сообщений: {e}")
        return []

def mark_message_sent(message_id: int) -> bool:
    """Отметить сообщение как отправленное"""
    try:
        with get_cursor() as cursor:
            cursor.execute('''
            UPDATE chat_messages
            SET sent = 1
            WHERE id = ?
            ''', (message_id,))

            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка отметки сообщения {message_id} как отправленного: {e}")
        return False

def get_chat_stats() -> Dict[str, Any]:
    """Получение статистики по чатам"""
    try:
        with get_cursor() as cursor:
            # Общая статистика
            cursor.execute('''
            SELECT
                COUNT(*) as total_chats,
                SUM(CASE WHEN chat_status = 'active' THEN 1 ELSE 0 END) as active_chats,
                SUM(CASE WHEN chat_status = 'paused' THEN 1 ELSE 0 END) as paused_chats,
                SUM(CASE WHEN chat_status = 'completed' THEN 1 ELSE 0 END) as completed_chats
            FROM chats
            ''')

            stats = cursor.fetchone()

            # Статистика сообщений
            cursor.execute('''
            SELECT COUNT(*) as total_messages,
                   AVG(message_count) as avg_messages_per_chat
            FROM (
                SELECT COUNT(cm.id) as message_count
                FROM chats c
                LEFT JOIN chat_messages cm ON c.id = cm.chat_id
                GROUP BY c.id
            )
            ''')

            msg_stats = cursor.fetchone()

            return {
                'total_chats': stats[0] or 0,
                'active_chats': stats[1] or 0,
                'paused_chats': stats[2] or 0,
                'completed_chats': stats[3] or 0,
                'total_messages': msg_stats[0] or 0,
                'avg_messages_per_chat': round(msg_stats[1] or 0, 1)
            }
    except Exception as e:
        logger.error(f"Ошибка получения статистики чатов: {e}")
        return {
            'total_chats': 0,
            'active_chats': 0,
            'paused_chats': 0,
            'completed_chats': 0,
            'total_messages': 0,
            'avg_messages_per_chat': 0
        }



def get_user_setting(user_id: int, key: str, default: str = '') -> str:
    """Получение пользовательской настройки из поля age_verified"""
    if key == 'age_verified':
        try:
            with get_cursor() as cursor:
                cursor.execute('SELECT age_verified FROM users WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                return 'true' if result and result[0] else 'false'
        except Exception as e:
            logger.error(f"Ошибка получения настройки возраста для {user_id}: {e}")
            return default
    return default

def update_user_setting(user_id: int, key: str, value: str) -> bool:
    """Обновление пользовательской настройки (только age_verified)"""
    if key == 'age_verified':
        try:
            verified = 1 if value.lower() == 'true' else 0
            with get_cursor() as cursor:
                cursor.execute('''
                UPDATE users
                SET age_verified = ?, last_updated = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''', (verified, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка обновления настройки возраста для {user_id}: {e}")
            return False
    return False

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С ГЕНЕРАЦИЯМИ ПЕРСОНАЖЕЙ =====

def save_character_generation(user_id: int, character_name: str, dish_name: str = None, prompt: str = None, image_url: str = None, ref_paths: List[str] = None) -> bool:
    """Сохранение информации о генерации персонажа"""
    try:
        with get_cursor() as cursor:
            # Сохраняем основную информацию о генерации
            cursor.execute('''INSERT INTO character_generations
                (user_id, character_name, dish_name, prompt, image_url, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, character_name, dish_name, prompt, image_url))

            generation_id = cursor.lastrowid

            # Сохраняем пути к референсам если есть
            if ref_paths:
                for ref_path in ref_paths:
                    cursor.execute('''INSERT INTO character_refs
                        (generation_id, ref_path, created_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    ''', (generation_id, ref_path))

            logger.info(f"Генерация персонажа '{character_name}' сохранена в БД для пользователя {user_id}")
            return True

    except Exception as e:
        logger.error(f"Ошибка сохранения генерации персонажа: {e}")
        return False

# Синонимы для обратной совместимости
log_action = fast_log_action
add_user = add_or_update_user

# Инициализируем базу данных при импорте
init_database()

print("database.py: База данных с системой адресов и промокодов загружена!")
