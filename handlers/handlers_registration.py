# handlers/handlers_registration.py

from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, BufferedInputFile
import database
import re
import asyncio
import logging
import os
from typing import Dict, List
from datetime import datetime
import config  # <-- ИМПОРТ КОНФИГА

from .utils import update_message, check_user_registration_fast, clear_user_cache, safe_delete_message, safe_send_message

logger = logging.getLogger(__name__)
router = Router()

# Хранилище ID всех сообщений регистрации для каждого пользователя
_registration_messages: Dict[int, List[int]] = {}

class RegistrationStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_agreement = State()
    waiting_for_name = State()

class EventRegistrationStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_agreement = State()
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

<u>Нажмите кнопку ниже или введите номер вручную в формате +7 XXX XXX XX XX:</u>"""
    
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

    # Показываем "попап" с соглашением
    text = f"""📜 <b>Пользовательское соглашение</b>

Для продолжения работы с ботом необходимо принять условия использования и дать согласие на обработку персональных данных.

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>

✅ Я согласен на обработку персональных данных"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять и продолжить", callback_data="accept_agreement")]
    ])

    msg = await safe_send_message(message.bot, user.id, text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
    if msg and msg.message_id:
        _add_registration_message(user.id, msg.message_id)
    
    await state.set_state(RegistrationStates.waiting_for_agreement)

# Обработчик для ручного ввода телефона (если пользователь пишет номер текстом)
@router.message(RegistrationStates.waiting_for_phone)
async def handle_manual_phone(message: types.Message, state: FSMContext):
    user = message.from_user
    phone = message.text.strip()
    
    await safe_delete_message(message.bot, message.chat.id, message.message_id)
    
    phone_regex = r'^\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2}$|^\+7\d{10}$|^8\d{10}$|^7\d{10}$'
    if not re.match(phone_regex, phone):
        text = f"""❌ Неверный формат телефона!

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

    # Показываем "попап" с соглашением
    text = f"""📜 <b>Пользовательское соглашение</b>

Для продолжения работы с ботом необходимо принять условия использования и дать согласие на обработку персональных данных.

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>

✅ Я согласен на обработку персональных данных"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять и продолжить", callback_data="accept_agreement")]
    ])
    
    msg = await safe_send_message(message.bot, user.id, text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
    if msg and msg.message_id:
        _add_registration_message(user.id, msg.message_id)
    await state.set_state(RegistrationStates.waiting_for_agreement)

@router.callback_query(F.data == "accept_agreement", RegistrationStates.waiting_for_agreement)
async def accept_agreement_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user = callback.from_user
    
    # Delete the agreement message (the "popup")
    await safe_delete_message(callback.bot, user_id, callback.message.message_id)
    
    # Check for existing name logic
    user_name = user.full_name
    if user_name and len(user_name.strip()) >= 2:
        text = f"""👤 <b>Это ваше имя: {user_name}?</b>"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Да, я {user_name}", callback_data=f"confirm_name:{user_name}")],
            [InlineKeyboardButton(text="✏️ Ввести другое имя", callback_data="enter_different_name")]
        ])
        msg = await safe_send_message(callback.bot, user_id, text, reply_markup=keyboard, parse_mode="HTML")
        if msg and msg.message_id:
            _add_registration_message(user_id, msg.message_id)
        await state.set_state(RegistrationStates.waiting_for_name)
    else:
        text = f"""👤 <b>Введите ваше имя:</b>"""
        msg = await safe_send_message(callback.bot, user_id, text, parse_mode="HTML")
        if msg and msg.message_id:
            _add_registration_message(user_id, msg.message_id)
        await state.set_state(RegistrationStates.waiting_for_name)

@router.message(RegistrationStates.waiting_for_name)
async def handle_name_input(message: types.Message, state: FSMContext):
    user = message.from_user
    text = message.text.strip()
    
    # Удаляем сообщение с именем (сообщение пользователя)
    await safe_delete_message(message.bot, message.chat.id, message.message_id)
    
    if len(text) < 2:
        msg_text = f"""❌ Имя должно быть от 2 символов."""
        
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
    
    # ВАЖНО: Сначала создаем/обновляем пользователя в БД
    database.add_or_update_user(user.id, user.username, user.full_name)
    
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
    
    # Вызываем функцию перенаправления после регистрации ПЕРЕД очисткой state
    await handle_post_registration_redirect(user.id, message.bot, state, context, data)
    
    # Очищаем state ПОСЛЕ перенаправления
    await state.clear()

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
    
    # ВАЖНО: Сначала создаем/обновляем пользователя в БД
    database.add_or_update_user(callback.from_user.id, callback.from_user.username, callback.from_user.full_name)
    
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
    
    # Вызываем функцию перенаправления после регистрации ПЕРЕД очисткой state
    await handle_post_registration_redirect(callback.from_user.id, callback.bot, state, context, data)
    
    # Очищаем state ПОСЛЕ перенаправления
    await state.clear()

@router.callback_query(F.data == "enter_different_name")
async def enter_different_name_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    text = f"""👤 <b>Введите ваше имя:</b>"""
    
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
        from .handlers_main import show_booking_options
        await show_booking_options(user_id, bot)
    
    elif context == 'personal_cabinet':
        # Возвращаем в главное меню (регистрация из личного кабинета)
        from .handlers_main import show_main_menu
        await show_main_menu(user_id, bot)
        
    elif context == 'private_event_registration':
        # Специальная обработка для частных мероприятий
        await handle_private_event_registration_completion(user_id, bot, state)
        
    else:
        # По умолчанию возвращаем в главное меню
        from .handlers_main import show_main_menu
        await show_main_menu(user_id, bot)

async def handle_private_event_registration_completion(user_id: int, bot, state: FSMContext):
    """Обработка завершения регистрации для частного мероприятия"""
    try:
        # Получаем тип мероприятия из состояния
        data = await state.get_data()
        event_type = data.get('event_type', None)
        
        # Отправляем срочную заявку админу с типом мероприятия
        from .handlers_main import send_private_event_application_to_admin
        await send_private_event_application_to_admin(user_id, bot, event_type)
        
        # Определяем эмодзи и название для типа мероприятия
        event_type_emoji = {
            'день_рождения': '🎂',
            'свадьба': '💒',
            'корпоратив': '🏢',
            'юбилей': '🎊',
            'детский_праздник': '🎈',
            'другое': '🎭'
        }
        
        emoji = event_type_emoji.get(event_type, '🎉') if event_type else '🎉'
        event_name = event_type.replace('_', ' ').title() if event_type else 'мероприятие'
        
        # Сообщение пользователю с предложением меню
        text = f"""{emoji} <b>СРОЧНАЯ ЗАЯВКА ПРИНЯТА!</b>

⚡ Ваша заявка на организацию мероприятия "{event_name}" отправлена!

📞 <b>Наш менеджер свяжется с вами в течение 15 минут!</b>

А пока вы можете ознакомиться с нашим меню и банкетным предложением. Хотите, чтобы я выслал их вам?"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📋 Основное меню", callback_data="show_main_menu_after_private_event")],
            [types.InlineKeyboardButton(text="🍾 Банкетное меню", callback_data="show_banquet_menu_after_private_event")],
            [types.InlineKeyboardButton(text="📋 Оба меню", callback_data="show_both_menus_after_private_event")],
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в handle_private_event_registration_completion: {e}")
        # Fallback - просто возвращаем в главное меню
        from .handlers_main import show_main_menu
        await show_main_menu(user_id, bot)

