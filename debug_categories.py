
import json
import os
import sys

# Mock menu_cache to avoid import errors if dependencies are missing
class MenuCache:
    def __init__(self):
        self.all_menus_cache = {}
        self.delivery_menus_cache = {}

menu_cache = MenuCache()

def load_cache():
    # Load delivery cache
    if os.path.exists('files/menu_cache.json'):
        with open('files/menu_cache.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            menu_cache.delivery_menus_cache = data.get('all_menus', {})
            menu_cache.all_menus_cache.update(menu_cache.delivery_menus_cache)
            print(f"Loaded {len(menu_cache.delivery_menus_cache)} delivery menus")

    # Load all menus cache
    if os.path.exists('files/all_menus_cache.json'):
        with open('files/all_menus_cache.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            other_menus = data.get('all_menus', {})
            menu_cache.all_menus_cache.update(other_menus)
            print(f"Total menus: {len(menu_cache.all_menus_cache)}")

def inspect_categories():
    print("\n--- Categories Inspection ---")
    ALLOWED_MENU_IDS = [90, 92, 141, 29, 32] # From core memories
    
    for menu_id, menu in menu_cache.all_menus_cache.items():
        if int(menu_id) not in ALLOWED_MENU_IDS:
            continue
            
        print(f"\nMenu ID: {menu_id} ({menu.get('name')})")
        for cat_id, cat in menu.get('categories', {}).items():
            print(f"  - ID: {cat_id}, Name: '{cat.get('name')}', Items: {len(cat.get('items', []))}")

def test_match(search_term):
    print(f"\n--- Testing Match for '{search_term}' ---")
    search_term = search_term.lower()
    ALLOWED_MENU_IDS = [90, 92, 141, 29, 32]
    
    found = False
    for menu_id in ALLOWED_MENU_IDS:
        menu = menu_cache.all_menus_cache.get(str(menu_id))
        if not menu: continue
        
        for cat_id, cat in menu.get('categories', {}).items():
            cat_name = cat.get('name', '').lower()
            
            is_match = False
            # Logic from handle_show_category_brief
            is_hot_search = any(root in search_term for root in ['горяч', 'основн', 'втор'])
            is_salad_search = 'салат' in search_term
            
            if is_hot_search:
                if any(root in cat_name for root in ['горяч', 'основн', 'втор']):
                    is_match = True
            elif is_salad_search:
                if 'салат' in cat_name:
                    is_match = True
            else:
                is_match = (search_term in cat_name)
            
            if is_match:
                print(f"MATCH! Menu {menu_id}, Category '{cat.get('name')}'")
                found = True
                
    if not found:
        print("NO MATCH FOUND")

if __name__ == "__main__":
    load_cache()
    inspect_categories()
    test_match("горячие блюда")
    test_match("салаты")
    test_match("супы")
