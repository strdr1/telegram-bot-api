"""
handlers.py
Все обработчики с защитой от таймаутов и оптимизациями
"""

from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramBadRequest
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
import keyboards
import database
import services
import config
import re
from datetime import datetime
import asyncio
import cache_manager
import aiohttp
import logging
from typing import Optional

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

# Хранилище ID последнего сообщения для каждого пользователя
last_message_ids = {}

# Кэш для быстрых проверок
user_registration_cache = {}
admin_cache = {}

# Состояния
class BookingStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_name = State()
    waiting_for_callback = State()
    waiting_faq_question = State()
    waiting_faq_answer = State()
    editing_setting = State()
    editing_review = State()
    editing_faq = State()

class AdminStates(StatesGroup):
    waiting_password = State()
    waiting_newsletter_text = State()
    waiting_newsletter_photo = State()

class OrderStates(StatesGroup):
    waiting_for_order_details = State()
    waiting_for_delivery_address = State()
    waiting_for_order_phone = State()

# ===== УТИЛИТЫ С ЗАЩИТОЙ ОТ ТАЙМАУТОВ =====

async def safe_send_message(bot, chat_id: int, text: str, **kwargs) -> Optional[types.Message]:
    """Безопасная отправка сообщения с повторными попытками"""
    for attempt in range(config.MAX_RETRIES):
        try:
            async with asyncio.timeout(config.MESSAGE_TIMEOUT):
                return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except asyncio.TimeoutError:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Таймаут при отправке сообщения пользователю {chat_id}")
                return None
            await asyncio.sleep(config.RETRY_DELAY)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            continue
        except (TelegramNetworkError, aiohttp.ClientError) as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Сетевая ошибка для пользователя {chat_id}: {e}")
                return None
            await asyncio.sleep(config.RETRY_DELAY)
        except Exception as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Ошибка отправки пользователю {chat_id}: {e}")
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
                    **kwargs
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
            # Игнорируем ошибки "message not modified" и "message not found"
            error_str = str(e)
            if "message is not modified" in error_str:
                return True
            elif "message to edit not found" in error_str:
                if chat_id in last_message_ids and last_message_ids[chat_id] == message_id:
                    del last_message_ids[chat_id]
                return False
            else:
                return False
        except (TelegramNetworkError, aiohttp.ClientError) as e:
            if attempt == config.MAX_RETRIES - 1:
                logger.error(f"Сетевая ошибка при редактировании сообщения {message_id}: {e}")
                return False
            await asyncio.sleep(config.RETRY_DELAY)
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
async def admin_newsletter_handler(user_id: int, bot):
    """Обработчик меню рассылок"""
    if not is_admin_fast(user_id):
        return
    
    pending_newsletters = database.get_pending_newsletters()
    
    text = "📢 <b>Управление рассылками</b>\n\n"
    
    if pending_newsletters:
        text += f"<b>Ожидающих рассылок:</b> {len(pending_newsletters)}\n"
        text += "<i>Последняя ожидающая рассылка:</i>\n"
        if pending_newsletters[0][1]:  # message_text
            preview = pending_newsletters[0][1][:100] + "..." if len(pending_newsletters[0][1]) > 100 else pending_newsletters[0][1]
            text += f"📝 {preview}\n\n"
    else:
        text += "✅ <b>Нет ожидающих рассылок</b>\n\n"
    
    text += "Выберите действие:"
    
    await update_message(user_id, text,
                        reply_markup=keyboards.newsletter_menu(),
                        parse_mode="HTML",
                        bot=bot)
async def update_message(user_id: int, text: str, reply_markup=None, parse_mode="HTML", bot=None):
    """Обновляет или создает одно сообщение с защитой от таймаутов"""
    if bot is None:
        return None
        
    message_id = last_message_ids.get(user_id)
    
    # Сначала пытаемся отредактировать существующее сообщение
    if message_id:
        success = await safe_edit_message(bot, user_id, message_id, text, 
                                         reply_markup=reply_markup, parse_mode=parse_mode)
        if success:
            return message_id
        # Если редактирование не удалось, очищаем ID
        if user_id in last_message_ids and last_message_ids[user_id] == message_id:
            del last_message_ids[user_id]
    
    # Отправляем новое сообщение
    try:
        new_message = await safe_send_message(bot, user_id, text, 
                                             reply_markup=reply_markup, 
                                             parse_mode=parse_mode)
        
        if new_message:
            # Асинхронно удаляем старое сообщение если есть
            old_message_id = last_message_ids.get(user_id)
            if old_message_id:
                asyncio.create_task(safe_delete_message(bot, user_id, old_message_id))
            
            # Сохраняем ID нового сообщения
            last_message_ids[user_id] = new_message.message_id
            return new_message.message_id
    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении сообщения пользователю {user_id}: {e}")
        try:
            # Пытаемся отправить простой текст
            simple_text = text.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
            new_message = await safe_send_message(bot, user_id, simple_text, reply_markup=reply_markup)
            if new_message:
                old_message_id = last_message_ids.get(user_id)
                if old_message_id:
                    asyncio.create_task(safe_delete_message(bot, user_id, old_message_id))
                last_message_ids[user_id] = new_message.message_id
                return new_message.message_id
        except Exception as e2:
            logger.error(f"Даже простой текст не отправился пользователю {user_id}: {e2}")
    
    return None

def check_user_registration_fast(user_id: int) -> str:
    """Сверхбыстрая проверка регистрации пользователя с кэшированием"""
    if user_id in user_registration_cache:
        return user_registration_cache[user_id]
    
    try:
        status = database.check_user_registration_fast(user_id)
        user_registration_cache[user_id] = status
        return status
    except Exception as e:
        logger.error(f"Ошибка проверки регистрации пользователя {user_id}: {e}")
        return 'not_registered'

def is_admin_fast(user_id: int) -> bool:
    """Быстрая проверка админа с кэшированием"""
    if user_id in admin_cache:
        return admin_cache[user_id]
    
    try:
        is_admin = database.is_admin(user_id)
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

# ===== РЕГИСТРАЦИЯ В 1 СООБЩЕНИЕ =====
async def handle_name_input(message: types.Message, state: FSMContext):
    """Обработка ввода имени пользователя (когда пользователь вводит имя вручную)"""
    user = message.from_user
    text = message.text.strip()
    
    if len(text) < 2:
        await update_message(user.id,
                           "❌ Имя должно содержать хотя бы 2 символа. Пожалуйста, введите ваше имя:",
                           bot=message.bot)
        return
    
    # Получаем телефон из состояния
    data = await state.get_data()
    phone = data.get('phone')
    
    if not phone:
        await update_message(user.id,
                           "❌ Ошибка: телефон не найден. Пожалуйста, начните регистрацию заново.",
                           bot=message.bot)
        await state.clear()
        return
    
    # Сохраняем телефон и имя
    database.update_user_phone(user.id, phone)
    database.update_user_name(user.id, text, accept_agreement=True)
    
    # Логируем
    database.log_action(user.id, "registration_completed", f"name:{text}, phone:{phone[:10]}...")
    
    # Очищаем кэш
    clear_user_cache(user.id)
    
    await update_message(user.id,
                       f"✅ <b>Регистрация завершена!</b>\n\nДобро пожаловать, {text}! 🎉\n\nВаш номер сохранен для быстрых заказов и бронирований.",
                       parse_mode="HTML",
                       bot=message.bot)
    
    await asyncio.sleep(1)
    
    # Проверяем откуда пришла регистрация
    context = data.get('context', 'general')
    
    if context == 'booking':
        await booking_start_handler(user.id, message.bot)
    elif context == 'delivery':
        await menu_delivery_handler(user.id, message.bot)
    else:
        await show_main_menu(user.id, message.bot)
    
    await state.clear()

async def ask_for_registration_phone(user_id: int, bot, context: str = "general"):
    """Запрос телефона для регистрации - ЕДИНСТВЕННОЕ СООБЩЕНИЕ СО ССЫЛКАМИ"""
    restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
    
    if context == "booking":
        text = f"""📞 <b>Для бронирования столика нужен ваш номер телефона</b>

✅ <b>Нажимая "Поделиться номером телефона", вы соглашаетесь:</b>
• <a href="{config.USER_AGREEMENT_URL}">Пользовательским соглашением</a>
• <a href="{config.PRIVACY_POLICY_URL}">Политикой обработки персональных данных</a>

<i>Мы сохраним ваш номер для быстрых бронирований в будущем</i>

Пожалуйста, поделитесь вашим контактом или введите номер вручную:

<b>Формат:</b> +7 XXX XXX XX XX
<b>Пример:</b> +7 912 345 67 89"""
    elif context == "delivery":
        text = f"""📞 <b>Для заказа доставки нужен ваш номер телефона</b>

✅ <b>Нажимая "Поделиться номером телефона", вы соглашаетесь:</b>
• <a href="{config.USER_AGREEMENT_URL}">Пользовательским соглашением</a>
• <a href="{config.PRIVACY_POLICY_URL}">Политикой обработки персональных данных</a>

<i>Мы сохраним ваш номер для быстрых заказов в будущем</i>

Пожалуйста, поделитесь вашим контактом или введите номер вручную:

<b>Формат:</b> +7 XXX XXX XX XX
<b>Пример:</b> +7 912 345 67 89"""
    else:
        text = f"""📱 <b>Регистрация в {restaurant_name}</b>

Для удобного обслуживания нам нужен ваш номер телефона.

✅ <b>Нажимая "Поделиться номером телефона", вы соглашаетесь:</b>
• <a href="{config.USER_AGREEMENT_URL}">Пользовательским соглашением</a>
• <a href="{config.PRIVACY_POLICY_URL}">Политикой обработки персональных данных</a>

<i>Мы сохраним ваш номер для быстрых заказов и бронирований</i>

Пожалуйста, поделитесь вашим контактом или введите номер вручную:

<b>Формат:</b> +7 XXX XXX XX XX
<b>Пример:</b> +7 912 345 67 89"""
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    # ТОЛЬКО ОДИН ВЫЗОВ update_message!
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)
async def show_main_menu(user_id: int, bot):
    """Показать главное меню с кэшированием"""
    cache_key = f"main_menu_{user_id}"
    cached_text = cache_manager.cache.get(cache_key)
    
    if cached_text:
        await update_message(user_id, cached_text, 
                           reply_markup=keyboards.main_menu(), 
                           parse_mode="HTML", 
                           bot=bot)
        return
    
    restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
    start_message = database.get_setting('start_message', config.START_MESSAGE)
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    
    text = f"""🎉 <b>{restaurant_name}</b>

{start_message}

<b>Контакты:</b>
📍 {restaurant_address}
📞 {restaurant_phone}
🕐 {restaurant_hours}"""
    
    cache_manager.cache.set(cache_key, text, ttl=300)
    
    await update_message(user_id, text, 
                        reply_markup=keyboards.main_menu(), 
                        parse_mode="HTML", 
                        bot=bot)

# ===== ОСНОВНЫЕ ОБРАБОТЧИКИ =====

@router.message(CommandStart())
async def start_handler(message: types.Message, state: FSMContext):
    """Быстрый обработчик /start"""
    user = message.from_user
    
    if user.is_bot:
        return
    
    logger.info(f"Получен /start от {user.id} ({user.username or 'нет username'})")
    
    # Быстрое сохранение пользователя
    database.add_user(user.id, user.username, user.full_name)
    database.log_action(user.id, "start")
    
    # НЕ проверяем регистрацию сразу - переносим в меню бронирования и доставки
    await state.clear()
    
    # Всегда показываем главное меню
    await show_main_menu(user.id, message.bot)

