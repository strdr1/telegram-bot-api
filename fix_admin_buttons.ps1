# Скрипт для исправления кнопок админ-панели
Write-Host "🔧 Исправляем кнопки админ-панели..." -ForegroundColor Green

# Подключаемся к серверу и обновляем код
$serverCommand = @"
cd /root/telegram-bot
git pull origin master
supervisorctl restart telegram-bot
supervisorctl restart miniapp-server
echo "✅ Кнопки админ-панели исправлены!"
"@

Write-Host "📡 Подключаемся к серверу..." -ForegroundColor Yellow
ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru $serverCommand

Write-Host "🎉 Готово! Кнопки админ-панели теперь должны правильно редактировать сообщения." -ForegroundColor Green