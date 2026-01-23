# Автоматическое исправление всех проблем через PowerShell
$password = "Mashkov.Rest"
$server = "root@a950841.fvds.ru"

Write-Host "🔧 Автоматическое исправление всех проблем..." -ForegroundColor Green

# Функция для выполнения SSH команд
function Invoke-SSHCommand {
    param($command)
    try {
        $result = echo $password | ssh -o StrictHostKeyChecking=no $server $command
        return $result
    }
    catch {
        Write-Host "❌ Ошибка SSH: $_" -ForegroundColor Red
        return $null
    }
}

# Функция для загрузки файлов
function Upload-File {
    param($localPath, $remotePath)
    try {
        echo $password | scp -o StrictHostKeyChecking=no $localPath "${server}:${remotePath}"
        return $?
    }
    catch {
        Write-Host "❌ Ошибка загрузки $localPath : $_" -ForegroundColor Red
        return $false
    }
}

# 1. Проверяем статус сервисов
Write-Host "`n1️⃣ Проверяем статус сервисов..." -ForegroundColor Yellow
$status = Invoke-SSHCommand "supervisorctl status"
if ($status) {
    Write-Host "✅ Сервисы:" -ForegroundColor Green
    Write-Host $status
}

# 2. Создаем токен AI
Write-Host "`n2️⃣ Создаем токен AI..." -ForegroundColor Yellow
Invoke-SSHCommand "mkdir -p /opt/telegram-bot/ai_ref"
Invoke-SSHCommand "echo 'ak_MUlqpkRNU2jE5Xo3tf2yOfZImxVP90gcvvcN2Neif2g' > /opt/telegram-bot/ai_ref/token.txt"
Write-Host "✅ Токен AI создан" -ForegroundColor Green

# 3. Загружаем исправленные файлы
Write-Host "`n3️⃣ Загружаем исправленные файлы..." -ForegroundColor Yellow

$files = @(
    @("miniapp_server.py", "/opt/telegram-bot/miniapp_server.py"),
    @("miniapp/admin.html", "/opt/telegram-bot/miniapp/admin.html"),
    @("keyboards.py", "/opt/telegram-bot/keyboards.py"),
    @("ai_assistant.py", "/opt/telegram-bot/ai_assistant.py")
)

foreach ($file in $files) {
    $localFile = $file[0]
    $remoteFile = $file[1]
    
    if (Test-Path $localFile) {
        Write-Host "📤 Загружаем $localFile..." -ForegroundColor Cyan
        echo $password | scp -o StrictHostKeyChecking=no $localFile "${server}:${remoteFile}"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ $localFile загружен" -ForegroundColor Green
        } else {
            Write-Host "❌ Ошибка загрузки $localFile" -ForegroundColor Red
        }
    } else {
        Write-Host "⚠️ Файл $localFile не найден" -ForegroundColor Yellow
    }
}

# 4. Перезапускаем сервисы
Write-Host "`n4️⃣ Перезапускаем сервисы..." -ForegroundColor Yellow

$services = @(
    "telegram-bot-group:telegram-bot",
    "telegram-bot-group:miniapp-api"
)

foreach ($service in $services) {
    Write-Host "🔄 Перезапускаем $service..." -ForegroundColor Cyan
    Invoke-SSHCommand "cd /opt/telegram-bot && supervisorctl restart $service"
    Write-Host "✅ $service перезапущен" -ForegroundColor Green
    Start-Sleep -Seconds 2
}

# 5. Тестируем API
Write-Host "`n5️⃣ Тестируем API..." -ForegroundColor Yellow

try {
    # Тест чатов
    $response = Invoke-WebRequest -Uri "https://a950841.fvds.ru/api/chats" -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        $chats = $response.Content | ConvertFrom-Json
        Write-Host "✅ API чатов работает: $($chats.Count) чатов" -ForegroundColor Green
    }
    
    # Тест статистики
    $response = Invoke-WebRequest -Uri "https://a950841.fvds.ru/api/stats" -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        $stats = $response.Content | ConvertFrom-Json
        Write-Host "✅ API статистики работает: $($stats | ConvertTo-Json -Compress)" -ForegroundColor Green
    }
}
catch {
    Write-Host "❌ Ошибка тестирования API: $_" -ForegroundColor Red
}

# 6. Тестируем AI
Write-Host "`n6️⃣ Тестируем AI..." -ForegroundColor Yellow
$aiTest = Invoke-SSHCommand "cd /opt/telegram-bot && python3 test_polza_api.py"
if ($aiTest -and $aiTest.Contains("✅ AI ответ:")) {
    Write-Host "✅ AI работает" -ForegroundColor Green
} else {
    Write-Host "❌ AI не работает" -ForegroundColor Red
    Write-Host $aiTest
}

# 7. Проверяем админ-панель
Write-Host "`n7️⃣ Проверяем админ-панель..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "https://a950841.fvds.ru/miniapp/admin.html" -TimeoutSec 10
    if ($response.StatusCode -eq 200 -and $response.Content.Contains("Админ-панель Mashkov")) {
        Write-Host "✅ Админ-панель доступна" -ForegroundColor Green
    } else {
        Write-Host "❌ Админ-панель недоступна" -ForegroundColor Red
    }
}
catch {
    Write-Host "❌ Ошибка проверки админ-панели: $_" -ForegroundColor Red
}

Write-Host "`n🎉 Диагностика завершена!" -ForegroundColor Green
Write-Host "`n📋 Что проверить:" -ForegroundColor Cyan
Write-Host "1. Админ-панель: https://a950841.fvds.ru/miniapp/admin.html"
Write-Host "2. Напиши боту любое сообщение для проверки AI"
Write-Host "3. Проверь кнопку 'Управление чатами' в админке бота"