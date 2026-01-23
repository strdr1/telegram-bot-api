# Simple fix script
$password = "Mashkov.Rest"

Write-Host "Fixing all issues..." -ForegroundColor Green

# 1. Create AI token
Write-Host "Creating AI token..." -ForegroundColor Yellow
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "mkdir -p /opt/telegram-bot/ai_ref"
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "echo 'ak_MUlqpkRNU2jE5Xo3tf2yOfZImxVP90gcvvcN2Neif2g' > /opt/telegram-bot/ai_ref/token.txt"

# 2. Upload files
Write-Host "Uploading files..." -ForegroundColor Yellow
echo $password | scp -o StrictHostKeyChecking=no miniapp_server.py root@a950841.fvds.ru:/opt/telegram-bot/
echo $password | scp -o StrictHostKeyChecking=no "miniapp/admin.html" root@a950841.fvds.ru:/opt/telegram-bot/miniapp/
echo $password | scp -o StrictHostKeyChecking=no keyboards.py root@a950841.fvds.ru:/opt/telegram-bot/
echo $password | scp -o StrictHostKeyChecking=no ai_assistant.py root@a950841.fvds.ru:/opt/telegram-bot/

# 3. Restart services
Write-Host "Restarting services..." -ForegroundColor Yellow
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "cd /opt/telegram-bot && supervisorctl restart telegram-bot-group:telegram-bot"
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "cd /opt/telegram-bot && supervisorctl restart telegram-bot-group:miniapp-api"

# 4. Test AI
Write-Host "Testing AI..." -ForegroundColor Yellow
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "cd /opt/telegram-bot && python3 test_polza_api.py"

Write-Host "Done! Check:" -ForegroundColor Green
Write-Host "1. Admin panel: https://a950841.fvds.ru/miniapp/admin.html"
Write-Host "2. Send message to bot to test AI"