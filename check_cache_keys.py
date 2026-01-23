import json
import os

try:
    with open('files/all_menus_cache.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        menus = data.get('all_menus', {})
        print("Loaded menu IDs:", list(menus.keys()))
        for mid, mdata in menus.items():
            print(f"ID: {mid}, Name: {mdata.get('name')}")
            cats = mdata.get('categories', {})
            print(f"  Categories count: {len(cats)}")
            for cid, cdata in cats.items():
                print(f"    - {cdata.get('name')} (Items: {len(cdata.get('items', []))})")
except Exception as e:
    print(f"Error: {e}")
