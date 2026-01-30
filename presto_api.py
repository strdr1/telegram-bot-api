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
                    'X-SBISAccessToken': self.access_token,
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
                
                # Если не нашли подходящий порог, используем базовую стоимость
                if delivery_cost is None:
                    if base_cost is not None:
                        delivery_cost = float(base_cost)
                    else:
                        delivery_cost = 300.0  # Дефолтное значение
            else:
                # Если нет thresholds, используем базовую стоимость
                if base_cost is None:
                    delivery_cost = 300.0
                else:
                    delivery_cost = float(base_cost)
            
            # ВАЖНО: проверяем бесплатную доставку по сумме
            if check_total >= free_delivery_threshold:
                delivery_cost = 0
            
            # Убеждаемся, что delivery_cost не None
            if delivery_cost is None:
                delivery_cost = 300.0
            
            # Форматируем текст`nif delivery_cost == 0:`nlogger.info(f"🎉 Доставка бесплатная (заказ от {free_delivery_threshold}₽)")`nreturn 0.0, f"🎉 Бесплатно (от {free_delivery_threshold}₽)"`nelse:`nneed_for_free = free_delivery_threshold - check_total`nmin_order_sum = district.get('minOrderSum', 1000)`nif need_for_free > 0:`nlogger.info(f"💰 Стоимость доставки: {delivery_cost}₽ (нужно еще {need_for_free}₽ до бесплатной)")`nif base_cost is None and min_order_sum == 1000 and delivery_cost > 0:`nreturn float(delivery_cost), f"{delivery_cost:.0f}₽ (бесплатно от {min_order_sum}₽, минимальный заказ {min_order_sum}₽)"`nelse:`nreturn float(delivery_cost), f"{delivery_cost:.0f}₽ (бесплатно от {free_delivery_threshold}₽, добавьте еще {need_for_free:.0f}₽)"`nelse:`nreturn float(delivery_cost), f"{delivery_cost:.0f}₽"
        
        except Exception as e:
            logger.error(f"❌ Ошибка расчета доставки: {e}", exc_info=True)
            
            # Запасной вариант
            check_total_for_fallback = original_cart_total if original_cart_total is not None else cart_total
            if check_total_for_fallback >= 3000:
                return 0.0, "🎉 Бесплатно"
            else:
                return 300.0, "300₽"
            if check_total_for_fallback >= 3000:
                return 0.0, "🎉 Бесплатно"
            else:
                need_for_free = 3000 - check_total_for_fallback
                return 300.0, f"300₽ (бесплатно от 3000₽, добавьте ещё {need_for_free:.0f}₽)"
    
    async def create_delivery_order(self, customer_data: Dict, cart_items: List[Dict], 
                           delivery_data: Dict, comment: str = '', 
                           is_pickup: bool = False, 
                           discount_amount: float = 0,
                           discount_type: str = 'percent') -> Dict:
        """
        Создание заказа доставки с проверкой минимальной суммы
    
        Args:
            customer_data: данные клиента
            cart_items: товары в корзине
            delivery_data: данные доставки
            comment: комментарий к заказу
            is_pickup: самовывоз или доставка
            discount_amount: сумма скидки
            discount_type: тип скидки ('percent' или 'amount')
    
        Returns:
            Словарь с результатом создания заказа
        """
        try:
            await self.init_session()

            url = f"{self.base_url}/order/create"

            # Формируем позиции заказа
            nomenclatures = []
            total_order_amount = 0  # Исходная сумма без скидки
            total_after_discount = 0  # Сумма после скидки
    
            for item in cart_items:
                # Исходная цена товара
                item_price = float(item.get('price', 0))
                item_quantity = int(item.get('quantity', 1))
        
                nomenclature = {
                    'id': int(item.get('dish_id')),
                    'priceListId': 92,  # Основной priceListId
                    'count': item_quantity,
                    'cost': item_price,  # Отправляем оригинальную цену
                    'name': item.get('name', 'Товар')
                }
                nomenclatures.append(nomenclature)
        
                # Считаем общую сумму заказа (исходную)
                total_order_amount += item_price * item_quantity
    
            # Рассчитываем сумму после скидки
            total_after_discount = total_order_amount - discount_amount
            if total_after_discount < 0:
                total_after_discount = 0
    
            # КРИТИЧЕСКАЯ ПРОВЕРКА №1: минимальная сумма заказа для доставки
            if not is_pickup:  # Для доставки проверяем минималку
                # Используем сумму ПОСЛЕ скидки для проверки (как требует Presto API)
                MIN_ORDER_SUM = 1000.0  # Hardcoded из Presto API
            
                if total_after_discount < MIN_ORDER_SUM:
                    logger.error(f"❌ Сумма заказа после скидки {total_after_discount:.2f}₽ меньше минимальной {MIN_ORDER_SUM}₽")
                    return {
                        'error': f'Order amount after discount {total_after_discount:.2f}₽ is less than minimum {MIN_ORDER_SUM}₽',
                        'details': f'Minimum order amount for delivery is {MIN_ORDER_SUM}₽ (checked AFTER discount)',
                        'total_before_discount': total_order_amount,
                        'total_after_discount': total_after_discount,
                        'discount_amount': discount_amount,
                        'min_order_sum': MIN_ORDER_SUM,
                        'need_to_add': MIN_ORDER_SUM - total_after_discount
                    }
            
                logger.info(f"✅ Сумма заказа проверена: {total_after_discount:.2f}₽ (мин. {MIN_ORDER_SUM}₽)")
            else:
                logger.info(f"✅ Самовывоз: сумма заказа {total_after_discount:.2f}₽")
    
            # Формируем данные заказа
            order_data = {
                'product': 'delivery',
                'pointId': self.point_id,
                'comment': comment,
                'customer': {
                    'name': customer_data.get('name', 'Клиент'),
                    'lastname': customer_data.get('lastname', ''),
                    'email': customer_data.get('email', ''),
                    'phone': customer_data.get('phone', '')
                },
                'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'nomenclatures': nomenclatures,
                'delivery': {
                    'isPickup': is_pickup,
                    'paymentType': 'online',
                    'persons': 1
                },
                'totalAmount': total_after_discount  # Сумма после скидки для Presto
            }
    
            # Добавляем скидку если есть
            if discount_amount > 0:
                if discount_type == 'percent':
                    # Для процентной скидки
                    order_data['discount'] = {
                        'type': 'percent',
                        'value': discount_amount,  # процент скидки
                        'name': 'Промокод'
                    }
                else:
                    # Для фиксированной суммы
                    order_data['discount'] = {
                        'type': 'amount',
                        'value': discount_amount,  # сумма скидки в рублях
                        'name': 'Промокод'
                    }
        
            # Если не самовывоз, добавляем данные о доставке
            if not is_pickup:
                # Получаем координаты
                latitude = delivery_data.get('latitude', 55.7558)
                longitude = delivery_data.get('longitude', 37.6176)
            
                # Формируем адрес в правильном формате для Presto
                address_obj = {
                    'Address': delivery_data.get('address_full', delivery_data.get('address_text', '')),
                    'Locality': delivery_data.get('locality', 'Москва'),
                    'Coordinates': {
                        'Lat': float(latitude),
                        'Lon': float(longitude)
                    },
                    'AptNum': delivery_data.get('apartment', ''),
                    'Entrance': delivery_data.get('entrance', ''),
                    'Floor': delivery_data.get('floor', ''),
                    'DoorCode': delivery_data.get('door_code', '')
                }
            
                # Если есть JSON адрес, используем его
                if delivery_data.get('address_json'):
                    try:
                        address_obj = json.loads(delivery_data.get('address_json'))
                    except:
                        pass
            
                order_data['delivery']['addressJSON'] = json.dumps(address_obj, ensure_ascii=False)
            
                # Добавляем district если есть
                district_id = delivery_data.get('district_id')
                if district_id:
                    order_data['delivery']['district'] = district_id
        
            # URL для возврата после оплаты
            shop_url = "https://t.me/mashkov_rest_bot"
            success_url = f"https://t.me/mashkov_rest_bot?start=payment_success"
            error_url = f"https://t.me/mashkov_rest_bot?start=payment_error"

            order_data['delivery']['shopURL'] = shop_url
            order_data['delivery']['successURL'] = success_url
            order_data['delivery']['errorURL'] = error_url
    
            # Добавляем информацию о заказе из Telegram
            telegram_info = f"Заказ из Telegram бота. ID пользователя: {customer_data.get('user_id', 'N/A')}"
            if comment:
                telegram_info += f"\nКомментарий пользователя: {comment}"

            if 'comment' in order_data:
                order_data['comment'] = telegram_info + "\n" + order_data['comment']
            else:
                order_data['comment'] = telegram_info

            logger.info(f"📦 Создание заказа: {len(nomenclatures)} позиций")
            logger.info(f"💰 Сумма заказа: {total_order_amount}₽")
            if discount_amount > 0:
                logger.info(f"🎁 Скидка: {discount_amount}₽ ({discount_type})")
                logger.info(f"💰 Итоговая сумма: {total_after_discount}₽")
        
            # Логируем полный запрос (без sensitive данных)
            safe_order_data = order_data.copy()
            if 'customer' in safe_order_data:
                safe_order_data['customer']['phone'] = safe_order_data['customer']['phone'][:3] + '***' if safe_order_data['customer']['phone'] else '***'
        
            logger.debug(f"📤 Отправляемые данные: {json.dumps(safe_order_data, ensure_ascii=False)}")
    
            async with self.session.post(url, json=order_data) as response:
                response_text = await response.text()
                logger.info(f"📤 Ответ от Presto API: {response.status} - {response_text[:500]}...")
    
                if response.status == 200:
                    try:
                        data = await response.json()
                        logger.info(f"✅ Заказ создан: #{data.get('orderNumber')}")
                        return data
                    except Exception as json_error:
                        logger.error(f"❌ Ошибка парсинга JSON: {json_error}")
                        return {'error': f'JSON parse error: {json_error}', 'details': response_text}
                else:
                    logger.error(f"❌ Ошибка HTTP {response.status}")
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get('message', error_data.get('error', 'Unknown error'))
                        logger.error(f"❌ Ошибка Presto: {error_msg}")
                        return {'error': f'HTTP {response.status}: {error_msg}', 'details': response_text}
                    except:
                        return {'error': f'HTTP {response.status}', 'details': response_text}
                    
        except Exception as e:
            logger.error(f"❌ Ошибка создания заказа: {e}", exc_info=True)
            return {'error': str(e)}
    
    async def get_order_status(self, sale_key: str) -> Dict:
        """
        Получение статуса заказа
        GET /order/{saleKey}/state
        """
        try:
            await self.init_session()
            
            url = f"{self.base_url}/order/{sale_key}/state"
            
            logger.info(f"📊 Проверка статуса заказа: {sale_key}")
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"❌ Ошибка проверки статуса: {response.status}")
                    return {'error': f'HTTP {response.status}'}
                    
        except Exception as e:
            logger.error(f"❌ Ошибка проверки статуса: {e}")
            return {'error': str(e)}
    
    async def get_payment_link(self, sale_key: str, shop_url: str, 
                              success_url: str, error_url: str) -> Optional[str]:
        """
        Получение ссылки на оплату
        GET /order/{saleKey}/payment-link
        """
        try:
            await self.init_session()
            
            url = f"{self.base_url}/order/{sale_key}/payment-link"
            
            params = {
                'shopURL': shop_url,
                'successURL': success_url,
                'errorURL': error_url
            }
            
            logger.info(f"💳 Получение ссылки на оплату: {sale_key}")
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    payment_url = data.get('link')
                    logger.info(f"✅ Ссылка на оплату получена")
                    return payment_url
                else:
                    logger.error(f"❌ Ошибка получения ссылки оплаты: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения ссылки оплаты: {e}")
            return None
    
    async def cancel_order(self, sale_key: str) -> bool:
        """
        Отмена заказа
        PUT /order/{saleKey}/cancel
        """
        try:
            await self.init_session()
            
            url = f"{self.base_url}/order/{sale_key}/cancel"
            
            logger.info(f"❌ Отмена заказа: {sale_key}")
            
            async with self.session.put(url) as response:
                if response.status == 200:
                    logger.info(f"✅ Заказ отменен: {sale_key}")
                    return True
                else:
                    logger.error(f"❌ Ошибка отмены заказа: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка отмены заказа: {e}")
            return False
    
    async def get_promocodes(self) -> Dict:
        """
        Получение списка промокодов
        """
        try:
            # В реальности здесь запрос к API Presto
            # Для демо используем статические данные
            return {
                'FIRSTORDER20': {
                    'code': 'FIRSTORDER20',
                    'description': '20% скидка на первый заказ',
                    'discount_percent': 20,
                    'max_uses': 1,
                    'active': True
                }
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения промокодов: {e}")
            return {}
    
    async def get_customer_uuid(self, phone: str) -> Optional[str]:
        """
        Получение UUID клиента по номеру телефона
        GET /customer/find?phone=89207444555
        """
        try:
            await self.init_session()
            
            url = f"{self.base_url}/customer/find"
            params = {'phone': phone}
            
            logger.info(f"🔍 Поиск клиента по телефону: {phone}")
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    uuid = data.get('person')
                    
                    if uuid:
                        logger.info(f"✅ UUID клиента найден: {uuid}")
                        return uuid
                    else:
                        logger.warning(f"⚠️ UUID не найден для телефона {phone}")
                        return None
                else:
                    logger.error(f"❌ Ошибка поиска клиента: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения UUID клиента: {e}")
            return None
    
    async def validate_promocode(self, promocode: str, user_id: int) -> Dict:
        """
        Проверка валидности промокода
        """
        try:
            # Проверяем использовал ли уже пользователь промокод
            user_orders = database.get_user_orders(user_id)
            if user_orders:
                return {
                    'valid': False,
                    'message': 'Промокод доступен только для первого заказа'
                }
            
            # Проверяем промокод в системе
            promocodes = await self.get_promocodes()
            promocode_data = promocodes.get(promocode.upper())
            
            if not promocode_data:
                return {
                    'valid': False,
                    'message': 'Неверный промокод'
                }
            
            if not promocode_data.get('active', True):
                return {
                    'valid': False,
                    'message': 'Промокод неактивен'
                }
            
            return {
                'valid': True,
                'message': 'Промокод действителен',
                'discount_percent': promocode_data.get('discount_percent', 0),
                'code': promocode.upper()
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки промокода: {e}")
            return {
                'valid': False,
                'message': 'Ошибка проверки промокода'
            }
    
    # ===== ФУНКЦИИ МЕНЮ =====
    
    def _parse_image_url(self, image_path: str) -> Optional[str]:
        """Парсит URL изображения"""
        if not image_path:
            return None
            
        if image_path.startswith('/img?params='):
            try:
                params_base64 = image_path.replace('/img?params=', '')
                params_base64 += '=' * (-len(params_base64) % 4)
                
                params_json = base64.b64decode(params_base64).decode('utf-8')
                params = json.loads(params_json)
                
                for key in ['PhotoURL', 'PhotoUrl', 'photoURL', 'photoUrl']:
                    if key in params and params[key]:
                        return params[key]
                        
                return None
                    
            except Exception:
                return None
        elif image_path.startswith('http'):
            return image_path
        elif image_path.startswith('/'):
            return f"https://api.sbis.ru{image_path}"
        else:
            return None
    
    async def get_menu_by_id(self, menu_id: int, price_lists_dict: Dict[int, Dict] = None) -> Dict:
        """
        Получение меню по ID
        """
        try:
            await self.init_session()

            menu_name = self.menus.get(menu_id, f"Меню {menu_id}")
            logger.info(f"🍽️ Загрузка меню: {menu_name}")

            params = {
                'pointId': self.point_id,
                'pageSize': 1000,
                'withBalance': 'true',
                'product': 'delivery'
            }

            # Add priceListId if this menu_id is a known price list
            if price_lists_dict and menu_id in price_lists_dict:
                params['priceListId'] = menu_id
                logger.info(f"📋 Используем priceListId={menu_id} для меню")

            url = f"{self.base_url}/nomenclature/list"

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"❌ Ошибка HTTP {response.status}")
                    return {}

                data = await response.json()

                if isinstance(data, dict) and 'nomenclatures' in data:
                    all_items = data['nomenclatures']
                    logger.info(f"📥 Получено элементов: {len(all_items)}")

                    is_price_list = price_lists_dict and menu_id in price_lists_dict
                    # Если это прайс-лист, не фильтруем категории по родительскому ID (передаем None)
                    categories = self._extract_categories(all_items, menu_id if not is_price_list else None)
                    logger.info(f"📂 Найдено категорий: {len(categories)}")

                    structured_menu = self._structure_menu_by_categories(all_items, categories, menu_id, is_price_list)
                    await self._download_menu_images(structured_menu)

                    return structured_menu
                else:
                    logger.error(f"❌ Неверная структура ответа")
                    return {}

        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке меню: {e}")
            return {}
    
    def _extract_categories(self, all_items: List[Dict], menu_id: int = None) -> Dict:
        """Извлекает категории"""
        categories = {}

        for item in all_items:
            is_parent = item.get('isParent', False)
            cost = item.get('cost')

            if is_parent and cost is None:
                category_id = item.get('hierarchicalId')
                category_name = item.get('name', '').strip()

                if category_id and category_name:
                    # If menu_id is specified, only include categories related to this menu
                    if menu_id is not None:
                        hierarchical_parent = item.get('hierarchicalParent')
                        if hierarchical_parent != menu_id and category_id != menu_id:
                            continue

                    display_name = self._add_emoji_to_category(category_name)

                    categories[category_id] = {
                        'id': category_id,
                        'name': category_name,
                        'display_name': display_name,
                        'parent_id': item.get('hierarchicalParent'),
                        'is_parent': True,
                        'hierarchical_id': category_id,
                        'hierarchical_parent': item.get('hierarchicalParent'),
                        'image_url': self._parse_image_url(item.get('images', [None])[0]) if item.get('images') else None
                    }

        if not categories:
            categories[0] = {
                'id': 0,
                'name': 'Все товары',
                'display_name': '📦 Все товары',
                'parent_id': None,
                'is_parent': True,
                'hierarchical_id': 0,
                'hierarchical_parent': None,
                'image_url': None
            }
            logger.info("📂 Создана общая категория")

        return categories

    def _extract_categories_for_menu(self, all_items: List[Dict], menu_id: int) -> Dict:
        """Извлекает категории для конкретного меню"""
        categories = {}

        for item in all_items:
            is_parent = item.get('isParent', False)
            cost = item.get('cost')

            if is_parent and cost is None:
                category_id = item.get('hierarchicalId')
                category_name = item.get('name', '').strip()

                if category_id and category_name:
                    # Include categories that are children of this menu or are the menu itself
                    hierarchical_parent = item.get('hierarchicalParent')
                    if hierarchical_parent == menu_id or category_id == menu_id:
                        display_name = self._add_emoji_to_category(category_name)

                        categories[category_id] = {
                            'id': category_id,
                            'name': category_name,
                            'display_name': display_name,
                            'parent_id': hierarchical_parent,
                            'is_parent': True,
                            'hierarchical_id': category_id,
                            'hierarchical_parent': hierarchical_parent,
                            'image_url': self._parse_image_url(item.get('images', [None])[0]) if item.get('images') else None
                        }

        if not categories:
            categories[0] = {
                'id': 0,
                'name': 'Все товары',
                'display_name': '📦 Все товары',
                'parent_id': None,
                'is_parent': True,
                'hierarchical_id': 0,
                'hierarchical_parent': None,
                'image_url': None
            }
            logger.info(f"📂 Создана общая категория для меню {menu_id}")

        return categories
    
    def _add_emoji_to_category(self, category_name: str) -> str:
        """Добавляет эмодзи к категории"""
        category_lower = category_name.lower()
        
        emoji_map = [
            ('пицц', '🍕'),
            ('закуск', '🥨'),
            ('салат', '🥗'),
            ('суп', '🍲'),
            ('гарнир', '🍚'),
            ('горяч', '🍖'),
            ('десерт', '🍰'),
            ('коктейл', '🍸'),
            ('сок', '🧃'),
            ('вод', '💧'),
            ('завтрак', '🍳'),
            ('сыр', '🧀'),
            ('кофе', '☕'),
            ('чай', '🍵'),
        ]
        
        for keyword, emoji in emoji_map:
            if keyword in category_lower:
                return f"{emoji} {category_name}"
        
        return f"📁 {category_name}"
    
    def _structure_menu_by_categories(self, all_items: List[Dict], categories: Dict, menu_id: int, is_price_list: bool = False) -> Dict:
        """Структурирует меню"""
        structured_categories = {}

        for cat_id, cat_info in categories.items():
            structured_categories[cat_id] = {
                'id': cat_id,
                'name': cat_info['name'],
                'display_name': cat_info['display_name'],
                'parent_id': cat_info['parent_id'],
                'items': [],
                'image_url': cat_info.get('image_url')
            }

        for item in all_items:
            if item.get('isParent', False) and item.get('cost') is None:
                continue

            # For price list menus, include all items (don't filter by hierarchicalParent)
            # For hierarchical menus, filter by hierarchicalParent == menu_id
            if not is_price_list and item.get('hierarchicalParent') != menu_id:
                continue

            dish = self._extract_dish_data(item)
            if dish:
                dish['menu_id'] = menu_id

                parent_id = item.get('hierarchicalParent')

                if parent_id and parent_id in structured_categories:
                    structured_categories[parent_id]['items'].append(dish)
                else:
                    if 0 not in structured_categories:
                        structured_categories[0] = {
                            'id': 0,
                            'name': 'Без категории',
                            'display_name': '📦 Без категории',
                            'parent_id': None,
                            'items': [],
                            'image_url': None
                        }
                    structured_categories[0]['items'].append(dish)

        result = {}
        category_order = []

        for item in all_items:
            if item.get('isParent', False) and item.get('cost') is None:
                category_id = item.get('hierarchicalId')
                if category_id and category_id in structured_categories:
                    if structured_categories[category_id]['items']:
                        result[category_id] = structured_categories[category_id]
                        category_order.append(category_id)

        if 0 in structured_categories and structured_categories[0]['items']:
            result[0] = structured_categories[0]

        return result
    
    def _extract_dish_data(self, item: Dict) -> Optional[Dict]:
        """Извлекает данные блюда"""
        try:
            dish_id = item.get('id')
            if not dish_id:
                return None
            
            attributes = item.get('attributes', {})
            
            # Пищевая ценность
            calories = attributes.get('calorie')
            calories_per_100 = attributes.get('calorie')
            protein = attributes.get('protein')
            fat = attributes.get('fat')
            carbohydrate = attributes.get('carbohydrate')
            weight = attributes.get('outQuantity')
            
            # Изображения
            image_url = None
            if item.get('images') and len(item['images']) > 0:
                for img_path in item['images']:
                    parsed_url = self._parse_image_url(img_path)
                    if parsed_url:
                        image_url = parsed_url
                        break
            
            # Описание
            description = item.get('description_simple') or item.get('description', '')
            if description and '<' in description:
                import re
                description = re.sub(r'<[^>]+>', '', description)
            
            # Цена
            price = 0
            try:
                cost = item.get('cost')
                if cost is not None:
                    price = float(cost)
            except (ValueError, TypeError):
                price = 0
            
            # Название
            name = item.get('name', 'Без названия').strip()
            
            # Создаем блюдо
            dish = {
                'id': dish_id,
                'external_id': item.get('externalId'),
                'name': name,
                'description': description[:500] if description else '',
                'price': price,
                'balance': 999,
                'unit': item.get('unit', 'шт.'),
                
                # Пищевая ценность
                'calories': float(calories) if calories is not None else None,
                'calories_per_100': float(calories_per_100) if calories_per_100 is not None else None,
                'protein': float(protein) if protein is not None else None,
                'fat': float(fat) if fat is not None else None,
                'carbohydrate': float(carbohydrate) if carbohydrate is not None else None,
                'weight': str(weight) if weight else None,
                
                # Изображение
                'image_url': image_url,
                'image_filename': f"{dish_id}.jpg" if image_url else None,
                'image_local_path': None,
                
                # Модификаторы
                'modifiers': item.get('modifiers', []),
                'modifiers_count': len(item.get('modifiers', [])),
                
                # Иерархия
                'hierarchical_id': item.get('hierarchicalId'),
                'hierarchical_parent': item.get('hierarchicalParent'),
                'category_id': item.get('hierarchicalParent'),
            }
            
            return dish
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения данных блюда: {e}")
            return None
    
    async def _download_menu_images(self, structured_menu: Dict):
        """Загружает изображения"""
        if not structured_menu:
            return
        
        os.makedirs(config.MENU_IMAGES_DIR, exist_ok=True)
        
        download_tasks = []
        
        for category_id, category_data in structured_menu.items():
            for dish in category_data['items']:
                image_url = dish.get('image_url')
                if image_url and dish.get('image_filename'):
                    save_path = os.path.join(config.MENU_IMAGES_DIR, dish['image_filename'])
                    dish['image_local_path'] = save_path
                    
                    if not os.path.exists(save_path):
                        download_tasks.append(
                            self._download_single_image(image_url, save_path, dish['id'])
                        )
                    else:
                        dish['image_downloaded'] = True
        
        if download_tasks:
            logger.info(f"🖼️ Загружаем {len(download_tasks)} изображений...")
            try:
                results = await asyncio.gather(*download_tasks, return_exceptions=True)
                successful = sum(1 for r in results if r is True)
                logger.info(f"✅ Изображений загружено: {successful}/{len(download_tasks)}")
            except Exception as e:
                logger.error(f"❌ Ошибка при загрузке изображений: {e}")
    
    async def _download_single_image(self, image_url: str, save_path: str, dish_id: int) -> bool:
        """Загрузка одного изображения"""
        try:
            await self.init_session()
            
            async with self.session.get(image_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    image_data = await response.read()
                    
                    with open(save_path, 'wb') as f:
                        f.write(image_data)
                    
                    return True
                else:
                    return False
                    
        except Exception:
            return False
    
    async def get_price_lists(self) -> List[Dict]:
        """
        Получает список всех доступных прайс-листов/меню через API Presto
        GET /retail/nomenclature/price-list
        """
        try:
            await self.init_session()

            url = f"{self.base_url}/nomenclature/price-list"

            from datetime import datetime
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            params = {
                'pointId': self.point_id,
                'actualDate': current_time,
                'pageSize': 100  # Берем много на всякий случай
            }

            logger.info(f"📋 Получаем список всех прайс-листов для точки {self.point_id}")

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"❌ Ошибка HTTP {response.status} при получении прайс-листов")
                    return []

                data = await response.json()

                if isinstance(data, dict) and 'priceLists' in data:
                    price_lists = data['priceLists']
                    logger.info(f"✅ Найдено {len(price_lists)} прайс-листов:")

                    for pl in price_lists:
                        pl_id = pl.get('id')
                        pl_name = pl.get('name', 'Без названия')
                        logger.info(f"   • ID {pl_id}: {pl_name}")

                    return price_lists
                else:
                    logger.error(f"❌ Неверная структура ответа при получении прайс-листов: {data}")
                    return []

        except Exception as e:
            logger.error(f"❌ Ошибка при получении списка прайс-листов: {e}")
            return []

    async def get_all_delivery_items(self) -> List[Dict]:
        """Получает все товары доставки без фильтрации по меню"""
        try:
            await self.init_session()

            params = {
                'pointId': self.point_id,
                'pageSize': 1000,
                'withBalance': 'true',
                'product': 'delivery'
            }

            url = f"{self.base_url}/nomenclature/list"

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"❌ Ошибка HTTP {response.status} при получении всех товаров доставки")
                    return []

                data = await response.json()

                if isinstance(data, dict) and 'nomenclatures' in data:
                    all_items = data['nomenclatures']
                    logger.info(f"📥 Получено всех элементов доставки: {len(all_items)}")
                    return all_items
                else:
                    logger.error(f"❌ Неверная структура ответа при получении всех товаров доставки")
                    return []

        except Exception as e:
            logger.error(f"❌ Ошибка при получении всех товаров доставки: {e}")
            return []

    async def get_all_menus(self) -> Dict[int, Dict]:
        """Получает все доступные меню через API прайс-листов"""
        all_menus = {}

        # Сначала получаем список всех доступных прайс-листов
        price_lists = await self.get_price_lists()

        if not price_lists:
            logger.warning("⚠️ Не удалось получить список прайс-листов, используем известные меню")
            # Fallback на известные меню
            price_lists = [{'id': menu_id, 'name': menu_name} for menu_id, menu_name in self.menus.items()]

        # ФИЛЬТРУЕМ ТОЛЬКО НУЖНЫЕ МЕНЮ ДОСТАВКИ
        delivery_menu_ids = {90, 92, 141}

        # Создаем словарь priceLists по ID для быстрого поиска
        price_lists_dict = {int(pl['id']): pl for pl in price_lists}

        # Загружаем меню для каждого ID доставки, если он есть в прайс-листах
        for menu_id in delivery_menu_ids:
            if menu_id not in price_lists_dict:
                logger.info(f"⏭️ Пропускаем меню {menu_id} (не найден в прайс-листах)")
                continue

            menu_name = price_lists_dict[menu_id]['name']

            logger.info(f"📥 Загружаем меню '{menu_name}' (ID: {menu_id})")
            menu_data = await self.get_menu_by_id(menu_id, price_lists_dict)

            if menu_data:
                all_menus[menu_id] = {
                    'id': menu_id,
                    'name': menu_name,
                    'categories': menu_data
                }

                categories_count = len(menu_data)
                total_items = sum(len(cat['items']) for cat in menu_data.values())
                logger.info(f"✅ Меню '{menu_name}': {categories_count} категорий, {total_items} товаров")
            else:
                logger.warning(f"⚠️ Меню '{menu_name}' (ID: {menu_id}) не загружено")

        logger.info(f"✅ Всего загружено меню: {len(all_menus)}")
        return all_menus

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

# Глобальный экземпляр API
presto_api = PrestoAPI()
