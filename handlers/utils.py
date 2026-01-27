"""
handlers/utils.py
Общие утилиты и вспомогательные функции
"""

from aiogram import types
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramBadRequest
import asyncio
import aiohttp
import logging
from typing import Optional
import database
import config
import cache_manager
from datetime import datetime
from functools import wraps
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Dict, Any, Awaitable
from contextlib import asynccontextmanager

# Функция для очистки номера телефона для tel: ссылки
def clean_phone_for_link(phone):
    """Очищает номер телефона для использования в tel: ссылке"""
    import re
    if not phone:
        return ""
    
    # Убираем все кроме цифр и плюса
    clean = re.sub(r'[^\d+]', '', phone)
    
    # Преобразуем российские номера
    if clean.startswith('8'):
        clean = '+7' + clean[1:]
    elif clean.startswith('7') and not clean.startswith('+7'):
        clean = '+7' + clean[1:]
    elif not clean.startswith('+'):
        clean = '+7' + clean
    
    return clean

logger = logging.getLogger(__name__)

# Хранилище ID последнего сообщения для каждого пользователя
last_message_ids = {}

# Кэш для быстрых проверок
user_registration_cache = {}
admin_cache = {}

# ===== ДЕКОРАТОРЫ =====

def handler_timeout(timeout_seconds: int = 10):
    """Декоратор для установки таймаута на обработчики"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут {timeout_seconds}с для функции {func.__name__}")
                return None
            except Exception as e:
                logger.error(f"Ошибка в {func.__name__}: {e}")
                return None
        return wrapper
    return decorator

class TimeoutMiddleware(BaseMiddleware):
    """Миддлваре для установки таймаутов на обработчики"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await asyncio.wait_for(handler(event, data), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Таймаут {self.timeout}с для обработчика")
            return None

# ===== УТИЛИТЫ С ЗАЩИТОЙ ОТ ТАЙМАУТОВ =====

async def safe_send_message(bot, chat_id: int, text: str, **kwargs) -> Optional[types.Message]:
    """Безопасная отправка сообщения с повторными попытками"""
    logger.info(f"📤 Отправка сообщения пользователю {chat_id} (len={len(text)})")
    for attempt in range(config.MAX_RETRIES):
        try:
            async with asyncio.timeout(config.MESSAGE_TIMEOUT):
                msg = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
                logger.info(f"✅ Сообщение отправлено пользователю {chat_id} (msg_id={msg.message_id})")
                return msg
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Таймаут отправки сообщения пользователю {chat_id} (попытка {attempt + 1})")
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"❌ ФИНАЛЬНЫЙ Таймаут при отправке сообщения пользователю {chat_id}")
                return None
            await asyncio.sleep(config.RETRY_DELAY)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            continue
        except (TelegramNetworkError, aiohttp.ClientError, aiohttp.ClientOSError, OSError) as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Сетевая ошибка для пользователя {chat_id}: {e}")
                return None
            logger.warning(f"Попытка {attempt + 1}/{config.MAX_RETRIES} отправки сообщения пользователю {chat_id}: {e}")
            await asyncio.sleep(config.RETRY_DELAY * (attempt + 1))  # Увеличиваем задержку с каждой попыткой
        except Exception as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Ошибка отправки пользователю {chat_id}: {e}")
                return None
            await asyncio.sleep(config.RETRY_DELAY)
    return None

async def safe_send_photo(bot, chat_id: int, photo, **kwargs) -> Optional[types.Message]:
    """Безопасная отправка фото с повторными попытками"""
    for attempt in range(config.MAX_RETRIES):
        try:
            async with asyncio.timeout(config.MESSAGE_TIMEOUT * 2):  # Больше времени для файлов
                return await bot.send_photo(chat_id=chat_id, photo=photo, **kwargs)
        except asyncio.TimeoutError:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Таймаут при отправке фото пользователю {chat_id}")
                return None
            await asyncio.sleep(config.RETRY_DELAY)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            continue
        except (TelegramNetworkError, aiohttp.ClientError, aiohttp.ClientOSError, OSError) as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Сетевая ошибка при отправке фото пользователю {chat_id}: {e}")
                return None
            logger.warning(f"Попытка {attempt + 1}/{config.MAX_RETRIES} отправки фото пользователю {chat_id}: {e}")
            await asyncio.sleep(config.RETRY_DELAY * (attempt + 1))
        except Exception as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Ошибка отправки фото пользователю {chat_id}: {e}")
                return None
            await asyncio.sleep(config.RETRY_DELAY)
    return None

