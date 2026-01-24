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
async def show_booking_options(callback_or_user_id, bot=None):
    """Показать опции бронирования"""
    # Определяем тип входных данных
    if hasattr(callback_or_user_id, 'from_user'):
        # Это callback
        callback = callback_or_user_id
        user_id = callback.from_user.id
        bot = callback.bot
        # Пытаемся отредактировать сообщение
        try:
            await callback.message.edit_text(
                "📅 <b>Бронирование столика</b>\n\n"
                "Вы можете забронировать столик двумя способами:\n\n"
                "1️⃣ Через наш конструктор бронирования (с выбором стола на схеме)\n"
                "2️⃣ Написать мне в чате, и я сам забронирую для вас!\n\n"
                "💡 <b>Пример сообщения:</b> \"3 человека, 19 января, в 19:30\"\n\n"
                "ℹ️ <b>Важно:</b> Автоматическое бронирование доступно до 4 человек.\n"
                "Для компаний от 5 человек свяжитесь с оператором.\n\n"
                "Выберите удобный для вас способ:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📍 Конструктор бронирования", callback_data="new_booking")],
                    [InlineKeyboardButton(text="💬 Забронировать в чате", callback_data="chat_operator")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
                ]),
                parse_mode="HTML"
            )
            return
        except Exception:
            pass  # Если редактирование не удалось, продолжаем с отправкой нового сообщения
    else:
        # Это user_id и bot
        user_id = callback_or_user_id
        if bot is None:
            return

    # Импортируем реальную функцию из handlers_booking
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
    # 🔴 БЛОКИРУЮЩАЯ ПРОВЕРКА: Если пользователь в режиме админ-чата, игнорируем ВСЕ действия
    if is_operator_chat(callback.from_user.id):
        logger.info(f"🚫 ПОЛЬЗОВАТЕЛЬ {callback.from_user.id} В РЕЖИМЕ АДМИН-ЧАТА - ИГНОРИРУЕМ CALLBACK")
        return

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


@router.callback_query(F.data == "show_banquet_menu_xls")
async def show_banquet_menu_xls_handler(callback: types.CallbackQuery):
    """Отправка банкетного меню (XLS)"""
    await callback.answer("📤 Отправляю меню...")
    
    banquet_menu_path = "files/menu/MenuBanket.xlsx"
    
    try:
        if os.path.exists(banquet_menu_path):
            with open(banquet_menu_path, 'rb') as file:
                await callback.bot.send_document(
                    chat_id=callback.from_user.id,
                    document=BufferedInputFile(
                        file.read(),
                        filename="Menu_Banket_Mashkov_Rest.xlsx"
                    ),
                    caption="🎉 <b>Банкетное меню</b>\n\nСпециальное предложение для ваших мероприятий!",
                    parse_mode="HTML"
                )
        else:
            await callback.answer("❌ Файл меню не найден", show_alert=True)
            logger.error(f"Файл банкетного меню не найден: {banquet_menu_path}")
            
    except Exception as e:
        logger.error(f"Ошибка отправки банкетного меню: {e}")
        await callback.answer("❌ Ошибка отправки файла", show_alert=True)


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

    # Проверяем на вопрос о персонаже для отправки промежуточного сообщения
    character_question_match = re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+заходил', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+заходила', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+заходили', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+был', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+была', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+были', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+приходил', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+приходила', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^А\s+([А-Яа-яЁёA-Za-z\s]+)\s+приходили', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^([А-Яа-яЁёA-Za-z\s]+)\s+заходил', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^([А-Яа-яЁёA-Za-z\s]+)\s+заходила', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^([А-Яа-яЁёA-Za-z\s]+)\s+заходили', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^([А-Яа-яЁёA-Za-z\s]+)\s+приходил', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^([А-Яа-яЁёA-Za-z\s]+)\s+приходила', message.text.strip(), re.IGNORECASE) or \
                              re.search(r'^([А-Яа-яЁёA-Za-z\s]+)\s+приходили', message.text.strip(), re.IGNORECASE)

    if character_question_match:
        character_name = character_question_match.group(1).strip()
        logger.info(f"Обнаружен вопрос о персонаже: '{character_name}' - отправляем промежуточное сообщение")

        # Отправляем промежуточное сообщение перед генерацией
        await safe_send_message(message.bot, user_id, f"📸 Сейчас сфотографирую {character_name}, секунду! ⏳")
        logger.info(f"Отправлено промежуточное сообщение для {character_name}")

        # Добавляем небольшую задержку чтобы сообщение успело отобразиться
        import asyncio
        await asyncio.sleep(1)
    
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

<i>Или напишите нам прямо здесь!</i>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💬 Написать оператору", callback_data="chat_operator")],
        [types.InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")]
    ])

    await safe_send_message(message.bot, message.from_user.id, text,
                           reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("restart_menu"))
@handler_timeout()
async def cmd_restart_menu(message: types.Message, state: FSMContext):
    """Принудительное обновление меню из Presto API"""
    user_id = message.from_user.id

    # Проверяем, является ли пользователь админом
    if not database.is_admin(user_id):
        await safe_send_message(message.bot, user_id,
                               "❌ Эта команда доступна только администраторам.",
                               parse_mode="HTML")
        return

    await safe_send_message(message.bot, user_id,
                           "🔄 <b>Начинаю обновление меню...</b>\n\nПожалуйста, подождите...",
                           parse_mode="HTML")

    try:
        # Импортируем функцию загрузки меню
        from menu_cache import menu_cache

        # Обновляем меню с принудительной перезагрузкой
        menus = await menu_cache.load_all_menus(force_update=True)

        if menus:
            total_items = 0
            for menu_id, menu_data in menus.items():
                for cat_id, cat_data in menu_data.get('categories', {}).items():
                    total_items += len(cat_data.get('items', []))

            await safe_send_message(message.bot, user_id,
                                   f"✅ <b>Меню успешно обновлено!</b>\n\n"
                                   f"📊 Загружено {len(menus)} меню\n"
                                   f"🍽️ Всего позиций: {total_items}\n\n"
                                   f"🕐 Обновлено: {datetime.now().strftime('%H:%M:%S')}",
                                   parse_mode="HTML")
        else:
            await safe_send_message(message.bot, user_id,
                                   "❌ <b>Ошибка обновления меню</b>\n\n"
                                   "Не удалось загрузить меню из Presto API.",
                                   parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при обновлении меню: {e}")
        await safe_send_message(message.bot, user_id,
                               f"❌ <b>Ошибка обновления меню</b>\n\n"
                               f"Подробности: {str(e)}",
                               parse_mode="HTML")

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
    # 🔴 БЛОКИРУЮЩАЯ ПРОВЕРКА: Если пользователь в режиме админ-чата, игнорируем ВСЕ действия
    if is_operator_chat(callback.from_user.id):
        logger.info(f"🚫 ПОЛЬЗОВАТЕЛЬ {callback.from_user.id} В РЕЖИМЕ АДМИН-ЧАТА - ИГНОРИРУЕМ CALLBACK")
        return

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
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboards.faq_menu(faq_list),
        parse_mode="HTML"
    )

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

