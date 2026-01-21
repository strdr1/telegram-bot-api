#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Отладочный тест для вопросов про калории
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_ai_response

async def test_debug_calories():
    """Отладочный тест"""
    
    print("🔍 Отладка вопросов про калории...")
    
    query = "Сколько калорий в пицце?"
    print(f"\n🔍 Тестируем: '{query}'")
    
    # Проверяем логику определения
    message_lower = query.lower()
    print(f"📝 message_lower: '{message_lower}'")
    
    has_calories = any(word in message_lower for word in ['калори', 'ккал'])
    print(f"🔢 Есть слова про калории: {has_calories}")
    
    specific_dishes = ['борщ', 'маргарита', '4 сыра', 'пепперони', 'инфаркт', 'том ям', 'цезарь']
    is_specific_dish = any(dish in message_lower for dish in specific_dishes)
    print(f"🍽️ Конкретное блюдо: {is_specific_dish}")
    
    has_pizza = 'пицц' in message_lower
    print(f"🍕 Есть 'пицц': {has_pizza}")
    
    if has_calories and not is_specific_dish and has_pizza:
        print("✅ Должен сработать calories_category_question для пиццы")
    else:
        print("❌ НЕ должен сработать calories_category_question")
    
    # Теперь проверяем реальный ответ
    result = await get_ai_response(query, user_id=515216260)
    print(f"\n📋 Результат: {result.get('type')}")
    text = result.get('text', '')
    if '❓' in text:
        print("✅ Есть вопрос уточнения в тексте")
    else:
        print("❌ Нет вопроса уточнения")
        print(f"📝 Текст: {text[-100:]}")  # Последние 100 символов

if __name__ == "__main__":
    asyncio.run(test_debug_calories())