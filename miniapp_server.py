#!/usr/bin/env python3
"""
miniapp_server.py - API server for admin miniapp
Serves chat data for the admin miniapp hosted on GitHub Pages
"""

import os
import json
import asyncio
from flask import Flask, jsonify, request
from flask_cors import CORS
import database
import logging

# Импортируем бота для отправки сообщений
try:
    from bot import bot
except ImportError:
    bot = None

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/api/chats', methods=['GET'])
def get_chats():
    """Get all chats for admin"""
    try:
        chats = database.get_all_chats_for_admin()
        return jsonify(chats)
    except Exception as e:
        print(f"Error getting chats: {e}")
        return jsonify({'error': 'Failed to get chats'}), 500

@app.route('/api/chats/<int:chat_id>', methods=['GET'])
def get_chat_messages(chat_id):
    """Get messages for a specific chat"""
    try:
        messages = database.get_chat_messages(chat_id)
        return jsonify(messages)
    except Exception as e:
        print(f"Error getting chat messages: {e}")
        return jsonify({'error': 'Failed to get messages'}), 500

@app.route('/api/chats/<int:chat_id>/messages', methods=['POST'])
def send_message(chat_id):
    """Send a message to a chat"""
    try:
        data = request.json
        message_text = data.get('message', '').strip()

        if not message_text:
            return jsonify({'error': 'Message cannot be empty'}), 400

        # Получаем информацию о чате
        chat_info = database.get_chat_by_id(chat_id)
        if not chat_info:
            logger.error(f"Chat {chat_id} not found in database")
            return jsonify({'error': 'Chat not found'}), 404

        user_chat_id = chat_info.get('user_id')
        user_name = chat_info.get('user_name', f'Пользователь {user_chat_id}')

        logger.info(f"Sending message from miniapp to user {user_chat_id} ({user_name})")

        # Save admin message to database
        success = database.save_chat_message(chat_id, 'admin', message_text)

        if not success:
            logger.error(f"Failed to save message to database for chat {chat_id}")
            return jsonify({'error': 'Failed to save message'}), 500

        # Сообщение будет отправлено ботом через очередь в базе данных
        # Миниапп сервер просто сохраняет сообщение с sent=0, бот его подхватит
        logger.info(f"Message saved to queue for user {user_chat_id}, bot will send it")

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return jsonify({'error': 'Failed to send message'}), 500

async def send_telegram_message(user_chat_id: int, message_text: str):
    """Асинхронная функция для отправки сообщения через Telegram бота"""
    try:
        from handlers.utils import safe_send_message

        # Импортируем бота здесь, чтобы избежать циклических импортов
        try:
            from bot import bot as telegram_bot
        except ImportError:
            logger.error("Cannot import telegram bot")
            return

        # Отправляем сообщение пользователю
        result = await safe_send_message(telegram_bot, user_chat_id, message_text)
        if result:
            logger.info(f"Successfully sent message to user {user_chat_id}")
        else:
            logger.error(f"Failed to send message to user {user_chat_id}")

    except Exception as e:
        logger.error(f"Error in send_telegram_message: {e}")

@app.route('/api/chats/<int:chat_id>/status', methods=['PUT'])
def update_chat_status(chat_id):
    """Update chat status (pause/resume)"""
    try:
        data = request.json
        status = data.get('status', '')

        if status not in ['active', 'paused', 'completed']:
            return jsonify({'error': 'Invalid status'}), 400

        # Получаем информацию о чате перед обновлением
        chat_info = database.get_chat_by_id(chat_id)
        if not chat_info:
            return jsonify({'error': 'Chat not found'}), 404

        user_chat_id = chat_info.get('user_id')
        user_name = chat_info.get('user_name', f'Пользователь {user_chat_id}')

        # Определяем сообщение для пользователя
        message_text = ""
        if status == 'paused':
            message_text = "🤖 Диалог переведен в ручной режим. Все ваши сообщения будут обрабатываться администратором."
        elif status == 'active':
            message_text = "🤖 Диалог возобновлен. Бот снова может отвечать на ваши сообщения автоматически."

        # Обновляем статус в базе данных
        success = database.update_chat_status(chat_id, status)

        if not success:
            return jsonify({'error': 'Failed to update status'}), 500

        # Отправляем сообщение пользователю, если статус изменился на paused или active
        if message_text and bot:
            try:
                from handlers.utils import safe_send_message
                import asyncio

                # Запускаем асинхронную отправку сообщения
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(safe_send_message(bot, user_chat_id, message_text))
                loop.close()

                if result:
                    logger.info(f"Status change message sent to user {user_chat_id}")
                else:
                    logger.error(f"Failed to send status change message to user {user_chat_id}")

            except Exception as e:
                logger.error(f"Error sending status change message: {e}")

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error updating chat status: {e}")
        return jsonify({'error': 'Failed to update status'}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get chat statistics"""
    try:
        stats = database.get_chat_stats()
        return jsonify(stats)
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({'error': 'Failed to get stats'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Initialize database
    database.init_database()

    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Starting MiniApp API server on port {port}")
    print("📱 API available for admin miniapp")
    app.run(host='0.0.0.0', port=port, debug=False)
