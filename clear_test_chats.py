#!/usr/bin/env python3
"""
clear_test_chats.py - Clear test chat data from database
"""

import database

def clear_test_chats():
    """Clear test chat data"""
    print("Clearing test chat data...")

    # Initialize database
    database.init_database()

    with database.get_cursor() as c:
        c.execute('DELETE FROM chat_messages')
        c.execute('DELETE FROM chats')

    print("✅ Test chats cleared!")

if __name__ == "__main__":
    clear_test_chats()
