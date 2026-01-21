import asyncio
import logging
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from presto_api_new import presto_api

# Set up logging
logging.basicConfig(level=logging.INFO)

async def test_menu_loading():
    """Test loading delivery menus"""
    try:
        print("🔄 Testing menu loading...")

        # Load all menus
        menus = await presto_api.get_all_menus()

        if menus:
            print(f"✅ Loaded {len(menus)} menus:")
            for menu_id, menu_data in menus.items():
                categories = menu_data.get('categories', {})
                total_items = sum(len(cat.get('items', [])) for cat in categories.values())
                print(f"  • {menu_data['name']} (ID: {menu_id}): {len(categories)} categories, {total_items} items")

                # Show categories
                for cat_id, cat_data in categories.items():
                    items_count = len(cat_data.get('items', []))
                    print(f"    - {cat_data.get('name', 'Unknown')}: {items_count} items")
        else:
            print("❌ No menus loaded")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_menu_loading())
