"""
handlers_personal_cabinet.py - Упрощенный личный кабинет
"""

from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import database
import keyboards
import re
import asyncio
from datetime import datetime
from typing import Optional
import logging
from .utils import update_message
from .handlers_registration import ask_for_registration_phone, RegistrationStates
from presto_api import presto_api

logger = logging.getLogger(__name__)
router = Router()

class PersonalCabinetStates(StatesGroup):
    waiting_for_new_phone = State()
    waiting_for_new_name = State()

@router.callback_query(F.data == "register_or_login")
async def register_or_login_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик регистрации/входа"""
    await callback.answer()
    
    user_id = callback.from_user.id
    registration_status = database.check_user_registration_fast(user_id)
    
    if registration_status == 'completed':
        await personal_cabinet_handler(callback, state)
    else:
        text = """👋 <b>Регистрация/Вход</b>

Для доступа к личному кабинету необходимо зарегистрироваться.

<b>Что дает регистрация:</b>
• История бронирований
• Быстрое оформление заказов
• Персональные промокоды

Нажмите кнопку ниже, чтобы поделиться номером телефона:"""
        
        keyboard = keyboards.register_or_login_menu()
        
        await update_message(user_id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=callback.bot)

@router.callback_query(F.data == "share_phone_for_registration")
async def share_phone_for_registration_handler(callback: types.CallbackQuery, state: FSMContext):
    """Запрос телефона для регистрации"""
    await callback.answer()
    
    user_id = callback.from_user.id
    await ask_for_registration_phone(user_id, callback.bot, "personal_cabinet", state)
    
    await state.set_state(RegistrationStates.waiting_for_phone)

@router.callback_query(F.data == "personal_cabinet")
async def personal_cabinet_handler(callback: types.CallbackQuery, state: FSMContext):
    """Основной обработчик личного кабинета"""
    await callback.answer()
    
    user_id = callback.from_user.id
    await state.clear()
    
    registration_status = database.check_user_registration_fast(user_id)
    
    if registration_status != 'completed':
        await callback.answer("❌ Сначала зарегистрируйтесь!", show_alert=True)
        await register_or_login_handler(callback, state)
        return
    
    user_data = database.get_user_complete_data(user_id)
    
    if not user_data:
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return
    
    # Получаем UUID если его нет
    presto_uuid = user_data.get('presto_uuid')
    if not presto_uuid and user_data.get('phone'):
        presto_uuid = await fetch_and_save_presto_uuid(user_id, user_data['phone'])
    
    text = f"""👤 <b>Личный кабинет</b>

<b>Ваши данные:</b>
👤 <b>Имя:</b> {user_data.get('full_name', 'Не указано')}
📱 <b>Телефон:</b> {user_data.get('phone', 'Не указан')}
🆔 <b>ID клиента:</b> {presto_uuid if presto_uuid else 'Не определен'}

<b>Выберите действие:</b>"""
    
    keyboard = keyboards.personal_cabinet_menu()
    
    await update_message(user_id, text,
                       reply_markup=keyboard,
                       parse_mode="HTML",
                       bot=callback.bot)

async def fetch_and_save_presto_uuid(user_id: int, phone: str) -> Optional[str]:
    """Получение UUID клиента из Presto API"""
    try:
        clean_phone = re.sub(r'[^\d]', '', phone)
        uuid = await presto_api.get_customer_uuid(clean_phone)
        
        if uuid:
            database.update_user_presto_uuid(user_id, uuid)
            logger.info(f"✅ UUID клиента сохранен: {uuid}")
            return uuid
        
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка получения UUID: {e}")
        return None

@router.callback_query(F.data == "change_phone")
async def change_phone_handler(callback: types.CallbackQuery, state: FSMContext):
    """Смена телефона"""
    await callback.answer()
    
    user_id = callback.from_user.id
    user_data = database.get_user_data(user_id)
    
    text = f"""📱 <b>Изменение телефона</b>

<b>Текущий телефон:</b> {user_data.get('phone', 'Не указан')}

