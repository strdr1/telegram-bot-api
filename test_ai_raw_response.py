#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест для проверки сырого ответа AI на вопросы про калории
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_ai_response

async def test_raw_ai_response():
    """Тест: проверяем что именно возвращает AI"""
    
    print("🧪 Тестируем сырой ответ AI...")
    
    queries = [
        "Сколько калорий в пицце?",
        "У вас есть пицца?",
        "Какие пиццы есть?"
    ]
    
    for query in queries:
        print(f"\n🔍 Запрос: '{query}'")
        
        try:
            result = await get_ai_response(query, user_id=515216260)
            
            print(f"📋 Тип: {result.get('type')}")
            print(f"📝 Текст: {result.get('text', 'Нет текста')[:200]}...")
            
            # Проверяем наличие маркеров в тексте
            text = result.get('text', '')
            if 'PARSE_CATEGORY:' in text:
                print("✅ Найден маркер PARSE_CATEGORY:")
            elif 'Парсе категорию:' in text or 'парсе категорию:' in text:
                print("⚠️ Найден русский маркер 'Парсе категорию:'")
            else:
                print("❌ Маркеры не найдены")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(test_raw_ai_response())