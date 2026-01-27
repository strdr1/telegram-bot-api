import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock config and database BEFORE importing ai_assistant
sys.modules['config'] = MagicMock()
sys.modules['database'] = MagicMock()
sys.modules['database'].get_setting.return_value = "1234567890"
sys.modules['database'].check_ai_generation_limit.return_value = (True, 10)

import ai_assistant

# Mock Menu Data
mock_menu = {
    "90": {
        "categories": {
            "10": {
                "name": "Морепродукты",
                "items": [
                    {"name": "Брускетта с креветками и авокадо", "description": "С авокадо", "price": 650},
                    {"name": "Мидии Мариньер", "description": "В соусе", "price": 1150},
                    {"name": "Том Ям", "description": "Острый суп", "price": 690},
                    {"name": "Жареные креветки", "description": "С чесноком", "price": 870}
                ]
            }
        }
    }
}

async def test_seafood_conversation_flow():
    user_id = 12345
    
    # 1. User asks for seafood
    print("\n--- Step 1: User asks for seafood ---")
    
    # Mock AI response for the first query
    mock_response_1 = MagicMock()
    mock_response_1.status_code = 200
    mock_response_1.json.return_value = {
        "choices": [{
            "message": {
                "content": "Конечно! У нас есть замечательные блюда. SEARCH:морепродукты"
            }
        }]
    }
    
    with patch('requests.post', return_value=mock_response_1):
        with patch('ai_assistant.load_menu_cache', return_value=mock_menu):
            response = await ai_assistant.get_ai_response("У вас есть что то с морепродуктами?", user_id)
            print(f"Response 1: {response['text']}")
            # Check for search_query in response or SEARCH marker in text (if not stripped)
            assert "SEARCH:морепродукты" in response['text'] or response.get('search_query') == 'морепродукты'

            # SIMULATE HANDLER ACTION: Add search results to history
            # This is what handlers_main.py does now
            simulated_search_results = (
                "🍽️ Морепродукты (найдено по названию):\n\n"
                "• Брускетта с креветками и авокадо — 650.0₽\n"
                "• Мидии Мариньер — 1150.0₽\n"
                "• Том Ям — 690.0₽\n"
                "• Жареные креветки — 870.0₽"
            )
            ai_assistant.add_bot_message_to_history(user_id, simulated_search_results)
            print("Simulated handler action: Added search results to AI context.")

    # 2. User asks for recommendation
    print("\n--- Step 2: User asks 'What do you recommend?' ---")
    mock_response_2 = MagicMock()
    mock_response_2.status_code = 200
    mock_response_2.json.return_value = {
        "choices": [{
            "message": {
                "content": "Рекомендую попробовать Мидии Мариньер!"
            }
        }]
    }
    
    with patch('requests.post', return_value=mock_response_2) as mock_post:
        with patch('ai_assistant.load_menu_cache', return_value=mock_menu):
            response = await ai_assistant.get_ai_response("Что посоветуешь?", user_id)
            print(f"Response 2: {response['text']}")
            
            # Verify that the history sent to AI includes our simulated search results
            call_args = mock_post.call_args
            if call_args:
                json_data = call_args[1].get('json', {})
                messages = json_data.get('messages', [])
                
                # Check SYSTEM PROMPT for the new Seafood rule
                system_msg = messages[0]['content']
                if "СПЕЦИАЛЬНО ДЛЯ МОРЕПРОДУКТОВ" in system_msg and "Если ты УЖЕ показал список" in system_msg:
                    print("✅ VERIFIED: System prompt contains UPDATED SEAFOOD context rule!")
                else:
                    print("❌ FAILED: System prompt MISSING UPDATED SEAFOOD context rule.")
                    print(f"System Prompt snippet: {system_msg[:500]}...")
                assert "СПЕЦИАЛЬНО ДЛЯ МОРЕПРОДУКТОВ" in system_msg

                if "Пример (ТОЛЬКО ЕСЛИ НЕТ КОНТЕКСТА)" in system_msg:
                    print("✅ VERIFIED: System prompt contains UPDATED GENERIC EXAMPLE!")
                else:
                    print("❌ FAILED: System prompt MISSING UPDATED GENERIC EXAMPLE.")
                assert "Пример (ТОЛЬКО ЕСЛИ НЕТ КОНТЕКСТА)" in system_msg

                # Check if any message in history contains our simulated text
                found_context = any("Мидии Мариньер" in msg.get('content', '') for msg in messages)
                if found_context:
                    print("✅ VERIFIED: AI received the search results in context!")
                else:
                    print("❌ FAILED: AI did NOT receive the search results in context.")
                    print(f"Messages sent: {[m.get('content') for m in messages]}")
                assert found_context

    # 4. User says "Are there others?" (А другие есть?)
    print("\n--- Step 4: User says 'А другие есть?' ---")
    
    # We expect this to NOT trigger banquet, but fallback to AI or local logic.
    # Since we are mocking, if it hits AI, it uses requests.post.
    # If it hits local logic (second_phrases), it might return a specific text.
    
    mock_response_4 = MagicMock()
    mock_response_4.status_code = 200
    mock_response_4.json.return_value = {
        "choices": [{
             "message": {
                 "content": "Вот еще блюда: Жареные креветки."
             }
        }]
    }

    with patch('requests.post', return_value=mock_response_4) as mock_post_4:
        with patch('ai_assistant.load_menu_cache', return_value=mock_menu):
            response = await ai_assistant.get_ai_response("А другие есть?", user_id)
            print(f"Response 4 Type: {response.get('type')}")
            print(f"Response 4 Text: {response.get('text')}")
            
            if response.get('show_banquet_options'):
                 print("❌ ERROR: Banquet options triggered!")
                 sys.exit(1)
            else:
                 print("✅ VERIFIED: Banquet options NOT triggered.")

            # Check if it was handled by second_phrases (which calls find_similar_dishes) 
            # OR passed to AI. 
            # In ai_assistant.py, 'second_phrases' logic attempts find_similar_dishes.
            # If find_similar_dishes returns nothing (which it might with mock menu if not set up right),
            # it proceeds to AI.
            # The key is that it didn't trigger BANQUET (which is separate logic).

    print("\n✅ Test Completed Successfully!")

if __name__ == "__main__":
    asyncio.run(test_seafood_conversation_flow())