async def safe_send_document(bot, chat_id: int, document, **kwargs) -> Optional[types.Message]:
    """Безопасная отправка документа с повторными попытками"""
    for attempt in range(config.MAX_RETRIES):
        try:
            async with asyncio.timeout(config.MESSAGE_TIMEOUT * 3):  # Еще больше времени для документов
                return await bot.send_document(chat_id=chat_id, document=document, **kwargs)
        except asyncio.TimeoutError:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Таймаут при отправке документа пользователю {chat_id}")
                return None
            await asyncio.sleep(config.RETRY_DELAY)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            continue
        except (TelegramNetworkError, aiohttp.ClientError, aiohttp.ClientOSError, OSError) as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Сетевая ошибка при отправке документа пользователю {chat_id}: {e}")
                return None
            logger.warning(f"Попытка {attempt + 1}/{config.MAX_RETRIES} отправки документа пользователю {chat_id}: {e}")
            await asyncio.sleep(config.RETRY_DELAY * (attempt + 1))
        except Exception as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Ошибка отправки документа пользователю {chat_id}: {e}")
                return None
            await asyncio.sleep(config.RETRY_DELAY)
    return None

async def safe_edit_message(bot, chat_id: int, message_id: int, text: str, **kwargs) -> bool:
    """Безопасное редактирование сообщения"""
    for attempt in range(config.MAX_RETRIES):
        try:
            async with asyncio.timeout(config.MESSAGE_TIMEOUT):
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    **kwargs  # ← передаем все параметры включая disable_web_page_preview
                )
                return True
        except asyncio.TimeoutError:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Таймаут при редактировании сообщения {message_id} пользователя {chat_id}")
                return False
            await asyncio.sleep(config.RETRY_DELAY)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            continue
        except TelegramBadRequest as e:
            error_str = str(e)
            if "message is not modified" in error_str:
                return True
            elif "message to edit not found" in error_str:
                if chat_id in last_message_ids and last_message_ids[chat_id] == message_id:
                    del last_message_ids[chat_id]
                return False
            else:
                return False
        except (TelegramNetworkError, aiohttp.ClientError, aiohttp.ClientOSError, OSError) as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Сетевая ошибка при редактировании сообщения {message_id}: {e}")
                return False
            logger.warning(f"Попытка {attempt + 1}/{config.MAX_RETRIES} редактирования сообщения {message_id}: {e}")
            await asyncio.sleep(config.RETRY_DELAY * (attempt + 1))  # Увеличиваем задержку с каждой попыткой
        except Exception as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Ошибка редактирования сообщения {message_id}: {e}")
                return False
            await asyncio.sleep(config.RETRY_DELAY)
    return False

async def safe_delete_message(bot, chat_id: int, message_id: int) -> bool:
    """Безопасное удаление сообщения"""
    try:
        async with asyncio.timeout(5):
            await bot.delete_message(chat_id, message_id)
            return True
    except Exception:
        return False

