import asyncio
from menu_cache import menu_cache

async def test():
    print('🔄 Проверяем загруженные меню бара...')
    bar_menus = menu_cache.get_bar_menus()
    print(f'✅ Меню бара: {len(bar_menus)}')

    for menu in bar_menus:
        print(f'  • {menu["name"]} (ID {menu["id"]}): {menu["categories_count"]} категорий, {menu["total_items"]} блюд')

    # Тестируем AI с алкоголем
    print('\n🔄 Тестируем AI с запросом про алкоголь...')
    from ai_assistant import get_ai_response
    result = await get_ai_response("Какие у вас коктейли?", 123456)
    print(f'Ответ AI: {result["text"][:200]}...')
    print(f'Маркер возраста: {result.get("confirm_age_verification", False)}')

asyncio.run(test())
