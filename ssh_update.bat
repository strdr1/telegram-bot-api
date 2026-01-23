@echo off
chcp 65001 >nul
echo ========================================
echo    Telegram Bot Update Script
echo ========================================
echo.

echo ШАГ 1: Подключение к серверу...
echo ========================================
ssh -o StrictHostKeyChecking=no root@155.212.164.61 "echo '=== СЕРВЕР ДОСТУПЕН ===' && cd /opt/telegram-bot && pwd"

echo.
echo ========================================
echo ШАГ 2: Остановка сервисов...
echo ========================================
ssh -o StrictHostKeyChecking=no root@155.212.164.61 "echo '=== ОСТАНАВЛИВАЕМ СЕРВИСЫ ===' && sudo supervisorctl stop telegram-bot-group:* && sleep 3"

echo.
echo ========================================
echo ШАГ 3: Обновление кода...
echo ========================================
ssh -o StrictHostKeyChecking=no root@155.212.164.61 "echo '=== ОБНОВЛЯЕМ КОД ===' && \
  mkdir -p /opt/telegram-bot-backup && \
  cp /opt/telegram-bot/restaurant.db /opt/telegram-bot-backup/restaurant.db 2>/dev/null || true && \
  cd /opt/telegram-bot && \
  git reset --hard HEAD && \
  git clean -fd && \
  git pull origin master && \
  cp /opt/telegram-bot-backup/restaurant.db /opt/telegram-bot/restaurant.db 2>/dev/null || true && \
  echo '=== ПРОВЕРКА КОДА ===' && git log --oneline -1"

echo.
echo ========================================
echo ШАГ 4: Запуск сервисов...
echo ========================================
ssh -o StrictHostKeyChecking=no root@155.212.164.61 "echo '=== ЗАПУСКАЕМ СЕРВИСЫ ===' && sudo supervisorctl start telegram-bot-group:* && sleep 5 && sudo supervisorctl status"

echo.
echo ========================================
echo ШАГ 5: Проверка работы...
echo ========================================
ssh -o StrictHostKeyChecking=no root@155.212.164.61 "echo '=== ПРОВЕРКА РАБОТЫ ===' && ps aux | grep python | grep -v grep | grep -E '(bot\.py|schedule_updates\.py|miniapp_server\.py)' | wc -l && echo 'процессов запущено' && echo '=== ПОСЛЕДНИЕ СООБЩЕНИЯ В ЛОГЕ ===' && tail -3 /var/log/telegram-bot/bot.log"

echo.
echo ========================================
echo    ✅ ОБНОВЛЕНИЕ ЗАВЕРШЕНО!
echo ========================================
echo.
echo Если возникли ошибки - проверьте логи на сервере:
echo ssh root@155.212.164.61 "tail -20 /var/log/telegram-bot/bot.log"
echo.
pause
