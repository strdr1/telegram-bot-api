"""
handlers_main.py
Основные обработчики и остальные функции
"""
from aiogram import types
from aiogram.fsm.state import State, StatesGroup
import os
import json
from aiogram.types import BufferedInputFile
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
import keyboards
import database
import config
import asyncio
import cache_manager
import logging
from datetime import datetime, date, timedelta
import aiohttp
from aiogram.exceptions import TelegramNetworkError
import cart_manager
import re
user_message_history = {}
from .utils import (
    update_message,
    check_user_registration_fast,
    send_order_notification,
    send_admin_notification,
    last_message_ids,
    safe_send_message,
    safe_edit_message,
    handler_timeout,
    safe_delete_message,
    set_operator_chat,
    set_operator_notifications,
    is_operator_chat,
    clear_operator_chat,
    typing_indicator
)
from difflib import SequenceMatcher

# Импортируем функции из других модулей с отложенным импортом для избежания циклических зависимостей

# Локальные определения функций с отложенным импортом
async def show_booking_options(user_id: int, bot):
    """Показать опции бронирования"""
    try:
        from .handlers_booking import show_booking_options as real_show_booking_options
        await real_show_booking_options(user_id, bot)
    except ImportError:
        # Fallback на простое меню
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Новая бронь", callback_data="new_booking")],
            [InlineKeyboardButton(text="📞 Админ", callback_data="call_admin")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
        ])
        await safe_send_message(bot, user_id,
                            "📅 <b>Бронирование столика</b>\n\nВыберите действие:",
                            reply_markup=kb, parse_mode="HTML")

async def menu_delivery_handler(user_id: int, bot, state=None):
    """Показать меню доставки"""
    try:
        from .handlers_delivery import menu_delivery_handler as real_menu_delivery_handler
        await real_menu_delivery_handler(user_id, bot, state)
    except ImportError:
        # Fallback на простое меню
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🍽️ Основное меню", callback_data="select_menu_90")],
            [InlineKeyboardButton(text="🍳 Завтраки", callback_data="select_menu_92")],
            [InlineKeyboardButton(text="🧀 Сырная карта", callback_data="select_menu_132")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
        ])
        await safe_send_message(bot, user_id,
                            "🍽️ <b>Меню доставки</b>\n\nВыберите меню:",
                            reply_markup=kb, parse_mode="HTML")

async def show_static_menu(user_id: int, bot):
    """Показать статическое меню"""
    try:
        from .handlers_delivery import show_static_menu as real_show_static_menu
        await real_show_static_menu(user_id, bot)
    except ImportError:
        # Fallback на простое меню
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 PDF меню", callback_data="menu_pdf")],
            [InlineKeyboardButton(text="🎉 Банкетное меню", callback_data="menu_banquet")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
        ])
        await safe_send_message(bot, user_id,
                            "📋 <b>Статическое меню</b>\n\nВыберите вариант:",
                            reply_markup=kb, parse_mode="HTML")

async def personal_cabinet_handler(user_id: int, bot, state=None):
    """Показать личный кабинет"""
    try:
        from .handlers_personal_cabinet import personal_cabinet_handler as real_personal_cabinet_handler
        # Адаптируем вызов - реальная функция ожидает callback, а не user_id
        from aiogram.types import CallbackQuery
        class FakeCallback:
            def __init__(self, user_id, bot):
                self.from_user = type('User', (), {'id': user_id})()
                self.bot = bot
            async def answer(self):
                pass
        
        fake_callback = FakeCallback(user_id, bot)
        await real_personal_cabinet_handler(fake_callback)
    except ImportError:
        # Fallback на простое меню
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Мои данные", callback_data="my_profile")],
            [InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders")],
            [InlineKeyboardButton(text="🏠 Мои адреса", callback_data="my_addresses")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
        ])
        await safe_send_message(bot, user_id,
                            "👤 <b>Личный кабинет</b>\n\nВыберите раздел:",
                            reply_markup=kb, parse_mode="HTML")

logger = logging.getLogger(__name__)
user_message_history = {}
user_document_history = {}
router = Router()

# Функция для логирования действий пользователя в миниапп
def log_user_action(user_id: int, action: str, details: str = None):
    """Логируем действия пользователя для миниаппа"""
    try:
        chat_id = database.get_or_create_chat(user_id, f'User {user_id}')
        message_text = f"Действие: {action}"
        if details:
            message_text += f" - {details}"
        database.save_chat_message(chat_id, 'action', message_text)
    except Exception as e:
        logger.error(f"Ошибка логирования действия пользователя {user_id}: {e}")

# Функция для очистки номера телефона для tel: ссылки
def clean_phone_for_link(phone):
    """Очищает номер телефона для использования в tel: ссылке"""
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

# Состояния для формы поставщиков
class SupplierStates(StatesGroup):
    waiting_company_name = State()
    waiting_phone = State()
    waiting_file = State()

@router.callback_query(F.data == "suppliers_contact")
async def suppliers_contact_callback(callback: types.CallbackQuery, state: FSMContext):
    """Форма для поставщиков"""
    await callback.answer()
    
    text = """🏭 <b>Для поставщиков</b>

Пожалуйста, заполните форму ниже. Мы свяжемся с вами в ближайшее время для обсуждения сотрудничества.

<b>Введите название вашей компании:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к контактам", callback_data="contact_us")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(SupplierStates.waiting_company_name)

@router.message(SupplierStates.waiting_company_name)
async def process_company_name(message: types.Message, state: FSMContext):
    """Обработка названия компании"""
    await state.update_data(company_name=message.text)
    
    text = """📞 <b>Введите контактный телефон:</b>

Укажите телефон для связи. Мы позвоним вам в рабочее время."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к контактам", callback_data="contact_us")]
    ])
    
    await update_message(message.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=message.bot)
    
    await state.set_state(SupplierStates.waiting_phone)

@router.message(SupplierStates.waiting_phone)
async def process_supplier_phone(message: types.Message, state: FSMContext):
    """Обработка телефона поставщика"""
    await state.update_data(phone=message.text)
    
    text = """📎 <b>Прикрепите файл (если нужно)</b>

Вы можете прикрепить:
• Коммерческое предложение
• Прайс-лист
• Каталог продукции
• Сертификаты качества

<b>Поддерживаемые форматы:</b>
PDF, DOC, DOCX, XLS, XLSX, JPG, PNG (до 10MB)

<b>Или нажмите "Пропустить" чтобы отправить без файла:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_supplier_file")],
        [types.InlineKeyboardButton(text="⬅️ Назад к контактам", callback_data="contact_us")]
    ])
    
    await update_message(message.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=message.bot)
    
    await state.set_state(SupplierStates.waiting_file)

@router.callback_query(F.data == "skip_supplier_file")
async def skip_supplier_file(callback: types.CallbackQuery, state: FSMContext):
    """Пропуск прикрепления файла"""
    await process_supplier_submission(callback, state, None)

@router.message(SupplierStates.waiting_file, F.document)
async def process_supplier_file(message: types.Message, state: FSMContext):
    """Обработка файла от поставщика"""
    file_id = message.document.file_id
    file_name = message.document.file_name
    file_size = message.document.file_size
    
    if file_size > 10 * 1024 * 1024:
        await message.answer("❌ Файл слишком большой! Максимальный размер: 10MB")
        return
    
    await process_supplier_submission(message, state, file_id, file_name)

@router.message(SupplierStates.waiting_file)
async def handle_supplier_text(message: types.Message):
    """Обработка текста вместо файла"""
    await message.answer("Пожалуйста, прикрепите файл или нажмите 'Пропустить'")

async def process_supplier_submission(source, state: FSMContext, file_id=None, file_name=None):
    """Обработка и отправка заявки поставщика"""
    user_id = source.from_user.id
    data = await state.get_data()
    
    username = source.from_user.username
    user_mention = f"@{username}" if username else f"Пользователь ID: {user_id}"
    
    supplier_text = f"""🏭 <b>НОВАЯ ЗАЯВКА ОТ ПОСТАВЩИКА</b>

📋 <b>Компания:</b> {data.get('company_name', 'Не указано')}
📞 <b>Телефон:</b> {data.get('phone', 'Не указано')}

