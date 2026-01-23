#!/usr/bin/env python3
"""
Test AI on server
"""
import sys
import os
sys.path.append('/opt/telegram-bot')
os.chdir('/opt/telegram-bot')

import asyncio
import ai_assistant

async def test_ai():
    print("🧪 Тестируем AI на сервере...")
    
    user_id = 515216260
    message = "Мак, сколько ккал в пицце?"
    
    try:
        result = await ai_assistant.get_ai_response(message, user_id)
        print(f"✅ Результат AI: {result}")
        
        if result and result.get('type') == 'text':
            print(f"📝 Текст ответа: {result['text']}")
            if result.get('show_category_brief'):
                print(f"📋 Показать краткую категорию: {result['show_category_brief']}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка AI: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    asyncio.run(test_ai())