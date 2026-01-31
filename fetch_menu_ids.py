
import asyncio
import logging
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from presto_api import presto_api

async def main():
    try:
        print("Fetching price lists from Presto API...")
        price_lists = await presto_api.get_price_lists()
        
        print("\n" + "="*50)
        print("AVAILABLE PRICE LISTS (MENUS):")
        print("="*50)
        
        for pl in price_lists:
            print(f"ID: {pl.get('id')} | Name: {pl.get('name')}")
            
        print("="*50 + "\n")
        
    except Exception as e:
        logger.error(f"Error fetching price lists: {e}")
    finally:
        await presto_api.close_session()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
