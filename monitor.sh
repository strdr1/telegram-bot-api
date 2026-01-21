#!/bin/bash

# Скрипт мониторинга Telegram Bot

function show_status() {
    echo "🤖 Статус Telegram Bot"
    echo "======================"
    
    # Проверяем статус через supervisor
    echo "📊 Supervisor статус:"
    sudo supervisorctl status telegram-bot-group
    echo ""
    
    # Проверяем процессы
    echo "🔍 Процессы:"
    ps aux | grep -E "(bot\.py|schedule_updates\.py)" | grep -v grep
    echo ""
    
    # Проверяем порты
    echo "🌐 Порты:"
    sudo netstat -tlnp | grep :8000
    echo ""
    
    # Проверяем Nginx
    echo "🌍 Nginx статус:"
    sudo systemctl status nginx --no-pager -l
    echo ""
    
    # Проверяем SSL сертификат
    echo "🔒 SSL сертификат:"
    if [ -f "/etc/letsencrypt/live/a950841.fvds.ru/fullchain.pem" ]; then
        openssl x509 -in /etc/letsencrypt/live/a950841.fvds.ru/fullchain.pem -text -noout | grep -E "(Subject:|Not After)"
    else
        echo "SSL сертификат не найден"
    fi
    echo ""
    
    # Проверяем место на диске
    echo "💾 Место на диске:"
    df -h /
    echo ""
    
    # Проверяем память
    echo "🧠 Использование памяти:"
    free -h
    echo ""
}

function show_logs() {
    echo "📋 Логи Telegram Bot"
    echo "==================="
    
    case "$1" in
        "bot")
            echo "🤖 Логи бота (последние 50 строк):"
            sudo tail -n 50 /var/log/telegram-bot/bot.log
            ;;
        "scheduler")
            echo "⏰ Логи планировщика (последние 50 строк):"
            sudo tail -n 50 /var/log/telegram-bot/scheduler.log
            ;;
        "nginx")
            echo "🌍 Логи Nginx (последние 50 строк):"
            sudo tail -n 50 /var/log/nginx/telegram-bot.access.log
            ;;
        "error")
            echo "❌ Логи ошибок:"
            echo "--- Bot errors ---"
            sudo tail -n 25 /var/log/telegram-bot/bot_error.log 2>/dev/null || echo "Нет ошибок бота"
            echo "--- Nginx errors ---"
            sudo tail -n 25 /var/log/nginx/telegram-bot.error.log 2>/dev/null || echo "Нет ошибок Nginx"
            ;;
        *)
            echo "Доступные логи:"
            echo "  ./monitor.sh logs bot       - логи бота"
            echo "  ./monitor.sh logs scheduler - логи планировщика"
            echo "  ./monitor.sh logs nginx     - логи Nginx"
            echo "  ./monitor.sh logs error     - логи ошибок"
            ;;
    esac
}

function restart_services() {
    echo "🔄 Перезапускаем сервисы..."
    
    # Перезапускаем bot через supervisor
    echo "🤖 Перезапускаем бота..."
    sudo supervisorctl restart telegram-bot-group
    
    # Перезапускаем Nginx
    echo "🌍 Перезапускаем Nginx..."
    sudo systemctl restart nginx
    
    echo "✅ Сервисы перезапущены!"
    sleep 2
    show_status
}

function update_bot() {
    echo "📥 Обновляем бота из GitHub..."
    
    cd /opt/telegram-bot
    sudo -u botuser git pull origin master
    
    echo "📦 Обновляем зависимости..."
    sudo -u botuser bash -c "source venv/bin/activate && pip install -r requirements.txt"
    
    echo "🔄 Перезапускаем сервисы..."
    sudo supervisorctl restart telegram-bot-group
    
    echo "✅ Обновление завершено!"
}

function backup_data() {
    echo "💾 Создаем резервную копию..."
    
    BACKUP_DIR="/opt/backups/telegram-bot"
    DATE=$(date +%Y%m%d_%H%M%S)
    
    sudo mkdir -p $BACKUP_DIR
    
    # Бэкап базы данных
    sudo -u botuser cp /opt/telegram-bot/restaurant.db $BACKUP_DIR/restaurant_$DATE.db
    
    # Бэкап конфигурации
    sudo cp /opt/telegram-bot/.env $BACKUP_DIR/env_$DATE.backup
    
    # Бэкап логов
    sudo tar -czf $BACKUP_DIR/logs_$DATE.tar.gz /var/log/telegram-bot/
    
    echo "✅ Резервная копия создана в $BACKUP_DIR"
    ls -la $BACKUP_DIR/
}

function test_webhook() {
    echo "🔗 Тестируем webhook..."
    
    # Тест доступности
    curl -s -o /dev/null -w "HTTP Status: %{http_code}\nTime: %{time_total}s\n" https://a950841.fvds.ru/health
    
    # Тест SSL
    echo ""
    echo "🔒 Проверяем SSL:"
    curl -s -I https://a950841.fvds.ru/webhook | head -1
}

# Главное меню
case "$1" in
    "status")
        show_status
        ;;
    "logs")
        show_logs "$2"
        ;;
    "restart")
        restart_services
        ;;
    "update")
        update_bot
        ;;
    "backup")
        backup_data
        ;;
    "test")
        test_webhook
        ;;
    *)
        echo "🤖 Telegram Bot Monitor"
        echo "======================"
        echo ""
        echo "Использование: ./monitor.sh [команда]"
        echo ""
        echo "Команды:"
        echo "  status   - показать статус всех сервисов"
        echo "  logs     - показать логи (bot|scheduler|nginx|error)"
        echo "  restart  - перезапустить все сервисы"
        echo "  update   - обновить бота из GitHub"
        echo "  backup   - создать резервную копию"
        echo "  test     - протестировать webhook"
        echo ""
        echo "Примеры:"
        echo "  ./monitor.sh status"
        echo "  ./monitor.sh logs bot"
        echo "  ./monitor.sh restart"
        ;;
esac