@router.message(Command("admin"))
async def admin_command(message: types.Message, state: FSMContext):
    """Команда для входа в админку"""
    user = message.from_user
    
    if user.is_bot:
        return
    
    # Проверяем регистрацию
    registration_status = check_user_registration_fast(user.id)
    if registration_status != 'completed':
        await update_message(user.id,
                           "⚠️ Пожалуйста, завершите регистрацию сначала! Для этого попробуйте забронировать столик или заказать доставку",
                           bot=message.bot)
        return
    
    if is_admin_fast(user.id):
        await show_admin_panel(user.id, message.bot)
    else:
        await update_message(user.id,
                           "🔐 <b>Введите пароль для доступа к админке:</b>",
                           parse_mode="HTML",
                           bot=message.bot)
        await state.set_state(AdminStates.waiting_password)

@router.message(F.contact)
async def handle_contact(message: types.Message, state: FSMContext):
    """Обработка отправленного контакта - РЕГИСТРАЦИЯ С ЗАПРОСОМ ИМЕНИ И ПОДТВЕРЖДЕНИЕМ"""
    user = message.from_user
    
    if not message.contact or not message.contact.phone_number:
        return
    
    phone = message.contact.phone_number
    logger.info(f"Получен контакт от {user.id}: {phone[:10]}...")
    
    # Проверка формата
    phone_regex = r'^\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}$|^\+7\d{10}$|^8\d{10}$|^7\d{10}$'
    
    if not re.match(phone_regex, phone):
        await update_message(user.id,
                           "❌ Неверный формат телефона!\nПожалуйста, введите номер вручную:",
                           bot=message.bot)
        return
    
    # Нормализация
    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone_clean.startswith("8"):
        phone_clean = "+7" + phone_clean[1:]
    elif phone_clean.startswith("7"):
        phone_clean = "+" + phone_clean
    
    # Сохраняем телефон в состоянии
    await state.update_data(phone=phone_clean)
    
    # Определяем контекст (откуда пришел запрос)
    current_state = await state.get_state()
    if current_state == BookingStates.waiting_for_phone.state:
        context = 'booking'
    elif "delivery" in str(current_state):
        context = 'delivery'
    else:
        context = 'general'
    
    await state.update_data(context=context)
    
    # Проверяем, есть ли имя в Telegram
    user_name = user.full_name
    
    if user_name and len(user_name.strip()) >= 2:
        # Есть имя в Telegram - показываем ИМЯ и кнопку подтверждения
        text = f"""👤 <b>Мы получили ваш номер телефона</b>

📱 <b>Телефон:</b> {phone_clean[:4]}***{phone_clean[-3:]} (скрыто для безопасности)
👤 <b>Имя в Telegram:</b> {user_name}

<b>Это ваше имя?</b>"""
        
        await update_message(user.id, text,
                           parse_mode="HTML",
                           bot=message.bot)
        
        # Создаем клавиатуру с кнопками
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=f"✅ Да, я {user_name}", callback_data=f"confirm_name:{user_name}")],
            [types.InlineKeyboardButton(text="✏️ Ввести другое имя", callback_data="enter_different_name")]
        ])
        
        await update_message(user.id, "Подтвердите ваше имя:",
                           reply_markup=keyboard,
                           bot=message.bot)
        
        await state.set_state(BookingStates.waiting_for_name)
    else:
        # Нет имени в Telegram - просто запрашиваем имя
        text = f"""👤 <b>Мы получили ваш номер телефона</b>

📱 <b>Телефон:</b> {phone_clean[:4]}***{phone_clean[-3:]} (скрыто для безопасности)

Теперь, пожалуйста, введите ваше имя:
<i>Как к вам обращаться?</i>"""
        
        await update_message(user.id, text,
                           parse_mode="HTML",
                           bot=message.bot)
        
        await state.set_state(BookingStates.waiting_for_name)

@router.callback_query(F.data.startswith("confirm_name:"))
async def confirm_name_callback(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение имени из Telegram"""
    await callback.answer()
    
    # Извлекаем имя из callback data
    user_name = callback.data.split(":", 1)[1]
    
    # Получаем телефон из состояния
    data = await state.get_data()
    phone = data.get('phone')
    
    if not phone:
        await update_message(callback.from_user.id,
                           "❌ Ошибка: телефон не найден. Пожалуйста, начните регистрацию заново.",
                           bot=callback.bot)
        await state.clear()
        return
    
    # Сохраняем телефон и имя
    database.update_user_phone(callback.from_user.id, phone)
    database.update_user_name(callback.from_user.id, user_name, accept_agreement=True)
    
    # Логируем
    database.log_action(callback.from_user.id, "registration_completed", f"name:{user_name}, phone:{phone[:10]}...")
    
    # Очищаем кэш
    clear_user_cache(callback.from_user.id)
    
    await update_message(callback.from_user.id,
                       f"✅ <b>Регистрация завершена!</b>\n\nДобро пожаловать, {user_name}! 🎉\n\nВаш номер сохранен для быстрых заказов и бронирований.",
                       parse_mode="HTML",
                       bot=callback.bot)
    
    await asyncio.sleep(1)
    
    # Проверяем откуда пришла регистрация
    context = data.get('context', 'general')
    
    if context == 'booking':
        await booking_start_handler(callback.from_user.id, callback.bot)
    elif context == 'delivery':
        await menu_delivery_handler(callback.from_user.id, callback.bot)
    else:
        await show_main_menu(callback.from_user.id, callback.bot)
    
    await state.clear()

@router.callback_query(F.data == "enter_different_name")
async def enter_different_name_callback(callback: types.CallbackQuery, state: FSMContext):
    """Запрос ввода другого имени"""
    await callback.answer()
    
    await update_message(callback.from_user.id,
                       "👤 <b>Введите ваше имя:</b>\n<i>Как к вам обращаться?</i>",
                       parse_mode="HTML",
                       bot=callback.bot)
    await state.set_state(BookingStates.waiting_for_name)
@router.message(AdminStates.waiting_newsletter_photo, F.photo | F.document)
async def handle_newsletter_photo(message: Message, state: FSMContext):
    """Обработка фото для рассылки"""
    user_id = message.from_user.id
    
    if not is_admin_fast(user_id):
        return
    
    photo_id = None
    message_type = 'text'
    
    if message.photo:
        photo_id = message.photo[-1].file_id
        message_type = 'photo'
        photo_info = f"✅ Фото добавлено!\nРазмер: {message.photo[-1].file_size // 1024}KB"
    elif message.document and message.document.mime_type.startswith('image/'):
        photo_id = message.document.file_id
        message_type = 'photo'
        photo_info = f"✅ Фото добавлено!\nТип: {message.document.mime_type}"
    else:
        await update_message(user_id, 
                           "❌ Пожалуйста, отправьте изображение!",
                           bot=message.bot)
        return
    
    data = await state.get_data()
    newsletter_text = data.get('newsletter_text', '')
    
    # Создаем предпросмотр рассылки
    preview_text = f"""📝 <b>ПРЕДПРОСМОТР РАССЫЛКИ</b>

<b>Текст:</b>
{newsletter_text[:200]}{'...' if len(newsletter_text) > 200 else ''}

<b>Тип:</b> {'Фото + текст' if message_type == 'photo' else 'Только текст'}
{photo_info}

<b>Переменные в тексте:</b>
• {{Имя пользователя}} → Иван Иванов
• {{Имя}} → Иван
• {{Дата}} → {datetime.now().strftime('%d.%m.%Y')}

<b>Выберите время отправки:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🕐 Отправить немедленно", callback_data=f"send_now_{message_type}_{'1' if photo_id else '0'}")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 1 час", callback_data=f"schedule_1h_{message_type}_{'1' if photo_id else '0'}")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 3 часа", callback_data=f"schedule_3h_{message_type}_{'1' if photo_id else '0'}")],
        [types.InlineKeyboardButton(text="📅 Запланировать на завтра", callback_data=f"schedule_tomorrow_{message_type}_{'1' if photo_id else '0'}")],
        [types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_text_newsletter")],
        [types.InlineKeyboardButton(text="🔄 Изменить фото", callback_data="add_photo")],
        [types.InlineKeyboardButton(text="🗑️ Отменить", callback_data="admin_newsletter")]
    ])
    
    await update_message(user_id, preview_text, 
                        reply_markup=keyboard, 
                        parse_mode="HTML", 
                        bot=message.bot)
    
    # Сохраняем данные в state для использования в callback
    await state.update_data(
        photo_id=photo_id,
        message_type=message_type,
        final_text=newsletter_text
    )
