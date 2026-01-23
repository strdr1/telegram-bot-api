#!/usr/bin/env python3
"""
Автоматическое исправление всех проблем
"""
import subprocess
import os
import time
import requests
import json

def run_ssh_command(command):
    """Выполнить SSH команду с автоматическим вводом пароля"""
    full_command = f'sshpass -p "Mashkov.Rest" ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "{command}"'
    try:
        result = subprocess.run(full_command, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def upload_file(local_path, remote_path):
    """Загрузить файл на сервер"""
    command = f'sshpass -p "Mashkov.Rest" scp -o StrictHostKeyChecking=no "{local_path}" root@a950841.fvds.ru:"{remote_path}"'
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except:
        return False

def main():
    print("🔧 Автоматическое исправление всех проблем...")
    
    # 1. Проверяем статус сервисов
    print("\n1️⃣ Проверяем статус сервисов...")
    success, output, error = run_ssh_command("supervisorctl status")
    if success:
        print("✅ Сервисы:")
        print(output)
    else:
        print(f"❌ Ошибка проверки сервисов: {error}")
    
    # 2. Создаем токен AI
    print("\n2️⃣ Создаем токен AI...")
    success, _, _ = run_ssh_command("mkdir -p /opt/telegram-bot/ai_ref")
    if success:
        success, _, _ = run_ssh_command("echo 'ak_MUlqpkRNU2jE5Xo3tf2yOfZImxVP90gcvvcN2Neif2g' > /opt/telegram-bot/ai_ref/token.txt")
        if success:
            print("✅ Токен AI создан")
        else:
            print("❌ Ошибка создания токена")
    
    # 3. Загружаем исправленные файлы
    print("\n3️⃣ Загружаем исправленные файлы...")
    files_to_upload = [
        ("miniapp_server.py", "/opt/telegram-bot/miniapp_server.py"),
        ("miniapp/admin.html", "/opt/telegram-bot/miniapp/admin.html"),
        ("keyboards.py", "/opt/telegram-bot/keyboards.py"),
        ("ai_assistant.py", "/opt/telegram-bot/ai_assistant.py")
    ]
    
    for local_file, remote_file in files_to_upload:
        if os.path.exists(local_file):
            if upload_file(local_file, remote_file):
                print(f"✅ {local_file} загружен")
            else:
                print(f"❌ Ошибка загрузки {local_file}")
        else:
            print(f"⚠️ Файл {local_file} не найден")
    
    # 4. Перезапускаем сервисы
    print("\n4️⃣ Перезапускаем сервисы...")
    services = [
        "telegram-bot-group:telegram-bot",
        "telegram-bot-group:miniapp-api"
    ]
    
    for service in services:
        success, _, _ = run_ssh_command(f"cd /opt/telegram-bot && supervisorctl restart {service}")
        if success:
            print(f"✅ {service} перезапущен")
        else:
            print(f"❌ Ошибка перезапуска {service}")
        time.sleep(2)
    
    # 5. Тестируем API
    print("\n5️⃣ Тестируем API...")
    try:
        # Тест чатов
        response = requests.get("https://a950841.fvds.ru/api/chats", timeout=10)
        if response.status_code == 200:
            chats = response.json()
            print(f"✅ API чатов работает: {len(chats)} чатов")
        else:
            print(f"❌ API чатов не работает: {response.status_code}")
        
        # Тест статистики
        response = requests.get("https://a950841.fvds.ru/api/stats", timeout=10)
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ API статистики работает: {stats}")
        else:
            print(f"❌ API статистики не работает: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Ошибка тестирования API: {e}")
    
    # 6. Тестируем AI
    print("\n6️⃣ Тестируем AI...")
    success, output, error = run_ssh_command("cd /opt/telegram-bot && python3 test_polza_api.py")
    if success and "✅ AI ответ:" in output:
        print("✅ AI работает")
    else:
        print(f"❌ AI не работает: {output} {error}")
    
    # 7. Проверяем админ-панель
    print("\n7️⃣ Проверяем админ-панель...")
    try:
        response = requests.get("https://a950841.fvds.ru/miniapp/admin.html", timeout=10)
        if response.status_code == 200 and "Админ-панель Mashkov" in response.text:
            print("✅ Админ-панель доступна")
        else:
            print(f"❌ Админ-панель недоступна: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка проверки админ-панели: {e}")
    
    print("\n🎉 Диагностика завершена!")
    print("\n📋 Что проверить:")
    print("1. Админ-панель: https://a950841.fvds.ru/miniapp/admin.html")
    print("2. Напиши боту любое сообщение для проверки AI")
    print("3. Проверь кнопку 'Управление чатами' в админке бота")

if __name__ == "__main__":
    main()