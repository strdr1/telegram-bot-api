#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Планировщик автообновлений бота
"""

import schedule
import time
import subprocess
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def run_update():
    """Запустить процесс обновления"""
    logger.info("Запуск планового обновления...")
    
    try:
        result = subprocess.run(
            ["python", "auto_update.py"],
            capture_output=True,
            text=True,
            timeout=300  # 5 минут таймаут
        )
        
        if result.returncode == 0:
            logger.info("Плановое обновление завершено успешно")
        else:
            logger.error(f"Ошибка планового обновления: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        logger.error("Плановое обновление превысило таймаут")
    except Exception as e:
        logger.error(f"Критическая ошибка планового обновления: {e}")

def main():
    """Основная функция планировщика"""
    logger.info("Запуск планировщика автообновлений...")
    
    # Настраиваем расписание
    # Проверяем обновления каждые 30 минут
    schedule.every(30).minutes.do(run_update)
    
    # Также можно настроить проверку в определенное время
    # schedule.every().day.at("03:00").do(run_update)  # Каждый день в 3:00
    # schedule.every().hour.do(run_update)  # Каждый час
    
    logger.info("Расписание настроено:")
    logger.info("   - Проверка обновлений каждые 30 минут")
    
    # Запускаем планировщик
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Проверяем каждую минуту
        except KeyboardInterrupt:
            logger.info("Планировщик остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"Ошибка планировщика: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()