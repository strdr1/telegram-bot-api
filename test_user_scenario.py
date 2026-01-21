#!/usr/bin/env python3
"""
Тест для воспроизведения сценария пользователя:
1. Пользователь спрашивает: "Какая калорийность у пиццы?"
2. Система должна показать КРАТКИЙ список пицц с вопросом уточнения
3. НЕ должно быть фотографий
"""

import asyncio
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_ai_response

async def test_user_scenario():
    print("🧪 Тестируем точный сценарий пользователя...")
    print("=" * 50)
    
    # Точный запрос пользователя
    user_query = "Какая калорийность у пиццы?"
    user_id = 515216260
    
    print(f"Запрос пользователя: '{user_query}'")
    print("-" * 30)
    
    try:
        result = await get_ai_response(user_query, user_id=user_id)
        
        print("Результат AI:")
        print(f"  type: {result.get('type')}")
        print(f"  text: {result.get('text', '')[:100]}...")
        print(f"  show_category_brief: {result.get('show_category_brief')}")
        print(f"  show_category: {result.get('show_category')}")
        print(f"  show_dish_card: {result.get('show_dish_card')}")
        
        # Проверяем что возвращается правильный флаг
        if result.get('show_category_brief'):
            print("✅ Правильно: возвращен флаг show_category_brief")
            print(f"   Категория: {result.get('show_category_brief')}")
        elif result.get('show_category'):
            print("❌ ОШИБКА: возвращен флаг show_category (полные карточки)")
            print(f"   Категория: {result.get('show_category')}")
        elif result.get('show_dish_card'):
            print("❌ ОШИБКА: возвращен флаг show_dish_card (карточка блюда)")
            print(f"   Блюдо: {result.get('show_dish_card')}")
        else:
            print("❌ ОШИБКА: не возвращен ни один флаг показа")
            
        # Проверяем текст ответа
        if result.get('text') and 'какой именно' in result.get('text', '').lower():
            print("✅ Правильно: есть вопрос уточнения")
        else:
            print("❌ ОШИБКА: нет вопроса уточнения")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_user_scenario())