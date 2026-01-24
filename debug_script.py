import asyncio
import logging
from menu_cache import menu_cache

# Настройка логирования
logging.basicConfig(level=logging.INFO)

async def main():
    print("Loading menus...")
    # Загружаем кэши (они должны загрузиться автоматически при импорте, но на всякий случай)
    # menu_cache._load_delivery_cache()
    # menu_cache._load_all_menus_cache()
    
    # Если кэши пустые, пробуем load_all_menus, но с force_update=False чтобы читать с диска
    if not menu_cache.delivery_menus_cache:
        await menu_cache.load_all_menus(force_update=False)

    print(f"DELIVERY MENUS ({len(menu_cache.delivery_menus_cache)}): {list(menu_cache.delivery_menus_cache.keys())}")
    for mid, mdata in menu_cache.delivery_menus_cache.items():
        print(f"  Menu {mid}: {mdata.get('name')}")
        for cid, cdata in mdata.get('categories', {}).items():
            print(f"    - {cdata.get('name')} (ID: {cid})")

    print(f"ALL MENUS ({len(menu_cache.all_menus_cache)}): {list(menu_cache.all_menus_cache.keys())}")
    for mid, mdata in menu_cache.all_menus_cache.items():
        # Не выводим дубликаты из доставки для краткости, если они те же
        if mid not in menu_cache.delivery_menus_cache:
            print(f"  Menu {mid}: {mdata.get('name')}")
            for cid, cdata in mdata.get('categories', {}).items():
                print(f"    - {cdata.get('name')} (ID: {cid})")

if __name__ == "__main__":
    asyncio.run(main())
