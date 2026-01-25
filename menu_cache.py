"""
menu_cache.py - ОБНОВЛЕННЫЙ
Кэширование меню из Presto API
"""

import json
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import asyncio
import pytz

import config
import database
from presto_api import presto_api

logger = logging.getLogger(__name__)

class MenuCache:
    """Класс для кэширования меню"""

    def __init__(self):
        self.cache_file = config.MENU_CACHE_FILE  # Для меню доставки
        self.all_menus_cache_file = os.path.join(os.path.dirname(self.cache_file), 'all_menus_cache.json')  # Для всех меню
        self.images_dir = config.MENU_IMAGES_DIR
        self.all_menus_cache = {}  # Хранит все меню
        self.delivery_menus_cache = {}  # Хранит только меню доставки
        self.last_update = None
        self.cache_ttl = 3600  # 1 час
        self.moscow_tz = pytz.timezone('Europe/Moscow')

        # Создаем директории
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)

        # Загружаем точку продаж из БД если есть
        self._load_point_id_from_db()

        # Загружаем кэши при инициализации
        self._load_delivery_cache()
        self._load_all_menus_cache()
        
        # ВАЖНО: Объединяем кэши в памяти, чтобы all_menus_cache содержал 
        # и меню доставки (90, 92, 141), и барные меню (32, 29)
        if self.delivery_menus_cache:
            self.all_menus_cache.update(self.delivery_menus_cache)
            logger.info(f"✅ Кэши объединены. Всего меню в памяти: {len(self.all_menus_cache)}")
    
    def _load_point_id_from_db(self):
        """Загрузка ID точки продаж из базы данных"""
        point_id_str = database.get_setting('presto_point_id')
        if point_id_str:
            try:
                presto_api.point_id = int(point_id_str)
                logger.info(f"📌 ID точки продаж загружен из БД: {presto_api.point_id}")
            except (ValueError, TypeError):
                logger.warning("⚠️ Неверный формат ID точки в БД")
    
    def _load_delivery_cache(self):
        """Загрузка кэша меню доставки из файла"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # Проверяем время кэша
                cache_time_str = cache_data.get('timestamp')
                if cache_time_str:
                    cache_time = datetime.fromisoformat(cache_time_str)

                    # Проверяем не устарел ли кэш
                    if (datetime.now() - cache_time).total_seconds() < self.cache_ttl:
                        self.delivery_menus_cache = cache_data.get('all_menus', {})
                        self.last_update = cache_time

                        # Также загружаем point_id из кэша если есть
                        cached_point_id = cache_data.get('point_id')
                        if cached_point_id and not presto_api.point_id:
                            presto_api.point_id = cached_point_id

                        logger.info(f"✅ Меню доставки загружены из кэша ({len(self.delivery_menus_cache)} меню)")
                        return True
                    else:
                        logger.info("🔄 Кэш меню доставки устарел, требуется обновление")
                else:
                    logger.warning("⚠️ Кэш меню доставки без timestamp, требуется обновление")

            return False

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки кэша меню доставки: {e}")
            return False

    def _load_all_menus_cache(self):
        """Загрузка кэша всех меню из файла"""
        try:
            if os.path.exists(self.all_menus_cache_file):
                with open(self.all_menus_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # Проверяем время кэша
                cache_time_str = cache_data.get('timestamp')
                if cache_time_str:
                    cache_time = datetime.fromisoformat(cache_time_str)

                    # Проверяем не устарел ли кэш
                    if (datetime.now() - cache_time).total_seconds() < self.cache_ttl:
                        self.all_menus_cache = cache_data.get('all_menus') or {}
                        logger.info(f"✅ Все меню загружены из кэша ({len(self.all_menus_cache)} меню)")
                        return True
                    else:
                        logger.info("🔄 Кэш всех меню устарел, требуется обновление")

            return False

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки кэша всех меню: {e}")
            return False

    def _save_delivery_cache(self):
        """Сохранение кэша меню доставки в файл"""
        try:
            # Фильтруем только меню доставки
            delivery_menu_ids = {90, 92, 141}
            filtered_menus = {}
            
            for k, v in self.all_menus_cache.items():
                try:
                    # Приводим ключ к int для проверки
                    k_int = int(k)
                    if k_int in delivery_menu_ids:
                        filtered_menus[str(k)] = v
                except (ValueError, TypeError):
                    continue
            
            # Обновляем кэш в памяти
            self.delivery_menus_cache = filtered_menus

            cache_data = {
                'timestamp': self.last_update.isoformat() if self.last_update else datetime.now().isoformat(),
                'point_id': presto_api.point_id,
                'all_menus': filtered_menus
            }

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ Меню доставки сохранены в кэш ({len(filtered_menus)} меню)")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения кэша меню доставки: {e}")
            return False

    def _save_all_menus_cache(self):
        """Сохранение кэша доп. меню (бар/алкоголь) в файл all_menus_cache.json"""
        try:
            # Фильтруем: оставляем только 32 и 29
            allowed_ids = {32, 29}
            filtered_menus = {}
            
            for k, v in self.all_menus_cache.items():
                try:
                    k_int = int(k)
                    if k_int in allowed_ids:
                        filtered_menus[str(k)] = v
                except (ValueError, TypeError):
                    continue

            cache_data = {
                'timestamp': self.last_update.isoformat() if self.last_update else datetime.now().isoformat(),
                'point_id': presto_api.point_id,
                'all_menus': filtered_menus
            }

            with open(self.all_menus_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ Доп. меню (32, 29) сохранены в кэш ({len(filtered_menus)} меню)")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения кэша всех меню: {e}")
            return False
    
    async def load_all_menus(self, force_update: bool = False) -> Dict:
        """
        Загружает все меню из API

        Args:
            force_update: Принудительное обновление

        Returns:
            Словарь со всеми меню
        """
        # Проверяем нужно ли обновлять
        if (force_update or
            not self.all_menus_cache or
            not self.last_update or
            (datetime.now() - self.last_update).total_seconds() > self.cache_ttl):

            logger.info("🔄 Загрузка всех меню из API...")

            try:
                # Получаем все меню из API
                menus = await presto_api.get_all_menus()

                if menus:
                    # Оставляем только нужные меню в памяти (доставка + бар)
                    # Доставка: 90, 92, 141
                    # Бар: 32, 29
                    allowed_ids = {90, 92, 141, 32, 29}
                    filtered_menus = {}
                    for k, v in menus.items():
                        try:
                            if int(k) in allowed_ids:
                                filtered_menus[str(k)] = v
                        except: continue

                    self.all_menus_cache = filtered_menus
                    self.last_update = datetime.now()
                    
                    # Сохраняем кэши (каждый метод сам возьмет что ему нужно из self.all_menus_cache)
                    self._save_delivery_cache()
                    self._save_all_menus_cache()

                    logger.info(f"✅ Загружено {len(filtered_menus)} меню (фильтр):")
                    for menu_id, menu_data in filtered_menus.items():
                        categories_count = len(menu_data.get('categories', {}))
                        total_items = sum(len(cat['items']) for cat in menu_data.get('categories', {}).values())
                        logger.info(f"   • {menu_data['name']}: {categories_count} категорий, {total_items} товаров")

                    return filtered_menus
                else:
                    logger.warning("⚠️ Не удалось загрузить меню из API")
                    # Возвращаем старый кэш если есть
                    if self.all_menus_cache:
                        return self.all_menus_cache

            except Exception as e:
                logger.error(f"❌ Ошибка загрузки меню: {e}")
                # Возвращаем старый кэш если есть
                if self.all_menus_cache:
                    return self.all_menus_cache

        return self.all_menus_cache
    
    def get_available_menus(self) -> List[Dict]:
        """Получает доступные меню для доставки с учетом времени"""
        current_time = datetime.now(self.moscow_tz).time()

        # Меню доступные для доставки/заказа
        delivery_menu_ids = {90, 92, 141}  # Только эти меню для доставки

        available_menus = []

        for menu_id, menu_data in self.all_menus_cache.items():
            # Проверяем, что меню в списке доставочных
            if menu_id not in delivery_menu_ids:
                continue

            menu_name = menu_data.get('name', '')

            # Проверяем время для завтраков (ID 90)
            if menu_id == 90:
                from datetime import time
                if current_time > time(16, 0):  # После 16:00
                    continue  # Пропускаем завтраки

            available_menus.append({
                'id': menu_id,
                'name': menu_name,
                'categories_count': len(menu_data.get('categories', {})),
                'total_items': sum(len(cat['items']) for cat in menu_data.get('categories', {}).values())
            })

        return available_menus

    def get_bar_menus(self) -> List[Dict]:
        """Получает меню бара (алкогольные напитки)"""
        # Меню бара
        bar_menu_ids = {29, 91, 86, 32}  # ДЕСЕРТЫ БАР, МЕНЮ КУХНЯ, НАПИТКИ 25, МЕНЮ АЛКОГОЛЬ

        bar_menus = []

        for menu_id, menu_data in self.all_menus_cache.items():
            if menu_id not in bar_menu_ids:
                continue

            menu_name = menu_data.get('name', '')

            bar_menus.append({
                'id': menu_id,
                'name': menu_name,
                'categories_count': len(menu_data.get('categories', {})),
                'total_items': sum(len(cat['items']) for cat in menu_data.get('categories', {}).values()),
                'is_alcoholic': menu_id == 32  # МЕНЮ АЛКОГОЛЬ
            })

        return bar_menus
    
    def get_menu_categories(self, menu_id: int) -> List[Dict]:
        """Получает категории конкретного меню"""
        if menu_id not in self.all_menus_cache:
            return []
    
        menu_data = self.all_menus_cache[menu_id]
        categories = []
    
        for cat_id, cat_data in menu_data.get('categories', {}).items():
            # ИСПРАВЛЕНИЕ: используем display_name если есть
            display_name = cat_data.get('display_name') or cat_data.get('name', 'Без названия')
        
            category_info = {
                'id': cat_id,
                'name': cat_data.get('name', 'Без названия'),
                'display_name': display_name,  # ← ДОБАВЛЯЕМ display_name!
                'item_count': len(cat_data.get('items', [])),
                'menu_id': menu_id,
                'menu_name': menu_data.get('name', '')
            }
            categories.append(category_info)
    
        # УБИРАЕМ СОРТИРОВКУ ПО АЛФАВИТУ! Оставляем как есть
        # categories.sort(key=lambda x: x['name'])  ← УДАЛИТЬ ЭТУ СТРОКУ!
        return categories
    
    def get_category_items(self, menu_id: int, category_id: int) -> List[Dict]:
        """Получает товары категории"""
        if (menu_id not in self.all_menus_cache or 
            category_id not in self.all_menus_cache[menu_id].get('categories', {})):
            return []
        
        category_data = self.all_menus_cache[menu_id]['categories'][category_id]
        return category_data.get('items', [])
    
    def get_dish_by_id(self, menu_id: int, dish_id: int) -> Optional[Dict]:
        """Поиск блюда по ID в меню"""
        if menu_id not in self.all_menus_cache:
            return None
        
        for cat_id, cat_data in self.all_menus_cache[menu_id].get('categories', {}).items():
            for dish in cat_data.get('items', []):
                if dish.get('id') == dish_id:
                    # Копируем и добавляем информацию о категории и меню
                    dish_copy = dish.copy()
                    dish_copy['category_id'] = cat_id
                    dish_copy['category_name'] = cat_data.get('name', '')
                    dish_copy['menu_id'] = menu_id
                    dish_copy['menu_name'] = self.all_menus_cache[menu_id].get('name', '')
                    return dish_copy
        
        return None
    
    def get_dish_by_index(self, menu_id: int, category_id: int, dish_index: int) -> Optional[Dict]:
        """Получение блюда по индексу в категории"""
        items = self.get_category_items(menu_id, category_id)
        
        if 0 <= dish_index < len(items):
            dish = items[dish_index].copy()
            dish['category_id'] = category_id
            dish['menu_id'] = menu_id
            
            # Добавляем информацию о категории и меню
            if menu_id in self.all_menus_cache:
                menu_data = self.all_menus_cache[menu_id]
                dish['menu_name'] = menu_data.get('name', '')
                
                if category_id in menu_data.get('categories', {}):
                    dish['category_name'] = menu_data['categories'][category_id].get('name', '')
            
            return dish
        
        return None
    
    def search_dishes(self, search_text: str, menu_id: Optional[int] = None) -> List[Dict]:
        """Поиск блюд по названию"""
        if not search_text:
            return []
        
        search_lower = search_text.lower()
        results = []
        seen_ids = set() # Чтобы не дублировать блюда

        # 1. Сначала ищем в кэше доставки (menu_cache.json) - ПРИОРИТЕТ
        # Если menu_id указан, ищем только если он в доставке. Если не указан - ищем во всей доставке.
        delivery_menus_to_search = []
        if menu_id:
             # Проверяем как str, так и int
             if str(menu_id) in self.delivery_menus_cache:
                 delivery_menus_to_search = [str(menu_id)]
             elif int(menu_id) in self.delivery_menus_cache: # На случай если ключи int
                 delivery_menus_to_search = [int(menu_id)]
        else:
             delivery_menus_to_search = list(self.delivery_menus_cache.keys())

        for m_id in delivery_menus_to_search:
            menu_data = self.delivery_menus_cache.get(m_id)
            if not menu_data: continue

            for cat_id, cat_data in menu_data.get('categories', {}).items():
                for dish in cat_data.get('items', []):
                    dish_name = dish.get('name', '').lower()
                    dish_desc = dish.get('description', '').lower()
                    
                    if (search_lower in dish_name or search_lower in dish_desc):
                        dish_id = dish.get('id')
                        if dish_id in seen_ids: continue
                        
                        dish_copy = dish.copy()
                        dish_copy['category_id'] = cat_id
                        dish_copy['category_name'] = cat_data.get('name', '')
                        dish_copy['menu_id'] = m_id
                        dish_copy['menu_name'] = menu_data.get('name', '')
                        results.append(dish_copy)
                        seen_ids.add(dish_id)

        # 2. Потом ищем в общем кэше (all_menus_cache.json), пропуская уже найденные
        menus_to_search = [menu_id] if menu_id else self.all_menus_cache.keys()
        
        for m_id in menus_to_search:
            # Пропускаем, если уже искали это меню в доставке (чтобы не дублировать логику)
            # Но если all_menus_cache содержит более полную версию (маловероятно), то можно и посмотреть.
            # Однако наша цель - приоритет доставки. Если мы нашли блюдо в доставке, мы его уже добавили.
            # Если в all_menus_cache есть блюдо с таким же ID, мы его пропустим (seen_ids).
            
            if m_id not in self.all_menus_cache:
                continue
            
            for cat_id, cat_data in self.all_menus_cache[m_id].get('categories', {}).items():
                for dish in cat_data.get('items', []):
                    dish_name = dish.get('name', '').lower()
                    dish_desc = dish.get('description', '').lower()
                    
                    if (search_lower in dish_name or search_lower in dish_desc):
                        dish_id = dish.get('id')
                        if dish_id in seen_ids: continue # Уже нашли в приоритетном кэше
                        
                        dish_copy = dish.copy()
                        dish_copy['category_id'] = cat_id
                        dish_copy['category_name'] = cat_data.get('name', '')
                        dish_copy['menu_id'] = m_id
                        dish_copy['menu_name'] = self.all_menus_cache[m_id].get('name', '')
                        results.append(dish_copy)
                        seen_ids.add(dish_id)
        
        return results
    
    def clear_cache(self) -> bool:
        """Очистка кэша"""
        try:
            self.all_menus_cache = {}
            self.last_update = None
            
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            
            # Также удаляем сохраненный point_id из БД
            database.update_setting('presto_point_id', '')
            
            logger.info("✅ Кэш меню очищен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки кэша: {e}")
            return False

    def get_category_by_id(self, menu_id: int, category_id: int) -> Optional[Dict]:
        """Получает категорию по ID"""
        if menu_id not in self.all_menus_cache:
            return None
        
        menu_data = self.all_menus_cache[menu_id]
        categories = menu_data.get('categories', {})
        
        if category_id not in categories:
            return None
        
        cat_data = categories[category_id]
        
        # Проверяем есть ли display_name
        name = cat_data.get('name', '')
        display_name = cat_data.get('display_name', name)
        
        return {
            'id': category_id,
            'name': name,
            'display_name': display_name,
            'item_count': len(cat_data.get('items', [])),
            'image_url': cat_data.get('image_url')
        }

# Глобальный экземпляр кэша меню
menu_cache = MenuCache()
