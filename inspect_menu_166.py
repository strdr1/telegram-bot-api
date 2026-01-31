import json
import os

def inspect_menu():
    cache_path = 'files/all_menus_cache.json'
    if not os.path.exists(cache_path):
        print(f"File {cache_path} not found!")
        return

    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Loaded cache. Keys: {list(data.keys())}")

    menu_166 = data.get('166')
    if not menu_166:
        print("Menu 166 not found in cache!")
        return

    print(f"Menu: {menu_166.get('name')}")
    print("Categories:")
    for cat_id, cat in menu_166.get('categories', {}).items():
        print(f"  - {cat.get('name')} (ID: {cat_id}) - {len(cat.get('items', []))} items")
        # Print first few items to check content
        # for item in cat.get('items', [])[:3]:
        #     print(f"    * {item.get('name')}")

if __name__ == "__main__":
    inspect_menu()
