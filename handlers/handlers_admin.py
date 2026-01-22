"""
handlers_admin.py
Обработчики админ-функций
"""

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
import keyboards
from keyboards import (
    admin_menu,
    newsletter_menu,
    reviews_admin_menu,
    faq_admin_menu,
    settings_menu,
    promocodes_admin_menu,
    contact_menu,
    category_selection_keyboard,  # ← Добавляем эту функцию
    dish_selection_keyboard       # ← И эту функцию
)
import database
import services
import config
import asyncio
import cache_manager
import logging
import os
import shutil
from datetime import datetime, timedelta
from typing import Optional
import aiohttp
from aiogram.exceptions import TelegramNetworkError
import re
import json
# Импортируем утилиты и состояния
from .utils import (
    safe_send_message,
    update_message,
    is_admin_fast,
    last_message_ids,
    user_registration_cache,
    admin_cache,
    clear_user_cache,
    handler_timeout
)
from .utils import clear_operator_chat, safe_delete_message

# Импортируем состояния из других модулей
from .handlers_booking import BookingStates

logger = logging.getLogger(__name__)

router = Router()

# Константы для путей к файлам
FILES_DIR = "files/menu"  
PDF_MENU_PATH = os.path.join(FILES_DIR, "Menu.pdf")
BANQUET_MENU_PATH = os.path.join(FILES_DIR, "MenuBanket.xlsx")

# Создаем директорию, если её нет
os.makedirs(FILES_DIR, exist_ok=True)

# Состояния для админки
class AdminStates(StatesGroup):
    waiting_password = State()
    waiting_newsletter_text = State()
    waiting_newsletter_photo = State()
    waiting_pdf_menu = State()  # Для загрузки PDF меню
    waiting_banquet_menu = State()  # Для загрузки банкетного меню
    waiting_reply = State()  # Для ответа пользователю через кнопку
    waiting_admin_id = State()  # Для добавления/удаления админа
    waiting_prompt_edit = State()  # Для редактирования промптов
    waiting_prompt_upload = State()  # Для загрузки промптов из файлов

# ===== УПРАВЛЕНИЕ МЕНЮ ФАЙЛАМИ =====

@router.callback_query(F.data == "admin_menu_files")
async def admin_menu_files_callback(callback: types.CallbackQuery):
    """Управление файлами меню"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Проверяем существование файлов
    pdf_exists = os.path.exists(PDF_MENU_PATH)
    banquet_exists = os.path.exists(BANQUET_MENU_PATH)
    
    text = """📋 <b>Управление файлами меню</b>

Здесь вы можете загрузить или обновить файлы меню для пользователей:

<b>📄 PDF меню</b>
<i>Текущий файл:</i> """
    text += f"<code>{os.path.basename(PDF_MENU_PATH)}</code> ({os.path.getsize(PDF_MENU_PATH) // 1024} KB)" if pdf_exists else "❌ Файл не загружен"
    
    text += "\n\n<b>📊 Банкетное меню (XLSX)</b>\n<i>Текущий файл:</i> "
    text += f"<code>{os.path.basename(BANQUET_MENU_PATH)}</code> ({os.path.getsize(BANQUET_MENU_PATH) // 1024} KB)" if banquet_exists else "❌ Файл не загружен"
    
    text += "\n\n💡 <i>При загрузке нового файла старый будет заменен. Поддерживаются PDF и XLSX файлы.</i>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📄 ЗАГРУЗИТЬ PDF МЕНЮ", callback_data="admin_upload_pdf")],
        [types.InlineKeyboardButton(text="📊 ЗАГРУЗИТЬ БАНКЕТНОЕ МЕНЮ", callback_data="admin_upload_banquet")],
        [types.InlineKeyboardButton(text="📤 СКАЧАТЬ ТЕКУЩИЕ ФАЙЛЫ", callback_data="admin_download_menus")],
        [types.InlineKeyboardButton(text="⬅️ НАЗАД В АДМИНКУ", callback_data="admin_back")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
@router.callback_query(F.data == "manage_table_photos")
async def manage_table_photos_callback(callback: types.CallbackQuery):
    """Управление фото столов для генерации изображений персонажей"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Проверяем какие фото столов есть
    table_photos = {
        'files/tables_holl.jpg': 'Основной стол (одиночный)',
        'files/table_for_1.jpg': 'Стол для одного',
        'files/big_table.jpg': 'Большой стол (групповой)'
    }

    text = """🖼️ <b>Управление фото столов</b>

Здесь вы можете заменить стандартные фото столов на свои собственные.
Эти фото используются для генерации изображений персонажей в ресторане.

<b>Текущие фото столов:</b>\n"""

    keyboard_buttons = []

    for file_path, description in table_photos.items():
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path) // 1024
            text += f"✅ <code>{os.path.basename(file_path)}</code> - {description} ({file_size} KB)\n"
            keyboard_buttons.append([
                types.InlineKeyboardButton(
                    text=f"🔄 Заменить {os.path.basename(file_path)}",
                    callback_data=f"replace_table_{os.path.basename(file_path).replace('.jpg', '')}"
                )
            ])
        else:
            text += f"❌ <code>{os.path.basename(file_path)}</code> - {description} (отсутствует)\n"
            keyboard_buttons.append([
                types.InlineKeyboardButton(
                    text=f"📤 Добавить {os.path.basename(file_path)}",
                    callback_data=f"replace_table_{os.path.basename(file_path).replace('.jpg', '')}"
                )
            ])

    text += "\n<b>Рекомендации:</b>\n"
    text += "• Формат: JPG\n"
    text += "• Размер: до 5 MB\n"
    text += "• Качество: высокое (ресторанный интерьер)\n"
    text += "• Освещение: теплое, уютное"

    keyboard_buttons.append([
        types.InlineKeyboardButton(text="⬅️ Назад к промптам", callback_data="admin_system_prompts")
    ])

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data.startswith("replace_table_"))
async def replace_table_photo_callback(callback: types.CallbackQuery, state: FSMContext):
    """Замена фото стола"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    table_name = callback.data.replace("replace_table_", "")
    filename = f"{table_name}.jpg"

    await state.update_data(replacing_table=filename)

    descriptions = {
        'tables_holl': 'основной стол (используется чаще всего)',
        'table_for_1': 'стол для одного человека',
        'big_table': 'большой стол для групп/команд'
    }

    description = descriptions.get(table_name, filename)

    text = f"""🖼️ <b>Замена фото стола: {filename}</b>

<b>Описание:</b> {description}

Пожалуйста, отправьте новое фото стола в формате JPG.

<b>Требования:</b>
• Формат: JPG (.jpg)
• Максимальный размер: 5 MB
• Рекомендуемое разрешение: 1024x1024 или выше
• Качественное фото ресторанного интерьера

<i>Старое фото будет заменено новым</i>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_table_photos")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

    await state.set_state(AdminStates.waiting_pdf_menu)  # Используем существующее состояние

@router.message(AdminStates.waiting_pdf_menu, F.photo)
async def handle_table_photo_upload(message: Message, state: FSMContext):
    """Обработка загрузки фото стола"""
    if not is_admin_fast(message.from_user.id):
        return

    data = await state.get_data()
    filename = data.get('replacing_table')

    if not filename:
        await state.clear()
        return

    photo = message.photo[-1]  # Берем самое качественное фото

    # Проверяем размер
    if photo.file_size > 5 * 1024 * 1024:  # 5 MB
        await update_message(message.from_user.id,
                           "❌ <b>Фото слишком большое!</b>\n\nМаксимальный размер: 5 MB.",
                           parse_mode="HTML",
                           bot=message.bot)
        return

    try:
        # Скачиваем фото
        file = await message.bot.get_file(photo.file_id)
        file_path = file.file_path

        downloaded_file = await message.bot.download_file(file_path)
        photo_data = downloaded_file.read()
        downloaded_file.close()

        # Создаем директорию если не существует
        os.makedirs('files', exist_ok=True)

        # Сохраняем фото, заменяя старое
        filepath = f'files/{filename}'
        with open(filepath, 'wb') as f:
            f.write(photo_data)

        file_size_kb = len(photo_data) // 1024

        text = f"""✅ <b>Фото стола успешно заменено!</b>

<b>Файл:</b> <code>{filename}</code>
<b>Размер:</b> {file_size_kb} KB
<b>Путь:</b> {filepath}

<i>Теперь это фото будет использоваться для генерации изображений персонажей</i>"""

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🖼️ Управление фото", callback_data="manage_table_photos")],
            [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
        ])

        await update_message(message.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)

        await state.clear()

        # Логируем действие
        database.log_action(message.from_user.id, "replace_table_photo",
                          f"filename:{filename}, size:{file_size_kb}KB")

    except Exception as e:
        logger.error(f"Ошибка загрузки фото стола: {e}")
        await update_message(message.from_user.id,
                           "❌ <b>Ошибка загрузки фото!</b>\n\nПопробуйте еще раз.",
                           parse_mode="HTML",
                           bot=message.bot)

@router.callback_query(F.data == "admin_upload_pdf")
async def admin_upload_pdf_callback(callback: types.CallbackQuery, state: FSMContext):
    """Загрузка PDF меню"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = """📄 <b>Загрузка PDF меню</b>

Пожалуйста, отправьте PDF файл с меню ресторана.

<b>Требования:</b>
• Формат: PDF (.pdf)
• Максимальный размер: 20 MB
• Рекомендуется: меню с барной картой

<i>При загрузке нового файла старый будет заменен.</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="admin_menu_files")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(AdminStates.waiting_pdf_menu)

@router.callback_query(F.data == "admin_upload_banquet")
async def admin_upload_banquet_callback(callback: types.CallbackQuery, state: FSMContext):
    """Загрузка банкетного меню"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = """📊 <b>Загрузка банкетного меню</b>

Пожалуйста, отправьте Excel файл (XLSX) с банкетным меню.

<b>Требования:</b>
• Формат: Excel (.xlsx)
• Максимальный размер: 10 MB
• Рекомендуется: таблица с ценами и описаниями блюд

<i>При загрузке нового файла старый будет заменен.</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="admin_menu_files")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(AdminStates.waiting_banquet_menu)

@router.callback_query(F.data == "admin_download_menus")
async def admin_download_menus_callback(callback: types.CallbackQuery):
    """Скачивание текущих файлов меню"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Проверяем существование файлов
    pdf_exists = os.path.exists(PDF_MENU_PATH)
    banquet_exists = os.path.exists(BANQUET_MENU_PATH)
    
    if not pdf_exists and not banquet_exists:
        text = "❌ <b>Нет доступных файлов для скачивания</b>\n\nФайлы меню еще не загружены."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="admin_menu_files")]
        ])
    else:
        text = "📥 <b>Скачать файлы меню</b>\n\nВыберите файл для скачивания:"
        
        keyboard_buttons = []
        
        if pdf_exists:
            file_size = os.path.getsize(PDF_MENU_PATH) // 1024
            keyboard_buttons.append([
                types.InlineKeyboardButton(
                    text=f"📄 Скачать PDF меню ({file_size} KB)", 
                    callback_data="download_pdf"
                )
            ])
        
        if banquet_exists:
            file_size = os.path.getsize(BANQUET_MENU_PATH) // 1024
            keyboard_buttons.append([
                types.InlineKeyboardButton(
                    text=f"📊 Скачать банкетное меню ({file_size} KB)", 
                    callback_data="download_banquet"
                )
            ])
        
        keyboard_buttons.append([
            types.InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="admin_menu_files")
        ])
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "download_pdf")
async def download_pdf_callback(callback: types.CallbackQuery):
    """Отправка PDF файла пользователю"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    if not os.path.exists(PDF_MENU_PATH):
        await callback.answer("❌ Файл не найден!", show_alert=True)
        return
    
    try:
        with open(PDF_MENU_PATH, 'rb') as file:
            await callback.bot.send_document(
                chat_id=callback.from_user.id,
                document=types.BufferedInputFile(
                    file.read(),
                    filename=os.path.basename(PDF_MENU_PATH)
                ),
                caption=f"📄 {os.path.basename(PDF_MENU_PATH)}"
            )
        
        await callback.answer("✅ Файл отправлен!", show_alert=False)
    except Exception as e:
        logger.error(f"Ошибка отправки PDF файла: {e}")
        await callback.answer("❌ Ошибка отправки файла!", show_alert=True)

@router.callback_query(F.data == "download_banquet")
async def download_banquet_callback(callback: types.CallbackQuery):
    """Отправка банкетного меню пользователю"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    if not os.path.exists(BANQUET_MENU_PATH):
        await callback.answer("❌ Файл не найден!", show_alert=True)
        return
    
    try:
        with open(BANQUET_MENU_PATH, 'rb') as file:
            await callback.bot.send_document(
                chat_id=callback.from_user.id,
                document=types.BufferedInputFile(
                    file.read(),
                    filename=os.path.basename(BANQUET_MENU_PATH)
                ),
                caption=f"📊 {os.path.basename(BANQUET_MENU_PATH)}"
            )
        
        await callback.answer("✅ Файл отправлен!", show_alert=False)
    except Exception as e:
        logger.error(f"Ошибка отправки XLSX файла: {e}")
        await callback.answer("❌ Ошибка отправки файла!", show_alert=True)

@router.message(AdminStates.waiting_pdf_menu, F.document)
async def handle_pdf_menu_upload(message: Message, state: FSMContext):
    """Обработка загрузки PDF меню"""
    if not is_admin_fast(message.from_user.id):
        return
    
    document = message.document
    
    # Проверяем формат
    if not document.mime_type == 'application/pdf':
        await update_message(message.from_user.id,
                           "❌ <b>Неверный формат файла!</b>\n\nПожалуйста, отправьте PDF файл.",
                           parse_mode="HTML",
                           bot=message.bot)
        return
    
    # Проверяем размер
    if document.file_size > 20 * 1024 * 1024:  # 20 MB
        await update_message(message.from_user.id,
                           "❌ <b>Файл слишком большой!</b>\n\nМаксимальный размер: 20 MB.",
                           parse_mode="HTML",
                           bot=message.bot)
        return
    
    try:
        # Создаем директорию если не существует
        os.makedirs(FILES_DIR, exist_ok=True)
        
        await update_message(message.from_user.id,
                           "⏳ <b>Загружаем файл...</b>\n\nПожалуйста, подождите.",
                           parse_mode="HTML",
                           bot=message.bot)
        
        # Скачиваем файл
        file = await message.bot.get_file(document.file_id)
        file_path = file.file_path
        
        # Скачиваем файл
        downloaded_file = await message.bot.download_file(file_path)
        file_data = downloaded_file.read()
        
        # Закрываем поток
        downloaded_file.close()
        
        # Добавляем небольшую задержку для освобождения файлов
        await asyncio.sleep(0.5)
        
        # Пытаемся удалить старый файл несколько раз
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if os.path.exists(PDF_MENU_PATH):
                    os.remove(PDF_MENU_PATH)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                await asyncio.sleep(0.5)
        
        # Сохраняем новый файл
        with open(PDF_MENU_PATH, 'wb') as f:
            f.write(file_data)
        
        file_size_kb = document.file_size // 1024
        
        text = f"""✅ <b>PDF меню успешно загружено!</b>