@router.message(F.text)
async def handle_text_messages(message: types.Message, state: FSMContext):
    """Оптимизированный обработчик текстовых сообщений"""
    user = message.from_user
    text = message.text.strip()
    
    current_state = await state.get_state()
    
    # ===== ОБРАБОТКА ИМЕНИ =====
    if current_state == BookingStates.waiting_for_name.state:
        await handle_name_input(message, state)
        return
    
    # ===== ОБРАБОТКА РУЧНОГО ВВОДА ТЕЛЕФОНА =====
    
    # Проверяем, может быть это телефон (простая проверка)
    phone_regex = r'^\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}$|^\+7\d{10}$|^8\d{10}$|^7\d{10}$'
    
    if re.match(phone_regex, text):
        # Это похоже на телефон
        
        # Нормализация
        phone_clean = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if phone_clean.startswith("8"):
            phone_clean = "+7" + phone_clean[1:]
        elif phone_clean.startswith("7"):
            phone_clean = "+" + phone_clean
        
        # Сохраняем телефон в состоянии
        await state.update_data(phone=phone_clean)
        
        # Проверяем, есть ли имя в Telegram
        user_name = user.full_name
        
        if user_name and len(user_name.strip()) >= 2:
            # Есть имя в Telegram - показываем ИМЯ и кнопку подтверждения
            text_msg = f"""👤 <b>Мы получили ваш номер телефона</b>

📱 <b>Телефон:</b> {phone_clean[:4]}***{phone_clean[-3:]} (скрыто для безопасности)
👤 <b>Имя в Telegram:</b> {user_name}

<b>Это ваше имя?</b>"""
            
            await update_message(user.id, text_msg,
                               parse_mode="HTML",
                               bot=message.bot)
            
            # Создаем клавиатуру с кнопками
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text=f"✅ Да, я {user_name}", callback_data=f"confirm_name:{user_name}")],
                [types.InlineKeyboardButton(text="✏️ Ввести другое имя", callback_data="enter_different_name")]
            ])
            
            await update_message(user.id, "Подтвердите ваше имя:",
                               reply_markup=keyboard,
                               bot=message.bot)
            
            await state.set_state(BookingStates.waiting_for_name)
        else:
            # Нет имени в Telegram - просто запрашиваем имя
            text_msg = f"""👤 <b>Мы получили ваш номер телефона</b>

📱 <b>Телефон:</b> {phone_clean[:4]}***{phone_clean[-3:]} (скрыто для безопасности)

Теперь, пожалуйста, введите ваше имя:
<i>Как к вам обращаться?</i>"""
            
            await update_message(user.id, text_msg,
                               parse_mode="HTML",
                               bot=message.bot)
            
            await state.set_state(BookingStates.waiting_for_name)
        return
    
    # ===== АДМИНСКИЕ СОСТОЯНИЯ =====
    
    # Проверка пароля админа
    elif current_state == AdminStates.waiting_password.state:
        await check_admin_password(message, state)
        return
    
    # Создание FAQ
    elif current_state == BookingStates.waiting_faq_question.state:
        await admin_faq_question_received(message, state)
        return
    
    elif current_state == BookingStates.waiting_faq_answer.state:
        await admin_faq_answer_received(message, state)
        return
    
    # Настройки бота
    elif current_state == BookingStates.editing_setting.state:
        await admin_save_setting(message, state)
        return
    
    # Удаление FAQ
    elif current_state == BookingStates.editing_faq.state:
        await admin_delete_faq_process(message, state)
        return
    
    # Удаление отзыва
    elif current_state == BookingStates.editing_review.state:
        await admin_delete_review_process(message, state)
        return
    
    # ===== РАССЫЛКИ =====
    
    # Текст для рассылки
    elif current_state == AdminStates.waiting_newsletter_text.state:
        await process_newsletter_text(message, state)
        return
    
    # Фото для рассылки (если пользователь отправил текст вместо фото)
    elif current_state == AdminStates.waiting_newsletter_photo.state:
        # Если пользователь в состоянии ожидания фото, но отправляет текст
        if text.lower() in ['отмена', 'cancel', 'назад', 'пропустить']:
            # Если пользователь хочет пропустить фото
            data = await state.get_data()
            newsletter_text = data.get('newsletter_text', '')
            
            # Создаем предпросмотр рассылки без фото
            preview_text = f"""📝 <b>ПРЕДПРОСМОТР РАССЫЛКИ</b>

<b>Текст:</b>
{newsletter_text[:200]}{'...' if len(newsletter_text) > 200 else ''}

<b>Тип:</b> Только текст
ℹ️ Без фото

<b>Переменные в тексте:</b>
• {{Имя пользователя}} → Иван Иванов
• {{Имя}} → Иван
• {{Дата}} → {datetime.now().strftime('%d.%m.%Y')}

<b>Выберите время отправки:</b>"""
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🕐 Отправить немедленно", callback_data="send_now_text_0")],
                [types.InlineKeyboardButton(text="⏰ Отложить на 1 час", callback_data="schedule_1h_text_0")],
                [types.InlineKeyboardButton(text="⏰ Отложить на 3 часа", callback_data="schedule_3h_text_0")],
                [types.InlineKeyboardButton(text="📅 Запланировать на завтра", callback_data="schedule_tomorrow_text_0")],
                [types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_text")],
                [types.InlineKeyboardButton(text="🗑️ Отменить", callback_data="admin_newsletter")]
            ])
            
            await update_message(user.id, preview_text, 
                                reply_markup=keyboard, 
                                parse_mode="HTML", 
                                bot=message.bot)
            
            # Сохраняем данные в state
            await state.update_data(
                photo_id=None,
                message_type='text',
                final_text=newsletter_text
            )
        else:
            await update_message(user.id,
                               "❌ Пожалуйста, отправьте фото или нажмите 'Пропустить' в меню.",
                               bot=message.bot)
        return
    
    # ===== БРОНИРОВАНИЕ =====
    
    # Телефон для бронирования (когда уже в состоянии ожидания телефона)
    elif current_state == BookingStates.waiting_for_phone.state:
        # Это обработка для ручного ввода телефона в состоянии waiting_for_phone
        # (когда пользователь уже нажал "бронирование" и мы ждем телефон)
        phone_regex = r'^\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}$|^\+7\d{10}$|^8\d{10}$|^7\d{10}$'
        
        if not re.match(phone_regex, text):
            await update_message(user.id,
                               "❌ Неверный формат телефона!\nПример: +7 912 345 67 89",
                               bot=message.bot)
            return
        
        phone_clean = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if phone_clean.startswith("8"):
            phone_clean = "+7" + phone_clean[1:]
        elif phone_clean.startswith("7"):
            phone_clean = "+" + phone_clean
        
        # Сохраняем телефон в состоянии
        await state.update_data(phone=phone_clean)
        
        # Проверяем, есть ли имя в Telegram
        user_name = user.full_name
        
        if user_name and len(user_name.strip()) >= 2:
            # Есть имя в Telegram - показываем ИМЯ и кнопку подтверждения
            text_msg = f"""👤 <b>Мы получили ваш номер телефона</b>

📱 <b>Телефон:</b> {phone_clean[:4]}***{phone_clean[-3:]} (скрыто для безопасности)
👤 <b>Имя в Telegram:</b> {user_name}

<b>Это ваше имя?</b>"""
            
            await update_message(user.id, text_msg,
                               parse_mode="HTML",
                               bot=message.bot)
            
            # Создаем клавиатуру с кнопками
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text=f"✅ Да, я {user_name}", callback_data=f"confirm_name:{user_name}")],
                [types.InlineKeyboardButton(text="✏️ Ввести другое имя", callback_data="enter_different_name")]
            ])
            
            await update_message(user.id, "Подтвердите ваше имя:",
                               reply_markup=keyboard,
                               bot=message.bot)
            
            await state.set_state(BookingStates.waiting_for_name)
        else:
            # Нет имени в Telegram - просто запрашиваем имя
            text_msg = f"""👤 <b>Мы получили ваш номер телефона</b>

📱 <b>Телефон:</b> {phone_clean[:4]}***{phone_clean[-3:]} (скрыто для безопасности)

Теперь, пожалуйста, введите ваше имя:
<i>Как к вам обращаться?</i>"""
            
            await update_message(user.id, text_msg,
                               parse_mode="HTML",
                               bot=message.bot)
            
            await state.set_state(BookingStates.waiting_for_name)
        return
    
    # ===== УДАЛЕНИЕ ВСЕХ ОТЗЫВОВ =====
    
    # Специальная команда для удаления всех отзывов
    elif text == "УДАЛИТЬ ВСЕ ОТЗЫВЫ":
        await confirm_delete_all_reviews(message)
        return
    
    # ===== КОМАНДЫ ДЛЯ ОТЛАДКИ =====
    
    elif text == "/debug_state":
        await update_message(user.id,
                           f"<b>Текущее состояние:</b> {current_state}",
                           parse_mode="HTML",
                           bot=message.bot)
        return
    
    elif text == "/clear_state":
        await state.clear()
        await update_message(user.id,
                           "✅ Состояние очищено!",
                           bot=message.bot)
        return
    
    # ===== ОБРАБОТКА ЗАКАЗОВ =====
    
    # Проверяем, если это заказ (простая проверка по наличию ключевых слов)
    order_keywords = ['заказ', 'доставка', 'хочу', 'хотел бы', 'можно', 'пицца', 'бургер', 'салат', 'суп', 'паста']
    if any(keyword in text.lower() for keyword in order_keywords):
        # Проверяем регистрацию
        registration_status = check_user_registration_fast(user.id)
        
        if registration_status == 'completed':
            # Пользователь зарегистрирован - перенаправляем оператору
            text_response = f"""🍽️ <b>Ваш запрос на заказ получен!</b>

<i>"{text}"</i>

Наш оператор свяжется с вами в ближайшее время для подтверждения заказа.

⏳ <b>Ожидайте ответа в течение 5-10 минут</b>"""
            
            await update_message(user.id, text_response,
                                parse_mode="HTML",
                                bot=message.bot)
            
            # Отправляем уведомление админам
            asyncio.create_task(send_order_notification(user.id, text, message.bot))
            return
    
    # ===== ИГНОРИРОВАНИЕ ПРОЧЕГО ТЕКСТА =====
    
    # Игнорируем текст, если пользователь не в специальном состоянии
    restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
    
    text_response = f"""🤖 <b>Используйте кнопки меню для навигации</b>

• Нажмите /start для главного меню
• Используйте кнопки внизу для выбора раздела
• Посмотрите FAQ для частых вопросов

<b>Чтобы зарегистрироваться в {restaurant_name}:</b>
1. Перейдите в раздел "📅 Бронирование столика" или "🚚 Доставка"
2. Нажмите "📱 Поделиться номером телефона"
3. Введите ваше имя
4. Регистрация пройдет автоматически!"""
    
    await update_message(user.id, text_response,
                        parse_mode="HTML",
                        bot=message.bot)
