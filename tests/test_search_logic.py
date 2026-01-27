
import asyncio
from unittest.mock import MagicMock

# Mock menu data
mock_menu = {
    'categories': {
        '1': {
            'name': 'Салаты',
            'items': [
                {
                    'id': '101',
                    'name': 'Салат с хрустящими баклажанами',
                    'description': 'Сочетание хрустящих баклажанов, сочных томатов...',
                    'price': 570
                },
                {
                    'id': '102',
                    'name': 'Греческий салат',
                    'description': 'Классический салат',
                    'price': 450
                }
            ]
        }
    }
}

mock_menu_cache = MagicMock()
mock_menu_cache.all_menus_cache = {'1': mock_menu}
mock_menu_cache.delivery_menus_cache = {'1': mock_menu}

# Copy logic from category_handler.py (simplified for testing)
def search_dish(raw_search):
    raw_search = raw_search.lower().strip()
    if ',' in raw_search:
        search_keywords = [k.strip() for k in raw_search.split(',') if k.strip()]
    else:
        search_keywords = [k.strip() for k in raw_search.split() if k.strip()]
    
    if not search_keywords:
        search_keywords = [raw_search]

    search_keywords = [k[:-1] if k.endswith('и') and len(k) > 3 and k != 'миди' else k for k in search_keywords]
    
    print(f"Keywords: {search_keywords}")
    
    found_items = []
    
    for item in mock_menu['categories']['1']['items']:
        item_name = item.get('name', '').lower()
        item_desc = item.get('description', '').lower()
        full_text = f"{item_name} {item_desc}"
        
        match = True
        for keyword in search_keywords:
            if keyword not in full_text:
                match = False
                break
        
        if match:
            found_items.append(item['name'])
            
    return found_items

# Test cases
print("--- Test 1: Exact match ---")
print(search_dish("Салат с хрустящими баклажанами"))

print("\n--- Test 2: User query ---")
print(search_dish("Салат с баклажанами"))

print("\n--- Test 3: Variation ---")
print(search_dish("баклажан"))

