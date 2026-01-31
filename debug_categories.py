
import json

try:
    with open(r'f:\1\telegram-bot-restaurant\files\all_menus_cache.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    menu = data['all_menus'].get('166')
    if menu:
        for cat in menu.get('categories', {}).values():
            if cat['name'] == 'ПАСТА':
                items = cat.get('items', [])
                print(f"Items count: {len(items)}")
                for item in items:
                    print(f"- {item['name']} ({item['price']})")
except Exception as e:
    print(e)