@router.callback_query(F.data == "event_registration")
async def event_registration_callback(callback: types.CallbackQuery):
    """Регистрация на мероприятия"""
    await callback.answer()

    user_id = callback.from_user.id
    log_user_action(user_id, "Открыл регистрацию на мероприятия")

    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    clean_phone = clean_phone_for_link(restaurant_phone)

    text = f"""🎉 <b>Регистрация на мероприятия</b>

Мы регулярно проводим интересные мероприятия в нашем ресторане.

Для регистрации на мероприятия свяжитесь с нами:

📞 <a href="tel:{clean_phone}">{restaurant_phone}</a>

<i>Наши менеджеры расскажут о предстоящих событиях и помогут с регистрацией!</i>"""

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.event_registration_menu(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения в event_registration_callback: {e}")
        # Если редактирование не удалось, отправляем новое сообщение
        await safe_send_message(
            callback.bot,
            user_id,
            text,
            reply_markup=keyboards.event_registration_menu(),
            parse_mode="HTML"
        )

async def send_private_event_application_to_admin(user_id: int, bot, event_type: str = None):
    """Отправка СРОЧНОЙ заявки на частное мероприятие администратору"""
    try:
        # Получаем данные пользователя
        user_data = database.get_user_complete_data(user_id)
        name = user_data.get('name', 'Не указано') if user_data else 'Не указано'
        phone = user_data.get('phone', 'Не указано') if user_data else 'Не указано'
        
        # Получаем username
        username = None
        try:
            user_info = await bot.get_chat(user_id)
            username = user_info.username
        except:
            username = None
        
        # Определяем тип мероприятия для отображения
        event_type_display = {
            'день_рождения': '🎂 День рождения',
            'свадьба': '💒 Свадьба',
            'корпоратив': '🏢 Корпоратив',
            'юбилей': '🎊 Юбилей',
            'детский_праздник': '🎈 Детский праздник',
            'другое': '🎭 Другое мероприятие'
        }
        
        event_display = event_type_display.get(event_type, '🎉 Частное мероприятие') if event_type else '🎉 Частное мероприятие'
        
        # Формируем СРОЧНОЕ сообщение для админа
        from datetime import datetime
        admin_text = f"""🚨 <b>ЗАЯВКА НА ЧАСТНОЕ МЕРОПРИЯТИЕ</b>

🎉 <b>Тип:</b> {event_display}

👤 <b>Клиент:</b> {name}
📱 <b>Телефон:</b> {phone}
🆔 <b>Telegram:</b> @{username if username else 'не указан'}
🆔 <b>ID:</b> {user_id}

⚡ <b>ПОВЫШЕННЫЙ ПРИОРИТЕТ!</b>

⏰ <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
        
        # Отправляем всем админам
        all_users = database.get_all_users()
        admin_ids = [user[0] for user in all_users if database.is_admin(user[0])]
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, admin_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка отправки срочной заявки на мероприятие админу {admin_id}: {e}")
        
        logger.info(f"СРОЧНАЯ заявка на частное мероприятие ({event_type}) от пользователя {user_id} отправлена админам")
        
    except Exception as e:
        logger.error(f"Ошибка отправки срочной заявки на частное мероприятие: {e}")

@router.callback_query(F.data == "show_main_menu_after_private_event")
async def show_main_menu_after_private_event_callback(callback: types.CallbackQuery):
    """Показать основное меню после регистрации на частное мероприятие"""
    await callback.answer()
    
    try:
        # Отправляем основное меню (PDF)
        menu_path = "files/menu/Menu.pdf"
        if os.path.exists(menu_path):
            with open(menu_path, 'rb') as menu_file:
                await callback.bot.send_document(
                    callback.from_user.id,
                    BufferedInputFile(menu_file.read(), filename="Основное_меню.pdf"),
                    caption="📋 <b>Основное меню ресторана Mashkov</b>\n\nВот наше полное меню с актуальными ценами!",
                    parse_mode="HTML"
                )
        else:
            await callback.bot.send_message(
                callback.from_user.id,
                "📋 <b>Основное меню</b>\n\nК сожалению, файл меню временно недоступен. Свяжитесь с нами для получения актуального меню.",
                parse_mode="HTML"
            )
        
        # Редактируем исходное сообщение
        await callback.message.edit_text(
            "✅ <b>Основное меню отправлено!</b>\n\nНаш менеджер скоро свяжется с вами для обсуждения деталей мероприятия.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
            ]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка отправки основного меню после частного мероприятия: {e}")

@router.callback_query(F.data == "show_banquet_menu_after_private_event")
async def show_banquet_menu_after_private_event_callback(callback: types.CallbackQuery):
    """Показать банкетное меню после регистрации на частное мероприятие"""
    await callback.answer()
    
    try:
        # Отправляем банкетное меню (Excel)
        banquet_menu_path = "files/menu/MenuBanket.xlsx"
        if os.path.exists(banquet_menu_path):
            with open(banquet_menu_path, 'rb') as banquet_file:
                await callback.bot.send_document(
                    callback.from_user.id,
                    BufferedInputFile(banquet_file.read(), filename="Банкетное_меню.xlsx"),
                    caption="🍾 <b>Банкетное меню ресторана Mashkov</b>\n\nСпециальные предложения для торжественных мероприятий!",
                    parse_mode="HTML"
                )
        else:
            await callback.bot.send_message(
                callback.from_user.id,
                "🍾 <b>Банкетное меню</b>\n\nК сожалению, файл банкетного меню временно недоступен. Свяжитесь с нами для получения актуального предложения.",
                parse_mode="HTML"
            )
        
        # Редактируем исходное сообщение
        await callback.message.edit_text(
            "✅ <b>Банкетное меню отправлено!</b>\n\nНаш менеджер скоро свяжется с вами для обсуждения деталей мероприятия.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
            ]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка отправки банкетного меню после частного мероприятия: {e}")

@router.callback_query(F.data == "show_both_menus_after_private_event")
async def show_both_menus_after_private_event_callback(callback: types.CallbackQuery):
    """Показать оба меню после регистрации на частное мероприятие"""
    await callback.answer()
    
    try:
        # Отправляем основное меню (PDF)
        menu_path = "files/menu/Menu.pdf"
        if os.path.exists(menu_path):
            with open(menu_path, 'rb') as menu_file:
                await callback.bot.send_document(
                    callback.from_user.id,
                    BufferedInputFile(menu_file.read(), filename="Основное_меню.pdf"),
                    caption="📋 <b>Основное меню ресторана Mashkov</b>",
                    parse_mode="HTML"
                )
        
        # Отправляем банкетное меню (Excel)
        banquet_menu_path = "files/menu/MenuBanket.xlsx"
        if os.path.exists(banquet_menu_path):
            with open(banquet_menu_path, 'rb') as banquet_file:
                await callback.bot.send_document(
                    callback.from_user.id,
                    BufferedInputFile(banquet_file.read(), filename="Банкетное_меню.xlsx"),
                    caption="🍾 <b>Банкетное меню ресторана Mashkov</b>\n\nСпециальные предложения для торжественных мероприятий!",
                    parse_mode="HTML"
                )
        
        # Редактируем исходное сообщение
        await callback.message.edit_text(
            "✅ <b>Оба меню отправлены!</b>\n\nТеперь вы можете ознакомиться с нашими предложениями. Наш менеджер скоро свяжется с вами для обсуждения деталей мероприятия.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
            ]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка отправки обоих меню после частного мероприятия: {e}")

@router.callback_query(F.data == "event_application")
async def event_application_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало процесса подачи заявки на мероприятие"""
    await callback.answer()
    
    user_id = callback.from_user.id
    log_user_action(user_id, "Начал подачу заявки на мероприятие")
    
    # Проверяем регистрацию пользователя
    if check_user_registration_fast(user_id) != 'completed':
        # Для незарегистрированных пользователей запускаем процесс регистрации
        from .handlers_registration import ask_for_event_registration_phone, EventRegistrationStates
        await ask_for_event_registration_phone(user_id, callback.bot, "event_registration")
        await state.set_state(EventRegistrationStates.waiting_for_phone)
        return
    
    # Если пользователь уже зарегистрирован, отправляем заявку
    await send_event_application_to_admin(user_id, callback.bot)
    
    # Всегда редактируем сообщение с благодарностью и кнопкой "Назад"
    text = """✅ <b>Спасибо за заявку!</b>

С вами скоро свяжутся для выяснения деталей и подтверждения регистрации.

📞 Если у вас есть срочные вопросы, вы можете связаться с нами напрямую."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Сообщение успешно отредактировано для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения в event_application_callback: {e}")
        # Если редактирование не удалось, отправляем новое сообщение
        await safe_send_message(
            callback.bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

@router.message(Command("event"))
async def event_command(message: types.Message):
    """Команда /event - показать меню мероприятий"""
    user_id = message.from_user.id
    log_user_action(user_id, "Использовал команду /event")

    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    clean_phone = clean_phone_for_link(restaurant_phone)

    text = f"""🎉 <b>Регистрация на мероприятия</b>

Мы регулярно проводим интересные мероприятия в нашем ресторане.

Для регистрации на мероприятия свяжитесь с нами:

📞 <a href="tel:{clean_phone}">{restaurant_phone}</a>

<i>Наши менеджеры расскажут о предстоящих событиях и помогут с регистрацией!</i>"""

    try:
        await safe_send_message(
            message.bot,
            user_id,
            text,
            reply_markup=keyboards.event_registration_menu(),
            parse_mode="HTML"
        )
        logger.info(f"Отправлено меню мероприятий по команде /event пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки меню мероприятий по команде /event пользователю {user_id}: {e}")

async def show_private_event_options_menu(user_id: int, bot):
    """Показать опции для частных мероприятий с двумя кнопками"""
    text = """🎉 <b>Организация частных мероприятий</b>

Да, конечно! Я могу забронировать дату под ваше мероприятие, могу многое рассказать и дать ответы на большинство вопросов.

Но лучше оставьте свой номер телефона и мы вам перезвоним в ближайшее время. 

Также я могу позвать человека и он ответит на ваши вопросы прямо здесь! 📞"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📱 Оставить телефон", callback_data="private_event_type_selection")],
        [types.InlineKeyboardButton(text="👨‍💼 Позвать человека", callback_data="contact_us")],
        [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
    ])

    try:
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Отправлено меню опций частных мероприятий пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки меню опций частных мероприятий пользователю {user_id}: {e}")

