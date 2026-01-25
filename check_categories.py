
import json

try:
    with open('files/menu_cache.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print("Categories found:")
    for menu_id, menu in data.get('all_menus', {}).items():
        print(f"Menu: {menu.get('name')} (ID: {menu_id})")
        for cat_id, cat in menu.get('categories', {}).items():
            print(f"  - {cat.get('name')} (ID: {cat_id})")
            
except Exception as e:
    print(f"Error: {e}")
