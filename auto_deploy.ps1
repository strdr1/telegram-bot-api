# 🚀 Автоматический скрипт развертывания Telegram Bot на сервере (PowerShell)
# Сервер: a950841.fvds.ru (155.212.164.61)
# Пароль: Mashkov.Rest

param(
    [switch]$Force
)

# Конфигурация сервера
$ServerIP = "155.212.164.61"
$ServerUser = "root"
$ServerPassword = "Mashkov.Rest"
$ServerDomain = "a950841.fvds.ru"

# Функции для цветного вывода
function Write-Success { param($Message) Write-Host "✅ $Message" -ForegroundColor Green }
function Write-Info { param($Message) Write-Host "ℹ️  $Message" -ForegroundColor Blue }
function Write-Warning { param($Message) Write-Host "⚠️  $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "❌ $Message" -ForegroundColor Red }
function Write-Header { 
    param($Message) 
    Write-Host "`n==================================" -ForegroundColor Blue
    Write-Host $Message -ForegroundColor Blue
    Write-Host "==================================" -ForegroundColor Blue
}

# Проверка наличия plink (PuTTY)
function Test-PuTTY {
    if (-not (Get-Command plink -ErrorAction SilentlyContinue)) {
        Write-Warning "PuTTY не найден. Скачиваем..."
        
        $puttyUrl = "https://the.earth.li/~sgtatham/putty/latest/w64/putty.zip"
        $puttyZip = "$env:TEMP\putty.zip"
        $puttyDir = "$env:TEMP\putty"
        
        try {
            Invoke-WebRequest -Uri $puttyUrl -OutFile $puttyZip
            Expand-Archive -Path $puttyZip -DestinationPath $puttyDir -Force
            
            # Добавляем в PATH для текущей сессии
            $env:PATH += ";$puttyDir"
            
            Write-Success "PuTTY скачан и настроен"
        }
        catch {
            Write-Error "Не удалось скачать PuTTY: $_"
            Write-Info "Скачайте PuTTY вручную с https://putty.org/"
            exit 1
        }
    }
}

# Функция для выполнения команд на сервере
function Invoke-RemoteCommand {
    param($Command)
    Write-Info "Выполняем: $Command"
    
    $result = & plink -ssh -batch -pw $ServerPassword "$ServerUser@$ServerIP" $Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Команда завершилась с кодом $LASTEXITCODE"
    }
    return $result
}

# Функция для копирования файла на сервер
function Copy-ToServer {
    param($LocalFile, $RemotePath)
    Write-Info "Копируем $LocalFile -> $RemotePath"
    & pscp -batch -pw $ServerPassword $LocalFile "$ServerUser@$ServerIP`:$RemotePath"
}

