"""
admin_fix.py
Исправление проблем с админкой
"""

import sqlite3
import sys

def check_admin(user_id):
    """Проверка админа напрямую в БД"""
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            print(f"✅ Пользователь {user_id} найден в таблице admins")
            return True
        else:
            print(f"❌ Пользователь {user_id} НЕ найден в таблице admins")
            return False
            
    except Exception as e:
        print(f"Ошибка: {e}")
        conn.close()
        return False

def add_admin_direct(user_id):
    """Добавление админа напрямую"""
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))
        conn.commit()
        print(f"✅ Пользователь {user_id} добавлен в админы")
        
        # Проверяем
        cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            print(f"✅ Подтверждено: пользователь {user_id} теперь админ")
        else:
            print(f"❌ Ошибка: пользователь {user_id} не добавился")
            
    except Exception as e:
        print(f"Ошибка добавления: {e}")
    finally:
        conn.close()

def list_all_admins():
    """Список всех админов"""
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT user_id, added_at FROM admins ORDER BY added_at')
        admins = cursor.fetchall()
        
        if admins:
            print("\n📋 Список всех админов:")
            for user_id, added_at in admins:
                print(f"• ID: {user_id}, добавлен: {added_at}")
        else:
            print("\n❌ В базе нет админов!")
            
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("🔧 Проверка и исправление админки")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        user_id = int(sys.argv[1])
        
        print(f"Проверяем пользователя {user_id}...")
        
        # Проверяем
        is_admin = check_admin(user_id)
        
        if not is_admin:
            answer = input(f"Добавить пользователя {user_id} в админы? (y/n): ")
            if answer.lower() == 'y':
                add_admin_direct(user_id)
    else:
        # Показываем всех админов
        list_all_admins()
        print("\nДля добавления админа запустите:")
        print(f"python admin_fix.py ВАШ_USER_ID")