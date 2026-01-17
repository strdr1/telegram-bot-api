@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title Restaurant Bot
color 0A

echo 🤖 Запуск Restaurant Telegram Bot
echo ================================
echo.

echo 🤖 Запуск Telegram бота с API...
python -X utf8 bot_with_api.py

echo.
echo Все сервисы завершили работу
pause
