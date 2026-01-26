#!/usr/bin/env python3
"""
miniapp_server.py - Simple API server for admin miniapp
"""

import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
import database
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["https://strdr1.github.io", "https://a950841.fvds.ru"], 
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"])

@app.route('/api/chats', methods=['GET'])
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

@app.route('/api/chats/<int:chat_id>', methods=['GET'])
def get_chat_messages(chat_id):
    """Get messages for a specific chat"""
    try:
        messages = database.get_chat_messages(chat_id, limit=100)
        # Преобразуем формат для админ-панели
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                'id': msg.get('id'),
                'sender': 'user' if msg.get('sender') == 'user' else 'admin',
                'message': msg.get('text', ''),
                'timestamp': msg.get('time', '')
            })
        
        response = jsonify(formatted_messages)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
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

        logger.info(f"Message saved to queue for user {user_chat_id}, bot will send it")

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return jsonify({'error': 'Failed to send message'}), 500

@app.route('/api/chats/<int:chat_id>/status', methods=['PUT'])
def update_chat_status(chat_id):
    """Update chat status (pause/resume)"""
    try:
        data = request.json
        status = data.get('status', '')

        if status not in ['active', 'paused', 'completed', 'help_needed']:
            return jsonify({'error': 'Invalid status'}), 400

        # Получаем информацию о чате перед обновлением
        chat_info = database.get_chat_by_id(chat_id)
        if not chat_info:
            return jsonify({'error': 'Chat not found'}), 404

        user_chat_id = chat_info.get('user_id')

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

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error updating chat status: {e}")
        return jsonify({'error': 'Failed to update status'}), 500

@app.route('/api/stats', methods=['GET'])
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

@app.route('/api/chats/<int:chat_id>/analyze', methods=['POST'])
def analyze_chat(chat_id):
    """Analyze chat with AI"""
    try:
        # Получаем сообщения чата
        messages = database.get_chat_messages(chat_id, limit=50)
        
        if not messages:
            return jsonify({'error': 'No messages found'}), 404
        
        # Простой анализ
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