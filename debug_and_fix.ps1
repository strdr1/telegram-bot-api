# Debug and fix AI and admin panel
$password = "Mashkov.Rest"

Write-Host "Debugging AI and admin panel..." -ForegroundColor Green

# 1. Check AI token file
Write-Host "1. Checking AI token..." -ForegroundColor Yellow
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "cat /opt/telegram-bot/ai_ref/token.txt"

# 2. Check bot logs for AI requests
Write-Host "2. Checking bot logs..." -ForegroundColor Yellow
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "supervisorctl tail telegram-bot-group:telegram-bot"

# 3. Test API messages endpoint
Write-Host "3. Testing messages API..." -ForegroundColor Yellow
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "curl -s https://a950841.fvds.ru/api/chats/1"

# 4. Check database for messages
Write-Host "4. Checking database messages..." -ForegroundColor Yellow
echo $password | ssh -o StrictHostKeyChecking=no root@a950841.fvds.ru "cd /opt/telegram-bot && sqlite3 restaurant.db 'SELECT id, sender, message_text, message_time FROM chat_messages WHERE chat_id = 1 ORDER BY message_time DESC LIMIT 10;'"

Write-Host "Debug complete!" -ForegroundColor Green