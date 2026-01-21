import requests
import logging
import os
import json
import datetime
from typing import Optional, Dict, Any, List
from config import PRESTO_ACCESS_TOKEN

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sbis.ru"
HEADERS = {
    "X-SBISAccessToken": PRESTO_ACCESS_TOKEN,
    "Content-Type": "application/json"
}

EXAMPLES_DIR = "examples"
os.makedirs(EXAMPLES_DIR, exist_ok=True)

def save_example(data: dict, filename: str):
    """Сохранить пример ответа API в файл"""
    try:
        path = os.path.join(EXAMPLES_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 [Presto] Сохранён пример: {path}")
    except Exception as e:
        print(f"⚠️ Ошибка сохранения: {e}")

def get_booking_calendar(from_date: str, to_date: str, point_id: int = 3596) -> Optional[Dict[str, Any]]:
    """
    Получить доступные интервалы бронирования — https://saby.ru/help/integration/api/app_presto/Presto_reserv/time
    
    ТРЕБОВАНИЯ PRESTO:
    - fromDate: "07.01.2026" (через точки)
    - toDate: "20.01.2026" (через точки)
    """
    url = f"{BASE_URL}/retail/booking/calendar"
    params = {
        "pointId": point_id,
        "fromDate": from_date,
        "toDate": to_date
    }
    try:
        print(f"📅 [Presto] Запрос календаря: {params}")
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        safe_name = f"calendar_{from_date}_to_{to_date}.json".replace(".", "-")
        save_example(data, safe_name)
        print(f"✅ [Presto] Календарь получен, записей: {len(data.get('dates', []))}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ [Presto] Ошибка календаря: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"📩 Тело ошибки: {e.response.text}")
        return None

def get_hall_tables(date_time: str, hall_id: Optional[int] = None, point_id: int = 3596) -> Optional[Dict[str, Any]]:
    """
    Получить схему зала на конкретное время.
    
    ТРЕБОВАНИЯ PRESTO:
    - pointId: ID точки продаж
    - date: "2026-01-07 18:00:00" (через тире)
    - hallId: опционально, ID конкретного зала
    
    ДОКУМЕНТАЦИЯ: https://saby.ru/help/integration/api/app_presto/Presto_reserv/hall_list
    """
    url = f"{BASE_URL}/retail/hall/list?"  # С восклицательным знаком, как указано
    
    # Парсим дату
    try:
        dt_obj = datetime.datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
        print(f"🕐 [Presto] Парсинг даты: {date_time} -> {dt_obj}")
    except ValueError as e:
        print(f"❌ [Presto] Ошибка парсинга даты: {e}")
        return None

    # Формируем параметры согласно документации
    params = {
        "pointId": point_id,
        "date": date_time,  # Основной параметр согласно документации
    }
    
    if hall_id is not None:
        params["hallId"] = hall_id

    print(f"📊 [Presto] Запрос схемы зала: {params}")
    
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Генерируем имя файла
        safe_date = date_time.replace(":", "_").replace(" ", "_")
        safe_name = f"hall_{point_id}_{safe_date}.json"
        if hall_id:
            safe_name = f"hall_{point_id}_{hall_id}_{safe_date}.json"
        
        save_example(data, safe_name)
        
        # Логируем результат
        halls_count = len(data.get('halls', []))
        items_total = 0
        for hall in data.get('halls', []):
            items_total += len(hall.get('items', []))
        
        print(f"✅ [Presto] Схема зала получена")
        print(f"   📍 Залы: {halls_count}")
        print(f"   🪑 Всего элементов: {items_total}")
        
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ [Presto] Ошибка схемы зала: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"📩 Тело ошибки: {e.response.text[:500]}")
        return None

def get_available_tables(date_time: str, guests: int, hall_id: Optional[int] = None, point_id: int = 3596) -> List[Dict[str, Any]]:
    """
    Получить список доступных столов для бронирования
    Возвращает список словарей с информацией о столах
    """
    hall_data = get_hall_tables(date_time, hall_id, point_id)
    if not hall_data:
        return []
    
    available_tables = []
    
    for hall in hall_data.get('halls', []):
        for item in hall.get('items', []):
            # Проверяем, что это стол
            if item.get('kind') != 'table':
                continue
            
            # Проверяем доступность
            if item.get('isBookingLocked', True):
                continue  # Бронирование запрещено
            
            if item.get('busy', True):
                continue  # Стол занят
            
            if not item.get('visible', True):
                continue  # Стол не видим
            
            # Проверяем вместимость
            capacity = item.get('capacity', 0)
            if capacity < guests:
                continue  # Недостаточно мест
            
            table_info = {
                'id': item.get('id'),
                'name': item.get('name', '?'),
                'capacity': capacity,
                'type': item.get('type', 0),
                'position': {
                    'x': item.get('x', 0),
                    'y': item.get('y', 0),
                    'z': item.get('z', 0)
                },
                'disposition': item.get('disposition', 0),
                'endTime': item.get('endTime', ''),
                'hall_id': hall.get('id'),
                'hall_name': hall.get('name')
            }
            
            available_tables.append(table_info)
    
    print(f"✅ [Presto] Найдено доступных столов: {len(available_tables)}")
    return available_tables

def create_booking(
    phone: str,
    name: str,
    datetime_str: str,
    visitors: int,
    hall_id: int,
    point_id: int = 3596,
    table_id: Optional[int] = None,
    comment: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Создать бронь через API Presto
    """
    url = f"{BASE_URL}/retail/order/create"
    
    # Формируем payload
    payload = {
        "product": "restaurant",
        "pointId": point_id,
        "comment": comment,
        "datetime": datetime_str,
        "customer": {
            "name": name,
            "phone": phone
        },
        "booking": {
            "visitors": visitors,
            "hall": hall_id
        }
    }
    
    if table_id is not None:
        payload["booking"]["table"] = table_id

    print(f"📝 [Presto] Создание брони...")
    print(f"📝 [Presto] Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=15)
        print(f"📝 [Presto] Статус ответа: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        # СОХРАНИТЕ ПОЛНЫЙ ОТВЕТ ДЛЯ АНАЛИЗА
        save_example(data, f"booking_full_response_{datetime_str.replace(':', '_').replace(' ', '_')}.json")
        
        print(f"✅ [Presto] Бронь создана успешно!")
        
        # РАСПЕЧАТАЙТЕ ВСЮ СТРУКТУРУ ОТВЕТА
        print("📋 [Presto] Полная структура ответа:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        # ИЩИТЕ ID В РАЗНЫХ МЕСТАХ
        external_id = None
        search_paths = [
            ('id',),
            ('order', 'id'),
            ('externalId',),
            ('booking_id',),
            ('bookingId',),
            ('reservationId',),
            ('data', 'id'),
            ('result', 'id'),
            ('response', 'id')
        ]
        
        for path in search_paths:
            try:
                value = data
                for key in path:
                    value = value[key]
                if value:
                    external_id = str(value)
                    print(f"🎯 [Presto] Найден ID по пути {path}: {external_id}")
                    break
            except (KeyError, TypeError):
                continue
        
        if external_id:
            data['_extracted_id'] = external_id
            print(f"🎉 [Presto] ID брони извлечен: {external_id}")
        else:
            print(f"⚠️ [Presto] ID брони не найден в ответе!")
            print(f"⚠️ [Presto] Ключи в ответе: {list(data.keys())}")
        
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"❌ [Presto] Ошибка создания брони: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"📩 Тело ошибки: {e.response.text[:500]}")
        return None

def get_booking_info(external_id: str) -> Optional[Dict[str, Any]]:
    """
    Получить информацию о бронировании по ID
    Метод: GET
    URL: https://api.sbis.ru/retail/order/{externalId}
    """
    url = f"{BASE_URL}/retail/order/{external_id}"
    
    # ДОБАВЬТЕ ЭТОТ ПРИНТ ДЛЯ ОТЛАДКИ
    print(f"🔍 [Presto] Формирую URL: {url}")
    print(f"🔍 [Presto] External ID: '{external_id}' (длина: {len(external_id)})")
    
    try:
        print(f"📋 [Presto] Запрос информации о бронировании: {external_id}")
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        # Логируем статус
        print(f"📊 [Presto] Статус ответа: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        save_example(data, f"booking_info_{external_id}.json")
        print(f"✅ [Presto] Информация о брони получена")
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"❌ [Presto] Ошибка получения информации о брони: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"📩 Тело ошибки: {e.response.text[:500]}")
        return None

def update_booking(external_id: str, booking_data: dict) -> Optional[Dict[str, Any]]:
    """
    Изменить бронирование
    Метод: PUT
    URL: https://api.sbis.ru/retail/order/{externalId}/update
    """
    url = f"{BASE_URL}/retail/order/{external_id}/update"
    
    try:
        print(f"✏️ [Presto] Обновление бронирования: {external_id}")
        response = requests.put(url, json=booking_data, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        save_example(data, f"booking_update_{external_id}.json")
        print(f"✅ [Presto] Бронирование обновлено")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ [Presto] Ошибка обновления брони: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"📩 Тело ошибки: {e.response.text[:500]}")
        return None

def cancel_booking(external_id: str) -> Optional[Dict[str, Any]]:
    """
    Отменить бронирование
    Метод: PUT
    URL: https://api.sbis.ru/retail/order/{externalId}/cancel
    """
    url = f"{BASE_URL}/retail/order/{external_id}/cancel"
    
    try:
        print(f"❌ [Presto] Отмена бронирования: {external_id}")
        response = requests.put(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        save_example(data, f"booking_cancel_{external_id}.json")
        print(f"✅ [Presto] Бронирование отменено")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ [Presto] Ошибка отмены брони: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"📩 Тело ошибки: {e.response.text[:500]}")
        return None

def get_booking_state(external_id: str) -> Optional[Dict[str, Any]]:
    """
    Получить статус бронирования
    Метод: GET
    URL: https://api.sbis.ru/retail/order/{externalId}/state
    """
    url = f"{BASE_URL}/retail/order/{external_id}/state"
    
    try:
        print(f"📊 [Presto] Запрос статуса бронирования: {external_id}")
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        save_example(data, f"booking_state_{external_id}.json")
        print(f"✅ [Presto] Статус брони получен")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ [Presto] Ошибка получения статуса брони: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"📩 Тело ошибки: {e.response.text[:500]}")
        return None

# Добавим статусы для удобства
BOOKING_STATUSES = {
    5: "📝 Черновик",
    10: "📱 Онлайн-заказ",
    20: "✅ Бронь подтверждена",
    30: "⏰ Гость опаздывает",
    40: "❌ Отмена заказа",
    45: "🚫 Не пришел",
    150: "🔒 Заблокирован",
    180: "📦 Отгружен",
    200: "✔️ Закрыт",
    220: "❌ Отменен"
}
# ===== ТЕСТОВЫЕ ФУНКЦИИ =====

def test_presto_api():
    """Тестирование всех функций API Presto"""
    print("🚀 Запуск теста API Presto...")
    
    # 1. Тест календаря
    print("\n1. 📅 Тест календаря бронирования:")
    from_date = datetime.datetime.now().strftime("%d.%m.%Y")
    to_date = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%d.%m.%Y")
    calendar = get_booking_calendar(from_date, to_date)
    
    if calendar:
        print(f"   ✅ Календарь получен")
        print(f"   📅 Дней доступно: {len(calendar.get('dates', []))}")
    
    # 2. Тест схемы зала
    print("\n2. 🏛️ Тест схемы зала:")
    test_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hall_data = get_hall_tables(test_date)
    
    if hall_data:
        print(f"   ✅ Схема зала получена")
    
    # 3. Тест доступных столов
    print("\n3. 🪑 Тест доступных столов:")
    tables = get_available_tables(test_date, guests=2)
    print(f"   ✅ Доступных столов: {len(tables)}")
    
    print("\n✅ Тест API Presto завершен!")

if __name__ == "__main__":
    # Запуск теста при прямом выполнении файла
    test_presto_api()
