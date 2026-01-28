
import asyncio
import logging
from menu_cache import MenuCache
from debug_context import generate_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_cache_and_context():
    logger.info("Starting menu cache update...")
    cache = MenuCache()
    # Force update from API
    await cache.load_all_menus(force_update=True)
    logger.info("Menu cache updated.")
    
    # Generate context file
    logger.info("Generating menu_context.json...")
    generate_context()
    logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(update_cache_and_context())
