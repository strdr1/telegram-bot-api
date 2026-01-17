# debug_categories.py - для отладки категорий
import asyncio
import logging
from presto_api import PrestoAPI

# Настройка логов
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def debug_categories():
    """Функция для отладки категорий"""
    api = PrestoAPI()
    await api.init_session()
    
    # Загружаем конкретное меню
    menu = await api.get_menu_by_id(92)  # Основное меню
    
    if menu:
        print("\n" + "="*80)
        print("ДЕБАГ КАТЕГОРИЙ МЕНЮ 92:")
        print("="*80)
        
        print(f"Всего категорий: {len(menu)}\n")
        
        for cat_id, cat_data in menu.items():
            print(f"📋 КАТЕГОРИЯ:")
            print(f"  • ID: {cat_id}")
            print(f"  • Display Name: {cat_data.get('display_name', 'НЕТ')}")
            print(f"  • Оригинальное имя: {cat_data.get('name', 'НЕТ')}")
            print(f"  • Parent ID: {cat_data.get('parent_id')}")
            print(f"  • Товаров: {len(cat_data.get('items', []))}")
            
            # Выводим первые 3 товара для проверки
            if cat_data.get('items'):
                print(f"  • Примеры товаров:")
                for i, item in enumerate(cat_data['items'][:3]):
                    print(f"    {i+1}. {item.get('name')} - {item.get('price')}₽")
            print("-"*40)
    
    await api.close_session()

async def debug_raw_api():
    """Отладочная функция для просмотра сырых данных API"""
    api = PrestoAPI()
    await api.init_session()
    
    print("\n" + "="*80)
    print("ЗАГРУЗКА СЫРЫХ ДАННЫХ ИЗ API:")
    print("="*80)
    
    params = {
        'pointId': api.point_id,
        'priceListId': 92,
        'pageSize': 1000,
        'withBalance': 'true',
        'product': 'delivery'
    }
    
    url = f"{api.base_url}/nomenclature/list"
    
    try:
        async with api.session.get(url, params=params) as response:
            response_text = await response.text()
            
            print(f"Статус: {response.status}")
            print(f"Заголовки: {response.headers}")
            
            # Сохраняем сырые данные в файл
            with open("debug_raw_api.json", "w", encoding="utf-8") as f:
                f.write(response_text)
            print("📁 Сырые данные сохранены в debug_raw_api.json")
            
            # Парсим JSON
            import json
            data = json.loads(response_text)
            
            # Ищем все элементы с isParent = True
            print("\n🔍 ПОИСК КАТЕГОРИЙ В СЫРЫХ ДАННЫХ:")
            print("-"*40)
            
            categories_found = []
            for item in data.get('nomenclatures', []):
                if item.get('isParent', False):
                    category_info = {
                        'id': item.get('hierarchicalId'),
                        'name': item.get('name'),
                        'hierarchicalParent': item.get('hierarchicalParent'),
                        'cost': item.get('cost'),
                        'externalId': item.get('externalId')
                    }
                    categories_found.append(category_info)
                    
                    print(f"📁 Категория:")
                    print(f"  • Name: {item.get('name')}")
                    print(f"  • HierarchicalId: {item.get('hierarchicalId')}")
                    print(f"  • HierarchicalParent: {item.get('hierarchicalParent')}")
                    print(f"  • Cost: {item.get('cost')}")
                    print(f"  • ExternalId: {item.get('externalId')}")
                    print(f"  • IsParent: {item.get('isParent')}")
                    print("-"*30)
            
            print(f"\n✅ Всего найдено категорий: {len(categories_found)}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    await api.close_session()

if __name__ == "__main__":
    print("🚀 Запуск отладки категорий...")
    # asyncio.run(debug_categories())
    asyncio.run(debug_raw_api())