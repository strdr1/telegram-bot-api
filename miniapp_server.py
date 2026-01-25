#!/usr/bin/env python3
"""
miniapp_server.py - API server for admin miniapp
Serves chat data for the admin miniapp hosted on GitHub Pages
"""

import os
import json
import asyncio
import time
from flask import Flask, jsonify, request, send_file
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
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Настройка CORS для поддержки Telegram WebApp
CORS(app, 
     origins=["https://strdr1.github.io", "https://a950841.fvds.ru", "*"], 
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
     supports_credentials=False)

# Дополнительные заголовки для Telegram WebApp
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Requested-With')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'false')
    return response

@app.route('/chats', methods=['GET'])
def get_chats():
    """Get all chats for admin"""
    try:
        chats = database.get_all_chats_for_admin()
        response = jsonify(chats)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except Exception as e:
        print(f"Error getting chats: {e}")
        return jsonify({'error': 'Failed to get chats'}), 500

@app.route('/chats/<int:chat_id>', methods=['GET'])
def get_chat_messages(chat_id):
    """Get messages for a specific chat"""
    try:
        messages = database.get_chat_messages(chat_id, limit=100)
        # Преобразуем формат для админ-панели
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                'id': msg.get('id'),
                'is_from_user': msg.get('sender') == 'user',
                'message_text': msg.get('text', ''),
                'created_at': msg.get('time', '')
            })
        
        response = jsonify(formatted_messages)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except Exception as e:
        print(f"Error getting chat messages: {e}")
        return jsonify({'error': 'Failed to get messages'}), 500

@app.route('/chats/<int:chat_id>/messages', methods=['POST'])
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

