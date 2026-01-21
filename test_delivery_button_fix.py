#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест для проверки кнопки доставки в полных карточках блюд
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_ai_response

async def test_delivery_button_in_dish_cards():
    """Тест: кнопка доставки должна появляться в полных карточках блюд"""
    
    print("🧪 Тестируем кнопку доставки в полных карточках блюд...")
    
    # Тестовые запросы на конкретные блюда
    test_cases = [
        "Борщ хочу",
        "Пицца Маргарита",
        "Расскажи про борщ",
        "Что такое пицца 4 сыра?",
        "Покажи салат Цезарь"
    ]
    
    success_count = 0
    total_count = len(test_cases)
    
    for i, query in enumerate(test_cases, 1):
        print(f"\n{i}. Тестируем: '{query}'")
        
        try:
            result = await get_ai_response(query, user_id=515216260)
            
            if result and result.get('type') == 'photo_with_text':
                # Проверяем что есть кнопка доставки
                has_delivery_button = result.get('show_delivery_button', False)
                
                if has_delivery_button:
                    print(f"   ✅ Кнопка доставки есть")
                    success_count += 1
                else:
                    print(f"   ❌ Кнопка доставки отсутствует!")
                    print(f"   📋 Результат: {result}")
            else:
                print(f"   ⚠️ Не photo_with_text тип: {result.get('type') if result else 'None'}")
                
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    print(f"\n📊 Результат: {success_count}/{total_count} тестов прошли успешно")
    
    if success_count == total_count:
        print("🎉 Все тесты прошли! Кнопка доставки работает корректно")
        return True
    else:
        print("⚠️ Некоторые тесты не прошли")
        return False

if __name__ == "__main__":
    asyncio.run(test_delivery_button_in_dish_cards())