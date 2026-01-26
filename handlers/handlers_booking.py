# handlers_booking.py

from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
import keyboards
import database
import config

import re
from aiogram.types import ReplyKeyboardRemove
from typing import Dict, List
from menu_cache import menu_cache
from cart_manager import cart_manager
import asyncio
import cache_manager
import logging
from datetime import datetime, timedelta, date
import json
import os
import random
import calendar

try:
    from presto_api_booking import get_booking_calendar, get_hall_tables, create_booking, get_available_tables
    from presto_api_booking import get_booking_info, update_booking, cancel_booking, get_booking_state, BOOKING_STATUSES
    print("✅ Presto API загружен успешно")
except ImportError as e:
    print(f"⚠️ Ошибка импорта Presto API: {e}")

try:
    from .handlers_main import clean_phone_for_link
except ImportError:
    def clean_phone_for_link(phone):
        return ''.join(c for c in phone if c.isdigit() or c == '+')
    def get_booking_calendar(*args, **kwargs):
        print("⚠️ Presto API не доступен: get_booking_calendar")
        return None
    
    def get_hall_tables(*args, **kwargs):
        print("⚠️ Presto API не доступен: get_hall_tables")
        return None
    
    def get_available_tables(*args, **kwargs):
        print("⚠️ Presto API не доступен: get_available_tables")
        return []
    
    def create_booking(*args, **kwargs):
        print("⚠️ Presto API не доступен: create_booking")
        return None
    
    def get_booking_info(*args, **kwargs):
        print("⚠️ Presto API не доступен: get_booking_info")
        return None
    
    def update_booking(*args, **kwargs):
        print("⚠️ Presto API не доступен: update_booking")
        return None
    
    def cancel_booking(*args, **kwargs):
        print("⚠️ Presto API не доступен: cancel_booking")
        return None
    
    def get_booking_state(*args, **kwargs):
        print("⚠️ Presto API не доступен: get_booking_state")
        return None
    
    BOOKING_STATUSES = {}

from .utils import update_message, check_user_registration_fast, clear_user_cache, send_admin_notification, safe_delete_message, safe_send_message, typing_indicator, clear_operator_chat
from .handlers_main import clean_phone_for_link

async def show_booking_options(callback_or_user_id, bot=None):
    """Показать опции бронирования"""
    # Определяем тип входных данных
    if hasattr(callback_or_user_id, 'from_user'):
        # Это callback - просто отправляем новое сообщение
        callback = callback_or_user_id
        user_id = callback.from_user.id
        bot = callback.bot
    else:
        # Это user_id и bot
        user_id = callback_or_user_id
        if bot is None:
            return

    # Всегда отправляем новое сообщение
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Конструктор бронирования", callback_data="new_booking")],
        [InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

    await safe_send_message(bot, user_id,
                           "📅 <b>Бронирование столика</b>\n\n"
                           "Вы можете забронировать столик двумя способами:\n\n"
                           "1️⃣ Через наш конструктор бронирования (с выбором стола на схеме)\n"
                           "2️⃣ Написать мне в чате, и я сам забронирую для вас!\n\n"
                           "💡 <b>Пример сообщения:</b> \"3 человека, 19 января, в 19:30\"\n\n"
                           "ℹ️ <b>Важно:</b> Автоматическое бронирование доступно до 4 человек.\n"
                           "Для компаний от 5 человек свяжитесь с оператором.\n\n"
                           "Выберите удобный для вас способ:",
                           reply_markup=kb,
                           parse_mode="HTML")

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from io import BytesIO
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ Pillow не установлен.")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None
    print("⚠️ requests не установлен.")

logger = logging.getLogger(__name__)
router = Router()

class BookingStates(StatesGroup):
    waiting_for_guests = State()
    waiting_for_date = State()
    waiting_for_time_category = State()
    waiting_for_time = State()
    waiting_for_table = State()
    waiting_for_confirmation = State()
    managing_booking = State()
    editing_booking = State()
    canceling_booking = State()
    selecting_booking = State()
    
    # Состояния для админки (из handlers_admin.py)
    editing_review = State()
    editing_setting = State()
    waiting_faq_question = State()
    waiting_faq_answer = State()
    editing_faq = State()
    waiting_promocode_code = State()
    waiting_phone_for_promocode = State()


# Хранилище для активных броней пользователей
# Ключ: user_id, Значение: список словарей с информацией о бронях
_user_bookings = {}
RU_MONTHS = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]
# Словарь названий категорий времени
category_names = {
    "morning": "☀️ Утро (8:00–12:00)",
    "lunch": "🍽️ Обед (12:00–16:00)",
    "evening": "🌙 Вечер (16:00–21:00)"
}

# Глобальная переменная для ID сообщения со схемой
_schema_message_id = None

async def get_user_bookings(user_id: int):
    """Получить бронирования пользователя"""
    user_data = database.get_user_data(user_id)
    if not user_data or not user_data.get('phone'):
        return []
    
    # Здесь должна быть логика получения броней по телефону пользователя
    # Поскольку у нас нет прямого API для получения броней по телефону,
    # будем хранить созданные брони локально
    if user_id in _user_bookings:
        return _user_bookings[user_id]
    
    return []

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)
async def save_user_booking(user_id: int, booking_data: dict):
    """Сохранить информацию о бронировании пользователя"""
    if user_id not in _user_bookings:
        _user_bookings[user_id] = []
    
    # Проверяем, нет ли уже такой брони
    for booking in _user_bookings[user_id]:
        if booking.get('external_id') == booking_data.get('external_id'):
            return
    
    _user_bookings[user_id].append(booking_data)

@router.callback_query(F.data == "booking")
async def booking_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    
    if check_user_registration_fast(user_id) != 'completed':
        from .handlers_registration import ask_for_registration_phone, RegistrationStates
        await ask_for_registration_phone(user_id, callback.bot, "booking")
        await state.set_state(RegistrationStates.waiting_for_phone)
        return
    
    # Проверим, есть ли активные брони у пользователя
    user_bookings = await get_user_bookings(user_id)
    active_bookings = [b for b in user_bookings if b.get('status_code', 0) not in [40, 45, 220]]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Новая бронь", callback_data="new_booking")],
        [InlineKeyboardButton(text="📋 Мои брони", callback_data="my_bookings")],
        [InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

    if active_bookings:
        # Показать меню выбора: новая бронь или управление существующими
        text = "📅 <b>Бронирование столика</b>\n\n" \
               f"У вас есть активные брони: {len(active_bookings)}\n\n" \
               "Вы можете создать новую бронь или управлять существующими."
    else:
        # Показать только кнопку новой брони
        text = "📅 <b>Бронирование столика</b>\n\n" \
               "Вы можете забронировать столик двумя способами:\n\n" \
               "1️⃣ Через наш конструктор бронирования (с выбором стола на схеме)\n" \
               "2️⃣ Написать мне в чате, и я сам забронирую для вас!\n\n" \
               "💡 <b>Пример сообщения:</b> \"3 человека, 19 января, в 19:30\"\n\n" \
               "ℹ️ <b>Важно:</b> Автоматическое бронирование доступно до 4 человек.\n" \
               "Для компаний от 5 человек свяжитесь с оператором.\n\n" \
               "Выберите удобный для вас способ:"

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")



@router.callback_query(F.data == "new_booking")
async def new_booking_handler(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    user_id = callback.from_user.id
    
    # Удаляем схему зала если есть
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, user_id, _schema_message_id)
            _schema_message_id = None
        except:
            pass
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"guests:{i}") for i in range(1, 4)],
        [InlineKeyboardButton(text=str(i), callback_data=f"guests:{i}") for i in range(4, 7)],
        [InlineKeyboardButton(text="💬 ЗАБРОНИРОВАТЬ В ЧАТЕ", callback_data="chat_operator")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="booking")]
    ])
    await update_message(user_id, "👥 <b>Сколько вас будет?</b>", reply_markup=kb, parse_mode="HTML", bot=callback.bot)
    await state.set_state(BookingStates.waiting_for_guests)

