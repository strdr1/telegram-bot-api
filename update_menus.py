import json
import asyncio
import logging
import os
from menu_cache import menu_cache

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def update_menus():
    """
    Принудительное обновление всех меню и сохранение в кэш
    """
    logger.info("🚀 Запуск обновления меню...")
    
    try:
        # Принудительно загружаем меню из API
        menus = await menu_cache.load_all_menus(force_update=True)
        
        if menus:
            logger.info(f"✅ Меню успешно обновлены. Всего меню: {len(menus)}")
            
            # Проверяем файл кэша
            cache_file = 'files/menu_cache.json'
            if os.path.exists(cache_file):
                size = os.path.getsize(cache_file) / 1024  # KB
                logger.info(f"📁 Файл кэша создан: {cache_file} ({size:.2f} KB)")
                
                # Проверка содержимого
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    point_id = data.get('point_id')
                    timestamp = data.get('timestamp')
                    cached_menus = data.get('all_menus', {})
                    
                    logger.info(f"   • Point ID: {point_id}")
                    logger.info(f"   • Timestamp: {timestamp}")
                    logger.info(f"   • Cached Menus: {len(cached_menus)}")
            else:
                logger.error(f"❌ Файл кэша не найден: {cache_file}")
        else:
            logger.error("❌ Не удалось получить меню из API")
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при обновлении: {e}", exc_info=True)

if __name__ == "__main__":
    # Запускаем асинхронную функцию
    asyncio.run(update_menus())
