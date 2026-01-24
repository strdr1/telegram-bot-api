
import asyncio
import logging
from menu_cache import MenuCache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    cache = MenuCache()
    # Force load to ensure we have data
    await cache.load_all_menus(force_update=True)
    
    print("\n=== DELIVERY MENUS CATEGORIES ===")
    for menu_id, menu in cache.delivery_menus_cache.items():
        print(f"Menu: {menu.get('name')} (ID: {menu_id})")
        categories = menu.get('categories', {})
        for cat_id, cat in categories.items():
            print(f"  - '{cat.get('name')}' (ID: {cat_id})")
            
    print("\n=== SEARCH TEST: 'горячее' ===")
    items = cache.get_category_items("горячее")
    print(f"Found {len(items)} items for 'горячее'")
    
    print("\n=== SEARCH TEST: 'Горячие блюда' ===")
    items = cache.get_category_items("Горячие блюда")
    print(f"Found {len(items)} items for 'Горячие блюда'")

if __name__ == "__main__":
    asyncio.run(main())
