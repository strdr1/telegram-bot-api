#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест для проверки правильной обработки вопросов про калории в категориях
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_ai_response

async def test_calories_questions():
    """Тест: вопросы про калории в категориях должны показывать список и спрашивать уточнение"""
    
    print("🧪 Тестируем вопросы про калории в категориях...")
    
    # Тестовые запросы про калории в категориях
    test_cases = [
        {
            "query": "Сколько калорий в пицце?",
            "expected_type": "category",
            "expected_category": "пицца",
            "should_ask": "В какой именно пицце"
        },
        {
            "query": "Какая калорийность у супов?",
            "expected_type": "category", 
            "expected_category": "суп",
            "should_ask": "В каком именно супе"
        },
        {
            "query": "Сколько калорий в десертах?",
            "expected_type": "category",
            "expected_category": "десерт", 
            "should_ask": "В каком именно десерте"
        }
    ]
    
    # Тестовые запросы про конкретные блюда (должны показывать карточку)
    specific_cases = [
        {
            "query": "Сколько калорий в борще?",
            "expected_type": "dish_photo",
            "expected_dish": "Борщ"
        },
        {
            "query": "Калорийность пиццы Маргарита",
            "expected_type": "dish_photo",
            "expected_dish": "Пицца Маргарита"
        }
    ]
    
    success_count = 0
    total_count = len(test_cases) + len(specific_cases)
    
    print("\n=== ТЕСТ 1: Вопросы про калории в КАТЕГОРИЯХ ===")
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}. Тестируем: '{case['query']}'")
        
        try:
            result = await get_ai_response(case['query'], user_id=515216260)
            
            if result and result.get('type') == 'text' and result.get('show_category'):
                # Проверяем что показывается правильная категория
                category_name = result.get('show_category', '')
                
                if case['expected_category'] in category_name.lower():
                    print(f"   ✅ Правильная категория: {category_name}")
                    
                    # Проверяем что есть вопрос уточнения
                    text = result.get('text', '')
                    if case['should_ask'].lower() in text.lower():
                        print(f"   ✅ Есть вопрос уточнения")
                        success_count += 1
                    else:
                        print(f"   ❌ Нет вопроса уточнения")
                        print(f"   📋 Текст: {text}")
                else:
                    print(f"   ❌ Неправильная категория: {category_name}")
            else:
                print(f"   ❌ Неправильный тип ответа: {result.get('type') if result else 'None'}")
                if result:
                    print(f"   📋 Результат: {result}")
                
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    print("\n=== ТЕСТ 2: Вопросы про калории в КОНКРЕТНЫХ блюдах ===")
    for i, case in enumerate(specific_cases, 1):
        print(f"\n{i}. Тестируем: '{case['query']}'")
        
        try:
            result = await get_ai_response(case['query'], user_id=515216260)
            
            if result and result.get('type') == 'photo_with_text':
                # Проверяем что показывается карточка конкретного блюда
                text = result.get('text', '')
                
                if case['expected_dish'].lower() in text.lower():
                    print(f"   ✅ Показана карточка блюда: {case['expected_dish']}")
                    
                    # Проверяем что есть информация о калориях
                    if 'калори' in text.lower() or 'ккал' in text.lower():
                        print(f"   ✅ Есть информация о калориях")
                        success_count += 1
                    else:
                        print(f"   ❌ Нет информации о калориях")
                else:
                    print(f"   ❌ Неправильное блюдо в карточке")
                    print(f"   📋 Текст: {text}")
            else:
                print(f"   ❌ Неправильный тип ответа: {result.get('type') if result else 'None'}")
                
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    print(f"\n📊 Результат: {success_count}/{total_count} тестов прошли успешно")
    
    if success_count == total_count:
        print("🎉 Все тесты прошли! Вопросы про калории обрабатываются корректно")
        return True
    else:
        print("⚠️ Некоторые тесты не прошли")
        return False

if __name__ == "__main__":
    asyncio.run(test_calories_questions())