async def send_order_notification(user_id: int, order_text: str, bot):
    """Асинхронная отправка уведомления о заказе админам"""
    try:
        user_data = database.get_user_data(user_id)
        user_name = user_data.get('full_name', f'Пользователь {user_id}') if user_data else f'Пользователь {user_id}'
        user_phone = user_data.get('phone', 'Не указан') if user_data else 'Не указан'
        
        notification_text = f"""🍽️ <b>НОВЫЙ ЗАКАЗ!</b>

👤 <b>Клиент:</b> {user_name}
📱 <b>Телефон:</b> {user_phone}
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}

<b>Заказ:</b>
{order_text[:500]}{'...' if len(order_text) > 500 else ''}

<b>ID пользователя:</b> {user_id}"""
        
        all_users = database.get_all_users()
        admins = [user for user in all_users if database.is_admin(user[0])]
        
        for admin in admins:
            admin_id = admin[0]
            try:
                await safe_send_message(bot, admin_id, notification_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений о заказе: {e}")
@router.message(AdminStates.waiting_password)
async def check_admin_password(message: types.Message, state: FSMContext):
    """Проверка пароля админа"""
    user_id = message.from_user.id
    entered_password = message.text.strip()
    
    if entered_password == config.ADMIN_PASSWORD:
        database.add_admin(user_id)
        admin_cache[user_id] = True
        
        await update_message(user_id, 
                           "✅ <b>Доступ к админке получен!</b>", 
                           parse_mode="HTML",
                           bot=message.bot)
        await asyncio.sleep(1)
        await show_admin_panel(user_id, message.bot)
        await state.clear()
    else:
        await update_message(user_id, 
                           "❌ <b>Неверный пароль!</b> Попробуйте еще раз:", 
                           parse_mode="HTML",
                           bot=message.bot)

# ===== CALLBACK ОБРАБОТЧИКИ =====

@router.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    """Быстрый возврат в главное меню"""
    await callback.answer()
    await show_main_menu(callback.from_user.id, callback.bot)

@router.callback_query(F.data == "menu_food")
async def menu_food_callback(callback: types.CallbackQuery):
    """Быстрое меню ресторана"""
    await callback.answer()
    await menu_food_handler(callback.from_user.id, callback.bot)

async def menu_food_handler(user_id: int, bot):
    """Оптимизированный обработчик меню"""
    database.log_action(user_id, "view_menu")
    
    text = """🍽️ <b>Меню ресторана</b>

Выберите что вас интересует:

<b>Меню доставки</b> — блюда с доставкой на дом
<b>PDF меню с барной картой</b> — полное меню для просмотра
<b>Банкетное меню</b> — для мероприятий и праздников

💡 <i>Совет: Если планируете мероприятие, посмотрите банкетное меню заранее!</i>"""
    
    await update_message(user_id, text,
                        reply_markup=keyboards.food_menu(),
                        parse_mode="HTML",
                        bot=bot)

@router.callback_query(F.data == "booking")
async def booking_callback(callback: types.CallbackQuery):
    """Быстрое бронирование"""
    await callback.answer()
    await booking_start_handler(callback.from_user.id, callback.bot)

async def booking_start_handler(user_id: int, bot, state: FSMContext = None):
    """Оптимизированный обработчик бронирования с проверкой регистрации"""
    database.log_action(user_id, "start_booking")
    
    # Проверяем регистрацию
    registration_status = check_user_registration_fast(user_id)
    
    if registration_status != 'completed':
        # Проверяем есть ли у пользователя имя в базе
        user_data = database.get_user_data(user_id)
        has_name = user_data and user_data.get('full_name')
        
        # ВСЕГДА показываем полную форму регистрации, НЕ показываем короткое сообщение!
        await ask_for_registration_phone(user_id, bot, context="booking")
        
        # Устанавливаем состояние для отслеживания
        if state:
            await state.update_data(context='booking')
            await state.set_state(BookingStates.waiting_for_phone)
        return
    
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    
    text = f"""📅 <b>Бронирование столика</b>

Забронируйте столик онлайн:

1. 📅 Выберите дату
2. 🕐 Выберите время  
3. 👥 Укажите количество гостей
4. 📞 Введите телефон (если не сохранен)
5. ✅ Получите подтверждение

Или по телефону: {restaurant_phone}"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📅 Забронировать столик", callback_data="book_now")],
        [types.InlineKeyboardButton(text="💬 Нужна помощь оператора", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)

@router.callback_query(F.data == "admin_back")
async def admin_back_callback(callback: types.CallbackQuery):
    """Быстрый возврат в админку"""
    await callback.answer()
    await show_admin_panel(callback.from_user.id, callback.bot)

async def show_admin_panel(user_id: int, bot):
    """Быстрая панель администратора"""
    stats = database.get_stats()
    
    text = f"""🛠️ <b>Админ-панель</b>

📊 <b>Статистика за сегодня:</b>
👥 Всего пользователей: {stats['total_users']}
🔥 Активных сегодня: {stats['active_today']}
📅 Броней сегодня: {stats['bookings_today']}
🍽️ Заказов сегодня: {stats['orders_today']}"""
    
    await update_message(user_id, text,
                        reply_markup=keyboards.admin_menu(),
                        parse_mode="HTML",
                        bot=bot)

@router.callback_query(F.data == "contact_us")
async def contact_us_callback(callback: types.CallbackQuery):
    """Быстрая связь с менеджером"""
    await callback.answer()
    
    user_id = callback.from_user.id
    user_name = callback.from_user.full_name or f"Пользователь {user_id}"
    
    text = """📞 <b>Связаться с менеджером</b>

Ваш запрос отправлен менеджеру!
Он свяжется с вами в ближайшее время.

⏳ <i>Ожидайте ответа в течение 5-10 минут</i>"""
    
    await update_message(user_id, text,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    # Асинхронная отправка уведомлений админам
    asyncio.create_task(send_admin_notification(user_id, user_name, callback.bot))

async def send_admin_notification(user_id: int, user_name: str, bot):
    """Асинхронная отправка уведомления админам"""
    try:
        all_users = database.get_all_users()
        admins = [user for user in all_users if database.is_admin(user[0])]
        
        notification_text = f"""🔔 <b>Новый запрос от клиента!</b>

👤 <b>Клиент:</b> {user_name} (ID: {user_id})
🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}
📱 <b>Действие:</b> Запрос связи с менеджером"""
        
        for admin in admins:
            admin_id = admin[0]
            try:
                await safe_send_message(bot, admin_id, notification_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений: {e}")

# ===== FAQ ОБРАБОТЧИКИ =====

@router.callback_query(F.data == "faq")
async def faq_callback(callback: types.CallbackQuery):
    """Быстрые FAQ"""
    await callback.answer()
    database.log_action(callback.from_user.id, "view_faq")
    
    # Кэшируем FAQ
    cache_key = "faq_list"
    faq_list = cache_manager.cache.get(cache_key)
    
    if faq_list is None:
        faq_list = database.get_faq()
        cache_manager.cache.set(cache_key, faq_list, ttl=600)  # 10 минут
    
    if not faq_list:
        text = "❓ <b>Частые вопросы</b>\n\nВопросов пока нет.\n\n<b>Не нашли ответ?</b> Нажмите '📞 Связаться с нами'!"
    else:
        text = "❓ <b>Частые вопросы</b>\n\n<b>Выберите вопрос:</b>\n"
        for faq_id, question, answer in faq_list:
            text += f"• {question}\n"
        
        text += "\n<b>Не нашли ответ?</b> Нажмите '📞 Связаться с нами'!"
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboards.faq_menu(faq_list),
                        parse_mode="HTML",
                        bot=callback.bot)

# ===== АДМИН ПАНЕЛЬ =====

@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: types.CallbackQuery):
    """Быстрая статистика"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    stats = database.get_stats()
    
    text = f"""📊 <b>Статистика</b>

👥 Всего пользователей: {stats['total_users']}
🔥 Активных сегодня: {stats['active_today']}
📅 Броней сегодня: {stats['bookings_today']}
🍽️ Заказов сегодня: {stats['orders_today']}"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "parse_reviews")
async def parse_reviews_callback(callback: types.CallbackQuery):
    """Парсинг отзывов без таймаута"""
    await callback.answer("⏳ Начинаем парсинг...", show_alert=False)
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    user_id = callback.from_user.id
    
    await update_message(
        user_id,
        "🔄 <b>Парсим отзывы с Яндекс Карт...</b>\n\nЭто может занять до 30 секунд.",
        parse_mode="HTML",
        bot=callback.bot
    )
    
    # Асинхронный парсинг БЕЗ таймаута
    asyncio.create_task(parse_reviews_task_safe(user_id, callback.bot))

async def parse_reviews_task_safe(user_id: int, bot):
    """Асинхронная задача парсинга"""
    try:
        reviews = await services.parse_yandex_reviews_fast()
        
        count = 0
        added_reviews = []
        
        for review in reviews:
            if review['text'] and len(review['text']) > 20:
                success = database.save_review(**review)
                if success:
                    count += 1
                    added_reviews.append(review['author'])
        
        if count > 0:
            text = f"✅ <b>Парсинг завершен успешно!</b>\n\n📊 Результаты:\n• Добавлено отзывов: {count}"
            if added_reviews:
                text += f"\n• Первые авторы: {', '.join(added_reviews[:3])}{'...' if len(added_reviews) > 3 else ''}"
        else:
            text = "ℹ️ <b>Парсинг завершен</b>\n\nНе найдено новых отзывов для добавления."
        
        # Добавляем кнопку "Назад"
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="👁️ Посмотреть все отзывы", callback_data="admin_view_reviews")],
            [types.InlineKeyboardButton(text="🔄 Спарсить еще раз", callback_data="parse_reviews")],
            [types.InlineKeyboardButton(text="⬅️ Назад к отзывам", callback_data="admin_reviews")]
        ])
        
        await update_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка парсинга: {error_msg}")
        
        if "timeout" in str(e).lower():
            error_text = "⏳ <b>Парсинг занял слишком много времени</b>\n\nПопробуйте позже."
        elif "connection" in str(e).lower():
            error_text = "🔌 <b>Ошибка соединения</b>\n\nПроверьте интернет-соединение."
        else:
            error_text = f"❌ <b>Ошибка:</b> {error_msg[:100]}..."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="parse_reviews")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_reviews")]
        ])
        
        await update_message(
            user_id,
            error_text,
            reply_markup=keyboard,
            parse_mode="HTML",
            bot=bot
        )

async def parse_reviews_task(user_id: int, bot):
    """Асинхронная задача парсинга"""
    try:
        async with asyncio.timeout(config.PARSE_TIMEOUT):
            reviews = await services.parse_yandex_reviews_fast()
        
        count = 0
        for review in reviews:
            if review['text'] and len(review['text']) > 20:
                database.save_review(**review)
                count += 1
        
        text = f"✅ <b>Парсинг завершен!</b>\n\nДобавлено отзывов: {count}"
        
        await update_message(user_id, text,
                            parse_mode="HTML",
                            bot=bot)
        
    except asyncio.TimeoutError:
        await update_message(
            user_id,
            "❌ <b>Таймаут парсинга!</b>\n\nНе удалось получить отзывы за отведенное время.",
            parse_mode="HTML",
            bot=bot
        )
    except Exception as e:
        error_msg = str(e)[:100]
        await update_message(
            user_id,
            f"❌ <b>Ошибка парсинга!</b>\n\n{error_msg}",
            parse_mode="HTML",
            bot=bot
        )

# ===== ОБРАБОТЧИКИ ДЛЯ ОТЗЫВОВ В АДМИНКЕ =====

@router.callback_query(F.data == "admin_view_reviews")
async def admin_view_reviews_callback(callback: types.CallbackQuery):
    """Просмотр всех отзывов в админке - САМЫЕ СВЕЖИЕ ПЕРВЫМИ"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    reviews = database.get_all_reviews()
    
    if not reviews:
        text = "⭐ <b>Все отзывы</b>\n\n❌ Отзывов пока нет в базе данных."
    else:
        text = f"⭐ <b>Все отзывы</b>\n\n<b>Всего отзывов:</b> {len(reviews)}\n\n<b>Самые свежие:</b>\n"
        
        # Показываем первые 5 самых свежих отзывов
        for i, review in enumerate(reviews[:5], 1):
            try:
                review_dict = dict(review)
                author = review_dict.get('author', 'Неизвестный')
                rating = review_dict.get('rating', 5)
                text_review = review_dict.get('text', '')
                date = review_dict.get('date', '') or review_dict.get('created_at', '')[:10]
                review_id = review_dict.get('id', 'N/A')
                
                stars = "⭐" * min(int(rating) if isinstance(rating, (int, str)) and str(rating).isdigit() else 5, 5)
                preview = text_review[:80] + "..." if len(text_review) > 80 else text_review
                
                # Форматируем дату
                date_display = ""
                if date:
                    try:
                        if "-" in date:
                            year, month, day = date.split("-")
                            date_display = f" ({day}.{month}.{year})"
                        else:
                            date_display = f" ({date})"
                    except:
                        date_display = f" ({date})"
                
                text += f"<b>ID: {review_id}</b> - {author}{date_display} {stars}\n"
                text += f"{preview}\n\n"
            except:
                continue
        
        if len(reviews) > 5:
            text += f"<i>... и еще {len(reviews) - 5} отзывов</i>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🗑️ Удалить один отзыв", callback_data="admin_delete_review_start")],
        [types.InlineKeyboardButton(text="🔄 Спарсить новые отзывы", callback_data="parse_reviews")],
        [types.InlineKeyboardButton(text="⬅️ Назад к отзывам", callback_data="admin_reviews")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_delete_review_start")
async def admin_delete_review_start_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало удаления одного отзыва"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    reviews = database.get_all_reviews()
    
    if not reviews:
        text = "🗑️ <b>Удаление отзыва</b>\n\n❌ Нет отзывов для удаления."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Спарсить отзывы", callback_data="parse_reviews")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_reviews")]
        ])
    else:
        text = "🗑️ <b>Удаление отзыва</b>\n\nВведите ID отзыва для удаления:\n\n<b>Последние отзывы:</b>\n"
        
        # Показываем последние 3 отзыва для справки
        for i, review in enumerate(reviews[:3], 1):
            try:
                review_dict = dict(review)
                author = review_dict.get('author', 'Неизвестный')
                review_id = review_dict.get('id', 'N/A')
                text_review = review_dict.get('text', '')
                
                preview = text_review[:50] + "..." if len(text_review) > 50 else text_review
                text += f"<b>ID {review_id}:</b> {author} - {preview}\n"
            except:
                continue
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_reviews")]
        ])
    
    await update_message(callback.from_user.id, text,
                       reply_markup=keyboard,
                       parse_mode="HTML",
                       bot=callback.bot)
    
    await state.set_state(BookingStates.editing_review)

