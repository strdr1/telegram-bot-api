# -*- coding: utf-8 -*-
"""
bot.py - ИСПРАВЛЕННЫЙ (с личным кабинетом) + Webhook support
"""

import asyncio
import logging
import sys
import os
import re
from datetime import datetime
from aiohttp import web
from aiohttp.web_request import Request
from aiogram import types

# Настройка кодировки для Windows
if sys.platform == 'win32':
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_ALL, 'Russian_Russia.1251')
        except:
            pass
    
    # Устанавливаем UTF-8 для stdout/stderr
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
import config
from config import BOT_TOKEN, REQUEST_TIMEOUT

# Импортируем все роутеры
from handlers.handlers_main import router as main_router
from handlers.handlers_admin import router as admin_router
from handlers.handlers_booking import router as booking_router
from handlers.handlers_delivery import router as delivery_router
from handlers.handlers_registration import router as registration_router
from handlers.handlers_personal_cabinet import router as personal_cabinet_router  # <-- ДОБАВИТЬ ЭТО
from handlers.handlers_main import error_handler
from handlers.utils import TimeoutMiddleware
from handlers import handlers_main, handlers_booking, handlers_delivery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
import keyboards

import database
from menu_cache import menu_cache
from presto_api import presto_api
from cart_manager import cart_manager
import handlers.utils

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Глобальный диспетчер для webhook
dp = None

async def process_message_queue(bot):
    """Обработка очереди сообщений от миниаппа"""
    while True:
        try:
            # Получаем неотправленные сообщения от админа
            unsent_messages = database.get_unsent_admin_messages()

            for message in unsent_messages:
                chat_id = message['chat_id']
                message_text = message['message_text']
                message_id = message['id']
                file_path = message.get('file_path')  # Путь к файлу, если есть

                logger.info(f"Отправка сообщения из очереди: chat {chat_id}, message_id {message_id}, file: {file_path}")

                result = False
                
                # Проверяем, является ли сообщение командой
                if message_text and message_text.startswith("CMD:"):
                    command = message_text[4:].strip()
                    logger.info(f"Выполнение команды: {command} для пользователя {message['user_id']}")
                    
                    try:
                        if command == "/booking":
                            await handlers_booking.show_booking_options(message['user_id'], bot)
                            result = True
                        elif command == "/delivery":
                            # Меню доставки (Мини-приложение)
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
                            
                            await handlers_main.safe_send_message(bot, message['user_id'], text,
                                                reply_markup=keyboard, parse_mode="HTML")
                            result = True
                        elif command == "/menu":
                            # Меню ресторана (выбор: Доставка, PDF, Банкет)
                            await handlers_delivery.menu_food_handler(message['user_id'], bot)
                            result = True
                        elif command == "/bot_menu" or command == "/start":
                            # Главное меню бота (контакты, режим работы)
                            restaurant_name = database.get_setting('restaurant_name', config.RESTAURANT_NAME)
                            restaurant_phone = database.get_setting('restaurant_phone', config.RESTAURANT_PHONE)
                            restaurant_address = database.get_setting('restaurant_address', config.RESTAURANT_ADDRESS)
                            restaurant_hours = database.get_setting('restaurant_hours', config.RESTAURANT_HOURS)
                            
                            # Очистка телефона
                            clean_phone = ''.join(c for c in restaurant_phone if c.isdigit() or c == '+')
                            if clean_phone.startswith('8'):
                                clean_phone = '+7' + clean_phone[1:]
                            elif clean_phone.startswith('7') and not clean_phone.startswith('+7'):
                                clean_phone = '+7' + clean_phone[1:]
                            elif not clean_phone.startswith('+'):
                                clean_phone = '+7' + clean_phone
                            
                            text = f"""🍽️ <b>{restaurant_name}</b>

<b>Контакты:</b>
📍 {restaurant_address}
📞 <a href="tel:{clean_phone}">{restaurant_phone}</a>
🕐 {restaurant_hours}"""
                            
                            keyboard = keyboards.main_menu_with_profile(message['user_id'])
                            await handlers_main.safe_send_message(bot, message['user_id'], text,
                                                reply_markup=keyboard, parse_mode="HTML")
                            result = True
                        else:
                            logger.warning(f"Неизвестная команда: {command}")
                            # Если команда не распознана, логируем и помечаем как обработанное
                            result = True
                    except Exception as e:
                        logger.error(f"Ошибка выполнения команды {command}: {e}")
                        # Отмечаем как отправленное, чтобы не зацикливаться
                        result = True
                
                # Если есть файл, отправляем его (если это не команда)
                elif file_path and os.path.exists(file_path):
                    try:
                        # Определяем тип файла
                        file_ext = os.path.splitext(file_path)[1].lower()
                        
                        from aiogram.types import FSInputFile
                        
                        if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                            # Отправляем как фото
                            photo = FSInputFile(file_path)
                            result = await handlers.utils.safe_send_photo(bot, message['user_id'], photo, caption=message_text)
                        elif file_ext in ['.pdf', '.doc', '.docx', '.txt', '.xlsx', '.xls']:
                            # Отправляем как документ
                            document = FSInputFile(file_path)
                            result = await handlers.utils.safe_send_document(bot, message['user_id'], document, caption=message_text)
                        else:
                            # Отправляем как документ по умолчанию
                            document = FSInputFile(file_path)
                            result = await handlers.utils.safe_send_document(bot, message['user_id'], document, caption=message_text)
                                
                    except Exception as e:
                        logger.error(f"Ошибка отправки файла {file_path}: {e}")
                        # Если не удалось отправить файл, отправляем только текст
                        result = await handlers.utils.safe_send_message(bot, message['user_id'], message_text)
                else:
                    # Отправляем только текст
                    result = await handlers.utils.safe_send_message(bot, message['user_id'], message_text)

                if result:
                    # Отмечаем сообщение как отправленное
                    database.mark_message_sent(message_id)
                    logger.info(f"Сообщение {message_id} успешно отправлено пользователю {message['user_id']}")
                else:
                    logger.error(f"Не удалось отправить сообщение {message_id} пользователю {message['user_id']}")

            # Ждем 5 секунд перед следующей проверкой
            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Ошибка в process_message_queue: {e}")
            await asyncio.sleep(10)  # В случае ошибки ждем дольше

