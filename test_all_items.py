#!/usr/bin/env python3
"""
Тест показа всех позиций в категориях
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_ai_response

async def test_all_items():
    """Тестируем показ всех позиций"""
    
    print("📋 ТЕСТ ПОКАЗА ВСЕХ ПОЗИЦИЙ")
    print("=" * 50)
    
    test_user_id = 12345
    
    test_cases = [
        {"message": "У вас есть вино?", "category": "вино"},
        {"message": "А у вас есть пиццы?", "category": "пиццы"},
        {"message": "У вас есть супы?", "category": "супы"}
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n🧪 ТЕСТ {i}: {test['message']}")
        print(f"📂 Категория: {test['category']}")
        print("-" * 40)
        
        try:
            response = await get_ai_response(test['message'], test_user_id)
            response_text = response.get('text', 'Нет ответа')
            
            # Считаем количество позиций с ценами
            lines_with_prices = [line for line in response_text.split('\n') if '₽' in line and '•' in line]
            
            print(f"📊 Найдено позиций: {len(lines_with_prices)}")
            
            # Проверяем на ограничения
            has_more_text = "... и ещё" in response_text
            
            if has_more_text:
                print("❌ ЕСТЬ ОГРАНИЧЕНИЯ! (показывает '... и ещё')")
            else:
                print("✅ ПОКАЗЫВАЕТ ВСЕ ПОЗИЦИИ!")
            
            # Показываем все позиции
            print("📋 Все позиции:")
            for j, line in enumerate(lines_with_prices, 1):
                print(f"   {j}. {line.strip()}")
                
        except Exception as e:
            print(f"❌ ОШИБКА: {e}")
        
        await asyncio.sleep(1)
    
    print("\n" + "=" * 50)
    print("🎯 РЕЗУЛЬТАТ: Проверьте, показываются ли ВСЕ позиции без ограничений")

if __name__ == "__main__":
    asyncio.run(test_all_items())