@app.route('/files', methods=['GET'])
def list_files():
    """List files in allowed directories"""
    try:
        # Allowed directories for file browsing
        allowed_dirs = ['files', 'rest_photos', 'temp', 'photos', 'miniapp']
        
        folder = request.args.get('folder', 'files')
        if folder not in allowed_dirs:
            return jsonify({'error': 'Access denied'}), 403
        
        base_path = f'/opt/telegram-bot/{folder}'
        if not os.path.exists(base_path):
            return jsonify({'files': [], 'folders': []})
        
        files = []
        folders = []
        
        for item in os.listdir(base_path):
            item_path = os.path.join(base_path, item)
            if os.path.isfile(item_path):
                # Get file info
                stat = os.stat(item_path)
                files.append({
                    'name': item,
                    'size': stat.st_size,
                    'modified': stat.st_mtime,
                    'type': 'file'
                })
            elif os.path.isdir(item_path):
                folders.append({
                    'name': item,
                    'type': 'folder'
                })
        
        response = jsonify({
            'files': sorted(files, key=lambda x: x['name']),
            'folders': sorted(folders, key=lambda x: x['name']),
            'current_folder': folder
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
        
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return jsonify({'error': 'Failed to list files'}), 500

@app.route('/files/download', methods=['GET'])
def download_file():
    """Download a file"""
    try:
        folder = request.args.get('folder', 'files')
        filename = request.args.get('filename')
        
        if not filename:
            return jsonify({'error': 'Filename required'}), 400
        
        # Security check
        allowed_dirs = ['files', 'rest_photos', 'temp', 'photos', 'miniapp']
        if folder not in allowed_dirs:
            return jsonify({'error': 'Access denied'}), 403
        
        # Prevent path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': 'Invalid filename'}), 400
        
        file_path = f'/opt/telegram-bot/{folder}/{filename}'
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return jsonify({'error': 'Failed to download file'}), 500

@app.route('/files/upload', methods=['POST'])
def upload_file():
    """Upload a file from computer"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        chat_id = request.form.get('chat_id')
        folder = request.form.get('folder', 'temp')
        
        if not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        
        if not chat_id:
            return jsonify({'error': 'chat_id required'}), 400
        
        # Security checks
        allowed_dirs = ['files', 'rest_photos', 'temp', 'photos', 'miniapp']
        if folder not in allowed_dirs:
            return jsonify({'error': 'Access denied'}), 403
        
        # Secure filename
        import re
        filename = re.sub(r'[^a-zA-Z0-9._-]', '_', file.filename)
        filename = f"{int(time.time())}_{filename}"
        
        # Create directory if not exists
        upload_dir = f'/opt/telegram-bot/{folder}'
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, filename)
        
        # Save file
        file.save(file_path)
        
        logger.info(f"File uploaded: {file_path}")
        
        # Get chat info
        chat_info = database.get_chat_by_id(int(chat_id))
        if not chat_info:
            # Remove uploaded file if chat not found
            os.remove(file_path)
            return jsonify({'error': 'Chat not found'}), 404
        
        # Save file send message to database queue
        message_text = f"📎 Файл: {file.filename}"
        success = database.save_chat_message(int(chat_id), 'admin', message_text, file_path=file_path)
        
        if not success:
            # Remove uploaded file if database save failed
            os.remove(file_path)
            return jsonify({'error': 'Failed to queue file'}), 500
        
        logger.info(f"File upload completed: {filename}")
        return jsonify({'success': True, 'filename': filename})
        
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return jsonify({'error': 'Failed to upload file'}), 500

@app.route('/files/send', methods=['POST'])
def send_file_to_chat():
    """Send a file to a chat"""
    try:
        logger.info(f"Received request: {request.method} {request.url}")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Data: {request.data}")
        
        try:
            data = request.get_json(force=True)
        except Exception as json_error:
            logger.error(f"JSON parsing error: {json_error}")
            return jsonify({'error': 'Invalid JSON'}), 400
            
        if not data:
            logger.error("No JSON data received")
            return jsonify({'error': 'No JSON data'}), 400
            
        chat_id = data.get('chat_id')
        folder = data.get('folder', 'files')
        filename = data.get('filename')
        
        logger.info(f"Sending file: chat_id={chat_id}, folder={folder}, filename={filename}")
        
        if not all([chat_id, filename]):
            logger.error("Missing chat_id or filename")
            return jsonify({'error': 'chat_id and filename required'}), 400
        
        # Security checks
        allowed_dirs = ['files', 'rest_photos', 'temp', 'photos', 'miniapp']
        if folder not in allowed_dirs:
            logger.error(f"Access denied for folder: {folder}")
            return jsonify({'error': 'Access denied'}), 403
        
        if '..' in filename or '/' in filename or '\\' in filename:
            logger.error(f"Invalid filename: {filename}")
            return jsonify({'error': 'Invalid filename'}), 400
        
        file_path = f'/opt/telegram-bot/{folder}/{filename}'
        logger.info(f"File path: {file_path}")
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            logger.error(f"File not found: {file_path}")
            return jsonify({'error': 'File not found'}), 404
        
        # Get chat info
        chat_info = database.get_chat_by_id(chat_id)
        if not chat_info:
            logger.error(f"Chat not found: {chat_id}")
            return jsonify({'error': 'Chat not found'}), 404
        
        logger.info(f"Chat found: {chat_info}")
        
        # Save file send message to database queue
        message_text = f"📎 Файл: {filename}"
        success = database.save_chat_message(chat_id, 'admin', message_text, file_path=file_path)
        
        if not success:
            logger.error(f"Failed to save message to database")
            return jsonify({'error': 'Failed to queue file'}), 500
        
        logger.info(f"File message saved successfully")
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        return jsonify({'error': 'Failed to send file'}), 500

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

@app.route('/chats/<int:chat_id>/status', methods=['PUT'])
def update_chat_status(chat_id):
    """Update chat status (pause/resume)"""
    try:
        data = request.get_json(force=True)
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

@app.route('/chats/<int:chat_id>/reply', methods=['POST'])
def reply_to_chat(chat_id):
    """Send a reply message to chat (equivalent to /reply command)"""
    try:
        data = request.get_json(force=True)
        message_text = data.get('message', '').strip()

        if not message_text:
            return jsonify({'error': 'Message cannot be empty'}), 400

        # Получаем информацию о чате
        chat_info = database.get_chat_by_id(chat_id)
        if not chat_info:
            return jsonify({'error': 'Chat not found'}), 404

        user_chat_id = chat_info.get('user_id')
        user_name = chat_info.get('user_name', f'Пользователь {user_chat_id}')

        logger.info(f"Admin reply to user {user_chat_id} ({user_name}): {message_text}")

        # Сохраняем сообщение админа в базу данных
        success = database.save_chat_message(chat_id, 'admin', message_text)

        if not success:
            logger.error(f"Failed to save admin reply to database for chat {chat_id}")
            return jsonify({'error': 'Failed to save message'}), 500

        logger.info(f"Admin reply saved to queue for user {user_chat_id}")

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error sending reply: {e}")
        return jsonify({'error': 'Failed to send reply'}), 500

@app.route('/chats/<int:chat_id>/stop', methods=['POST'])
def stop_chat(chat_id):
    """Stop chat mode (equivalent to /stop_chat command)"""
    try:
        # Получаем информацию о чате
        chat_info = database.get_chat_by_id(chat_id)
        if not chat_info:
            return jsonify({'error': 'Chat not found'}), 404

        user_chat_id = chat_info.get('user_id')
        user_name = chat_info.get('user_name', f'Пользователь {user_chat_id}')

        logger.info(f"Stopping chat mode for user {user_chat_id} ({user_name})")

        # Завершаем режим чата
        try:
            # Импортируем функции из handlers
            from handlers.handlers_admin import clear_operator_chat
            
            clear_operator_chat(user_chat_id)
            
            # Отправляем уведомление пользователю
            stop_message = "ℹ️ Оператор завершил чат. Вы снова в автоматическом режиме."
            database.save_chat_message(chat_id, 'admin', stop_message)
            
            logger.info(f"Chat mode stopped for user {user_chat_id}")
            
        except Exception as e:
            logger.error(f"Error stopping chat mode: {e}")
            return jsonify({'error': f'Failed to stop chat mode: {str(e)}'}), 500

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error stopping chat: {e}")
        return jsonify({'error': 'Failed to stop chat'}), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get chat statistics"""
    try:
        stats = database.get_chat_stats()
        response = jsonify(stats)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({'error': 'Failed to get stats'}), 500

@app.route('/chats/<int:chat_id>/analyze', methods=['POST'])
def analyze_chat(chat_id):
    """Analyze chat with AI"""
    try:
        # Получаем сообщения чата
        messages = database.get_chat_messages(chat_id, limit=50)
        
        if not messages:
            return jsonify({'error': 'No messages found'}), 404
        
        # Формируем текст для анализа
        chat_text = ""
        for msg in messages:
            sender = "Пользователь" if msg.get('sender') == 'user' else "Бот"
            chat_text += f"{sender}: {msg.get('text', '')}\n"
        
        # Простой анализ (можно заменить на AI)
        analysis = f"""
🔍 Анализ чата (ID: {chat_id})

📊 Статистика:
• Всего сообщений: {len(messages)}
• Сообщений пользователя: {len([m for m in messages if m.get('sender') == 'user'])}
• Сообщений бота: {len([m for m in messages if m.get('sender') == 'admin'])}

💬 Последнее сообщение: {messages[-1].get('text', '')[:100] if messages else 'Нет сообщений'}...

🎯 Возможные причины завершения:
• Пользователь получил нужную информацию
• Бот предоставил полный ответ
• Пользователь переключился на другую задачу
• Техническая проблема или ошибка

💡 Рекомендации:
• Проверить качество последних ответов бота
• Убедиться что пользователь получил помощь
• При необходимости связаться с пользователем
        """
        
        response = jsonify({'analysis': analysis.strip()})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
        
    except Exception as e:
        logger.error(f"Error analyzing chat {chat_id}: {e}")
        return jsonify({'error': 'Failed to analyze chat'}), 500

@app.route('/api/files/preview', methods=['GET'])
def preview_file():
    """Preview file"""
    try:
        path = request.args.get('path', '')
        real_path = f"/opt/telegram-bot{path}"
        
        # Безопасность
        allowed_paths = [
            '/opt/telegram-bot/files',
            '/opt/telegram-bot/rest_photos', 
            '/opt/telegram-bot/temp',
            '/opt/telegram-bot/photos',
            '/opt/telegram-bot/miniapp'
        ]
        
        if not any(real_path.startswith(allowed) for allowed in allowed_paths):
            return jsonify({'error': 'Access denied'}), 403
        
        if not os.path.exists(real_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Определяем MIME тип
        import mimetypes
        mime_type, _ = mimetypes.guess_type(real_path)
        
        return send_file(real_path, mimetype=mime_type)
        
    except Exception as e:
        logger.error(f"Error previewing file: {e}")
        return jsonify({'error': 'Failed to preview file'}), 500

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