👤 <b>Отправитель:</b> {user_mention}
📅 <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
    
    if file_name:
        supplier_text += f"\n📎 <b>Файл:</b> {file_name}"
    
    admin_chat_id = database.get_setting('suppliers_chat_id')
    
    if admin_chat_id:
        try:
            if file_id:
                file = await source.bot.get_file(file_id)
                downloaded_file = await source.bot.download_file(file.file_path)
                file_content = downloaded_file.read()
                
                await source.bot.send_document(
                    chat_id=int(admin_chat_id),
                    document=BufferedInputFile(file_content, filename=file_name or "file"),
                    caption=supplier_text,
                    parse_mode="HTML"
                )
            else:
                await source.bot.send_message(
                    chat_id=int(admin_chat_id),
                    text=supplier_text,
                    parse_mode="HTML"
                )
            
            success_text = """✅ <b>Ваша заявка отправлена успешно!</b>

<b>Что будет дальше:</b>
1. Наш менеджер изучит ваше предложение
2. Мы свяжемся с вами по указанному телефону
3. Обсудим детали сотрудничества

⏳ <i>Обычно мы отвечаем в течение 1-2 рабочих дней</i>

<i>Спасибо за интерес к нашему ресторану!</i>"""
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
            ])
            
            await update_message(user_id,
                               success_text,
                               reply_markup=keyboard,
                               parse_mode="HTML",
                               bot=source.bot)
            
            database.log_action(user_id, "supplier_form_submitted", 
                              f"company:{data.get('company_name', '')}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки заявки поставщика: {e}")
            
            restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
            clean_phone = clean_phone_for_link(restaurant_phone)
            
            error_text = f"""❌ <b>Ошибка отправки заявки</b>

К сожалению, произошла техническая ошибка при отправке вашей заявки.

<b>Что вы можете сделать:</b>
1. Попробовать отправить заявку позже
2. Связаться с нами по телефону: <a href="tel:{clean_phone}">{restaurant_phone}</a>
3. Написать нам в WhatsApp

<i>Приносим извинения за неудобства!</i>"""
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="suppliers_contact")],
                [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
            ])
            
            await update_message(user_id,
                               error_text,
                               reply_markup=keyboard,
                               parse_mode="HTML",
                               bot=source.bot)
    else:
        notification_text = f"""🏭 Заявка от поставщика
Компания: {data.get('company_name', 'Неизвестно')}
От: {user_mention}
Телефон: {data.get('phone', 'Не указан')}"""
        asyncio.create_task(send_admin_notification(user_id, notification_text, source.bot))
        
        info_text = """✅ <b>Ваша заявка принята!</b>

Мы получили ваше коммерческое предложение. Наши менеджеры свяжутся с вами в ближайшее время.

<i>Спасибо за интерес к сотрудничеству!</i>"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        await update_message(user_id,
                           info_text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=source.bot)
    
    await state.clear()



# ===== START И ОСНОВНЫЕ КОМАНДЫ =====

@router.message(Command("clean_my_chat"))
async def clean_my_chat_handler(message: types.Message, state: FSMContext):
    """Очистка всех сообщений в чате за 10 секунд"""
    user = message.from_user
    
    if user.is_bot:
        return
    
    logger.info(f"Получен /clean_my_chat от {user.id} ({user.username or 'нет username'})")
    
    try:
        # Отправляем сообщение о начале очистки
        status_msg = await message.bot.send_message(
            chat_id=user.id,
            text="🧹 <b>Начинаю очистку чата...</b>\n\nПожалуйста, подождите...",
            parse_mode="HTML"
        )
        
        deleted_count = 0
        current_message_id = message.message_id
        
        # Ограничиваем время работы 3 секундами
        async def cleanup_with_timeout():
            nonlocal deleted_count
            start_time = asyncio.get_event_loop().time()
            
            for msg_id in range(current_message_id, max(1, current_message_id - 1000), -1):
                # Проверяем таймаут
                if asyncio.get_event_loop().time() - start_time > 3:
                    break
                    
                try:
                    await message.bot.delete_message(user.id, msg_id)
                    deleted_count += 1
                    
                    # Обновляем статус каждые 10 сообщений
                    if deleted_count % 10 == 0:
                        try:
                            await message.bot.edit_message_text(
                                chat_id=user.id,
                                message_id=status_msg.message_id,
                                text=f"🧹 <b>Очищаю чат...</b>\n\nУдалено: {deleted_count} сообщений",
                                parse_mode="HTML"
                            )
                        except:
                            pass
                            
                except Exception:
                    continue
        
        # Запускаем очистку с таймаутом
        try:
            await asyncio.wait_for(cleanup_with_timeout(), timeout=3.0)
        except asyncio.TimeoutError:
            pass  # Таймаут - это нормально
        
        # Очищаем кэш сообщений
        if user.id in last_message_ids:
            del last_message_ids[user.id]
        
        # Показываем стартовое сообщение
        await message.bot.send_message(chat_id=user.id, text=config.START_MESSAGE, parse_mode="HTML")
        
        # Отправляем сообщение о завершении
        await message.bot.edit_message_text(
            chat_id=user.id,
            message_id=status_msg.message_id,
            text=f"✅ <b>Очистка завершена</b>\n\nУдалено: {deleted_count} сообщений",
            parse_mode="HTML"
        )
        
        # Ждем 2 секунды
        await asyncio.sleep(2)
        
        # Удаляем сообщение о завершении
        try:
            await message.bot.delete_message(user.id, status_msg.message_id)
        except Exception:
            pass
        
        logger.info(f"Очистка чата завершена для {user.id}: удалено {deleted_count} сообщений за 3 секунды")
        
    except Exception as e:
        logger.error(f"Ошибка при очистке чата для {user.id}: {e}")
        try:
            await message.bot.send_message(
                chat_id=user.id,
                text="❌ Не удалось очистить чат. Попробуйте позже.",
                parse_mode="HTML"
            )
        except:
            pass

@router.message(CommandStart())
@handler_timeout()
async def start_handler(message: types.Message, state: FSMContext):
    """Быстрый обработчик /start"""
    user = message.from_user
    
    if user.is_bot:
        return
    
    logger.info(f"Получен /start от {user.id} ({user.username or 'нет username'})")
    
    database.add_user(user.id, user.username, user.full_name)
    database.log_action(user.id, "start")
    
    await state.clear()
    
    # Отправляем только стартовое сообщение без кнопок
    await message.bot.send_message(chat_id=user.id, text=config.START_MESSAGE, parse_mode="HTML")
    
    # Удаляем сообщение /start от пользователя
    asyncio.create_task(delete_start_message_after_delay(message, 30))


# ===== КОМАНДЫ-ЯРЛЫКИ =====

@router.message(Command("bot_menu"))
@handler_timeout()
async def cmd_bot_menu(message: types.Message, state: FSMContext):
    """Открыть главное меню бота"""
    restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    
    clean_phone = clean_phone_for_link(restaurant_phone)
    
    text = f"""🍽️ <b>{restaurant_name}</b>

<b>Контакты:</b>
📍 {restaurant_address}
📞 <a href="tel:{clean_phone}">{restaurant_phone}</a>
🕐 {restaurant_hours}"""
    
    keyboard = keyboards.main_menu_with_profile(message.from_user.id)
    await safe_send_message(message.bot, message.from_user.id, text,
                           reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("menu"))
@handler_timeout()
async def cmd_menu(message: types.Message, state: FSMContext):
    """Открыть меню ресторана с проверкой возраста"""
    user_id = message.from_user.id
    
    # Проверяем, подтверждал ли пользователь возраст
    if user_id not in age_verification_cache:
        # Показываем проверку возраста
        text = """🔞 <b>Подтверждение возраста</b>

Меню ресторана содержит информацию об алкогольных напитках.

<b>Вам исполнилось 18 лет?</b>