Введите новый номер телефона:
<i>Формат: +7 999 123-45-67 или 89991234567</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад в ЛК", callback_data="personal_cabinet")]
    ])
    
    await update_message(user_id, text,
                       reply_markup=keyboard,
                       parse_mode="HTML",
                       bot=callback.bot)
    
    await state.set_state(PersonalCabinetStates.waiting_for_new_phone)

@router.message(PersonalCabinetStates.waiting_for_new_phone)
async def process_new_phone(message: types.Message, state: FSMContext):
    """Обработка нового телефона"""
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    phone_text = message.text.strip()
    clean_phone = re.sub(r'[^\d+]', '', phone_text)
    
    if not clean_phone or len(clean_phone) < 10:
        await message.answer("❌ Неверный формат телефона.")
        return
    
    if clean_phone.startswith('8'):
        clean_phone = '+7' + clean_phone[1:]
    elif clean_phone.startswith('7') and not clean_phone.startswith('+7'):
        clean_phone = '+7' + clean_phone[1:]
    elif not clean_phone.startswith('+'):
        clean_phone = '+7' + clean_phone
    
    success = database.update_user_phone(user_id, clean_phone)
    
    if success:
        # Получаем новый UUID
        await fetch_and_save_presto_uuid(user_id, clean_phone)
        
        text = f"""✅ <b>Телефон успешно обновлен!</b>

<b>Новый телефон:</b> {clean_phone}"""
        
        await update_message(user_id, text,
                           reply_markup=keyboards.back_to_cabinet(),
                           parse_mode="HTML",
                           bot=message.bot)
    else:
        await message.answer("❌ Ошибка обновления телефона.")
    
    await state.clear()

@router.callback_query(F.data == "change_name")
async def change_name_handler(callback: types.CallbackQuery, state: FSMContext):
    """Смена имени"""
    await callback.answer()
    
    user_id = callback.from_user.id
    user_data = database.get_user_data(user_id)
    
    text = f"""👤 <b>Изменение имени</b>

<b>Текущее имя:</b> {user_data.get('full_name', 'Не указано')}

Введите новое имя:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад в ЛК", callback_data="personal_cabinet")]
    ])
    
    await update_message(user_id, text,
                       reply_markup=keyboard,
                       parse_mode="HTML",
                       bot=callback.bot)
    
    await state.set_state(PersonalCabinetStates.waiting_for_new_name)

@router.message(PersonalCabinetStates.waiting_for_new_name)
async def process_new_name(message: types.Message, state: FSMContext):
    """Обработка нового имени"""
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    new_name = message.text.strip()
    
    if len(new_name) < 2:
        await message.answer("❌ Имя слишком короткое.")
        return
    
    success = database.update_user_name(user_id, new_name)
    
    if success:
        text = f"""✅ <b>Имя успешно обновлено!</b>

<b>Новое имя:</b> {new_name}"""
        
        await update_message(user_id, text,
                           reply_markup=keyboards.back_to_cabinet(),
                           parse_mode="HTML",
                           bot=message.bot)
    else:
        await message.answer("❌ Ошибка обновления имени.")
    
    await state.clear()

@router.callback_query(F.data == "booking_history")
async def booking_history_handler(callback: types.CallbackQuery):
    """История бронирований"""
    await callback.answer()
    
    user_id = callback.from_user.id
    
    from .handlers_booking import get_user_bookings
    bookings = await get_user_bookings(user_id)
    
    if not bookings:
        text = """📅 <b>История бронирований</b>

У вас пока нет бронирований.

<b>Забронируйте столик!</b>"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📅 Забронировать столик", callback_data="booking")],
            [types.InlineKeyboardButton(text="⬅️ Назад в ЛК", callback_data="personal_cabinet")]
        ])
    else:
        text = f"""📅 <b>История бронирований</b>

<b>Всего бронирований:</b> {len(bookings)}

<i>Выберите бронирование для просмотра:</i>"""
        
        keyboard = keyboards.booking_history_menu(bookings, page=0)
    
    await update_message(user_id, text,
                       reply_markup=keyboard,
                       parse_mode="HTML",
                       bot=callback.bot)

print("✅ handlers_personal_cabinet.py загружен!")