async def show_private_event_registration_menu(user_id: int, bot):
    """Показать меню регистрации частных мероприятий (дни рождения, свадьбы, корпоративы)"""
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)

    text = f"""🎉 <b>Организация частных мероприятий</b>

Мы поможем организовать ваше идеальное мероприятие:

🎂 <b>Дни рождения</b> - торжественные празднования
💒 <b>Свадьбы</b> - незабываемые церемонии  
🏢 <b>Корпоративы</b> - деловые встречи
🎊 <b>Юбилеи</b> - особенные даты
🎈 <b>Детские праздники</b> - веселье для малышей

<b>⚡ СРОЧНО! Оставьте заявку, и наш менеджер свяжется с вами в течение 15 минут!</b>

📞 Или звоните прямо сейчас: {restaurant_phone}"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📝 ОСТАВИТЬ СРОЧНУЮ ЗАЯВКУ", callback_data="private_event_type_selection")],
        [types.InlineKeyboardButton(text="⬅️ НАЗАД В ГЛАВНОЕ МЕНЮ", callback_data="back_main")]
    ])

    try:
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Отправлено меню частных мероприятий пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки меню частных мероприятий пользователю {user_id}: {e}")

@router.callback_query(F.data == "private_event_type_selection")
async def private_event_type_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    """Выбор типа частного мероприятия"""
    await callback.answer()
    
    text = """🎉 <b>Выберите тип мероприятия</b>