async def schedule_daily_menu_update():
    """Ежедневное обновление меню ровно в 09:00 по Москве"""
    tz = menu_cache.moscow_tz
    while True:
        try:
            now = datetime.now(tz)
            # Следующее обновление в 09:00
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if target <= now:
                # Если уже прошло — берем завтра
                from datetime import timedelta
                target = target + timedelta(days=1)
            # Сколько ждать до 09:00
            wait_seconds = (target - now).total_seconds()
            logger.info(f"Планируем обновление меню на {target.strftime('%Y-%m-%d %H:%M:%S %Z')}, подождем {int(wait_seconds)} сек.")
            await asyncio.sleep(wait_seconds)
            # Обновляем меню
            try:
                logger.info("🕘 09:00 МСК — выполняем обновление меню (force_update=True)")
                await menu_cache.load_all_menus(force_update=True)
                logger.info("✅ Меню обновлено успешно")
            except Exception as e:
                logger.error(f"Ошибка обновления меню в 09:00: {e}")
            # После обновления — планируем следующее через сутки
            await asyncio.sleep(24 * 60 * 60)
        except Exception as e:
            logger.error(f"Ошибка в планировщике ежедневного обновления меню: {e}")
            await asyncio.sleep(60)
async def load_presto_menus():
    """Загрузка всех меню и изображений из Presto API"""
    print("🔄 Загружаем меню и изображения из Presto API...")
    print("=" * 50)
    
    try:
        # Загружаем ВСЕ меню и изображения
        print("📥 Загружаем все меню (90, 92, 132)...")
        
        menus = await menu_cache.load_all_menus(force_update=True)
        
        if menus:
            print(f"✅ Загружено {len(menus)} меню:")
            for menu_id, menu_data in menus.items():
                categories_count = len(menu_data.get('categories', {}))
                total_items = sum(len(cat['items']) for cat in menu_data.get('categories', {}).values())
                print(f"   • {menu_data['name']}: {categories_count} категорий, {total_items} товаров")
            
            # Подсчитываем общее количество изображений
            total_images = 0
            for menu_id, menu_data in menus.items():
                for cat_id, cat_data in menu_data.get('categories', {}).items():
                    for dish in cat_data.get('items', []):
                        if dish.get('image_filename'):
                            total_images += 1
            
            print(f"\n🖼️ Всего изображений товаров: {total_images}")
            print("✅ Все меню и изображения загружены и готовы к работе!")
        else:
            print("⚠️ Не удалось загрузить меню")
            print("ℹ️  Меню будет недоступно")
            
    except Exception as e:
        print(f"❌ Ошибка при загрузке меню: {e}")
        import traceback
        traceback.print_exc()
        print("ℹ️  Меню будет недоступно")

async def shutdown(bot=None):
    """Корректное завершение работы"""
    print("\n🛑 Завершение работы...")
    
    # Закрываем сессию API
    try:
        await presto_api.close_session()
        print("✅ Сессия API закрыта")
    except Exception as e:
        print(f"⚠️ Ошибка закрытия сессии API: {e}")
    
    # Закрываем сессию бота если передана
    if bot:
        try:
            await bot.session.close()
            print("✅ Сессия бота закрыта")
        except Exception as e:
            print(f"⚠️ Ошибка закрытия сессии бота: {e}")
    
    # Закрываем соединения с БД
    try:
        database.close_all_connections()
        print("✅ Соединения с БД закрыты")
    except Exception as e:
        print(f"⚠️ Ошибка закрытия БД: {e}")

async def webhook_handler(request: Request, bot: Bot) -> web.Response:
    """Обработчик webhook от Telegram"""
    try:
        # Получаем данные от Telegram
        data = await request.json()
        
        # Создаем Update объект
        from aiogram.types import Update
        update = Update(**data)
        
        # Передаем в диспетчер
        await dp.feed_update(bot, update)
        
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка в webhook handler: {e}")
        return web.Response(status=500)