async def update_message(user_id: int, text: str, reply_markup=None, parse_mode="HTML", bot=None):
    """Обновляет существующее сообщение или отправляет новое если нет"""
    if bot is None:
        return None
    if is_admin_fast(user_id):
        new_message = await safe_send_message(
            bot=bot,
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        if new_message:
            last_message_ids[user_id] = new_message.message_id
            return new_message.message_id
        return None

    message_id = last_message_ids.get(user_id)
    
    if message_id:
        # Пытаемся отредактировать существующее сообщение
        success = await safe_edit_message(
            bot=bot,
            chat_id=user_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        
        if success:
            return message_id
    
    # Отправляем новое сообщение
    new_message = await safe_send_message(
        bot=bot,
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    
    if new_message:
        last_message_ids[user_id] = new_message.message_id
        return new_message.message_id
    
    return None

def check_user_registration_fast(user_id: int) -> str:
    """Сверхбыстрая проверка регистрации пользователя с кэшированием"""
    if user_id in user_registration_cache:
        logger.info(f"🔍 КЭШ: Проверка регистрации {user_id} -> {user_registration_cache[user_id]}")
        return user_registration_cache[user_id]
    
    try:
        logger.info(f"🔍 БД: Запрос статуса регистрации для {user_id}...")
        status = database.check_user_registration_fast(user_id)
        logger.info(f"🔍 БД: Результат для {user_id} -> {status}")
        user_registration_cache[user_id] = status
        return status
    except Exception as e:
        logger.error(f"❌ Ошибка проверки регистрации пользователя {user_id}: {e}", exc_info=True)
        return 'not_registered'

def is_admin_fast(user_id: int) -> bool:
    """Быстрая проверка админа с кэшированием"""
    if user_id in admin_cache:
        logger.debug(f"Кэшированная проверка админа {user_id}: {admin_cache[user_id]}")
        return admin_cache[user_id]
    
    try:
        is_admin = database.is_admin(user_id)
        logger.debug(f"Проверка админа {user_id} в БД: {is_admin}")
        admin_cache[user_id] = is_admin
        return is_admin
    except Exception as e:
        logger.error(f"Ошибка проверки админа {user_id}: {e}")
        return False

def clear_user_cache(user_id: int):
    """Очистка кэша пользователя"""
    user_registration_cache.pop(user_id, None)
    admin_cache.pop(user_id, None)
    database.clear_user_cache(user_id)
    cache_key = f"main_menu_{user_id}"
    cache_manager.cache.delete(cache_key)

# ===== УТИЛИТЫ ДЛЯ УВЕДОМЛЕНИЙ =====

async def send_admin_notification(user_id: int, message_text: str, bot):
    """Асинхронная отправка уведомления админам с @username"""
    try:
        # Получаем информацию о пользователе
        try:
            user = await bot.get_chat(user_id)
            username = user.username
            full_name = user.full_name or f"Пользователь {user_id}"
            
            # Формируем упоминание пользователя
            if username:
                user_mention = f"@{username}"
                user_display = f"{user_mention} ({full_name})"
            else:
                user_display = f"Пользователь {full_name} (ID: {user_id})"
                
        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
            user_display = f"Пользователь ID: {user_id}"
        
        # Получаем всех админов
        admins = database.get_all_admins()
        
        notification_text = f"""🔔 <b>Новый запрос от клиента!</b>

👤 <b>Клиент:</b> {user_display}
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}
📱 <b>Действие:</b> {message_text}

💬 <b>Ответить:</b> /reply_{user_id}"""
        
        for admin_id in admins:
            try:
                await safe_send_message(
                    bot, 
                    admin_id, 
                    notification_text, 
                    parse_mode="HTML"
                )
                logger.info(f"Уведомление отправлено админу {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений: {e}")

async def send_order_notification(user_id: int, order_text: str, bot):
    """Асинхронная отправка уведомления о заказе админам"""
    try:
        # Получаем информацию о пользователе
        try:
            user = await bot.get_chat(user_id)
            username = user.username
            full_name = user.full_name or f"Пользователь {user_id}"
            
            # Формируем упоминание пользователя
            if username:
                user_mention = f"@{username}"
                user_display = f"{user_mention} ({full_name})"
            else:
                user_display = f"Пользователь ID: {user_id}"
                
        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
            user_display = f"Пользователь ID: {user_id}"
        
        # Получаем данные пользователя из БД
        user_data = database.get_user_data(user_id)
        user_phone = user_data.get('phone', 'Не указан') if user_data else 'Не указан'
        
        # Получаем всех админов
        all_users = database.get_all_users()
        admins = [user[0] for user in all_users if database.is_admin(user[0])]
        
        notification_text = f"""🍽️ <b>НОВЫЙ ЗАКАЗ!</b>

👤 <b>Клиент:</b> {user_display}
📱 <b>Телефон:</b> <a href="tel:{clean_phone_for_link(user_phone)}">{user_phone}</a>
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}

<b>Заказ:</b>
{order_text[:500]}{'...' if len(order_text) > 500 else ''}

💬 <b>Ответить:</b> /reply_{user_id}
📞 <b>Позвонить:</b> /call_{user_id}"""
        
        for admin_id in admins:
            try:
                await safe_send_message(
                    bot, 
                    admin_id, 
                    notification_text, 
                    parse_mode="HTML"
                )
                logger.info(f"Уведомление о заказе отправлено админу {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о заказе админу {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений о заказе: {e}")

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С ОПЕРАТОРОМ =====

# Хранилище для чатов с оператором
operator_chats = {}  # {user_id: {'active': bool, 'expires_at': timestamp}}
operator_notifications = {}  # {user_id: {admin_id: message_id}}
assigned_operators = {}  # {user_id: admin_id}

def set_operator_chat(user_id: int, active: bool, ttl: int = 3600):
    """Установка режима чата с оператором"""
    import time
    if active:
        operator_chats[user_id] = {
            'active': True,
            'expires_at': time.time() + ttl
        }
    else:
        operator_chats.pop(user_id, None)

def is_operator_chat(user_id: int) -> bool:
    """Проверка активности чата с оператором"""
    import time
    if user_id not in operator_chats:
        return False
    
    chat_info = operator_chats[user_id]
    if time.time() > chat_info.get('expires_at', 0):
        operator_chats.pop(user_id, None)
        return False
    
    return chat_info.get('active', False)

def clear_operator_chat(user_id: int):
    """Очистка чата с оператором"""
    operator_chats.pop(user_id, None)
    operator_notifications.pop(user_id, None)
    assigned_operators.pop(user_id, None)

def set_operator_notifications(user_id: int, notifications: dict):
    """Сохранение ID уведомлений для удаления"""
    operator_notifications[user_id] = notifications

def get_operator_notifications(user_id: int) -> dict:
    """Получение ID уведомлений"""
    return operator_notifications.get(user_id, {})

def get_assigned_operator(user_id: int) -> Optional[int]:
    """Получение назначенного оператора"""
    return assigned_operators.get(user_id)

def clear_operator_notifications(user_id: int):
    """Очистка уведомлений оператора"""
    operator_notifications.pop(user_id, None)

# ===== ИНДИКАТОР "ПЕЧАТАЕТ..." =====

@asynccontextmanager
async def typing_indicator(bot, chat_id: int):
    """Контекстный менеджер для показа индикатора 'Печатает...'"""
    typing_task = None
    try:
        async def keep_typing():
            while True:
                try:
                    await bot.send_chat_action(chat_id, "typing")
                    await asyncio.sleep(5)
                except Exception:
                    break
        
        typing_task = asyncio.create_task(keep_typing())
        yield
    finally:
        if typing_task:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
