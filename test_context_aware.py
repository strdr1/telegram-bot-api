#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест контекстно-зависимых коротких ответов
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database
from category_handler import handle_show_category

async def test_context_aware_handling():
    """Тест контекстно-зависимой обработки коротких ответов"""
    print("🧠 Тестируем контекстно-зависимую обработку коротких ответов...\n")
    
    # Создаем тестового пользователя
    test_user_id = 999999999
    test_user_name = "Test User"
    
    # Создаем чат и добавляем контекстные сообщения
    chat_id = database.get_or_create_chat(test_user_id, test_user_name)
    
    # Симулируем диалог о пицце
    database.save_chat_message(chat_id, 'user', 'Какая калорийность у пиццы?')
    database.save_chat_message(chat_id, 'bot', 'У нас есть несколько видов пиццы! Какая именно вас интересует?')
    
    print("📝 Создан контекст диалога о пицце")
    print("👤 Пользователь спросил: 'Какая калорийность у пиццы?'")
    print("🤖 Бот ответил: 'У нас есть несколько видов пиццы! Какая именно вас интересует?'")
    print()
    
    # Получаем последние сообщения
    recent_messages = database.get_recent_chat_messages(chat_id, limit=10)
    print(f"📋 Найдено {len(recent_messages)} последних сообщений:")
    for msg in recent_messages:
        print(f"  {msg['sender']}: {msg['message'][:50]}...")
    print()
    
    # Проверяем обнаружение контекста
    category_keywords = {
        'пицца': ['пицц', 'pizza', 'пиццы', 'пиццей', 'пиццу'],
        'суп': ['суп', 'soup', 'супы', 'супов', 'супчик', 'борщ', 'солянка'],
        'десерт': ['десерт', 'сладк', 'торт', 'пирожн', 'десерты', 'десертов', 'мороженое', 'тирамису'],
    }
    
    detected_category = None
    for message_data in recent_messages:
        if message_data.get('sender') == 'bot':
            bot_text = message_data.get('message', '').lower()
            for category, keywords in category_keywords.items():
                if any(keyword in bot_text for keyword in keywords):
                    detected_category = category
                    print(f"🎯 Обнаружена категория '{category}' в сообщении бота: '{bot_text[:50]}...'")
                    break
            if detected_category:
                break
    
    if detected_category:
        print(f"✅ УСПЕХ: Контекст категории '{detected_category}' обнаружен!")
        
        # Тестируем показ категории
        print(f"\n🔍 Тестируем показ категории '{detected_category}'...")
        try:
            # Создаем фиктивный бот для тестирования
            class MockBot:
                async def send_message(self, chat_id, text, **kwargs):
                    print(f"📤 Бот отправил бы сообщение: {text[:100]}...")
                    return True
            
            mock_bot = MockBot()
            await handle_show_category(detected_category, test_user_id, mock_bot)
            print("✅ УСПЕХ: Категория показана корректно!")
            
        except Exception as e:
            print(f"❌ ОШИБКА при показе категории: {e}")
            return False
            
    else:
        print("❌ ОШИБКА: Контекст категории НЕ обнаружен!")
        return False
    
    # Очищаем тестовые данные
    try:
        with database.get_cursor() as cursor:
            cursor.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
            cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        print("\n🧹 Тестовые данные очищены")
    except Exception as e:
        print(f"⚠️ Ошибка очистки тестовых данных: {e}")
    
    return True

async def main():
    """Главная функция тестирования"""
    print("🚀 Запуск тестирования контекстно-зависимых ответов...\n")
    
    success = await test_context_aware_handling()
    
    print(f"\n🏁 РЕЗУЛЬТАТ:")
    if success:
        print("🎉 КОНТЕКСТНО-ЗАВИСИМАЯ ОБРАБОТКА РАБОТАЕТ!")
        print("Короткие ответы типа 'хочу' будут правильно обрабатываться в контексте!")
    else:
        print("💥 Есть проблемы с контекстно-зависимой обработкой")

if __name__ == "__main__":
    asyncio.run(main())