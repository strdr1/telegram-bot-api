#!/usr/bin/env python3
"""
Автоматическое обновление меню из Presto API
Запускается ежедневно в 4:00 утра через cron
"""
import asyncio
import sys
import os
import json
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
        from presto_api import PrestoAPI
        from debug_context import generate_context

        # 1. Загружаем последнее сохраненное состояние (snapshot)
        last_snapshot = database.get_last_menu_snapshot()
        old_menu_data = json.loads(last_snapshot['menu_data']) if last_snapshot else {}

        # 2. Обновляем меню с принудительной перезагрузкой
        menus = await menu_cache.load_all_menus(force_update=True)

        if menus:
            total_items = 0
            for menu_id, menu_data in menus.items():
                for cat_id, cat_data in menu_data.get('categories', {}).items():
                    total_items += len(cat_data.get('items', []))

            # 3. Сравниваем меню
            comparison = PrestoAPI.compare_menus(old_menu_data, menus)
            
            # 4. Проверяем порог изменений
            threshold_str = database.get_setting('menu_change_threshold')
            threshold = float(threshold_str) if threshold_str else 15.0
            
            is_significant = comparison['change_percent'] >= threshold
            comparison['is_significant'] = is_significant
            
            # 5. Сохраняем новый snapshot
            # Сериализуем меню в JSON
            current_menu_json = json.dumps(menus, ensure_ascii=False)
            database.save_menu_snapshot(
                current_menu_json, 
                comparison['items_count'], 
                comparison['change_percent'], 
                is_significant
            )
            
            # 6. Обновляем контекст AI
            print("🧠 Обновляю контекст для AI...")
            generate_context()

            success_message = (
                f"✅ Меню успешно обновлено автоматически!\n\n"
                f"📊 Загружено {len(menus)} меню\n"
                f"🍽️ Всего позиций: {total_items}\n"
                f"📈 Изменения: {comparison['change_percent']}%\n"
                f"⚠️ Значительное обновление: {'Да' if is_significant else 'Нет'}\n"
                f"🕐 Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            print(success_message)

            # Логируем в базу данных
            database.log_action(
                0, 
                "auto_menu_update", 
                f"success: items={total_items}, change={comparison['change_percent']}%, significant={is_significant}"
            )

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
