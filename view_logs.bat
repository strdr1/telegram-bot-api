@echo off
chcp 65001 >nul
echo ========================================
echo    Просмотр логов сервера в реальном времени
echo ========================================
echo.
echo Подключение к логам бота (bot.log)...
echo Для выхода нажмите Ctrl+C
echo.
ssh -o StrictHostKeyChecking=no root@155.212.164.61 "tail -f /var/log/telegram-bot/bot.log"
pause