<b>Информация о файле:</b>
📄 Название: {document.file_name}
📦 Размер: {file_size_kb} KB
📁 Тип: PDF

Файл сохранен как: Menu.pdf
Теперь доступен для пользователей."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📄 Загрузить другое меню", callback_data="admin_upload_pdf")],
            [types.InlineKeyboardButton(text="📋 Управление файлами", callback_data="admin_menu_files")],
            [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
        ])
        
        await update_message(message.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)
        
        await state.clear()
        
        # Логируем действие
        database.log_action(message.from_user.id, "upload_menu_pdf", 
                          f"filename:{document.file_name}, size:{file_size_kb}KB")
        
    except Exception as e:
        logger.error(f"Ошибка загрузки PDF: {e}")
        
        error_msg = str(e)
        if "Процесс не может получить доступ к файлу" in error_msg:
            error_text = """❌ <b>Файл занят другим процессом!</b>

Возможные причины:
1. Файл открыт в другой программе (например, Adobe Reader)
2. Бот все еще использует файл
3. Антивирус блокирует доступ

<b>Решение:</b>
• Закройте все программы, которые могут использовать файл Menu.pdf
• Подождите 30 секунд и попробуйте снова
• Перезагрузите бота если проблема persists"""
        else:
            error_text = f"❌ <b>Ошибка загрузки файла!</b>\n\n{error_msg[:100]}..."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="admin_upload_pdf")],
            [types.InlineKeyboardButton(text="📋 Управление файлами", callback_data="admin_menu_files")]
        ])
        
        await update_message(message.from_user.id, error_text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)

@router.message(AdminStates.waiting_banquet_menu, F.document)
async def handle_banquet_menu_upload(message: Message, state: FSMContext):
    """Обработка загрузки банкетного меню"""
    if not is_admin_fast(message.from_user.id):
        return
    
    document = message.document
    
    # Проверяем формат (Excel файлы)
    allowed_mime_types = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
        'application/vnd.ms-excel',  # .xls
    ]
    
    if document.mime_type not in allowed_mime_types and not document.file_name.endswith(('.xlsx', '.xls')):
        await update_message(message.from_user.id,
                           "❌ <b>Неверный формат файла!</b>\n\nПожалуйста, отправьте Excel файл (.xlsx или .xls).",
                           parse_mode="HTML",
                           bot=message.bot)
        return
    
    # Проверяем размер
    if document.file_size > 10 * 1024 * 1024:  # 10 MB
        await update_message(message.from_user.id,
                           "❌ <b>Файл слишком большой!</b>\n\nМаксимальный размер: 10 MB.",
                           parse_mode="HTML",
                           bot=message.bot)
        return
    
    try:
        # Создаем директорию если не существует
        os.makedirs(FILES_DIR, exist_ok=True)
        
        await update_message(message.from_user.id,
                           "⏳ <b>Загружаем файл...</b>\n\nПожалуйста, подождите.",
                           parse_mode="HTML",
                           bot=message.bot)
        
        # Скачиваем файл
        file = await message.bot.get_file(document.file_id)
        file_path = file.file_path
        
        # Скачиваем файл
        downloaded_file = await message.bot.download_file(file_path)
        file_data = downloaded_file.read()
        
        # Закрываем поток
        downloaded_file.close()
        
        # Добавляем небольшую задержку для освобождения файлов
        await asyncio.sleep(0.5)
        
        # Пытаемся удалить старый файл несколько раз
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if os.path.exists(BANQUET_MENU_PATH):
                    os.remove(BANQUET_MENU_PATH)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                await asyncio.sleep(0.5)
        
        # Сохраняем новый файл
        with open(BANQUET_MENU_PATH, 'wb') as f:
            f.write(file_data)
        
        file_size_kb = document.file_size // 1024
        
        text = f"""✅ <b>Банкетное меню успешно загружено!</b>

<b>Информация о файле:</b>
📊 Название: {document.file_name}
📦 Размер: {file_size_kb} KB
📁 Тип: Excel

Файл сохранен как: MenuBanket.xlsx
Теперь доступен для пользователей."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📊 Загрузить другое меню", callback_data="admin_upload_banquet")],
            [types.InlineKeyboardButton(text="📋 Управление файлами", callback_data="admin_menu_files")],
            [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
        ])
        
        await update_message(message.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)
        
        await state.clear()
        
        # Логируем действие
        database.log_action(message.from_user.id, "upload_menu_banquet", 
                          f"filename:{document.file_name}, size:{file_size_kb}KB")
        
    except Exception as e:
        logger.error(f"Ошибка загрузки банкетного меню: {e}")
        
        error_msg = str(e)
        if "Процесс не может получить доступ к файлу" in error_msg:
            error_text = """❌ <b>Файл занят другим процессом!</b>

Возможные причины:
1. Файл открыт в Microsoft Excel или другой программе
2. Бот все еще использует файл
3. Антивирус блокирует доступ

<b>Решение:</b>
• Закройте все программы, которые могут использовать файл MenuBanket.xlsx
• Подождите 30 секунд и попробуйте снова
• Перезагрузите бота если проблема persists"""
        else:
            error_text = f"❌ <b>Ошибка загрузки файла!</b>\n\n{error_msg[:100]}..."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="admin_upload_banquet")],
            [types.InlineKeyboardButton(text="📋 Управление файлами", callback_data="admin_menu_files")]
        ])
        
        await update_message(message.from_user.id, error_text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)

# ===== АДМИН КОМАНДЫ =====

async def show_admin_panel(user_id: int, bot, message_id: int = None):
    """Показать админ-панель с подтверждением доступа"""
    stats = database.get_stats()

    text = f"""✅ <b>Доступ к админке получен!</b>

🛠️ <b>Админ-панель ресторана</b>

📊 <b>Статистика за сегодня:</b>
👥 Всего пользователей: {stats['total_users']}
🔥 Активных сегодня: {stats['active_today']}
📅 Броней сегодня: {stats['bookings_today']}
🍽️ Заказов сегодня: {stats['orders_today']}

Выберите раздел для управления:"""

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboards.admin_menu(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования админ-панели: {e}")
            await update_message(user_id, text,
                                reply_markup=keyboards.admin_menu(),
                                parse_mode="HTML",
                                bot=bot)
    else:
        await update_message(user_id, text,
                            reply_markup=keyboards.admin_menu(),
                            parse_mode="HTML",
                            bot=bot)

@router.message(Command("admin_menu"))
async def admin_menu_command(message: types.Message):
    """Команда для быстрого доступа к админ-меню"""
    user = message.from_user

    if not is_admin_fast(user.id):
        await message.answer("❌ У вас нет доступа к админ-меню")
        return

    await show_admin_panel(user.id, message.bot)


    @router.message(Command("add_admin"))
    async def add_admin_command(message: types.Message):
        """Добавить администратора: /add_admin <user_id> (только для админов)"""
        if not is_admin_fast(message.from_user.id):
            await message.answer("❌ У вас нет доступа к этой команде.")
            return

        parts = (message.text or '').strip().split()
        if len(parts) < 2:
            await message.answer("Использование: /add_admin <user_id>")
            return

        try:
            target_id = int(parts[1])
        except ValueError:
            await message.answer("❌ Неверный ID. Укажите числовой user_id.")
            return

        try:
            ok = database.add_admin(target_id)
            if ok:
                database.clear_admin_cache(target_id)
                await message.answer(f"✅ Пользователь {target_id} добавлен в список администраторов.")
                try:
                    await safe_send_message(message.bot, target_id, "🔔 Вас добавили в администраторы бота. Используйте /admin для входа.")
                except Exception:
                    pass
            else:
                await message.answer("❌ Не удалось добавить администратора.")
        except Exception as e:
            logger.error(f"Ошибка add_admin_command: {e}")
            await message.answer("❌ Ошибка при добавлении администратора.")


    @router.message(Command("remove_admin"))
    async def remove_admin_command(message: types.Message):
        """Удалить администратора: /remove_admin <user_id> (только для админов)"""
        if not is_admin_fast(message.from_user.id):
            await message.answer("❌ У вас нет доступа к этой команде.")
            return

        parts = (message.text or '').strip().split()
        if len(parts) < 2:
            await message.answer("Использование: /remove_admin <user_id>")
            return

        try:
            target_id = int(parts[1])
        except ValueError:
            await message.answer("❌ Неверный ID. Укажите числовой user_id.")
            return

        try:
            ok = database.remove_admin(target_id)
            if ok:
                database.clear_admin_cache(target_id)
                await message.answer(f"✅ Пользователь {target_id} удалён из списка администраторов.")
                try:
                    await safe_send_message(message.bot, target_id, "ℹ️ Ваши права администратора отозваны.")
                except Exception:
                    pass
            else:
                await message.answer("❌ Не удалось удалить администратора.")
        except Exception as e:
            logger.error(f"Ошибка remove_admin_command: {e}")
            await message.answer("❌ Ошибка при удалении администратора.")

@router.message(AdminStates.waiting_password)
async def check_admin_password(message: types.Message, state: FSMContext):
    """Проверка пароля админа"""
    user_id = message.from_user.id
    entered_password = message.text.strip()

    if entered_password == config.ADMIN_PASSWORD:
        database.add_admin(user_id)
        admin_cache[user_id] = True

        # Удаляем сообщение с запросом пароля
        try:
            await message.delete()
        except Exception:
            pass

        # Отправляем новое сообщение с меню админки
        stats = database.get_stats()
        text = f"""✅ <b>Доступ к админке получен!</b>

🛠️ <b>Админ-панель ресторана</b>

📊 <b>Статистика за сегодня:</b>
👥 Всего пользователей: {stats['total_users']}
🔥 Активных сегодня: {stats['active_today']}
📅 Броней сегодня: {stats['bookings_today']}
🍽️ Заказов сегодня: {stats['orders_today']}

Выберите раздел для управления:"""

        await message.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=keyboards.admin_menu(),
            parse_mode="HTML"
        )

        await state.clear()
    else:
        await update_message(user_id,
                           "❌ <b>Неверный пароль!</b> Попробуйте еще раз:",
                           parse_mode="HTML",
                           bot=message.bot)

@router.callback_query(F.data == "admin_back")
async def admin_back_callback(callback: types.CallbackQuery, state: FSMContext):
    """Быстрый возврат в админку - сбрасывает состояния промптов"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Сбрасываем ВСЕ состояния промптов при выходе из меню
    await state.clear()

    await show_admin_panel(callback.from_user.id, callback.bot, callback.message.message_id)

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

# ===== РАССЫЛКИ =====

async def admin_newsletter_handler(user_id: int, bot):
    """Обработчик меню рассылок"""
    if not is_admin_fast(user_id):
        return
    
    pending_newsletters = database.get_pending_newsletters()
    
    text = "📢 <b>Управление рассылками</b>\n\n"
    
    if pending_newsletters:
        text += f"<b>Ожидающих рассылок:</b> {len(pending_newsletters)}\n"
        text += "<i>Последняя ожидающая рассылка:</i>\n"
        if pending_newsletters[0][1]:
            preview = pending_newsletters[0][1][:100] + "..." if len(pending_newsletters[0][1]) > 100 else pending_newsletters[0][1]
            text += f"📝 {preview}\n\n"
    else:
        text += "✅ <b>Нет ожидающих рассылок</b>\n\n"
    
    text += "Выберите действие:"
    
    await update_message(user_id, text,
                        reply_markup=keyboards.newsletter_menu(),
                        parse_mode="HTML",
                        bot=bot)

@router.callback_query(F.data == "admin_newsletter")
async def admin_newsletter_callback(callback: types.CallbackQuery, state: FSMContext):
    """Быстрое управление рассылками"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    await state.clear()  # Очищаем состояние на всякий случай
    await admin_newsletter_handler(callback.from_user.id, callback.bot)

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

@router.message(AdminStates.waiting_newsletter_text)
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
        [types.InlineKeyboardButton(text="🕐 Отправить немедленно", callback_data=f"send_now_{message_type}")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 1 час", callback_data=f"schedule_1h_{message_type}")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 3 часа", callback_data=f"schedule_3h_{message_type}")],
        [types.InlineKeyboardButton(text="📅 Запланировать на завтра", callback_data=f"schedule_tomorrow_{message_type}")],
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
        [types.InlineKeyboardButton(text="🕐 Отправить немедленно", callback_data="send_now_text")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 1 час", callback_data="schedule_1h_text")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 3 часа", callback_data="schedule_3h_text")],
        [types.InlineKeyboardButton(text="📅 Запланировать на завтра", callback_data="schedule_tomorrow_text")],
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
        [types.InlineKeyboardButton(text="🕐 Отправить немедленно", callback_data=f"send_now_{message_type}")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 1 час", callback_data=f"schedule_1h_{message_type}")],
        [types.InlineKeyboardButton(text="⏰ Отложить на 3 часа", callback_data=f"schedule_3h_{message_type}")],
        [types.InlineKeyboardButton(text="📅 Запланировать на завтра", callback_data=f"schedule_tomorrow_{message_type}")],
        [types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_text_newsletter")],
        [types.InlineKeyboardButton(text="🗑️ Отменить", callback_data="admin_newsletter")]
    ])
    
    await update_message(callback.from_user.id, preview_text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

# Обработчики кнопок времени рассылки
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
        schedule_type = callback_data.replace('send_now_', '')
    elif callback_data.startswith('schedule_1h_'):
        schedule_time = '1h'
        schedule_text = "через 1 час"
        schedule_type = callback_data.replace('schedule_1h_', '')
    elif callback_data.startswith('schedule_3h_'):
        schedule_time = '3h'
        schedule_text = "через 3 часа"
        schedule_type = callback_data.replace('schedule_3h_', '')
    elif callback_data.startswith('schedule_tomorrow_'):
        schedule_time = 'tomorrow'
        schedule_text = "завтра"
        schedule_type = callback_data.replace('schedule_tomorrow_', '')
    else:
        schedule_time = 'immediate'
        schedule_text = "немедленно"
        schedule_type = 'text'
    
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

# ===== УПРАВЛЕНИЕ ОТЗЫВАМИ =====

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

@router.callback_query(F.data == "admin_view_reviews")
async def admin_view_reviews_callback(callback: types.CallbackQuery):
    """Просмотр всех отзывов в админке"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    reviews = database.get_all_reviews()
    
    if not reviews:
        text = "⭐ <b>Все отзывы</b>\n\n❌ Отзывов пока нет в базе данных."
    else:
        text = f"⭐ <b>Все отзывы</b>\n\n<b>Всего отзывов:</b> {len(reviews)}\n\n<b>Самые свежие:</b>\n"
        
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

