#!/bin/bash

# Скрипт развертывания Telegram Bot на Ubuntu 24.04
# Сервер: a950841.fvds.ru (155.212.164.61)

set -e

echo "🚀 Начинаем развертывание Telegram Bot..."

# Обновляем систему
echo "📦 Обновляем систему..."
sudo apt update && sudo apt upgrade -y

# Устанавливаем необходимые пакеты
echo "📦 Устанавливаем необходимые пакеты..."
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3 curl wget

# Создаем пользователя для бота (если не существует)
if ! id "botuser" &>/dev/null; then
    echo "👤 Создаем пользователя botuser..."
    sudo useradd -m -s /bin/bash botuser
    sudo usermod -aG www-data botuser
fi

# Создаем директории
echo "📁 Создаем директории..."
sudo mkdir -p /opt/telegram-bot
sudo mkdir -p /var/log/telegram-bot
sudo mkdir -p /var/run/telegram-bot

# Клонируем репозиторий
echo "📥 Клонируем репозиторий..."
cd /opt
if [ -d "telegram-bot" ]; then
    cd telegram-bot
    sudo git pull origin master
else
    sudo git clone https://github.com/strdr1/telegram-bot-api.git telegram-bot
    cd telegram-bot
fi

# Устанавливаем права
sudo chown -R botuser:botuser /opt/telegram-bot
sudo chown -R botuser:botuser /var/log/telegram-bot
sudo chown -R botuser:botuser /var/run/telegram-bot

# Переключаемся на пользователя botuser
sudo -u botuser bash << 'EOF'
cd /opt/telegram-bot

# Создаем виртуальное окружение
echo "🐍 Создаем виртуальное окружение..."
python3 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
echo "📦 Устанавливаем Python зависимости..."
pip install --upgrade pip
pip install -r requirements.txt

# Создаем .env файл (если не существует)
if [ ! -f .env ]; then
    echo "⚙️ Создаем .env файл..."
    cp .env.example .env || echo "# Настройте переменные окружения" > .env
fi

echo "✅ Установка завершена для пользователя botuser"
EOF

echo "🎉 Развертывание завершено!"
echo "📝 Следующие шаги:"
echo "1. Настройте .env файл: sudo nano /opt/telegram-bot/.env"
echo "2. Настройте Nginx: sudo cp /opt/telegram-bot/nginx.conf /etc/nginx/sites-available/telegram-bot"
echo "3. Настройте Supervisor: sudo cp /opt/telegram-bot/supervisor.conf /etc/supervisor/conf.d/telegram-bot.conf"
echo "4. Запустите сервисы: sudo systemctl restart nginx && sudo supervisorctl reread && sudo supervisorctl update"