@router.callback_query(F.data == "my_bookings")
async def my_bookings_handler(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id

    await callback.answer()
    user_id = callback.from_user.id

    # Удаляем схему зала если есть
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, user_id, _schema_message_id)
            _schema_message_id = None
        except:
            pass

    await show_user_bookings(callback, state)

async def show_user_bookings(callback: types.CallbackQuery, state: FSMContext = None):
    """Показать список броней пользователя"""
    # Очищаем завершенные брони перед показом
    logger.debug("Очистка завершенных бронирований пропущена")

    user_id = callback.from_user.id
    user_bookings = await get_user_bookings(user_id)

    if not user_bookings:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Новая бронь", callback_data="new_booking")],
            [InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="booking")]
        ])

        try:
            await callback.message.edit_text(
                "📋 <b>Мои брони</b>\n\n"
                "У вас пока нет активных бронирований.",
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            await callback.bot.send_message(
                user_id,
                "📋 <b>Мои брони</b>\n\n"
                "У вас пока нет активных бронирований.",
                reply_markup=kb,
                parse_mode="HTML"
            )
        return

    # Показываем только активные брони (после очистки)
    text = "📋 <b>Мои брони</b>\n\n"

    if user_bookings:
        text += f"✅ <b>Активные брони ({len(user_bookings)}):</b>\n"
        for i, booking in enumerate(user_bookings, 1):
            status = BOOKING_STATUSES.get(booking.get('status_code', 0), f"Статус: {booking.get('status_code', 0)}")
            text += f"{i}. {booking.get('date_display', 'Дата')} - {booking.get('time', 'Время')}\n"
            text += f"   Гостей: {booking.get('guests', 0)}, Стол: {booking.get('table_name', '—')}\n"
            text += f"   {status}\n\n"

    kb_rows = []

    # Кнопки для активных броней
    for i, booking in enumerate(user_bookings[:5], 1):  # Ограничим 5 бронями
        kb_rows.append([InlineKeyboardButton(
            text=f"📅 Бронь {i}: {booking.get('date_display', '')} {booking.get('time', '')}",
            callback_data=f"booking_details:{booking.get('external_id', '')}"
        )])

    # Общие кнопки
    kb_rows.append([InlineKeyboardButton(text="➕ Новая бронь", callback_data="new_booking")])
    kb_rows.append([InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")])
    kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="booking")])

    try:
        await callback.message.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления

    try:
        await callback.bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение списка броней: {e}")

    if state:
        await state.set_state(BookingStates.managing_booking)

@router.callback_query(F.data.startswith("booking_details:"))
async def booking_details_callback(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    external_id = callback.data.split(":", 1)[1]
    
    # Удаляем схему зала если есть
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
            _schema_message_id = None
        except:
            pass
    
    # Получаем информацию о брони
    booking_info = get_booking_info(external_id)
    
    if not booking_info:
        # Если API не работает, покажем локальную информацию
        user_id = callback.from_user.id
        user_bookings = await get_user_bookings(user_id)
        
        for booking in user_bookings:
            if booking.get('external_id') == external_id:
                status_code = booking.get('status_code', 0)
                status_text = BOOKING_STATUSES.get(status_code, f"Статус: {status_code}")
                
                text = (
                    f"📋 <b>Детали бронирования</b>\n\n"
                    f"<b>Статус:</b> {status_text}\n\n"
                    f"<b>📅 Дата:</b> {booking.get('date_display', '—')}\n"
                    f"<b>🕐 Время:</b> {booking.get('time', '—')}\n"
                    f"<b>👥 Гостей:</b> {booking.get('guests', 0)}\n"
                    f"<b>🪑 Стол:</b> №{booking.get('table_name', '—')}\n\n"
                    f"<i>⚠️ Не удалось получить полную информацию от сервера бронирования</i>"
                )
                
                kb_rows = []
                # Проверяем статус для показа кнопок действий
                if status_code not in [40, 45, 220]:  # Не отмененные/не пришедшие
                    kb_rows.append([InlineKeyboardButton(text="✏️ Редактировать бронь", callback_data=f"edit_booking:{external_id}")])
                    kb_rows.append([InlineKeyboardButton(text="❌ Отменить бронь", callback_data=f"cancel_booking:{external_id}")])
                
                kb_rows.append([InlineKeyboardButton(text="📋 Все мои брони", callback_data="my_bookings")])
                kb_rows.append([InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")])
                kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="booking")])
                
                await update_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML", bot=callback.bot)
                await state.set_state(BookingStates.managing_booking)
                return
        
        await update_message(callback.from_user.id,
                            "❌ Не удалось найти информацию о брони.\n"
                            "Попробуйте обновить список броней.",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="📋 Обновить список", callback_data="my_bookings")],
                                [InlineKeyboardButton(text="📞 Админ", callback_data="call_admin")],
                                [InlineKeyboardButton(text="⬅️ Назад", callback_data="booking")]
                            ]),
                            parse_mode="HTML",
                            bot=callback.bot)
        return
    
    # Получаем статус
    state_info = get_booking_state(external_id)
    status_code = state_info.get('state', 0) if state_info else 0
    status_text = BOOKING_STATUSES.get(status_code, f"Статус: {status_code}")
    
    # Получаем данные о брони из ответа API
    # ВНИМАНИЕ: booking_info уже содержит данные, не нужно искать booking_info.get('order', {})
    booking_data = booking_info  # Прямой доступ к данным
    
    customer = booking_data.get('customer', {})
    booking_details = booking_data.get('booking', {})
    
    # Форматируем дату и время из одного поля datetime
    datetime_str = booking_data.get('datetime', '')
    date_display = "—"
    time_display = "—"
    
    if datetime_str:
        try:
            dt_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
            date_display = dt_obj.strftime("%d.%m.%Y")
            time_display = dt_obj.strftime("%H:%M")
        except Exception as e:
            print(f"Ошибка парсинга даты {datetime_str}: {e}")
            # Пытаемся разобрать другими способами
            try:
                dt_obj = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                date_display = dt_obj.strftime("%d.%m.%Y")
                time_display = dt_obj.strftime("%H:%M")
            except:
                date_display = datetime_str[:10] if len(datetime_str) >= 10 else "—"
                time_display = datetime_str[11:16] if len(datetime_str) >= 16 else "—"
    
    # Получаем количество гостей (может быть строкой или числом)
    guests = booking_details.get('visitors', 0)
    if isinstance(guests, str):
        try:
            guests = int(guests)
        except:
            guests = 0
    
    # Получаем номер стола
    table_num = booking_details.get('table', '—')
    
    # Формируем имя клиента (фамилия + имя)
    customer_name = "—"
    if customer:
        lastname = customer.get('lastname', '')
        firstname = customer.get('name', '')
        if lastname and firstname:
            customer_name = f"{lastname} {firstname}"
        elif lastname:
            customer_name = lastname
        elif firstname:
            customer_name = firstname
    
    # Формируем текст (БЕЗ ID брони и зала)
    text = (
        f"📋 <b>Детали бронирования</b>\n\n"
        f"<b>Статус:</b> {status_text}\n\n"
        f"<b>📅 Дата:</b> {date_display}\n"
        f"<b>🕐 Время:</b> {time_display}\n"
        f"<b>👥 Гостей:</b> {guests}\n"
        f"<b>🪑 Стол:</b> №{table_num}\n\n"
        f"<b>👤 Клиент:</b>\n"
        f"• Имя: {customer_name}\n"
        f"• Телефон: {customer.get('phone', '—')}"
    )
    
    # Создаем меню управления
    kb_rows = []
    
    # Кнопки действий (только для активных броней)
    if status_code not in [40, 45, 220]:  # Не отмененные/не пришедшие/отмененные
        kb_rows.append([InlineKeyboardButton(text="✏️ Редактировать бронь", callback_data=f"edit_booking:{external_id}")])
        kb_rows.append([InlineKeyboardButton(text="❌ Отменить бронь", callback_data=f"cancel_booking:{external_id}")])
    
    kb_rows.append([InlineKeyboardButton(text="🔄 Обновить статус", callback_data=f"refresh_booking:{external_id}")])
    kb_rows.append([InlineKeyboardButton(text="📋 Все мои брони", callback_data="my_bookings")])
    kb_rows.append([InlineKeyboardButton(text="📞 Админ", callback_data="call_admin")])
    kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="booking")])
    
    try:
        await callback.message.delete()
    except Exception:
        pass

    try:
        await callback.bot.send_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Не удалось отправить детали брони: {e}")

    await state.set_state(BookingStates.managing_booking)