@router.message(BookingStates.editing_review)
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
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    text = """💣 <b>Удаление всех отзывов</b>

⚠️ <b>ВНИМАНИЕ!</b> Это действие удалит ВСЕ отзывы из базы данных!
Данное действие необратимо.

<b>Вы уверены, что хотите удалить все отзывы?</b>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Да, удалить все отзывы", callback_data="confirm_delete_all_reviews")],
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_reviews")]
    ])

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "confirm_delete_all_reviews")
async def confirm_delete_all_reviews_callback(callback: types.CallbackQuery):
    """Подтверждение удаления всех отзывов"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    try:
        # Удаляем все отзывы из базы данных
        database.execute_query("DELETE FROM reviews")
        
        # Очищаем кэш отзывов
        import cache_manager
        cache_keys_to_clear = [key for key in cache_manager.cache._cache.keys() if 'reviews' in key]
        for key in cache_keys_to_clear:
            cache_manager.cache.delete(key)
        
        text = """✅ <b>Все отзывы удалены</b>

Все отзывы были успешно удалены из базы данных.
Кэш также очищен."""

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад к управлению отзывами", callback_data="admin_reviews")]
        ])

        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка удаления всех отзывов: {e}")
        
        text = f"""❌ <b>Ошибка удаления отзывов</b>

Произошла ошибка при удалении отзывов:
<code>{str(e)}</code>"""

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад к управлению отзывами", callback_data="admin_reviews")]
        ])

        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

# ===== УПРАВЛЕНИЕ FAQ =====

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

@router.message(BookingStates.waiting_faq_question)
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

@router.message(BookingStates.waiting_faq_answer)
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

@router.message(BookingStates.editing_faq)
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

# ===== НАСТРОЙКИ БОТА =====

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

@router.message(BookingStates.editing_setting)
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
@router.message(F.text.startswith('/reply_'))
async def reply_command_handler(message: types.Message):
    """Обработчик команд вида /reply_{user_id}"""
    
    if not is_admin_fast(message.from_user.id):
        return
    
    try:
        text = message.text.strip()
        
        # Удаляем "/reply_" из начала
        if not text.startswith('/reply_'):
            return
        
        # Разделяем команду и текст
        parts = text.split(' ', 1)
        
        # Получаем user_id
        command_with_id = parts[0]  # /reply_515216260
        user_id_str = command_with_id.replace('/reply_', '')
        
        try:
            user_id = int(user_id_str)
        except ValueError:
            await message.answer("❌ Неверный формат ID. Используйте: /reply_число текст")
            return
        
        # Проверяем, есть ли текст
        if len(parts) < 2:
            await message.answer(f"❌ Нет текста сообщения. Используйте: /reply_{user_id} ваш_текст")
            return
        
        reply_text = parts[1]
        
        # Отправляем сообщение
        try:
            await message.bot.send_message(
                chat_id=user_id,
                text=f"💬 <b>Сообщение от администратора:</b>\n\n{reply_text}",
                parse_mode="HTML"
            )
            await message.answer(f"✅ Отправлено пользователю {user_id}")
            # Удаляем уведомления другим администраторам, если были
            try:
                from .utils import get_operator_notifications, delete_operator_notifications
                notifications = get_operator_notifications(user_id)
                if notifications:
                    for adm_id, msg_id in list(notifications.items()):
                        try:
                            # удаляем уведомление у всех админов
                            await safe_delete_message(message.bot, adm_id, msg_id)
                        except Exception:
                            pass
                    # чистим запись уведомлений
                    delete_operator_notifications(user_id)
            except Exception:
                pass

            # НЕ завершаем автоматически режим чата - пусть админ сам решает
            # try:
            #     from .utils import clear_operator_chat
            #     clear_operator_chat(user_id)
            # except Exception:
            #     pass
            
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ["blocked", "deactivated", "not found"]):
                await message.answer(f"❌ Не удалось отправить пользователю {user_id}")
            else:
                await message.answer(f"❌ Ошибка: {str(e)[:50]}")
                
    except Exception as e:
        logger.error(f"Ошибка обработки /reply: {e}")
        await message.answer("❌ Ошибка обработки команды")


@router.message(F.text.startswith('/stop_chat_'))
async def stop_chat_command_handler(message: types.Message):
    """Админ завершает режим чата для пользователя: /stop_chat_{user_id}"""
    if not is_admin_fast(message.from_user.id):
        return

    text = message.text.strip()
    if not text.startswith('/stop_chat_'):
        return

    user_id_str = text.replace('/stop_chat_', '')
    try:
        user_id = int(user_id_str)
    except ValueError:
        await message.answer("❌ Неверный формат ID. Используйте: /stop_chat_число")
        return

    try:
        # Выключаем режим чата и убираем уведомления/назначения
        try:
            from .utils import delete_operator_notifications, clear_assigned_operator
            delete_operator_notifications(user_id)
            clear_assigned_operator(user_id)
        except Exception:
            pass

        clear_operator_chat(user_id)

        # Оповещаем пользователя
        try:
            await safe_send_message(message.bot, user_id, "ℹ️ Оператор завершил чат. Вы снова в автоматическом режиме.")
        except Exception:
            pass

        await message.answer(f"✅ Режим чата для пользователя {user_id} завершён")
    except Exception as e:
        logger.error(f"Ошибка при завершении чата для {user_id}: {e}")
        await message.answer("❌ Ошибка при завершении чата")


@router.message(Command("stop_chat"))
async def stop_chat_simple_handler(message: types.Message):
    """Админ завершает режим чата: /stop_chat (в ответ на пересланное сообщение) или /stop_chat <user_id>"""
    if not is_admin_fast(message.from_user.id):
        return

    user_id = None

    # Если команда отправлена в ответ на пересланное сообщение — извлекаем оригинального отправителя
    if message.reply_to_message and getattr(message.reply_to_message, 'forward_from', None):
        try:
            user_id = message.reply_to_message.forward_from.id
        except Exception:
            user_id = None

    # Если передан аргумент — пытаемся разобрать его как ID
    if user_id is None:
        parts = (message.text or '').strip().split()
        if len(parts) > 1:
            try:
                user_id = int(parts[1])
            except ValueError:
                user_id = None

    if not user_id:
        await message.answer("Использование:\n/stop_chat (в ответ на пересланное сообщение)\nили\n/stop_chat <user_id>")
        return

    try:
        try:
            from .utils import delete_operator_notifications, clear_assigned_operator
            delete_operator_notifications(user_id)
            clear_assigned_operator(user_id)
        except Exception:
            pass

        clear_operator_chat(user_id)
        try:
            await safe_send_message(message.bot, user_id, "ℹ️ Оператор завершил чат. Вы снова в автоматическом режиме.")
        except Exception:
            pass

        await message.answer(f"✅ Режим чата для пользователя {user_id} завершён")
    except Exception as e:
        logger.error(f"Ошибка при завершении чата для {user_id}: {e}")
        await message.answer("❌ Ошибка при завершении чата")

@router.callback_query(F.data == "edit_setting_suppliers_chat_id")
async def edit_suppliers_chat_id_callback(callback: types.CallbackQuery, state: FSMContext):
    """Настройка ID чата для уведомлений поставщиков"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    current_value = database.get_setting('suppliers_chat_id', '')
    
    text = f"""🏭 <b>Настройка чата для уведомлений поставщиков</b>

Здесь вы можете указать ID чата или группы, куда будут отправляться заявки от поставщиков.

<b>Текущее значение:</b> {current_value or 'Не установлено'}

<b>Как получить ID чата:</b>
1. Добавьте бота в нужный чат/группу
2. Дайте боту права администратора
3. Отправьте в чат любое сообщение
4. Бот автоматически определит ID

<b>Введите ID чата (число):</b>
<i>Или отправьте /id в нужный чат чтобы получить его ID</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Узнать ID чата", url="https://t.me/username_to_id_bot")],
        [types.InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="admin_settings")]
    ])
    
    await update_message(callback.from_user.id, text,
                       parse_mode="HTML", 
                       bot=callback.bot)
    
    await state.update_data(setting_key='suppliers_chat_id')
    await state.set_state(BookingStates.editing_setting)
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

@router.callback_query(F.data == "admin_back_to_promocodes")
async def admin_back_to_promocodes_callback(callback: types.CallbackQuery):
    """Возврат в меню промокодов из админки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    await admin_promocodes_callback(callback)

# ===== УПРАВЛЕНИЕ ПРОМОКОДАМИ =====

# Словарь для хранения ID сообщений пользователя при создании промокодов
user_promocode_messages = {}

async def cleanup_promocode_messages(user_id: int, bot):
    """Удаление всех сообщений пользователя при создании промокода"""
    if user_id in user_promocode_messages:
        for msg_id in user_promocode_messages[user_id][:]:
            try:
                await bot.delete_message(user_id, msg_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение промокода {msg_id}: {e}")
            user_promocode_messages[user_id].remove(msg_id)
        user_promocode_messages[user_id] = []

async def add_promocode_message(user_id: int, message_id: int):
    """Добавление ID сообщения в список для удаления"""
    if user_id not in user_promocode_messages:
        user_promocode_messages[user_id] = []
    user_promocode_messages[user_id].append(message_id)

@router.callback_query(F.data == "admin_promocodes")
async def admin_promocodes_callback(callback: types.CallbackQuery):
    """Быстрое управление промокодами"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    active_promocodes = database.get_all_promocodes()
    active_count = sum(1 for p in active_promocodes if p['is_active'])
    
    text = f"""🎁 <b>Управление промокодами</b>

<b>Статистика:</b>
✅ Активных промокодов: {active_count}
📊 Всего промокодов: {len(active_promocodes)}

<b>Последние активные промокоды:</b>"""
    
    for promo in active_promocodes[:3]:
        if promo['is_active']:
            discount = f"{promo['discount_percent']}%" if promo['discount_percent'] > 0 else f"{promo['discount_amount']}₽"
            text += f"\n• <code>{promo['code']}</code> - {discount}"
            if promo.get('description'):
                text += f" ({promo['description'][:20]}...)"
    
    text += "\n\n💡 <i>Промокоды могут быть общими, для конкретных пользователей или для определенных блюд</i>"
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboards.promocodes_admin_menu(),
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_add_promocode")
async def admin_add_promocode_callback(callback: types.CallbackQuery, state: FSMContext):
    """Добавление нового промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    text = """🎁 <b>Создание промокода</b>

<b>Шаг 1: Выберите тип промокода:</b>

1. <b>Общий</b> - для всех пользователей
2. <b>Индивидуальный</b> - для конкретного пользователя (по телефону)
3. <b>Товарный</b> - для категорий или конкретных блюд

<b>Выберите тип:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🌐 Общий промокод", callback_data="add_general_promocode")],
        [types.InlineKeyboardButton(text="👤 Индивидуальный промокод", callback_data="add_personal_promocode")],
        [types.InlineKeyboardButton(text="🍽️ Товарный промокод", callback_data="add_product_promocode")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "add_general_promocode")
async def add_general_promocode_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания общего промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    text = """🎁 <b>Создание общего промокода</b>

Введите код промокода (только латинские буквы и цифры):
<i>Пример: SUMMER20, BONUS15, WELCOME10</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_add_promocode")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.update_data(promocode_type='general')
    await state.set_state(PromocodeStates.waiting_promocode_code)

@router.callback_query(F.data == "add_personal_promocode")
async def add_personal_promocode_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания индивидуального промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    text = """👤 <b>Создание индивидуального промокода</b>

Введите телефон пользователя в формате:
<i>+79991234567 или 79991234567</i>

Промокод будет привязан только к этому номеру телефона."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_add_promocode")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.update_data(promocode_type='personal')
    await state.set_state(PromocodeStates.waiting_phone_for_promocode)

@router.callback_query(F.data == "add_product_promocode")
async def add_product_promocode_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания товарного промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    text = """🍽️ <b>Создание товарного промокода</b>

<b>Выберите действие:</b>

1. <b>Для категории блюд</b> - скидка на все блюда категории
2. <b>Для конкретных блюд</b> - выбрать одно или несколько блюд
3. <b>Для всего меню</b> - скидка на всё меню

<b>Выберите вариант:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📂 Для категории блюд", callback_data="promo_for_category")],
        [types.InlineKeyboardButton(text="🍽️ Для конкретных блюд", callback_data="promo_for_dishes")],
        [types.InlineKeyboardButton(text="📋 Для всего меню", callback_data="promo_for_all_menu")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_add_promocode")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.update_data(promocode_type='product')

# Состояния для промокодов
class PromocodeStates(StatesGroup):
    waiting_promocode_code = State()
    waiting_phone_for_promocode = State()
    waiting_discount_type = State()
    waiting_discount_value = State()
    waiting_min_order = State()
    waiting_max_discount = State()
    waiting_valid_from_date = State()
    waiting_valid_to_date = State()
    waiting_single_use = State()
    waiting_description = State()
    waiting_category_selection = State()
    waiting_dish_selection = State()
    waiting_promocode_conditions = State()

# ===== ОБРАБОТЧИКИ СООБЩЕНИЙ ДЛЯ ПРОМОКОДОВ =====

@router.message(PromocodeStates.waiting_promocode_code)
async def process_promocode_code(message: types.Message, state: FSMContext):
    """Обработка кода промокода"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    code = message.text.strip().upper()
    
    # Проверяем формат
    if not re.match(r'^[A-Z0-9]+$', code):
        await update_message(message.from_user.id,
                           "❌ <b>Неверный формат кода!</b>\n\nИспользуйте только латинские буквы и цифры.",
                           parse_mode="HTML",
                           bot=message.bot)
        return
    
    # Проверяем уникальность
    existing = database.get_promocode(code)
    if existing:
        await update_message(message.from_user.id,
                           f"❌ <b>Промокод {code} уже существует!</b>",
                           parse_mode="HTML",
                           bot=message.bot)
        return
    
    await state.update_data(promocode_code=code)
    
    text = f"""🎁 <b>Промокод: {code}</b>

<b>Выберите тип скидки:</b>

1. <b>Процентная скидка</b> (например, 20%)
2. <b>Фиксированная сумма</b> (например, 500₽)"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📊 Процентная скидка", callback_data="discount_percent")],
        [types.InlineKeyboardButton(text="💰 Фиксированная сумма", callback_data="discount_amount")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_add_promocode")]
    ])
    
    await update_message(message.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=message.bot)
    
    await state.set_state(PromocodeStates.waiting_discount_type)

@router.message(PromocodeStates.waiting_phone_for_promocode)
async def process_phone_for_promocode(message: types.Message, state: FSMContext):
    """Обработка телефона для индивидуального промокода"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    phone = message.text.strip()
    
    # Нормализуем номер телефона
    phone = re.sub(r'[^\d+]', '', phone)
    if phone.startswith('8'):
        phone = '+7' + phone[1:]
    elif phone.startswith('7') and not phone.startswith('+7'):
        phone = '+' + phone
    
    # Проверяем формат
    if not re.match(r'^\+7\d{10}$', phone):
        await update_message(message.from_user.id,
                           "❌ <b>Неверный формат телефона!</b>\n\nИспользуйте формат: +79991234567",
                           parse_mode="HTML",
                           bot=message.bot)
        return
    
    await state.update_data(phone=phone)
    
    text = f"""👤 <b>Индивидуальный промокод для {phone}</b>

Введите код промокода (только латинские буквы и цифры):
<i>Пример: IRINA20, VIP15, SPECIAL10</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_add_promocode")]
    ])
    
    await update_message(message.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=message.bot)
    
    await state.set_state(PromocodeStates.waiting_promocode_code)

@router.callback_query(F.data.in_(["discount_percent", "discount_amount"]))
async def process_discount_type(callback: types.CallbackQuery, state: FSMContext):
    """Обработка типа скидки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    discount_type = 'percent' if callback.data == 'discount_percent' else 'amount'
    await state.update_data(discount_type=discount_type)
    
    if discount_type == 'percent':
        text = """📊 <b>Процентная скидка</b>

Введите размер скидки в процентах:
<i>От 1 до 100%</i>

<i>Пример: 20 (для 20% скидки)</i>"""
    else:
        text = """💰 <b>Фиксированная скидка</b>

Введите сумму скидки в рублях:
<i>Минимальная сумма: 1 рубль</i>

<i>Пример: 500 (для скидки 500₽)</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_promocode_type")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(PromocodeStates.waiting_discount_value)

@router.message(PromocodeStates.waiting_discount_value)
async def process_discount_value(message: types.Message, state: FSMContext):
    """Обработка значения скидки"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    try:
        value = float(message.text.strip())
        data = await state.get_data()
        discount_type = data.get('discount_type')
        
        if discount_type == 'percent':
            if value < 1 or value > 100:
                raise ValueError("Процент должен быть от 1 до 100")
        else:
            if value < 1:
                raise ValueError("Сумма должна быть не менее 1 рубля")
        
        await state.update_data(discount_value=value)
        
        text = """💰 <b>Минимальная сумма заказа</b>

Введите минимальную сумму заказа для применения промокода:
<i>0 - если промокод действует на любую сумму</i>

<i>Пример: 3000 (для заказов от 3000₽)</i>"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➡️ Пропустить (любая сумма)", callback_data="skip_min_order")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_discount_type")]
        ])
        
        await update_message(message.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=message.bot)
        
        await state.set_state(PromocodeStates.waiting_min_order)
        
    except ValueError as e:
        await update_message(message.from_user.id,
                           f"❌ <b>Неверное значение!</b>\n\n{str(e)}",
                           parse_mode="HTML",
                           bot=message.bot)

@router.message(PromocodeStates.waiting_min_order)
async def process_min_order_amount(message: types.Message, state: FSMContext):
    """Обработка минимальной суммы заказа для промокода"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    try:
        min_order = float(message.text.strip())
        if min_order < 0:
            raise ValueError("Сумма не может быть отрицательной")
        
        await state.update_data(min_order_amount=min_order)
        
        data = await state.get_data()
        discount_type = data.get('discount_type')
        
        if discount_type == 'percent':
            text = """📈 <b>Максимальная сумма скидки</b>

Введите максимальную сумму скидки в рублях:
<i>0 - если нет ограничения</i>

<i>Пример: 1000 (максимальная скидка 1000₽, даже если 20% от заказа больше)</i>"""
            
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="➡️ Без ограничения", callback_data="skip_max_discount")],
                [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_discount_value")]
            ])
            
            await update_message(message.from_user.id, text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                bot=message.bot)
            
            await state.set_state(PromocodeStates.waiting_max_discount)
        else:
            # Для фиксированной скидки пропускаем этот шаг
            await ask_for_valid_from_date(message.from_user.id, message.bot, state)
        
    except ValueError as e:
        await update_message(message.from_user.id,
                           f"❌ <b>Неверное значение!</b>\n\n{str(e)}",
                           parse_mode="HTML",
                           bot=message.bot)

