#!/usr/bin/env python3
"""
add_test_chats.py - Add test chat data to the database
"""

import database
from datetime import datetime, timedelta
import random

def add_test_chats():
    """Add some test chat data"""
    print("Adding test chat data...")

    # Initialize database
    database.init_database()

    # Test users and chats
    test_chats = [
        {
            'user_id': 123456789,
            'user_name': 'Иван Петров',
            'status': 'active',
            'messages': [
                ('user', 'Здравствуйте! Хочу забронировать столик на двоих на вечер'),
                ('admin', 'Здравствуйте! Конечно, на какое время и дату вас интересует бронь?'),
                ('user', 'Сегодня на 19:00, если есть места'),
                ('admin', 'Отлично! У нас есть свободный столик на 19:00. Подтверждаю бронь на ваше имя.')
            ]
        },
        {
            'user_id': 987654321,
            'user_name': 'Мария Иванова',
            'status': 'paused',
            'messages': [
                ('user', 'Добрый день! Интересует меню доставки'),
                ('admin', 'Здравствуйте! Конечно, наше меню доставки включает пиццу, пасту, салаты и десерты.')
            ]
        },
        {
            'user_id': 555666777,
            'user_name': 'Алексей Сидоров',
            'status': 'completed',
            'messages': [
                ('user', 'Спасибо за обслуживание! Все было очень вкусно'),
                ('admin', 'Спасибо за ваш отзыв! Рады что вам понравилось. Приходите еще!')
            ]
        }
    ]

    for chat_data in test_chats:
        # Create chat
        chat_id = database.get_or_create_chat(chat_data['user_id'], chat_data['user_name'])

        # Update chat status
        database.update_chat_status(chat_id, chat_data['status'])

        # Add messages with timestamps
        base_time = datetime.now() - timedelta(hours=random.randint(1, 24))

        for i, (sender, message_text) in enumerate(chat_data['messages']):
            # Add some time variation between messages
            message_time = base_time + timedelta(minutes=i * 5 + random.randint(1, 10))

            # Insert message with specific timestamp
            database.save_chat_message(chat_id, sender, message_text)

            # Update the message timestamp (this is a bit hacky but works for testing)
            try:
                with database.get_cursor() as cursor:
                    cursor.execute('''
                    UPDATE chat_messages
                    SET message_time = ?
                    WHERE chat_id = ? AND message_text = ? AND sender = ?
                    ''', (message_time.isoformat(), chat_id, message_text, sender))
            except Exception as e:
                print(f"Warning: Could not update message timestamp: {e}")

    print("✅ Test chat data added successfully!")
    print("📊 Run the miniapp server to see the chats: python miniapp_server.py")

if __name__ == "__main__":
    add_test_chats()