@router.callback_query(F.data.startswith("edit_booking:"))
async def edit_booking_callback(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    external_id = callback.data.split(":", 1)[1]
    
    # Удаляем схему зала если есть
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
            _schema_message_id = None
        except:
            pass
    
    text = (
        "✏️ <b>Редактирование бронирования</b>\n\n"
        "Изменение брони через систему пока не поддерживается.\n\n"
        "✅ <b>Рекомендуем:</b>\n"
        "1. Отменить текущую бронь\n"
        "2. Создать новую бронь с нужными параметрами\n\n"
        "Для этого нажмите кнопку ниже."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить и создать новую бронь", callback_data=f"cancel_and_new:{external_id}")],
        [InlineKeyboardButton(text="⬅️ Назад к деталям", callback_data=f"booking_details:{external_id}")]
    ])
    
    await update_message(callback.from_user.id, text, reply_markup=kb, parse_mode="HTML", bot=callback.bot)
    await state.set_state(BookingStates.editing_booking)

@router.callback_query(F.data.startswith("cancel_and_new:"))
async def cancel_and_new_booking(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    external_id = callback.data.split(":", 1)[1]
    
    # Сначала отменяем бронь
    result = cancel_booking(external_id)
    
    if result:
        # Обновляем статус в локальном хранилище
        user_id = callback.from_user.id
        if user_id in _user_bookings:
            for booking in _user_bookings[user_id]:
                if booking.get('external_id') == external_id:
                    booking['status_code'] = 220  # Отменен
                    break
        
        text = (
            "✅ <b>Бронь отменена</b>\n\n"
            "Теперь вы можете создать новую бронь с нужными параметрами.\n\n"
            "Нажмите на кнопку ниже, чтобы начать процесс бронирования заново."
        )
    else:
        text = (
            "❌ <b>Не удалось отменить бронь</b>\n\n"
            "Попробуйте создать новую бронь без отмены текущей."
        )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать новую бронь", callback_data="new_booking")],
        [InlineKeyboardButton(text="📋 Мои брони", callback_data="my_bookings")],
        [InlineKeyboardButton(text="📞 Админ", callback_data="call_admin")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")]
    ])
    
    await update_message(callback.from_user.id, text, reply_markup=kb, parse_mode="HTML", bot=callback.bot)
    await state.clear()

@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking_callback(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    external_id = callback.data.split(":", 1)[1]
    
    # Удаляем схему зала если есть
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
            _schema_message_id = None
        except:
            pass
    
    # Получаем информацию о брони для подтверждения
    booking_info = get_booking_info(external_id)
    if not booking_info:
        # Если API не работает, пробуем найти в локальном хранилище
        user_id = callback.from_user.id
        user_bookings = await get_user_bookings(user_id)
        
        for booking in user_bookings:
            if booking.get('external_id') == external_id:
                # Формируем информацию из локальных данных
                text = (
                    "❌ <b>Отмена бронирования</b>\n\n"
                    f"<b>Вы уверены, что хотите отменить бронь?</b>\n\n"
                    f"<b>Детали брони:</b>\n"
                    f"• Дата: {booking.get('date_display', '—')}\n"
                    f"• Время: {booking.get('time', '—')}\n"
                    f"• Гостей: {booking.get('guests', 0)}\n"
                    f"• Стол: №{booking.get('table_name', '—')}\n\n"
                    "<i>После отмены восстановить бронь будет невозможно.</i>"
                )
                
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Да, отменить бронь", callback_data=f"confirm_cancel:{external_id}")],
                    [InlineKeyboardButton(text="❌ Нет, вернуться назад", callback_data=f"booking_details:{external_id}")]
                ])
                
                await update_message(callback.from_user.id, text, reply_markup=kb, parse_mode="HTML", bot=callback.bot)
                await state.set_state(BookingStates.canceling_booking)
                return
        
        await update_message(callback.from_user.id,
                            "❌ Не удалось получить информацию о брони.",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="⬅️ Назад к деталям", callback_data=f"booking_details:{external_id}")]
                            ]),
                            parse_mode="HTML",
                            bot=callback.bot)
        return
    
    # Получаем данные из API
    booking_data = booking_info
    customer = booking_data.get('customer', {})
    booking_details = booking_data.get('booking', {})
    
    # Форматируем дату и время
    datetime_str = booking_data.get('datetime', '')
    try:
        dt_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
        date_display = dt_obj.strftime("%d.%m.%Y")
        time_display = dt_obj.strftime("%H:%M")
    except:
        date_display = datetime_str[:10] if len(datetime_str) >= 10 else "—"
        time_display = datetime_str[11:16] if len(datetime_str) >= 16 else "—"
    
    # Получаем количество гостей
    guests = booking_details.get('visitors', 0)
    table_num = booking_details.get('table', '—')
    
    text = (
        "❌ <b>Отмена бронирования</b>\n\n"
        f"<b>Вы уверены, что хотите отменить бронь?</b>\n\n"
        f"<b>Детали брони:</b>\n"
        f"• Дата: {date_display}\n"
        f"• Время: {time_display}\n"
        f"• Гостей: {guests}\n"
        f"• Стол: №{table_num}\n"
        "<i>После отмены восстановить бронь будет невозможно.</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отменить бронь", callback_data=f"confirm_cancel:{external_id}")],
        [InlineKeyboardButton(text="❌ Нет, вернуться назад", callback_data=f"booking_details:{external_id}")]
    ])
    
    await update_message(callback.from_user.id, text, reply_markup=kb, parse_mode="HTML", bot=callback.bot)
    await state.set_state(BookingStates.canceling_booking)

@router.callback_query(F.data.startswith("confirm_cancel:"))
async def confirm_cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    external_id = callback.data.split(":", 1)[1]
    
    # Удаляем схему зала если есть
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
            _schema_message_id = None
        except:
            pass
    
    # Отменяем бронирование
    result = cancel_booking(external_id)
    
    if result:
        text = (
            "✅ <b>Бронирование отменено</b>\n\n"
            "Ваше бронирование было успешно отменено.\n\n"
            "<i>Будем рады видеть вас в другой раз!</i>"
        )
        
        # Обновляем статус в локальном хранилище
        user_id = callback.from_user.id
        if user_id in _user_bookings:
            for booking in _user_bookings[user_id]:
                if booking.get('external_id') == external_id:
                    booking['status_code'] = 220  # Отменен
                    break
    else:
        text = (
            "❌ <b>Не удалось отменить бронирование</b>\n\n"
            "Попробуйте позже или свяжитесь с администратором."
        )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои брони", callback_data="my_bookings")],
        [InlineKeyboardButton(text="➕ Новая бронь", callback_data="new_booking")],
        [InlineKeyboardButton(text="📞 Админ", callback_data="call_admin")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")]
    ])
    
    await update_message(callback.from_user.id, text, reply_markup=kb, parse_mode="HTML", bot=callback.bot)
    await state.clear()

