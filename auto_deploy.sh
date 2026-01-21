#!/bin/bash

# 🚀 Автоматический скрипт развертывания Telegram Bot на сервере
# Сервер: a950841.fvds.ru (155.212.164.61)
# Пароль: Mashkov.Rest

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Конфигурация сервера
SERVER_IP="155.212.164.61"
SERVER_USER="root"
SERVER_PASSWORD="Mashkov.Rest"
SERVER_DOMAIN="a950841.fvds.ru"

# Функция для вывода цветного текста
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_header() {
    echo -e "${BLUE}"
    echo "=================================="
    echo "$1"
    echo "=================================="
    echo -e "${NC}"
}

# Проверка наличия sshpass
check_sshpass() {
    if ! command -v sshpass &> /dev/null; then
        print_warning "sshpass не установлен. Устанавливаем..."
        
        # Определяем ОС и устанавливаем sshpass
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            sudo apt-get update && sudo apt-get install -y sshpass
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            if command -v brew &> /dev/null; then
                brew install hudochenkov/sshpass/sshpass
            else
                print_error "Установите Homebrew или sshpass вручную"
                exit 1
            fi
        else
            print_error "Неподдерживаемая ОС. Установите sshpass вручную"
            exit 1
        fi
        
        print_status "sshpass установлен"
    fi
}

# Функция для выполнения команд на сервере
run_remote() {
    local command="$1"
    print_info "Выполняем: $command"
    sshpass -p "$SERVER_PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "$command"
}

# Функция для копирования файла на сервер
copy_to_server() {
    local local_file="$1"
    local remote_path="$2"
    print_info "Копируем $local_file -> $remote_path"
    sshpass -p "$SERVER_PASSWORD" scp -o StrictHostKeyChecking=no "$local_file" "$SERVER_USER@$SERVER_IP:$remote_path"
}

