@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title Restaurant Bot - Stop
color 0C

echo 🛑 Остановка Restaurant Telegram Bot
echo ===================================
echo.

REM Остановка всех процессов Python
echo 🔄 Останавливаем процессы Python...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1

if %errorlevel% == 0 (
    echo ✅ Бот успешно остановлен
) else (
    echo ⚠️ Процессы Python не найдены или уже остановлены
)

echo.
echo 👋 Готово!
pause