@router.callback_query(F.data.startswith("refresh_booking:"))
async def refresh_booking_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Обновляю информацию...")
    external_id = callback.data.split(":", 1)[1]
    
    # Обновляем информацию о брони
    booking_info = get_booking_info(external_id)
    state_info = get_booking_state(external_id)
    
    if booking_info and state_info:
        status_code = state_info.get('state', 0)
        status_text = BOOKING_STATUSES.get(status_code, f"Статус: {status_code}")
        
        # Обновляем статус в локальном хранилище
        user_id = callback.from_user.id
        if user_id in _user_bookings:
            for booking in _user_bookings[user_id]:
                if booking.get('external_id') == external_id:
                    booking['status_code'] = status_code
                    break
        
        # Если статус завершенный, удаляем из списка
        if status_code in [40, 45, 180, 200, 220]:
            logger.debug("Очистка завершенных бронирований пропущена")
            text = (
                "🔄 <b>Бронирование завершено</b>\n\n"
                f"<b>Текущий статус:</b> {status_text}\n\n"
                "<i>Эта бронь была автоматически удалена из списка активных.</i>"
            )
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Мои брони", callback_data="my_bookings")],
                [InlineKeyboardButton(text="➕ Новая бронь", callback_data="new_booking")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="booking")]
            ])
            
            await update_message(callback.from_user.id, text, reply_markup=kb, parse_mode="HTML", bot=callback.bot)
            return
    
    # Возвращаемся к деталям брони
    await booking_details_callback(callback, state)

def filter_tables_by_guests(available_tables: list, guests: int) -> list:
    """
    Фильтрует список доступных столов по количеству гостей.
    """
    filtered_tables = []
    for table in available_tables:
        table_name = table['name']
        try:
            table_num = int(table_name)
        except (ValueError, TypeError):
            table_num = 0

        if guests in [1, 2]:
            allowed_tables = [3, 4, 5, 7, 8, 10, 12, 14, 15, 16]
            if table_num in allowed_tables:
                filtered_tables.append(table)
        elif guests in [3, 4]:
            allowed_tables = [1, 2, 6, 11, 17, 18]
            if table_num in allowed_tables:
                filtered_tables.append(table)
        # Для гостей >=5 обработка идёт в другом месте (админ)
    return filtered_tables

@router.callback_query(F.data.startswith("guests:"), BookingStates.waiting_for_guests)
async def select_guests(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    guests = int(callback.data.split(":", 1)[1])
    if guests >= 5:
        text = (
            f"👥 <b>Бронирование на {guests} человек</b>\n\n"
            f"❌ <b>Автоматическое бронирование недоступно</b>\n\n"
            f"Бронь стола доступна в автоматическом режиме до 4 человек.\n"
            f"Для компании от 5 человек свяжитесь с оператором."
        )
        
        await update_message(
            callback.from_user.id,
            text,
            parse_mode="HTML",
            bot=callback.bot
        )
        
        # Показываем меню связи
        await call_admin(callback)
        await state.clear()
        return

    await state.update_data(guests=guests)

    # === НОВАЯ ЛОГИКА ДИАПАЗОНА ДАТ ===
    today = datetime.today()
    current_month_start = today.replace(day=1)
    next_month_start = (current_month_start + timedelta(days=32)).replace(day=1)
    two_months_ahead = (next_month_start + timedelta(days=32)).replace(day=1)
    next_month_end = two_months_ahead - timedelta(days=1)

    from_date = today.strftime("%d.%m.%Y")
    to_date = next_month_end.strftime("%d.%m.%Y")
    # ===================================

    print(f"📅 [Presto] Запрос календаря: {{'pointId': 3596, 'fromDate': '{from_date}', 'toDate': '{to_date}'}}")

    calendar_data = get_booking_calendar(from_date, to_date)
    if not calendar_data or not calendar_data.get("dates"):
        await update_message(
            callback.from_user.id,
            "❌ Нет доступных дат для бронирования.\n"
            "Пожалуйста, попробуйте позже или свяжитесь с администратором.",
            reply_markup=keyboards.back_to_main(),
            bot=callback.bot
        )
        await state.clear()
        return

    await state.update_data(presto_calendar=calendar_data)
    await show_date_selection(callback.from_user.id, callback.bot, state)

async def show_date_selection(user_id: int, bot, state: FSMContext):
    now = date.today()
    year = now.year
    month = now.month
    min_date = now

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    # Заголовок — русский месяц
    month_name = RU_MONTHS[month]
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore")
    ])

    # Дни недели
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=wd, callback_data="ignore") for wd in weekdays
    ])

    # Дни месяца
    month_days = calendar.monthcalendar(year, month)
    for week in month_days:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                date_obj = date(year, month, day)
                str_date = f"{day:02d}.{month:02d}.{year}"
                if date_obj < min_date:
                    row.append(InlineKeyboardButton(text="✕", callback_data="ignore"))
                else:
                    row.append(InlineKeyboardButton(text=str(day), callback_data=f"sel_date:{str_date}"))
        kb.inline_keyboard.append(row)

    # Навигация
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    kb.inline_keyboard.append([
        InlineKeyboardButton(text="←", callback_data=f"nav_cal:{prev_year}:{prev_month}"),
        InlineKeyboardButton(text="→", callback_data=f"nav_cal:{next_year}:{next_month}")
    ])

    await update_message(
        user_id,
        "📅 <b>Выберите дату бронирования</b>",
        reply_markup=kb,
        parse_mode="HTML",
        bot=bot
    )
    await state.set_state(BookingStates.waiting_for_date)

@router.callback_query(F.data.startswith("nav_cal:"), BookingStates.waiting_for_date)
async def navigate_calendar(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    _, year, month = callback.data.split(":")
    year, month = int(year), int(month)
    min_date = date.today()

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    month_name = RU_MONTHS[month]
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore")
    ])

    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=wd, callback_data="ignore") for wd in weekdays
    ])

    month_days = calendar.monthcalendar(year, month)
    for week in month_days:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                date_obj = date(year, month, day)
                str_date = f"{day:02d}.{month:02d}.{year}"
                if date_obj < min_date:
                    row.append(InlineKeyboardButton(text="✕", callback_data="ignore"))
                else:
                    row.append(InlineKeyboardButton(text=str(day), callback_data=f"sel_date:{str_date}"))
        kb.inline_keyboard.append(row)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    kb.inline_keyboard.append([
        InlineKeyboardButton(text="←", callback_data=f"nav_cal:{prev_year}:{prev_month}"),
        InlineKeyboardButton(text="→", callback_data=f"nav_cal:{next_year}:{next_month}")
    ])

    await callback.message.edit_reply_markup(reply_markup=kb)

