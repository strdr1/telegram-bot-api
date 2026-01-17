#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import requests
import base64
import random
from difflib import SequenceMatcher
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

BOT_TOKEN = "8232824966:AAGf-mgQLc58W9YIiil5lNnRD0GkcaFluYY"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Словарь для хранения истории сообщений пользователей
user_history = {}

def load_menu():
    try:
        with open('menu_cache.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def load_token():
    try:
        with open('token.txt', 'r') as f:
            return f.read().strip()
    except:
        return ""

def search_menu(query, menu_data, limit=5):
    results = []
    query_lower = query.lower()
    
    for menu_id, menu in menu_data.get('all_menus', {}).items():
        for category_id, category in menu.get('categories', {}).items():
            for item in category.get('items', []):
                name = item['name'].lower()
                similarity = SequenceMatcher(None, query_lower, name).ratio()
                if similarity > 0.3 or query_lower in name:
                    results.append({
                        'name': item['name'],
                        'price': item['price'],
                        'calories': item.get('calories', 'не указано'),
                        'category': category.get('name', ''),
                        'similarity': similarity
                    })
    
    return sorted(results, key=lambda x: x['similarity'], reverse=True)[:limit]

def get_dish_photo(dish_name, menu_data):
    """Поиск фото блюда в меню"""
    dish_name_lower = dish_name.lower()
    
    for menu_id, menu in menu_data.get('all_menus', {}).items():
        for category_id, category in menu.get('categories', {}).items():
            for item in category.get('items', []):
                if dish_name_lower in item['name'].lower():
                    image_url = item.get('image_url')
                    if image_url:
                        return {
                            'name': item['name'],
                            'image_url': image_url,
                            'price': item['price'],
                            'calories': item.get('calories', 'не указано'),
                            'description': item.get('description', '')
                        }
    return None

def gen_local_image(prompt):
    try:
        import time
        
        print(f"Начинаю генерацию: {prompt}")
        
        # Создаем задачу генерации
        url = "https://api.kie.ai/api/v1/jobs/createTask"
        headers = {
            "Authorization": "Bearer d6bd19312c6a075f3418d68ee943bda0",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "google/nano-banana",
            "input": {
                "prompt": prompt,
                "output_format": "png",
                "image_size": "1:1"
            }
        }
        
        print(f"Отправляю запрос на создание задачи...")
        response = requests.post(url, headers=headers, json=data)
        print(f"Статус ответа: {response.status_code}")
        print(f"Ответ: {response.text}")
        
        if response.status_code != 200:
            return f"Ошибка создания задачи: {response.text}"
        
        task_id = response.json()['data']['taskId']
        print(f"Задача создана: {task_id}")
        
        # Ждем результат
        status_url = f"https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId={task_id}"
        
        for i in range(60):
            time.sleep(2)
            print(f"Проверка статуса {i+1}/60...")
            status_response = requests.get(status_url, headers=headers)
            
            if status_response.status_code == 200:
                result = status_response.json()
                status = result['data']['status']
                print(f"Статус задачи: {status}")
                
                if status == 'completed':
                    image_url = result['data']['output']['images'][0]
                    print(f"Изображение готово: {image_url}")
                    return image_url
                elif status == 'failed':
                    print("Генерация не удалась")
                    return None
        
        print("Таймаут ожидания")
        return None
            
    except Exception as e:
        error_msg = f"Ошибка генерации: {str(e)}"
        print(error_msg)
        return error_msg
    try:
        url = "https://t2i.mcpcore.xyz/api/free/generate"
        data = {
            "prompt": prompt,
            "model": "turbo"
        }
        
        response = requests.post(url, json=data, stream=True, timeout=60)
        
        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        try:
                            data_json = json.loads(line[6:])
                            if data_json.get('status') == 'complete':
                                return data_json.get('imageUrl')
                        except:
                            continue
        return None
    except Exception as e:
        print(f"Ошибка генерации: {e}")
        return None

def get_ai_response(message, menu_data, token, user_id):
    try:
        # Получаем историю пользователя
        if user_id not in user_history:
            user_history[user_id] = []
        
        # Добавляем текущее сообщение
        user_history[user_id].append({"role": "user", "content": message})
        
        # Ограничиваем до 20 последних сообщений
        if len(user_history[user_id]) > 20:
            user_history[user_id] = user_history[user_id][-20:]
        
        menu_context = "МЕНЮ РЕСТОРАНА:\n\n"
        
        for menu_id, menu in menu_data.get('all_menus', {}).items():
            menu_name = menu.get('name', 'Без названия')
            clean_menu_name = menu_name.replace('🍳', '').replace('📋', '').replace('🍕', '').strip()
            menu_context += f"=== {clean_menu_name} ===\n"
            
            for category_id, category in menu.get('categories', {}).items():
                category_name = category.get('name', 'Без названия')
                clean_category = category_name.replace('🍕', '').replace('🥨', '').replace('🥗', '').replace('🍲', '').replace('🍚', '').replace('📁', '').replace('🍖', '').strip()
                menu_context += f"\n{clean_category}:\n"
                
                for item in category.get('items', []):
                    menu_context += f"• {item['name']} - {item['price']}₽"
                    if item.get('calories'):
                        menu_context += f" ({item['calories']} ккал)"
                    menu_context += "\n"
            menu_context += "\n"
        
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        system_prompt = (
            f"Ты продажник в ресторане. Отвечай просто и коротко, без звездочек и маркдауна. У тебя есть точное меню:\n{menu_context}\n\n"
            "ВСЕГДА используй ТОЧНЫЕ данные из меню выше. НЕ придумывай цифры! "
            "Если пользователь спрашивает про блюдо которого нет в меню - используй search_menu. "
            "Если пользователь просит фото - используй get_dish_photo. "
            "Если пользователь просит сгенерировать изображение - используй gen_image."
        )
        
        tools = [{
            "type": "function",
            "function": {
                "name": "search_menu",
                "description": "Поиск блюд в меню ресторана",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Название блюда для поиска"
                        }
                    },
                    "required": ["query"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "get_dish_photo",
                "description": "Получение фото блюда из меню",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dish_name": {
                            "type": "string",
                            "description": "Название блюда для поиска фото"
                        }
                    },
                    "required": ["dish_name"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "gen_image",
                "description": "Генерация изображения по описанию",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Описание изображения для генерации"
                        }
                    },
                    "required": ["prompt"]
                }
            }
        }]
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        data = {
            "model": "GigaChat",
            "messages": [
                {"role": "system", "content": system_prompt}
            ] + user_history[user_id],
            "temperature": 0.7
        }
        
        response = requests.post(url, headers=headers, json=data, verify=False, timeout=30)
        
        if response.status_code == 401:
            import subprocess
            import os
            subprocess.run(["python", "get_token.py"], cwd=os.getcwd())
            new_token = load_token()
            if new_token and new_token != token:
                headers["Authorization"] = f"Bearer {new_token}"
                response = requests.post(url, headers=headers, json=data, verify=False, timeout=30)
        
        if response.status_code == 200:
            result = response.json()['choices'][0]['message']
            response_text = result.get('content', '')
            
            # Парсим ответ на наличие вызовов функций
            if 'get_dish_photo(' in response_text:
                # Извлекаем название блюда из вызова функции
                import re
                match = re.search(r'get_dish_photo\(["\']([^"\']*)["\'\)]', response_text)
                if match:
                    dish_name = match.group(1)
                    dish_info = get_dish_photo(dish_name, menu_data)
                    
                    if dish_info:
                        user_history[user_id].append({"role": "assistant", "content": f"Вот фото {dish_info['name']}"})
                        return f"PHOTO:{dish_info['image_url']}|{dish_info['name']} - {dish_info['price']}₽ ({dish_info['calories']} ккал)\n{dish_info['description']}"
                    else:
                        return "Фото блюда не найдено"
            
            elif 'search_menu(' in response_text:
                # Извлекаем запрос для поиска
                match = re.search(r'search_menu\(["\']([^"\']*)["\'\)]', response_text)
                if match:
                    query = match.group(1)
                    search_results = search_menu(query, menu_data)
                    
                    if search_results:
                        result_text = f"Нашел в меню:\n"
                        for item in search_results[:3]:
                            result_text += f"{item['name']} - {item['price']}₽ ({item['calories']} ккал)\n"
                        user_history[user_id].append({"role": "assistant", "content": result_text})
                        return result_text
                    else:
                        return "Блюдо не найдено в меню"
            
            elif 'gen_image(' in response_text:
                # Извлекаем промпт для генерации
                match = re.search(r'gen_image\(["\']([^"\']*)["\'\)]', response_text)
                if match:
                    prompt = match.group(1)
                    image_url = gen_image(prompt)
                    
                    if image_url:
                        return f"Готово! Вот ваше изображение: {image_url}"
                    else:
                        return "Ошибка генерации изображения"
            
            # Обычный ответ
            user_history[user_id].append({"role": "assistant", "content": response_text})
            return response_text
        else:
            return f"Ошибка API: {response.status_code}"
    except Exception as e:
        return f"Ошибка: {str(e)}"

