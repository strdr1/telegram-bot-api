
@echo off
chcp 65001 > nul
echo ============================================
echo          ЗАПУСК БОТА MASHKOV
echo ============================================
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo X Python not found! Install Python 3.8+
    pause
    exit /b 1
)

REM Проверяем виртуальное окружение
if exist venv\Scripts\activate.bat (
    echo + Virtual environment found
    call venv\Scripts\activate.bat

    REM ОБЯЗАТЕЛЬНАЯ установка requests
    echo = Installing requests...
    pip install requests --quiet --force-reinstall

    echo = Installing all dependencies...
    pip install -r requirements.txt --quiet --force-reinstall

    REM Проверяем, установлен ли requests
    python -c "import requests; print('✓ requests installed')" 2>nul
    if errorlevel 1 (
        echo X Failed to install requests, trying again...
        pip install requests --force-reinstall
    )

    REM Проверяем, установлен ли Pillow
    python -c "from PIL import Image; print('✓ Pillow installed')" 2>nul
    if errorlevel 1 (
        echo X Failed to install Pillow, trying again...
        pip install Pillow --force-reinstall
    )

    REM Запускаем бота в активированном виртуальном окружении
    echo.
    echo = Starting bot...
    echo.
    REM Токен GigaChat будет получен автоматически при первом использовании AI
    python bot.py
) else (
    echo ! Virtual environment not found, installing dependencies globally

    REM ОБЯЗАТЕЛЬНАЯ установка requests глобально
    echo = Installing requests globally...
    pip install requests --quiet --force-reinstall

    echo = Installing all dependencies globally...
    pip install -r requirements.txt --quiet --force-reinstall

    REM Проверяем, установлен ли requests
    python -c "import requests; print('✓ requests installed')" 2>nul
    if errorlevel 1 (
        echo X Failed to install requests, trying again...
        pip install requests --force-reinstall
    )

    REM Проверяем, установлен ли Pillow
    python -c "from PIL import Image; print('✓ Pillow installed')" 2>nul
    if errorlevel 1 (
        echo X Failed to install Pillow, trying again...
        pip install Pillow --force-reinstall
    )

    REM Запускаем бота без виртуального окружения
    echo.
    echo = Starting bot...
    echo.
    python bot.py
)

REM При завершении
echo.
echo = Bot stopped
pause