# ===== РЕГИСТРАЦИЯ НА МЕРОПРИЯТИЯ =====

async def ask_for_event_registration_phone(user_id: int, bot, context: str = "event_registration"):
    """Запрос телефона для регистрации на мероприятие (улучшенная версия)"""
    await _cleanup_registration_messages(user_id, bot)
    
    text = """📝 <b>Заявка на мероприятие</b>

Для подачи заявки нам нужны ваши контактные данные.

📱 <b>Поделитесь номером телефона или введите вручную:</b>"""

    # Создаем клавиатуру с кнопкой поделиться номером И кнопкой назад
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📱 Поделиться номером", callback_data="share_phone_event")],
        [types.InlineKeyboardButton(text="⬅️ Назад к мероприятиям", callback_data="event_registration")]
    ])

    msg = await bot.send_message(
        user_id, 
        text, 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )
    if msg and msg.message_id:
        _add_registration_message(user_id, msg.message_id)

@router.callback_query(F.data == "share_phone_event")
async def share_phone_event_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Поделиться номером' для мероприятий"""
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Сохраняем контекст в state - по умолчанию event_registration, но может быть private_event_registration
    current_state_data = await state.get_data()
    context = current_state_data.get('context', 'event_registration')
    await state.update_data(context=context)
    
    text = """📱 <b>Поделитесь номером телефона</b>

Нажмите кнопку ниже или введите номер вручную в формате +7 XXX XXX XX XX"""

    # Создаем reply клавиатуру для получения контакта
    reply_keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    # Создаем inline клавиатуру с кнопкой "Назад"
    inline_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к мероприятиям", callback_data="event_registration")]
    ])
    
    # Редактируем сообщение
    await callback.message.edit_text(
        text,
        reply_markup=inline_keyboard,
        parse_mode="HTML"
    )
    
    # Отправляем reply клавиатуру отдельным сообщением
    msg = await callback.bot.send_message(
        user_id,
        "👆 Используйте кнопку выше или введите номер вручную:",
        reply_markup=reply_keyboard
    )
    if msg and msg.message_id:
        _add_registration_message(user_id, msg.message_id)
    
    # Устанавливаем состояние ожидания телефона
    await state.set_state(EventRegistrationStates.waiting_for_phone)