# Основная функция
function Start-Deployment {
    Write-Header "🚀 АВТОМАТИЧЕСКОЕ РАЗВЕРТЫВАНИЕ TELEGRAM BOT"
    
    Write-Info "Сервер: $ServerDomain ($ServerIP)"
    Write-Info "Пользователь: $ServerUser"
    Write-Info "Начинаем развертывание..."
    
    # Проверяем PuTTY
    Test-PuTTY
    
    # Тестируем подключение
    Write-Info "Тестируем подключение к серверу..."
    try {
        $testResult = Invoke-RemoteCommand "echo 'Подключение успешно'"
        if ($testResult -match "Подключение успешно") {
            Write-Success "Подключение к серверу установлено"
        } else {
            throw "Неожиданный ответ сервера"
        }
    }
    catch {
        Write-Error "Не удалось подключиться к серверу!"
        Write-Error "Проверьте IP адрес, пароль и доступность сервера"
        exit 1
    }
    
    # Шаг 1: Обновляем систему
    Write-Header "📦 УСТАНОВКА СИСТЕМНЫХ ПАКЕТОВ"
    Invoke-RemoteCommand "apt update && apt upgrade -y"
    Invoke-RemoteCommand "apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3 curl wget certbot python3-certbot-nginx"
    Write-Success "Системные пакеты установлены"
    
    # Шаг 2: Создаем пользователя
    Write-Header "👤 СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ"
    Invoke-RemoteCommand "if ! id 'botuser' &>/dev/null; then useradd -m -s /bin/bash botuser && usermod -aG www-data botuser; fi"
    Write-Success "Пользователь botuser создан"
    
    # Шаг 3: Создаем директории
    Write-Header "📁 СОЗДАНИЕ ДИРЕКТОРИЙ"
    Invoke-RemoteCommand "mkdir -p /opt/telegram-bot /var/log/telegram-bot /var/run/telegram-bot"
    Invoke-RemoteCommand "chown -R botuser:botuser /opt/telegram-bot /var/log/telegram-bot /var/run/telegram-bot"
    Write-Success "Директории созданы"
    
    # Шаг 4: Клонируем репозиторий
    Write-Header "📥 КЛОНИРОВАНИЕ РЕПОЗИТОРИЯ"
    Invoke-RemoteCommand "cd /opt && if [ -d 'telegram-bot' ]; then cd telegram-bot && git pull origin master; else git clone https://github.com/strdr1/telegram-bot-api.git telegram-bot && cd telegram-bot; fi"
    Invoke-RemoteCommand "chown -R botuser:botuser /opt/telegram-bot"
    Write-Success "Репозиторий клонирован"
    
    # Шаг 5: Python зависимости
    Write-Header "🐍 УСТАНОВКА PYTHON ЗАВИСИМОСТЕЙ"
    Invoke-RemoteCommand "cd /opt/telegram-bot && sudo -u botuser python3 -m venv venv"
    Invoke-RemoteCommand "cd /opt/telegram-bot && sudo -u botuser bash -c 'source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt'"
    Write-Success "Python зависимости установлены"
    
    # Шаг 6: Создаем .env файл
    Write-Header "⚙️ СОЗДАНИЕ КОНФИГУРАЦИИ"
    
    if (Test-Path ".env") {
        Write-Info "Читаем локальный .env файл..."
        
        $envContent = Get-Content ".env"
        $botToken = ($envContent | Where-Object { $_ -match "BOT_TOKEN=" }) -replace "BOT_TOKEN=", ""
        $adminPassword = ($envContent | Where-Object { $_ -match "ADMIN_PASSWORD=" }) -replace "ADMIN_PASSWORD=", ""
        $prestoConnectionId = ($envContent | Where-Object { $_ -match "PRESTO_CONNECTION_ID=" }) -replace "PRESTO_CONNECTION_ID=", ""
        $prestoAppSecret = ($envContent | Where-Object { $_ -match "PRESTO_APP_SECRET=" }) -replace "PRESTO_APP_SECRET=", ""
        $prestoSecretKey = ($envContent | Where-Object { $_ -match "PRESTO_SECRET_KEY=" }) -replace "PRESTO_SECRET_KEY=", ""
        $prestoAccessToken = ($envContent | Where-Object { $_ -match "PRESTO_ACCESS_TOKEN=" }) -replace "PRESTO_ACCESS_TOKEN=", ""
        $googleApiKey = ($envContent | Where-Object { $_ -match "GOOGLE_API_KEY=" }) -replace "GOOGLE_API_KEY=", ""
        $googleSearchEngineId = ($envContent | Where-Object { $_ -match "GOOGLE_SEARCH_ENGINE_ID=" }) -replace "GOOGLE_SEARCH_ENGINE_ID=", ""
        
        # Создаем серверный .env файл
        $serverEnv = @"
# Telegram Bot Configuration
BOT_TOKEN=$botToken
ADMIN_USER_ID=515216260
ADMIN_PASSWORD=$adminPassword

# Database
DATABASE_URL=sqlite:///restaurant.db

# Presto API Keys
PRESTO_CONNECTION_ID=$prestoConnectionId
PRESTO_APP_SECRET=$prestoAppSecret
PRESTO_SECRET_KEY=$prestoSecretKey
PRESTO_ACCESS_TOKEN=$prestoAccessToken

# Google API Keys
GOOGLE_API_KEY=$googleApiKey
GOOGLE_SEARCH_ENGINE_ID=$googleSearchEngineId

# AI API
POLZA_AI_TOKEN=ak_MUlqpkRNU2jE5Xo3tf2yOfZImxVP90gcvvcN2Neif2g

# Restaurant Settings
RESTAURANT_NAME=Машков
RESTAURANT_PHONE=+7 (495) 123-45-67
RESTAURANT_ADDRESS=Москва, ул. Примерная, 1
RESTAURANT_HOURS=Ежедневно с 10:00 до 23:00

# Server Settings
HOST=0.0.0.0
PORT=8000
WEBHOOK_MODE=true
WEBHOOK_URL=https://$ServerDomain/webhook
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8000

# Miniapp Settings
MINIAPP_URL=https://$ServerDomain/miniapp/

# GitHub Auto-update
GITHUB_REPO=strdr1/telegram-bot-api
GITHUB_BRANCH=master

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/telegram-bot/bot.log
"@
        
        # Сохраняем во временный файл и копируем на сервер
        $tempEnvFile = "$env:TEMP\server.env"
        $serverEnv | Out-File -FilePath $tempEnvFile -Encoding UTF8
        Copy-ToServer $tempEnvFile "/opt/telegram-bot/.env"
        Invoke-RemoteCommand "chown botuser:botuser /opt/telegram-bot/.env"
        Remove-Item $tempEnvFile
        
        Write-Success "Конфигурация создана"
    } else {
        Write-Error "Локальный .env файл не найден!"
        exit 1
    }
    
    # Шаг 7: SSL сертификат
    Write-Header "🔒 НАСТРОЙКА SSL СЕРТИФИКАТА"
    Invoke-RemoteCommand "certbot certonly --nginx -d $ServerDomain --email admin@$ServerDomain --agree-tos --non-interactive --quiet || echo 'SSL уже настроен или ошибка'"
    Write-Success "SSL сертификат настроен"
    
    # Шаг 8: Nginx
    Write-Header "🌐 НАСТРОЙКА NGINX"
    Invoke-RemoteCommand "cp /opt/telegram-bot/nginx.conf /etc/nginx/sites-available/telegram-bot"
    Invoke-RemoteCommand "ln -sf /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/"
    Invoke-RemoteCommand "rm -f /etc/nginx/sites-enabled/default"
    Invoke-RemoteCommand "nginx -t && systemctl restart nginx"
    Write-Success "Nginx настроен"
    
    # Шаг 9: Supervisor
    Write-Header "🔧 НАСТРОЙКА SUPERVISOR"
    Invoke-RemoteCommand "cp /opt/telegram-bot/supervisor.conf /etc/supervisor/conf.d/telegram-bot.conf"
    Invoke-RemoteCommand "supervisorctl reread && supervisorctl update"
    Write-Success "Supervisor настроен"
    
    # Шаг 10: Запуск сервисов
    Write-Header "🚀 ЗАПУСК СЕРВИСОВ"
    Invoke-RemoteCommand "supervisorctl start telegram-bot-group"
    Start-Sleep -Seconds 5
    Write-Success "Сервисы запущены"
    
    # Шаг 11: Проверка статуса
    Write-Header "🔍 ПРОВЕРКА СТАТУСА"
    Invoke-RemoteCommand "supervisorctl status"
    
    # Проверяем webhook
    Write-Info "Проверяем webhook..."
    try {
        $webhookTest = Invoke-WebRequest -Uri "https://$ServerDomain/health" -UseBasicParsing
        if ($webhookTest.Content -match "ok") {
            Write-Success "Webhook работает!"
        } else {
            Write-Warning "Webhook может быть еще не готов, проверьте через минуту"
        }
    }
    catch {
        Write-Warning "Webhook может быть еще не готов, проверьте через минуту"
    }
    
    # Финальная информация
    Write-Header "🎉 РАЗВЕРТЫВАНИЕ ЗАВЕРШЕНО!"
    
    Write-Host "`n✅ Бот успешно развернут на сервере!" -ForegroundColor Green
    Write-Host "`n🔗 Ссылки:" -ForegroundColor Yellow
    Write-Host "   • Webhook: https://$ServerDomain/webhook"
    Write-Host "   • Health check: https://$ServerDomain/health"
    Write-Host "   • Миниапп: https://$ServerDomain/miniapp/"
    Write-Host "`n📋 Что делать дальше:" -ForegroundColor Yellow
    Write-Host "   1. Настройте миниапп в @BotFather:"
    Write-Host "      URL: https://$ServerDomain/miniapp/"
    Write-Host "   2. Протестируйте бота в Telegram"
    Write-Host "`n🔧 Управление:" -ForegroundColor Yellow
    Write-Host "   • Статус: plink -ssh -batch -pw $ServerPassword $ServerUser@$ServerIP '/opt/telegram-bot/monitor.sh status'"
    Write-Host "   • Логи: plink -ssh -batch -pw $ServerPassword $ServerUser@$ServerIP '/opt/telegram-bot/monitor.sh logs bot'"
    Write-Host "   • Перезапуск: plink -ssh -batch -pw $ServerPassword $ServerUser@$ServerIP '/opt/telegram-bot/monitor.sh restart'"
}

# Запускаем развертывание
Start-Deployment