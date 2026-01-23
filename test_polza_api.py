#!/usr/bin/env python3
"""
Тест Polza AI API
"""
import requests
import json

def test_polza_api():
    url = "https://api.polza.ai/api/v1/chat/completions"
    token = "ak_NYI27neWOiQniROZ1SkUDSwotl6XIUvY87fCjNnSvWw"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    data = {
        "model": "mistralai/mistral-small-3.2-24b-instruct",
        "messages": [
            {"role": "user", "content": "Привет"}
        ],
        "max_tokens": 100
    }
    
    try:
        print("🔍 Тестируем Polza AI API...")
        print(f"URL: {url}")
        print(f"Token: {token[:20]}...")
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            if 'choices' in result and result['choices']:
                content = result['choices'][0]['message']['content']
                print(f"✅ AI ответ: {content}")
                return True
        
        print("❌ API не работает")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

if __name__ == "__main__":
    test_polza_api()