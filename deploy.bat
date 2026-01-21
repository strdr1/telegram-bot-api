@echo off
echo.
echo ==========================================
echo [DEPLOYMENT] Automatic Telegram Bot Deployment
echo ==========================================
echo Server: a950841.fvds.ru (155.212.164.61)
echo Password: Mashkov.Rest
echo.
echo [INFO] Starting PowerShell deployment script...

powershell -ExecutionPolicy Bypass -File auto_deploy.ps1

echo.
echo [COMPLETED] Deployment finished!
pause