async def admin_delete_review_process(message: types.Message, state: FSMContext):
    """Обработка удаления отзыва"""
    if not is_admin_fast(message.from_user.id):
        return
    
    try:
        review_id = int(message.text.strip())
        
        # Пробуем удалить отзыв
        success = database.delete_review(review_id)
        
        if success:
            text = f"✅ Отзыв с ID {review_id} успешно удален!"
        else:
            text = f"❌ Не удалось удалить отзыв с ID {review_id}. Проверьте правильность ID."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🗑️ Удалить еще отзыв", callback_data="admin_delete_review_start")],
            [types.InlineKeyboardButton(text="👁️ Посмотреть все отзывы", callback_data="admin_view_reviews")],
            [types.InlineKeyboardButton(text="⬅️ Назад к отзывам", callback_data="admin_reviews")]
        ])
        
        await update_message(message.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)
        
    except ValueError:
        text = "❌ Пожалуйста, введите числовой ID отзыва."
        await update_message(message.from_user.id, text,
                           bot=message.bot)
        return
    
    await state.clear()

@router.callback_query(F.data == "admin_delete_all_reviews")
async def admin_delete_all_reviews_callback(callback: types.CallbackQuery):
    """Удаление всех отзывов"""
    await callback.answer("⚠️ Вы уверены?", show_alert=True)
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = """💣 <b>Удаление всех отзывов</b>

⚠️ <b>ВНИМАНИЕ!</b> Это действие удалит ВСЕ отзывы из базы данных!
Данное действие необратимо.

Для подтверждения удаления всех отзывов введите: <code>УДАЛИТЬ ВСЕ ОТЗЫВЫ</code>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_reviews")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.message(F.text == "УДАЛИТЬ ВСЕ ОТЗЫВЫ")
async def confirm_delete_all_reviews(message: types.Message):
    """Подтверждение удаления всех отзывов"""
    if not is_admin_fast(message.from_user.id):
        return
    
    deleted_count = database.delete_all_reviews()
    
    if deleted_count > 0:
        text = f"✅ Удалено {deleted_count} отзывов!"
    else:
        text = "ℹ️ Не было отзывов для удаления."
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔄 Спарсить новые отзывы", callback_data="parse_reviews")],
        [types.InlineKeyboardButton(text="⬅️ Назад к отзывам", callback_data="admin_reviews")]
    ])
    
    await update_message(message.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=message.bot)

# ===== РАССЫЛКИ =====
@router.callback_query(F.data == "back_to_preview")
async def back_to_preview_callback(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к предпросмотру рассылки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    newsletter_text = data.get('newsletter_text', '')
    photo_id = data.get('photo_id')
    message_type = data.get('message_type', 'text')
    
    photo_info = "ℹ️ Без фото"
    if photo_id and message_type == 'photo':
        photo_info = "✅ Фото добавлено!"
    
    preview_text = f"""📝 <b>ПРЕДПРОСМОТР РАССЫЛКИ</b>

<b>Текст:</b>
{newsletter_text[:200]}{'...' if len(newsletter_text) > 200 else ''}

<b>Тип:</b> {'Фото + текст' if message_type == 'photo' else 'Только текст'}
{photo_info}

<b>Переменные в тексте:</b>
• {{Имя пользователя}} → Иван Иванов
• {{Имя}} → Иван
• {{Дата}} → {datetime.now().strftime('%d.%m.%Y')}

<b>Выберите время отправки:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🕐 Отправить немедленно", callback_data=f"send_now_{message_type}_{'1' if photo_id else '0'}")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 1 час", callback_data=f"schedule_1h_{message_type}_{'1' if photo_id else '0'}")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 3 часа", callback_data=f"schedule_3h_{message_type}_{'1' if photo_id else '0'}")],
        [types.InlineKeyboardButton(text="📅 Запланировать на завтра", callback_data=f"schedule_tomorrow_{message_type}_{'1' if photo_id else '0'}")],
        [types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_text")],
        [types.InlineKeyboardButton(text="🗑️ Отменить", callback_data="admin_newsletter")]
    ])
    
    await update_message(callback.from_user.id, preview_text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
@router.callback_query(F.data == "admin_newsletter")
async def admin_newsletter_callback(callback: types.CallbackQuery, state: FSMContext):
    """Быстрое управление рассылками"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    await state.clear()  # Очищаем состояние на всякий случай
    await admin_newsletter_handler(callback.from_user.id, callback.bot)
@router.callback_query(F.data == "edit_text")
async def edit_text_callback(callback: types.CallbackQuery, state: FSMContext):
    """Редактирование текста рассылки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    current_text = data.get('newsletter_text', '')
    
    text = f"""✏️ <b>Редактирование текста рассылки</b>

<b>Текущий текст:</b>
{current_text[:500]}{'...' if len(current_text) > 500 else ''}

Введите новый текст или отправьте текущий без изменений:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к предпросмотру", callback_data="back_to_preview")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(AdminStates.waiting_newsletter_text)
@router.callback_query(F.data.startswith("send_newsletter_"))
async def send_newsletter_callback(callback: types.CallbackQuery):
    """Быстрая рассылка с защитой от таймаутов"""
    await callback.answer("🚀 Запускаем рассылку...", show_alert=False)
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    newsletter_id = int(callback.data.split("_")[2])
    
    all_users = database.get_all_users(limit=500)  # Ограничиваем количество
    
    await update_message(
        callback.from_user.id,
        f"📤 <b>Рассылка запущена</b>\n\nОтправляем сообщение {len(all_users)} пользователям...",
        parse_mode="HTML",
        bot=callback.bot
    )
    
    # Запускаем асинхронную рассылку
    asyncio.create_task(send_newsletter_task_safe(newsletter_id, callback.from_user.id, callback.bot))

async def send_newsletter_task_safe(newsletter_id: int, admin_id: int, bot):
    """Безопасная задача рассылки с поддержкой переменных"""
    try:
        newsletter_info = database.get_newsletter_by_id(newsletter_id)
        
        if not newsletter_info:
            await update_message(
                admin_id,
                "❌ <b>Рассылка не найдена!</b>",
                parse_mode="HTML",
                bot=bot
            )
            return
        
        message_text = newsletter_info['message_text']
        message_type = newsletter_info['message_type']
        photo_id = newsletter_info.get('photo_id')
        
        all_users = database.get_all_users(limit=500)
        sent_count = 0
        failed_count = 0
        
        batch_size = config.NEWSLETTER_BATCH_SIZE
        
        # Получаем информацию об админе для логов
        admin_data = database.get_user_data(admin_id)
        admin_name = admin_data.get('full_name', 'Админ') if admin_data else 'Админ'
        
        await update_message(
            admin_id,
            f"📤 <b>Начинаем рассылку #{newsletter_id}</b>\n\n"
            f"Отправляем сообщение {len(all_users)} пользователям...\n"
            f"Базовая рассылка запущена {admin_name}",
            parse_mode="HTML",
            bot=bot
        )
        
        for i in range(0, len(all_users), batch_size):
            batch = all_users[i:i+batch_size]
            
            for user in batch:
                user_id = user[0]
                user_full_name = user[1] or f"Пользователь {user_id}"
                user_username = user[2] or ""
                
                # Подготавливаем персонализированный текст
                personalized_text = message_text
                
                # Заменяем переменные
                personalized_text = personalized_text.replace(
                    '{Имя пользователя}', 
                    user_full_name
                ).replace(
                    '{Имя}', 
                    user_full_name.split()[0] if user_full_name and ' ' in user_full_name else user_full_name
                ).replace(
                    '{Дата}', 
                    datetime.now().strftime('%d.%m.%Y')
                )
                
                try:
                    if message_type == 'photo' and photo_id:
                        await bot.send_photo(
                            chat_id=user_id,
                            photo=photo_id,
                            caption=personalized_text,
                            parse_mode="HTML"
                        )
                    else:
                        await bot.send_message(
                            chat_id=user_id,
                            text=personalized_text,
                            parse_mode="HTML"
                        )
                    
                    sent_count += 1
                    
                    # Обновляем прогресс каждые 50 отправленных сообщений
                    if sent_count % 50 == 0:
                        progress_text = f"📤 <b>Прогресс рассылки #{newsletter_id}</b>\n\n"
                        progress_text += f"✅ Успешно отправлено: {sent_count}\n"
                        progress_text += f"❌ Не удалось отправить: {failed_count}\n"
                        progress_text += f"👥 Всего пользователей: {len(all_users)}\n"
                        progress_text += f"📈 Прогресс: {sent_count/len(all_users)*100:.1f}%"
                        
                        await update_message(
                            admin_id,
                            progress_text,
                            parse_mode="HTML",
                            bot=bot
                        )
                    
                except Exception as e:
                    error_str = str(e)
                    if "bot was blocked" in error_str or "user is deactivated" in error_str:
                        failed_count += 1
                    elif "Too Many Requests" in error_str:
                        try:
                            retry_after = int(error_str.split('retry after ')[1].split(')')[0])
                            await asyncio.sleep(retry_after)
                            # Пробуем еще раз
                            try:
                                if message_type == 'photo' and photo_id:
                                    await bot.send_photo(
                                        chat_id=user_id,
                                        photo=photo_id,
                                        caption=personalized_text,
                                        parse_mode="HTML"
                                    )
                                else:
                                    await bot.send_message(
                                        chat_id=user_id,
                                        text=personalized_text,
                                        parse_mode="HTML"
                                    )
                                sent_count += 1
                            except:
                                failed_count += 1
                        except:
                            failed_count += 1
                    else:
                        failed_count += 1
            
            # Пауза между батчами
            if i + batch_size < len(all_users):
                await asyncio.sleep(config.NEWSLETTER_DELAY)
        
        database.update_newsletter_status(newsletter_id, 'sent', sent_count)
        
        text = f"""✅ <b>Рассылка #{newsletter_id} завершена!</b>

📊 Результаты:
✅ Успешно отправлено: {sent_count}
❌ Не удалось отправить: {failed_count}
👥 Всего пользователей: {len(all_users)}
📈 Эффективность: {sent_count/len(all_users)*100:.1f}%"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📊 Статистика рассылки", callback_data=f"newsletter_stats_{newsletter_id}")],
            [types.InlineKeyboardButton(text="🔄 Создать новую рассылку", callback_data="admin_create_newsletter")],
            [types.InlineKeyboardButton(text="⬅️ Назад к рассылкам", callback_data="admin_newsletter")]
        ])
        
        await update_message(
            admin_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
            bot=bot
        )
        
        # Логируем завершение рассылки
        database.log_action(admin_id, "newsletter_completed", 
                          f"id:{newsletter_id}, sent:{sent_count}, failed:{failed_count}")
        
    except Exception as e:
        logger.error(f"Ошибка при рассылке #{newsletter_id}: {e}")
        
        database.update_newsletter_status(newsletter_id, 'failed')
        
        error_text = f"❌ <b>Ошибка при рассылке #{newsletter_id}!</b>\n\n{str(e)[:200]}..."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"retry_newsletter_{newsletter_id}")],
            [types.InlineKeyboardButton(text="⬅️ Назад к рассылкам", callback_data="admin_newsletter")]
        ])
        
        await update_message(
            admin_id,
            error_text,
            reply_markup=keyboard,
            parse_mode="HTML",
            bot=bot
        )
