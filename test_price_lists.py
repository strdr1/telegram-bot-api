import asyncio
from presto_api import presto_api

async def test_price_lists():
    print('🔄 Получаем список всех прайс-листов...')
    price_lists = await presto_api.get_price_lists()

    print(f'✅ Найдено {len(price_lists)} прайс-листов:')

    for pl in price_lists:
        pl_id = pl.get('id')
        pl_name = pl.get('name', 'Без названия')
        print(f'   • ID {pl_id}: {pl_name}')

    # Ищем конкретные меню
    target_menus = ['НАПИТКИ 25', 'МЕНЮ КУХНЯ', 'ДЕСЕРТЫ БАР']
    found_menus = []

    for pl in price_lists:
        pl_name = pl.get('name', '').upper()
        for target in target_menus:
            if target.upper() in pl_name or pl_name in target.upper():
                found_menus.append((pl.get('id'), pl.get('name')))
                break

    print(f'\n🎯 Искомые меню:')
    for menu_id, menu_name in found_menus:
        print(f'   • Найдено: ID {menu_id} - {menu_name}')

    missing = [m for m in target_menus if not any(m.upper() in pl.get('name', '').upper() or pl.get('name', '').upper() in m.upper() for pl in price_lists)]
    if missing:
        print(f'   • Не найдены: {missing}')

asyncio.run(test_price_lists())
