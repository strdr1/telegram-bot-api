@echo off
chcp 65001 >nul
echo.
echo 🚀 Автоматическое развертывание Telegram Bot
echo ==========================================
echo.
echo Сервер: a950841.fvds.ru (155.212.164.61)
echo Пароль: Mashkov.Rest
echo.

REM Проверяем наличие PowerShell
powershell -Command "Get-Host" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ PowerShell не найден!
    pause
    exit /b 1
)

echo ✅ Запускаем PowerShell скрипт развертывания...
echo.

REM Запускаем PowerShell скрипт
powershell -ExecutionPolicy Bypass -File "auto_deploy.ps1"

echo.
echo 🎉 Развертывание завершено!
echo.
pause