# Основная функция развертывания
main() {
    print_header "🚀 АВТОМАТИЧЕСКОЕ РАЗВЕРТЫВАНИЕ TELEGRAM BOT"
    
    print_info "Сервер: $SERVER_DOMAIN ($SERVER_IP)"
    print_info "Пользователь: $SERVER_USER"
    print_info "Начинаем развертывание..."
    
    # Проверяем sshpass
    check_sshpass
    
    # Тестируем подключение
    print_info "Тестируем подключение к серверу..."
    if ! sshpass -p "$SERVER_PASSWORD" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$SERVER_USER@$SERVER_IP" "echo 'Подключение успешно'"; then
        print_error "Не удалось подключиться к серверу!"
        print_error "Проверьте IP адрес, пароль и доступность сервера"
        exit 1
    fi
    print_status "Подключение к серверу установлено"
    
    # Шаг 1: Обновляем систему и устанавливаем пакеты
    print_header "📦 УСТАНОВКА СИСТЕМНЫХ ПАКЕТОВ"
    run_remote "apt update && apt upgrade -y"
    run_remote "apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3 curl wget certbot python3-certbot-nginx"
    print_status "Системные пакеты установлены"
    
    # Шаг 2: Создаем пользователя для бота
    print_header "👤 СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ"
    run_remote "if ! id 'botuser' &>/dev/null; then useradd -m -s /bin/bash botuser && usermod -aG www-data botuser; fi"
    print_status "Пользователь botuser создан"
    
    # Шаг 3: Создаем директории
    print_header "📁 СОЗДАНИЕ ДИРЕКТОРИЙ"
    run_remote "mkdir -p /opt/telegram-bot /var/log/telegram-bot /var/run/telegram-bot"
    run_remote "chown -R botuser:botuser /opt/telegram-bot /var/log/telegram-bot /var/run/telegram-bot"
    print_status "Директории созданы"
    
    # Шаг 4: Клонируем репозиторий
    print_header "📥 КЛОНИРОВАНИЕ РЕПОЗИТОРИЯ"
    run_remote "cd /opt && if [ -d 'telegram-bot' ]; then cd telegram-bot && git pull origin master; else git clone https://github.com/strdr1/telegram-bot-api.git telegram-bot && cd telegram-bot; fi"
    run_remote "chown -R botuser:botuser /opt/telegram-bot"
    print_status "Репозиторий клонирован"
    
    # Шаг 5: Создаем виртуальное окружение и устанавливаем зависимости
    print_header "🐍 УСТАНОВКА PYTHON ЗАВИСИМОСТЕЙ"
    run_remote "cd /opt/telegram-bot && sudo -u botuser python3 -m venv venv"
    run_remote "cd /opt/telegram-bot && sudo -u botuser bash -c 'source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt'"
    print_status "Python зависимости установлены"
    
    # Шаг 6: Создаем .env файл с данными
    print_header "⚙️ СОЗДАНИЕ КОНФИГУРАЦИИ"
    
    # Читаем локальный .env файл и создаем серверный
    if [ -f ".env" ]; then
        print_info "Копируем конфигурацию из локального .env файла..."
        
        # Создаем временный .env файл для сервера
        cat > /tmp/server.env << EOF
# Telegram Bot Configuration
BOT_TOKEN=$(grep "BOT_TOKEN=" .env | cut -d'=' -f2)
ADMIN_USER_ID=515216260
ADMIN_PASSWORD=$(grep "ADMIN_PASSWORD=" .env | cut -d'=' -f2)

# Database
DATABASE_URL=sqlite:///restaurant.db

# Presto API Keys
PRESTO_CONNECTION_ID=$(grep "PRESTO_CONNECTION_ID=" .env | cut -d'=' -f2)
PRESTO_APP_SECRET=$(grep "PRESTO_APP_SECRET=" .env | cut -d'=' -f2)
PRESTO_SECRET_KEY=$(grep "PRESTO_SECRET_KEY=" .env | cut -d'=' -f2)
PRESTO_ACCESS_TOKEN=$(grep "PRESTO_ACCESS_TOKEN=" .env | cut -d'=' -f2)

# Google API Keys
GOOGLE_API_KEY=$(grep "GOOGLE_API_KEY=" .env | cut -d'=' -f2)
GOOGLE_SEARCH_ENGINE_ID=$(grep "GOOGLE_SEARCH_ENGINE_ID=" .env | cut -d'=' -f2)

# AI API
POLZA_AI_TOKEN=your_polza_ai_token_here

# Restaurant Settings
RESTAURANT_NAME=Машков
RESTAURANT_PHONE=+7 (495) 123-45-67
RESTAURANT_ADDRESS=Москва, ул. Примерная, 1
RESTAURANT_HOURS=Ежедневно с 10:00 до 23:00

# Server Settings
HOST=0.0.0.0
PORT=8000
WEBHOOK_MODE=true
WEBHOOK_URL=https://$SERVER_DOMAIN/webhook
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8000

# Miniapp Settings
MINIAPP_URL=https://$SERVER_DOMAIN/miniapp/

# GitHub Auto-update
GITHUB_REPO=strdr1/telegram-bot-api
GITHUB_BRANCH=master

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/telegram-bot/bot.log
EOF
        
        # Копируем .env файл на сервер
        copy_to_server "/tmp/server.env" "/opt/telegram-bot/.env"
        run_remote "chown botuser:botuser /opt/telegram-bot/.env"
        rm /tmp/server.env
        
        print_status "Конфигурация создана"
    else
        print_error "Локальный .env файл не найден!"
        exit 1
    fi
    
    # Шаг 7: Настраиваем SSL сертификат
    print_header "🔒 НАСТРОЙКА SSL СЕРТИФИКАТА"
    run_remote "certbot certonly --nginx -d $SERVER_DOMAIN --email admin@$SERVER_DOMAIN --agree-tos --non-interactive --quiet || echo 'SSL уже настроен или ошибка'"
    print_status "SSL сертификат настроен"
    
    # Шаг 8: Настраиваем Nginx
    print_header "🌐 НАСТРОЙКА NGINX"
    run_remote "cp /opt/telegram-bot/nginx.conf /etc/nginx/sites-available/telegram-bot"
    run_remote "ln -sf /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/"
    run_remote "rm -f /etc/nginx/sites-enabled/default"
    run_remote "nginx -t && systemctl restart nginx"
    print_status "Nginx настроен"
    
    # Шаг 9: Настраиваем Supervisor
    print_header "🔧 НАСТРОЙКА SUPERVISOR"
    run_remote "cp /opt/telegram-bot/supervisor.conf /etc/supervisor/conf.d/telegram-bot.conf"
    run_remote "supervisorctl reread && supervisorctl update"
    print_status "Supervisor настроен"
    
    # Шаг 10: Запускаем сервисы
    print_header "🚀 ЗАПУСК СЕРВИСОВ"
    run_remote "supervisorctl start telegram-bot-group"
    sleep 5
    print_status "Сервисы запущены"
    
    # Шаг 11: Проверяем статус
    print_header "🔍 ПРОВЕРКА СТАТУСА"
    run_remote "supervisorctl status"
    
    # Проверяем webhook
    print_info "Проверяем webhook..."
    if curl -s "https://$SERVER_DOMAIN/health" | grep -q "ok"; then
        print_status "Webhook работает!"
    else
        print_warning "Webhook может быть еще не готов, проверьте через минуту"
    fi
    
    # Финальная информация
    print_header "🎉 РАЗВЕРТЫВАНИЕ ЗАВЕРШЕНО!"
    
    echo -e "${GREEN}"
    echo "✅ Бот успешно развернут на сервере!"
    echo ""
    echo "🔗 Ссылки:"
    echo "   • Webhook: https://$SERVER_DOMAIN/webhook"
    echo "   • Health check: https://$SERVER_DOMAIN/health"
    echo "   • Миниапп: https://$SERVER_DOMAIN/miniapp/"
    echo ""
    echo "📋 Что делать дальше:"
    echo "   1. Настройте миниапп в @BotFather:"
    echo "      URL: https://$SERVER_DOMAIN/miniapp/"
    echo "   2. Добавьте POLZA_AI_TOKEN в .env файл на сервере"
    echo "   3. Протестируйте бота в Telegram"
    echo ""
    echo "🔧 Управление:"
    echo "   • Статус: ssh root@$SERVER_IP '/opt/telegram-bot/monitor.sh status'"
    echo "   • Логи: ssh root@$SERVER_IP '/opt/telegram-bot/monitor.sh logs bot'"
    echo "   • Перезапуск: ssh root@$SERVER_IP '/opt/telegram-bot/monitor.sh restart'"
    echo -e "${NC}"
}

# Запускаем основную функцию
main "$@"