@router.message(PromocodeStates.waiting_max_discount)
async def process_max_discount_amount(message: types.Message, state: FSMContext):
    """Обработка максимальной суммы скидки"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    try:
        max_discount = float(message.text.strip())
        if max_discount < 0:
            raise ValueError("Сумма не может быть отрицательной")
        
        await state.update_data(max_discount_amount=max_discount)
        await ask_for_valid_from_date(message.from_user.id, message.bot, state)
        
    except ValueError as e:
        await update_message(message.from_user.id,
                           f"❌ <b>Неверное значение!</b>\n\n{str(e)}",
                           parse_mode="HTML",
                           bot=message.bot)

@router.message(PromocodeStates.waiting_valid_from_date)
async def process_valid_from_date(message: types.Message, state: FSMContext):
    """Обработка даты начала действия"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    date_text = message.text.strip()
    
    # Проверяем формат даты
    try:
        date_obj = datetime.strptime(date_text, '%d.%m.%Y')
        today = datetime.now().date()
        
        # Проверяем, что дата не в прошлом
        if date_obj.date() < today:
            await update_message(message.from_user.id,
                               "❌ <b>Дата не может быть в прошлом!</b>\n\nВведите корректную дату:",
                               parse_mode="HTML",
                               bot=message.bot)
            return
        
        await state.update_data(valid_from=date_text)
        await ask_for_valid_to_date(message.from_user.id, message.bot, state)
        
    except ValueError:
        await update_message(message.from_user.id,
                           "❌ <b>Неверный формат даты!</b>\n\nИспользуйте формат: ДД.ММ.ГГГГ\n<i>Пример: 09.01.2026</i>",
                           parse_mode="HTML",
                           bot=message.bot)

@router.message(PromocodeStates.waiting_valid_to_date)
async def process_valid_to_date(message: types.Message, state: FSMContext):
    """Обработка даты окончания действия"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    date_text = message.text.strip()
    
    # Проверяем формат даты
    try:
        date_obj = datetime.strptime(date_text, '%d.%m.%Y')
        
        state_data = await state.get_data()
        valid_from_str = state_data.get('valid_from')
        
        if valid_from_str:
            valid_from_obj = datetime.strptime(valid_from_str, '%d.%m.%Y')
            
            # Проверяем, что дата окончания позже даты начала
            if date_obj.date() <= valid_from_obj.date():
                await update_message(message.from_user.id,
                                   "❌ <b>Дата окончания должна быть позже даты начала!</b>\n\nВведите корректную дату:",
                                   parse_mode="HTML",
                                   bot=message.bot)
                return
        
        await state.update_data(valid_to=date_text)
        await process_valid_dates_complete(message.from_user.id, message.bot, state)
        
    except ValueError:
        await update_message(message.from_user.id,
                           "❌ <b>Неверный формат даты!</b>\n\nИспользуйте формат: ДД.ММ.ГГГГ\n<i>Пример: 09.03.2026</i>",
                           parse_mode="HTML",
                           bot=message.bot)

@router.message(PromocodeStates.waiting_promocode_conditions)
async def process_max_uses(message: types.Message, state: FSMContext):
    """Обработка лимита использований"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    try:
        max_uses = int(message.text.strip())
        if max_uses < 0:
            raise ValueError("Количество не может быть отрицательным")
        
        await state.update_data(max_uses=max_uses)
        await ask_for_description(message.from_user.id, message.bot, state)
        
    except ValueError as e:
        await update_message(message.from_user.id,
                           f"❌ <b>Неверное значение!</b>\n\n{str(e)}",
                           parse_mode="HTML",
                           bot=message.bot)

@router.message(PromocodeStates.waiting_description)
async def process_description(message: types.Message, state: FSMContext):
    """Обработка описания промокода"""
    if not is_admin_fast(message.from_user.id):
        return
    
    # Добавляем сообщение в список для удаления
    await add_promocode_message(message.from_user.id, message.message_id)
    
    description = message.text.strip()
    
    # Очищаем все предыдущие сообщения перед финальным шагом
    await cleanup_promocode_messages(message.from_user.id, message.bot)
    
    await finalize_promocode(message.from_user.id, message.bot, state, description)

@router.message(PromocodeStates.waiting_promocode_conditions)
async def process_promocode_stats_request(message: types.Message, state: FSMContext):
    """Обработка запроса детальной статистики"""
    if not is_admin_fast(message.from_user.id):
        return
    
    code = message.text.strip().upper()
    stats = database.get_promocode_stats(code)
    
    if not stats:
        text = f"""❌ <b>Промокод не найден</b>

Промокод <code>{code}</code> не существует в системе.

Проверьте правильность ввода или создайте новый промокод."""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать другой код", callback_data="admin_detailed_promo_stats")],
            [types.InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_add_promocode")],
            [types.InlineKeyboardButton(text="⬅️ Назад к статистике", callback_data="admin_promocodes_stats")]
        ])
    else:
        text = f"""📊 <b>Детальная статистика: {code}</b>

<b>Основная информация:</b>
📅 Создан: {stats['created_at'][:10] if stats['created_at'] else 'Неизвестно'}
🎯 Использований: {stats['used_count']}/{stats['max_uses'] if stats['max_uses'] > 0 else '∞'}
💸 Скидка: {stats['discount_percent']}% или {stats['discount_amount']}₽
📈 Минимальный заказ: {stats.get('min_order_amount', 0)}₽
✅ Статус: {'Активен ✅' if stats['is_active'] else 'Неактивен ❌'}

<b>Срок действия:</b>
📅 Начало: {stats['valid_from'] or 'Не ограничено'}
📅 Окончание: {stats['valid_to'] or 'Не ограничено'}"""

        # Добавляем информацию о категориях/блюдах
        settings = stats.get('settings', {})
        dish_promos = []
        category_promos = []
        
        for key, value in settings.items():
            if key.startswith(f'promocode_{code}_dish_'):
                dish_id = key.replace(f'promocode_{code}_dish_', '')
                dish_promos.append(dish_id)
            elif key.startswith(f'promocode_{code}_category_'):
                category_id = key.replace(f'promocode_{code}_category_', '')
                category_promos.append(category_id)
        
        if dish_promos:
            text += f"\n\n<b>Применяется к блюдам:</b> {len(dish_promos)} блюд"
            if len(dish_promos) <= 5:
                for dish_id in dish_promos[:5]:
                    text += f"\n• ID: {dish_id}"
        
        if category_promos:
            text += f"\n\n<b>Применяется к категориям:</b> {len(category_promos)} категорий"
            if len(category_promos) <= 5:
                for category_id in category_promos[:5]:
                    text += f"\n• ID: {category_id}"
        
        # Добавляем историю использований
        usage = stats.get('usage', [])
        if usage:
            text += f"\n\n<b>Последние использования ({len(usage)}):</b>"
            for i, use in enumerate(usage[:3], 1):
                date_str = use['used_at'][:10] if use['used_at'] else 'Неизвестно'
                user_info = use['full_name'] or f"Пользователь {use['user_id']}"
                discount = use['discount_amount'] or '?'
                text += f"\n{i}. {date_str} - {user_info} (-{discount}₽)"
            
            if len(usage) > 3:
                text += f"\n... и еще {len(usage) - 3} использований"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📋 Список всех использований", callback_data=f"admin_promo_usage_{code}")],
            [types.InlineKeyboardButton(text="✏️ Редактировать промокод", callback_data=f"admin_edit_promocode_{code}")],
            [types.InlineKeyboardButton(text="🔄 Обновить статистику", callback_data="admin_promocodes_stats")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes_stats")]
        ])
    
    await update_message(message.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=message.bot)
    
    await state.clear()

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ПРОМОКОДОВ =====

async def ask_for_valid_from_date(user_id: int, bot, state: FSMContext):
    """Запрос даты начала действия промокода"""
    today = datetime.now().strftime('%d.%m.%Y')
    
    text = f"""📅 <b>Дата начала действия промокода</b>

Введите дату начала действия промокода в формате <b>ДД.ММ.ГГГГ</b>

<i>Сегодня: {today}</i>
<i>Пример: 09.01.2026</i>

Или нажмите "С сегодняшнего дня", чтобы начать с текущей даты."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🗓️ С сегодняшнего дня", callback_data="start_from_today")],
        [types.InlineKeyboardButton(text="🔄 Бессрочный промокод", callback_data="unlimited_promocode")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_max_discount")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)
    
    await state.set_state(PromocodeStates.waiting_valid_from_date)

async def ask_for_valid_to_date(user_id: int, bot, state: FSMContext):
    """Запрос даты окончания действия промокода"""
    state_data = await state.get_data()
    valid_from = state_data.get('valid_from', datetime.now().strftime('%d.%m.%Y'))
    
    text = f"""📅 <b>Дата окончания действия промокода</b>

<b>Начало действия:</b> {valid_from}

Введите дату окончания действия промокода в формате <b>ДД.ММ.ГГГГ</b>

<i>Пример: 09.03.2026 (на 2 месяца)</i>
<i>Или: 31.12.2026 (до конца года)</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➡️ До конца месяца", callback_data="end_of_month")],
        [types.InlineKeyboardButton(text="➡️ До конца года", callback_data="end_of_year")],
        [types.InlineKeyboardButton(text="⬅️ Изменить начало", callback_data="back_to_valid_from")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)
    
    await state.set_state(PromocodeStates.waiting_valid_to_date)

async def ask_for_description(user_id: int, bot, state: FSMContext):
    """Запрос описания промокода"""
    text = """📝 <b>Описание промокода</b>

Введите описание промокода (необязательно):
<i>Это описание будет видно только в админке</i>

<i>Пример: "Летняя акция 20% на все заказы"</i>

Или нажмите "Пропустить", чтобы оставить без описания."""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_description")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_single_use")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)
    
    await state.set_state(PromocodeStates.waiting_description)

async def process_valid_dates_complete(user_id: int, bot, state: FSMContext):
    """Завершение ввода дат и переход к следующему шагу"""
    state_data = await state.get_data()
    valid_from = state_data.get('valid_from')
    valid_to = state_data.get('valid_to')
    
    # Преобразуем даты в нужный формат для БД (YYYY-MM-DD)
    if valid_from and valid_to:
        try:
            from_date = datetime.strptime(valid_from, '%d.%m.%Y').strftime('%Y-%m-%d')
            to_date = datetime.strptime(valid_to, '%d.%m.%Y').strftime('%Y-%m-%d')
            await state.update_data(
                valid_from_db=from_date,
                valid_to_db=to_date,
                valid_from_display=valid_from,
                valid_to_display=valid_to
            )
        except:
            await state.update_data(
                valid_from_db=valid_from,
                valid_to_db=valid_to,
                valid_from_display=valid_from,
                valid_to_display=valid_to
            )
    
    text = """🔄 <b>Одноразовый промокод?</b>

Промокод можно использовать:
• <b>Один раз</b> - после использования становится неактивным
• <b>Многоразовый</b> - можно использовать много раз (до лимита использований)

<b>Выберите тип:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Одноразовый", callback_data="single_use")],
        [types.InlineKeyboardButton(text="🔄 Многоразовый", callback_data="multi_use")],
        [types.InlineKeyboardButton(text="⬅️ Назад к дате начала", callback_data="back_to_valid_from")]
    ])
    
    await update_message(user_id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=bot)
    
    await state.set_state(PromocodeStates.waiting_single_use)

async def finalize_promocode(user_id: int, bot, state: FSMContext, description: str):
    """Финальное создание промокода"""
    data = await state.get_data()
    
    # Собираем все данные
    code = data.get('promocode_code')
    promocode_type = data.get('promocode_type', 'general')
    discount_type = data.get('discount_type')
    discount_value = data.get('discount_value')
    min_order_amount = data.get('min_order_amount', 0)
    max_discount_amount = data.get('max_discount_amount', 0)
    
    # Используем даты из новых полей
    valid_from = data.get('valid_from_db')
    valid_to = data.get('valid_to_db')
    valid_from_display = data.get('valid_from_display')
    valid_to_display = data.get('valid_to_display')
    
    is_single_use = data.get('is_single_use', True)
    max_uses = 1 if is_single_use else data.get('max_uses', 0)
    
    # Определяем параметры для базы данных
    discount_percent = discount_value if discount_type == 'percent' else 0
    discount_amount = discount_value if discount_type == 'amount' else 0
    
    # Для индивидуальных промокодов добавляем префикс
    if promocode_type == 'personal':
        phone = data.get('phone', '')
        # Сохраняем связь промокода с телефоном
        database.update_setting(f'promocode_{code}_phone', phone)
    
    # Для товарных промокодов сохраняем информацию о категориях/блюдах
    selected_categories = data.get('selected_categories', [])
    selected_dishes = data.get('selected_dishes', [])
    is_all_menu = data.get('is_all_menu', False)
    
    # Создаем промокод в базе данных
    success = database.add_promocode(
        code=code,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        description=description,
        min_order_amount=min_order_amount,
        max_uses=max_uses,
        is_first_order_only=False,
        valid_from=valid_from,
        valid_to=valid_to
    )
    
    if success:
        # Сохраняем информацию о категориях/блюдах для товарных промокодов
        if promocode_type == 'product':
            if is_all_menu:
                database.update_setting(f'promocode_{code}_all_menu', 'true')
            
            for category_id in selected_categories:
                database.update_setting(f'promocode_{code}_category_{category_id}', 'true')
            
            for dish_id in selected_dishes:
                database.update_setting(f'promocode_{code}_dish_{dish_id}', 'true')
        
        # Формируем текст успешного создания
        text = f"""✅ <b>Промокод создан успешно!</b>

