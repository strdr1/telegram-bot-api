# Миниапп Админки - Развертывание

## Проблема
Миниапп работает на GitHub Pages, но JavaScript не может напрямую работать с базой данных SQLite. Нужен API сервер.

## Решение
Развернуть Flask API сервер на бесплатном хостинге, который будет предоставлять данные миниаппу.

## Шаг 1: Подготовка файлов

У вас должны быть файлы:
- `miniapp_server.py` - Flask API сервер
- `database.py` - функции работы с БД
- `requirements.txt` - зависимости Python
- `restaurant.db` - ваша база данных

## Шаг 2: Развертывание API сервера

### Вариант 1: Railway (Рекомендуется - бесплатно)

1. Зарегистрируйтесь на [Railway.app](https://railway.app)
2. Создайте новый проект
3. Подключите GitHub репозиторий
4. Railway автоматически обнаружит Python проект
5. Добавьте переменные окружения (если нужно)
6. Разверните проект

### Вариант 2: Render (Бесплатно)

1. Зарегистрируйтесь на [Render.com](https://render.com)
2. Создайте новый Web Service
3. Подключите GitHub репозиторий
4. Укажите:
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python miniapp_server.py`
5. Разверните

### Вариант 3: Heroku

1. Зарегистрируйтесь на [Heroku.com](https://heroku.com)
2. Создайте новое приложение
3. Подключите GitHub
4. Разверните из ветки main

## Шаг 3: Настройка миниаппа

1. Откройте `miniapp/index.html`
2. Найдите строку:
   ```javascript
   const API_BASE = 'http://localhost:8080'; // ← ЗАМЕНИТЕ НА ВАШ ПРОДАКШЕН СЕРВЕР
   ```
3. Замените `http://localhost:8080` на URL вашего развернутого API сервера (например, `https://your-api.onrender.com`)
4. Загрузите `miniapp/index.html` на GitHub Pages по адресу https://strdr1.github.io/Admin-app/

## Новая опция: Запуск бота и API вместе

Используйте `bot_with_api.py` для запуска бота и API в одном процессе:

```bash
python bot_with_api.py
```

Или для продакшена используйте `production_api.py`:

```bash
python production_api.py
```

## Шаг 4: Проверка работы

1. Откройте миниапп по адресу https://strdr1.github.io/Admin-app/
2. Проверьте в консоли браузера (F12), что API запросы работают
3. Убедитесь, что чаты загружаются из базы данных

## Структура API

```
GET  /api/chats           - Получить все чаты
GET  /api/chats/{id}      - Получить сообщения чата
POST /api/chats/{id}/messages - Отправить сообщение
PUT  /api/chats/{id}/status   - Изменить статус чата
GET  /api/stats           - Получить статистику
GET  /health              - Проверка работоспособности
```

## Локальная разработка

Для тестирования локально:
```bash
pip install -r requirements.txt
python miniapp_server.py
```

Миниапп будет доступен на http://localhost:8080/

## Важно!

- **База данных** должна быть в той же папке, что и `miniapp_server.py`
- **CORS** включен для работы с GitHub Pages
- **HTTPS** обязателен для Telegram Web Apps
- **Бесплатные хостинги** могут иметь лимиты на использование

## Troubleshooting

### Ошибка CORS
Убедитесь, что в `miniapp_server.py` есть строка:
```python
CORS(app)
```

### База данных не найдена
Убедитесь, что `restaurant.db` находится в корне проекта на сервере.

### API возвращает ошибки
Проверьте логи сервера в панели управления хостингом.

## Альтернативные решения

Если не хотите развертывать отдельный сервер:
1. Использовать Supabase/Vercel Edge Functions
2. Перейти на платный хостинг с базой данных
3. Использовать Telegram Bot API как прокси (сложно)
