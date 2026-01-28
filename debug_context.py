
import json
import os
import logging
from menu_cache import ALLOWED_MENU_IDS

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_menu_cache():
    """Загрузка кэша всех меню для AI с приоритетом доставки"""
    try:
        all_menus = {}
        
        # 1. Сначала загружаем меню доставки (menu_cache.json) - ЭТО ПРИОРИТЕТ
        delivery_cache_file = 'files/menu_cache.json'
        if os.path.exists(delivery_cache_file):
            try:
                with open(delivery_cache_file, 'r', encoding='utf-8') as f:
                    delivery_data = json.load(f)
                    delivery_menus = delivery_data.get('all_menus', {})
                    if delivery_menus:
                        all_menus.update(delivery_menus)
                        logger.info(f"AI: Загружено {len(delivery_menus)} меню из кэша доставки")
                    else:
                        logger.warning("AI: Кэш доставки пуст (all_menus)")
            except Exception as e:
                logger.error(f"AI: Ошибка загрузки menu_cache.json: {e}")
        else:
            logger.warning(f"AI: Файл {delivery_cache_file} не найден")

        # 2. Затем загружаем общий кэш (all_menus_cache.json) и добавляем то, чего нет
        all_cache_file = 'files/all_menus_cache.json'
        if os.path.exists(all_cache_file):
            try:
                with open(all_cache_file, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
                    other_menus = all_data.get('all_menus', {})
                    
                    # Добавляем только те меню, которых еще нет, И КОТОРЫЕ РАЗРЕШЕНЫ
                    for m_id, m_data in other_menus.items():
                        try:
                            # 🛑 STRICT FILTER: Skip menus not in whitelist
                            if int(m_id) not in ALLOWED_MENU_IDS:
                                continue
                        except:
                            continue
                            
                        if m_id not in all_menus:
                            all_menus[m_id] = m_data
                            
                    logger.info(f"AI: Догружено из общего кэша. Всего меню: {len(all_menus)}")
            except Exception as e:
                logger.error(f"AI: Ошибка загрузки all_menus_cache.json: {e}")
        else:
             logger.warning(f"AI: Файл {all_cache_file} не найден")

        return all_menus
    except Exception as e:
        logger.error(f"Ошибка загрузки кэша меню для AI: {e}")
        return {}

def generate_context():
    menu_data = load_menu_cache()
    if not menu_data:
        logger.error("Menu data is empty!")
        return

    menu_knowledge_base = []
    target_menu_ids = sorted(list(ALLOWED_MENU_IDS))
    
    all_categories = set()

    for menu_id in target_menu_ids:
        menu_key = str(menu_id)
        if menu_key in menu_data:
            menu = menu_data[menu_key]
        elif menu_id in menu_data:
            menu = menu_data[menu_id]
        else:
            logger.warning(f"Menu ID {menu_id} not found in loaded data")
            continue

        menu_name = menu.get('name', '').strip()
        logger.info(f"Processing menu: {menu_name} (ID: {menu_id})")
        
        menu_section = {
            "menu_name": menu_name,
            "categories": []
        }

        for category_id, category in menu.get('categories', {}).items():
            category_name = category.get('name', '').strip()
            all_categories.add(category_name)
            
            # 🛑 Исключаем категории добавок, модификаторов и конструкторов из контекста AI
            if any(bad_word in category_name.lower() for bad_word in ['добавки', 'модификаторы', 'топпинги', 'соусы к', 'дополнительно', 'конструктор']):
                continue

            category_data = {
                "category_name": category_name,
                "items": []
            }

            items = category.get('items', [])
            items = [item for item in items if float(item.get('price', 0)) > 0]
            
            for item in items[:5]:
                dish_info = {
                    "name": item['name'],
                    "price": item['price']
                }
                category_data["items"].append(dish_info)
            
            menu_section["categories"].append(category_data)
        
        menu_knowledge_base.append(menu_section)

    print("\nALL CATEGORIES FOUND:")
    for cat in sorted(all_categories):
        print(f"- {cat}")

    with open('menu_context.json', 'w', encoding='utf-8') as f:
        json.dump(menu_knowledge_base, f, ensure_ascii=False, indent=2)
    print("\nSaved to menu_context.json")

if __name__ == "__main__":
    generate_context()
