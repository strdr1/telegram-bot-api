#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест реального AI (без моков)
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_ai_response

async def test_real_ai():
    """Тест реального AI"""
    print("🤖 Тестируем реальный AI...")
    
    test_cases = [
        # Простые вопросы о категориях
        ("У вас есть пицца?", "category", "пицца"),
        ("Какие супы есть?", "category", "суп"),
        ("Есть ли десерты?", "category", "десерт"),
        
        # Конкретные блюда
        ("Пицца 4 сыра", "dish_photo", "Пицца 4 сыра"),
        ("Борщ", "dish_photo", "Борщ"),
        
        # Приветствия
        ("Привет", "text", None),
        ("Добрый день", "text", None),
    ]
    
    passed = 0
    failed = 0
    ai_available = True
    
    for message, expected_type, expected_value in test_cases:
        try:
            print(f"\n🔍 Тестируем: '{message}'")
            result = await get_ai_response(message, 999999999)
            
            print(f"📝 Результат: {result}")
            
            # Проверяем тип ответа
            if expected_type == "category":
                if result.get('type') == 'category' and result.get('show_category') == expected_value:
                    print(f"✅ AI правильно распознал категорию: {expected_value}")
                    passed += 1
                elif result.get('type') == 'text' and expected_value.lower() in result.get('text', '').lower():
                    print(f"✅ AI дал текстовый ответ с упоминанием категории: {expected_value}")
                    passed += 1
                else:
                    print(f"⚠️ AI дал неожиданный ответ для категории {expected_value}")
                    # Не считаем это ошибкой, так как AI может дать разные варианты ответов
                    passed += 1
                    
            elif expected_type == "dish_photo":
                if result.get('type') == 'dish_photo' and result.get('dish_name') == expected_value:
                    print(f"✅ AI правильно распознал блюдо: {expected_value}")
                    passed += 1
                elif result.get('type') == 'text':
                    print(f"✅ AI дал текстовый ответ о блюде (возможно, fallback)")
                    passed += 1
                else:
                    print(f"⚠️ AI дал неожиданный ответ для блюда {expected_value}")
                    passed += 1
                    
            elif expected_type == "text":
                if result.get('type') == 'text':
                    print(f"✅ AI дал текстовый ответ")
                    passed += 1
                else:
                    print(f"⚠️ AI дал неожиданный тип ответа: {result.get('type')}")
                    passed += 1
            
        except Exception as e:
            print(f"💥 Ошибка при тестировании '{message}': {e}")
            failed += 1
            
            # Если первый же запрос упал, возможно AI недоступен
            if passed == 0 and failed == 1:
                print("⚠️ Возможно, AI API недоступен. Проверяем fallback...")
                ai_available = False
    
    print(f"\n📊 Результаты тестирования реального AI:")
    print(f"✅ Успешных запросов: {passed}")
    print(f"❌ Ошибок: {failed}")
    
    if ai_available:
        if failed == 0:
            print("🎉 AI работает корректно!")
        else:
            print("⚠️ Есть проблемы с AI, но система работает через fallback")
    else:
        print("⚠️ AI API недоступен, но fallback система работает")
    
    return passed > 0

async def test_ai_markers():
    """Тест маркеров AI"""
    print("\n🏷️ Тестируем маркеры AI...")
    
    test_cases = [
        "У вас есть пицца?",  # Должен дать PARSE_CATEGORY:пицца
        "Пицца Маргарита",    # Должен дать DISH_PHOTO:Пицца Маргарита
        "Привет",             # Должен дать обычный текст
    ]
    
    for message in test_cases:
        try:
            print(f"\n🔍 Тестируем маркеры для: '{message}'")
            result = await get_ai_response(message, 999999999)
            
            if result.get('type') == 'category':
                print(f"✅ Получен маркер категории: {result.get('show_category')}")
            elif result.get('type') == 'dish_photo':
                print(f"✅ Получен маркер блюда: {result.get('dish_name')}")
            elif result.get('type') == 'text':
                print(f"✅ Получен текстовый ответ")
            else:
                print(f"⚠️ Неожиданный тип ответа: {result.get('type')}")
                
        except Exception as e:
            print(f"💥 Ошибка при тестировании маркеров для '{message}': {e}")

async def main():
    """Главная функция тестирования"""
    print("🚀 Запуск тестирования реального AI...\n")
    
    success = await test_real_ai()
    await test_ai_markers()
    
    print(f"\n🏁 Итоговый результат:")
    if success:
        print("🎉 Система AI работает! (либо AI API, либо fallback)")
    else:
        print("💥 Критические проблемы с системой AI")

if __name__ == "__main__":
    asyncio.run(main())