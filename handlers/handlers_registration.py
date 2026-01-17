# handlers/handlers_registration.py

from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
import database
import re
import asyncio
import logging
from typing import Dict, List
import config  # <-- ИМПОРТ КОНФИГА

from .utils import update_message, check_user_registration_fast, clear_user_cache, safe_delete_message, safe_send_message

logger = logging.getLogger(__name__)
router = Router()

# Хранилище ID всех сообщений регистрации для каждого пользователя
_registration_messages: Dict[int, List[int]] = {}

class RegistrationStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_name = State()

def _add_registration_message(user_id: int, message_id: int):
    """Добавление ID сообщения регистрации для последующего удаления"""
    if user_id not in _registration_messages:
        _registration_messages[user_id] = []
    _registration_messages[user_id].append(message_id)

async def _cleanup_registration_messages(user_id: int, bot):
    """Очистка всех сообщений регистрации"""
    if user_id in _registration_messages:
        for msg_id in _registration_messages[user_id][:]:
            try:
                await bot.delete_message(user_id, msg_id)
            except:
                pass
        _registration_messages[user_id] = []

async def ask_for_registration_phone(user_id: int, bot, context: str = "general", state: FSMContext = None):
    """Запрос телефона для регистрации с сохранением контекста"""
    
    # Сохраняем контекст в state, если он передан
    if state:
        await state.update_data(context=context)
    
    text = f"""📞 <b>Регистрация</b>

Для продолжения нам нужен ваш номер телефона.

<b>Нажимая кнопку "Поделиться номером телефона", вы автоматически соглашаетесь:</b>
✅ На обработку персональных данных
✅ С пользовательским соглашением

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>

<u>Или введите номер вручную в формате +7 XXX XXX XX XX:</u>"""
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    # Создаем inline клавиатуру с кнопкой "Назад"
    if context == 'personal_cabinet':
        back_callback = "personal_cabinet"
    else:
        back_callback = "back_main"
    
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)]
    ])
    
    msg = await bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    # Отправляем отдельное сообщение с inline кнопкой "Назад"
    back_msg = await bot.send_message(
        chat_id=user_id,
        text="⬅️ <i>Или вернитесь назад</i>",
        reply_markup=inline_keyboard,
        parse_mode="HTML"
    )
    
    if back_msg and back_msg.message_id:
        _add_registration_message(user_id, back_msg.message_id)
    
    if msg and msg.message_id:
        _add_registration_message(user_id, msg.message_id)
    
    # Логируем начало регистрации
    database.log_action(user_id, "registration_started", context)

