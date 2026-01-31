import json
import os

def inspect_pasta_breakfast():
    cache_path = 'files/all_menus_cache.json'
    
    if not os.path.exists(cache_path):
        print(f"File {cache_path} not found!")
        return

    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_menus = data.get('all_menus', {})
    
    # Check PASTA in Menu 166
    menu_166 = all_menus.get('166')
    if menu_166:
        categories = menu_166.get('categories', {})
        # Find category with name "ПАСТА" or ID 6156
        pasta_cat = categories.get('6156')
        if not pasta_cat:
            # Try searching by name
            for cid, cat in categories.items():
                if 'паста' in cat.get('name', '').lower():
                    pasta_cat = cat
                    print(f"Found Pasta by name: {cat.get('name')} (ID: {cid})")
                    break
        
        if pasta_cat:
            items = pasta_cat.get('items', [])
            print(f"🍝 PASTA Category (ID {pasta_cat.get('id')}): {len(items)} items")
            for item in items:
                print(f"   - {item.get('name')} (Price: {item.get('price')})")
        else:
            print("❌ PASTA category NOT found in Menu 166 cache")
    else:
        print("❌ Menu 166 NOT found in cache")

    print("-" * 30)

    # Check Breakfast Menu 167
    menu_167 = all_menus.get('167')
    if menu_167:
        print(f"🍳 Breakfast Menu 167 found: {menu_167.get('name')}")
        categories = menu_167.get('categories', {})
        total_items = 0
        for cat_id, cat in categories.items():
            count = len(cat.get('items', []))
            total_items += count
            print(f"   - Category '{cat.get('name')}' (ID: {cat_id}): {count} items")
        print(f"   Total Breakfast items: {total_items}")
    else:
        print("❌ Menu 167 (Breakfast) NOT found in cache")

if __name__ == "__main__":
    inspect_pasta_breakfast()
