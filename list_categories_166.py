import json
import os

def list_categories():
    cache_path = 'files/all_menus_cache.json'
    output_path = 'menu_166_categories.txt'
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        menu_166 = data.get('all_menus', {}).get('166')
        
        with open(output_path, 'w', encoding='utf-8') as out:
            if not menu_166:
                out.write("Menu 166 not found in cache.\n")
                return

            out.write(f"Menu: {menu_166.get('name')}\n")
            out.write("Categories:\n")
            for cat_id, cat in menu_166.get('categories', {}).items():
                out.write(f" - {cat.get('name')} (ID: {cat_id})\n")
                
    except Exception as e:
        with open(output_path, 'w', encoding='utf-8') as out:
            out.write(f"Error: {e}\n")

if __name__ == "__main__":
    list_categories()
