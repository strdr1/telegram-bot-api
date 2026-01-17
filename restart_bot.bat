@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title Restaurant Bot - Restart
color 0C

echo 🔄 Перезапуск Restaurant Telegram Bot
echo ====================================
echo.

REM Остановка всех процессов Python (осторожно!)
echo 🛑 Останавливаем все процессы Python...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1

echo ✅ Процессы остановлены
echo.

REM Пауза перед перезапуском
echo ⏳ Ожидание 3 секунды...
timeout /t 3 /nobreak >nul

echo 🚀 Запускаем бота заново...
echo.

REM Запуск бота с UTF-8
python -X utf8 bot.py

echo.
echo Бот завершил работу
pause