⚠️ Употребление алкоголя лицами до 18 лет запрещено законом."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ ДА, МНЕ ЕСТЬ 18 ЛЕТ", callback_data="confirm_age_18_menu")],
            [types.InlineKeyboardButton(text="❌ НЕТ, МНЕ НЕТ 18 ЛЕТ", callback_data="deny_age_18_menu")]
        ])
        
        await safe_send_message(message.bot, message.from_user.id, text,
                               reply_markup=keyboard, parse_mode="HTML")
        return
    
    # Пользователь уже подтвердил возраст - показываем меню
    text = """🍽️ <b>Меню ресторана</b>

📱 <b>Электронное меню</b> — интерактивное меню с алкогольными напитками (требуется подтверждение возраста 18+)

📋 <b>PDF меню</b> — полное меню с барной картой для скачивания

🎉 <b>Банкетное меню</b> — специальные предложения для мероприятий

Выберите удобный для вас вариант:"""
    
    await safe_send_message(message.bot, message.from_user.id, text,
                           reply_markup=keyboards.food_menu(), parse_mode="HTML")

@router.message(Command("delivery"))
@handler_timeout()
async def cmd_delivery(message: types.Message, state: FSMContext):
    """Открыть меню доставки"""
    text = """🚚 <b>Заказать доставку</b>

📱 Мы запустили новое мини-приложение для заказа доставки!

<b>Преимущества нового приложения:</b>
• 🍽️ Полное меню с фотографиями
• 🛒 Удобная корзина
• 💳 Онлайн оплата
• 📍 Точное определение адреса
• ⏱️ Отслеживание заказа

Нажмите кнопку ниже, чтобы открыть приложение доставки:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🚚 Открыть мини-приложение", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
        [types.InlineKeyboardButton(text="🍎 App Store", url=config.APP_IOS)],
        [types.InlineKeyboardButton(text="🤖 Google Play", url=config.APP_ANDROID)],
        [types.InlineKeyboardButton(text="🟦 RuStore", url=config.APP_RUSTORE)],
        [types.InlineKeyboardButton(text="📞 Заказать по телефону", callback_data="call_us")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])
    
    await safe_send_message(message.bot, message.from_user.id, text,
                           reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("booking"))
@handler_timeout()
async def cmd_booking(message: types.Message, state: FSMContext):
    """Открыть меню бронирования"""
    await show_booking_options(message.from_user.id, message.bot)

@router.message(Command("pk"))
@handler_timeout()
async def cmd_pk(message: types.Message, state: FSMContext):
    """Открыть личный кабинет"""
    await personal_cabinet_handler(message.from_user.id, message.bot)

@router.message(Command("way"))
@handler_timeout()
async def cmd_way(message: types.Message, state: FSMContext):
    """Показать информацию о том, как нас найти"""
    restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    clean_phone = clean_phone_for_link(restaurant_phone)
    
    text = f"""📍 <b>Как нас найти</b>

<b>Адрес:</b> {restaurant_address}
<b>Телефон:</b> <a href="tel:{clean_phone}">{restaurant_phone}</a>
<b>Часы работы:</b> {restaurant_hours}

{database.get_setting('how_to_get', config.HOW_TO_GET)}"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🗺️ Открыть в Яндекс.Картах", url="https://yandex.ru/maps/213/moscow/?ll=37.550225%2C55.920305&mode=routes&rtext=~55.920257%2C37.550906&rtt=auto&ruri=~ymapsbm1%3A%2F%2Forg%3Foid%3D202266309008&z=17")],
        [types.InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")]
    ])
    
    await safe_send_message(message.bot, message.from_user.id, text, 
                           reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("rew"))
@handler_timeout()
async def cmd_rew(message: types.Message, state: FSMContext):
    """Показать отзывы"""
    await show_reviews_handler(message.from_user.id, message.bot)

@router.message(Command("call"))
@handler_timeout()
async def cmd_call(message: types.Message, state: FSMContext):
    """Показать контакты"""
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    clean_phone = clean_phone_for_link(restaurant_phone)
    
    text = f"""📞 <b>Связаться с нами</b>

<a href="tel:{clean_phone}">{restaurant_phone}</a>

<b>Часы работы:</b>
{restaurant_hours}

💬 Или напишите нам прямо здесь!"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💬 Написать оператору", callback_data="chat_operator")],
        [types.InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")]
    ])
    
    await safe_send_message(message.bot, message.from_user.id, text, 
                           reply_markup=keyboard, parse_mode="HTML")

async def delete_start_message_after_delay(message: types.Message, delay_seconds: int):
    """Удаляет сообщение через указанное количество секунд"""
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
        logger.debug(f"Сообщение /start от {message.from_user.id} удалено через {delay_seconds} секунд")
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение /start через {delay_seconds} секунд: {e}")

async def show_main_menu(user_id: int, bot):
    """Показать главное меню с динамической кнопкой ЛК/регистрации"""
    restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
    start_message = database.get_setting('start_message', config.START_MESSAGE)
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    
    clean_phone = clean_phone_for_link(restaurant_phone)
    
    text = f"""🎉 <b>{restaurant_name}</b>

{start_message}

<b>Контакты:</b>
📍 {restaurant_address}
📞 <a href="tel:{clean_phone}">{restaurant_phone}</a>
🕐 {restaurant_hours}"""
    
    # Используем динамическую клавиатуру с проверкой регистрации
    keyboard = keyboards.main_menu_with_profile(user_id)
    
    # Отправляем новое сообщение
    message = await safe_send_message(
        bot=bot,
        chat_id=user_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    
    if message and message.message_id:
        last_message_ids[user_id] = message.message_id
    else:
        logger.warning(f"Не удалось отправить главное меню пользователю {user_id}")

# ===== ОБРАБОТЧИКИ МЕНЮ =====

# Кэш для проверки возраста - запоминаем на всю сессию
age_verification_cache = {}

def is_age_verified(user_id: int) -> bool:
    """Проверяет, подтвержден ли возраст пользователя в БД"""
    try:
        # Проверяем в кэше сначала
        if user_id in age_verification_cache:
            return age_verification_cache[user_id]

        # Проверяем в БД
        age_verified = database.get_user_setting(user_id, 'age_verified', 'false') == 'true'
        age_verification_cache[user_id] = age_verified
        return age_verified
    except Exception as e:
        logger.error(f"Ошибка проверки возраста для пользователя {user_id}: {e}")
        return False

def set_age_verified(user_id: int, verified: bool):
    """Сохраняет подтверждение возраста в БД и кэше"""
    try:
        database.update_user_setting(user_id, 'age_verified', 'true' if verified else 'false')
        age_verification_cache[user_id] = verified
        logger.info(f"Возраст пользователя {user_id} {'подтвержден' if verified else 'не подтвержден'}")
    except Exception as e:
        logger.error(f"Ошибка сохранения возраста для пользователя {user_id}: {e}")

@router.callback_query(F.data == "menu_food")
async def menu_food_callback(callback: types.CallbackQuery):
    """Меню ресторана с проверкой возраста"""
    await callback.answer()

    user_id = callback.from_user.id
    log_user_action(user_id, "Открыл меню ресторана")
    
    # Проверяем, подтверждал ли пользователь возраст
    if user_id not in age_verification_cache:
        # Показываем проверку возраста
        text = """🔞 <b>Подтверждение возраста</b>

Меню ресторана содержит информацию об алкогольных напитках.

<b>Вам исполнилось 18 лет?</b>

⚠️ Употребление алкоголя лицами до 18 лет запрещено законом."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ ДА, МНЕ ЕСТЬ 18 ЛЕТ", callback_data="confirm_age_18_menu")],
            [types.InlineKeyboardButton(text="❌ НЕТ, МНЕ НЕТ 18 ЛЕТ", callback_data="deny_age_18_menu")],
            [types.InlineKeyboardButton(text="⬅️ НАЗАД В ГЛАВНОЕ МЕНЮ", callback_data="back_main")]
        ])
        
        try:
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            last_message_ids[callback.from_user.id] = callback.message.message_id
        except Exception as e:
            logger.error(f"Ошибка редактирования проверки возраста: {e}")
            await update_message(callback.from_user.id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=callback.bot)
        return
    
    # Пользователь уже подтвердил возраст - показываем меню
    text = """🍽️ <b>Меню ресторана</b>

📱 <b>Электронное меню</b> — интерактивное меню с алкогольными напитками

📋 <b>PDF меню</b> — полное меню с барной картой для скачивания

🎉 <b>Банкетное меню</b> — специальные предложения для мероприятий

Выберите удобный для вас вариант:"""
    
    try:
        await callback.bot.edit_message_text(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=keyboards.food_menu(),
            parse_mode="HTML"
        )
        last_message_ids[callback.from_user.id] = callback.message.message_id
    except Exception as e:
        logger.error(f"Ошибка редактирования меню: {e}")
        await update_message(callback.from_user.id, text,
                            reply_markup=keyboards.food_menu(),
                            parse_mode="HTML",
                            bot=callback.bot)

