#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys

def test_prompt_reading():
    print("Проверка чтения промпта персонажей...")

    try:
        if os.path.exists('character_prompt.txt'):
            with open('character_prompt.txt', 'r', encoding='utf-8') as f:
                admin_character_prompt = f.read().strip()
            print(f'✓ Файл найден, содержимое: "{admin_character_prompt}"')

            # Проверяем добавление к базовому промпту
            base_prompt = "КРИТИЧЕСКИ ВАЖНО! Если пользователь спрашивает про любых персонажей..."
            if admin_character_prompt:
                full_prompt = base_prompt + f"\n\nДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ОТ АДМИНА:\n{admin_character_prompt}"
                print(f'✓ Полный промпт будет содержать настройку: "{admin_character_prompt}"')
                print(f'✓ Длина полного промпта: {len(full_prompt)} символов')
                return True
            else:
                print('✗ Файл пустой')
                return False
        else:
            print('✗ Файл character_prompt.txt не найден')
            return False
    except Exception as e:
        print(f'✗ Ошибка чтения файла: {e}')
        return False

if __name__ == "__main__":
    test_prompt_reading()