<b>Код:</b> <code>{code}</code>
<b>Тип:</b> {'Общий' if promocode_type == 'general' else 'Индивидуальный' if promocode_type == 'personal' else 'Товарный'}
<b>Скидка:</b> {discount_value}{'%' if discount_type == 'percent' else '₽'}
<b>Минимальный заказ:</b> {min_order_amount}₽"""
        
        if valid_from and valid_to:
            text += f"\n<b>Срок действия:</b> с {valid_from_display} по {valid_to_display}"
        else:
            text += "\n<b>Срок действия:</b> бессрочно"
        
        text += f"\n<b>Использований:</b> {'1 раз' if is_single_use else f'{max_uses} раз' if max_uses > 0 else 'без ограничений'}"
        
        if promocode_type == 'personal':
            text += f"\n<b>Для телефона:</b> {data.get('phone')}"
        
        if promocode_type == 'product':
            if is_all_menu:
                text += f"\n<b>Применение:</b> На всё меню"
            elif selected_categories:
                text += f"\n<b>Применение:</b> {len(selected_categories)} категорий"
            elif selected_dishes:
                text += f"\n<b>Применение:</b> {len(selected_dishes)} блюд"
        
        if discount_type == 'percent' and max_discount_amount > 0:
            text += f"\n<b>Макс. скидка:</b> {max_discount_amount}₽"
        
        if description:
            text += f"\n<b>Описание:</b> {description}"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ Создать еще промокод", callback_data="admin_add_promocode")],
            [types.InlineKeyboardButton(text="📋 Все промокоды", callback_data="admin_view_promocodes")],
            [types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_promocodes_stats")],
            [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
        ])
        
        await update_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
        
        # Логируем создание промокода
        database.log_action(user_id, "promocode_created", f"code:{code}, type:{promocode_type}")
    else:
        text = "❌ <b>Ошибка при создании промокода!</b>\n\nПопробуйте еще раз."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="admin_add_promocode")],
            [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
        ])
        
        await update_message(user_id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=bot)
    
    await state.clear()

# ===== КОЛБЭК ОБРАБОТЧИКИ ДЛЯ ПРОМОКОДОВ =====

@router.callback_query(F.data == "back_to_promocode_type")
async def back_to_promocode_type(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору типа скидки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    data = await state.get_data()
    code = data.get('promocode_code', 'НОВЫЙ')
    
    text = f"""🎁 <b>Промокод: {code}</b>

<b>Выберите тип скидки:</b>

