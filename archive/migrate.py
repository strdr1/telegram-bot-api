"""
migrate.py
Миграция базы данных - добавление новых колонок
"""

import sqlite3
import os

def migrate_database():
    """Миграция базы данных"""
    print("🔄 Начинаем миграцию базы данных...")
    
    if not os.path.exists('restaurant.db'):
        print("❌ База данных не найдена! Создайте ее сначала запустив бота.")
        return
    
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    
    try:
        # Проверяем наличие колонок в таблице users
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"Текущие колонки в таблице users: {columns}")
        
        # Добавляем недостающие колонки
        if 'registration_step' not in columns:
            print("➕ Добавляем колонку registration_step...")
            cursor.execute('ALTER TABLE users ADD COLUMN registration_step TEXT DEFAULT "phone"')
        
        if 'registered_at' not in columns:
            print("➕ Добавляем колонку registered_at...")
            cursor.execute('ALTER TABLE users ADD COLUMN registered_at TEXT DEFAULT CURRENT_TIMESTAMP')
        
        conn.commit()
        print("✅ Миграция успешно завершена!")
        
        # Проверяем результат
        cursor.execute("PRAGMA table_info(users)")
        new_columns = [column[1] for column in cursor.fetchall()]
        print(f"Новые колонки в таблице users: {new_columns}")
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
