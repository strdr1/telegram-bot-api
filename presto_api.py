import json
import logging
import asyncio
import aiohttp
import base64
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import config
import database

logger = logging.getLogger(__name__)

class PrestoAPI:
    """Класс для работы с API Presto"""
    
    def __init__(self):
        self.access_token = config.PRESTO_ACCESS_TOKEN
        self.point_id = 3596  # MASHKOV.REST
        self.base_url = "https://api.sbis.ru/retail"
        self.session = None
        
        # Меню для загрузки
        self.menus = {
            90: "🍳 ЗАВТРАКИ (до 16:00)",
            92: "📋 ОСНОВНОЕ МЕНЮ",
            141: "🧀 СЫРНАЯ КАРТА"
        }
        
        # Кэш промокодов (id: code)
        self.promocodes = {}
        
        logger.info(f"🔌 Инициализация PrestoAPI")
        logger.info(f"   Точка ID: {self.point_id} (MASHKOV.REST)")
    
    async def init_session(self):
        """Инициализация сессии"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            )
    
    async def close_session(self):
        """Закрытие сессии"""
        if self.session:
            await self.session.close()
            self.session = None
    
    # ===== ФУНКЦИИ ДЛЯ РАБОТЫ С АДРЕСАМИ И ДОСТАВКОЙ =====
    
    async def suggest_address(self, address: str, 
                         apartment: str = '', 
                         entrance: str = '', 
                         floor: str = '', 
                         door_code: str = '',
                         locality: str = 'Москва') -> List[Dict]:
        """
        Корректировка адреса через API Presto
        GET /delivery/suggested-address
        """
        try:
            await self.init_session()
        
            url = f"{self.base_url}/delivery/suggested-address"
        
            # Добавляем город к запросу для точного поиска
            if not any(city in address.lower() for city in ['москва', 'мск', 'moscow']):
                search_address = f"Москва, {address}"
            else:
                search_address = address
        
            params = {
                'address': search_address,
                'aptNum': apartment,
                'entrance': entrance,
                'floor': floor,
                'doorCode': door_code,
                'pageSize': 10
            }
        
            logger.info(f"📍 Корректировка адреса: {search_address}")
        
            async with self.session.get(url, params=params) as response:
                response_text = await response.text()
            
                if response.status == 200:
                    data = await response.json()
                    addresses = data.get('addresses', [])
                
                    logger.info(f"✅ Найдено {len(addresses)} вариантов адреса")
                
                    # Фильтруем московские адреса
                    moscow_addresses = []
                    for addr in addresses:
                        address_full = addr.get('addressFull', '').lower()
                        if any(moscow_keyword in address_full 
                               for moscow_keyword in ['москва', 'мск', 'moscow', 'moskva']):
                            moscow_addresses.append(addr)
                
                    if not moscow_addresses and addresses:
                        moscow_addresses = [addresses[0]]
                
                    return moscow_addresses
                    
        except Exception as e:
            logger.error(f"❌ Ошибка корректировки адреса: {e}")
            return []
    
    async def get_delivery_districts(self, with_coordinates: bool = True) -> List[Dict]:
        """
        Получение списка районов доставки
        GET /district/list
        """
        try:
            await self.init_session()
        
            url = f"{self.base_url}/district/list"
        
            params = {
                'pointId': self.point_id,
                'withCoordinates': 'true' if with_coordinates else 'false'
            }
        
            logger.info(f"📍 Запрос списка районов доставки...")
        
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    districts = data.get('districts', [])
                
                    logger.info(f"✅ Получено {len(districts)} районов доставки")
                    return districts
                else:
                    logger.error(f"❌ Ошибка получения районов: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения районов: {e}")
            return []
    
    async def reverse_geocode(self, latitude: float, longitude: float) -> Optional[str]:
        """Обратное геокодирование через DaData"""
        try:
            DADATA_API_KEY = config.DADATA_API_KEY
            DADATA_SECRET_KEY = config.DADATA_SECRET_KEY
        
            if not DADATA_API_KEY or not DADATA_SECRET_KEY:
                logger.warning("⚠️ Нет ключей DaData для обратного геокодирования")
                return f"{latitude:.6f}, {longitude:.6f}"
        
            url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/geolocate/address"
        
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Token {DADATA_API_KEY}",
                "X-Secret": DADATA_SECRET_KEY
            }
        
            data = {
                "lat": latitude,
                "lon": longitude,
                "count": 1,
                "radius_meters": 100
            }
        
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                    
                        if result.get('suggestions') and len(result['suggestions']) > 0:
                            address = result['suggestions'][0].get('value', '')
                            logger.info(f"📍 DaData обратное геокодирование: {latitude}, {longitude} → {address}")
                            return address
        
            return f"{latitude:.6f}, {longitude:.6f}"
        
        except Exception as e:
            logger.error(f"❌ Ошибка обратного геокодирования: {e}")
            return f"{latitude:.6f}, {longitude:.6f}"

    async def geocode_address(self, address: str) -> Optional[Dict[str, float]]:
        """
        Геокодирование через DaData API с очисткой кэша
        """
        try:
            DADATA_API_KEY = config.DADATA_API_KEY
            DADATA_SECRET_KEY = config.DADATA_SECRET_KEY
        
            logger.info(f"📍 Геокодирование адреса: {address}")
        
            url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
        
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Token {DADATA_API_KEY}",
                "X-Secret": DADATA_SECRET_KEY
            }
        
            # Добавляем параметр для отключения кэша
            data = {
                "query": address,
                "count": 1,
                "language": "ru",
                "locations": [
                    {"kladr_id": "7700000000000"},  # Москва
                    {"kladr_id": "5000000000000"}   # Московская область
                ],
                "restrict_value": True,
                "from_bound": {"value": "street"},  # Точнее геокодирование
                "to_bound": {"value": "house"}      # До дома
            }
        
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                    
                        if result.get('suggestions') and len(result['suggestions']) > 0:
                            suggestion = result['suggestions'][0]
                            suggestion_data = suggestion.get('data', {})
                        
                            # Детальный логинг
                            logger.info(f"📍 DaData результат для '{address}':")
                            logger.info(f"   📍 Полный адрес: {suggestion.get('value')}")
                            logger.info(f"   📍 Регион: {suggestion_data.get('region')}")
                            logger.info(f"   📍 Город: {suggestion_data.get('city')}")
                            logger.info(f"   📍 Улица: {suggestion_data.get('street')}")
                            logger.info(f"   📍 Дом: {suggestion_data.get('house')}")
                        
                            geo_lat = suggestion_data.get('geo_lat')
                            geo_lon = suggestion_data.get('geo_lon')
                        
                            if geo_lat and geo_lon:
                                lat = float(geo_lat)
                                lon = float(geo_lon)
                                logger.info(f"✅ Координаты найдены: {lat:.6f}, {lon:.6f}")
                                return {'lat': lat, 'lon': lon}
                            else:
                                logger.warning(f"⚠️ DaData не вернул координаты для '{address}'")
        
            # Если DaData не нашел, используем упрощенное геокодирование как запасной вариант
            logger.info(f"📍 Используем упрощенное геокодирование для: {address}")
            return self._simple_geocode(address)
            
        except Exception as e:
            logger.error(f"❌ Ошибка геокодирования: {e}")
            return {'lat': 55.7558, 'lon': 37.6176}
    
    def _simple_geocode(self, address: str) -> Dict[str, float]:
        """Упрощенное геокодирование"""
        address_lower = address.lower()
        
        if any(keyword in address_lower for keyword in ['долгопруд']):
            return {'lat': 55.9300, 'lon': 37.5200}
        elif any(keyword in address_lower for keyword in ['химки']):
            return {'lat': 55.8880, 'lon': 37.4300}
        elif any(keyword in address_lower for keyword in ['зеленоград']):
            return {'lat': 55.9825, 'lon': 37.1814}
        elif any(keyword in address_lower for keyword in ['ландау']):
            return {'lat': 55.9202547, 'lon': 37.5502152}
        else:
            return {'lat': 55.7558, 'lon': 37.6176}
    
    def calculate_delivery_cost_simple(self, district: Dict, cart_total: float, original_cart_total: float = None) -> Tuple[float, str]:
        """
        Расчет стоимости доставки
        
        cart_total: сумма заказа после применения скидки
        original_cart_total: исходная сумма заказа без учета скидки (для проверки порога)
        """
        try:
            logger.info(f"📊 Расчет доставки: сумма со скидкой {cart_total}₽")
            if original_cart_total is not None:
                logger.info(f"📊 Исходная сумма для проверки порога: {original_cart_total}₽")
            
            # Используем оригинальную сумму для проверки порога, если она передана
            check_total = original_cart_total if original_cart_total is not None else cart_total
            
            logger.info(f"📊 Данные района: {json.dumps(district, default=str)[:500]}...")
            
            # Получаем базовую стоимость доставки
            base_cost = district.get('cost')
            logger.info(f"📊 base_cost = {base_cost}")
            
            # Проверяем порог бесплатной доставки
            free_delivery_threshold = district.get('costForFreeDelivery')
            if free_delivery_threshold is None:
                free_delivery_threshold = 3000.0
            else:
                free_delivery_threshold = float(free_delivery_threshold)
            
            # Проверяем thresholds если есть
            thresholds = district.get('sumThresholds', [])
            
            # ВАЖНОЕ ИЗМЕНЕНИЕ: Если есть thresholds, используем их в первую очередь
            if thresholds and isinstance(thresholds, list):
                logger.info(f"📊 Найдены пороги доставки: {thresholds}")
                
                # Находим подходящий порог (по исходной сумме!)
                sorted_thresholds = sorted(thresholds, key=lambda x: float(x.get('From', 0)))
                delivery_cost = None
                
                for threshold in sorted_thresholds:
                    threshold_from = float(threshold.get('From', 0))
                    threshold_price = threshold.get('Price')
                    
                    if threshold_price is None:
                        continue
                    
                    threshold_price = float(threshold_price)
                    
                    if check_total >= threshold_from:
                        delivery_cost = threshold_price
                        logger.info(f"✅ Применен порог: от {threshold_from}₽ = {threshold_price}₽")
                    else:
                        break
                
                # Если не нашли подходящий порог
                if delivery_cost is None:
                    if base_cost is not None:
                        delivery_cost = float(base_cost)
                    else:
                        # Если base_cost тоже None, значит доставка бесплатная от минимальной суммы
                        min_order_sum = district.get('minOrderSum', 1000)
                        logger.info(f"🎉 Район с бесплатной доставкой (минимальный заказ {min_order_sum}₽)")
                        return 0.0, f"🎉 Бесплатно (минимальный заказ {min_order_sum}₽)"
            else:
                # Если нет thresholds
                if base_cost is None:
                    # СПЕЦИАЛЬНЫЙ СЛУЧАЙ: Район "Соседи" - бесплатная доставка от минимальной суммы
                    min_order_sum = district.get('minOrderSum', 1000)
                    logger.info(f"🎉 Район с бесплатной доставкой (минимальный заказ {min_order_sum}₽)")
                    return 0.0, f"🎉 Бесплатно (минимальный заказ {min_order_sum}₽)"
                else:
                    delivery_cost = float(base_cost)
            
            # ВАЖНО: проверяем бесплатную доставку по сумме
            if check_total >= free_delivery_threshold:
                delivery_cost = 0
            
            # Форматируем текст
            return delivery_cost, f"{int(delivery_cost)}₽"
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета стоимости доставки: {e}")
            return 500.0, "500₽"

    @staticmethod
    def compare_menus(old_menu_data: Dict, new_menu_data: Dict) -> Dict:
        """
        Сравнение двух версий меню
        Возвращает статистику изменений
        """
        try:
            def extract_items(menu_data):
                items = {}
                for menu_id, menu in menu_data.items():
                    # Handle both dictionary and integer keys for menu_id
                    categories = menu.get('categories', {})
                    for cat_id, cat_data in categories.items():
                        for item in cat_data.get('items', []):
                            item_id = str(item.get('id'))
                            items[item_id] = {
                                'name': item.get('name'),
                                'price': item.get('price'),
                                'description': item.get('description', ''),
                                'menu_id': menu_id,
                                'category': cat_data.get('name')
                            }
                return items

            old_items = extract_items(old_menu_data)
            new_items = extract_items(new_menu_data)
            
            added_ids = set(new_items.keys()) - set(old_items.keys())
            removed_ids = set(old_items.keys()) - set(new_items.keys())
            common_ids = set(new_items.keys()) & set(old_items.keys())
            
            changed_items = []
            
            for item_id in common_ids:
                old = old_items[item_id]
                new = new_items[item_id]
                
                changes = []
                if old['price'] != new['price']:
                    changes.append(f"цена: {old['price']} -> {new['price']}")
                if old['name'] != new['name']:
                    changes.append(f"название")
                if old['description'] != new['description']:
                    changes.append(f"описание")
                    
                if changes:
                    changed_items.append({
                        'id': item_id,
                        'name': new['name'],
                        'changes': changes
                    })
            
            total_items = len(old_items) if old_items else len(new_items)
            total_changes = len(added_ids) + len(removed_ids) + len(changed_items)
            
            change_percent = (total_changes / total_items * 100) if total_items > 0 else 0
            
            return {
                'items_count': len(new_items),
                'added': [new_items[i] for i in added_ids],
                'removed': [old_items[i] for i in removed_ids],
                'changed': changed_items,
                'change_percent': round(change_percent, 2),
                'is_significant': False # Будет установлено позже на основе порога
            }
            
        except Exception as e:
            logger.error(f"Error comparing menus: {e}")
            return {
                'items_count': 0,
                'added': [],
                'removed': [],
                'changed': [],
                'change_percent': 0.0,
                'is_significant': False
            }