1. <b>Процентная скидка</b> (например, 20%)
2. <b>Фиксированная сумма</b> (например, 500₽)"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📊 Процентная скидка", callback_data="discount_percent")],
        [types.InlineKeyboardButton(text="💰 Фиксированная сумма", callback_data="discount_amount")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_add_promocode")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(PromocodeStates.waiting_discount_type)

@router.callback_query(F.data == "skip_min_order")
async def skip_min_order_callback(callback: types.CallbackQuery, state: FSMContext):
    """Пропуск минимальной суммы заказа"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    await state.update_data(min_order_amount=0)
    
    data = await state.get_data()
    discount_type = data.get('discount_type')
    
    if discount_type == 'percent':
        text = """📈 <b>Максимальная сумма скидки</b>

Введите максимальную сумму скидки в рублях:
<i>0 - если нет ограничения</i>

<i>Пример: 1000 (максимальная скидка 1000₽, даже если 20% от заказа больше)</i>"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➡️ Без ограничения", callback_data="skip_max_discount")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_discount_value")]
        ])
        
        await update_message(callback.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
        
        await state.set_state(PromocodeStates.waiting_max_discount)
    else:
        # Для фиксированной скидки пропускаем этот шаг
        await ask_for_valid_from_date(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data == "skip_max_discount")
async def skip_max_discount_callback(callback: types.CallbackQuery, state: FSMContext):
    """Пропуск максимальной скидки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    await state.update_data(max_discount_amount=0)
    await ask_for_valid_from_date(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data == "start_from_today")
async def start_from_today_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начинаем с сегодняшней даты"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    today = datetime.now().strftime('%d.%m.%Y')
    await state.update_data(valid_from=today)
    await ask_for_valid_to_date(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data == "end_of_month")
async def end_of_month_callback(callback: types.CallbackQuery, state: FSMContext):
    """Устанавливаем дату окончания - конец текущего месяца"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Получаем последний день текущего месяца
    today = datetime.now()
    if today.month == 12:
        last_day = datetime(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(today.year, today.month + 1, 1) - timedelta(days=1)
    
    valid_to = last_day.strftime('%d.%m.%Y')
    await state.update_data(valid_to=valid_to)
    
    await process_valid_dates_complete(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data == "end_of_year")
async def end_of_year_callback(callback: types.CallbackQuery, state: FSMContext):
    """Устанавливаем дату окончания - конец текущего года"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    today = datetime.now()
    valid_to = f"31.12.{today.year}"
    await state.update_data(valid_to=valid_to)
    
    await process_valid_dates_complete(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data == "unlimited_promocode")
async def unlimited_promocode_callback(callback: types.CallbackQuery, state: FSMContext):
    """Создание бессрочного промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    await state.update_data(valid_from=None, valid_to=None)
    
    text = """🔄 <b>Одноразовый промокод?</b>

Промокод можно использовать:
• <b>Один раз</b> - после использования становится неактивным
• <b>Многоразовый</b> - можно использовать много раз (до лимита использований)

<b>Выберите тип:</b>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Одноразовый", callback_data="single_use")],
        [types.InlineKeyboardButton(text="🔄 Многоразовый", callback_data="multi_use")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_valid_from")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(PromocodeStates.waiting_single_use)

@router.callback_query(F.data.in_(["single_use", "multi_use"]))
async def process_single_use(callback: types.CallbackQuery, state: FSMContext):
    """Обработка типа использования промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    is_single_use = callback.data == 'single_use'
    await state.update_data(is_single_use=is_single_use)
    
    if not is_single_use:
        text = """🔄 <b>Многоразовый промокод</b>

<b>Выберите, может ли один пользователь использовать промокод несколько раз:</b>

1. <b>Только один раз на пользователя</b> - пользователь может использовать промокод только один раз (рекомендуется)
2. <b>Много раз на пользователя</b> - один пользователь может использовать промокод много раз

<b>Выберите вариант:</b>"""
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Только один раз на пользователя", callback_data="once_per_user")],
            [types.InlineKeyboardButton(text="🔄 Много раз на пользователя", callback_data="multi_per_user")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_valid_dates")]
        ])
        
        await update_message(callback.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=callback.bot)
    else:
        # Для одноразового промокода = только один раз на пользователя
        await state.update_data(once_per_user=True, max_uses=1)
        await ask_for_description(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data.in_(["once_per_user", "multi_per_user"]))
async def process_once_per_user(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора once_per_user"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    once_per_user = callback.data == 'once_per_user'
    await state.update_data(once_per_user=once_per_user)
    
    text = """🔢 <b>Лимит использований</b>

Введите максимальное количество использований промокода:
<i>0 - без ограничений (не рекомендуется)</i>

<i>Пример: 100 (промокод можно использовать 100 раз всего)</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➡️ Без ограничений", callback_data="unlimited_uses")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_single_use")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(PromocodeStates.waiting_promocode_conditions)

@router.callback_query(F.data == "unlimited_uses")
async def unlimited_uses_callback(callback: types.CallbackQuery, state: FSMContext):
    """Без ограничений на использование"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    await state.update_data(max_uses=0)
    await ask_for_description(callback.from_user.id, callback.bot, state)

@router.callback_query(F.data == "skip_description")
async def skip_description_callback(callback: types.CallbackQuery, state: FSMContext):
    """Пропуск описания промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем все предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    await finalize_promocode(callback.from_user.id, callback.bot, state, '')

# Обработчики кнопок "Назад"
@router.callback_query(F.data.in_([
    "back_to_discount_type", 
    "back_to_discount_value",
    "back_to_max_discount",
    "back_to_min_order",
    "back_to_valid_from",
    "back_to_valid_dates",
    "back_to_single_use"
]))
async def back_to_previous_step(callback: types.CallbackQuery, state: FSMContext):
    """Общий обработчик для кнопок 'Назад'"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем сообщения текущего шага
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    # Возвращаемся к началу создания промокода
    await admin_add_promocode_callback(callback, state)

# ===== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ПРОМОКОДОВ =====

@router.callback_query(F.data == "admin_back_to_promocodes")
async def admin_back_to_promocodes_callback(callback: types.CallbackQuery):
    """Возврат в меню промокодов из админки"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    await admin_promocodes_callback(callback)

@router.callback_query(F.data == "admin_view_promocodes")
async def admin_view_promocodes_callback(callback: types.CallbackQuery):
    """Просмотр всех промокодов"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    promocodes = database.get_all_promocodes()
    
    if not promocodes:
        text = "🎁 <b>Все промокоды</b>\n\nПромокодов пока нет."
    else:
        text = f"""🎁 <b>Все промокоды</b>

<b>Всего промокодов:</b> {len(promocodes)}
<b>Активных:</b> {sum(1 for p in promocodes if p['is_active'])}
<b>Использовано:</b> {sum(p['used_count'] for p in promocodes)}

<b>Список промокодов:</b>\n"""
        
        for promo in promocodes[:10]:  # Показываем первые 10
            status = "✅" if promo['is_active'] else "❌"
            type_text = "🔢" if promo['discount_percent'] > 0 else "💰"
            discount = f"{promo['discount_percent']}%" if promo['discount_percent'] > 0 else f"{promo['discount_amount']}₽"
            
            text += f"\n{status} <code>{promo['code']}</code> {type_text} {discount}"
            text += f" | Использовано: {promo['used_count']}/{promo['max_uses'] if promo['max_uses'] > 0 else '∞'}"
            if promo.get('valid_to'):
                try:
                    date_obj = datetime.strptime(promo['valid_to'], '%Y-%m-%d')
                    text += f" | До: {date_obj.strftime('%d.%m.%Y')}"
                except:
                    text += f" | До: {promo['valid_to']}"
        
        if len(promocodes) > 10:
            text += f"\n\n... и еще {len(promocodes) - 10} промокодов"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Создать новый", callback_data="admin_add_promocode")],
        [types.InlineKeyboardButton(text="⚙️ Управление", callback_data="admin_manage_promocodes")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_manage_promocodes")
async def admin_manage_promocodes_callback(callback: types.CallbackQuery):
    """Управление промокодами"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Очищаем предыдущие сообщения
    await cleanup_promocode_messages(callback.from_user.id, callback.bot)
    
    text = """⚙️ <b>Управление промокодами</b>

Выберите действие:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Активировать/деактивировать", callback_data="admin_toggle_promocode")],
        [types.InlineKeyboardButton(text="✏️ Изменить промокод", callback_data="admin_edit_promocode")],
        [types.InlineKeyboardButton(text="🗑️ Удалить промокод", callback_data="admin_delete_promocode")],
        [types.InlineKeyboardButton(text="📊 Статистика промокодов", callback_data="admin_promocodes_stats")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_promocodes_stats")
async def admin_promocodes_stats_callback(callback: types.CallbackQuery):
    """Статистика промокодов"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    stats = database.get_all_promocode_stats()
    
    text = f"""📊 <b>Статистика промокодов</b>

<b>Общая статистика:</b>
📈 Всего промокодов: {stats.get('total', 0)}
✅ Активных: {stats.get('active', 0)}
🚀 Действующих сейчас: {stats.get('currently_active', 0)}
🎯 Всего использований: {stats.get('total_uses', 0)}

<b>Последние 30 дней:</b>"""
    
    daily_stats = stats.get('daily_stats', [])
    if daily_stats:
        for day_stat in daily_stats[:5]:  # Показываем последние 5 дней
            date_str = day_stat[0]
            count = day_stat[1]
            total_discount = day_stat[2] or 0
            text += f"\n• {date_str}: {count} использований (-{total_discount}₽)"
    else:
        text += "\n• Нет данных за последние 30 дней"
    
    text += f"\n\n<b>Самые популярные промокоды:</b>"
    
    popular_promos = stats.get('popular_promos', [])
    if popular_promos:
        for promo in popular_promos[:5]:  # Топ-5 промокодов
            code = promo[0]
            description = promo[1] or 'Без описания'
            used_count = promo[2]
            unique_users = promo[5] or 0
            
            text += f"\n• <code>{code}</code>: {used_count} использований ({unique_users} пользователей)"
            if len(description) > 30:
                text += f"\n  <i>{description[:30]}...</i>"
    else:
        text += "\n• Нет данных о популярности"
    
    text += "\n\n💡 <i>Статистика обновляется в реальном времени</i>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Подробная статистика по коду", callback_data="admin_detailed_promo_stats")],
        [types.InlineKeyboardButton(text="📊 Экспорт данных", callback_data="admin_export_promo_stats")],
        [types.InlineKeyboardButton(text="⬅️ Назад к промокодам", callback_data="admin_promocodes")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_detailed_promo_stats")
async def admin_detailed_promo_stats_callback(callback: types.CallbackQuery, state: FSMContext):
    """Запрос кода для детальной статистики"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = """🔍 <b>Подробная статистика по промокоду</b>

Введите код промокода для просмотра детальной статистики:
<i>Пример: FIRSTORDER20, SUMMER15, etc.</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes_stats")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(PromocodeStates.waiting_promocode_conditions)

@router.callback_query(F.data == "promo_for_category")
async def promo_for_category_callback(callback: types.CallbackQuery, state: FSMContext):
    """Выбор категорий для промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Загружаем категории из меню
    from menu_cache import menu_cache
    await menu_cache.load_all_menus()
    
    all_categories = []
    available_menus = menu_cache.get_available_menus()
    
    for menu in available_menus:
        menu_id = menu['id']
        categories = menu_cache.get_menu_categories(menu_id)
        
        for category in categories:
            category['menu_id'] = menu_id
            category['full_name'] = f"{category['display_name']} ({menu['name']})"
            all_categories.append(category)
    
    if not all_categories:
        text = "❌ <b>Нет доступных категорий</b>\n\nНе удалось загрузить меню. Попробуйте позже."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="promo_for_category")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="add_product_promocode")]
        ])
        
        await update_message(callback.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=callback.bot)
        return
    
    text = f"""📂 <b>Выбор категорий для промокода</b>

<b>Найдено категорий:</b> {len(all_categories)}
<b>Выберите категории, к которым будет применяться промокод:</b>

👆 Нажимайте на категории для выбора/отмены выбора
✅ Выбранные категории отмечены галочкой"""
    
    await state.update_data({
        'available_categories': all_categories,
        'selected_categories': []
    })
    
    keyboard = category_selection_keyboard(all_categories, [])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "promo_for_all_menu")
async def promo_for_all_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Промокод для всего меню"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Получаем текущие данные из state
    data = await state.get_data()
    code = data.get('promocode_code', 'НОВЫЙ')
    
    text = f"""📋 <b>Промокод для всего меню</b>

<b>Код:</b> <code>{code}</code>
<b>Тип:</b> Для всего меню

Промокод будет действовать на все блюда во всех меню.

Для продолжения введите код промокода:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="add_product_promocode")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    # Сохраняем информацию, что промокод для всего меню
    await state.update_data(is_all_menu=True)
    await state.set_state(PromocodeStates.waiting_promocode_code)

@router.callback_query(F.data.startswith("toggle_category_"))
async def toggle_category_selection(callback: types.CallbackQuery, state: FSMContext):
    """Переключение выбора категории"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    category_id = int(callback.data.replace("toggle_category_", ""))
    
    data = await state.get_data()
    selected_categories = data.get('selected_categories', [])
    available_categories = data.get('available_categories', [])
    
    if category_id in selected_categories:
        selected_categories.remove(category_id)
        await callback.answer(f"❌ Категория удалена из выбора")
    else:
        selected_categories.append(category_id)
        await callback.answer(f"✅ Категория добавлена в выбор")
    
    await state.update_data(selected_categories=selected_categories)
    
    # Обновляем клавиатуру
    keyboard = category_selection_keyboard(available_categories, selected_categories)
    
    try:
        await callback.bot.edit_message_reply_markup(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.debug(f"Не удалось обновить клавиатуру: {e}")

@router.callback_query(F.data == "promo_for_dishes")
async def promo_for_dishes_callback(callback: types.CallbackQuery, state: FSMContext):
    """Выбор конкретных блюд для промокода"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    # Загружаем все блюда из меню
    from menu_cache import menu_cache
    await menu_cache.load_all_menus()
    
    all_dishes = []
    available_menus = menu_cache.get_available_menus()
    
    for menu in available_menus:
        menu_id = menu['id']
        categories = menu_cache.get_menu_categories(menu_id)
        
        for category in categories:
            category_id = category['id']
            dishes = menu_cache.get_category_items(menu_id, category_id)
            
            for dish in dishes:
                dish['menu_id'] = menu_id
                dish['category_id'] = category_id
                dish['full_name'] = f"{dish['name']} ({menu['name']})"
                all_dishes.append(dish)
    
    if not all_dishes:
        text = "❌ <b>Нет доступных блюд</b>\n\nНе удалось загрузить меню. Попробуйте позже."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="promo_for_dishes")],
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="add_product_promocode")]
        ])
        
        await update_message(callback.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=callback.bot)
        return
    
    text = f"""🍽️ <b>Выбор блюд для промокода</b>

<b>Найдено блюд:</b> {len(all_dishes)}
<b>Выберите блюда, к которым будет применяться промокод:</b>

👆 Нажимайте на блюда для выбора/отмены выбора
✅ Выбранные блюда отмечены галочкой"""
    
    await state.update_data({
        'available_dishes': all_dishes,
        'selected_dishes': [],
        'current_dish_page': 0
    })
    
    keyboard = dish_selection_keyboard(all_dishes[:10], [], 0, 10)
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data.startswith("toggle_dish_"))
async def toggle_dish_selection(callback: types.CallbackQuery, state: FSMContext):
    """Переключение выбора блюда"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    dish_id = int(callback.data.replace("toggle_dish_", ""))
    
    data = await state.get_data()
    selected_dishes = data.get('selected_dishes', [])
    available_dishes = data.get('available_dishes', [])
    current_page = data.get('current_dish_page', 0)
    
    if dish_id in selected_dishes:
        selected_dishes.remove(dish_id)
        await callback.answer(f"❌ Блюдо удалено из выбора")
    else:
        selected_dishes.append(dish_id)
        await callback.answer(f"✅ Блюдо добавлено в выбор")
    
    await state.update_data(selected_dishes=selected_dishes)
    
    # Обновляем клавиатуру
    keyboard = dish_selection_keyboard(
        available_dishes, 
        selected_dishes, 
        current_page,
        10
    )
    
    try:
        await callback.bot.edit_message_reply_markup(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.debug(f"Не удалось обновить клавиатуру: {e}")

@router.callback_query(F.data.startswith("dish_page_"))
async def change_dish_page(callback: types.CallbackQuery, state: FSMContext):
    """Смена страницы при выборе блюд"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    page = int(callback.data.replace("dish_page_", ""))
    
    data = await state.get_data()
    available_dishes = data.get('available_dishes', [])
    selected_dishes = data.get('selected_dishes', [])
    
    await state.update_data(current_dish_page=page)
    
    # Обновляем клавиатуру
    keyboard = dish_selection_keyboard(
        available_dishes, 
        selected_dishes, 
        page,
        10
    )
    
    try:
        await callback.bot.edit_message_reply_markup(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.debug(f"Не удалось обновить клавиатуру: {e}")

@router.callback_query(F.data == "confirm_categories_selection")
async def confirm_categories_selection(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение выбора категорий"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    selected_categories = data.get('selected_categories', [])
    
    if not selected_categories:
        await callback.answer("❌ Выберите хотя бы одну категорию!", show_alert=True)
        return
    
    text = f"""✅ <b>Выбрано категорий: {len(selected_categories)}</b>

Для продолжения введите код промокода:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к выбору категорий", callback_data="promo_for_category")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(PromocodeStates.waiting_promocode_code)

@router.callback_query(F.data == "confirm_dishes_selection")
async def confirm_dishes_selection(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение выбора блюд"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    data = await state.get_data()
    selected_dishes = data.get('selected_dishes', [])
    
    if not selected_dishes:
        await callback.answer("❌ Выберите хотя бы одно блюдо!", show_alert=True)
        return
    
    text = f"""✅ <b>Выбрано блюд: {len(selected_dishes)}</b>

Для продолжения введите код промокода:"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад к выбору блюд", callback_data="promo_for_dishes")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(PromocodeStates.waiting_promocode_code)

# ===== ОБРАБОТЧИКИ УПРАВЛЕНИЯ ЧАТОМ =====

@router.message(Command("admin"))
@handler_timeout()
async def admin_command_handler(message: types.Message, state: FSMContext):
    """Обработчик команды /admin"""
    user_id = message.from_user.id
    
    logger.info(f"Получена команда /admin от {user_id}")
    
    # Всегда запрашиваем пароль
    await message.answer(
        "🔐 <b>Введите пароль для доступа к админке:</b>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_password)

@router.message(Command("admin_menu"))
@handler_timeout()
async def admin_menu_command_handler(message: types.Message):
    """Обработчик команды /admin_menu"""
    if not is_admin_fast(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели")
        return
    
    logger.info(f"Получена команда /admin_menu от {message.from_user.id}")
    
    # Показываем главное админ меню
    await show_admin_panel(message.from_user.id, message.bot)

async def show_admin_panel(user_id: int, bot):
    """Показать админ-панель"""
    text = """🛠️ <b>Админ-панель ресторана</b>

Выберите раздел для управления:"""

    await update_message(user_id, text,
                        reply_markup=keyboards.admin_menu(),
                        parse_mode="HTML",
                        bot=bot)

@router.callback_query(F.data.startswith("reply_"))
async def reply_callback_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Ответить' в уведомлениях о чате"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    try:
        # Получаем user_id из callback_data
        user_id_str = callback.data.replace("reply_", "")
        user_id = int(user_id_str)

        # Устанавливаем состояние ожидания ответа
        await state.set_state(AdminStates.waiting_reply)
        await state.update_data(reply_to_user=user_id)

        await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text=f"💬 Напишите ответ пользователю {user_id}:",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_reply")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка в reply_callback_handler: {e}")
        await callback.bot.send_message(
            callback.from_user.id,
            "❌ Ошибка обработки запроса"
        )

@router.callback_query(F.data.startswith("stop_chat_"))
async def stop_chat_callback_handler(callback: types.CallbackQuery):
    """Обработчик кнопки 'Завершить чат'"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    try:
        # Получаем user_id из callback_data
        user_id_str = callback.data.replace("stop_chat_", "")
        user_id = int(user_id_str)
        
        # Завершаем режим чата
        from .utils import clear_operator_chat, clear_operator_notifications
        clear_operator_chat(user_id)
        clear_operator_notifications(user_id)
        
        # Уведомляем пользователя
        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text="✅ Чат с администратором завершен. Если у вас остались вопросы, вы можете начать новый чат."
            )
        except Exception:
            pass
        
        await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text=f"✅ Чат с пользователем {user_id} завершен"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в stop_chat_callback_handler: {e}")
        await callback.bot.send_message(
            callback.from_user.id,
            "❌ Ошибка завершения чата"
        )

@router.callback_query(F.data == "cancel_reply")
async def cancel_reply_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отмена ответа пользователю"""
    await callback.answer()
    await state.clear()
    
    await callback.bot.send_message(
        chat_id=callback.from_user.id,
        text="❌ Ответ отменен"
    )

@router.message(AdminStates.waiting_reply)
async def process_reply_message(message: types.Message, state: FSMContext):
    """Обработка сообщения-ответа админа"""
    data = await state.get_data()
    user_id = data.get('reply_to_user')
    
    if not user_id:
        await state.clear()
        return
    
    reply_text = message.text.strip()
    
    try:
        await message.bot.send_message(
            chat_id=user_id,
            text=f"💬 <b>Сообщение от администратора:</b>\n\n{reply_text}",
            parse_mode="HTML"
        )
        
        await message.answer(f"✅ Отправлено пользователю {user_id}")
        
        # Удаляем уведомления другим администраторам
        try:
            from .utils import get_operator_notifications, delete_operator_notifications
            notifications = get_operator_notifications(user_id)
            if notifications:
                for adm_id, msg_id in list(notifications.items()):
                    try:
                        await safe_delete_message(message.bot, adm_id, msg_id)
                    except Exception:
                        pass
                delete_operator_notifications(user_id)
        except Exception:
            pass
        
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ["blocked", "deactivated", "not found"]):
            await message.answer(f"❌ Не удалось отправить пользователю {user_id}")
        else:
            await message.answer(f"❌ Ошибка: {str(e)[:50]}")
    
    await state.clear()


# ===== УПРАВЛЕНИЕ АДМИНАМИ =====

@router.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins_callback(callback: types.CallbackQuery):
    """Управление админами"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    admins = database.get_all_admins()
    
    text = f"""👥 <b>Управление администраторами</b>

<b>Всего админов:</b> {len(admins)}

<b>Список администраторов:</b>\n"""
    
    for admin_id in admins:
        user_data = database.get_user_data(admin_id)
        if user_data:
            name = user_data.get('full_name', f'Пользователь {admin_id}')
            username = user_data.get('username', '')
            text += f"\n• {name}"
            if username:
                text += f" (@{username})"
            text += f" - ID: <code>{admin_id}</code>"
        else:
            text += f"\n• ID: <code>{admin_id}</code>"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin")],
        [types.InlineKeyboardButton(text="❌ Удалить админа", callback_data="admin_remove_admin")],
        [types.InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    """Добавление админа"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = """➕ <b>Добавление администратора</b>

Введите ID пользователя, которого хотите сделать администратором:

<i>Пример: 123456789</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_manage_admins")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.update_data(admin_action='add')
    await state.set_state(AdminStates.waiting_admin_id)

@router.callback_query(F.data == "admin_remove_admin")
async def admin_remove_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    """Удаление админа"""
    await callback.answer()
    
    if not is_admin_fast(callback.from_user.id):
        return
    
    text = """❌ <b>Удаление администратора</b>

Введите ID пользователя, которого хотите удалить из администраторов:

<i>Пример: 123456789</i>"""
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_manage_admins")]
    ])
    
    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.update_data(admin_action='remove')
    await state.set_state(AdminStates.waiting_admin_id)

@router.message(AdminStates.waiting_admin_id)
async def process_admin_id(message: types.Message, state: FSMContext):
    """Обработка ID админа"""
    if not is_admin_fast(message.from_user.id):
        return
    
    try:
        admin_id = int(message.text.strip())
        data = await state.get_data()
        action = data.get('admin_action')
        
        if action == 'add':
            success = database.add_admin(admin_id)
            if success:
                admin_cache[admin_id] = True
                text = f"✅ <b>Администратор добавлен!</b>\n\nID: <code>{admin_id}</code>"
                try:
                    await safe_send_message(message.bot, admin_id, "🔑 Вас добавили в администраторы бота. Используйте /admin для входа.")
                except:
                    pass
            else:
                text = f"❌ <b>Не удалось добавить администратора</b>\n\nВозможно, он уже в списке."
        else:  # remove
            success = database.remove_admin(admin_id)
            if success:
                if admin_id in admin_cache:
                    del admin_cache[admin_id]
                text = f"✅ <b>Администратор удалён!</b>\n\nID: <code>{admin_id}</code>"
                try:
                    await safe_send_message(message.bot, admin_id, "ℹ️ Ваши права администратора отозваны.")
                except:
                    pass
            else:
                text = f"❌ <b>Не удалось удалить администратора</b>\n\nВозможно, его нет в списке."
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="👥 Список админов", callback_data="admin_manage_admins")],
            [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
        ])

        await update_message(message.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)

    except ValueError:
        await update_message(message.from_user.id,
                           "❌ <b>Неверный формат!</b>\n\nВведите числовой ID.",
                           parse_mode="HTML",
                           bot=message.bot)
        return

    await state.clear()

# ===== УПРАВЛЕНИЕ СИСТЕМНЫМИ ПРОМПТАМИ =====

@router.callback_query(F.data == "admin_system_prompts")
async def admin_system_prompts_callback(callback: types.CallbackQuery, state: FSMContext):
    """Управление системными промптами"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # ОЧИЩАЕМ ВСЕ СОСТОЯНИЯ ПРОМПТОВ ПРИ ВХОДЕ В МЕНЮ
    await state.clear()

    text = """🤖 <b>Управление системными промптами</b>

Здесь вы можете управлять системными промптами AI-ассистента ресторана.

<b>📝 Основной промпт</b> - определяет поведение бота при общении с пользователями:
• Отвечает на вопросы о меню и ресторане
• Обрабатывает заказы и бронирования
• Предоставляет информацию о блюдах

