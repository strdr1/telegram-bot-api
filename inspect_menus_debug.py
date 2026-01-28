
import asyncio
import logging
from menu_cache import menu_cache

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def inspect_menus():
    print("--- MENU INSPECTION ---")
    
    try:
        # Update menu cache
        await menu_cache.load_all_menus(force_update=True)
    except Exception as e:
        print(f"Error updating menu cache: {e}")
    
    print(f"Menus in cache: {len(menu_cache.all_menus_cache)}")
    
    for menu_id, menu in menu_cache.all_menus_cache.items():
        print(f"\nMenu ID: {menu_id} | Name: {menu.get('name')}")
        categories = menu.get('categories', {})
        print(f"Categories count: {len(categories)}")
        for cat_id, cat in categories.items():
            print(f"  - CatID: {cat_id} | Name: '{cat.get('name')}' | Display: '{cat.get('display_name')}'")

if __name__ == "__main__":
    asyncio.run(inspect_menus())
