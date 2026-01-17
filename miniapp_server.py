#!/usr/bin/env python3
"""
miniapp_server.py - API server for admin miniapp
Serves chat data for the admin miniapp hosted on GitHub Pages
"""

import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
import database

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

        # Save admin message
        success = database.save_chat_message(chat_id, 'admin', message_text)

        if not success:
            return jsonify({'error': 'Failed to save message'}), 500

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error sending message: {e}")
        return jsonify({'error': 'Failed to send message'}), 500

@app.route('/api/chats/<int:chat_id>/status', methods=['PUT'])
def update_chat_status(chat_id):
    """Update chat status (pause/resume)"""
    try:
        data = request.json
        status = data.get('status', '')

        if status not in ['active', 'paused', 'completed']:
            return jsonify({'error': 'Invalid status'}), 400

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
