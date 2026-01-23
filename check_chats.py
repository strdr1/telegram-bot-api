#!/usr/bin/env python3
import database

database.init_database()
chats = database.get_all_chats_for_admin()
print(f"Найдено чатов: {len(chats)}")
for chat in chats:
    print(f"  - ID: {chat['id']}, User: {chat['user_name']}, Status: {chat['chat_status']}")