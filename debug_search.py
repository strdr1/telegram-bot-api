import json
import os

def search_cache():
    cache_file = 'files/all_menus_cache.json'
    if not os.path.exists(cache_file):
        print("Cache file not found")
        return

    with open(cache_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    all_menus = data.get('all_menus', {})
    
    print(f"Searching {len(all_menus)} menus...")
    
    for m_id, m_data in all_menus.items():
        if str(m_id) == '166': # Kitchen menu
            print(f"Checking Menu {m_id}: {m_data.get('name')}")
            for cat_id, cat in m_data.get('categories', {}).items():
                cat_name = cat.get('name')
                items = cat.get('items', [])
                print(f"  Category: {cat_name} ({len(items)} items)")
                
                if 'пицца' in cat_name.lower():
                    for item in items:
                        print(f"    - {item['name']} (Price: {item.get('price')})")
                        if 'корона' in item['name'].lower() or 'корона' in item.get('description', '').lower():
                             print("!!! FOUND CORONA HERE !!!")

if __name__ == "__main__":
    search_cache()