@router.callback_query(F.data.startswith("newsletter_stats_"))
async def newsletter_stats_callback(callback: types.CallbackQuery):
    """Статистика конкретной рассылки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    try:
        newsletter_id = int(callback.data.replace("newsletter_stats_", ""))
        newsletter_info = database.get_newsletter_by_id(newsletter_id)
        
        if not newsletter_info:
            await update_message(
                callback.from_user.id,
                "❌ <b>Рассылка не найдена!</b>",
                parse_mode="HTML",
                bot=callback.bot
            )
            return
        
        message_type = "📸 Фото + текст" if newsletter_info['message_type'] == 'photo' else "📝 Только текст"
        created_at = newsletter_info['created_at'][:19] if newsletter_info['created_at'] else "Неизвестно"
        
        text = f"""📊 <b>Статистика рассылки #{newsletter_id}</b>

<b>Информация:</b>
📅 Создана: {created_at}
📱 Тип: {message_type}
📈 Статус: {newsletter_info['status'].upper()}

<b>Результаты:</b>
✅ Успешно отправлено: {newsletter_info['sent_count']}
👥 Всего пользователей: {database.get_all_users().__len__()} (на момент рассылки)

<b>Текст рассылки:</b>
{newsletter_info['message_text'][:200]}{'...' if len(newsletter_info['message_text']) > 200 else ''}"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Отправить еще раз", callback_data=f"resend_newsletter_{newsletter_id}")],
            [types.InlineKeyboardButton(text="📋 Копировать текст", callback_data=f"copy_text_{newsletter_id}")],
            [types.InlineKeyboardButton(text="⬅️ Назад к рассылкам", callback_data="admin_newsletter")]
        ])
        
        await update_message(
            callback.from_user.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
            bot=callback.bot
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await update_message(
            callback.from_user.id,
            f"❌ <b>Ошибка при получении статистики!</b>\n\n{str(e)[:100]}",
            parse_mode="HTML",
            bot=callback.bot
        )
@router.callback_query(F.data == "admin_all_newsletters")
async def admin_all_newsletters_callback(callback: types.CallbackQuery):
    """Просмотр всех рассылок"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    try:
        with database.get_cursor() as cursor:
            cursor.execute('''
            SELECT id, message_type, sent_count, status, created_at 
            FROM newsletters 
            ORDER BY created_at DESC 
            LIMIT 20
            ''')
            newsletters = cursor.fetchall() or []
        
        if not newsletters:
            text = "📨 <b>История рассылок</b>\n\nРассылок еще не было."
        else:
            text = f"📨 <b>История рассылок</b>\n\n<b>Последние {len(newsletters)} рассылок:</b>\n\n"
            
            for newsletter in newsletters:
                nl_id = newsletter[0]
                nl_type = "📸" if newsletter[1] == 'photo' else "📝"
                nl_sent = newsletter[2]
                nl_status = newsletter[3]
                nl_date = newsletter[4][:16] if newsletter[4] else "Неизвестно"
                
                status_icon = "✅" if nl_status == 'sent' else "⏳" if nl_status == 'pending' else "❌"
                
                text += f"{status_icon} <b>#{nl_id}</b> {nl_type} - Отправлено: {nl_sent}\n"
                text += f"   📅 {nl_date}\n\n"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📊 Подробная статистика", callback_data=f"newsletter_stats_{newsletters[0][0]}" if newsletters else "admin_newsletter")],
            [types.InlineKeyboardButton(text="⬅️ Назад к рассылкам", callback_data="admin_newsletter")]
        ])
        
        await update_message(
            callback.from_user.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
            bot=callback.bot
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения списка рассылок: {e}")
        await update_message(
            callback.from_user.id,
            "❌ <b>Ошибка при получении списка рассылок!</b>",
            parse_mode="HTML",
            bot=callback.bot
        )
# ===== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК =====
@router.error()
async def error_handler(event, bot):
    """Глобальный обработчик ошибок"""
    logger.error(f"Глобальная ошибка: {event.exception}")
    
    if hasattr(event, 'exception'):
        exc = event.exception
        if isinstance(exc, aiohttp.ClientConnectorError):
            logger.error("Ошибка соединения с Telegram API")
        elif isinstance(exc, asyncio.TimeoutError):
            logger.error("Таймаут при обработке запроса")
        elif isinstance(exc, TelegramNetworkError):
            logger.error("Сетевая ошибка Telegram")
    
    return True

# ===== ОСТАЛЬНЫЕ CALLBACK ОБРАБОТЧИКИ =====

@router.callback_query(F.data == "reviews")
async def reviews_callback(callback: types.CallbackQuery):
    """Быстрые отзывы"""
    await callback.answer()
    await show_reviews_handler(callback.from_user.id, callback.bot)

async def show_reviews_handler(user_id: int, bot):
    """Показ отзывов - САМЫЕ СВЕЖИЕ ПЕРВЫМИ"""
    database.log_action(user_id, "view_reviews")
    
    # Используем кэшированные отзывы
    cache_key = f"reviews_{user_id}"
    cached_text = cache_manager.cache.get(cache_key)
    
    if cached_text:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⭐ Читать все отзывы", url=config.YANDEX_REVIEWS_URL)],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
        ])
        
        await update_message(user_id, cached_text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
        return
    
    all_reviews = database.get_reviews(limit=5)
    
    if not all_reviews:
        text = """⭐ <b>Отзывы о ресторане</b>

📝 <i>Отзывов пока нет. Они будут появляться здесь после того, как администратор добавит их через админку.</i>"""
    else:
        text = f"""⭐ <b>Отзывы о ресторане</b>

<b>Самые свежие отзывы:</b>\n"""
        
        unique_reviews = []
        seen_authors = set()
        
        for review in all_reviews:
            try:
                review_dict = dict(review)
                author = review_dict.get('author', '')
                rating = review_dict.get('rating', 5)
                text_review = review_dict.get('text', '')
                date = review_dict.get('date', '') or review_dict.get('created_at', '')[:10]
                
                if author and author not in seen_authors:
                    # Быстрый расчет звезд
                    stars = "⭐" * min(int(rating) if isinstance(rating, (int, str)) and str(rating).isdigit() else 5, 5)
                    clean_text = text_review[:100] + "..." if len(text_review) > 100 else text_review
                    
                    # Форматируем дату красиво
                    date_display = ""
                    if date:
                        try:
                            # Пробуем распарсить дату
                            if "-" in date:
                                year, month, day = date.split("-")
                                month_names = ["января", "февраля", "марта", "апреля", "мая", "июня",
                                             "июля", "августа", "сентября", "октября", "ноября", "декабря"]
                                month_name = month_names[int(month)-1] if 1 <= int(month) <= 12 else month
                                date_display = f" ({day} {month_name} {year})"
                        except:
                            date_display = f" ({date})"
                    
                    text += f"\n<b>{author}{date_display}</b> {stars}\n{clean_text}\n\n"
                    seen_authors.add(author)
                    
                    if len(unique_reviews) >= 3:
                        break
            except:
                continue
    
    cache_manager.cache.set(cache_key, text, ttl=300)
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐ Читать все отзывы", url=config.YANDEX_REVIEWS_URL)],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)

@router.callback_query(F.data == "about_us")
async def about_us_callback(callback: types.CallbackQuery):
    """Быстрая информация о нас"""
    await callback.answer()
    database.log_action(callback.from_user.id, "view_about")
    
    restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
    restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    how_to_get = database.get_setting('how_to_get', config.HOW_TO_GET)
    concept_description = database.get_setting('concept_description', config.CONCEPT_DESCRIPTION)
    
    text = f"""🏢 <b>О нас</b>

{concept_description}

📍 <b>Адрес:</b> {restaurant_address}
📞 <b>Телефон:</b> {restaurant_phone}
🕐 <b>Часы работы:</b> {restaurant_hours}

<b>Как добраться:</b>
{how_to_get}"""
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboards.about_menu(),
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "menu_delivery")
async def menu_delivery_callback(callback: types.CallbackQuery, state: FSMContext):
    """Быстрое меню доставки"""
    await callback.answer()
    await menu_delivery_handler(callback.from_user.id, callback.bot, state)

async def menu_delivery_handler(user_id: int, bot, state: FSMContext = None):
    """Оптимизированный обработчик меню доставки с проверкой регистрации"""
    # Проверяем регистрацию
    registration_status = check_user_registration_fast(user_id)
    
    if registration_status != 'completed':
        # ВСЕГДА показываем полную форму регистрации!
        await ask_for_registration_phone(user_id, bot, context="delivery")
        
        # Устанавливаем состояние для отслеживания
        if state:
            await state.update_data(context='delivery')
            await state.set_state(BookingStates.waiting_for_phone)
        return
    
    delivery_cost = database.get_setting('delivery_cost', config.DELIVERY_COST)
    free_delivery_min = database.get_setting('free_delivery_min', config.FREE_DELIVERY_MIN)
    delivery_time = database.get_setting('delivery_time', config.DELIVERY_TIME)
    
    text = f"""🚚 <b>Меню доставки</b>

Мы доставляем самые популярные блюда:

• Пицца Маргарита — 650₽
• Бургер Классик — 850₽
• Салат Цезарь — 680₽
• Паста Карбонара — 750₽

💰 <b>Доставка:</b> {delivery_cost}₽ (бесплатно от {free_delivery_min}₽)
⏱️ <b>Время:</b> {delivery_time}

💡 <i>Хотите заказать доставку? Напишите нам в чат список блюд!</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Получить PDF меню", callback_data="menu_pdf")],
        [types.InlineKeyboardButton(text="🍽️ Сделать заказ", callback_data="make_order")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_food")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)

# Дополнительные обработчики для остальных callback
@router.callback_query(F.data.startswith("faq_"))
async def faq_answer_callback(callback: types.CallbackQuery):
    """Быстрый ответ на FAQ"""
    await callback.answer()
    
    try:
        faq_id = int(callback.data.replace("faq_", ""))
        
        # Кэшируем FAQ
        cache_key = "faq_list"
        faq_list = cache_manager.cache.get(cache_key)
        
        if faq_list is None:
            faq_list = database.get_faq()
            cache_manager.cache.set(cache_key, faq_list, ttl=600)
        
        answer_text = "Пожалуйста, задайте этот вопрос оператору."
        question_text = "Вопрос"
        
        for f_id, question, answer in faq_list:
            if f_id == faq_id:
                answer_text = answer
                question_text = question
                break
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад к вопросам", callback_data="faq")],
            [types.InlineKeyboardButton(text="📞 Не нашли ответ? Свяжитесь с нами!", callback_data="contact_us")]
        ])
        
        await update_message(callback.from_user.id,
                           f"<b>❓ Вопрос:</b> {question_text}\n\n<b>💡 Ответ:</b> {answer_text}",
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=callback.bot)
    except:
        await callback.answer("Ошибка при получении ответа", show_alert=True)