@router.message(EventRegistrationStates.waiting_for_phone)
async def handle_event_phone_input(message: types.Message, state: FSMContext):
    """Обработка ввода телефона для регистрации на мероприятие"""
    user = message.from_user
    user_id = user.id
    
    _add_registration_message(user_id, message.message_id)
    
    phone = None
    if message.contact:
        phone = message.contact.phone_number
    elif message.text:
        # Попытка извлечь номер из текста
        import re
        phone_match = re.search(r'[\+]?[0-9\s\-\(\)]{10,}', message.text)
        if phone_match:
            phone = phone_match.group().strip()
    
    if not phone:
        text = """❌ <b>Некорректный номер телефона</b>

Пожалуйста, поделитесь номером телефона через кнопку или введите корректный номер в формате +7 XXX XXX XX XX."""
        
        reply_keyboard = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        inline_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад к мероприятиям", callback_data="event_registration")]
        ])
        
        msg = await message.answer(text, reply_markup=reply_keyboard, parse_mode="HTML")
        if msg and msg.message_id:
            _add_registration_message(user_id, msg.message_id)
            
        back_msg = await message.answer(
            "⬅️ <i>Или вернитесь к выбору мероприятий</i>",
            reply_markup=inline_keyboard,
            parse_mode="HTML"
        )
        if back_msg and back_msg.message_id:
            _add_registration_message(user_id, back_msg.message_id)
        return
    
    # Сохраняем телефон и контекст
    current_data = await state.get_data()
    context = current_data.get('context', 'event_registration')
    await state.update_data(event_phone=phone, context=context)
    
    # Показываем "попап" с соглашением
    text = f"""📜 <b>Пользовательское соглашение</b>

Для продолжения работы с ботом необходимо принять условия использования и дать согласие на обработку персональных данных.

<a href="{config.USER_AGREEMENT_URL}">📄 Пользовательское соглашение</a>
<a href="{config.PRIVACY_POLICY_URL}">🔒 Политика конфиденциальности</a>

✅ Я согласен на обработку персональных данных"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Принять и продолжить", callback_data="accept_event_agreement")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="event_registration")]
    ])

    msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    if msg and msg.message_id:
        _add_registration_message(user_id, msg.message_id)
    
    await state.set_state(EventRegistrationStates.waiting_for_agreement)

@router.callback_query(F.data == "accept_event_agreement", EventRegistrationStates.waiting_for_agreement)
async def accept_event_agreement_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    
    # Delete the agreement message
    await safe_delete_message(callback.bot, user_id, callback.message.message_id)
    
    # Ask for name
    text = """👤 <b>Введите ваше имя:</b>

