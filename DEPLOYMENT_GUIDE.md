# 🚀 Руководство по развертыванию Telegram Bot на сервере

## 📋 Информация о сервере
- **Домен**: a950841.fvds.ru
- **IP**: 155.212.164.61
- **ОС**: Ubuntu 24.04
- **ID сервера**: 16430504

## 🔧 Автоматическое развертывание

### 1. Подключение к серверу
```bash
ssh root@155.212.164.61
```

### 2. Запуск скрипта развертывания
```bash
# Скачиваем и запускаем скрипт развертывания
curl -sSL https://raw.githubusercontent.com/strdr1/telegram-bot-api/master/deploy.sh | bash
```

### 3. Настройка переменных окружения
```bash
# Редактируем .env файл
sudo nano /opt/telegram-bot/.env
```

**Обязательные переменные:**
```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_ID=your_telegram_user_id
POLZA_AI_TOKEN=your_polza_ai_token
PRESTO_API_TOKEN=your_presto_api_token
WEBHOOK_MODE=true
WEBHOOK_URL=https://a950841.fvds.ru/webhook
```

### 4. Настройка SSL сертификата
```bash
# Запускаем скрипт настройки SSL
sudo /opt/telegram-bot/setup-ssl.sh
```

### 5. Настройка Nginx
```bash
# Копируем конфигурацию Nginx
sudo cp /opt/telegram-bot/nginx.conf /etc/nginx/sites-available/telegram-bot
sudo ln -sf /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Проверяем конфигурацию и перезапускаем
sudo nginx -t
sudo systemctl restart nginx
```

### 6. Настройка Supervisor
```bash
# Копируем конфигурацию Supervisor
sudo cp /opt/telegram-bot/supervisor.conf /etc/supervisor/conf.d/telegram-bot.conf

# Перезагружаем конфигурацию
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start telegram-bot-group
```

### 7. Настройка миниаппа
```bash
# Запускаем скрипт настройки миниаппа
sudo /opt/telegram-bot/setup-miniapp.sh
```

## 🔍 Проверка работы

### Проверка статуса сервисов
```bash
# Статус Nginx
sudo systemctl status nginx

# Статус Supervisor
sudo supervisorctl status

# Логи бота
sudo tail -f /var/log/telegram-bot/bot.log

# Логи Nginx
sudo tail -f /var/log/nginx/telegram-bot.access.log
sudo tail -f /var/log/nginx/telegram-bot.error.log
```

### Проверка webhook
```bash
# Проверка health endpoint
curl https://a950841.fvds.ru/health

# Проверка webhook (должен вернуть 405 Method Not Allowed для GET)
curl https://a950841.fvds.ru/webhook
```

## 🛠️ Управление сервисами

### Supervisor команды
```bash
# Статус всех процессов
sudo supervisorctl status

# Перезапуск бота
sudo supervisorctl restart telegram-bot

# Перезапуск планировщика
sudo supervisorctl restart telegram-bot-scheduler

# Перезапуск всей группы
sudo supervisorctl restart telegram-bot-group

# Остановка/запуск
sudo supervisorctl stop telegram-bot-group
sudo supervisorctl start telegram-bot-group
```

### Nginx команды
```bash
# Перезапуск Nginx
sudo systemctl restart nginx

# Проверка конфигурации
sudo nginx -t

# Перезагрузка конфигурации
sudo systemctl reload nginx
```

## 📱 Настройка миниаппа в Telegram

### 1. Создание миниаппа в BotFather
1. Отправьте `/newapp` в @BotFather
2. Выберите вашего бота
3. Введите название: "Ресторан Машков"
4. Введите описание: "Заказ доставки из ресторана Машков"
5. Загрузите фото (512x512 px)
6. Введите URL: `https://a950841.fvds.ru/miniapp/`

### 2. Альтернативный URL (GitHub Pages)
Если основной сервер недоступен, используйте:
`https://strdr1.github.io/mashkov-telegram-app/`

## 🔄 Автообновление

Система автообновления настроена и работает:
- Проверка обновлений каждые 30 минут
- Автоматическое обновление из GitHub
- Резервное копирование перед обновлением
- Автоматический перезапуск после обновления

### Ручное обновление
```bash
# Переход в директорию проекта
cd /opt/telegram-bot

# Обновление из GitHub
sudo -u botuser git pull origin master

# Установка новых зависимостей
sudo -u botuser /opt/telegram-bot/venv/bin/pip install -r requirements.txt

# Перезапуск сервисов
sudo supervisorctl restart telegram-bot-group
```

## 🔧 Мониторинг

### Скрипт мониторинга
```bash
# Запуск скрипта мониторинга
sudo /opt/telegram-bot/monitor.sh
```

### Логи
- **Бот**: `/var/log/telegram-bot/bot.log`
- **Планировщик**: `/var/log/telegram-bot/scheduler.log`
- **Nginx доступ**: `/var/log/nginx/telegram-bot.access.log`
- **Nginx ошибки**: `/var/log/nginx/telegram-bot.error.log`

## 🚨 Устранение неполадок

### Бот не отвечает
1. Проверьте статус процессов: `sudo supervisorctl status`
2. Проверьте логи: `sudo tail -f /var/log/telegram-bot/bot.log`
3. Перезапустите бота: `sudo supervisorctl restart telegram-bot`

### Webhook не работает
1. Проверьте SSL сертификат: `curl -I https://a950841.fvds.ru`
2. Проверьте Nginx: `sudo nginx -t && sudo systemctl status nginx`
3. Проверьте логи Nginx: `sudo tail -f /var/log/nginx/telegram-bot.error.log`

### Миниапп не загружается
1. Проверьте файлы: `ls -la /opt/telegram-bot/miniapp/`
2. Проверьте права: `sudo chown -R botuser:botuser /opt/telegram-bot/miniapp`
3. Проверьте Nginx конфигурацию для `/miniapp/`

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи всех сервисов
2. Убедитесь, что все переменные окружения настроены
3. Проверьте статус всех сервисов
4. При необходимости перезапустите все сервисы

## 🔐 Безопасность

- SSL сертификат автоматически обновляется
- Nginx настроен с security headers
- Rate limiting для webhook
- Процессы запускаются от непривилегированного пользователя
- Ограничения доступа к файлам системы