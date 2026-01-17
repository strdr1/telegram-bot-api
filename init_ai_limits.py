"""
Скрипт для инициализации таблицы лимитов AI генераций
"""
import sqlite3

def init_ai_limits_table():
    """Создание таблицы ai_generations если её нет"""
    try:
        conn = sqlite3.connect('restaurant.db')
        cursor = conn.cursor()
        
        # Создаем таблицу
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_generations (
            user_id INTEGER NOT NULL,
            generation_date TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, generation_date)
        )
        ''')
        
        conn.commit()
        conn.close()
        
        print("[OK] Таблица ai_generations успешно создана!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Ошибка при создании таблицы: {e}")
        return False

if __name__ == "__main__":
    init_ai_limits_table()
