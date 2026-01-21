#!/bin/bash

# Скрипт настройки миниаппа для Telegram Bot

set -e

echo "📱 Настраиваем миниапп..."

# Создаем директорию для миниаппа
sudo mkdir -p /opt/telegram-bot/miniapp
sudo chown -R botuser:botuser /opt/telegram-bot/miniapp

# Обновляем index.html с правильными настройками
sudo -u botuser tee /opt/telegram-bot/miniapp/index.html > /dev/null << 'EOF'
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ресторан Машков - Заказ</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: var(--tg-theme-bg-color, #ffffff);
            color: var(--tg-theme-text-color, #000000);
        }
        .container {
            max-width: 400px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo {
            width: 80px;
            height: 80px;
            background: var(--tg-theme-button-color, #0088cc);
            border-radius: 50%;
            margin: 0 auto 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            color: white;
        }
        .title {
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .subtitle {
            color: var(--tg-theme-hint-color, #999999);
            font-size: 16px;
        }
        .menu-section {
            background: var(--tg-theme-secondary-bg-color, #f8f8f8);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .menu-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
        }
        .menu-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid var(--tg-theme-hint-color, #e0e0e0);
        }
        .menu-item:last-child {
            border-bottom: none;
        }
        .item-info {
            flex: 1;
        }
        .item-name {
            font-weight: 500;
            margin-bottom: 5px;
        }
        .item-price {
            color: var(--tg-theme-button-color, #0088cc);
            font-weight: bold;
        }
        .add-button {
            background: var(--tg-theme-button-color, #0088cc);
            color: var(--tg-theme-button-text-color, #ffffff);
            border: none;
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 14px;
            cursor: pointer;
        }
        .cart {
            position: fixed;
            bottom: 20px;
            left: 20px;
            right: 20px;
            background: var(--tg-theme-button-color, #0088cc);
            color: var(--tg-theme-button-text-color, #ffffff);
            border-radius: 12px;
            padding: 15px;
            text-align: center;
            font-weight: bold;
            display: none;
        }
        .loading {
            text-align: center;
            padding: 40px;
            color: var(--tg-theme-hint-color, #999999);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🍽️</div>
            <div class="title">Ресторан Машков</div>
            <div class="subtitle">Заказ доставки</div>
        </div>

        <div id="loading" class="loading">
            Загружаем меню...
        </div>

        <div id="menu" style="display: none;">
            <div class="menu-section">
                <div class="menu-title">🍕 Пиццы</div>
                <div class="menu-item">
                    <div class="item-info">
                        <div class="item-name">Пицца Маргарита</div>
                        <div class="item-price">750₽</div>
                    </div>
                    <button class="add-button" onclick="addToCart('pizza-margherita', 750)">+</button>
                </div>
                <div class="menu-item">
                    <div class="item-info">
                        <div class="item-name">Пицца Пепперони</div>
                        <div class="item-price">780₽</div>
                    </div>
                    <button class="add-button" onclick="addToCart('pizza-pepperoni', 780)">+</button>
                </div>
            </div>

            <div class="menu-section">
                <div class="menu-title">🍲 Супы</div>
                <div class="menu-item">
                    <div class="item-info">
                        <div class="item-name">Борщ украинский</div>
                        <div class="item-price">450₽</div>
                    </div>
                    <button class="add-button" onclick="addToCart('soup-borsch', 450)">+</button>
                </div>
            </div>
        </div>

        <div id="cart" class="cart">
            <div id="cart-content">Корзина пуста</div>
        </div>
    </div>

    <script>
        // Инициализация Telegram WebApp
        let tg = window.Telegram.WebApp;
        tg.expand();
        tg.ready();

        // Применяем тему Telegram
        document.body.style.backgroundColor = tg.themeParams.bg_color || '#ffffff';
        document.body.style.color = tg.themeParams.text_color || '#000000';

        // Корзина
        let cart = {};
        let cartTotal = 0;

        function addToCart(itemId, price) {
            if (cart[itemId]) {
                cart[itemId].quantity += 1;
            } else {
                cart[itemId] = { price: price, quantity: 1 };
            }
            updateCart();
            
            // Вибрация при добавлении
            tg.HapticFeedback.impactOccurred('light');
        }

        function updateCart() {
            cartTotal = 0;
            let itemCount = 0;
            
            for (let itemId in cart) {
                cartTotal += cart[itemId].price * cart[itemId].quantity;
                itemCount += cart[itemId].quantity;
            }

            const cartElement = document.getElementById('cart');
            const cartContent = document.getElementById('cart-content');

            if (itemCount > 0) {
                cartContent.innerHTML = `Товаров: ${itemCount} • Сумма: ${cartTotal}₽`;
                cartElement.style.display = 'block';
                cartElement.onclick = () => {
                    // Отправляем данные корзины в Telegram
                    tg.sendData(JSON.stringify({
                        action: 'order',
                        cart: cart,
                        total: cartTotal
                    }));
                };
                
                // Показываем главную кнопку
                tg.MainButton.setText(`Заказать за ${cartTotal}₽`);
                tg.MainButton.show();
                tg.MainButton.onClick(() => {
                    tg.sendData(JSON.stringify({
                        action: 'order',
                        cart: cart,
                        total: cartTotal
                    }));
                });
            } else {
                cartElement.style.display = 'none';
                tg.MainButton.hide();
            }
        }

        // Симуляция загрузки меню
        setTimeout(() => {
            document.getElementById('loading').style.display = 'none';
            document.getElementById('menu').style.display = 'block';
        }, 1000);

        // Обработка закрытия приложения
        tg.onEvent('mainButtonClicked', () => {
            tg.close();
        });

        console.log('Telegram WebApp initialized');
    </script>
</body>
</html>
EOF

# Обновляем netlify.toml
sudo -u botuser tee /opt/telegram-bot/miniapp/netlify.toml > /dev/null << 'EOF'
[build]
  publish = "."

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "ALLOWALL"
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "strict-origin-when-cross-origin"

[[headers]]
  for = "*.html"
  [headers.values]
    Cache-Control = "public, max-age=0, must-revalidate"

[[headers]]
  for = "*.js"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"

[[headers]]
  for = "*.css"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
EOF

echo "✅ Миниапп настроен!"
echo "📱 Локальный URL: https://a950841.fvds.ru/miniapp/"
echo "🌐 GitHub Pages URL: https://strdr1.github.io/mashkov-telegram-app/"