@router.callback_query(F.data == "confirm_age_18_menu")
async def confirm_age_18_menu_callback(callback: types.CallbackQuery):
    """Подтверждение возраста для меню"""
    await callback.answer()

    user_id = callback.from_user.id
    set_age_verified(user_id, True)  # Сохраняем подтверждение в БД

    text = """🍽️ <b>Меню ресторана</b>

📱 <b>Электронное меню</b> — интерактивное меню с алкогольными напитками

📋 <b>PDF меню</b> — полное меню с барной картой для скачивания

🎉 <b>Банкетное меню</b> — специальные предложения для мероприятий

Выберите удобный для вас вариант:"""

    try:
        await callback.bot.edit_message_text(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=keyboards.food_menu(),
            parse_mode="HTML"
        )
        last_message_ids[callback.from_user.id] = callback.message.message_id
    except Exception as e:
        logger.error(f"Ошибка редактирования меню: {e}")
        await update_message(callback.from_user.id, text,
                            reply_markup=keyboards.food_menu(),
                            parse_mode="HTML",
                            bot=callback.bot)

@router.callback_query(F.data == "deny_age_18_menu")
async def deny_age_18_menu_callback(callback: types.CallbackQuery):
    """Отказ от подтверждения возраста для меню"""
    await callback.answer()
    
    text = """🚫 <b>Доступ ограничен</b>

К сожалению, меню с алкогольными напитками доступно только лицам старше 18 лет.

📋 <b>Вы можете посмотреть:</b>
• PDF меню (без алкогольных напитков)
• Банкетное меню
• Связаться с нами для уточнения

Выберите альтернативный вариант:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 PDF МЕНЮ", callback_data="menu_pdf")],
        [types.InlineKeyboardButton(text="🎉 БАНКЕТНОЕ МЕНЮ", callback_data="menu_banquet")],
        [types.InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С НАМИ", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="⬅️ НАЗАД В ГЛАВНОЕ МЕНЮ", callback_data="back_main")]
    ])
    
    try:
        await callback.bot.edit_message_text(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        last_message_ids[callback.from_user.id] = callback.message.message_id
    except Exception as e:
        logger.error(f"Ошибка редактирования отказа: {e}")
        await update_message(callback.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)

@router.callback_query(F.data == "electronic_menu_18")
async def electronic_menu_18_callback(callback: types.CallbackQuery):
    """Проверка возраста для электронного меню"""
    await callback.answer()
    
    text = """🔞 <b>Подтверждение возраста</b>

Электронное меню содержит информацию об алкогольных напитках.

<b>Вам исполнилось 18 лет?</b>

⚠️ Употребление алкоголя лицами до 18 лет запрещено законом."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Да, мне есть 18 лет", callback_data="confirm_age_18")],
        [types.InlineKeyboardButton(text="❌ Нет, мне нет 18 лет", callback_data="deny_age_18")],
        [types.InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="menu_food")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "electronic_menu_direct")
async def electronic_menu_direct_callback(callback: types.CallbackQuery):
    """Прямое открытие электронного меню через мини-приложение"""
    await callback.answer()
    
    text = """📱 <b>Электронное меню</b>

🍽️ Добро пожаловать в наше интерактивное меню!

Здесь вы найдете:
• Полный ассортимент блюд
• Алкогольные и безалкогольные напитки
• Актуальные цены
• Детальные описания

Нажмите кнопку ниже, чтобы открыть меню:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📱 ОТКРЫТЬ ЭЛЕКТРОННОЕ МЕНЮ", web_app=types.WebAppInfo(url="https://sabyget.ru/menu/mashkovrest_77"))],
        [types.InlineKeyboardButton(text="⬅️ НАЗАД К МЕНЮ", callback_data="menu_food")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "confirm_age_18")
async def confirm_age_18_callback(callback: types.CallbackQuery):
    """Подтверждение возраста - открываем электронное меню"""
    await callback.answer()
    
    text = """📱 <b>Электронное меню</b>

🍽️ Добро пожаловать в наше интерактивное меню!

Здесь вы найдете:
• Полный ассортимент блюд
• Алкогольные и безалкогольные напитки
• Актуальные цены
• Детальные описания

Нажмите кнопку ниже, чтобы открыть меню:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📱 Открыть электронное меню", web_app=types.WebAppInfo(url="https://sabyget.ru/menu/mashkovrest_77"))],
        [types.InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="menu_food")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "deny_age_18")
async def deny_age_18_callback(callback: types.CallbackQuery):
    """Отказ от подтверждения возраста"""
    await callback.answer()
    
    text = """🚫 <b>Доступ ограничен</b>

К сожалению, электронное меню с алкогольными напитками доступно только лицам старше 18 лет.

📋 <b>Вы можете посмотреть:</b>
• PDF меню (без алкогольных напитков)
• Банкетное меню
• Связаться с нами для уточнения

Выберите альтернативный вариант:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 PDF меню", callback_data="menu_pdf")],
        [types.InlineKeyboardButton(text="🎉 Банкетное меню", callback_data="menu_banquet")],
        [types.InlineKeyboardButton(text="📞 Связаться с нами", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="menu_food")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "menu_delivery")
async def menu_delivery_callback(callback: types.CallbackQuery):
    """Обработчик доставки - теперь показывает мини-апп"""
    await callback.answer()

    user_id = callback.from_user.id
    log_user_action(user_id, "Открыл меню доставки")

    text = """🚚 <b>Заказать доставку</b>

📱 Мы запустили новое мини-приложение для заказа доставки!

<b>Преимущества нового приложения:</b>
• 🍽️ Полное меню с фотографиями
• 🛒 Удобная корзина
• 💳 Онлайн оплата
• 📍 Точное определение адреса
• ⏱️ Отслеживание заказа

