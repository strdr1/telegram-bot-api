#!/bin/bash

echo "=== Установка Google Chrome и драйвера ==="

# 1. Установка зависимостей
sudo apt-get update
sudo apt-get install -y wget unzip curl gnupg

# 2. Добавление ключа и репозитория Google
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'

# 3. Установка Chrome
sudo apt-get update
sudo apt-get install -y google-chrome-stable

# 4. Проверка версии
echo "Google Chrome version:"
google-chrome --version

echo "=== Установка завершена ==="
