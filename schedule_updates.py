#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Планировщик автообновлений бота
"""

import time
import subprocess
import logging
from datetime import datetime, date
import pytz

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
            ["python", "auto_menu_update.py"],
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
    
    moscow_tz = pytz.timezone('Europe/Moscow')
    last_run: date = None

    logger.info("Расписание настроено: ежедневно в 08:00 по Москве")

    while True:
        try:
            now_msk = datetime.now(moscow_tz)
            if now_msk.hour == 8 and now_msk.minute == 0:
                if last_run != now_msk.date():
                    run_update()
                    last_run = now_msk.date()
                    time.sleep(65)  # чтобы не сработало дважды в ту же минуту
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("Планировщик остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"Ошибка планировщика: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
