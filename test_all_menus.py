import asyncio
from menu_cache import menu_cache

async def test():
    print('🔄 Загружаем все меню...')
    menus = await menu_cache.load_all_menus(force_update=True)
    print(f'✅ Загружено {len(menus)} меню')

    for menu_id, menu in menus.items():
        categories = menu.get('categories', {})
        total_items = sum(len(cat.get('items', [])) for cat in categories.values())
        print(f'  • Меню {menu_id} ({menu.get("name", "Без названия")}): {len(categories)} категорий, {total_items} блюд')

asyncio.run(test())
