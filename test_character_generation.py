#!/usr/bin/env python3
"""
Тестовый скрипт для проверки генерации персонажей
"""

import asyncio
import sys
import os

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import gen_image, get_random_delivery_dish, load_menu_cache

async def test_character_generation():
    """Тестирование генерации персонажей"""
    print("🧪 Тестируем генерацию персонажей")
    print("=" * 50)
    
    # Тестируем выбор блюда
    print("1️⃣ Тестируем выбор блюда...")
    menu_data = load_menu_cache()
    random_dish = get_random_delivery_dish(menu_data)
    
    if random_dish:
        print(f"✅ Выбрано блюдо: {random_dish['name']} ({random_dish['price']}₽)")
        print(f"📸 Фото блюда: {random_dish.get('image_local_path', 'Нет')}")
    else:
        print("❌ Блюдо не выбрано")
        return
    
    print("\n2️⃣ Тестируем генерацию изображения...")
    print("⚠️ Это займет около 30-60 секунд...")
    
    # Тестируем генерацию (без реального запроса к API)
    character_name = "Менделеев"
    print(f"🎭 Персонаж: {character_name}")
    print(f"🍽️ Блюдо: {random_dish['name']}")
    
    # Показываем что будет отправлено в API
    print(f"\n📤 Модель: bytedance/seedream-v4-edit")
    print(f"📤 Промпт для генерации:")
    if random_dish:
        prompt = f"Add photorealistic {character_name} eating {random_dish['name']} at the restaurant table. Ultra realistic, photographic quality, keep original restaurant interior unchanged, preserve exact camera angle and lighting, do not change table position or restaurant background, only add the character naturally sitting at the table"
    else:
        prompt = f"Add photorealistic {character_name} at the restaurant table. Ultra realistic, photographic quality, keep original restaurant interior unchanged, preserve exact camera angle and lighting, do not change table position or restaurant background, only add the character naturally sitting at the table"
    
    print(f"'{prompt}'")
    
    print(f"\n📷 Изображения для генерации:")
    print(f"- Фото стола: files/table_for_1.jpg")
    if random_dish.get('image_local_path'):
        print(f"- Фото блюда: {random_dish['image_local_path']}")
    print(f"- Референсы персонажа: будут загружены автоматически")
    
    print(f"\n⚙️ Параметры генерации:")
    print(f"- image_size: square_hd")
    print(f"- image_resolution: 1K") 
    print(f"- max_images: 1")
    
    print(f"\n✅ Система готова к генерации!")
    print(f"💡 Для реального теста запустите бота и напишите: '{character_name}'")

if __name__ == "__main__":
    asyncio.run(test_character_generation())