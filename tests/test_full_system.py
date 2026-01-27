
import sys
import os
import re
import asyncio
import json
from unittest.mock import MagicMock, patch

# Mock sys.path to find modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies GLOBALLY
mock_database_module = MagicMock()
mock_database_module.check_ai_generation_limit.return_value = (True, 10)
mock_database_module.get_user_language.return_value = "ru"
mock_database_module.get_last_user_messages.return_value = []

sys.modules['database'] = mock_database_module
sys.modules['config'] = MagicMock()
sys.modules['keyboards'] = MagicMock()
sys.modules['aiogram'] = MagicMock()
sys.modules['aiogram.types'] = MagicMock()
sys.modules['aiogram.fsm.context'] = MagicMock()

# --- 1. TEST HANDLERS LOGIC (Regex) ---
def test_booking_regex():
    print("\n1. 🧪 TESTING BOOKING REGEX (Handlers Logic)")
    booking_keywords = [
        'забронировать', 'забранировать', 'бронировать', 'бранировать',
        'столик', 'стол', 'бронь', 'резерв', 'резервировать',
        'хочу забронировать', 'можно забронировать', 'заказать стол',
        'заказать столик', 'столик на', 'бронь на', 'резерв на',
        'забронируй', 'забронировать стол', 'забронировать столик'
    ]
    
    # The regex logic from handlers_main.py
    booking_pattern = r'\b(' + '|'.join(map(re.escape, booking_keywords)) + r')\b'
    
    test_cases = {
        "Хочу забронировать столик": True,
        "Нужен стол на двоих": True,
        "Это неприемлемо": False, 
        "Я настолько устал": False,
        "У вас есть свободный столик?": True,
        "Бронь на вечер": True
    }
    
    passed = True
    for text, expected in test_cases.items():
        text_lower = text.lower()
        match = bool(re.search(booking_pattern, text_lower))
        status = "✅" if match == expected else "❌"
        print(f"{status} Text: '{text}' -> Match: {match} (Expected: {expected})")
        if match != expected:
            passed = False
            
    return passed

# --- 2. TEST AI ASSISTANT LOGIC ---
async def test_ai_logic():
    print("\n2. 🧪 TESTING AI ASSISTANT LOGIC")
    
    # Mock data for menu
    mock_menu_data = {
        "90": {
            "categories": {
                "10": {
                    "items": [
                        {"name": "Пицца Маргарита", "price": 500, "description": "Классика"},
                        {"name": "Том Ям", "price": 600, "description": "Острый суп"}
                    ]
                }
            }
        }
    }

    # Mock response for AI API
    mock_ai_response = MagicMock()
    mock_ai_response.status_code = 200
    mock_ai_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "AI RESPONSE TEXT"
                }
            }
        ]
    }
    
    # Context manager to patch dependencies of ai_assistant
    # We remove patch('ai_assistant.database') because we mocked it globally
    with patch('ai_assistant.load_menu_cache', return_value=mock_menu_data), \
         patch('ai_assistant.search_in_faq', return_value=None), \
         patch('ai_assistant.config', MagicMock()), \
         patch('ai_assistant.requests.post', return_value=mock_ai_response):
         
        # Import module if not already imported (patch ensures it is)
        import ai_assistant
        from ai_assistant import get_ai_response
        
        # Clear history to ensure clean state
        ai_assistant.user_history.clear()
        
        # Test A: Specific Dish (Short) -> Should trigger local search logic
        print("\n--- Test A: Specific Dish 'Том Ям' (Fast Local Search) ---")
        try:
            res = await get_ai_response("Том Ям", 123)
            print(f"Result type: {res.get('type')}")
            
            if res.get('type') in ['show_dish_card', 'photo_with_text'] or 'DISH_PHOTO' in str(res):
                print("✅ Correctly identified as dish request")
            else:
                print(f"❌ Failed: Got {res.get('type')} - {res.get('text')}")
        except Exception as e:
            print(f"❌ Error in Test A: {e}")
            import traceback
            traceback.print_exc()

        # Test B: "Others" -> Should NOT trigger local search, should go to AI
        print("\n--- Test B: Context Query 'А другие?' (Should go to AI) ---")
        try:
            res = await get_ai_response("А другие?", 124)
            print(f"Result type: {res.get('type')}")
            if res.get('type') == 'text' and res.get('text') == "AI RESPONSE TEXT":
                 print("✅ Correctly went to AI")
            elif res.get('type') == 'text':
                 print(f"⚠️ Got text: {res.get('text')} (Might be context handler or mocked response)")
            else:
                 print(f"❌ Failed: Got {res.get('type')}")
        except Exception as e:
            print(f"❌ Error in Test B: {e}")
            
        # Test C: Banquet Query
        print("\n--- Test C: Banquet Query 'У меня день рождения' ---")
        try:
            res = await get_ai_response("У меня день рождения", 125)
            if res.get('show_banquet_options'):
                print("✅ AI correctly suggested banquet options")
            else:
                print(f"⚠️ AI did not suggest banquet options")
                print(f"Response: {res}")
        except Exception as e:
             print(f"❌ Error in Test C: {e}")

async def main():
    regex_passed = test_booking_regex()
    await test_ai_logic()
    
    if regex_passed:
        print("\n✅ SYSTEM TEST COMPLETED")
    else:
        print("\n❌ SYSTEM TEST FAILED")

if __name__ == "__main__":
    asyncio.run(main())
