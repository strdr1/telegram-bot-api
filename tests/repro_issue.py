
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock objects
class MockBot:
    async def send_message(self, chat_id, text, **kwargs):
        print(f"[Bot] send_message to {chat_id}: {text}")
        return type('obj', (object,), {'message_id': 123})
    
    async def send_photo(self, chat_id, photo, caption, **kwargs):
        print(f"[Bot] send_photo to {chat_id}: {caption[:50]}...")
        return type('obj', (object,), {'message_id': 123})

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_search():
    print("--- Testing Search Logic ---")
    try:
        from category_handler import find_dishes_by_name
        from menu_cache import menu_cache
        
        # Initialize cache explicitly
        print("Initializing menu cache...")
        await menu_cache.load_all_menus(force_update=True)
        print("Menus loaded:", len(menu_cache.all_menus_cache))
        
        query = "салат с баклажанами"
        print(f"Searching for: '{query}'")
        
        results = find_dishes_by_name(query)
        print(f"Found {len(results)} dishes")
        
        found = False
        for dish in results:
            print(f"- {dish['name']} (ID: {dish['id']})")
            if "хрустящими баклажанами" in dish['name'].lower() or "баклажан" in dish['name'].lower():
                found = True
        
        if found:
            print("✅ Target dish found!")
        else:
            print("❌ Target dish NOT found!")
            
    except Exception as e:
        print(f"Error during search test: {e}")
        import traceback
        traceback.print_exc()

async def test_category_display():
    print("\n--- Testing Category Display Logic ---")
    try:
        from category_handler import handle_show_category
        
        bot = MockBot()
        user_id = 12345
        category_name = "Салаты" # Testing "Какие салаты есть?" -> "Салаты" (usually AI extracts this)
        
        print(f"Showing category: '{category_name}'")
        await handle_show_category(category_name, user_id, bot)
        print("✅ handle_show_category finished without exception")
        
    except Exception as e:
        print(f"❌ Error during category display test: {e}")
        import traceback
        traceback.print_exc()

async def main():
    await test_search()
    await test_category_display()

if __name__ == "__main__":
    asyncio.run(main())