Нажмите кнопку ниже, чтобы открыть приложение доставки:"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🚚 Открыть мини-приложение", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
        [types.InlineKeyboardButton(text="🍎 App Store", url=config.APP_IOS)],
        [types.InlineKeyboardButton(text="🤖 Google Play", url=config.APP_ANDROID)],
        [types.InlineKeyboardButton(text="🟦 RuStore", url=config.APP_RUSTORE)],
        [types.InlineKeyboardButton(text="📞 Заказать по телефону", callback_data="call_us")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

# ===== ИНФОРМАЦИЯ И FAQ =====

@router.callback_query(F.data == "about_us")
async def about_us_callback(callback: types.CallbackQuery):
    """Быстрая информация о нас с фото"""
    await callback.answer()
    database.log_action(callback.from_user.id, "view_about")
    
    restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    
    clean_phone = clean_phone_for_link(restaurant_phone)
    
    caption = f"""📍 <b>Как нас найти</b>

<b>Адрес:</b> {restaurant_address}

<b>Телефон:</b>
<a href="tel:{clean_phone}">{restaurant_phone}</a>

<b>Часы работы:</b>
{restaurant_hours}"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🗺️ Открыть в Яндекс.Картах", url="https://yandex.ru/maps/213/moscow/?ll=37.550225%2C55.920305&mode=routes&rtext=~55.920257%2C37.550906&rtt=auto&ruri=~ymapsbm1%3A%2F%2Forg%3Foid%3D202266309008&z=17")],
        [types.InlineKeyboardButton(text="💬 Написать", callback_data="chat_operator")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])
    
    try:
        photo_path = "files/REST_PHOTO.webp"
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo_file:
                try:
                    await callback.bot.edit_message_media(
                        chat_id=callback.from_user.id,
                        message_id=callback.message.message_id,
                        media=types.InputMediaPhoto(
                            media=BufferedInputFile(photo_file.read(), filename="restaurant.jpg"),
                            caption=caption,
                            parse_mode="HTML"
                        ),
                        reply_markup=keyboard
                    )
                    
                    last_message_ids[callback.from_user.id] = callback.message.message_id
                    
                    user_id = callback.from_user.id
                    if user_id not in user_message_history:
                        user_message_history[user_id] = []
                    user_message_history[user_id].append(callback.message.message_id)
                    
                    logger.info(f"Сообщение с фото отредактировано для пользователя {callback.from_user.id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка редактирования с фото: {e}")
                    try:
                        await callback.bot.edit_message_text(
                            chat_id=callback.from_user.id,
                            message_id=callback.message.message_id,
                            text=caption,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                        logger.info(f"Сообщение без фото отредактировано для пользователя {callback.from_user.id}")
                    except Exception as e2:
                        logger.error(f"Ошибка редактирования текста: {e2}")
                        await update_message(callback.from_user.id, caption,
                                            reply_markup=keyboard,
                                            parse_mode="HTML",
                                            bot=callback.bot)
        else:
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        try:
            await callback.bot.edit_message_text(
                chat_id=callback.from_user.id,
                message_id=callback.message.message_id,
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e2:
            await update_message(callback.from_user.id, caption,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=callback.bot)

@router.callback_query(F.data == "faq")
async def faq_callback(callback: types.CallbackQuery):
    """Быстрые FAQ"""
    await callback.answer()
    database.log_action(callback.from_user.id, "view_faq")

    user_id = callback.from_user.id
    log_user_action(user_id, "Открыл FAQ")
    
    cache_key = "faq_list"
    faq_list = cache_manager.cache.get(cache_key)
    
    if faq_list is None:
        faq_list = database.get_faq()
        cache_manager.cache.set(cache_key, faq_list, ttl=600)
    
    if not faq_list:
        text = "❓ <b>Частые вопросы</b>\n\nВопросов пока нет.\n\n<b>Не нашли ответ?</b> Нажмите '📞 Свяжитесь с нами'!"
    else:
        text = "❓ <b>Частые вопросы</b>\n\n<b>Выберите вопрос:</b>\n"
        for faq_id, question, answer in faq_list:
            text += f"• {question}\n"
        
        text += "\n<b>Не нашли ответ?</b> Нажмите '📞 Свяжитесь с нами'!"
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboards.faq_menu(faq_list),
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data.startswith("faq_"))
async def faq_answer_callback(callback: types.CallbackQuery):
    """Быстрый ответ на FAQ"""
    await callback.answer()
    
    try:
        faq_id = int(callback.data.replace("faq_", ""))
        
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

# ===== ОТЗЫВЫ =====

@router.callback_query(F.data == "reviews")
async def reviews_callback(callback: types.CallbackQuery):
    """Быстрые отзывы"""
    await callback.answer()
    await show_reviews_handler(callback.from_user.id, callback.bot)

async def show_reviews_handler(user_id: int, bot):
    """Показ отзывов - САМЫЕ СВЕЖИЕ ПЕРВЫМИ"""
    database.log_action(user_id, "view_reviews")
    
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
                    stars = "⭐" * min(int(rating) if isinstance(rating, (int, str)) and str(rating).isdigit() else 5, 5)
                    clean_text = text_review[:100] + "..." if len(text_review) > 100 else text_review
                    
                    date_display = ""
                    if date:
                        try:
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

# ===== КОНТАКТЫ И ОПЕРАТОР =====

@router.callback_query(F.data == "contact_us")
async def contact_us_callback(callback: types.CallbackQuery):
    """Быстрая связь с менеджером — с кликабельным телефоном"""
    await callback.answer()

    user_id = callback.from_user.id
    log_user_action(user_id, "Открыл контакты")

    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)

    clean_phone = clean_phone_for_link(restaurant_phone)

    text = f"""📞 <b>Связаться с нами</b>

<a href="tel:{clean_phone}">{restaurant_phone}</a>

<b>Выберите способ связи:</b>
• <b>Написать сообщение</b> — чат с оператором
• <b>Для поставщиков</b> — форма для коммерческих предложений

<i>Мы всегда рады помочь вам!</i>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💬 Написать оператору", callback_data="chat_operator")],
        [types.InlineKeyboardButton(text="🏭 Для поставщиков", callback_data="suppliers_contact")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])

    await update_message(
        callback.from_user.id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        bot=callback.bot
    )

@router.callback_query(F.data == "chat_operator")
async def chat_operator_callback(callback: types.CallbackQuery):
    """Быстрый чат с оператором"""
    await callback.answer()
    
    user_id = callback.from_user.id
    user_name = callback.from_user.full_name or f"Пользователь {user_id}"
    
    text = """💬 <b>Чат с оператором</b>

Напишите ваш вопрос прямо здесь в чат!

<b>Что можно уточнить:</b>
• Информацию о заказе
• Уточнение по доставке
• Вопросы по меню
• Предложения и пожелания
• Технические проблемы с ботом

<b>А пока посмотрите:</b>
• Частые вопросы (FAQ)
• Информацию о доставке
• Меню ресторана"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❓ FAQ", callback_data="faq")],
        [types.InlineKeyboardButton(text="🍽️ Меню", callback_data="menu_food")],
        [types.InlineKeyboardButton(text="⬅️ Назад к контактам", callback_data="contact_us")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    # Включаем режим чата для пользователя (час по умолчанию)
    set_operator_chat(user_id, True, ttl=3600)

    # Уведомляем админов индивидуально и сохраняем ID уведомлений
    async def notify_admins():
        try:
            admins = database.get_all_admins()
            notifications = {}
            notify_text = f"🔔 <b>Новый запрос:</b> Пользователь {user_name} (ID: {user_id}).\nОтвет: /reply_{user_id}  |  Завершить: /stop_chat_{user_id}"
            for admin_id in admins:
                try:
                    sent = await safe_send_message(callback.bot, admin_id, notify_text, parse_mode='HTML')
                    if sent:
                        notifications[admin_id] = sent.message_id
                except Exception as e:
                    logger.debug(f"Не удалось отправить уведомление админу {admin_id}: {e}")
            if notifications:
                set_operator_notifications(user_id, notifications)
        except Exception as e:
            logger.debug(f"Ошибка уведомления админов: {e}")

    asyncio.create_task(notify_admins())
    # Подтверждаем пользователю, что оператор оповещён
    try:
        await safe_send_message(callback.bot, user_id, "✅ Оператор оповещён — напишите ваш вопрос, мы свяжемся с вами как можно скорее.")
    except Exception:
        pass

@router.callback_query(F.data == "call_us")
async def call_us_callback(callback: types.CallbackQuery):
    """Звонок в ресторан — с кликабельной ссылкой"""
    await callback.answer()
    
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    
    clean_phone = clean_phone_for_link(restaurant_phone)

    text = f"""📞 <b>Позвонить в ресторан</b>

<a href="tel:{clean_phone}">{restaurant_phone}</a>

<b>Часы работы:</b>
{restaurant_hours}

