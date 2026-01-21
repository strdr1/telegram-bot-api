#!/usr/bin/env python3
"""
Тест для проверки fallback логики при недоступности AI
"""

import asyncio
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_fallback_response

def test_fallback_scenario():
    print("🧪 Тестируем fallback логику...")
    print("=" * 50)
    
    test_cases = [
        {
            'query': 'Какая калорийность у пиццы?',
            'expected_flag': 'show_category_brief',
            'expected_category': 'пицца'
        },
        {
            'query': 'Сколько калорий в супах?',
            'expected_flag': 'show_category_brief',
            'expected_category': 'суп'
        },
        {
            'query': 'пицца',
            'expected_flag': 'show_category_brief',
            'expected_category': 'пицца'
        },
        {
            'query': 'какие есть супы?',
            'expected_flag': 'show_category_brief',
            'expected_category': 'суп'
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"{i}. Тестируем: '{case['query']}'")
        
        result = get_fallback_response(case['query'], user_id=515216260)
        
        # Проверяем флаг
        if result.get(case['expected_flag']):
            category = result.get(case['expected_flag'])
            if case['expected_category'] in category.lower():
                print(f"   ✅ Правильный флаг и категория: {case['expected_flag']} = {category}")
            else:
                print(f"   ❌ Неверная категория: {category} (ожидалась: {case['expected_category']})")
        else:
            print(f"   ❌ Неверный флаг. Получен: {list(result.keys())}")
            print(f"      Результат: {result}")
        
        # Проверяем что нет show_category (полные карточки)
        if result.get('show_category'):
            print(f"   ❌ ОШИБКА: найден флаг show_category (полные карточки): {result.get('show_category')}")
        else:
            print(f"   ✅ Нет флага show_category (полные карточки)")
        
        print()

if __name__ == "__main__":
    test_fallback_scenario()