Как к вам обращаться при связи по поводу мероприятия?"""
    
    inline_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к мероприятиям", callback_data="event_registration")]
    ])
    
    msg = await callback.message.answer(text, reply_markup=inline_keyboard, parse_mode="HTML")
    if msg and msg.message_id:
        _add_registration_message(user_id, msg.message_id)
    
    await state.set_state(EventRegistrationStates.waiting_for_name)

@router.message(EventRegistrationStates.waiting_for_name)
async def handle_event_name_input(message: types.Message, state: FSMContext):
    """Обработка ввода имени для регистрации на мероприятие"""
    user = message.from_user
    user_id = user.id
    
    _add_registration_message(user_id, message.message_id)
    
    name = message.text.strip() if message.text else ""
    
    if not name or len(name) < 2:
        text = """❌ <b>Некорректное имя</b>

Пожалуйста, введите ваше имя (минимум 2 символа)."""
        
        inline_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад к мероприятиям", callback_data="event_registration")]
        ])
        
        msg = await message.answer(text, reply_markup=inline_keyboard, parse_mode="HTML")
        if msg and msg.message_id:
            _add_registration_message(user_id, msg.message_id)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    phone = data.get('event_phone', '')
    context = data.get('context', 'event_registration')
    
    # Очищаем сообщения регистрации
    await _cleanup_registration_messages(user_id, message.bot)
    
    # Обрабатываем в зависимости от контекста
    if context == 'private_event_registration':
        # Для частных мероприятий - срочная заявка
        await handle_private_event_registration_completion(user_id, message.bot, state)
    else:
        # Для обычных мероприятий - стандартная заявка
        await send_event_application_to_admin(user_id, message.bot, name, phone, user.username)
        
        # Показываем подтверждение
        text = """✅ <b>Заявка отправлена!</b>

Спасибо за интерес к нашим мероприятиям!

С вами скоро свяжутся наши менеджеры для выяснения деталей и подтверждения регистрации.

📞 Если у вас есть срочные вопросы, вы можете связаться с нами напрямую."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📞 Связаться с нами", callback_data="contact_us")],
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    await state.clear()

async def send_event_application_to_admin(user_id: int, bot, name: str = None, phone: str = None, username: str = None):
    """Отправка заявки на мероприятие администратору"""
    try:
        # Получаем данные пользователя если не переданы
        if not name or not phone:
            user_data = database.get_user_complete_data(user_id)
            if user_data:
                name = name or user_data.get('name', 'Не указано')
                phone = phone or user_data.get('phone', 'Не указано')
            else:
                name = name or 'Не указано'
                phone = phone or 'Не указано'
        
        # Получаем username если не передан
        if not username:
            try:
                user_info = await bot.get_chat(user_id)
                username = user_info.username
            except:
                username = None
        
        # Формируем сообщение для админа
        admin_text = f"""🎉 <b>НОВАЯ ЗАЯВКА НА МЕРОПРИЯТИЕ</b>

👤 <b>Пользователь:</b> {name}
📱 <b>Телефон:</b> {phone}
🆔 <b>Telegram:</b> @{username if username else 'не указан'}
🆔 <b>ID:</b> {user_id}

📝 <b>Тип заявки:</b> Регистрация на мероприятие

⏰ <b>Время подачи:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
        
        # Отправляем всем админам
        all_users = database.get_all_users()
        admin_ids = [user[0] for user in all_users if database.is_admin(user[0])]
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, admin_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка отправки заявки на мероприятие админу {admin_id}: {e}")
        
        logger.info(f"Заявка на мероприятие от пользователя {user_id} отправлена админам")
        
    except Exception as e:
        logger.error(f"Ошибка отправки заявки на мероприятие: {e}")

__all__ = ['router', 'RegistrationStates', 'EventRegistrationStates', 'ask_for_registration_phone', 'ask_for_event_registration_phone', 'handle_post_registration_redirect']
