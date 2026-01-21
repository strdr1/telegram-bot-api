@echo off
chcp 65001 > nul
echo ============================================
echo        ОСТАНОВКА PYTHON ПРОЦЕССОВ
echo ============================================
echo.

echo = Поиск запущенных Python процессов...
tasklist /fi "imagename eq python.exe" 2>nul | find /i "python.exe" >nul
if %errorlevel%==0 (
    echo + Найдены процессы python.exe
) else (
    echo - Процессы python.exe не найдены
)

tasklist /fi "imagename eq pythonw.exe" 2>nul | find /i "pythonw.exe" >nul
if %errorlevel%==0 (
    echo + Найдены процессы pythonw.exe
) else (
    echo - Процессы pythonw.exe не найдены
)

echo.
echo = Останавливаем все Python процессы...

REM Останавливаем python.exe
taskkill /f /im python.exe >nul 2>&1
if %errorlevel%==0 (
    echo ✓ Процессы python.exe остановлены
) else (
    echo - Нет активных процессов python.exe
)

REM Останавливаем pythonw.exe (фоновые процессы)
taskkill /f /im pythonw.exe >nul 2>&1
if %errorlevel%==0 (
    echo ✓ Процессы pythonw.exe остановлены
) else (
    echo - Нет активных процессов pythonw.exe
)

echo.
echo ============================================
echo         ВСЕ PYTHON ПРОЦЕССЫ ОСТАНОВЛЕНЫ
echo ============================================
echo.
pause