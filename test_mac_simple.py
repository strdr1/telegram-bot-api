#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простой тест имени бота "Мак" без рекурсии
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_ai_response

async def test_mac_simple():
    """Простой тест имени Мак"""
    print("🤖 Простой тест имени бота 'Мак'...\n")
    
    test_cases = [
        "Мак",
        "Привет, Мак!",
        "Как тебя зовут?",
        "Что ты умеешь?",
        "Привет"
    ]
    
    for message in test_cases:
        try:
            print(f"🔍 Тестируем: '{message}'")
            result = await get_ai_response(message, 999999999)
            
            response_text = result.get('text', '')
            has_mac_name = 'мак' in response_text.lower()
            
            print(f"✅ Ответ содержит имя 'Мак': {'Да' if has_mac_name else 'Нет'}")
            print(f"📝 Ответ: {response_text[:100]}...")
            print()
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print()

async def main():
    """Главная функция"""
    await test_mac_simple()

if __name__ == "__main__":
    asyncio.run(main())