@router.callback_query(F.data.startswith("sel_date:"), BookingStates.waiting_for_date)
async def select_date(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    selected_date = callback.data.split(":", 1)[1]  # формат: DD.MM.YYYY
    await state.update_data(selected_date=selected_date)

    # Остальной код — как был
    data = await state.get_data()
    calendar_data = data.get("presto_calendar", {})
    hall_info = None
    for entry in calendar_data.get("dates", []):
        if isinstance(entry, dict) and "date" in entry:
            entry_date_str = entry.get("date", "")
            try:
                entry_date = None
                for fmt in ["%d.%m.%Y", "%Y-%m-%d"]:
                    try:
                        entry_date = datetime.strptime(entry_date_str, fmt)
                        break
                    except ValueError:
                        continue
                selected_date_dt = datetime.strptime(selected_date, "%d.%m.%Y")
                if entry_date and entry_date.date() == selected_date_dt.date():
                    hall_info = entry.get("halls", {})
                    break
            except Exception:
                continue

    if not hall_info:
        await update_message(callback.from_user.id,
            "❌ Нет доступных залов на выбранную дату.",
            reply_markup=keyboards.back_to_main(),
            bot=callback.bot)
        return

    try:
        hall_id_str = next(iter(hall_info.keys()))
        hall_id = int(hall_id_str)
        await state.update_data(hall_id=hall_id)
    except Exception as e:
        await update_message(callback.from_user.id,
            "❌ Ошибка обработки информации о зале.",
            reply_markup=keyboards.back_to_main(),
            bot=callback.bot)
        return

    await show_time_categories(callback.from_user.id, callback.bot, state)

async def show_time_categories(user_id: int, bot, state: FSMContext):
    data = await state.get_data()
    selected_date = data.get("selected_date")
    guests = data.get("guests", 1)
    
    try:
        dt_obj = datetime.strptime(selected_date, "%d.%m.%Y")
        api_date = dt_obj.strftime("%Y-%m-%d")
        
        # Проверяем доступность для всех трех категорий времени
        time_categories = []
        
        # Проверяем утро (08:00)
        test_tables = get_available_tables(f"{api_date} 08:00:00", guests)
        if test_tables:
            filtered = filter_tables_by_guests(test_tables, guests)
            if filtered:
                time_categories.append("morning")
        
        # Проверяем обед (12:00)
        test_tables = get_available_tables(f"{api_date} 12:00:00", guests)
        if test_tables:
            filtered = filter_tables_by_guests(test_tables, guests)
            if filtered:
                time_categories.append("lunch")
        
        # Проверяем вечер (18:00)
        test_tables = get_available_tables(f"{api_date} 18:00:00", guests)
        if test_tables:
            filtered = filter_tables_by_guests(test_tables, guests)
            if filtered:
                time_categories.append("evening")
        
        if not time_categories:
            await update_message(user_id,
                                "❌ Нет доступных временных интервалов.",
                                reply_markup=keyboards.back_to_main(),
                                bot=bot)
            return
        
        kb = []
        for category in time_categories:
            kb.append([InlineKeyboardButton(
                text=category_names.get(category, category),
                callback_data=f"time_cat:{category}"
            )])
        
        kb.append([InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")])
        kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="new_booking")])
        kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")])
        
        await update_message(user_id,
                            "🕒 <b>Выберите удобное время</b>",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                            parse_mode="HTML",
                            bot=bot)
        await state.set_state(BookingStates.waiting_for_time_category)
        
    except Exception as e:
        await update_message(user_id,
                            "❌ Ошибка при загрузке временных интервалов.",
                            reply_markup=keyboards.back_to_main(),
                            bot=bot)

@router.callback_query(F.data.startswith("time_cat:"), BookingStates.waiting_for_time_category)
async def select_time_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    category = callback.data.split(":", 1)[1]
    await state.update_data(selected_time_category=category)
    
    data = await state.get_data()
    selected_date = data.get("selected_date")
    guests = data.get("guests", 1)
    
    # Определяем временные слоты для категории
    time_slots = []
    if category == "morning":
        time_slots = ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]
    elif category == "lunch":
        time_slots = ["12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]
    elif category == "evening":
        time_slots = ["16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30"]
    
    # Показываем времена по 4 в ряд
    kb = []
    for i in range(0, len(time_slots), 4):
        row = []
        for j in range(4):
            if i + j < len(time_slots):
                time_slot = time_slots[i + j]
                row.append(InlineKeyboardButton(
                    text=time_slot,
                    callback_data=f"sel_time:{time_slot}"
                ))
        kb.append(row)
    
    kb.append([InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="new_booking")])
    kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")])
    
    await update_message(callback.from_user.id,
                        f"🕐 <b>Выберите точное время</b>\n\n"
                        f"Вы выбрали: {category_names.get(category, category)}",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                        parse_mode="HTML",
                        bot=callback.bot)
    await state.set_state(BookingStates.waiting_for_time)

