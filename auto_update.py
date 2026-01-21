#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт автообновления бота через GitHub
"""

import subprocess
import sys
import os
import logging
import time
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('update.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def run_command(command, cwd=None):
    """Выполнить команду и вернуть результат"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=cwd,
            capture_output=True, 
            text=True, 
            timeout=60
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Команда '{command}' превысила таймаут")
        return False, "", "Timeout"
    except Exception as e:
        logger.error(f"Ошибка выполнения команды '{command}': {e}")
        return False, "", str(e)

def check_for_updates():
    """Проверить наличие обновлений"""
    logger.info("🔍 Проверяем наличие обновлений...")
    
    # Получаем информацию о текущем коммите
    success, current_commit, error = run_command("git rev-parse HEAD")
    if not success:
        logger.error(f"Не удалось получить текущий коммит: {error}")
        return False
    
    current_commit = current_commit.strip()
    logger.info(f"Текущий коммит: {current_commit[:8]}")
    
    # Получаем обновления с удаленного репозитория
    success, output, error = run_command("git fetch origin")
    if not success:
        logger.error(f"Не удалось получить обновления: {error}")
        return False
    
    # Проверяем, есть ли новые коммиты
    success, remote_commit, error = run_command("git rev-parse origin/main")
    if not success:
        logger.error(f"Не удалось получить удаленный коммит: {error}")
        return False
    
    remote_commit = remote_commit.strip()
    logger.info(f"Удаленный коммит: {remote_commit[:8]}")
    
    if current_commit != remote_commit:
        logger.info("✅ Найдены обновления!")
        return True
    else:
        logger.info("ℹ️ Обновлений нет")
        return False

def backup_important_files():
    """Создать резервную копию важных файлов"""
    logger.info("💾 Создаем резервную копию важных файлов...")
    
    important_files = [
        '.env',
        'config.py', 
        'ai_ref/token.txt',
        'restaurant.db'
    ]
    
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    try:
        os.makedirs(backup_dir, exist_ok=True)
        
        for file_path in important_files:
            if os.path.exists(file_path):
                # Создаем директории если нужно
                backup_file_path = os.path.join(backup_dir, file_path)
                backup_file_dir = os.path.dirname(backup_file_path)
                if backup_file_dir:
                    os.makedirs(backup_file_dir, exist_ok=True)
                
                # Копируем файл
                success, output, error = run_command(f'copy "{file_path}" "{backup_file_path}"')
                if success:
                    logger.info(f"✅ Скопирован: {file_path}")
                else:
                    logger.warning(f"⚠️ Не удалось скопировать {file_path}: {error}")
        
        logger.info(f"💾 Резервная копия создана в: {backup_dir}")
        return backup_dir
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания резервной копии: {e}")
        return None

def apply_updates():
    """Применить обновления"""
    logger.info("🔄 Применяем обновления...")
    
    # Сохраняем изменения в stash (если есть)
    run_command("git stash")
    
    # Получаем обновления
    success, output, error = run_command("git pull origin main")
    if not success:
        logger.error(f"❌ Не удалось применить обновления: {error}")
        return False
    
    logger.info("✅ Обновления применены успешно!")
    
    # Восстанавливаем изменения из stash (если были)
    run_command("git stash pop")
    
    return True

def restart_bot():
    """Перезапустить бота"""
    logger.info("🔄 Перезапускаем бота...")
    
    # Останавливаем текущий процесс бота (если запущен)
    run_command("taskkill /f /im python.exe")
    
    # Ждем немного
    time.sleep(2)
    
    # Запускаем бота заново
    if os.path.exists("start.bat"):
        success, output, error = run_command("start.bat")
        if success:
            logger.info("✅ Бот перезапущен!")
            return True
        else:
            logger.error(f"❌ Не удалось перезапустить бота: {error}")
            return False
    else:
        logger.warning("⚠️ Файл start.bat не найден, запустите бота вручную")
        return False

def main():
    """Основная функция автообновления"""
    logger.info("🚀 Запуск автообновления...")
    
    try:
        # Проверяем наличие обновлений
        if not check_for_updates():
            logger.info("✅ Автообновление завершено - обновлений нет")
            return
        
        # Создаем резервную копию
        backup_dir = backup_important_files()
        if not backup_dir:
            logger.error("❌ Не удалось создать резервную копию, обновление отменено")
            return
        
        # Применяем обновления
        if not apply_updates():
            logger.error("❌ Не удалось применить обновления")
            return
        
        # Перезапускаем бота
        restart_bot()
        
        logger.info("🎉 Автообновление завершено успешно!")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка автообновления: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()