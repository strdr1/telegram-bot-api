import json

def check_pizza_corona():
    with open('files/all_menus_cache.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    menu_166 = data.get('all_menus', {}).get('166', {})
    items = []
    for cat in menu_166.get('categories', {}).values():
        items.extend(cat.get('items', []))
        
    found = False
    for item in items:
        name = item.get('name', '').lower()
        if 'корона' in name:
            print(f"✅ Found: {item.get('name')} (ID: {item.get('id')})")
            found = True
            
    if not found:
        print("❌ 'Корона' not found in Menu 166")

if __name__ == "__main__":
    check_pizza_corona()
