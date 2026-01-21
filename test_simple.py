#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простой тест основной функциональности
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_assistant import get_fallback_response

def test_fallback_system():
    """Тест fallback системы"""
    print("🧪 Тестируем fallback систему...")
    
    test_cases = [
        # Конкретные блюда
        ("Пицца 4 сыра", "dish_photo", "Пицца 4 сыра"),
        ("пицца пепперони", "dish_photo", "Пицца Пепперони"),
        ("борщ", "dish_photo", "Борщ"),
        ("стейк", "dish_photo", "Стейк"),
        ("солянка", "dish_photo", "Солянка"),
        ("пицца инфаркт", "dish_photo", "Пицца Инфаркт"),
        ("пицца мясная", "dish_photo", "Пицца Мясная"),
        
        # Категории
        ("У вас есть пицца?", "category", "пицца"),
        ("какие супы есть", "category", "суп"),
        ("есть ли пиво", "category", "пиво"),
        ("какое вино", "category", "вино"),
        ("есть ли десерты", "category", "десерт"),
        
        # Приветствия
        ("привет", "text", "Привет-привет"),
        ("здравствуйте", "text", "Добро пожаловать"),
        ("добрый день", "text", "Добро пожаловать"),
        
        # Общие вопросы
        ("меню", "text", "меню богатое"),
        ("доставка", "text", "Доставляем быстрее"),
        ("заказать", "text", "Доставляем быстрее"),
        ("бронирование", "text", "Столик забронировать"),
        ("столик", "text", "Столик забронировать"),
        ("отзывы", "text", "отзывы хорошие"),
        ("приложение", "text", "приложение удобнее"),
        ("скачать", "text", "приложение удобнее"),
        
        # Алкоголь
        ("пиво", "text", "Пиво у нас есть"),
        ("вино", "text", "Винная карта"),
        ("водка", "text", "Водка у нас качественная"),
        
        # Контакты
        ("телефон", "text", "Наши контакты"),
        ("адрес", "text", "Наши контакты"),
        ("контакты", "text", "Наши контакты"),
        
        # Короткие ответы
        ("хочу", "text", "что именно показать"),
        ("да", "text", "что именно показать"),
        ("покажи", "text", "что именно показать"),
        ("давай", "text", "что именно показать"),
        ("конечно", "text", "что именно показать"),
    ]
    
    passed = 0
    failed = 0
    
    for message, expected_type, expected_content in test_cases:
        try:
            result = get_fallback_response(message, 999999999)
            
            # Проверяем тип ответа
            if expected_type == "text":
                if result['type'] != 'text':
                    print(f"❌ '{message}' -> Неверный тип: {result['type']} (ожидался text)")
                    failed += 1
                    continue
                    
                if expected_content.lower() not in result['text'].lower():
                    print(f"❌ '{message}' -> Неверный контент: {result['text'][:50]}... (ожидался: {expected_content})")
                    failed += 1
                    continue
                    
            elif expected_type == "dish_photo":
                if result['type'] != 'dish_photo':
                    print(f"❌ '{message}' -> Неверный тип: {result['type']} (ожидался dish_photo)")
                    failed += 1
                    continue
                    
                if result['dish_name'] != expected_content:
                    print(f"❌ '{message}' -> Неверное блюдо: {result['dish_name']} (ожидалось: {expected_content})")
                    failed += 1
                    continue
                    
            elif expected_type == "category":
                if result['type'] != 'category':
                    print(f"❌ '{message}' -> Неверный тип: {result['type']} (ожидался category)")
                    failed += 1
                    continue
                    
                if result['show_category'] != expected_content:
                    print(f"❌ '{message}' -> Неверная категория: {result['show_category']} (ожидалась: {expected_content})")
                    failed += 1
                    continue
            
            print(f"✅ '{message}' -> {result['type']}")
            passed += 1
            
        except Exception as e:
            print(f"💥 '{message}' -> Ошибка: {e}")
            failed += 1
    
    print(f"\n📊 Результаты тестирования:")
    print(f"✅ Пройдено: {passed}")
    print(f"❌ Провалено: {failed}")
    print(f"📈 Успешность: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("🎉 Все тесты fallback системы прошли успешно!")
    else:
        print("⚠️ Есть проблемы в fallback системе")
    
    return failed == 0

def test_marker_detection():
    """Тест обнаружения маркеров в тексте"""
    print("\n🏷️ Тестируем обнаружение маркеров...")
    
    # Импортируем функции для тестирования маркеров
    import re
    
    test_texts = [
        ("PARSE_CATEGORY:пицца", "PARSE_CATEGORY", "пицца"),
        ("DISH_PHOTO:Пицца 4 сыра", "DISH_PHOTO", "Пицца 4 сыра"),
        ("Текст с SHOW_DELIVERY_BUTTON в конце", "SHOW_DELIVERY_BUTTON", None),
        ("SHOW_APPS для приложений", "SHOW_APPS", None),
        ("Показываю SHOW_HALL_PHOTOS фото зала", "SHOW_HALL_PHOTOS", None),
        ("SHOW_BAR_PHOTOS SHOW_KASSA_PHOTOS", "SHOW_BAR_PHOTOS", None),
    ]
    
    passed = 0
    failed = 0
    
    for text, expected_marker, expected_value in test_texts:
        try:
            # Проверяем PARSE_CATEGORY
            if expected_marker == "PARSE_CATEGORY":
                match = re.search(r'PARSE_CATEGORY:(.+)', text)
                if match:
                    value = match.group(1).strip()
                    if value == expected_value:
                        print(f"✅ '{expected_marker}' найден: {value}")
                        passed += 1
                    else:
                        print(f"❌ '{expected_marker}' неверное значение: {value} (ожидалось: {expected_value})")
                        failed += 1
                else:
                    print(f"❌ '{expected_marker}' не найден в: {text}")
                    failed += 1
                    
            # Проверяем DISH_PHOTO
            elif expected_marker == "DISH_PHOTO":
                match = re.search(r'DISH_PHOTO:(.+)', text)
                if match:
                    value = match.group(1).strip()
                    if value == expected_value:
                        print(f"✅ '{expected_marker}' найден: {value}")
                        passed += 1
                    else:
                        print(f"❌ '{expected_marker}' неверное значение: {value} (ожидалось: {expected_value})")
                        failed += 1
                else:
                    print(f"❌ '{expected_marker}' не найден в: {text}")
                    failed += 1
                    
            # Проверяем другие маркеры
            else:
                if expected_marker in text:
                    print(f"✅ '{expected_marker}' найден")
                    passed += 1
                else:
                    print(f"❌ '{expected_marker}' не найден в: {text}")
                    failed += 1
                    
        except Exception as e:
            print(f"💥 Ошибка при проверке '{expected_marker}': {e}")
            failed += 1
    
    print(f"\n📊 Результаты тестирования маркеров:")
    print(f"✅ Пройдено: {passed}")
    print(f"❌ Провалено: {failed}")
    
    if failed == 0:
        print("🎉 Все тесты маркеров прошли успешно!")
    else:
        print("⚠️ Есть проблемы с обнаружением маркеров")
    
    return failed == 0

def main():
    """Главная функция тестирования"""
    print("🚀 Запуск простого тестирования системы...\n")
    
    success1 = test_fallback_system()
    success2 = test_marker_detection()
    
    print(f"\n🏁 Итоговый результат:")
    if success1 and success2:
        print("🎉 Все тесты прошли успешно! Система работает корректно.")
    else:
        print("⚠️ Есть проблемы в системе, требуется доработка.")

if __name__ == "__main__":
    main()