@router.callback_query(F.data.startswith("sel_time:"), BookingStates.waiting_for_time)
async def select_time(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    time_slot = callback.data.split(":", 1)[1]
    await state.update_data(selected_time=time_slot)
    
    data = await state.get_data()
    selected_date = data.get("selected_date")
    guests = data.get("guests", 1)
    
    try:
        async with typing_indicator(callback.bot, callback.from_user.id):
            dt_obj = datetime.strptime(selected_date, "%d.%m.%Y")
            api_date = dt_obj.strftime("%Y-%m-%d")
            datetime_api = f"{api_date} {time_slot}:00"
            
            # ПРОВЕРЯЕМ доступность столов только после выбора времени
            available_tables = get_available_tables(datetime_api, guests)
            filtered_tables = filter_tables_by_guests(available_tables, guests)
        
        if not filtered_tables:
            await callback.message.edit_text(
                f"❌ Нет доступных столов на {time_slot}.\n"
                "Пожалуйста, выберите другое время.",
                reply_markup=keyboards.back_to_main()
            )
            return
        
        await state.update_data(booking_datetime=datetime_api, filtered_tables=filtered_tables)
        
        # РЕДАКТИРУЕМ сообщение на схему зала с кнопками столов
        schema_text = "🪑 <b>Схема зала и выбор столика</b>\n\n"
        
        if PIL_AVAILABLE:
            hall_data = get_hall_tables(datetime_api)
            if hall_data and hall_data.get("halls"):
                schema_id = f"hall_{callback.from_user.id}_{int(datetime.now().timestamp())}"
                image_path, free_table_ids = generate_hall_schema(
                    hall_data, 
                    guests, 
                    schema_id,
                    selected_date,
                    time_slot
                )
                
                if image_path and os.path.exists(image_path):
                    try:
                        photo = FSInputFile(image_path)
                        
                        # Создаем кнопки выбора столиков по 4 в ряд
                        kb = []
                        row = []
                        for table in filtered_tables:
                            row.append(InlineKeyboardButton(
                                text=f"🪑 {table['name']}",
                                callback_data=f"sel_table:{table['id']}"
                            ))
                            if len(row) == 4:
                                kb.append(row)
                                row = []
                        
                        # Добавляем оставшиеся кнопки, если есть
                        if row:
                            kb.append(row)
                        
                        # Дополнительные кнопки
                        if filtered_tables:
                            kb.append([InlineKeyboardButton(
                                text="🎲 ВЫБРАТЬ ЛЮБОЙ СТОЛ",
                                callback_data="random_table"
                            )])
                        
                        kb.append([InlineKeyboardButton(text="⬅️ ВЫБРАТЬ ДРУГОЕ ВРЕМЯ", callback_data="back_to_time_selection")])
                        kb.append([InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_booking")])
                        
                        # Удаляем старое сообщение и отправляем новое с фото
                        await callback.message.delete()
                        
                        sent_message = await callback.bot.send_photo(
                            chat_id=callback.from_user.id,
                            photo=photo,
                            caption=schema_text + 
                                    "🟢 — свободен и доступен для брони\n"
                                    "🔴 — занят\n"
                                    "⚫ — бронь недоступна\n\n"
                                    "👇 <b>Выберите стол:</b>",
                            parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
                        )
                        _schema_message_id = sent_message.message_id
                        
                        await state.set_state(BookingStates.waiting_for_table)
                        return
                        
                    except Exception as e:
                        print(f"Ошибка отправки схемы: {e}")
        
        # Если схема не удалась, редактируем на кнопки выбора столиков
        kb = []
        row = []
        for table in filtered_tables:
            row.append(InlineKeyboardButton(
                text=f"🪑 Стол {table['name']}",
                callback_data=f"sel_table:{table['id']}"
            ))
            if len(row) == 4:
                kb.append(row)
                row = []
        
        if row:
            kb.append(row)
        
        if filtered_tables:
            kb.append([InlineKeyboardButton(
                text="🎲 ВЫБРАТЬ ЛЮБОЙ СТОЛ",
                callback_data="random_table"
            )])
        
        if not kb:
            kb.append([InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")])
        
        kb.append([InlineKeyboardButton(text="⬅️ Выбрать другое время", callback_data="back_to_time_selection")])
        kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")])
        
        await callback.message.edit_text(
            "👇 <b>Выберите стол:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML"
        )
        await state.set_state(BookingStates.waiting_for_table)
        
    except Exception as e:
        await callback.message.edit_text(
            "❌ Ошибка при обработке времени.",
            reply_markup=keyboards.back_to_main()
        )

@router.callback_query(F.data == "back_to_time_selection")
async def back_to_time_selection(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    
    # Удаляем схему зала при возврате
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
            _schema_message_id = None
        except Exception:
            pass
    
    data = await state.get_data()
    selected_time_category = data.get("selected_time_category", "evening")
    
    # Возвращаемся к выбору времени в той же категории
    time_slots = []
    if selected_time_category == "morning":
        time_slots = ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]
    elif selected_time_category == "lunch":
        time_slots = ["12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]
    elif selected_time_category == "evening":
        time_slots = ["16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30"]
    
    # Показываем времена по 4 в ряд
    kb = []
    for i in range(0, len(time_slots), 4):
        row = []
        for j in range(4):
            if i + j < len(time_slots):
                time_slot_option = time_slots[i + j]
                row.append(InlineKeyboardButton(
                    text=time_slot_option,
                    callback_data=f"sel_time:{time_slot_option}"
                ))
        kb.append(row)
    
    kb.append([InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="new_booking")])
    kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")])
    
    try:
        await callback.message.edit_text(
            f"🕐 <b>Выберите точное время</b>\n\n"
            f"Вы выбрали: {category_names.get(selected_time_category, selected_time_category)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML"
        )
    except:
        # Если редактирование не удалось, удаляем и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        await callback.bot.send_message(
            callback.from_user.id,
            f"🕐 <b>Выберите точное время</b>\n\n"
            f"Вы выбрали: {category_names.get(selected_time_category, selected_time_category)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML"
        )
    
    await state.set_state(BookingStates.waiting_for_time)

@router.callback_query(F.data.startswith("sel_time_back:"))
async def select_time_back(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    
    # Удаляем схему зала при возврате
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
            _schema_message_id = None
        except Exception:
            pass
    
    time_slot = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected_time_category = data.get("selected_time_category", "evening")
    
    # Возвращаемся к выбору времени в той же категории
    time_slots = []
    if selected_time_category == "morning":
        time_slots = ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]
    elif selected_time_category == "lunch":
        time_slots = ["12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]
    elif selected_time_category == "evening":
        time_slots = ["16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30"]
    
    # Показываем времена по 4 в ряд
    kb = []
    for i in range(0, len(time_slots), 4):
        row = []
        for j in range(4):
            if i + j < len(time_slots):
                time_slot_option = time_slots[i + j]
                row.append(InlineKeyboardButton(
                    text=time_slot_option,
                    callback_data=f"sel_time:{time_slot_option}"
                ))
        kb.append(row)
    
    kb.append([InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="new_booking")])
    kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")])
    
    await update_message(callback.from_user.id,
                        f"🕐 <b>Выберите точное время</b>\n\n"
                        f"Вы выбрали: {category_names.get(selected_time_category, selected_time_category)}",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                        parse_mode="HTML",
                        bot=callback.bot)
    await state.set_state(BookingStates.waiting_for_time)

@router.callback_query(F.data == "random_table", BookingStates.waiting_for_table)
async def select_random_table(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    
    data = await state.get_data()
    filtered_tables = data.get("filtered_tables", [])
    
    if not filtered_tables:
        try:
            await callback.message.edit_text(
                "❌ Нет доступных столов для выбора.",
                reply_markup=keyboards.back_to_main()
            )
        except:
            await callback.message.delete()
            await callback.bot.send_message(
                callback.from_user.id,
                "❌ Нет доступных столов для выбора.",
                reply_markup=keyboards.back_to_main()
            )
        return
    
    random_table = random.choice(filtered_tables)
    table_id = random_table['id']
    
    await state.update_data(selected_table=table_id, selected_table_name=random_table['name'])
    
    user_data = database.get_user_data(callback.from_user.id)
    
    try:
        dt_obj = datetime.strptime(data['selected_date'], "%d.%m.%Y")
        display_date = dt_obj.strftime("%d.%m.%Y")
    except:
        display_date = data['selected_date']
    
    text = (
        f"🎲 <b>Выбран случайный стол</b>\n\n"
        f"✅ <b>Подтвердите бронирование</b>\n\n"
        f"📅 Дата: {display_date}\n"
        f"🕐 Время: {data['selected_time']}\n"
        f"👥 Гостей: {data['guests']}\n"
        f"🪑 Стол: №{random_table['name']} (до {random_table['capacity']} гостей)\n"
        f"👤 Имя: {user_data['full_name'] if user_data else '—'}\n"
        f"📞 Телефон: {user_data['phone'] if user_data else '—'}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить бронь", callback_data="confirm_booking")],
        [InlineKeyboardButton(text="📞 Админ", callback_data="call_admin")],
        [InlineKeyboardButton(text="⬅️ Выбрать другой стол", callback_data="back_to_time_selection")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")]
    ])
    
    # Всегда создаем новое сообщение, удаляем старое
    _schema_message_id = None

    try:
        await callback.message.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления

    try:
        await callback.bot.send_message(
            callback.from_user.id,
            text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение подтверждения: {e}")
    
    await state.set_state(BookingStates.waiting_for_confirmation)

@router.callback_query(F.data.startswith("sel_table:"), BookingStates.waiting_for_table)
async def select_table(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer()
    table_id = int(callback.data.split(":", 1)[1])
    
    data = await state.get_data()
    filtered_tables = data.get("filtered_tables", [])
    
    selected_table = None
    for table in filtered_tables:
        if table['id'] == table_id:
            selected_table = table
            break
    
    if not selected_table:
        try:
            await callback.message.edit_text(
                "❌ Выбранный стол больше не доступен.",
                reply_markup=keyboards.back_to_main()
            )
        except:
            await callback.message.delete()
            await callback.bot.send_message(
                callback.from_user.id,
                "❌ Выбранный стол больше не доступен.",
                reply_markup=keyboards.back_to_main()
            )
        return
    
    await state.update_data(selected_table=table_id, selected_table_name=selected_table['name'])
    
    user_data = database.get_user_data(callback.from_user.id)
    
    try:
        dt_obj = datetime.strptime(data['selected_date'], "%d.%m.%Y")
        display_date = dt_obj.strftime("%d.%m.%Y")
    except:
        display_date = data['selected_date']
    
    text = (
        f"✅ <b>Подтвердите бронирование</b>\n\n"
        f"📅 Дата: {display_date}\n"
        f"🕐 Время: {data['selected_time']}\n"
        f"👥 Гостей: {data['guests']}\n"
        f"🪑 Стол: №{selected_table['name']} (до {selected_table['capacity']} гостей)\n"
        f"👤 Имя: {user_data['full_name'] if user_data else '—'}\n"
        f"📞 Телефон: {user_data['phone'] if user_data else '—'}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить бронь", callback_data="confirm_booking")],
        [InlineKeyboardButton(text="📞 Админ", callback_data="call_admin")],
        [InlineKeyboardButton(text="⬅️ Назад к выбору стола", callback_data="back_to_time_selection")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")]
    ])
    
    # Пытаемся отредактировать сообщение, если не получается - удаляем и отправляем новое
    try:
        if _schema_message_id and callback.message.message_id == _schema_message_id:
            # Если это сообщение со схемой (фото), удаляем его и отправляем новое
            await callback.message.delete()
            await callback.bot.send_message(
                callback.from_user.id, 
                text, 
                reply_markup=kb, 
                parse_mode="HTML"
            )
            _schema_message_id = None
        else:
            # Обычное редактирование текстового сообщения
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        # Если редактирование не удалось, удаляем и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        await callback.bot.send_message(
            callback.from_user.id, 
            text, 
            reply_markup=kb, 
            parse_mode="HTML"
        )
        _schema_message_id = None
    
    await state.set_state(BookingStates.waiting_for_confirmation)

@router.callback_query(F.data == "confirm_booking", BookingStates.waiting_for_confirmation)
async def confirm_booking(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id
    
    await callback.answer("Обрабатываем бронирование...", show_alert=False)
    
    data = await state.get_data()
    user_data = database.get_user_data(callback.from_user.id)
    
    if not user_data or not user_data.get('phone'):
        try:
            await callback.message.edit_text(
                "❌ Ошибка: пользователь не найден.",
                reply_markup=keyboards.back_to_main()
            )
        except:
            await callback.message.delete()
            await callback.bot.send_message(
                callback.from_user.id,
                "❌ Ошибка: пользователь не найден.",
                reply_markup=keyboards.back_to_main()
            )
        await state.clear()
        return
    
    try:
        async with typing_indicator(callback.bot, callback.from_user.id):
            result = create_booking(
                phone=user_data["phone"],
                name=user_data.get("full_name", "Гость"),
                datetime_str=data['booking_datetime'],
                visitors=data['guests'],
                hall_id=data['hall_id'],
                point_id=3596,
                table_id=data.get('selected_table'),
                comment=f"Бронь через Telegram бот. Пользователь: @{callback.from_user.username}"
            )
        
        # Удаляем схему зала
        if _schema_message_id:
            try:
                await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
                _schema_message_id = None
            except:
                pass
        
        if result:
            try:
                dt_obj = datetime.strptime(data['selected_date'], "%d.%m.%Y")
                display_date = dt_obj.strftime("%d.%m.%Y")
            except:
                display_date = data['selected_date']
            
            # Пытаемся извлечь ID из ответа
            external_id = None
            
            # Проверяем извлеченный ID
            if '_extracted_id' in result:
                external_id = result['_extracted_id']
                print(f"🎯 [Bot] Используем извлеченный ID: {external_id}")
            else:
                # Ищем ID вручную
                search_paths = [
                    ('id',),
                    ('order', 'id'),
                    ('externalId',),
                    ('booking_id',),
                    ('bookingId',),
                    ('reservationId',)
                ]
                
                for path in search_paths:
                    try:
                        value = result
                        for key in path:
                            value = value[key]
                        if value:
                            external_id = str(value)
                            print(f"🎯 [Bot] Найден ID по пути {path}: {external_id}")
                            break
                    except (KeyError, TypeError):
                        continue
            
            # Сохраняем информацию о брони
            if external_id:
                booking_info = {
                    'external_id': external_id,
                    'date_display': display_date,
                    'time': data['selected_time'],
                    'guests': data['guests'],
                    'table_name': data.get('selected_table_name', ''),
                    'status_code': 10,  # Онлайн-заказ
                    'datetime': data['booking_datetime'],
                    'hall_id': data['hall_id'],
                    'table_id': data.get('selected_table')
                }
                
                await save_user_booking(callback.from_user.id, booking_info)
                
                success_text = (
                    f"🎉 <b>Бронь успешно создана!</b>\n\n"
                    f"📅 Дата: {display_date}\n"
                    f"🕐 Время: {data['selected_time']}\n"
                    f"👥 Гостей: {data['guests']}\n"
                    f"🪑 Стол: №{data.get('selected_table_name', '')}\n"
                    f"📋 ID брони: {external_id}\n\n"
                    f"📞 Контакты ресторана:\n"
                    f"<a href=\"tel:{clean_phone_for_link(config.RESTAURANT_PHONE)}\">{config.RESTAURANT_PHONE}</a>\n\n"
                    f"<i>Ждём вас с нетерпением! 😊</i>"
                )
            else:
                # Если ID не найден, показываем без него
                success_text = (
                    f"🎉 <b>Бронь успешно создана!</b>\n\n"
                    f"📅 Дата: {display_date}\n"
                    f"🕐 Время: {data['selected_time']}\n"
                    f"👥 Гостей: {data['guests']}\n"
                    f"🪑 Стол: №{data.get('selected_table_name', '')}\n\n"
                    f"📞 Контакты ресторана:\n"
                    f"<a href=\"tel:{clean_phone_for_link(config.RESTAURANT_PHONE)}\">{config.RESTAURANT_PHONE}</a>\n\n"
                    f"<i>Ждём вас с нетерпением! 😊</i>"
                )
                print(f"⚠️ [Bot] ID брони не найден в ответе API")
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Мои брони", callback_data="my_bookings")],
                [InlineKeyboardButton(text="➕ Новая бронь", callback_data="new_booking")],
                [InlineKeyboardButton(text="📞 Админ", callback_data="call_admin")],
                [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")]
            ])
            
            # Всегда создаем новое сообщение с результатом
            try:
                await callback.message.delete()
            except Exception:
                pass  # Игнорируем ошибки удаления

            try:
                await callback.bot.send_message(
                    callback.from_user.id,
                    success_text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение с результатом брони: {e}")
            
        else:
            try:
                await callback.message.edit_text(
                    "❌ Не удалось создать бронь.\n"
                    "Пожалуйста, свяжитесь с администратором.",
                    reply_markup=keyboards.back_to_main()
                )
            except:
                await callback.message.delete()
                await callback.bot.send_message(
                    callback.from_user.id,
                    "❌ Не удалось создать бронь.\n"
                    "Пожалуйста, свяжитесь с администратором.",
                    reply_markup=keyboards.back_to_main()
                )
    
    except Exception as e:
        print(f"Ошибка при создании брони: {e}")
        try:
            await callback.message.edit_text(
                "❌ Произошла ошибка при создании брони.\n"
                "Пожалуйста, попробуйте позже или свяжитесь с администратором.",
                reply_markup=keyboards.back_to_main()
            )
        except:
            await callback.message.delete()
            await callback.bot.send_message(
                callback.from_user.id,
                "❌ Произошла ошибка при создании брони.\n"
                "Пожалуйста, попробуйте позже или свяжитесь с администратором.",
                reply_markup=keyboards.back_to_main()
            )
    
    await state.clear()

@router.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    global _schema_message_id

    # Удаляем схему зала при возврате в главное меню
    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
            _schema_message_id = None
        except:
            pass

    # Очищаем режим чата с оператором при выходе из бронирования
    from .utils import clear_operator_chat
    clear_operator_chat(callback.from_user.id)

    from .handlers_main import show_main_menu
    await show_main_menu(callback.from_user.id, callback.bot)

def generate_hall_schema(hall_data: dict, guests: int, schema_id: str, selected_date: str, selected_time: str) -> tuple[str, list]:
    try:
        if not PIL_AVAILABLE:
            print("⚠️ Pillow не установлен, пропускаем генерацию схемы зала")
            return None, []

        hall = hall_data["halls"][0]
        items = hall.get("items", [])
        base_schema_path = os.path.join("files", "tables.png")
        if not os.path.exists(base_schema_path):
            return None, []

        img = Image.open(base_schema_path).convert("RGBA")
        width, height = img.size
        overlay = Image.new('RGBA', (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        rel = hall.get("relation", {})
        api_left = rel.get("left", 0)
        api_top = rel.get("top", 0)
        api_right = rel.get("right", 1000)
        api_bottom = rel.get("bottom", 800)
        api_width = api_right - api_left
        api_height = api_bottom - api_top
        scale_x = width / api_width if api_width > 0 else 1
        scale_y = height / api_height if api_height > 0 else 1

        free_table_ids = []

        # ✅ Определяем, какие номера столов разрешены
        allowed_table_numbers = set()
        if guests in (1, 2):
            allowed_table_numbers = {3, 4, 5, 7, 8, 10, 12, 14, 15, 16}
        elif guests in (3, 4):
            allowed_table_numbers = {1, 2, 6, 11, 17, 18}

        for item in items:
            if item.get("kind") != "table" or not item.get("visible", True):
                continue

            name = str(item.get("name", "?"))
            try:
                table_num = int(name)
            except (ValueError, TypeError):
                table_num = -1

            # ✅ ПРОПУСКАЕМ стол, если он НЕ в списке разрешённых для этого количества гостей
            if table_num not in allowed_table_numbers:
                continue

            api_x = item.get("x", 0)
            api_y = item.get("y", 0)
            x = (api_x - api_left) * scale_x
            y = (api_y - api_top) * scale_y
            capacity = item.get("capacity", 0)
            busy = item.get("busy", True)
            locked = item.get("isBookingLocked", False)

            if locked:
                color = (0, 0, 0, 200)
            elif busy:
                color = (255, 0, 0, 200)
            else:
                color = (0, 255, 0, 200)
                free_table_ids.append(item["id"])

            radius = 20
            draw.ellipse(
                [x - radius, y - radius, x + radius, y + radius],
                fill=color,
                outline=(255, 255, 255, 255),
                width=3
            )

            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except:
                font = ImageFont.load_default()

            try:
                left, top, right, bottom = font.getbbox(name)
                text_width = right - left
                text_height = bottom - top
            except:
                text_width, text_height = font.getsize(name)

            draw.text(
                (x - text_width / 2, y - text_height / 2),
                name,
                fill=(255, 255, 255, 255),
                font=font,
                stroke_width=1,
                stroke_fill=(0, 0, 0, 200)
            )

        # --- Наложение фона схемы ---
        img = Image.alpha_composite(img, overlay)

        # --- Текст с датой, временем, гостями ---
        try:
            font_large = ImageFont.truetype("arial.ttf", 20)
            font_small = ImageFont.truetype("arial.ttf", 16)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        try:
            dt_obj = datetime.strptime(selected_date, "%d.%m.%Y")
            display_date = dt_obj.strftime("%d.%m.%Y")
        except:
            display_date = selected_date

        date_text = f"Дата: {display_date}"
        time_text = f"Время: {selected_time}"
        guests_text = f"Гостей: {guests}"

        text_overlay = Image.new('RGBA', (width, height), (255, 255, 255, 0))
        text_draw = ImageDraw.Draw(text_overlay)

        try:
            left, top, right, bottom = font_large.getbbox(date_text)
            date_width = right - left
            left, top, right, bottom = font_small.getbbox(time_text)
            time_width = right - left
            left, top, right, bottom = font_small.getbbox(guests_text)
            guests_width = right - left
            max_width = max(date_width, time_width, guests_width)
        except:
            max_width = 200

        text_x = width - max_width - 20
        text_y = 20

        text_draw.rectangle(
            [text_x - 10, text_y - 10, text_x + max_width + 10, text_y + 80],
            fill=(0, 0, 0, 180),
            outline=(255, 255, 255, 200),
            width=2
        )
        text_draw.text((text_x, text_y), date_text, fill=(255, 255, 255, 255), font=font_large)
        text_draw.text((text_x, text_y + 30), time_text, fill=(255, 255, 255, 255), font=font_small)
        text_draw.text((text_x, text_y + 55), guests_text, fill=(255, 255, 255, 255), font=font_small)

        img = Image.alpha_composite(img, text_overlay)

        filepath = os.path.join(TEMP_DIR, f"{schema_id}.png")
        img.save(filepath, "PNG")
        return filepath, free_table_ids

    except Exception as e:
        print(f"Ошибка в generate_hall_schema: {e}")
        return None, []

@router.callback_query(F.data == "call_admin")
async def call_admin(callback: types.CallbackQuery):
    # Получаем контактную информацию
    restaurant_phone = database.get_setting('restaurant_phone', '+7 (903) 748-80-80')
    restaurant_hours = database.get_setting('restaurant_hours', 'Ежедневно с 08:00 до 22:00')
    
    # Получаем админов
    all_users = database.get_all_users()
    admins = [user for user in all_users if database.is_admin(user[0])]
    
    text = f"📞 <b>Контактная информация</b>\n\n"
    
    # Телефон и часы работы
    text += f"🏢 <b>Ресторан:</b>\n"
    text += f"📱 Телефон: <a href=\"tel:{clean_phone_for_link(restaurant_phone)}\">{restaurant_phone}</a>\n"
    text += f"🕐 Часы: {restaurant_hours}\n\n"
    
    keyboard_buttons = []
    
    # Администраторы
    if admins:
        text += f"👑 <b>Администраторы:</b>\n"
        
        admin_buttons = []
        for i, admin in enumerate(admins[:3], 1):  # Ограничиваем 3 админами
            admin_id = admin[0]
            full_name = admin[1] or f"Админ {i}"
            username = admin[2]
            
            if username:
                # В тексте
                text += f"\n{i}. <b>{full_name}</b>\n"
                text += f"   @{username}\n"
                
                # Кнопка
                admin_buttons.append(InlineKeyboardButton(
                    text=f"📱 {full_name[:10]}...", 
                    url=f"tg://user?id={admin_id}"
                ))
            else:
                text += f"\n{i}. <b>{full_name}</b> (ID: {admin_id})\n"
        
        # Группируем кнопки админов по 2 в ряд
        if admin_buttons:
            for i in range(0, len(admin_buttons), 2):
                row = admin_buttons[i:i+2]
                keyboard_buttons.append(row)
            
            text += "\n<i>Для оперативной связи рекомендуем написать администратору в Telegram</i>"
        else:
            text += "\n<i>Для связи используйте телефон ресторана</i>"
    else:
        text += "\n<i>Для связи используйте телефон ресторана</i>"
    
    # Навигационные кнопки
    keyboard_buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="booking"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "cancel_booking")
async def cancel_booking_flow(callback: types.CallbackQuery, state: FSMContext):
    global _schema_message_id

    # Удаляем сообщение о подтверждении бронирования
    try:
        await callback.message.delete()
    except Exception:
        pass

    if _schema_message_id:
        try:
            await safe_delete_message(callback.bot, callback.from_user.id, _schema_message_id)
            _schema_message_id = None
        except Exception:
            pass

    await state.clear()
    await update_message(callback.from_user.id,
                        "❌ Бронирование отменено.",
                        reply_markup=keyboards.back_to_main(),
                        bot=callback.bot)


__all__ = [
    'router',
    'booking_start',
    'show_booking_options',
    'new_booking_handler',
    'my_bookings_handler',
    'show_user_bookings',
    'booking_details_callback',
    'edit_booking_callback',
    'cancel_booking_callback',
    'confirm_cancel_booking',
    'refresh_booking_callback',
    'select_guests',
    'select_date',
    'select_time_category',
    'select_time',
    'select_table',
    'select_random_table',
    'confirm_booking',
    'cancel_and_new_booking',
    'call_admin',
    'cancel_booking_flow',
    'back_main',
    'back_to_time_selection'
]
