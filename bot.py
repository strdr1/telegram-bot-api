# -*- coding: utf-8 -*-
"""
bot.py - ИСПРАВЛЕННЫЙ (с личным кабинетом)
"""

import asyncio
import logging
import sys
import os

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

                logger.info(f"Отправка сообщения из очереди: chat {chat_id}, message_id {message_id}")

                # Отправляем сообщение пользователю
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
    
    # Регистрация всех обработчиков в правильном порядке
    # Важен порядок! Сначала общие, потом конкретные
    dp.include_router(registration_router)
    dp.include_router(admin_router)  # <-- АДМИН РОУТЕР ПЕРВЫМ
    dp.include_router(main_router)
    dp.include_router(delivery_router)
    dp.include_router(booking_router)
    dp.include_router(personal_cabinet_router)  # <-- ДОБАВИТЬ ПЕРЕД АДМИНКОЙ
    
    # Регистрируем обработчик ошибок
    dp.errors.register(error_handler)

    # Запускаем фоновую задачу для обработки сообщений из миниаппа
    message_queue_task = asyncio.create_task(process_message_queue(bot))
    print("📨 Фоновая задача обработки сообщений миниаппа запущена")

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
    
    try:
        # Запускаем бота
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
