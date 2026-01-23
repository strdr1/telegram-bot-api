#!/usr/bin/env python3
"""
Прямой тест AI
"""
import sys
sys.path.append('/opt/telegram-bot')

import asyncio
import ai_assistant

async def test_ai():
    print("🧪 Тестируем AI напрямую...")
    
    user_id = 515216260
    message = "Мак, сколько ккал в пицце?"
    
    try:
        result = await ai_assistant.get_ai_response(message, user_id)
        print(f"✅ Результат AI: {result}")
        return True
    except Exception as e:
        print(f"❌ Ошибка AI: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    asyncio.run(test_ai())