@router.callback_query(F.data == "admin_orders")
async def admin_orders_callback(callback: types.CallbackQuery):
    """Быстрый просмотр заказов"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    orders = database.get_all_orders()
    
    text = "🍽️ <b>Заказы</b>\n\n"
    
    if orders:
        text += f"<b>Всего заказов:</b> {len(orders)}\n\n"
        
        for order_id, full_name, items, total_amount, status, created_at in orders[:3]:
            text += f"<b>ID: {order_id}</b> - {full_name or 'Неизвестно'}\n"
            text += f"Сумма: {total_amount}₽ | Статус: {status}\n"
            text += f"<i>{created_at[:16] if created_at else ''}</i>\n\n"
    else:
        text += "❌ <b>Заказов пока нет!</b>\n\n"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_create_newsletter")
async def admin_create_newsletter_callback(callback: types.CallbackQuery, state: FSMContext):
    """Быстрое создание рассылки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = """📝 <b>Создание рассылки</b>

Введите текст рассылки. Вы можете использовать HTML-разметку:
<b>жирный</b>, <i>курсив</i>, ссылки и т.д.

Максимальная длина: 4096 символов."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к рассылкам", callback_data="admin_newsletter")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(AdminStates.waiting_newsletter_text)

async def process_newsletter_text(message: types.Message, state: FSMContext):
    """Оптимизированная обработка текста рассылки"""
    if not is_admin_fast(message.from_user.id):
        return
    
    newsletter_text = message.text
    
    if len(newsletter_text) > 4096:
        await update_message(message.from_user.id, 
                           "❌ Текст слишком длинный! Максимум 4096 символов.", 
                           bot=message.bot)
        return
    
    await state.update_data(newsletter_text=newsletter_text)
    
    text = """📷 <b>Добавить фото к рассылке?</b>

Вы можете прикрепить фото к рассылке или отправить только текст.

<code>💡 Вы можете использовать переменные в тексте:
{Имя пользователя} - будет заменено на имя пользователя
{Имя} - короткая форма имени
{Дата} - текущая дата</code>

Выберите действие:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📸 Прикрепить фото", callback_data="add_photo")],
        [types.InlineKeyboardButton(text="➡️ Пропустить (только текст)", callback_data="skip_photo")],
        [types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_text_newsletter")],
        [types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_newsletter")]
    ])
    
    await update_message(message.from_user.id, text, 
                        reply_markup=keyboard, 
                        parse_mode="HTML", 
                        bot=message.bot)
    
    await state.set_state(AdminStates.waiting_newsletter_photo)
@router.callback_query(F.data == "add_photo")
async def add_photo_callback(callback: types.CallbackQuery, state: FSMContext):
    """Кнопка для добавления фото к рассылке"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = """📸 <b>Прикрепите фото к рассылке</b>

Пожалуйста, отправьте фото для рассылки.

<code>💡 Советы:
• Используйте качественные фото
• Размер не должен превышать 10MB
• Поддерживаются форматы: JPG, PNG, WEBP</code>

<i>Или нажмите "Пропустить" чтобы создать рассылку без фото</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➡️ Пропустить (без фото)", callback_data="skip_photo")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_text")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
@router.callback_query(F.data == "back_to_text")
async def back_to_text_callback(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к редактированию текста рассылки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    newsletter_text = data.get('newsletter_text', '')
    
    text = f"""✏️ <b>Редактирование текста рассылки</b>

<b>Текущий текст:</b>
{newsletter_text[:500]}{'...' if len(newsletter_text) > 500 else ''}

Введите новый текст или отправьте текущий без изменений:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_newsletter")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(AdminStates.waiting_newsletter_text)
@router.callback_query(F.data == "edit_text_newsletter")
async def edit_text_newsletter_callback(callback: types.CallbackQuery, state: FSMContext):
    """Редактирование текста рассылки из меню"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    newsletter_text = data.get('newsletter_text', '')
    
    text = f"""✏️ <b>Редактирование текста рассылки</b>

<b>Текущий текст:</b>
{newsletter_text[:500]}{'...' if len(newsletter_text) > 500 else ''}

Введите новый текст или отправьте текущий без изменений:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(AdminStates.waiting_newsletter_text)
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к меню выбора фото"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    newsletter_text = data.get('newsletter_text', '')
    
    text = """📷 <b>Добавить фото к рассылке?</b>

Вы можете прикрепить фото к рассылке или отправить только текст.

<code>💡 Вы можете использовать переменные в тексте:
{Имя пользователя} - будет заменено на имя пользователя
{Имя} - короткая форма имени
{Дата} - текущая дата</code>

Выберите действие:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📸 Прикрепить фото", callback_data="add_photo")],
        [types.InlineKeyboardButton(text="➡️ Пропустить (только текст)", callback_data="skip_photo")],
        [types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_text_newsletter")],
        [types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_newsletter")]
    ])
    
    await update_message(callback.from_user.id, text, 
                        reply_markup=keyboard, 
                        parse_mode="HTML", 
                        bot=callback.bot)
    
    await state.set_state(AdminStates.waiting_newsletter_photo)

@router.callback_query(F.data.startswith("send_now_"))
@router.callback_query(F.data.startswith("schedule_"))
async def handle_newsletter_schedule(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора времени отправки рассылки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    newsletter_text = data.get('final_text', '')
    photo_id = data.get('photo_id')
    message_type = data.get('message_type', 'text')
    
    # Определяем тип расписания
    callback_data = callback.data
    
    if callback_data.startswith('send_now_'):
        schedule_time = 'immediate'
        schedule_text = "немедленно"
    elif callback_data.startswith('schedule_1h_'):
        schedule_time = '1h'
        schedule_text = "через 1 час"
    elif callback_data.startswith('schedule_3h_'):
        schedule_time = '3h'
        schedule_text = "через 3 часа"
    elif callback_data.startswith('schedule_tomorrow_'):
        schedule_time = 'tomorrow'
        schedule_text = "завтра"
    else:
        schedule_time = 'immediate'
        schedule_text = "немедленно"
    
    # Создаем рассылку в базе данных
    newsletter_id = database.create_newsletter(
        callback.from_user.id,
        newsletter_text,
        message_type,
        photo_id
    )
    
    if not newsletter_id:
        await update_message(callback.from_user.id,
                           "❌ Ошибка при создании рассылки!",
                           bot=callback.bot)
        await state.clear()
        return
    
    # Если отправка немедленная - запускаем
    if schedule_time == 'immediate':
        await update_message(
            callback.from_user.id,
            f"🚀 <b>Запускаем рассылку немедленно!</b>\n\nID рассылки: {newsletter_id}",
            parse_mode="HTML",
            bot=callback.bot
        )
        
        # Запускаем асинхронную рассылку
        asyncio.create_task(send_newsletter_task_safe(newsletter_id, callback.from_user.id, callback.bot))
    else:
        # Для отложенных рассылок сохраняем время
        # Здесь нужно добавить логику для планирования (можно использовать apscheduler или cron)
        await update_message(
            callback.from_user.id,
            f"✅ <b>Рассылка запланирована!</b>\n\n"
            f"ID рассылки: {newsletter_id}\n"
            f"Время отправки: {schedule_text}\n\n"
            f"Рассылка будет отправлена автоматически.",
            parse_mode="HTML",
            bot=callback.bot
        )
    
    await state.clear()

@router.callback_query(F.data == "skip_photo")
async def skip_photo_callback(callback: types.CallbackQuery, state: FSMContext):
    """Пропуск добавления фото"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    newsletter_text = data.get('newsletter_text', '')
    
    # Создаем предпросмотр рассылки без фото
    preview_text = f"""📝 <b>ПРЕДПРОСМОТР РАССЫЛКИ</b>

<b>Текст:</b>
{newsletter_text[:200]}{'...' if len(newsletter_text) > 200 else ''}

<b>Тип:</b> Только текст
ℹ️ Без фото

<b>Переменные в тексте:</b>
• {{Имя пользователя}} → Иван Иванов
• {{Имя}} → Иван
• {{Дата}} → {datetime.now().strftime('%d.%m.%Y')}

<b>Выберите время отправки:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🕐 Отправить немедленно", callback_data="send_now_text_0")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 1 час", callback_data="schedule_1h_text_0")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 3 часа", callback_data="schedule_3h_text_0")],
        [types.InlineKeyboardButton(text="📅 Запланировать на завтра", callback_data="schedule_tomorrow_text_0")],
        [types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_text_newsletter")],
        [types.InlineKeyboardButton(text="🗑️ Отменить", callback_data="admin_newsletter")]
    ])
    
    await update_message(callback.from_user.id, preview_text, 
                        reply_markup=keyboard, 
                        parse_mode="HTML", 
                        bot=callback.bot)
    
    # Сохраняем данные в state
    await state.update_data(
        photo_id=None,
        message_type='text',
        final_text=newsletter_text
    )

@router.callback_query(F.data == "admin_reviews")
async def admin_reviews_callback(callback: types.CallbackQuery):
    """Быстрое управление отзывами"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    reviews = database.get_all_reviews()
    
    text = "⭐ <b>Управление отзывами</b>\n\n"
    
    if reviews:
        text += f"<b>Всего отзывов в базе:</b> {len(reviews)}\n\n"
        
        for i, review in enumerate(reviews[:2]):
            try:
                review_dict = dict(review)
                author = review_dict.get('author', 'Неизвестный')
                rating = review_dict.get('rating', 5)
                text_review = review_dict.get('text', '')
                
                stars = "⭐" * min(int(rating) if isinstance(rating, (int, str)) and str(rating).isdigit() else 5, 5)
                preview = text_review[:60] + "..." if len(text_review) > 60 else text_review
                
                text += f"<b>{author}</b> {stars}\n{preview}\n\n"
            except:
                continue
    else:
        text += "❌ <b>Отзывов пока нет!</b>\n\n"
    
    text += "💡 <i>Используйте 'Спарсить отзывы' для добавления реальных отзывов с Яндекс Карт</i>"
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboards.reviews_admin_menu(),
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_faq")
async def admin_faq_callback(callback: types.CallbackQuery):
    """Быстрое управление FAQ"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    faq = database.get_faq()
    
    text = "❓ <b>Управление FAQ</b>\n\n"
    
    if faq:
        text += f"<b>Всего вопросов:</b> {len(faq)}\n\n"
    else:
        text += "Вопросов пока нет.\n"
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboards.faq_admin_menu(),
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_add_faq")
async def admin_add_faq_callback(callback: types.CallbackQuery, state: FSMContext):
    """Быстрое добавление FAQ"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = "📝 <b>Добавление нового FAQ</b>\n\nВведите вопрос:"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к FAQ", callback_data="admin_faq")]
    ])
    
    await update_message(callback.from_user.id, text,
                       reply_markup=keyboard,
                       parse_mode="HTML",
                       bot=callback.bot)
    await state.set_state(BookingStates.waiting_faq_question)

async def admin_faq_question_received(message: types.Message, state: FSMContext):
    """Быстрое получение вопроса FAQ"""
    if not is_admin_fast(message.from_user.id):
        return
    
    await state.update_data(faq_question=message.text)
    
    text = "📝 <b>Добавление нового FAQ</b>\n\nТеперь введите ответ на вопрос:"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_faq")]
    ])
    
    await update_message(message.from_user.id, text,
                       reply_markup=keyboard, 
                       parse_mode="HTML",
                       bot=message.bot)
    await state.set_state(BookingStates.waiting_faq_answer)

async def admin_faq_answer_received(message: types.Message, state: FSMContext):
    """Быстрое получение ответа FAQ"""
    if not is_admin_fast(message.from_user.id):
        return
    
    data = await state.get_data()
    question = data.get('faq_question', '')
    answer = message.text
    
    database.save_faq(question, answer)
    
    # Очищаем кэш FAQ
    cache_manager.cache.delete("faq_list")
    
    text = f"""✅ <b>FAQ добавлен!</b>

