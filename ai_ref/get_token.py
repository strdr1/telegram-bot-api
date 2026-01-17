import requests
import uuid
import base64

def get_gigachat_token(authorization_key):
    """
    Получение токена доступа для GigaChat API
    
    Args:
        authorization_key (str): Ключ авторизации из личного кабинета
    
    Returns:
        dict: Ответ с токеном доступа и временем истечения
    """
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {authorization_key}"
    }
    
    data = {
        "scope": "GIGACHAT_API_PERS"
    }
    
    response = requests.post(url, headers=headers, data=data, verify=False)
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Ошибка получения токена: {response.status_code} - {response.text}")

if __name__ == "__main__":
    # Замените на ваш ключ авторизации
    auth_key = "MDE5YmIyNGEtMmMyYS03YmYyLWE1YTctYzBiOTk0ZDNiODI3OjNkNmJkNDg5LTU4MzUtNGE0My1iMmQzLWRhMzQzZmE4MTMzNQ=="
    
    try:
        token_data = get_gigachat_token(auth_key)
        access_token = token_data['access_token']
        
        # Сохраняем токен в файл
        with open('token.txt', 'w') as f:
            f.write(access_token)
        
        print(f"Токен доступа: {access_token}")
        print(f"Истекает: {token_data['expires_at']}")
    except Exception as e:
        print(f"Ошибка: {e}")