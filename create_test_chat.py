#!/usr/bin/env python3
"""
Создание тестового чата для проверки админ-панели
"""

import database
import datetime

def create_test_chat():
    """Создание тестового чата"""
    
    # Инициализируем базу данных
    database.init_database()
    
    # Создаем тестового пользователя
    test_user_id = 123456789
    test_user_name = "Тестовый Пользователь"
    
    try:
        with database.get_cursor() as cursor:
            # Добавляем пользователя если его нет
            cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, full_name, registered_at)
            VALUES (?, ?, ?)
            ''', (test_user_id, test_user_name, datetime.datetime.now().isoformat()))
            
            # Создаем чат
            cursor.execute('''
            INSERT OR IGNORE INTO chats (user_id, user_name, chat_status, last_message, last_message_time)
            VALUES (?, ?, ?, ?, ?)
            ''', (test_user_id, test_user_name, 'active', 'Привет! Как дела?', datetime.datetime.now().isoformat()))
            
            chat_id = cursor.lastrowid or 1
            
            # Добавляем несколько тестовых сообщений
            test_messages = [
                ('user', 'Привет! Как дела?'),
                ('admin', 'Здравствуйте! Все отлично, спасибо!'),
                ('user', 'Можно посмотреть меню?'),
                ('admin', 'Конечно! Вот наше меню...'),
                ('user', 'Спасибо!')
            ]
            
            for sender, message in test_messages:
                cursor.execute('''
                INSERT INTO chat_messages (chat_id, sender, message_text, sent)
                VALUES (?, ?, ?, ?)
                ''', (chat_id, sender, message, 1))
            
            print(f"✅ Создан тестовый чат ID: {chat_id}")
            print(f"👤 Пользователь: {test_user_name} (ID: {test_user_id})")
            print(f"💬 Добавлено сообщений: {len(test_messages)}")
            
    except Exception as e:
        print(f"❌ Ошибка создания тестового чата: {e}")

if __name__ == '__main__':
    create_test_chat()