Какое мероприятие вы хотите организовать?"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🎂 День рождения", callback_data="private_event_type:день_рождения")],
        [types.InlineKeyboardButton(text="💒 Свадьба", callback_data="private_event_type:свадьба")],
        [types.InlineKeyboardButton(text="🏢 Корпоратив", callback_data="private_event_type:корпоратив")],
        [types.InlineKeyboardButton(text="🎊 Юбилей", callback_data="private_event_type:юбилей")],
        [types.InlineKeyboardButton(text="🎈 Детский праздник", callback_data="private_event_type:детский_праздник")],
        [types.InlineKeyboardButton(text="🎭 Другое мероприятие", callback_data="private_event_type:другое")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения выбора типа мероприятия: {e}")
        await safe_send_message(
            callback.bot,
            callback.from_user.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("private_event_type:"))
async def private_event_type_selected_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора типа частного мероприятия"""
    await callback.answer()
    
    user_id = callback.from_user.id
    event_type = callback.data.split(":", 1)[1]
    
    # Сохраняем тип мероприятия в состоянии
    await state.update_data(event_type=event_type, context='private_event_registration')
    
    log_user_action(user_id, f"Выбрал тип мероприятия: {event_type}")
    
    # Проверяем регистрацию пользователя
    if check_user_registration_fast(user_id) != 'completed':
        # Для незарегистрированных пользователей запускаем процесс регистрации
        from .handlers_registration import ask_for_event_registration_phone, EventRegistrationStates
        await ask_for_event_registration_phone(user_id, callback.bot, "private_event_registration")
        await state.set_state(EventRegistrationStates.waiting_for_phone)
        return
    
    # Если пользователь уже зарегистрирован, отправляем срочную заявку с типом мероприятия
    await send_private_event_application_to_admin(user_id, callback.bot, event_type)
    
    # Показываем подтверждение с предложением меню
    await show_private_event_confirmation_with_menu(user_id, callback.bot, callback.message, event_type)

async def show_private_event_confirmation_with_menu(user_id: int, bot, message, event_type: str):
    """Показать подтверждение заявки с предложением меню"""
    event_type_emoji = {
        'день_рождения': '🎂',
        'свадьба': '💒',
        'корпоратив': '🏢',
        'юбилей': '🎊',
        'детский_праздник': '🎈',
        'другое': '🎭'
    }
    
    emoji = event_type_emoji.get(event_type, '🎉')
    event_name = event_type.replace('_', ' ').title()
    
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
    
    try:
        await message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Показано подтверждение заявки на {event_type} для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка показа подтверждения заявки: {e}")
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

async def show_event_registration_menu(user_id: int, bot):
    """Показать меню регистрации на мероприятия"""
    restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
    clean_phone = clean_phone_for_link(restaurant_phone)

    text = f"""🎉 <b>Регистрация на мероприятия</b>

Мы регулярно проводим интересные мероприятия в нашем ресторане.

Для регистрации на мероприятия свяжитесь с нами:

📞 <a href="tel:{clean_phone}">{restaurant_phone}</a>

<i>Наши менеджеры расскажут о предстоящих событиях и помогут с регистрацией!</i>"""

    try:
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboards.event_registration_menu(),
            parse_mode="HTML"
        )
        logger.info(f"Отправлено меню регистрации на мероприятия пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки меню регистрации на мероприятия пользователю {user_id}: {e}")

async def send_event_application_to_admin(user_id: int, bot):
    """Отправка заявки на мероприятие администратору для зарегистрированного пользователя"""
    try:
        # Получаем данные пользователя
        user_data = database.get_user_complete_data(user_id)
        name = user_data.get('name', 'Не указано') if user_data else 'Не указано'
        phone = user_data.get('phone', 'Не указано') if user_data else 'Не указано'
        
        # Получаем username
        username = None
        try:
            user_info = await bot.get_chat(user_id)
            username = user_info.username
        except:
            username = None
        
        # Формируем сообщение для админа
        from datetime import datetime
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

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
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

async def show_our_app_menu(user_id: int, bot):
    """Показать меню приложений (helper function for AI assistant)"""
    text = f"""📱 <b>Наше приложение</b>

Скачайте наше приложение для удобного заказа доставки и бронирования!

<b>Преимущества нашего приложения:</b>
• 🎉 Анонсы мероприятий и событий
• 🍽️ Полное меню с фотографиями
• 🛒 Удобная корзина для заказов
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
    
    try:
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Отправлено меню приложений пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки меню приложений пользователю {user_id}: {e}")

@router.callback_query(F.data == "our_app")
async def our_app_callback_handler(callback: types.CallbackQuery):
    """Показать меню приложений"""
    await callback.answer()
    
    text = f"""📱 <b>Наше приложение</b>

Скачайте наше приложение для удобного заказа доставки и бронирования!

<b>Преимущества нашего приложения:</b>
• 🎉 Анонсы мероприятий и событий
• 🍽️ Полное меню с фотографиями
• 🛒 Удобная корзина для заказов
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
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        logger.info(f"Отправлено меню приложений пользователю {callback.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения в our_app_callback: {e}")
        # Если редактирование не удалось, отправляем новое сообщение
        await safe_send_message(
            callback.bot,
            callback.from_user.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

async def show_hall_photos(user_id: int, bot):
    """Показать фотографии зала"""
    try:
        # Отправляем фото зала
        hall_photos = ['rest_photos/holl1.jpg', 'rest_photos/holl2.jpg']
        photos_sent = 0
        
        for i, photo_path in enumerate(hall_photos):
            if os.path.exists(photo_path):
                try:
                    # Проверяем размер файла
                    file_size = os.path.getsize(photo_path)
                    logger.info(f"Отправляем фото {photo_path}, размер: {file_size / (1024*1024):.1f}MB")
                    
                    if file_size > 10 * 1024 * 1024:  # 10MB limit
                        logger.warning(f"Файл {photo_path} слишком большой ({file_size / (1024*1024):.1f}MB), отправляем как документ")
                        # Отправляем как документ
                        with open(photo_path, 'rb') as photo:
                            await bot.send_document(
                                user_id,
                                BufferedInputFile(photo.read(), filename=f"hall_{i+1}.jpg"),
                                caption=f"🏛️ <b>Наш уютный зал</b> ({i+1}/{len(hall_photos)})" if i == 0 else f"🏛️ <b>Фото зала</b> ({i+1}/{len(hall_photos)})",
                                parse_mode="HTML"
                            )
                            photos_sent += 1
                    else:
                        try:
                            with open(photo_path, 'rb') as photo:
                                caption = f"🏛️ <b>Наш уютный зал</b> ({i+1}/{len(hall_photos)})" if i == 0 else None
                                await bot.send_photo(
                                    user_id,
                                    BufferedInputFile(photo.read(), filename=f"hall_{i+1}.jpg"),
                                    caption=caption,
                                    parse_mode="HTML"
                                )
                                photos_sent += 1
                        except Exception as photo_send_error:
                            # Если не удалось отправить как фото (например, PHOTO_INVALID_DIMENSIONS), отправляем как документ
                            logger.warning(f"Не удалось отправить {photo_path} как фото ({photo_send_error}), отправляем как документ")
                            try:
                                with open(photo_path, 'rb') as photo:
                                    await bot.send_document(
                                        user_id,
                                        BufferedInputFile(photo.read(), filename=f"hall_{i+1}.jpg"),
                                        caption=f"🏛️ <b>Наш уютный зал</b> ({i+1}/{len(hall_photos)})" if i == 0 else f"🏛️ <b>Фото зала</b> ({i+1}/{len(hall_photos)})",
                                        parse_mode="HTML"
                                    )
                                    photos_sent += 1
                            except Exception as doc_error:
                                logger.error(f"Не удалось отправить {photo_path} даже как документ: {doc_error}")
                    
                    logger.info(f"Фото {photo_path} отправлено успешно")
                except Exception as photo_error:
                    logger.error(f"Ошибка отправки фото {photo_path}: {photo_error}")
            else:
                logger.warning(f"Файл {photo_path} не найден")
        
        # Если не удалось отправить ни одного фото
        if photos_sent == 0:
            await safe_send_message(
                bot,
                user_id,
                "🏛️ К сожалению, не удалось загрузить фотографии зала. Приходите к нам и увидите всё своими глазами! 😊",
                parse_mode="HTML"
            )
        
        # Отправляем сообщение с кнопкой назад
        text = "🏛️ Вот наш просторный и уютный зал! Здесь проходят все наши мероприятия и банкеты."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📅 Забронировать столик", callback_data="booking")],
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Отправлены фото зала пользователю {user_id} (отправлено: {photos_sent})")
    except Exception as e:
        logger.error(f"Ошибка отправки фото зала пользователю {user_id}: {e}")

async def show_bar_photos(user_id: int, bot):
    """Показать фотографии бара"""
    try:
        # Отправляем фото бара
        bar_photos = ['rest_photos/bar_1.jpg', 'rest_photos/bar_2.jpg']
        
        for i, photo_path in enumerate(bar_photos):
            if os.path.exists(photo_path):
                with open(photo_path, 'rb') as photo:
                    caption = f"🍸 <b>Наш стильный бар</b> ({i+1}/{len(bar_photos)})" if i == 0 else None
                    await bot.send_photo(
                        user_id,
                        BufferedInputFile(photo.read(), filename=f"bar_{i+1}.jpg"),
                        caption=caption,
                        parse_mode="HTML"
                    )
        
        # Отправляем сообщение с кнопкой назад
        text = "🍸 Вот наш стильный бар! Здесь вы можете насладиться широким выбором напитков и коктейлей."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🍽️ Открыть меню ресторана", callback_data="menu_food")],
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Отправлены фото бара пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки фото бара пользователю {user_id}: {e}")

async def show_kassa_photos(user_id: int, bot):
    """Показать фотографии кассы"""
    try:
        # Отправляем фото кассы
        kassa_photos = ['rest_photos/kassa1.jpg', 'rest_photos/kassa2.jpg']
        photos_sent = 0
        
        for i, photo_path in enumerate(kassa_photos):
            if os.path.exists(photo_path):
                try:
                    # Проверяем размер файла
                    file_size = os.path.getsize(photo_path)
                    logger.info(f"Отправляем фото {photo_path}, размер: {file_size / (1024*1024):.1f}MB")
                    
                    if file_size > 10 * 1024 * 1024:  # 10MB limit
                        logger.warning(f"Файл {photo_path} слишком большой ({file_size / (1024*1024):.1f}MB), отправляем как документ")
                        with open(photo_path, 'rb') as photo:
                            await bot.send_document(
                                user_id,
                                BufferedInputFile(photo.read(), filename=f"kassa_{i+1}.jpg"),
                                caption=f"💳 <b>Наша касса</b> ({i+1}/{len(kassa_photos)})" if i == 0 else f"💳 <b>Фото кассы</b> ({i+1}/{len(kassa_photos)})",
                                parse_mode="HTML"
                            )
                            photos_sent += 1
                    else:
                        try:
                            with open(photo_path, 'rb') as photo:
                                caption = f"💳 <b>Наша касса</b> ({i+1}/{len(kassa_photos)})" if i == 0 else None
                                await bot.send_photo(
                                    user_id,
                                    BufferedInputFile(photo.read(), filename=f"kassa_{i+1}.jpg"),
                                    caption=caption,
                                    parse_mode="HTML"
                                )
                                photos_sent += 1
                        except Exception as photo_send_error:
                            logger.warning(f"Не удалось отправить {photo_path} как фото ({photo_send_error}), отправляем как документ")
                            try:
                                with open(photo_path, 'rb') as photo:
                                    await bot.send_document(
                                        user_id,
                                        BufferedInputFile(photo.read(), filename=f"kassa_{i+1}.jpg"),
                                        caption=f"💳 <b>Наша касса</b> ({i+1}/{len(kassa_photos)})" if i == 0 else f"💳 <b>Фото кассы</b> ({i+1}/{len(kassa_photos)})",
                                        parse_mode="HTML"
                                    )
                                    photos_sent += 1
                            except Exception as doc_error:
                                logger.error(f"Не удалось отправить {photo_path} даже как документ: {doc_error}")
                    
                    logger.info(f"Фото {photo_path} отправлено успешно")
                except Exception as photo_error:
                    logger.error(f"Ошибка отправки фото {photo_path}: {photo_error}")
            else:
                logger.warning(f"Файл {photo_path} не найден")
        
        # Если не удалось отправить ни одного фото
        if photos_sent == 0:
            await safe_send_message(
                bot,
                user_id,
                "💳 К сожалению, не удалось загрузить фотографии кассы. Приходите к нам и увидите всё своими глазами! 😊",
                parse_mode="HTML"
            )
        
        # Отправляем сообщение с кнопкой назад
        text = "💳 Вот наша касса! Здесь вы можете оплатить заказ наличными или картой."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🍽️ Посмотреть меню", callback_data="menu_food")],
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Отправлены фото кассы пользователю {user_id} (отправлено: {photos_sent})")
    except Exception as e:
        logger.error(f"Ошибка отправки фото кассы пользователю {user_id}: {e}")

async def show_wc_photos(user_id: int, bot):
    """Показать фотографии туалета"""
    try:
        # Отправляем фото туалета
        wc_photos = ['rest_photos/wc1.jpg', 'rest_photos/wc2.jpg']
        photos_sent = 0
        
        for i, photo_path in enumerate(wc_photos):
            if os.path.exists(photo_path):
                try:
                    # Проверяем размер файла
                    file_size = os.path.getsize(photo_path)
                    logger.info(f"Отправляем фото {photo_path}, размер: {file_size / (1024*1024):.1f}MB")
                    
                    if file_size > 10 * 1024 * 1024:  # 10MB limit
                        logger.warning(f"Файл {photo_path} слишком большой ({file_size / (1024*1024):.1f}MB), отправляем как документ")
                        with open(photo_path, 'rb') as photo:
                            await bot.send_document(
                                user_id,
                                BufferedInputFile(photo.read(), filename=f"wc_{i+1}.jpg"),
                                caption=f"🚻 <b>Наш туалет</b> ({i+1}/{len(wc_photos)})" if i == 0 else f"🚻 <b>Фото туалета</b> ({i+1}/{len(wc_photos)})",
                                parse_mode="HTML"
                            )
                            photos_sent += 1
                    else:
                        try:
                            with open(photo_path, 'rb') as photo:
                                caption = f"🚻 <b>Наш туалет</b> ({i+1}/{len(wc_photos)})" if i == 0 else None
                                await bot.send_photo(
                                    user_id,
                                    BufferedInputFile(photo.read(), filename=f"wc_{i+1}.jpg"),
                                    caption=caption,
                                    parse_mode="HTML"
                                )
                                photos_sent += 1
                        except Exception as photo_send_error:
                            logger.warning(f"Не удалось отправить {photo_path} как фото ({photo_send_error}), отправляем как документ")
                            try:
                                with open(photo_path, 'rb') as photo:
                                    await bot.send_document(
                                        user_id,
                                        BufferedInputFile(photo.read(), filename=f"wc_{i+1}.jpg"),
                                        caption=f"🚻 <b>Наш туалет</b> ({i+1}/{len(wc_photos)})" if i == 0 else f"🚻 <b>Фото туалета</b> ({i+1}/{len(wc_photos)})",
                                        parse_mode="HTML"
                                    )
                                    photos_sent += 1
                            except Exception as doc_error:
                                logger.error(f"Не удалось отправить {photo_path} даже как документ: {doc_error}")
                    
                    logger.info(f"Фото {photo_path} отправлено успешно")
                except Exception as photo_error:
                    logger.error(f"Ошибка отправки фото {photo_path}: {photo_error}")
            else:
                logger.warning(f"Файл {photo_path} не найден")
        
        # Если не удалось отправить ни одного фото
        if photos_sent == 0:
            await safe_send_message(
                bot,
                user_id,
                "🚻 К сожалению, не удалось загрузить фотографии туалета. Приходите к нам и увидите всё своими глазами! 😊",
                parse_mode="HTML"
            )
        
        # Отправляем сообщение с кнопкой назад
        text = "🚻 Вот наш туалет! Чистый и уютный для комфорта наших гостей."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Отправлены фото туалета пользователю {user_id} (отправлено: {photos_sent})")
    except Exception as e:
        logger.error(f"Ошибка отправки фото туалета пользователю {user_id}: {e}")

async def show_restaurant_menu(user_id: int, bot):
    """Показать меню ресторана с проверкой возраста"""
    try:
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
            
            await safe_send_message(
                bot,
                user_id,
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        
        # Пользователь уже подтвердил возраст - показываем меню
        text = """🍽️ <b>Меню ресторана</b>

📱 <b>Электронное меню</b> — интерактивное меню с алкогольными напитками (требуется подтверждение возраста 18+)

📋 <b>PDF меню</b> — полное меню с барной картой для скачивания

🎉 <b>Банкетное меню</b> — специальные предложения для мероприятий

Выберите удобный для вас вариант:"""
        
        keyboard = keyboards.food_menu()
        
        await safe_send_message(
            bot,
            user_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Показано меню ресторана пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка показа меню ресторана пользователю {user_id}: {e}")



# ===== ТЕКСТОВЫЙ ОБРАБОТЧИК =====

@router.message(F.text, StateFilter(None))
async def handle_text_messages(message: types.Message, state: FSMContext):
    """Общий обработчик текстовых сообщений — ТОЛЬКО если нет активного состояния"""
    user = message.from_user
    text = message.text.strip().lower()

    logger.info(f"🔍 НАЧАЛО ОБРАБОТКИ СООБЩЕНИЯ: '{message.text}' от пользователя {user.id}")

    if text.startswith('/'):
        return

    # Код пересылки админ-чата перенесен в начало функции

    # Проверяем и сбрасываем лимит AI генераций при изменении баланса бонусов
    from ai_assistant import check_and_reset_ai_limit
    await check_and_reset_ai_limit(user.id)



    # Проверяем статус чата - если на паузе, сохраняем сообщение в миниапп и игнорируем
    try:
        chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
        chat_info = database.get_chat_by_id(chat_id)
        if chat_info and chat_info.get('chat_status') == 'paused':
            # Сохраняем сообщение в миниапп
            database.save_chat_message(chat_id, 'user', message.text)
            logger.info(f"Сообщение пользователя {user.id} сохранено в миниапп (чат на паузе): {message.text[:50]}...")

            # Отправляем уведомление пользователю, что диалог на паузе
            await safe_send_message(message.bot, user.id,
                                   "🤖 <b>Диалог переведен в ручной режим</b>\n\n"
                                   "Ваши сообщения будут обрабатываться администратором. "
                                   "Пожалуйста, подождите ответа оператора.",
                                   parse_mode="HTML")
            return
    except Exception as e:
        logger.error(f"Ошибка проверки статуса чата для {user.id}: {e}")

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

    # Приветствия (только если не в режиме админ-чата)
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

    user_id = message.from_user.id

    # Проверяем на сообщение с конкретными параметрами бронирования
    booking_details = parse_booking_message(message.text)
    if booking_details:
        logger.info(f"Обнаружен запрос бронирования с параметрами: {message.text}")
        await process_direct_booking_request(user_id, message.bot, booking_details, state)

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

        # Проверяем на показ банкетных опций
        if result.get('show_banquet_options'):
            from aiogram import types
            from config import ADMIN_CHAT_ID
            
            # Клавиатура для банкета
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✍️ Написать администратору", callback_data="chat_operator")],
                [types.InlineKeyboardButton(text="📋 Посмотреть банкетное меню (XLS)", callback_data="show_banquet_menu_xls")]
            ])
            
            await safe_send_message(message.bot, user.id, result['text'], reply_markup=keyboard, parse_mode="HTML")
            
            # Сохраняем в чат
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', f"Ответ про банкет: {result['text']}")
            except Exception as e:
                logger.error(f"Ошибка сохранения в миниапп: {e}")
                
            return

        # Проверяем на показ категории (краткий список)
        if result.get('show_category_brief'):
            category_name = result.get('show_category_brief')
            logger.info(f"Показываем краткий список категории: {category_name} для пользователя {user_id}")
            from category_handler import handle_show_category_brief
            await handle_show_category_brief(category_name, user_id, message.bot)

            # Сохраняем в чат
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', f'Показал краткий список категории: {category_name}')
            except Exception as e:
                logger.error(f"Ошибка сохранения в миниапп: {e}")

            return

        # Проверяем на показ категории (полный список)
        if result.get('show_category'):
            category_name = result.get('show_category')
            logger.info(f"Показываем категорию: {category_name} для пользователя {user_id}")
            from category_handler import handle_show_category
            await handle_show_category(category_name, user_id, message.bot)

            # Сохраняем в чат
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', f'Показал категорию: {category_name}')
            except Exception as e:
                logger.error(f"Ошибка сохранения в миниапп: {e}")

            return

        # Проверяем на показ отзывов
        if result.get('show_reviews'):
            await show_reviews_handler(user_id, message.bot)
            return

        # Проверяем на показ приложений
        if result.get('show_apps'):
            # Показываем текст ИИ + кнопки приложения
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🍎 App Store", url=config.APP_IOS)],
                [types.InlineKeyboardButton(text="🤖 Google Play", url=config.APP_ANDROID)],
                [types.InlineKeyboardButton(text="🟦 RuStore", url=config.APP_RUSTORE)]
            ])
            
            await safe_send_message(message.bot, user.id, result['text'], 
                                   reply_markup=keyboard, parse_mode="HTML")
            return

        # Проверяем на показ фото зала
        if result.get('show_hall_photos'):
            await show_hall_photos(user.id, message.bot)
            return

        # Проверяем на показ фото бара
        if result.get('show_bar_photos'):
            await show_bar_photos(user.id, message.bot)
            return

        # Проверяем на показ фото кассы
        if result.get('show_kassa_photos'):
            await show_kassa_photos(user.id, message.bot)
            return

        # Проверяем на показ фото туалета
        if result.get('show_wc_photos'):
            await show_wc_photos(user.id, message.bot)
            return

        # Проверяем на показ меню ресторана
        if result.get('show_restaurant_menu'):
            logger.info(f"Обрабатываем show_restaurant_menu для пользователя {user_id}")
            # Сначала отправляем ответ AI
            await safe_send_message(message.bot, user_id, result['text'])
            # Сохраняем ответ бота
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', result['text'])
            except Exception as e:
                logger.error(f"Ошибка сохранения ответа бота: {e}")
            # Затем показываем меню ресторана
            await show_restaurant_menu(user.id, message.bot)
            return

        # Проверяем на парсинг бронирования
        if result.get('parse_booking'):
            await safe_send_message(message.bot, user_id, result['text'])
            # Сохраняем ответ бота
            try:
                chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                database.save_chat_message(chat_id, 'bot', result['text'])
            except Exception as e:
                logger.error(f"Ошибка сохранения ответа бота: {e}")
            
            # Парсим детали бронирования из исходного сообщения пользователя
            booking_details = parse_booking_message(message.text)
            if booking_details:
                # Обрабатываем прямое бронирование
                await process_direct_booking_request(user_id, message.bot, booking_details, state)
            else:
                # Если не удалось распарсить, показываем меню бронирования
                await show_booking_options(user_id, message.bot)
            return



        if result['type'] == 'text':
            logger.info(f"Обрабатываем result['type'] == 'text' для пользователя {user_id}")

            # Проверяем на маркер вызова человека - должен работать НЕ в режиме админ-чата
            logger.info(f"Проверка CALL_HUMAN: call_human={result.get('call_human', False)}, is_operator_chat={is_operator_chat(user.id)}")
            if result.get('call_human', False) and not is_operator_chat(user.id):
                logger.info(f"Маркер CALL_HUMAN обнаружен для пользователя {user.id}")
                logger.info("Создаю кнопки для CALL_HUMAN")
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="💬 Написать оператору", callback_data="chat_operator")],
                    [types.InlineKeyboardButton(text="📞 Позвонить", callback_data="call_us")],
                    [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
                ])
                await safe_send_message(message.bot, user.id, result['text'], reply_markup=keyboard)
                try:
                    chat_id = database.get_or_create_chat(user.id, user.full_name or f'User {user.id}')
                    database.save_chat_message(chat_id, 'bot', result['text'])
                except Exception as e:
                    logger.error(f"Ошибка сохранения в миниапп: {e}")
                return

            # Проверяем нужны ли кнопки с приложениями
            if result.get('show_booking_options', False):
                # Показываем меню бронирования напрямую
                await show_booking_options(user.id, message.bot)
                return
            elif result.get('show_private_event_registration', False):
                # Показываем опции частных мероприятий
                await show_private_event_options_menu(user.id, message.bot)
                return
            elif result.get('show_event_registration', False):
                # Показываем меню регистрации на мероприятия
                await show_event_registration_menu(user.id, message.bot)
                return
            elif result.get('show_delivery_apps', False):
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🚚 Мини-приложение", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))],
                    [types.InlineKeyboardButton(text="🍎 App Store", url=config.APP_IOS)],
                    [types.InlineKeyboardButton(text="🤖 Google Play", url=config.APP_ANDROID)],
                    [types.InlineKeyboardButton(text="🟦 RuStore", url=config.APP_RUSTORE)]
                ])
                await safe_send_message(message.bot, user.id, result['text'], reply_markup=keyboard, parse_mode="HTML")
            elif result.get('show_category'):
                # Показываем категорию блюд
                category_name = result.get('show_category')
                logger.info(f"Показываем категорию: {category_name}")

                # Сначала отправляем текст с вопросом
                await safe_send_message(message.bot, user.id, result['text'], parse_mode="HTML")

                # Затем показываем категорию
                from category_handler import handle_show_category
                await handle_show_category(category_name, user.id, message.bot)
                return
            elif result.get('show_delivery_button', False):
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))]
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
                if result.get('photo_path'):
                    from aiogram.types import FSInputFile
                    photo = FSInputFile(result['photo_path'])
                    await message.answer_photo(photo, caption=result['text'], reply_markup=keyboard, parse_mode="HTML")
                else:
                    await message.answer_photo(result['photo_url'], caption=result['text'], reply_markup=keyboard, parse_mode="HTML")
            elif result.get('show_delivery_button', False):
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="🚚 Заказать доставку", web_app=types.WebAppInfo(url="https://strdr1.github.io/mashkov-telegram-app/"))]
                ])
                if result.get('photo_path'):
                    from aiogram.types import FSInputFile
                    photo = FSInputFile(result['photo_path'])
                    await message.answer_photo(photo, caption=result['text'], reply_markup=keyboard, parse_mode="HTML")
                else:
                    await message.answer_photo(result['photo_url'], caption=result['text'], reply_markup=keyboard, parse_mode="HTML")
            else:
                if result.get('photo_path'):
                    from aiogram.types import FSInputFile
                    photo = FSInputFile(result['photo_path'])
                    await message.answer_photo(photo, caption=result['text'], parse_mode="HTML")
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
        logger.error(f"Тип ошибки: {type(e)}")
        logger.error(f"Сообщение пользователя: {message.text}")
        import traceback
        logger.error(f"Полный traceback: {traceback.format_exc()}")
        
        text_response = """🤖 <b>Извините, произошла техническая ошибка</b>

Попробуйте переформулировать вопрос или используйте кнопки меню ниже."""
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
    # 🔴 БЛОКИРУЮЩАЯ ПРОВЕРКА: Если пользователь в режиме админ-чата, игнорируем ВСЕ действия
    if is_operator_chat(callback.from_user.id):
        logger.info(f"🚫 ПОЛЬЗОВАТЕЛЬ {callback.from_user.id} В РЕЖИМЕ АДМИН-ЧАТА - ИГНОРИРУЕМ CALLBACK")
        return

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
    guests_match = re.search(r'(\d+)\s*(человек|чел|гост|гостя|гостей)', text)
    if not guests_match:
        # Дополнительный поиск для "столик на X"
        guests_match = re.search(r'столик\s+на\s+(\d+)', text)
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

    # Регулярное выражение для времени (поддерживает :, ., пробел)
    time_match = re.search(r'(\d{1,2})[:\.\s](\d{2})', text)
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

    # Проверяем количество гостей - если больше 4, предлагаем связаться с оператором
    if booking_details['guests'] > 4:
        text = (
            f"👥 <b>Бронирование на {booking_details['guests']} человек</b>\n\n"
            f"📅 Дата: {booking_details['date_str']}\n"
            f"🕐 Время: {booking_details['time_str']}\n\n"
            f"❌ <b>Автоматическое бронирование недоступно</b>\n\n"
            f"Бронь стола доступна в автоматическом режиме до 4 человек.\n"
            f"Для компании от 5 человек свяжитесь с оператором.\n\n"
            f"💡 <b>Варианты решения:</b>\n"
            f"• 📞 Позвонить нам для бронирования\n"
            f"• 💬 Написать оператору в чате\n"
            f"• 🔄 Сделать несколько броней на 2-4 человека"
        )
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📞 Позвонить", callback_data="call_us")],
            [types.InlineKeyboardButton(text="💬 Написать оператору", callback_data="chat_operator")],
            [types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_main")]
        ])
        
        await safe_send_message(bot, user_id, text, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
        return

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