<i>Звоните в часы работы — мы всегда на связи!</i>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к контактам", callback_data="contact_us")]
    ])
    
    try:
        await callback.bot.edit_message_text(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        last_message_ids[callback.from_user.id] = callback.message.message_id
    except Exception as e:
        logger.error(f"Ошибка редактирования меню звонка: {e}")
        await update_message(
            callback.from_user.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
            bot=callback.bot
        )

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

@router.callback_query(F.data == "our_app")
async def our_app_callback(callback: types.CallbackQuery):
    """Наше приложение"""
    await callback.answer()
    
    text = f"""📱 <b>Наше приложение</b>

Скачайте наше приложение для удобного заказа доставки и бронирования!

<b>Преимущества:</b>
• 🍽️ Полное меню с фотографиями
• 🛒 Удобная корзина
• 💳 Онлайн оплата
• 📍 Точное определение адреса
• ⏱️ Отслеживание заказа

Выберите вашу платформу:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🍎 App Store", url=config.APP_IOS)],
        [types.InlineKeyboardButton(text="🤖 Google Play", url=config.APP_ANDROID)],
        [types.InlineKeyboardButton(text="🟦 RuStore", url=config.APP_RUSTORE)],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

# ===== ТЕКСТОВЫЙ ОБРАБОТЧИК =====

@router.message(F.text, StateFilter(None))
async def handle_text_messages(message: types.Message, state: FSMContext):
    """Общий обработчик текстовых сообщений — ТОЛЬКО если нет активного состояния"""
    user = message.from_user
    text = message.text.strip().lower()
    
    if text.startswith('/'):
        return

    # Приветствия
    greetings = ['привет', 'добрый день', 'добрый вечер', 'здравствуйте', 'добро пожаловать', 'hi', 'hello']
    if any(greeting in text for greeting in greetings):
        greeting_text = f"""👋 Привет! Добро пожаловать в {database.get_setting('restaurant_name', config.RESTAURANT_NAME)}!

Я помогу вам:
• 🍽️ Посмотреть меню и заказать доставку
• 📅 Забронировать столик
• ❓ Ответить на вопросы
• 📞 Связаться с администратором

Выберите что вас интересует или напишите свой вопрос!"""
        
        keyboard = keyboards.main_menu_with_profile(user.id)
        await safe_send_message(message.bot, user.id, greeting_text, 
                               reply_markup=keyboard, parse_mode="HTML")
        return

    # Команды доставки
    delivery_keywords = ['доставка', 'заказать', 'меню', 'еда', 'блюда', 'доставить', 'можно заказать']
    if any(keyword in text for keyword in delivery_keywords):
        text = """🚚 <b>Заказать доставку</b>

📱 Мы запустили новое мини-приложение для заказа доставки!

<b>Преимущества нового приложения:</b>
• 🍽️ Полное меню с фотографиями
• 🛒 Удобная корзина
• 💳 Онлайн оплата
• 📍 Точное определение адреса
• ⏱️ Отслеживание заказа

Нажмите кнопку ниже, чтобы открыть приложение доставки:"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🚚 Открыть мини-приложение", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
            [types.InlineKeyboardButton(text="🍎 App Store", url=config.APP_IOS)],
            [types.InlineKeyboardButton(text="🤖 Google Play", url=config.APP_ANDROID)],
            [types.InlineKeyboardButton(text="🟦 RuStore", url=config.APP_RUSTORE)],
            [types.InlineKeyboardButton(text="📞 Заказать по телефону", callback_data="call_us")],
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        await safe_send_message(message.bot, user.id, text,
                               reply_markup=keyboard, parse_mode="HTML")
        return

    # Команды главного меню
    main_menu_keywords = ['главное меню', 'меню бота', 'основное меню', 'начало', 'старт']
    if any(keyword in text for keyword in main_menu_keywords):
        await show_main_menu(user.id, message.bot)
        return

    # Команды личного кабинета
    cabinet_keywords = ['личный кабинет', 'мой профиль', 'мои данные', 'кабинет']
    if any(keyword in text for keyword in cabinet_keywords):
        await personal_cabinet_handler(user.id, message.bot, state)
        return

    # Команды контактов
    contact_keywords = ['контакты', 'телефон', 'адрес', 'связаться']
    if any(keyword in text for keyword in contact_keywords):
        restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
        restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
        clean_phone = clean_phone_for_link(restaurant_phone)
        
        contact_text = f"""📞 <b>Наши контакты</b>

📍 <b>Адрес:</b> {restaurant_address}
📞 <b>Телефон:</b> <a href="tel:{clean_phone}">{restaurant_phone}</a>

💬 Или напишите нам прямо здесь!"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💬 Написать оператору", callback_data="chat_operator")],
            [types.InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")]
        ])
        
        await safe_send_message(message.bot, user.id, contact_text,
                               reply_markup=keyboard, parse_mode="HTML")
        return

    # Проверяем на прямые команды бронирования ПЕРЕД отправкой в AI
    booking_keywords = [
        'забронировать', 'забранировать', 'бронировать', 'бранировать',
        'столик', 'стол', 'бронь', 'резерв', 'резервировать',
        'хочу забронировать', 'можно забронировать', 'заказать стол',
        'заказать столик', 'столик на', 'бронь на', 'резерв на',
        'забронируй', 'забронировать стол', 'забронировать столик'
    ]

    message_lower = message.text.lower()
    is_booking_request = any(keyword in message_lower for keyword in booking_keywords)

    # Проверяем на сообщение с конкретными параметрами бронирования
    booking_details = parse_booking_message(message.text)
    if booking_details:
        logger.info(f"Обнаружен запрос бронирования с параметрами: {message.text}")
        await process_direct_booking_request(user.id, message.bot, booking_details, state)

        # Сохраняем в чат для миниаппа
        try:
            chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
            database.save_chat_message(chat_id, 'user', message.text)
            database.save_chat_message(chat_id, 'bot', f'Распознал бронирование: {booking_details["guests"]} чел., {booking_details["date_str"]}, {booking_details["time_str"]}')
        except Exception as e:
            logger.error(f"Ошибка сохранения в миниапп: {e}")

        return
    elif is_booking_request:
        # Прямой показ меню бронирования без AI
        logger.info(f"Обнаружен запрос бронирования: {message.text}")
        await show_booking_options(user.id, message.bot)

        # Сохраняем в чат для миниаппа
        try:
            chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
            database.save_chat_message(chat_id, 'user', message.text)
            database.save_chat_message(chat_id, 'bot', 'Показал меню бронирования')
        except Exception as e:
            logger.error(f"Ошибка сохранения в миниапп: {e}")

        return

    # Проверяем на алкогольные вопросы ДО вызова AI
    alcohol_keywords = ['вино', 'вина', 'пиво', 'пива', 'коньяк', 'водка', 'водки', 'виски', 'ром', 'джин', 'текила', 'ликер', 'ликера', 'коктейль', 'коктейли', 'алкоголь', 'напитки', 'напиток', 'выпить', 'пить', 'спиртное']
    message_lower = message.text.lower()
    is_alcohol_question = any(keyword in message_lower for keyword in alcohol_keywords)

    if is_alcohol_question and not is_age_verified(user.id):
        # Алкогольный вопрос и возраст не подтвержден - показываем диалог возраста
        text = """🔞 <b>Подтверждение возраста</b>

Информация содержит данные об алкогольных напитках.

<b>Вам исполнилось 18 лет?</b>

⚠️ Употребление алкоголя лицами до 18 лет запрещено законом."""

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ ДА, МНЕ ЕСТЬ 18 ЛЕТ", callback_data="confirm_age_18_menu")],
            [types.InlineKeyboardButton(text="❌ НЕТ, МНЕ НЕТ 18 ЛЕТ", callback_data="deny_age_18_menu")]
        ])

        await safe_send_message(message.bot, user.id, text, reply_markup=keyboard, parse_mode="HTML")

        # Сохраняем в чат
        try:
            chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
            database.save_chat_message(chat_id, 'user', message.text)
            database.save_chat_message(chat_id, 'bot', 'Показал диалог подтверждения возраста')
        except Exception as e:
            logger.error(f"Ошибка сохранения в миниапп: {e}")

        return

    # Всегда сохраняем сообщения пользователей в базу данных для миниаппа
    try:
        # Создаем/получаем чат для пользователя
        chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')

        # Сохраняем сообщение пользователя
        database.save_chat_message(chat_id, 'user', message.text)

        logger.info(f"Сообщение пользователя {user.id} сохранено в миниапп: {message.text[:50]}...")

    except Exception as e:
        logger.error(f"Ошибка сохранения сообщения пользователя {user.id}: {e}")

    # Если пользователь в режиме чата с оператором — пересылаем сообщение админам
    try:
        if is_operator_chat(user.id):

            from .utils import get_assigned_operator
            assigned = get_assigned_operator(user.id)
            if assigned:
                admins = [assigned]
            else:
                admins = database.get_all_admins()
            for admin_id in admins:
                try:
                    # Пересылаем любое содержимое — текст, фото, голос, документ и т.д.
                    await message.bot.forward_message(chat_id=admin_id, from_chat_id=user.id, message_id=message.message_id)

                    # Создаем клавиатуру с кнопками управления чатом
                    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{user.id}")],
                        [types.InlineKeyboardButton(text="❌ Завершить чат", callback_data=f"stop_chat_{user.id}")]
                    ])

                    await safe_send_message(message.bot, admin_id,
                                           f"💬 Новое сообщение от {user.full_name or user.id}\n\n"
                                           f"Команды: /reply_{user.id} текст_ответа\n"
                                           f"Или используйте кнопки ниже:",
                                           reply_markup=keyboard)
                except Exception as e:
                    logger.debug(f"Не удалось переслать сообщение админу {admin_id}: {e}")

            # Подтверждаем пользователю, что сообщение отправлено
            try:
                await safe_send_message(message.bot, user.id,
                                       "✅ Ваше сообщение отправлено администратору. Ожидайте ответа...")
            except Exception:
                pass

            # Удаляем сообщение пользователя чтобы не хранить в чате
            try:
                await safe_delete_message(message.bot, user.id, message.message_id)
            except Exception:
                pass
            return
    except Exception as e:
        logger.debug(f"Ошибка в обработчике операторского чата: {e}")

    # Если ничего не найдено - используем AI
    try:
        async with typing_indicator(message.bot, user.id):
            from ai_assistant import get_ai_response
            result = await get_ai_response(message.text, user.id)

        # Проверяем на показ категории
        if result.get('show_category'):
            category_name = result.get('show_category')
            logger.info(f"Показываем категорию: {category_name} для пользователя {user.id}")
            from category_handler import handle_show_category
            await handle_show_category(category_name, user.id, message.bot)

            # Сохраняем в чат
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', f'Показал категорию: {category_name}')
            except Exception as e:
                logger.error(f"Ошибка сохранения в миниапп: {e}")

            return

        # Проверяем на парсинг бронирования
        if result.get('parse_booking'):
            await safe_send_message(message.bot, user.id, result['text'])
            # Сохраняем ответ бота
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', result['text'])
            except Exception as e:
                logger.error(f"Ошибка сохранения ответа бота: {e}")
            # Показываем меню бронирования
            await show_booking_options(user.id, message.bot)
            return



        if result['type'] == 'text':
            # Проверяем нужны ли кнопки с приложениями
            if result.get('show_booking_options', False):
                # Показываем меню бронирования напрямую
                await show_booking_options(user.id, message.bot)
                return
            elif result.get('show_delivery_apps', False):
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🚚 Мини-приложение", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
                    [types.InlineKeyboardButton(text="🍎 App Store", url=config.APP_IOS)],
                    [types.InlineKeyboardButton(text="🤖 Google Play", url=config.APP_ANDROID)],
                    [types.InlineKeyboardButton(text="🟦 RuStore", url=config.APP_RUSTORE)]
                ])
                await safe_send_message(message.bot, user.id, result['text'], reply_markup=keyboard, parse_mode="HTML")
            elif result.get('show_delivery_button', False):
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://glittery-starlight-5cb21d.netlify.app/"))]
                ])
                await safe_send_message(message.bot, user.id, result['text'], reply_markup=keyboard, parse_mode="HTML")
            else:
                await safe_send_message(message.bot, user.id, result['text'])

            # Сохраняем ответ бота
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', result['text'])
            except Exception as e:
                logger.error(f"Ошибка сохранения ответа бота: {e}")

        elif result['type'] == 'photo_with_text':
            # Проверяем нужны ли кнопки
            if result.get('show_delivery_apps', False):
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🚚 Мини-приложение", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
                    [types.InlineKeyboardButton(text="🍎 App Store", url=config.APP_IOS)],
                    [types.InlineKeyboardButton(text="🤖 Google Play", url=config.APP_ANDROID)],
                    [types.InlineKeyboardButton(text="🟦 RuStore", url=config.APP_RUSTORE)]
                ])
                await message.answer_photo(result['photo_url'], caption=result['text'], reply_markup=keyboard, parse_mode="HTML")
            elif result.get('show_delivery_button', False):
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://glittery-starlight-5cb21d.netlify.app/"))]
                ])
                await message.answer_photo(result['photo_url'], caption=result['text'], reply_markup=keyboard, parse_mode="HTML")
            else:
                await message.answer_photo(result['photo_url'], caption=result['text'], parse_mode="HTML")

            # Сохраняем ответ бота
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', result['text'])
            except Exception as e:
                logger.error(f"Ошибка сохранения ответа бота: {e}")

    except Exception as e:
        logger.error(f"Ошибка AI: {e}")
        text_response = """🤖 <b>Я не понял ваш запрос</b>

Используйте кнопки меню ниже или задайте вопрос оператору."""
        keyboard = keyboards.main_menu_with_profile(user.id)
        await safe_send_message(message.bot, user.id, text_response,
                               reply_markup=keyboard, parse_mode="HTML")

        # Сохраняем ошибочный ответ бота
        try:
            chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
            database.save_chat_message(chat_id, 'bot', text_response)
        except Exception as e:
            logger.error(f"Ошибка сохранения ошибочного ответа бота: {e}")

# ===== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК =====

@router.error()
async def error_handler(event, bot):
    """Глобальный обработчик ошибки"""
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

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

@router.callback_query(F.data == "back_main")
async def back_main_callback(callback: types.CallbackQuery):
    """Быстрый возврат в главное меню - РЕДАКТИРУЕМ сообщение"""
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Очищаем старые сообщения и документы
    if user_id in user_message_history and user_message_history[user_id]:
        for msg_id in user_message_history[user_id][:]:
            if msg_id != callback.message.message_id:
                try:
                    await callback.bot.delete_message(user_id, msg_id)
                except Exception as e:
                    logger.debug(f"Не удалось удалить фото {msg_id}: {e}")
        user_message_history[user_id] = []
    
    try:
        from .handlers_delivery import user_document_history
        if user_id in user_document_history and user_document_history[user_id]:
            for doc_id in user_document_history[user_id][:]:
                try:
                    await callback.bot.delete_message(user_id, doc_id)
                except Exception as e:
                    logger.debug(f"Не удалось удалить документ {doc_id}: {e}")
            user_document_history[user_id] = []
    except ImportError:
        pass
    
    try:
        from .handlers_delivery import cleanup_carousel_messages
        await cleanup_carousel_messages(user_id, callback.bot)
    except ImportError:
        pass
    
    # Получаем данные для главного меню
    restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
    start_message = database.get_setting('start_message', config.START_MESSAGE)
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
    restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
    
    clean_phone = clean_phone_for_link(restaurant_phone)
    
    text = f"""🎉 <b>{restaurant_name}</b>

{start_message}

<b>Контакты:</b>
📍 {restaurant_address}
📞 <a href="tel:{clean_phone}">{restaurant_phone}</a>
🕐 {restaurant_hours}"""
    
    keyboard = keyboards.main_menu_with_profile(user_id)
    
    # Редактируем текущее сообщение
    try:
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # Обновляем кэш ID последнего сообщения
        last_message_ids[user_id] = callback.message.message_id
        
    except Exception as e:
        logger.error(f"Ошибка редактирования главного меню: {e}")
        # Если не удалось отредактировать, отправляем новое
        message = await safe_send_message(
            bot=callback.bot,
            chat_id=user_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        if message and message.message_id:
            last_message_ids[user_id] = message.message_id

def parse_booking_message(text):
    """
    Распознает сообщения с параметрами бронирования

    Возвращает словарь с параметрами или None если не распознано

    Форматы:
    - "3 человека, 19 января, в 19:30"
    - "2 человека, завтра, в 20:00"
    - "4 человека, сегодня, в 18:30"
    - "5 человек, через неделю, в 15:00"
    """
    text = text.lower().strip()

    # Регулярное выражение для поиска количества гостей
    guests_match = re.search(r'(\d+)\s*(человек|чел|гост|гостя)', text)
    if not guests_match:
        return None

    guests = int(guests_match.group(1))
    if guests < 1 or guests > 10:
        return None

    # Словарь месяцев
    months = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
        'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
        'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4, 'май': 5, 'июнь': 6,
        'июль': 7, 'август': 8, 'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12
    }

    # Регулярное выражение для даты
    date_match = None
    target_date = None

    # Проверяем на "сегодня", "завтра", "через неделю"
    if 'сегодня' in text:
        target_date = datetime.now().date()
    elif 'завтра' in text:
        target_date = datetime.now().date() + timedelta(days=1)
    elif 'через неделю' in text or 'через 1 неделю' in text:
        target_date = datetime.now().date() + timedelta(weeks=1)
    else:
        # Ищем дату типа "19 января"
        date_match = re.search(r'(\d{1,2})\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)', text)
        if date_match:
            day = int(date_match.group(1))
            month_name = date_match.group(2)
            if month_name in months and 1 <= day <= 31:
                current_year = datetime.now().year
                try:
                    target_date = date(current_year, months[month_name], day)
                    # Если дата уже прошла в этом году, переносим на следующий год
                    if target_date < datetime.now().date():
                        target_date = date(current_year + 1, months[month_name], day)
                except ValueError:
                    return None

    if not target_date:
        return None

    # Регулярное выражение для времени
    time_match = re.search(r'(\d{1,2})[:\.](\d{2})', text)
    if not time_match:
        return None

    hours = int(time_match.group(1))
    minutes = int(time_match.group(2))

    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None

    # Форматируем время
    time_str = f"{hours:02d}:{minutes:02d}"
    date_str = target_date.strftime("%d.%m.%Y")

    return {
        'guests': guests,
        'date': target_date,
        'time': time_str,
        'date_str': date_str,
        'time_str': time_str
    }

async def process_direct_booking_request(user_id: int, bot, booking_details: dict, state: FSMContext):
    """
    Обрабатывает прямой запрос бронирования с параметрами и сразу показывает схему столов
    """
    from .handlers_booking import BookingStates

    logger.info(f"Обрабатываю прямую бронь: {booking_details}")

    # Проверяем регистрацию
    if check_user_registration_fast(user_id) != 'completed':
        from .handlers_registration import ask_for_registration_phone, RegistrationStates
        await ask_for_registration_phone(user_id, bot, "direct_booking")
        await state.set_state(RegistrationStates.waiting_for_phone)
        # Сохраняем детали бронирования для восстановления после регистрации
        await state.update_data(direct_booking_details=booking_details)
        return

    # Заполняем state данными бронирования
    await state.update_data(
        guests=booking_details['guests'],
        selected_date=booking_details['date_str'],
        selected_time=booking_details['time_str']
    )

    # Получаем календарь для проверки доступности даты
    from datetime import datetime
    dt_obj = datetime.strptime(booking_details['date_str'], "%d.%m.%Y")
    api_date = dt_obj.strftime("%Y-%m-%d")

    # Импортируем функции для работы с API
    try:
        from presto_api_booking import get_booking_calendar

        # Получаем календарь на месяц
        from_date = dt_obj.replace(day=1).strftime("%d.%m.%Y")
        to_date = (dt_obj.replace(day=1) + timedelta(days=62)).replace(day=1).strftime("%d.%m.%Y")

        calendar_data = get_booking_calendar(from_date, to_date)
        if calendar_data and calendar_data.get("dates"):
            await state.update_data(presto_calendar=calendar_data)
        else:
            logger.warning("Не удалось получить календарь, продолжаем без него")

    except ImportError:
        logger.warning("Presto API недоступен, продолжаем без календаря")

    # Определяем категорию времени (утро/обед/вечер)
    hours = int(booking_details['time'].split(':')[0])
    if 8 <= hours < 12:
        time_category = "morning"
    elif 12 <= hours < 16:
        time_category = "lunch"
    else:
        time_category = "evening"

    await state.update_data(selected_time_category=time_category)

    # Получаем доступные столы для выбранного времени
    try:
        from presto_api_booking import get_available_tables, get_hall_tables

        datetime_api = f"{api_date} {booking_details['time']}:00"
        available_tables = get_available_tables(datetime_api, booking_details['guests'])

        from .handlers_booking import filter_tables_by_guests
        filtered_tables = filter_tables_by_guests(available_tables, booking_details['guests'])

        if not filtered_tables:
            await safe_send_message(bot, user_id,
                f"❌ К сожалению, нет свободных столов на {booking_details['guests']} человек на {booking_details['date_str']} в {booking_details['time_str']}.\n\n"
                f"Попробуйте выбрать другое время или дату.",
                parse_mode="HTML")
            return

        await state.update_data(
            booking_datetime=datetime_api,
            filtered_tables=filtered_tables
        )

        # Получаем информацию о зале для генерации схемы
        hall_data = get_hall_tables(datetime_api)
        if hall_data and isinstance(hall_data, dict) and hall_data.get("halls"):
            # hall_data["halls"] может быть списком или словарём
            halls = hall_data["halls"]
            if isinstance(halls, list) and halls:
                # Если список, берём первый элемент
                hall = halls[0]
                hall_id = hall.get("id") or hall.get("hall_id") or 3596
            elif isinstance(halls, dict) and halls:
                # Если словарь, берём первый ключ
                hall_id = next(iter(halls.keys()))
            else:
                hall_id = 3596  # fallback

            await state.update_data(hall_id=int(hall_id))

            # Генерируем схему зала
            from .handlers_booking import generate_hall_schema, _schema_message_id

            schema_id = f"direct_booking_{user_id}_{int(datetime.now().timestamp())}"
            image_path, free_table_ids = generate_hall_schema(
                hall_data,
                booking_details['guests'],
                schema_id,
                booking_details['date_str'],
                booking_details['time_str']
            )

            if image_path and os.path.exists(image_path):
                try:
                    from aiogram.types import FSInputFile

                    photo = FSInputFile(image_path)

                    # Создаем кнопки выбора столиков
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

                    if row:
                        kb.append(row)

                    # Добавляем дополнительные кнопки
                    if filtered_tables:
                        kb.append([InlineKeyboardButton(
                            text="🎲 ВЫБРАТЬ ЛЮБОЙ СТОЛ",
                            callback_data="random_table"
                        )])

                    kb.append([InlineKeyboardButton(text="⬅️ ВЫБРАТЬ ДРУГОЕ ВРЕМЯ", callback_data="back_to_time_selection")])
                    kb.append([InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="cancel_booking")])

                    # Отправляем схему с кнопками
                    sent_message = await bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption=f"🪑 <b>Схема зала и выбор столика</b>\n\n"
                               f"📅 Дата: {booking_details['date_str']}\n"
                               f"🕐 Время: {booking_details['time_str']}\n"
                               f"👥 Гостей: {booking_details['guests']}\n\n"
                               f"🟢 — свободен и доступен для брони\n"
                               f"🔴 — занят\n"
                               f"⚫ — бронь недоступна\n\n"
                               f"👇 <b>Выберите стол:</b>",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
                    )

                    _schema_message_id = sent_message.message_id
                    await state.set_state(BookingStates.waiting_for_table)

                    logger.info(f"Показал схему столов для прямой брони: {user_id}")
                    return

                except Exception as e:
                    logger.error(f"Ошибка отправки схемы: {e}")

        # Если схема недоступна, показываем кнопки выбора столов
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

        kb.append([InlineKeyboardButton(text="⬅️ Выбрать другое время", callback_data="back_to_time_selection")])
        kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")])

        await safe_send_message(bot, user_id,
            f"👇 <b>Выберите стол для бронирования:</b>\n\n"
            f"📅 Дата: {booking_details['date_str']}\n"
            f"🕐 Время: {booking_details['time_str']}\n"
            f"👥 Гостей: {booking_details['guests']}\n\n"
            f"Доступные столы:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML"
        )

        await state.set_state(BookingStates.waiting_for_table)
        logger.info(f"Показал список столов для прямой брони: {user_id}")

    except Exception as e:
        logger.error(f"Ошибка обработки прямой брони: {e}")
        await safe_send_message(bot, user_id,
            f"❌ Произошла ошибка при обработке бронирования.\n\n"
            f"Попробуйте воспользоваться обычным конструктором бронирования.",
            parse_mode="HTML"
        )

print("✅ handlers_main.py загружен с AI!")
