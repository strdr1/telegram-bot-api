#!/usr/bin/env python3
"""
Автоматическое обновление меню из Presto API
Запускается ежедневно в 4:00 утра через cron
"""
import asyncio
import sys
import os
from datetime import datetime

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def auto_update_menu():
    """Автоматическое обновление меню"""
    print(f"🔄 Начинаю автоматическое обновление меню в {datetime.now().strftime('%H:%M:%S')}")

    try:
        # Импортируем необходимые модули
        from menu_cache import menu_cache
        import database

        # Обновляем меню с принудительной перезагрузкой
        menus = await menu_cache.load_all_menus(force_update=True)

        if menus:
            total_items = 0
            for menu_id, menu_data in menus.items():
                for cat_id, cat_data in menu_data.get('categories', {}).items():
                    total_items += len(cat_data.get('items', []))

            success_message = (
                f"✅ Меню успешно обновлено автоматически!\n\n"
                f"📊 Загружено {len(menus)} меню\n"
                f"🍽️ Всего позиций: {total_items}\n\n"
                f"🕐 Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            print(success_message)

            # Логируем в базу данных
            database.log_action(0, "auto_menu_update", f"success: {len(menus)} menus, {total_items} items")

            

        else:
            error_message = "❌ Ошибка автоматического обновления меню - не удалось загрузить меню из Presto API"
            print(error_message)

            # Логируем ошибку
            database.log_action(0, "auto_menu_update", "error: failed to load menus")

            

    except Exception as e:
        error_message = f"❌ Критическая ошибка автоматического обновления меню: {str(e)}"
        print(error_message)

        # Логируем критическую ошибку
        try:
            import database
            database.log_action(0, "auto_menu_update", f"critical_error: {str(e)}")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(auto_update_menu())