async def health_handler(request: Request) -> web.Response:
    """Health check endpoint"""
    return web.json_response({"status": "ok", "bot": "running"})

async def setup_webhook(bot: Bot):
    """Настройка webhook"""
    webhook_url = os.getenv('WEBHOOK_URL')
    if webhook_url:
        try:
            await bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "inline_query"]
            )
            logger.info(f"Webhook установлен: {webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки webhook: {e}")
            return False
    return False

async def main():
    """Основная функция запуска бота"""
    print("🤖 Бот запускается...")
    print("=" * 50)
    
    # Создаем сессию с таймаутами
    session = AiohttpSession(timeout=REQUEST_TIMEOUT)
    
    # Создаем бота с настройками
    default = DefaultBotProperties(
        parse_mode="HTML",
        link_preview_is_disabled=True,
        protect_content=False
    )
    
    bot = Bot(token=BOT_TOKEN, default=default, session=session)
    
    # Настройка диспетчера
    global dp
    dp = Dispatcher(storage=MemoryStorage())
    # Регистрируем middleware таймаута глобально (если поддерживается)
    try:
        if TimeoutMiddleware is not None:
            dp.message.middleware(TimeoutMiddleware())
            dp.callback_query.middleware(TimeoutMiddleware())
            print("🔒 Timeout middleware registered")
    except Exception as e:
        print(f"⚠️ Не удалось зарегистрировать TimeoutMiddleware: {e}")
    
    # Инициализация систем
    try:
        print("🔄 Инициализируем базу данных...")
        database.init_database()
        print("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        print(f"❌ Ошибка при инициализации БД: {e}")
    
    # Загрузка меню из Presto API
    await load_presto_menus()
    
    # Регистрация роутеров (ПОРЯДОК ВАЖЕН!)
    dp.include_router(registration_router)
    dp.include_router(personal_cabinet_router)
    dp.include_router(admin_router)
    dp.include_router(main_router)
    dp.include_router(delivery_router)
    dp.include_router(booking_router)
    
    # Регистрируем обработчик ошибок
    dp.errors.register(error_handler)

    # Запускаем фоновую задачу для обработки сообщений из миниаппа
    message_queue_task = asyncio.create_task(process_message_queue(bot))
    print("📨 Фоновая задача обработки сообщений миниаппа запущена")
    # Запускаем ежедневное обновление меню в 09:00
    daily_update_task = asyncio.create_task(schedule_daily_menu_update())
    print("🕘 Фоновая задача ежедневного обновления меню запущена")

    print("\n" + "=" * 50)
    print("✅ Все обработчики зарегистрированы")
    print("📊 Список роутеров:")
    print(f"   • Регистрация (/{registration_router.name})")
    print(f"   • Главное меню (/{main_router.name})")
    print(f"   • Доставка (/{delivery_router.name})")
    print(f"   • Бронирование (/{booking_router.name})")
    print(f"   • Личный кабинет (/{personal_cabinet_router.name})")  # <-- ДОБАВИТЬ
    print(f"   • Админка (/{admin_router.name})")
    print("🚀 Бот готов к работе!")
    print("=" * 50)
    
    # Проверяем режим работы (webhook или polling)
    webhook_mode = os.getenv('WEBHOOK_MODE', 'false').lower() == 'true'
    
    if webhook_mode:
        print("🌐 Запуск в режиме webhook...")
        
        # Настраиваем webhook
        webhook_success = await setup_webhook(bot)
        if not webhook_success:
            print("❌ Не удалось настроить webhook, переключаемся на polling")
            webhook_mode = False
    
    try:
        if webhook_mode:
            # Запуск webhook сервера
            app = web.Application()
            
            # Настраиваем обработчики
            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
            )
            webhook_requests_handler.register(app, path="/webhook")
            
            # Health check endpoint
            app.router.add_get("/health", health_handler)
            
            # Настраиваем приложение
            setup_application(app, dp, bot=bot)
            
            # Запускаем сервер
            port = int(os.getenv('WEBHOOK_PORT', 8000))
            print(f"🌐 Webhook сервер запускается на порту {port}")
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '127.0.0.1', port)
            await site.start()
            
            print(f"✅ Webhook сервер запущен на http://127.0.0.1:{port}")
            
            # Ждем завершения
            try:
                await asyncio.Future()  # run forever
            except KeyboardInterrupt:
                print("\n⏹️ Бот остановлен пользователем")
            finally:
                await runner.cleanup()
        else:
            # Запуск polling
            print("🔄 Запуск в режиме polling...")
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                polling_timeout=25,
                drop_pending_updates=True,
                close_bot_session=True,
            )
    except KeyboardInterrupt:
        print("\n⏹️ Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        print(f"❌ Критическая ошибка при запуске бота: {e}")
    finally:
        # Корректное завершение
        await shutdown(bot)
        print("✅ Все ресурсы освобождены")

if __name__ == "__main__":
    # Настраиваем event loop для Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()
