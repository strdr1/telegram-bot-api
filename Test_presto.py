#!/usr/bin/env python3
"""
test_order_final.py - Финальный тест заказа с товаром "тест комплект"
"""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime

# ===== КОНФИГУРАЦИЯ =====
PRESTO_ACCESS_TOKEN = "aT9ATVJhVWc9NnpSOmR2RzszKmE7NnclOlVWTmJsOls6LWZyTX5OZCgufnUdV89bVlsLT5LMlZT14tWzN0MTIwMjYtMDEtMDQgMTQ6NDU6NDYuOTMwOTY2"
PRESTO_POINT_ID = 3596
BASE_URL = "https://api.sbis.ru/retail"

# ===== ДАННЫЕ ТОВАРА =====
# Точное название как в системе
TARGET_PRODUCT_NAME = "тест комплект"  # Малыми буквами для поиска
PRICE_LIST_ID = 92  # Основное меню

class OrderTester:
    def __init__(self):
        self.access_token = PRESTO_ACCESS_TOKEN
        self.point_id = PRESTO_POINT_ID
        self.base_url = BASE_URL
        self.session = None
        self.found_product = None
    
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
    
    async def find_test_product(self):
        """Ищем товар 'тест комплект' в системе"""
        print("🔍 Поиск товара 'тест комплект' в меню 92...")
        
        try:
            url = f"{self.base_url}/nomenclature/list"
            params = {
                'pointId': str(self.point_id),
                'priceListId': str(PRICE_LIST_ID),
                'pageSize': '200',  # Увеличим для надежности
                'withBalance': 'true',
                'product': 'delivery'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"❌ Ошибка при загрузке меню: {response.status}")
                    response_text = await response.text()
                    print(f"Ответ: {response_text[:500]}")
                    return False
                
                data = await response.json()
                nomenclatures = data.get('nomenclatures', [])
                print(f"📊 Загружено {len(nomenclatures)} элементов из меню")
                
                # Сохраняем весь ответ для отладки
                with open('full_menu_response.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("💾 Полный ответ меню сохранен в full_menu_response.json")
                
                # Ищем товар
                found_items = []
                
                for item in nomenclatures:
                    # Пропускаем категории (у них isParent=True и cost=None)
                    if item.get('isParent', False) and item.get('cost') is None:
                        continue
                    
                    item_name = item.get('name', '').strip()
                    
                    # Ищем точное совпадение (без учета регистра)
                    if TARGET_PRODUCT_NAME.lower() == item_name.lower():
                        found_items.append(item)
                    # Или частичное совпадение
                    elif TARGET_PRODUCT_NAME.lower() in item_name.lower():
                        found_items.append(item)
                
                if found_items:
                    print(f"✅ Найдено {len(found_items)} совпадений!")
                    
                    # Берем первый найденный товар
                    product = found_items[0]
                    self.found_product = {
                        'id': product.get('id'),
                        'name': product.get('name'),
                        'article': product.get('article'),
                        'externalId': product.get('externalId'),
                        'cost': product.get('cost'),
                        'hierarchicalId': product.get('hierarchicalId'),
                        'hierarchicalParent': product.get('hierarchicalParent'),
                        'unit': product.get('unit', 'шт.')
                    }
                    
                    print(f"\n📦 НАЙДЕН ТОВАР:")
                    print(f"   Название: {self.found_product['name']}")
                    print(f"   ID: {self.found_product['id']}")
                    print(f"   Артикул: {self.found_product['article']}")
                    print(f"   Цена: {self.found_product['cost']}₽")
                    print(f"   External ID: {self.found_product['externalId']}")
                    print(f"   Hierarchical ID: {self.found_product['hierarchicalId']}")
                    
                    # Сохраняем найденный товар отдельно
                    with open('found_product.json', 'w', encoding='utf-8') as f:
                        json.dump(self.found_product, f, ensure_ascii=False, indent=2)
                    print("💾 Данные товара сохранены в found_product.json")
                    
                    return True
                else:
                    print("❌ Товар 'тест комплект' не найден!")
                    print("\n📋 Список всех товаров (первые 20):")
                    
                    # Выводим список товаров для отладки
                    count = 0
                    for item in nomenclatures:
                        if not item.get('isParent', False) and item.get('cost') is not None:
                            count += 1
                            name = item.get('name', 'Без названия')
                            price = item.get('cost', 0)
                            print(f"  {count}. '{name}' - {price}₽")
                            if count >= 20:
                                break
                    
                    return False
                    
        except Exception as e:
            print(f"❌ Ошибка поиска товара: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def create_test_order(self):
        """Создаем тестовый заказ"""
        if not self.found_product:
            print("❌ Сначала найдите товар!")
            return False
        
        print("\n🛒 СОЗДАНИЕ ТЕСТОВОГО ЗАКАЗА")
        print("-" * 40)
        
        # Формируем номенклатуру - используем ВСЕ доступные идентификаторы
        nomenclature = {
            'count': 1,
            'cost': self.found_product['cost'],
            'name': self.found_product['name'],
            'priceListId': PRICE_LIST_ID
        }
        
        # Добавляем ВСЕ возможные идентификаторы
        if self.found_product.get('id'):
            nomenclature['id'] = self.found_product['id']
            print(f"📝 Используем ID: {self.found_product['id']}")
        
        if self.found_product.get('article'):
            nomenclature['nomNumber'] = self.found_product['article']
            print(f"📝 Используем артикул: {self.found_product['article']}")
        
        if self.found_product.get('externalId'):
            nomenclature['externalId'] = self.found_product['externalId']
            print(f"📝 Используем externalId: {self.found_product['externalId']}")
        
        # Данные заказа
        order_data = {
            "product": "delivery",
            "pointId": self.point_id,
            "comment": "Тестовый заказ API - тест комплект",
            "customer": {
                "name": "Тест",
                "lastname": "API",
                "phone": "+79001112233",
                "email": "test@example.com"
            },
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "nomenclatures": [nomenclature],
            "delivery": {
                "addressJSON": json.dumps({
                    "Address": "Москва, Тестовая улица, д. 1",
                    "Locality": "Москва",
                    "Coordinates": {"Lat": 55.7558, "Lon": 37.6176},
                    "AptNum": "1",
                    "Entrance": "1",
                    "Floor": "1",
                    "DoorCode": "1#"
                }),
                "paymentType": "cash",
                "persons": 1,
                "isPickup": False,
                "district": 20646  # Район "Город"
            }
        }
        
        print(f"\n📦 Товар: {self.found_product['name']}")
        print(f"💰 Цена: {self.found_product['cost']}₽")
        print(f"📍 Адрес: Москва, Тестовая улица, д. 1")
        print(f"🗺️ Район: Город (ID: 20646)")
        
        try:
            # Сохраняем запрос
            with open('final_order_request.json', 'w', encoding='utf-8') as f:
                json.dump(order_data, f, ensure_ascii=False, indent=2)
            print("💾 Запрос сохранен в final_order_request.json")
            
            # Отправляем запрос
            url = f"{self.base_url}/order/create"
            
            print(f"\n📤 Отправляем запрос на {url}...")
            
            async with self.session.post(
                url, 
                json=order_data,
                timeout=30
            ) as response:
                response_text = await response.text()
                
                print(f"\n📊 РЕЗУЛЬТАТ:")
                print(f"  HTTP статус: {response.status}")
                print(f"  Длина ответа: {len(response_text)} символов")
                
                # Сохраняем ответ
                result_data = {
                    'timestamp': datetime.now().isoformat(),
                    'status_code': response.status,
                    'response': response_text,
                    'headers': dict(response.headers)
                }
                
                with open('final_order_response.json', 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
                print("💾 Ответ сохранен в final_order_response.json")
                
                if response.status == 200:
                    try:
                        result = json.loads(response_text)
                        
                        print(f"\n🎉 УСПЕХ! Заказ создан!")
                        
                        if 'orderNumber' in result:
                            print(f"✅ Номер заказа: {result['orderNumber']}")
                        
                        if 'saleKey' in result:
                            print(f"🔑 Sale Key: {result['saleKey']}")
                        
                        if 'message' in result and result['message']:
                            print(f"💬 Сообщение: {result['message']}")
                        
                        print(f"\n📄 Полный ответ:")
                        print(json.dumps(result, ensure_ascii=False, indent=2))
                        
                        return True
                        
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Ответ не в JSON формате: {e}")
                        print(f"📄 Ответ: {response_text}")
                        return False
                        
                else:
                    print(f"❌ ОШИБКА: HTTP {response.status}")
                    print(f"\n📄 Ответ сервера:")
                    print(response_text)
                    
                    # Пытаемся распарсить JSON ошибки
                    try:
                        error_data = json.loads(response_text)
                        if 'error' in error_data:
                            error = error_data['error']
                            print(f"\n🔍 ДЕТАЛИ ОШИБКИ:")
                            print(f"  Код: {error.get('code')}")
                            print(f"  Сообщение: {error.get('message')}")
                            print(f"  Детали: {error.get('details', 'Нет деталей')}")
                            
                            # Особый случай: номенклатуры не существуют
                            if 'Указанные номенклатуры не существуют' in str(error.get('details', '')):
                                print(f"\n⚠️  ВОЗМОЖНОЕ РЕШЕНИЕ:")
                                print(f"  1. Проверьте, что товар АКТИВЕН в системе Presto")
                                print(f"  2. Проверьте, что товар доступен для ЗАКАЗА")
                                print(f"  3. Убедитесь, что используется правильный priceListId ({PRICE_LIST_ID})")
                                print(f"  4. Попробуйте использовать только ОДИН идентификатор (id или nomNumber)")
                    except:
                        pass
                    
                    return False
                    
        except Exception as e:
            print(f"❌ Ошибка при отправке запроса: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def simple_create_order(self):
        """Простой тест заказа с минимальными данными"""
        print("\n🛒 ПРОСТОЙ ТЕСТ ЗАКАЗА")
        print("-" * 40)
        
        # Самый простой запрос
        order_data = {
            "product": "delivery",
            "pointId": self.point_id,
            "customer": {
                "name": "Тест",
                "phone": "+79001112233"
            },
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "nomenclatures": [
                {
                    "name": "тест комплект",
                    "count": 1,
                    "cost": 1.0
                }
            ],
            "delivery": {
                "addressJSON": json.dumps({
                    "Address": "Тестовый адрес",
                    "Locality": "Москва"
                }),
                "paymentType": "cash",
                "isPickup": False
            }
        }
        
        print("📤 Отправляем упрощенный запрос...")
        
        try:
            url = f"{self.base_url}/order/create"
            
            async with self.session.post(url, json=order_data, timeout=30) as response:
                response_text = await response.text()
                print(f"📊 Статус: {response.status}")
                print(f"📄 Ответ: {response_text[:500]}...")
                
                return response.status == 200
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return False

async def main():
    """Главная функция"""
    print("🛒 ФИНАЛЬНЫЙ ТЕСТ API SABY PRESTO")
    print("=" * 60)
    print()
    
    tester = OrderTester()
    
    try:
        await tester.init_session()
        
        print("Выберите действие:")
        print("1. Найти товар и создать заказ (полный тест)")
        print("2. Только найти товар 'тест комплект'")
        print("3. Простой тест заказа (минимальные данные)")
        
        choice = input("\nВаш выбор (1-3): ").strip()
        
        if choice == '1':
            # Полный тест
            if await tester.find_test_product():
                print("\n" + "=" * 60)
                confirm = input("\n⚠️  Создать тестовый заказ? (y/n): ").lower().strip()
                if confirm == 'y':
                    await tester.create_test_order()
                else:
                    print("⏹️ Создание заказа отменено")
        
        elif choice == '2':
            # Только поиск товара
            await tester.find_test_product()
        
        elif choice == '3':
            # Простой тест
            confirm = input("\n⚠️  Создать простой тестовый заказ? (y/n): ").lower().strip()
            if confirm == 'y':
                await tester.simple_create_order()
        
        else:
            print("❌ Неверный выбор")
    
    except KeyboardInterrupt:
        print("\n\n⏹️ Тест прерван")
    
    finally:
        await tester.close_session()
        print("\n🏁 Тест завершен")

if __name__ == "__main__":
    asyncio.run(main())