from menu_cache import menu_cache
import sys

# Configure stdout to handle utf-8
sys.stdout.reconfigure(encoding='utf-8')

print("Loading menus...")
menu_cache.load_all_menus(force_update=True)
print(f"Delivery IDs: {list(menu_cache.delivery_menus_cache.keys())}")

found_hot = False
for mid, data in menu_cache.delivery_menus_cache.items():
    cats = list(data.get('categories', {}).keys())
    print(f"Menu {mid} cats: {cats}")
    if any("горячие" in c.lower() for c in cats):
        found_hot = True

if found_hot:
    print("SUCCESS: 'горячие' category found in delivery cache.")
else:
    print("FAILURE: 'горячие' category NOT found in delivery cache.")
