#!/bin/bash

# Скрипт обновления Telegram Bot на сервере
# Сервер: a950841.fvds.ru (155.212.164.61)

echo "========================================"
echo "   Telegram Bot Update Script"
echo "========================================"
echo

echo "[1/6] Connecting to server..."
echo

# Выполняем команды на сервере
ssh -o StrictHostKeyChecking=no root@155.212.164.61 << 'EOF'
echo "Mashkov.Rest"
echo ========================================
echo "   SERVER CONNECTION ESTABLISHED"
echo ========================================
echo

cd /opt/telegram-bot
echo "[2/6] Current directory:"
pwd
echo

echo "[3/6] Checking git status..."
sudo -u botuser git status --porcelain
echo

echo "[4/6] Pulling latest changes..."
sudo -u botuser git pull origin master
echo

echo "[5/6] Restarting services..."
sudo supervisorctl restart telegram-bot-group
echo

echo "[6/6] Service status:"
sudo supervisorctl status
echo

echo ========================================
echo "   UPDATE COMPLETED SUCCESSFULLY!"
echo ========================================
EOF

echo
echo ========================================
echo "   Update process finished!"
echo ========================================
echo
