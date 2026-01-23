# 🚀 Полное руководство по развертыванию Telegram-бота ресторана Mashkov

## 📋 Содержание
1. [Требования к серверу](#требования-к-серверу)
2. [Подготовка сервера](#подготовка-сервера)
3. [Установка зависимостей](#установка-зависимостей)
4. [Настройка бота](#настройка-бота)
5. [Настройка базы данных](#настройка-базы-данных)
6. [Настройка веб-сервера](#настройка-веб-сервера)
7. [Настройка SSL](#настройка-ssl)
8. [Настройка процессов](#настройка-процессов)
9. [Настройка мини-приложения](#настройка-мини-приложения)
10. [Автоматическое развертывание](#автоматическое-развертывание)
11. [Мониторинг и логи](#мониторинг-и-логи)
12. [Резервное копирование](#резервное-копирование)
13. [Устранение неполадок](#устранение-неполадок)

---

## 🖥️ Требования к серверу

### Минимальные требования:
- **ОС**: Ubuntu 20.04+ или CentOS 8+
- **RAM**: 2GB (рекомендуется 4GB)
- **CPU**: 2 ядра
- **Диск**: 20GB SSD
- **Сеть**: Статический IP-адрес

### Рекомендуемые требования:
- **ОС**: Ubuntu 24.04 LTS
- **RAM**: 4GB
- **CPU**: 4 ядра
- **Диск**: 40GB SSD
- **Сеть**: Статический IP + домен

---

## 🔧 Подготовка сервера

### 1. Обновление системы
```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

### 2. Создание пользователя (опционально)
```bash
sudo adduser botuser
sudo usermod -aG sudo botuser
su - botuser
```

### 3. Настройка SSH (рекомендуется)
```bash
# Генерация SSH ключей на локальной машине
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Копирование ключа на сервер
ssh-copy-id root@your_server_ip
```

---

## 📦 Установка зависимостей

### 1. Python и pip
```bash
sudo apt install python3 python3-pip python3-venv -y
```

### 2. Git
```bash
sudo apt install git -y
```

### 3. Nginx
```bash
sudo apt install nginx -y
sudo systemctl enable nginx
sudo systemctl start nginx
```

### 4. Supervisor
```bash
sudo apt install supervisor -y
sudo systemctl enable supervisor
sudo systemctl start supervisor
```

### 5. Certbot (для SSL)
```bash
sudo apt install certbot python3-certbot-nginx -y
```

### 6. Дополнительные пакеты
```bash
sudo apt install curl wget unzip htop nano -y
```

---

## 🤖 Настройка бота

### 1. Клонирование репозитория
```bash
cd /root
git clone https://github.com/strdr1/telegram-bot-api.git telegram-bot
cd telegram-bot
```

### 2. Создание виртуального окружения
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Установка Python зависимостей
```bash
pip install -r requirements.txt
```

### 4. Настройка конфигурации
```bash
cp .env.example .env
nano .env
```

**Содержимое .env файла:**
```env
# Telegram Bot Token (получить у @BotFather)
BOT_TOKEN=your_bot_token_here

# Webhook URL (ваш домен)
WEBHOOK_URL=https://yourdomain.com/webhook

# Presto API настройки
PRESTO_API_URL=https://api.presto.ru
PRESTO_LOGIN=your_login
PRESTO_PASSWORD=your_password

# AI настройки
POLZA_AI_TOKEN=your_polza_ai_token

# Админы (Telegram User ID через запятую)
ADMIN_IDS=123456789,987654321

# База данных
DATABASE_PATH=restaurant.db

# Логирование
LOG_LEVEL=INFO
```

### 5. Инициализация базы данных
```bash
python3 database.py
```

---

## 🗄️ Настройка базы данных

### 1. Создание структуры БД
База данных SQLite создается автоматически при первом запуске. Основные таблицы:

- `users` - пользователи
- `chat_messages` - сообщения чатов
- `bookings` - бронирования
- `faq` - часто задаваемые вопросы
- `reviews` - отзывы
- `settings` - настройки системы

### 2. Настройка прав доступа
```bash
chmod 644 restaurant.db
chown root:root restaurant.db
```

### 3. Резервное копирование БД
```bash
# Создание бэкапа
cp restaurant.db restaurant_backup_$(date +%Y%m%d_%H%M%S).db

# Автоматический бэкап (добавить в crontab)
echo "0 2 * * * cd /root/telegram-bot && cp restaurant.db backups/restaurant_backup_\$(date +\%Y\%m\%d_\%H\%M\%S).db" | crontab -
```

---

## 🌐 Настройка веб-сервера

### 1. Создание конфигурации Nginx
```bash
sudo nano /etc/nginx/sites-available/telegram-bot
```

**Содержимое конфигурации:**
```nginx
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=webhook:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=general:10m rate=1r/s;

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Logs
    access_log /var/log/nginx/telegram-bot.access.log;
    error_log /var/log/nginx/telegram-bot.error.log;

    # Telegram Webhook
    location /webhook {
        limit_req zone=webhook burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_read_timeout 30s;
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
    }

    # API для мини-приложения
    location /api/ {
        limit_req zone=general burst=10 nodelay;
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS headers
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS";
        add_header Access-Control-Allow-Headers "Content-Type, Authorization";
        
        if ($request_method = 'OPTIONS') {
            return 204;
        }
    }

    # Статические файлы мини-приложения
    location /miniapp/ {
        alias /var/www/telegram-bot/miniapp/;
        try_files $uri $uri/ =404;
        
        # Cache static files
        expires 1h;
        add_header Cache-Control "public, immutable";
    }

    # Загрузка файлов
    location /uploads/ {
        alias /root/telegram-bot/files/;
        try_files $uri =404;
    }

    # Health check
    location /health {
        access_log off;
        return 200 "OK";
        add_header Content-Type text/plain;
    }
}
```

### 2. Активация конфигурации
```bash
sudo ln -s /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🔒 Настройка SSL

### 1. Получение SSL сертификата
```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### 2. Автоматическое обновление сертификата
```bash
sudo crontab -e
# Добавить строку:
0 12 * * * /usr/bin/certbot renew --quiet
```

### 3. Проверка SSL
```bash
sudo certbot certificates
```

---

## ⚙️ Настройка процессов

### 1. Создание конфигурации Supervisor
```bash
sudo nano /etc/supervisor/conf.d/telegram-bot.conf
```

**Содержимое конфигурации:**
```ini
[group:telegram-bot-group]
programs=telegram-bot,miniapp-api,telegram-bot-scheduler

[program:telegram-bot]
command=/root/telegram-bot/venv/bin/python /root/telegram-bot/bot.py
directory=/root/telegram-bot
user=root
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/telegram-bot.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
environment=PYTHONPATH="/root/telegram-bot"

[program:miniapp-api]
command=/root/telegram-bot/venv/bin/python /root/telegram-bot/miniapp_server.py
directory=/root/telegram-bot
user=root
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/miniapp-api.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
environment=PYTHONPATH="/root/telegram-bot"

[program:telegram-bot-scheduler]
command=/root/telegram-bot/venv/bin/python /root/telegram-bot/schedule_updates.py
directory=/root/telegram-bot
user=root
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/scheduler.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
environment=PYTHONPATH="/root/telegram-bot"
```

### 2. Обновление конфигурации Supervisor
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start all
```

### 3. Проверка статуса процессов
```bash
sudo supervisorctl status
```

---

## 📱 Настройка мини-приложения

### 1. Создание директории для статических файлов
```bash
sudo mkdir -p /var/www/telegram-bot/miniapp
sudo chown -R www-data:www-data /var/www/telegram-bot
```

### 2. Копирование файлов мини-приложения
```bash
cp /root/telegram-bot/miniapp/* /var/www/telegram-bot/miniapp/
```

### 3. Настройка прав доступа
```bash
sudo chmod 644 /var/www/telegram-bot/miniapp/*
sudo chmod 755 /var/www/telegram-bot/miniapp
```

### 4. Создание мини-приложения в BotFather
1. Отправьте `/newapp` боту @BotFather
2. Выберите вашего бота
3. Введите название: `Admin`
4. Введите описание: `Admin panel for restaurant bot`
5. Загрузите фото (512x512 px)
6. Введите URL: `https://yourdomain.com/miniapp/admin.html`

---

## 🔄 Автоматическое развертывание

### 1. Создание скрипта развертывания
```bash
nano /root/telegram-bot/deploy.sh
```

**Содержимое скрипта:**
```bash
#!/bin/bash

echo "🚀 Начинаем развертывание..."

# Переход в директорию проекта
cd /root/telegram-bot

# Остановка процессов
echo "⏹️ Остановка процессов..."
supervisorctl stop all

# Обновление кода
echo "📥 Обновление кода..."
git pull origin master

# Обновление зависимостей
echo "📦 Обновление зависимостей..."
source venv/bin/activate
pip install -r requirements.txt

# Копирование файлов мини-приложения
echo "📱 Обновление мини-приложения..."
cp miniapp/* /var/www/telegram-bot/miniapp/

# Запуск процессов
echo "▶️ Запуск процессов..."
supervisorctl start all

# Проверка статуса
echo "✅ Проверка статуса..."
supervisorctl status

echo "🎉 Развертывание завершено!"
```

### 2. Настройка прав выполнения
```bash
chmod +x /root/telegram-bot/deploy.sh
```

### 3. Создание webhook для автоматического развертывания
```bash
nano /root/telegram-bot/webhook_deploy.py
```

**Содержимое webhook:**
```python
#!/usr/bin/env python3
from flask import Flask, request
import subprocess
import hmac
import hashlib

app = Flask(__name__)
SECRET = "your_github_webhook_secret"

@app.route('/deploy', methods=['POST'])
def deploy():
    signature = request.headers.get('X-Hub-Signature-256')
    if signature:
        expected = 'sha256=' + hmac.new(
            SECRET.encode(),
            request.data,
            hashlib.sha256
        ).hexdigest()
        
        if hmac.compare_digest(signature, expected):
            subprocess.run(['/root/telegram-bot/deploy.sh'])
            return 'Deployed', 200
    
    return 'Unauthorized', 401

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)
```

---

## 📊 Мониторинг и логи

### 1. Просмотр логов
```bash
# Логи бота
sudo tail -f /var/log/supervisor/telegram-bot.log

# Логи API
sudo tail -f /var/log/supervisor/miniapp-api.log

# Логи Nginx
sudo tail -f /var/log/nginx/telegram-bot.access.log
sudo tail -f /var/log/nginx/telegram-bot.error.log

# Системные логи
sudo journalctl -u supervisor -f
```

### 2. Мониторинг процессов
```bash
# Статус процессов
sudo supervisorctl status

# Использование ресурсов
htop

# Дисковое пространство
df -h

# Сетевые подключения
netstat -tulpn | grep :8000
netstat -tulpn | grep :8080
```

### 3. Настройка алертов
```bash
# Создание скрипта проверки
nano /root/telegram-bot/health_check.sh
```

**Содержимое скрипта:**
```bash
#!/bin/bash

# Проверка процессов
if ! supervisorctl status telegram-bot | grep -q RUNNING; then
    echo "❌ Telegram bot не запущен!"
    supervisorctl start telegram-bot
fi

if ! supervisorctl status miniapp-api | grep -q RUNNING; then
    echo "❌ API сервер не запущен!"
    supervisorctl start miniapp-api
fi

# Проверка доступности
if ! curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "❌ Бот недоступен!"
fi

if ! curl -f http://localhost:8080/chats > /dev/null 2>&1; then
    echo "❌ API недоступен!"
fi
```

### 4. Добавление в crontab
```bash
crontab -e
# Добавить:
*/5 * * * * /root/telegram-bot/health_check.sh
```

---

## 💾 Резервное копирование

### 1. Создание скрипта бэкапа
```bash
nano /root/telegram-bot/backup.sh
```

**Содержимое скрипта:**
```bash
#!/bin/bash

BACKUP_DIR="/root/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Бэкап базы данных
cp /root/telegram-bot/restaurant.db $BACKUP_DIR/restaurant_$DATE.db

# Бэкап конфигурации
tar -czf $BACKUP_DIR/config_$DATE.tar.gz \
    /root/telegram-bot/.env \
    /etc/nginx/sites-available/telegram-bot \
    /etc/supervisor/conf.d/telegram-bot.conf

# Бэкап файлов
tar -czf $BACKUP_DIR/files_$DATE.tar.gz /root/telegram-bot/files/

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "✅ Бэкап создан: $DATE"
```

### 2. Автоматизация бэкапов
```bash
chmod +x /root/telegram-bot/backup.sh
crontab -e
# Добавить:
0 3 * * * /root/telegram-bot/backup.sh
```

---

## 🔧 Устранение неполадок

### Частые проблемы и решения:

#### 1. Бот не отвечает
```bash
# Проверка процесса
supervisorctl status telegram-bot

# Перезапуск
supervisorctl restart telegram-bot

# Проверка логов
tail -f /var/log/supervisor/telegram-bot.log
```

#### 2. Мини-приложение не загружается
```bash
# Проверка API
curl http://localhost:8080/chats

# Проверка статических файлов
ls -la /var/www/telegram-bot/miniapp/

# Проверка Nginx
nginx -t
systemctl status nginx
```

#### 3. SSL проблемы
```bash
# Проверка сертификата
certbot certificates

# Обновление сертификата
certbot renew

# Проверка конфигурации Nginx
nginx -t
```

#### 4. База данных заблокирована
```bash
# Проверка процессов использующих БД
lsof /root/telegram-bot/restaurant.db

# Перезапуск всех процессов
supervisorctl restart all
```

#### 5. Высокое использование ресурсов
```bash
# Проверка использования CPU/RAM
htop

# Проверка логов на ошибки
grep -i error /var/log/supervisor/*.log

# Очистка логов
truncate -s 0 /var/log/supervisor/*.log
```

---

## 📞 Поддержка

### Полезные команды:
```bash
# Полная перезагрузка всех сервисов
systemctl restart nginx supervisor

# Проверка всех портов
netstat -tulpn | grep -E ':(80|443|8000|8080)'

# Проверка дискового пространства
du -sh /root/telegram-bot/*

# Мониторинг в реальном времени
watch -n 1 'supervisorctl status'
```

### Контакты для поддержки:
- **Документация**: Этот файл
- **Логи**: `/var/log/supervisor/`
- **Конфигурация**: `/root/telegram-bot/.env`

---

## ✅ Чек-лист развертывания

- [ ] Сервер подготовлен и обновлен
- [ ] Установлены все зависимости
- [ ] Настроен домен и DNS
- [ ] Получен SSL сертификат
- [ ] Настроен Nginx
- [ ] Настроен Supervisor
- [ ] Создан Telegram бот в BotFather
- [ ] Создано мини-приложение в BotFather
- [ ] Настроены переменные окружения
- [ ] Инициализирована база данных
- [ ] Запущены все процессы
- [ ] Настроено резервное копирование
- [ ] Настроен мониторинг
- [ ] Проведено тестирование

**🎉 Поздравляем! Ваш бот успешно развернут и готов к работе!**