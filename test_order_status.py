import requests

order_id = "989"
url = f"https://api.sbis.ru/retail/order/?externalId={order_id}"
token = "aT9ATVJhVWc9NnpSOmR2RzszKmE7NnclOlVWTmJsOls6LWZyTX5OZCgufnUdV89bVlsLT5LMlZT14tWzN0MTIwMjYtMDEtMDQgMTQ6NDU6NDYuOTMwOTY2"

headers = {
    "X-SBISAccessToken": token,
    "Accept": "application/json"
}
response = requests.get(url, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
