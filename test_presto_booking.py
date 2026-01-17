import requests
import json

# Параметры запроса согласно документации
parameters = {
    'pointId': 3596,  # Идентификатор точки продаж
    'date': '2026-01-07 13:00:00',  # Дата и время в правильном формате
    'hallId': 9195  # Идентификатор конкретного зала
}

# URL API
url = 'https://api.sbis.ru/retail/hall/list?'  # Убрал вопросительный знак

# Заголовки с токеном
headers = {
    "X-SBISAccessToken": "aT9ATVJhVWc9NnpSOmR2RzszKmE7NnclOlVWTmJsOls6LWZyTX5OZCgufnUdV89bVlsLT5LMlZT14tWzN0MTIwMjYtMDEtMDQgMTQ6NDU6NDYuOTMwOTY2"
}  

print("Отправка запроса к API Presto для получения списка столов...")
print(f"Параметры запроса: {json.dumps(parameters, indent=2, ensure_ascii=False)}")
print("-" * 50)

try:
    # Отправка GET-запроса
    response = requests.get(url, params=parameters, headers=headers)
    
    # Проверка статуса ответа
    print(f"Статус ответа: {response.status_code}")
    
    if response.status_code == 200:
        # Парсим JSON ответ
        data = response.json()
        
        print("\n✅ Успешный ответ от API!")
        print(f"Количество залов в ответе: {len(data.get('halls', []))}")
        print("-" * 50)
        
        # Обрабатываем каждый зал
        for hall in data.get('halls', []):
            print(f"\n🎯 Зал: {hall.get('name')}")
            print(f"ID зала: {hall.get('id')}")
            print(f"Активен: {hall.get('active')}")
            
            # Считаем столы
            tables = [item for item in hall.get('items', []) if item.get('kind') == 'table']
            print(f"Всего столов в зале: {len(tables)}")
            
            # Фильтруем доступные для бронирования столы
            available_tables = [
                table for table in tables 
                if not table.get('isBookingLocked', True) and not table.get('busy', True)
            ]
            
            print(f"Доступных для бронирования столов: {len(available_tables)}")
            
            if available_tables:
                print("\n📋 Список доступных столов:")
                print("-" * 40)
                for i, table in enumerate(available_tables, 1):
                    print(f"{i}. Стол №{table.get('name')}")
                    print(f"   ID: {table.get('id')}")
                    print(f"   Мест: {table.get('capacity')}")
                    print(f"   Тип: {table.get('type')} ({'квадратный' if table.get('type') == 0 else 'прямоугольный' if table.get('type') == 1 else 'круглый' if table.get('type') == 2 else 'другой'})")
                    print(f"   Положение: x={table.get('x')}, y={table.get('y')}")
                    print(f"   Видимый: {table.get('visible')}")
                    print(f"   Время освобождения: {table.get('endTime', 'не указано')}")
                    print()
            
            # Также выводим все элементы для информации
            print(f"\n📊 Все элементы зала ({len(hall.get('items', []))} шт.):")
            for item in hall.get('items', []):
                kind = item.get('kind', 'unknown')
                name = item.get('name', 'без имени')
                busy = "занят" if item.get('busy') else "свободен"
                locked = "заблокирован" if item.get('isBookingLocked') else "доступен"
                
                if kind == 'table':
                    print(f"  🪑 Стол '{name}' - {busy}, бронь {locked}")
                elif kind == 'bar':
                    print(f"  🍸 Барная стойка '{name}' - {busy}, бронь {locked}")
                else:
                    print(f"  📍 {kind.capitalize()} '{name}'")
        
        # Информация о пагинации
        outcome = data.get('outcome', {})
        if outcome.get('hasMore', False):
            print("\n⚠️ Есть дополнительные данные на следующей странице!")
        else:
            print("\n✅ Все данные получены.")
            
        print("\n📄 Полный ответ JSON сохранен в файл 'response.json'")
        with open('response.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            
    else:
        print(f"\n❌ Ошибка! Код статуса: {response.status_code}")
        print(f"Текст ответа: {response.text}")
        
except requests.exceptions.RequestException as e:
    print(f"\n❌ Ошибка при выполнении запроса: {e}")
except json.JSONDecodeError as e:
    print(f"\n❌ Ошибка парсинга JSON: {e}")
    print(f"Ответ сервера: {response.text}")
except Exception as e:
    print(f"\n❌ Неожиданная ошибка: {type(e).__name__}: {e}")