<b>🎭 Промпт персонажей</b> - управляет генерацией изображений знаменитостей:
• Определяет, когда показывать персонажей
• Настраивает стиль и качество изображений
• Контролирует ответы на вопросы о знаменитостях

<b>⚠️ Важные предупреждения:</b>
• Изменения вступают в силу после перезапуска бота
• Рекомендуется делать резервные копии промптов
• Неправильные промпты могут нарушить работу бота
• Максимальная длина промпта: 4000 символов"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📝 Основной промпт", callback_data="edit_main_prompt")],
        [types.InlineKeyboardButton(text="📥 Скачать основной промпт", callback_data="download_main_prompt")],
        [types.InlineKeyboardButton(text="🎭 Промпт персонажей", callback_data="edit_character_prompt")],
        [types.InlineKeyboardButton(text="📥 Скачать промпт персонажей", callback_data="download_character_prompt")],
        [types.InlineKeyboardButton(text="📤 Загрузить промпт", callback_data="upload_prompt")],
        [types.InlineKeyboardButton(text="📋 Просмотр промптов", callback_data="view_prompts")],
        [types.InlineKeyboardButton(text="🖼️ Управление фото столов", callback_data="manage_table_photos")],
        [types.InlineKeyboardButton(text="🔄 Сброс к умолчанию", callback_data="reset_prompts")],
        [types.InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_back")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "admin_chat_management")
async def admin_chat_management_callback(callback: types.CallbackQuery):
    """Открытие управления чатами"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Получаем все чаты из базы данных
    chats = database.get_all_chats_for_admin()

    text = f"""💬 <b>Управление чатами пользователей</b>

<b>Найдено чатов:</b> {len(chats)}
<b>Активных:</b> {sum(1 for c in chats if c.get('status') == 'active')}

<b>Варианты открытия миниаппа:</b>

1. <b>GitHub Pages</b> (продакшен) - https://strdr1.github.io/Admin-app/
2. <b>Локальный сервер</b> - для тестирования

<i>📱 Миниапп показывает реальные чаты из базы данных в реальном времени</i>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🌐 ОТКРЫТЬ МИНИАПП (GitHub Pages)", url="https://strdr1.github.io/Admin-app/")],
        [types.InlineKeyboardButton(text="🏠 ЛОКАЛЬНЫЙ СЕРВЕР (для тестов)", url="http://localhost:8080/")],
        [types.InlineKeyboardButton(text="📊 СТАТИСТИКА ЧАТОВ", callback_data="admin_chat_stats")],
        [types.InlineKeyboardButton(text="⬅️ НАЗАД В АДМИНКУ", callback_data="admin_back")]
    ])

    try:
        await callback.bot.edit_message_text(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования в admin_chat_management_callback: {e}")
        await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

@router.callback_query(F.data == "admin_chat_stats")
async def admin_chat_stats_callback(callback: types.CallbackQuery):
    """Статистика чатов"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    stats = database.get_chat_stats()

    text = f"""📊 <b>Статистика чатов</b>

<b>Всего чатов:</b> {stats.get('total_chats', 0)}
<b>Активных чатов:</b> {stats.get('active_chats', 0)}
<b>Завершенных:</b> {stats.get('completed_chats', 0)}
<b>Приостановленных:</b> {stats.get('paused_chats', 0)}

<b>Сообщения:</b>
• Всего: {stats.get('total_messages', 0)}
• От пользователей: {stats.get('user_messages', 0)}
• От админов: {stats.get('admin_messages', 0)}

<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💬 УПРАВЛЕНИЕ ЧАТАМИ", callback_data="admin_chat_management")],
        [types.InlineKeyboardButton(text="⬅️ НАЗАД В АДМИНКУ", callback_data="admin_back")]
    ])

    try:
        await callback.bot.edit_message_text(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования в admin_chat_stats_callback: {e}")
        await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

@router.callback_query(F.data == "admin_back")
async def admin_back_callback_fix(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Назад в админку' - сбрасывает состояния промптов"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Сбрасываем ВСЕ состояния промптов при выходе из меню
    await state.clear()

    text = """🛠️ <b>Админ-панель ресторана</b>

Выберите раздел для управления:"""

    try:
        await callback.bot.edit_message_text(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=keyboards.admin_menu(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования в admin_back_callback_fix: {e}")
        await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text=text,
            reply_markup=keyboards.admin_menu(),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "edit_main_prompt")
async def edit_main_prompt_callback(callback: types.CallbackQuery, state: FSMContext):
    """Редактирование основного системного промпта"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Получаем текущий основной промпт
    current_prompt = database.get_setting('main_system_prompt', '')

    if not current_prompt:
        # Если промпт не задан, берем из кода
        current_prompt = "Ты AI-помощник бота ресторана Mashkov. Отвечай просто и красиво, БЕЗ звездочек и маркдауна."

    text = f"""📝 <b>Редактирование основного системного промпта</b>

<b>Текущий промпт:</b>
<pre>{current_prompt[:300]}{'...' if len(current_prompt) > 300 else ''}</pre>

<b>Введите новый системный промпт:</b>
<i>Максимум 4000 символов</i>

<b>💡 Примеры настроек:</b>
• <code>Строгий режим</code> - более формальные ответы
• <code>Дружелюбный стиль</code> - разговорный тон
• <code>Минималистичный</code> - короткие ответы без эмодзи
• <code>Подробный</code> - развернутые объяснения

<i>Опишите желаемый стиль общения бота</i>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔄 Сброс к умолчанию", callback_data="reset_main_prompt")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_system_prompts")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

    await state.update_data(editing_prompt='main')
    await state.set_state(AdminStates.waiting_prompt_edit)

@router.callback_query(F.data == "edit_character_prompt")
async def edit_character_prompt_callback(callback: types.CallbackQuery, state: FSMContext):
    """Редактирование промпта персонажей"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Получаем текущий промпт персонажей
    current_prompt = database.get_setting('character_system_prompt', '')

    if not current_prompt:
        # Если промпт не задан, берем из кода
        current_prompt = "КРИТИЧЕСКИ ВАЖНО! Если пользователь спрашивает про необычных персонажей... (текст из кода)"

    text = f"""🎭 <b>Редактирование промпта персонажей</b>

<b>Текущий промпт:</b>
<pre>{current_prompt[:300]}{'...' if len(current_prompt) > 300 else ''}</pre>

<b>Введите новый промпт для персонажей:</b>
<i>Максимум 4000 символов</i>

<b>💡 Примеры настроек:</b>
• <code>Новогоднее настроение</code> - праздничный стиль, снег, подарки
• <code>Летний праздник</code> - яркие цвета, солнце, пляж
• <code>Минималистичный</code> - простые фоны, чистые линии
• <code>Фантастический</code> - яркие эффекты, магия, необычные элементы

<i>Опишите желаемый стиль и атмосферу для генерации изображений персонажей</i>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔄 Сброс к умолчанию", callback_data="reset_character_prompt")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_system_prompts")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

    await state.update_data(editing_prompt='character')
    await state.set_state(AdminStates.waiting_prompt_edit)

@router.callback_query(F.data == "view_prompts")
async def view_prompts_callback(callback: types.CallbackQuery):
    """Просмотр текущих промптов из файлов - показываем только дополнительные настройки"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    main_prompt = "⚪ <i>Используется по умолчанию</i>"
    character_prompt = "⚪ <i>Используется по умолчанию</i>"

    # Читаем дополнительные настройки из файлов
    try:
        if os.path.exists('main_prompt.txt'):
            with open('main_prompt.txt', 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    main_prompt = f"🟢 <b>Настроено:</b>\n<pre>{content[:150]}{'...' if len(content) > 150 else ''}</pre>"
    except Exception as e:
        logger.error(f"Ошибка чтения основного промпта: {e}")

    try:
        if os.path.exists('character_prompt.txt'):
            with open('character_prompt.txt', 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    character_prompt = f"🟢 <b>Настроено:</b>\n<pre>{content[:150]}{'...' if len(content) > 150 else ''}</pre>"
    except Exception as e:
        logger.error(f"Ошибка чтения промпта персонажей: {e}")

    text = f"""📋 <b>Дополнительные настройки промптов</b>

<i>Показаны только пользовательские настройки. Основной промпт AI остается неизменным.</i>

<b>📝 Основной промпт (дополнительно):</b>
{main_prompt}

<b>🎭 Промпт персонажей (дополнительно):</b>
{character_prompt}

<i>Эти настройки добавляются к базовым промптам AI</i>"""

@router.callback_query(F.data == "reset_all_additional_prompts")
async def reset_all_additional_prompts_callback(callback: types.CallbackQuery):
    """Сброс всех дополнительных промптов"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    text = """🔄 <b>Сброс дополнительных промптов</b>

⚠️ <b>ВНИМАНИЕ!</b> Это действие удалит все дополнительные настройки промптов и вернет AI к базовым настройкам.

<b>Файлы будут удалены:</b>
• main_prompt.txt
• character_prompt.txt

<b>Вы уверены?</b>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Да, сбросить", callback_data="confirm_reset_all_additional")],
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="view_prompts")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "confirm_reset_all_additional")
async def confirm_reset_all_additional_callback(callback: types.CallbackQuery):
    """Подтверждение сброса всех дополнительных промптов"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Удаляем файлы промптов
    files_deleted = []
    try:
        if os.path.exists('main_prompt.txt'):
            os.remove('main_prompt.txt')
            files_deleted.append('main_prompt.txt')
    except Exception as e:
        logger.error(f"Ошибка удаления main_prompt.txt: {e}")

    try:
        if os.path.exists('character_prompt.txt'):
            os.remove('character_prompt.txt')
            files_deleted.append('character_prompt.txt')
    except Exception as e:
        logger.error(f"Ошибка удаления character_prompt.txt: {e}")

    text = f"""✅ <b>Дополнительные промпты сброшены!</b>

<b>Удаленные файлы:</b>
{chr(10).join(f"• {file}" for file in files_deleted) if files_deleted else "• Нет файлов для удаления"}

AI теперь использует только базовые настройки промптов."""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Проверить статус", callback_data="view_prompts")],
        [types.InlineKeyboardButton(text="✏️ Настроить заново", callback_data="admin_system_prompts")],
        [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✏️ Редактировать", callback_data="admin_system_prompts")],
        [types.InlineKeyboardButton(text="🔄 Сбросить все", callback_data="reset_all_additional_prompts")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "reset_prompts")
async def reset_prompts_callback(callback: types.CallbackQuery):
    """Сброс всех промптов к умолчанию"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    text = """🔄 <b>Сброс промптов к умолчанию</b>

⚠️ <b>ВНИМАНИЕ!</b> Это действие сбросит все измененные системные промпты к значениям по умолчанию из кода.

<b>Вы уверены?</b>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Да, сбросить", callback_data="confirm_reset_prompts")],
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_system_prompts")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "confirm_reset_prompts")
async def confirm_reset_prompts_callback(callback: types.CallbackQuery):
    """Подтверждение сброса промптов"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Сбрасываем промпты
    database.delete_setting('main_system_prompt')
    database.delete_setting('character_system_prompt')

    text = """✅ <b>Промпты сброшены к умолчанию!</b>

Все системные промпты возвращены к значениям по умолчанию из кода бота."""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Просмотр промптов", callback_data="view_prompts")],
        [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "reset_main_prompt")
async def reset_main_prompt_callback(callback: types.CallbackQuery, state: FSMContext):
    """Сброс основного промпта"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    database.delete_setting('main_system_prompt')

    text = """✅ <b>Основной промпт сброшен к умолчанию!</b>

Промпт возвращен к значению по умолчанию из кода бота."""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📝 Редактировать снова", callback_data="edit_main_prompt")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_system_prompts")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data == "reset_character_prompt")
async def reset_character_prompt_callback(callback: types.CallbackQuery, state: FSMContext):
    """Сброс промпта персонажей"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Удаляем настройку из базы данных
    database.delete_setting('character_system_prompt')

    # Удаляем файл с промптом, если он существует
    try:
        if os.path.exists('character_prompt.txt'):
            os.remove('character_prompt.txt')
            logger.info("Файл character_prompt.txt удален при сбросе к умолчанию")
    except Exception as e:
        logger.error(f"Ошибка удаления character_prompt.txt: {e}")

    text = """✅ <b>Промпт персонажей сброшен к умолчанию!</b>

Промпт возвращен к значению по умолчанию из кода бота.
Файл character_prompt.txt также удален."""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🎭 Редактировать снова", callback_data="edit_character_prompt")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_system_prompts")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

# Обработчик сохранения промпта (используем состояние waiting_reply)
@router.message(AdminStates.waiting_reply)
async def save_system_prompt(message: types.Message, state: FSMContext):
    """Сохранение измененного системного промпта"""
    if not is_admin_fast(message.from_user.id):
        return

    data = await state.get_data()
    prompt_type = data.get('editing_prompt')

    if not prompt_type:
        await state.clear()
        return

    new_prompt = message.text.strip()

    if len(new_prompt) > 4000:
        await update_message(message.from_user.id,
                           "❌ <b>Промпт слишком длинный!</b>\n\nМаксимум 4000 символов.",
                           parse_mode="HTML",
                           bot=message.bot)
        return

    # Сохраняем промпт
    setting_key = f"{prompt_type}_system_prompt"
    database.update_setting(setting_key, new_prompt)

    prompt_name = "основной" if prompt_type == 'main' else "персонажей"

    text = f"""✅ <b>Промпт {prompt_name} успешно сохранен!</b>

<b>Новый промпт:</b>
<pre>{new_prompt[:200]}{'...' if len(new_prompt) > 200 else ''}</pre>

Изменения вступят в силу при следующем перезапуске бота или через некоторое время."""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Просмотр всех промптов", callback_data="view_prompts")],
        [types.InlineKeyboardButton(text="✏️ Редактировать еще", callback_data="admin_system_prompts")],
        [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
    ])

    await update_message(message.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=message.bot)

    await state.clear()

@router.message(AdminStates.waiting_prompt_edit)
async def save_system_prompt_edit(message: types.Message, state: FSMContext):
    """Сохранение измененного системного промпта в файл"""
    if not is_admin_fast(message.from_user.id):
        return

    data = await state.get_data()
    prompt_type = data.get('editing_prompt')

    if not prompt_type:
        await state.clear()
        return

    new_prompt = message.text.strip()

    if len(new_prompt) > 4000:
        await update_message(message.from_user.id,
                           "❌ <b>Промпт слишком длинный!</b>\n\nМаксимум 4000 символов.",
                           parse_mode="HTML",
                           bot=message.bot)
        return

    # Сохраняем промпт в файл
    filename = f"{prompt_type}_prompt.txt"
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(new_prompt)

        # Также сохраняем в базе данных как резервная копия
        setting_key = f"{prompt_type}_system_prompt"
        database.update_setting(setting_key, new_prompt)

        prompt_name = "основной" if prompt_type == 'main' else "персонажей"

        text = f"""✅ <b>Промпт {prompt_name} успешно сохранен!</b>

<b>Файл:</b> <code>{filename}</code>
<b>Новый промпт:</b>
<pre>{new_prompt[:200]}{'...' if len(new_prompt) > 200 else ''}</pre>