@router.message(F.contact)
async def handle_contact(message: types.Message, state: FSMContext):
    user = message.from_user
    
    # Удаляем сообщение с контактом (сообщение пользователя)
    await safe_delete_message(message.bot, message.chat.id, message.message_id)
    
    if not message.contact or not message.contact.phone_number:
        return

    phone = message.contact.phone_number
    
    # Автоматическое согласие при нажатии кнопки "Поделиться номером телефона"
    # accept_agreement = True
    
    phone_regex = r'^\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}$|^\+7\d{10}$|^8\d{10}$|^7\d{10}$'
    if not re.match(phone_regex, phone):
        # Не редактируем, а отправляем новое сообщение
        text = f"""❌ Неверный формат телефона!

<b>Нажимая кнопку "Поделиться номером телефона", вы автоматически соглашаетесь:</b>
✅ На обработку персональных данных
✅ С пользовательским соглашением

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>

Пожалуйста, введите номер вручную в формате +7 XXX XXX XX XX:"""
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        msg = await safe_send_message(message.bot, user.id, text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        if msg and msg.message_id:
            _add_registration_message(user.id, msg.message_id)
        return

    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone_clean.startswith("8"):
        phone_clean = "+7" + phone_clean[1:]
    elif phone_clean.startswith("7"):
        phone_clean = "+" + phone_clean

    await state.update_data(phone=phone_clean)
    # Сохраняем контекст, если он еще не сохранен
    data = await state.get_data()
    if 'context' not in data:
        current_state = await state.get_state()
        context = 'booking' if current_state == RegistrationStates.waiting_for_phone.state else 'general'
        await state.update_data(context=context)

    user_name = user.full_name
    if user_name and len(user_name.strip()) >= 2:
        text = f"""👤 <b>Это ваше имя: {user_name}?</b>

<b>Подтверждая имя, вы соглашаетесь:</b>
✅ На обработку персональных данных
✅ С пользовательским соглашением

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Да, я {user_name}", callback_data=f"confirm_name:{user_name}")],
            [InlineKeyboardButton(text="✏️ Ввести другое имя", callback_data="enter_different_name")]
        ])
        # Отправляем новое сообщение вместо редактирования
        msg = await safe_send_message(message.bot, user.id, text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        if msg and msg.message_id:
            _add_registration_message(user.id, msg.message_id)
        await state.set_state(RegistrationStates.waiting_for_name)
    else:
        text = f"""👤 <b>Введите ваше имя:</b>

<b>Вводя имя, вы соглашаетесь:</b>
✅ На обработку персональных данных
✅ С пользовательским соглашением

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>"""
        
        msg = await safe_send_message(message.bot, user.id, text, parse_mode="HTML", disable_web_page_preview=True)
        if msg and msg.message_id:
            _add_registration_message(user.id, msg.message_id)
        await state.set_state(RegistrationStates.waiting_for_name)

# Обработчик для ручного ввода телефона (если пользователь пишет номер текстом)
@router.message(RegistrationStates.waiting_for_phone)
async def handle_manual_phone(message: types.Message, state: FSMContext):
    user = message.from_user
    phone = message.text.strip()
    
    await safe_delete_message(message.bot, message.chat.id, message.message_id)
    
    phone_regex = r'^\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}$|^\+7\d{10}$|^8\d{10}$|^7\d{10}$'
    if not re.match(phone_regex, phone):
        text = f"""❌ Неверный формат телефона!

<b>При вводе номера телефона, вы соглашаетесь:</b>
✅ На обработку персональных данных
✅ С пользовательским соглашением

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>

Пожалуйста, введите номер в формате +7 XXX XXX XX XX:"""
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        msg = await safe_send_message(message.bot, user.id, text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        if msg and msg.message_id:
            _add_registration_message(user.id, msg.message_id)
        return

    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone_clean.startswith("8"):
        phone_clean = "+7" + phone_clean[1:]
    elif phone_clean.startswith("7"):
        phone_clean = "+" + phone_clean

    await state.update_data(phone=phone_clean)
    # Сохраняем контекст, если он еще не сохранен
    data = await state.get_data()
    if 'context' not in data:
        current_state = await state.get_state()
        context = 'booking' if current_state == RegistrationStates.waiting_for_phone.state else 'general'
        await state.update_data(context=context)

    text = f"""👤 <b>Введите ваше имя:</b>

<b>Вводя имя, вы соглашаетесь:</b>
✅ На обработку персональных данных
✅ С пользовательским соглашением

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>"""
    
    msg = await safe_send_message(message.bot, user.id, text, parse_mode="HTML", disable_web_page_preview=True)
    if msg and msg.message_id:
        _add_registration_message(user.id, msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_name)

@router.message(RegistrationStates.waiting_for_name)
async def handle_name_input(message: types.Message, state: FSMContext):
    user = message.from_user
    text = message.text.strip()
    
    # Удаляем сообщение с именем (сообщение пользователя)
    await safe_delete_message(message.bot, message.chat.id, message.message_id)
    
    if len(text) < 2:
        msg_text = f"""❌ Имя должно быть от 2 символов.

<b>Вводя имя, вы соглашаетесь:</b>
✅ На обработку персональных данных
✅ С пользовательским соглашением

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>"""
        
        msg = await safe_send_message(message.bot, user.id, msg_text, parse_mode="HTML", disable_web_page_preview=True)
        if msg and msg.message_id:
            _add_registration_message(user.id, msg.message_id)
        return

    data = await state.get_data()
    phone = data.get('phone')
    if not phone:
        await safe_send_message(message.bot, user.id, "❌ Ошибка: телефон не найден.")
        await state.clear()
        return

    # Автоматическое согласие при регистрации
    agreement_accepted = True
    context = data.get('context', 'general')
    
    database.update_user_phone(user.id, phone)
    database.update_user_name(user.id, text, accept_agreement=agreement_accepted)
    clear_user_cache(user.id)

    # Отправляем сообщение о завершении регистрации
    reg_message = await safe_send_message(
        message.bot, 
        user.id, 
        f"""✅ <b>Регистрация завершена, {text}! 🎉</b>

<b>Вы успешно зарегистрированы!</b>

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>

Спасибо, что выбрали нас!""", 
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    # Добавляем ID этого сообщения в список для удаления
    if reg_message and reg_message.message_id:
        _add_registration_message(user.id, reg_message.message_id)
    
    await asyncio.sleep(2)
    
    # Удаляем ВСЕ сообщения регистрации
    await _cleanup_registration_messages(user.id, message.bot)
    
    # Очищаем state
    await state.clear()
    
    # Вызываем функцию перенаправления после регистрации
    await handle_post_registration_redirect(user.id, message.bot, state, context, data)

@router.callback_query(F.data.startswith("confirm_name:"))
async def confirm_name_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_name = callback.data.split(":", 1)[1]
    data = await state.get_data()
    phone = data.get('phone')
    if not phone:
        await safe_send_message(callback.bot, callback.from_user.id, "❌ Ошибка: телефон не найден.")
        await state.clear()
        return

    # Автоматическое согласие при регистрации
    agreement_accepted = True
    context = data.get('context', 'general')
    
    database.update_user_phone(callback.from_user.id, phone)
    database.update_user_name(callback.from_user.id, user_name, accept_agreement=agreement_accepted)
    clear_user_cache(callback.from_user.id)

    # Отправляем сообщение о завершении регистрации
    reg_message = await safe_send_message(
        callback.bot, 
        callback.from_user.id, 
        f"""✅ <b>Регистрация завершена, {user_name}! 🎉</b>

<b>Вы успешно зарегистрированы!</b>

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>

Спасибо, что выбрали нас!""", 
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    # Добавляем ID сообщений для удаления
    if reg_message and reg_message.message_id:
        _add_registration_message(callback.from_user.id, reg_message.message_id)
    _add_registration_message(callback.from_user.id, callback.message.message_id)
    
    await asyncio.sleep(2)
    
    # Удаляем ВСЕ сообщения регистрации
    await _cleanup_registration_messages(callback.from_user.id, callback.bot)
    await state.clear()
    
    # Вызываем функцию перенаправления после регистрации
    await handle_post_registration_redirect(callback.from_user.id, callback.bot, state, context, data)

@router.callback_query(F.data == "enter_different_name")
async def enter_different_name_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    text = f"""👤 <b>Введите ваше имя:</b>

<b>Вводя имя, вы соглашаетесь:</b>
✅ На обработку персональных данных
✅ С пользовательским соглашением

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>"""
    
    msg = await safe_send_message(callback.bot, callback.from_user.id, text, parse_mode="HTML", disable_web_page_preview=True)
    if msg and msg.message_id:
        _add_registration_message(callback.from_user.id, msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_name)

async def handle_post_registration_redirect(user_id: int, bot, state: FSMContext, context: str, state_data: dict):
    """Перенаправление пользователя после регистрации в зависимости от контекста"""
    
    if context == 'before_order_type':
        # Возвращаем к выбору типа заказа
        from .handlers_delivery import show_order_type_selection_from_cart
        cart_summary = state_data.get('cart_summary', {})
        await state.update_data(cart_summary=cart_summary)
        await show_order_type_selection_from_cart(user_id, bot, state)
        
    elif context == 'add_to_cart':
        # Возвращаем к добавлению в корзину
        from .handlers_delivery import menu_delivery_handler
        pending_dish = state_data.get('pending_dish', {})
        if pending_dish:
            from menu_cache import menu_cache
            from cart_manager import cart_manager
            
            menu_id = pending_dish.get('menu_id')
            dish_id = pending_dish.get('dish_id')
            
            dish = menu_cache.get_dish_by_id(menu_id, dish_id)
            if dish:
                success = cart_manager.add_to_cart(
                    user_id=user_id,
                    dish_id=dish_id,
                    dish_name=dish['name'],
                    price=dish['price'],
                    quantity=1,
                    image_url=dish.get('image_url')
                )
                
                if success:
                    await safe_send_message(bot, user_id, f"✅ {dish['name']} добавлен в корзину")
        
        # Возвращаем в меню
        await menu_delivery_handler(user_id, bot, state)
        
    elif context == 'order_from_cart':
        # Возвращаем к оформлению заказа
        from .handlers_delivery import show_order_type_selection_from_cart
        cart_summary = state_data.get('cart_summary', {})
        await state.update_data(cart_summary=cart_summary)
        await show_order_type_selection_from_cart(user_id, bot, state)
        
    elif context == 'delivery':
        # Возвращаем в меню доставки
        from .handlers_delivery import menu_delivery_handler
        await menu_delivery_handler(user_id, bot, state)
        
    elif context == 'booking':
        # Возвращаем к бронированию
        from .handlers_booking import show_booking_options
        await show_booking_options(user_id, bot)
    
    elif context == 'personal_cabinet':
        # Возвращаем в главное меню (регистрация из личного кабинета)
        from .handlers_main import show_main_menu
        await show_main_menu(user_id, bot)
        
    else:
        # По умолчанию возвращаем в главное меню
        from .handlers_main import show_main_menu
        await show_main_menu(user_id, bot)

__all__ = ['router', 'RegistrationStates', 'ask_for_registration_phone', 'handle_post_registration_redirect']