@dp.message(Command("gen"))
async def gen_handler(message: types.Message):
    prompt = message.text.replace('/gen', '').strip()
    if not prompt:
        await message.answer("Укажите описание: /gen <промпт>")
        return
    
    token = load_token()
    print(f"\n=== ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЯ ===")
    print(f"Исходный промпт: {prompt}")
    
    try:
        # Шаг 1: Улучшаем промпт через GigaChat
        import subprocess
        import os
        subprocess.run(["python", "get_token.py"], cwd=os.getcwd())
        token = load_token()
        
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        
        images = ['tables_holl.jpg', 'kassa.jpg', 'table_for_1.jpg']
        selected_image = random.choice(images)
        print(f"Выбрано изображение: {selected_image}")
        
        # Адаптируем промпт под выбранное изображение
        image_context = {
            'kassa.jpg': 'стоящего за кассой в ресторане',
            'tables_holl.jpg': 'сидящего за столом в зале ресторана',
            'table_for_1.jpg': 'сидящего за столиком на одного'
        }
        context = image_context.get(selected_image, 'сидящего за столом')
        
        improve_data = {
            "model": "GigaChat-Pro",
            "messages": [{"role": "user", "content": f"Переведи на английский кратко, добавь только небольшие детали для редактирования СУЩЕСТВУЮЩЕГО изображения (не создавай новую сцену). Адаптируй позу персонажа: {context}. Промпт: {prompt}"}],
            "temperature": 0.5
        }
        
        print("Улучшаю промпт через GigaChat...")
        improve_response = requests.post(url, headers=headers, json=improve_data, verify=False, timeout=30)
        
        if improve_response.status_code == 200:
            improved_prompt = improve_response.json()['choices'][0]['message']['content']
            print(f"Улучшенный промпт: {improved_prompt}")
        else:
            improved_prompt = prompt
            print(f"Ошибка улучшения ({improve_response.status_code}), использую оригинал")
        
        # Шаг 3: Загружаем изображение на freeimage.host
        import time
        
        with open(selected_image, 'rb') as f:
            files = {'source': f}
            print("Загрузка файла...")
            upload_response = requests.post("https://freeimage.host/api/1/upload", files=files, data={'key': '6d207e02198a847aa98d0a2a901485a5'})
        
        if upload_response.status_code != 200:
            await message.answer(f"Ошибка загрузки: {upload_response.text}")
            return
        
        file_url = upload_response.json()['image']['url']
        print(f"URL файла: {file_url}")
        
        kie_url = "https://api.kie.ai/api/v1/jobs/createTask"
        kie_headers = {
            "Authorization": "Bearer d6bd19312c6a075f3418d68ee943bda0",
            "Content-Type": "application/json"
        }
        
        kie_data = {
            "model": "google/nano-banana-edit",
            "input": {
                "prompt": improved_prompt,
                "image_urls": [file_url],
                "output_format": "png",
                "image_size": "1:1"
            }
        }
        
        print("Отправка запроса в KIE.AI...")
        kie_response = requests.post(kie_url, headers=kie_headers, json=kie_data)
        print(f"Статус: {kie_response.status_code}")
        
        if kie_response.status_code == 200:
            result_data = kie_response.json()
            
            if result_data.get('code') != 200:
                await message.answer(f"Ошибка KIE.AI: {result_data.get('msg')}")
                return
            
            task_id = result_data['data']['taskId']
            print(f"Задача создана: {task_id}")
            
            status_url = "https://api.kie.ai/api/v1/jobs/recordInfo"
            
            for i in range(20):
                time.sleep(3)
                print(f"Проверка статуса {i+1}/20...")
                status_response = requests.get(status_url, headers=kie_headers, params={'taskId': task_id})
                
                if status_response.status_code == 200:
                    result = status_response.json()
                    
                    if result.get('code') != 200:
                        print(f"Ошибка API: {result}")
                        await message.answer(f"Ошибка: {result.get('msg')}")
                        return
                    
                    state = result['data']['state']
                    print(f"Статус: {state}")
                    
                    if state == 'success':
                        result_json = json.loads(result['data']['resultJson'])
                        image_url = result_json['resultUrls'][0]
                        print(f"Готово: {image_url}")
                        await message.answer_photo(image_url, caption=f"Промпт: {prompt}")
                        return
                    elif state == 'fail':
                        error = result['data'].get('failMsg', 'Неизвестная ошибка')
                        print(f"Ошибка генерации: {error}")
                        await message.answer(f"Генерация не удалась: {error}")
                        return
                else:
                    print(f"Ошибка запроса статуса: {status_response.status_code}")
            
            await message.answer("Таймаут генерации")
        else:
            await message.answer(f"Ошибка KIE.AI: {kie_response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Привет! Я бот-продажник ресторана 🍽️\nСпрашивай про блюда, калории, цены!\nИспользуй /gen для генерации изображений!")

@dp.message()
async def message_handler(message: types.Message):
    menu_data = load_menu()
    
    if not menu_data:
        await message.answer("Ошибка загрузки меню")
        return
    
    # Всегда обновляем токен перед запросом
    import subprocess
    import os
    print("Обновляю токен...")
    subprocess.run(["python", "get_token.py"], cwd=os.getcwd())
    token = load_token()
    
    if not token:
        await message.answer("Ошибка загрузки токена")
        return
    
    response = get_ai_response(message.text, menu_data, token, message.from_user.id)
    
    # Проверяем на фото блюда
    if response.startswith("PHOTO:"):
        parts = response.split("|", 1)
        photo_url = parts[0].replace("PHOTO:", "")
        caption = parts[1] if len(parts) > 1 else ""
        await message.answer_photo(photo_url, caption=caption)
    else:
        await message.answer(response)

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())