Изменения вступят в силу немедленно!"""

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📋 Просмотр всех промптов", callback_data="view_prompts")],
            [types.InlineKeyboardButton(text="✏️ Редактировать еще", callback_data="admin_system_prompts")],
            [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
        ])

        await update_message(message.from_user.id, text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            bot=message.bot)

    except Exception as e:
        logger.error(f"Ошибка сохранения промпта в файл: {e}")
        await update_message(message.from_user.id,
                           f"❌ <b>Ошибка сохранения файла!</b>\n\n{str(e)}",
                           parse_mode="HTML",
                           bot=message.bot)

    await state.clear()

# ===== ОБРАБОТЧИКИ СКАЧИВАНИЯ И ЗАГРУЗКИ ПРОМПТОВ =====

@router.callback_query(F.data == "download_main_prompt")
async def download_main_prompt_callback(callback: types.CallbackQuery):
    """Скачивание основного системного промпта из файла txt"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Читаем промпт из файла
    current_prompt = ""
    try:
        if os.path.exists('main_prompt.txt'):
            with open('main_prompt.txt', 'r', encoding='utf-8') as f:
                current_prompt = f.read().strip()
    except Exception as e:
        logger.error(f"Ошибка чтения основного промпта из файла: {e}")

    if not current_prompt:
        # Если файл не существует или пустой, берем из базы данных или по умолчанию
        current_prompt = database.get_setting('main_system_prompt', '')
        if not current_prompt:
            current_prompt = "Ты AI-помощник бота ресторана Mashkov. Отвечай просто и красиво, БЕЗ звездочек и маркдауна."

    # Создаем файл в памяти
    import io
    file_content = current_prompt.encode('utf-8')

    # Отправляем файл пользователю
    try:
        await callback.bot.send_document(
            chat_id=callback.from_user.id,
            document=types.BufferedInputFile(
                file_content,
                filename="main_system_prompt.txt"
            ),
            caption="📝 Основной системный промпт"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки файла основного промпта: {e}")
        await callback.answer("❌ Ошибка отправки файла!", show_alert=True)

@router.callback_query(F.data == "download_character_prompt")
async def download_character_prompt_callback(callback: types.CallbackQuery):
    """Скачивание промпта персонажей из файла txt"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    # Читаем промпт из файла
    current_prompt = ""
    try:
        if os.path.exists('character_prompt.txt'):
            with open('character_prompt.txt', 'r', encoding='utf-8') as f:
                current_prompt = f.read().strip()
    except Exception as e:
        logger.error(f"Ошибка чтения промпта персонажей из файла: {e}")

    if not current_prompt:
        # Если файл не существует или пустой, берем из базы данных или по умолчанию
        current_prompt = database.get_setting('character_system_prompt', '')
        if not current_prompt:
            current_prompt = """КРИТИЧЕСКИ ВАЖНО! Если пользователь спрашивает про любых персонажей, знаменитостей или людей (Дедпул, Человек-паук, Наруто, Мстители, Железный человек, Тор, Халк, Энштейн, Ксения Собчак, Маколей Калкин, супергерои, киногерои, аниме персонажи, исторические личности, актеры, музыканты и т.д.), ты ОБЯЗАН отвечать ТОЛЬКО УТВЕРДИТЕЛЬНО с юмором!

СТРОГО ЗАПРЕЩЕНО использовать эти фразы:
❌ 'нет' ❌ 'не видели' ❌ 'у нас нет' ❌ 'не переживайте' ❌ 'если появится'
❌ 'не бывал' ❌ 'не заходил' ❌ 'кто знает' ❌ 'может быть' ❌ 'может он'
❌ 'не видно' ❌ 'не появился' ❌ 'если вдруг' ❌ 'точно у нас не'

ОБЯЗАТЕЛЬНО используй ТОЛЬКО эти фразы:
✅ 'Да!' ✅ 'Конечно!' ✅ 'Вот он!' ✅ 'Он уже здесь!' ✅ 'Да, он тут!'
✅ 'Сидит за столиком!' ✅ 'Вот они сидят!' ✅ 'Они уже здесь!'

ВАЖНО! ИМЯ ПЕРСОНАЖА ДОЛЖНО БЫТЬ ТОЧНО КАК В ЗАПРОСЕ ПОЛЬЗОВАТЕЛЯ! НЕ ПЕРЕВОДИ И НЕ ИЗМЕНЯЙ ИМЯ!
Примеры:
- Пользователь сказал 'Маколей Калкин' -> используй 'Маколей Калкин'
- Пользователь сказал 'Iron Man' -> используй 'Iron Man'
- Пользователь сказал 'Дедпул' -> используй 'Дедпул'

ФОРМАТ ОТВЕТА (СТРОГО СЛЕДУЙ ЭТОМУ ШАБЛОНУ):
Шаг 1: Начни с УТВЕРДИТЕЛЬНОЙ фразы: 'Да! Вот он сидит за столом...' или 'Конечно! Вот они уже здесь...'
Шаг 2: Добавь название блюда из меню: '...и уже ждет нашу Пиццу Пепперони!'
Шаг 3: Предложи заказать: 'Хотите тоже попробовать?' или 'Присоединяйтесь!'
Шаг 4: ОБЯЗАТЕЛЬНО добавь: GEN_IMAGE:ПЕРСОНАЖ + описание на английском
Шаг 5: ОБЯЗАТЕЛЬНО добавь: SHOW_DELIVERY_BUTTON

ФОРМАТ GEN_IMAGE:
GEN_IMAGE:[персонаж] sitting on couch at center table near window in cozy restaurant hall, realistic photo, detailed interior, warm lighting

ПРИМЕРЫ:
- Дедпул -> 'Да! Вот он сидит за столом и уже ждет нашу Пиццу Пепперони! Хотите тоже попробовать?' GEN_IMAGE:Дедпул sitting on couch at center table near window in cozy restaurant hall, realistic photo, detailed interior, warm lighting SHOW_DELIVERY_BUTTON
- Маколей Калкин -> 'Да! Вот он сидит за столиком и ждет нашу Пиццу Маргарита! Присоединяйтесь!' GEN_IMAGE:Маколей Калкин sitting on couch at center table near window in cozy restaurant hall, realistic photo, detailed interior, warm lighting SHOW_DELIVERY_BUTTON
- Iron Man -> 'Конечно! Вот он ждет наш фирменный Стейк! Хотите тоже попробовать?' GEN_IMAGE:Iron Man sitting on couch at center table near window in modern restaurant hall, realistic photo, detailed interior, warm lighting SHOW_DELIVERY_BUTTON
- Мстители -> 'Да! Вот они сидят за большим столом и ждут наши фирменные блюда! Присоединяйтесь к команде!' GEN_IMAGE:Мстители sitting together at center table near window in cozy restaurant hall, realistic photo, detailed interior, warm lighting SHOW_DELIVERY_BUTTON

КЛЮЧЕВЫЕ ФРАЗЫ:
- sitting on couch (сидит на диване)
- at center table (за центральным столом)
- near window (около окна)
- in restaurant hall/interior (в зале ресторана)
- realistic photo, detailed interior (реалистичное фото, детальный интерьер)
- warm lighting (теплое освещение)"""

    # Создаем файл в памяти
    import io
    file_content = current_prompt.encode('utf-8')

    # Отправляем файл пользователю
    try:
        await callback.bot.send_document(
            chat_id=callback.from_user.id,
            document=types.BufferedInputFile(
                file_content,
                filename="character_system_prompt.txt"
            ),
            caption="🎭 Промпт персонажей"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки файла промпта персонажей: {e}")
        await callback.answer("❌ Ошибка отправки файла!", show_alert=True)

@router.callback_query(F.data == "upload_prompt")
async def upload_prompt_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало загрузки промпта из txt файла"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    text = """📤 <b>Загрузка системного промпта</b>

Пожалуйста, отправьте текстовый файл (.txt) с новым промптом.

<b>Требования:</b>
• Формат: TXT (.txt)
• Максимальный размер: 100 KB
• Кодировка: UTF-8

<b>Выберите тип промпта для замены:</b>"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📝 Основной промпт", callback_data="upload_main_prompt")],
        [types.InlineKeyboardButton(text="🎭 Промпт персонажей", callback_data="upload_character_prompt")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_system_prompts")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)

@router.callback_query(F.data.startswith("upload_"))
async def upload_prompt_type_callback(callback: types.CallbackQuery, state: FSMContext):
    """Выбор типа промпта для загрузки"""
    await callback.answer()

    if not is_admin_fast(callback.from_user.id):
        return

    prompt_type = callback.data.replace("upload_", "")
    
    if prompt_type == "main_prompt":
        prompt_name = "основного"
        state_data = "main"
    else:  # character_prompt
        prompt_name = "персонажей"
        state_data = "character"

    await state.update_data(uploading_prompt=state_data)

    text = f"""📤 <b>Загрузка {prompt_name} промпта</b>

Пожалуйста, отправьте текстовый файл (.txt) с новым промптом.

<b>Требования:</b>
• Формат: TXT (.txt)
• Максимальный размер: 100 KB
• Кодировка: UTF-8"""

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="upload_prompt")]
    ])

    await update_message(callback.from_user.id, text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        bot=callback.bot)
    
    await state.set_state(AdminStates.waiting_prompt_upload)

@router.message(AdminStates.waiting_prompt_upload, F.document)
async def handle_prompt_upload(message: types.Message, state: FSMContext):
    """Обработка загрузки промпта из txt файла"""
    if not is_admin_fast(message.from_user.id):
        return

    document = message.document

    # Проверяем формат
    if not document.mime_type == 'text/plain' and not document.file_name.endswith('.txt'):
        await update_message(message.from_user.id,
                           "❌ <b>Неверный формат файла!</b>\n\nПожалуйста, отправьте текстовый файл (.txt).",
                           parse_mode="HTML",
                           bot=message.bot)
        return

    # Проверяем размер
    if document.file_size > 100 * 1024:  # 100 KB
        await update_message(message.from_user.id,
                           "❌ <b>Файл слишком большой!</b>\n\nМаксимальный размер: 100 KB.",
                           parse_mode="HTML",
                           bot=message.bot)
        return

    try:
        # Скачиваем файл
        file = await message.bot.get_file(document.file_id)
        file_path = file.file_path

        # Скачиваем содержимое файла
        downloaded_file = await message.bot.download_file(file_path)
        file_content = downloaded_file.read()
        downloaded_file.close()

        # Декодируем содержимое
        try:
            new_prompt = file_content.decode('utf-8')
        except UnicodeDecodeError:
            await update_message(message.from_user.id,
                               "❌ <b>Ошибка кодировки!</b>\n\nФайл должен быть в кодировке UTF-8.",
                               parse_mode="HTML",
                               bot=message.bot)
            return

        # Проверяем длину
        if len(new_prompt) > 4000:
            await update_message(message.from_user.id,
                               "❌ <b>Промпт слишком длинный!</b>\n\nМаксимум 4000 символов.",
                               parse_mode="HTML",
                               bot=message.bot)
            return

        # Получаем тип промпта из состояния
        data = await state.get_data()
        prompt_type = data.get('uploading_prompt', 'main')
        setting_key = f"{prompt_type}_system_prompt"

        # Сохраняем промпт
        database.update_setting(setting_key, new_prompt)

        prompt_name = "основного" if prompt_type == 'main' else "персонажей"

        text = f"""✅ <b>Промпт {prompt_name} успешно загружен!</b>

<b>Новый промпт:</b>
<pre>{new_prompt[:200]}{'...' if len(new_prompt) > 200 else ''}</pre>

Изменения вступят в силу при следующем перезапуске бота или через некоторое время."""

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📋 Просмотр всех промптов", callback_data="view_prompts")],
            [types.InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]
        ])

        await update_message(message.from_user.id, text,
                           reply_markup=keyboard,
                           parse_mode="HTML",
                           bot=message.bot)

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка загрузки промпта: {e}")
        await update_message(message.from_user.id,
                           "❌ <b>Ошибка загрузки файла!</b>\n\nПопробуйте еще раз.",
                           parse_mode="HTML",
                           bot=message.bot)

# ===== ОБРАБОТЧИК ДАННЫХ ОТ МИНИАППА =====

@router.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    """Обработка данных от Telegram Web App (миниаппа)"""
    user_id = message.from_user.id
    logger.info(f"Получены данные от миниаппа от пользователя {user_id}")

    try:
        # Получаем данные от миниаппа
        web_app_data = message.web_app_data.data
        logger.info(f"Сырые данные от миниаппа: {web_app_data}")

        data = json.loads(web_app_data)
        logger.info(f"Распарсенные данные: {data}")

        if data.get('action') == 'send_admin_message':
            logger.info("Обработка действия send_admin_message")

            chat_id = data.get('chatId')
            admin_message = data.get('message')

            logger.info(f"chat_id: {chat_id}, admin_message: {admin_message}")

            if not chat_id or not admin_message:
                logger.error("Отсутствует chat_id или admin_message")
                await safe_send_message(message.bot, user_id, "❌ Неполные данные для отправки сообщения")
                return

            # Получаем информацию о чате
            logger.info(f"Получаем информацию о чате {chat_id}")
            chat_info = database.get_chat_by_id(chat_id)
            if not chat_info:
                logger.error(f"Чат {chat_id} не найден в базе данных")
                await safe_send_message(message.bot, user_id, f"❌ Чат не найден (ID: {chat_id})")
                return

            user_chat_id = chat_info.get('user_id')
            user_name = chat_info.get('user_name', f'Пользователь {user_chat_id}')

            logger.info(f"Отправляем сообщение пользователю {user_chat_id} ({user_name})")

            # Отправляем сообщение пользователю
            try:
                send_result = await safe_send_message(message.bot, user_chat_id, admin_message)
                if send_result:
                    logger.info(f"Сообщение успешно отправлено пользователю {user_chat_id}")
                else:
                    logger.error(f"safe_send_message вернул None для пользователя {user_chat_id}")
                    await safe_send_message(message.bot, user_id,
                                           f"❌ Не удалось отправить сообщение пользователю {user_name}")
                    return

                # Сохраняем сообщение админа в базу данных
                logger.info(f"Сохраняем сообщение в базу данных")
                database.save_chat_message(chat_id, 'admin', admin_message)

                await safe_send_message(message.bot, user_id,
                                       f"✅ Сообщение отправлено пользователю {user_name}")

                logger.info(f"Админ {user_id} успешно отправил сообщение в чат {chat_id}: {admin_message}")

            except Exception as e:
                logger.error(f"Ошибка отправки сообщения в чат {chat_id}: {e}")
                await safe_send_message(message.bot, user_id,
                                       f"❌ Ошибка отправки сообщения пользователю {user_name}: {str(e)}")

        else:
            logger.warning(f"Неизвестное действие: {data.get('action')}")
            await safe_send_message(message.bot, user_id, f"❌ Неизвестное действие: {data.get('action')}")

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON данных от миниаппа: {e}, сырые данные: {web_app_data}")
        await safe_send_message(message.bot, message.from_user.id,
                               "❌ Ошибка обработки данных от миниаппа (неправильный JSON)")
    except Exception as e:
        logger.error(f"Ошибка обработки web_app_data: {e}")
        await safe_send_message(message.bot, message.from_user.id,
                               f"❌ Произошла ошибка при обработке данных: {str(e)}")