<b>Вопрос:</b> {question}"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Посмотреть все FAQ", callback_data="admin_view_faq")],
        [types.InlineKeyboardButton(text="➕ Добавить еще FAQ", callback_data="admin_add_faq")],
        [types.InlineKeyboardButton(text="⬅️ Назад к FAQ", callback_data="admin_faq")]
    ])
    
    await update_message(message.from_user.id, text,
                       reply_markup=keyboard,
                       parse_mode="HTML", 
                       bot=message.bot)
    
    await state.clear()

@router.callback_query(F.data == "admin_view_faq")
async def admin_view_faq_callback(callback: types.CallbackQuery):
    """Быстрый просмотр всех FAQ"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    faq_list = database.get_faq()
    
    if not faq_list:
        text = "❓ <b>Все вопросы FAQ</b>\n\nВопросов пока нет."
    else:
        text = f"""❓ <b>Все вопросы FAQ</b>

<b>Всего вопросов:</b> {len(faq_list)}

<b>Список вопросов:</b>\n"""
        
        for faq_id, question, answer in faq_list:
            text += f"\n<b>ID {faq_id}:</b> {question}\n"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Добавить новый FAQ", callback_data="admin_add_faq")],
        [types.InlineKeyboardButton(text="🗑️ Удалить FAQ", callback_data="admin_delete_faq_start")],
        [types.InlineKeyboardButton(text="⬅️ Назад к FAQ", callback_data="admin_faq")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_delete_faq_start")
async def admin_delete_faq_start_callback(callback: types.CallbackQuery, state: FSMContext):
    """Быстрое начало удаления FAQ"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = "🗑️ <b>Удаление FAQ</b>\n\nВведите ID вопроса для удаления:"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к FAQ", callback_data="admin_faq")]
    ])
    
    await update_message(callback.from_user.id, text,
                       reply_markup=keyboard,
                       parse_mode="HTML",
                       bot=callback.bot)
    await state.set_state(BookingStates.editing_faq)

async def admin_delete_faq_process(message: types.Message, state: FSMContext):
    """Быстрая обработка удаления FAQ"""
    if not is_admin_fast(message.from_user.id):
        return
    
    try:
        faq_id = int(message.text.strip())
        
        success = database.delete_faq(faq_id)
        
        if success:
            # Очищаем кэш FAQ
            cache_manager.cache.delete("faq_list")
            text = f"✅ FAQ с ID {faq_id} успешно удален!"
        else:
            text = f"❌ Не удалось удалить FAQ с ID {faq_id}."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🗑️ Удалить еще FAQ", callback_data="admin_delete_faq_start")],
            [types.InlineKeyboardButton(text="📋 Посмотреть все FAQ", callback_data="admin_view_faq")],
            [types.InlineKeyboardButton(text="⬅️ Назад к FAQ", callback_data="admin_faq")]
        ])
        
        await update_message(message.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)
        
    except ValueError:
        text = "❌ Пожалуйста, введите числовой ID вопроса."
        await update_message(message.from_user.id, text,
                           bot=message.bot)
        return
    
    await state.clear()

@router.callback_query(F.data == "admin_settings")
async def admin_settings_callback(callback: types.CallbackQuery):
    """Быстрые настройки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    settings = database.get_all_settings()
    
    text = "⚙️ <b>Настройки бота</b>\n\n"
    text += "<b>Основные настройки:</b>\n"
    
    setting_keys = [
        ('restaurant_name', 'Название ресторана'),
        ('restaurant_phone', 'Телефон'),
        ('restaurant_address', 'Адрес'),
        ('delivery_cost', 'Стоимость доставки'),
    ]
    
    for key, description in setting_keys:
        value = settings.get(key, 'Не установлено')
        text += f"<b>{description}:</b> {value[:30]}...\n"
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboards.settings_menu(),
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data.startswith("edit_setting_"))
async def admin_edit_setting_callback(callback: types.CallbackQuery, state: FSMContext):
    """Быстрое редактирование настройки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    setting_key = callback.data.replace("edit_setting_", "")
    
    setting_names = {
        'restaurant_name': 'Название ресторана',
        'restaurant_address': 'Адрес',
        'restaurant_phone': 'Телефон',
        'restaurant_hours': 'Часы работы',
        'how_to_get': 'Как добраться',
        'concept_description': 'Описание концепта',
        'start_message': 'Стартовое сообщение',
        'delivery_cost': 'Стоимость доставки',
        'free_delivery_min': 'Минимум для бесплатной доставки',
        'delivery_time': 'Время доставки'
    }
    
    current_value = database.get_setting(setting_key, '')
    setting_name = setting_names.get(setting_key, setting_key)
    
    text = f"""⚙️ <b>Редактирование настройки</b>

<b>Настройка:</b> {setting_name}

<b>Текущее значение:</b>
{current_value[:100]}{'...' if len(current_value) > 100 else ''}

<b>Введите новое значение:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="admin_settings")]
    ])
    
    await update_message(callback.from_user.id, text,
                       parse_mode="HTML", 
                       bot=callback.bot)
    
    await state.update_data(setting_key=setting_key)
    await state.set_state(BookingStates.editing_setting)

async def admin_save_setting(message: types.Message, state: FSMContext):
    """Быстрое сохранение настройки"""
    if not is_admin_fast(message.from_user.id):
        return
    
    data = await state.get_data()
    setting_key = data.get('setting_key')
    
    if setting_key:
        database.update_setting(setting_key, message.text)
        
        # Очищаем кэш главного меню для всех пользователей
        cache_manager.cache.clear_pattern("main_menu_*")
        
        setting_names = {
            'restaurant_name': 'Название ресторана',
            'restaurant_address': 'Адрес',
            'restaurant_phone': 'Телефон',
            'restaurant_hours': 'Часы работы',
            'how_to_get': 'Как добраться',
            'concept_description': 'Описание концепта',
            'start_message': 'Стартовое сообщение',
            'delivery_cost': 'Стоимость доставки',
            'free_delivery_min': 'Минимум для бесплатной доставки',
            'delivery_time': 'Время доставки'
        }
        
        setting_name = setting_names.get(setting_key, setting_key)
        
        text = f"""✅ <b>Настройка обновлена!</b>

<b>Настройка:</b> {setting_name}
<b>Новое значение:</b>
{message.text[:100]}{'...' if len(message.text) > 100 else ''}

Изменения применятся сразу."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⚙️ Редактировать другую настройку", callback_data="admin_settings")],
            [types.InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back")]
        ])
        
        await update_message(message.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)
    
    await state.clear()

# ===== БРОНИРОВАНИЕ =====

async def process_phone_booking(message: types.Message, state: FSMContext):
    """Быстрая обработка телефона для бронирования"""
    phone = message.text.strip()
    
    phone_regex = r'^\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}$|^\+7\d{10}$|^8\d{10}$|^7\d{10}$'
    
    if not re.match(phone_regex, phone):
        await update_message(message.from_user.id,
                           "❌ Неверный формат телефона!\nПример: +7 912 345 67 89",
                           bot=message.bot)
        return
    
    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone_clean.startswith("8"):
        phone_clean = "+7" + phone_clean[1:]
    elif phone_clean.startswith("7"):
        phone_clean = "+" + phone_clean
    
    data = await state.get_data()
    
    booking_id = database.save_booking(
        message.from_user.id,
        data['booking_date'],
        data['booking_time'],
        phone_clean,
        data['booking_guests']
    )
    
    database.log_action(message.from_user.id, "booking_created", f"id:{booking_id}")
    
    masked_phone = f"+7 XXX XXX {phone_clean[-4:-2]} {phone_clean[-2:]}" if len(phone_clean) >= 11 else phone_clean
    
    text = f"""✅ <b>Бронирование подтверждено!</b>

🎉 Ваш столик забронирован.

<b>Детали:</b>
📅 Дата: {data['booking_date']}
🕐 Время: {data['booking_time']}:00
📞 Телефон: {masked_phone}
👥 Гости: {data['booking_guests']}

⏳ Ожидайте звонка для подтверждения."""
    
    await update_message(message.from_user.id, text,
                        reply_markup=keyboards.back_to_main(),
                        parse_mode="HTML",
                        bot=message.bot)
    await state.clear()

# ===== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ =====

@router.callback_query(F.data == "menu_pdf")
async def menu_pdf_callback(callback: types.CallbackQuery):
    """Быстрое PDF меню"""
    await callback.answer()
    
    text = """📋 <b>Полное меню в PDF</b>

Ссылка на меню: https://mashkov.rest/menu.pdf

💡 <i>У нас также есть специальное банкетное меню для вашего праздника!</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🎉 Банкетное меню", callback_data="menu_banquet")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_food")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "photos")
async def photos_callback(callback: types.CallbackQuery):
    """Быстрые фото"""
    await callback.answer()
    
    text = """📸 <b>Фотогалерея</b>

<code>Фото экстерьера и интерьера будут доступны в ближайшее время</code>

<b>А пока:</b>
• 3D-тур ресторана (скоро)
• Больше фото в нашем Instagram"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="about_us")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "chat_operator")
async def chat_operator_callback(callback: types.CallbackQuery):
    """Быстрый чат с оператором"""
    await callback.answer()
    
    text = """💬 <b>Чат с оператором</b>

Напишите ваш вопрос прямо здесь в чат!

⏳ <i>Среднее время ответа: 5-10 минут</i>

<b>А пока посмотрите:</b>
• Частые вопросы (FAQ)
• Информацию о доставке"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❓ FAQ", callback_data="faq")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="contact_us")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

# ===== ОБРАБОТЧИК ДЛЯ СОЗДАНИЯ ЗАКАЗА =====

@router.callback_query(F.data == "make_order")
async def make_order_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало заказа доставки"""
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Проверяем регистрацию
    registration_status = check_user_registration_fast(user_id)
    
    if registration_status != 'completed':
        # ВСЕГДА показываем полную форму регистрации!
        await ask_for_registration_phone(user_id, callback.bot, context="delivery")
        
        # Устанавливаем состояние для отслеживания
        await state.update_data(context='delivery')
        await state.set_state(BookingStates.waiting_for_phone)
        return
    
    text = """🍽️ <b>Сделать заказ</b>

Напишите в чат, что вы хотите заказать:

• Название блюд
• Количество
• Особые пожелания (например, без лука)

Наш оператор свяжется с вами для подтверждения заказа и уточнения адреса доставки."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📱 Связаться с оператором", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_delivery")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)


# ===== КОМАНДА ОЧИСТКИ КЭША =====

@router.message(Command("clear_cache"))
async def clear_cache_command(message: types.Message):
    """Команда для очистки кэшей"""
    user_id = message.from_user.id
    
    if not is_admin_fast(user_id):
        await message.answer("❌ У вас нет доступа к этой команде!")
        return
    
    # Очищаем все кэши
    user_registration_cache.clear()
    admin_cache.clear()
    last_message_ids.clear()
    cache_manager.cache.clear()
    database.clear_admin_cache()
    
    await message.answer("✅ Все кэши очищены!")