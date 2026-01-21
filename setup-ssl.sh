#!/bin/bash

# Скрипт настройки SSL сертификата для домена a950841.fvds.ru

set -e

DOMAIN="a950841.fvds.ru"
EMAIL="admin@$DOMAIN"

echo "🔒 Настраиваем SSL сертификат для $DOMAIN..."

# Устанавливаем Certbot
echo "📦 Устанавливаем Certbot..."
sudo apt update
sudo apt install -y certbot python3-certbot-nginx

# Временно настраиваем базовый Nginx конфиг для получения сертификата
echo "⚙️ Создаем временный Nginx конфиг..."
sudo tee /etc/nginx/sites-available/temp-ssl > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 200 "SSL setup in progress...";
        add_header Content-Type text/plain;
    }
}
EOF

# Активируем временный конфиг
sudo ln -sf /etc/nginx/sites-available/temp-ssl /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Получаем SSL сертификат
echo "🔐 Получаем SSL сертификат от Let's Encrypt..."
sudo certbot certonly --nginx -d $DOMAIN --email $EMAIL --agree-tos --non-interactive

# Проверяем, что сертификат получен
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "✅ SSL сертификат успешно получен!"
    
    # Устанавливаем основной конфиг
    echo "⚙️ Устанавливаем основной Nginx конфиг..."
    sudo cp /opt/telegram-bot/nginx.conf /etc/nginx/sites-available/telegram-bot
    sudo ln -sf /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/temp-ssl
    
    # Тестируем конфиг и перезагружаем
    sudo nginx -t && sudo systemctl reload nginx
    
    # Настраиваем автообновление сертификата
    echo "🔄 Настраиваем автообновление сертификата..."
    sudo crontab -l 2>/dev/null | { cat; echo "0 12 * * * /usr/bin/certbot renew --quiet && /usr/bin/systemctl reload nginx"; } | sudo crontab -
    
    echo "🎉 SSL настроен успешно!"
    echo "🌐 Ваш сайт доступен по адресу: https://$DOMAIN"
else
    echo "❌ Ошибка получения SSL сертификата!"
    echo "Проверьте, что домен $DOMAIN указывает на IP 155.212.164.61"
    exit 1
fi