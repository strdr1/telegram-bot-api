import asyncio
import logging
import aiohttp
import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_date(date_str, description):
    token = config.PRESTO_ACCESS_TOKEN
    point_id = 3596
    base_url = "https://api.sbis.ru/retail"
    url = f"{base_url}/nomenclature/price-list"
    
    params = {'pointId': point_id, 'pageSize': 100, 'actualDate': date_str}
    headers = {'X-SBISAccessToken': token, 'Accept': 'application/json'}

    logger.info(f"Checking for {description} ({date_str})...")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                price_lists = data.get('priceLists', [])
                print(f"\n--- RESULTS FOR {description} ---")
                for pl in price_lists:
                    print(f"ID {pl.get('id')}: {pl.get('name')}")
            else:
                logger.error(f"Error: {response.status}")
                print(await response.text())

async def main():
    # Saturday 10:00 AM (Weekend Breakfast should be visible)
    await check_date('2026-01-31 10:00:00', "SATURDAY 10:00")
    
    # Monday 10:00 AM (Weekday Breakfast should be visible)
    await check_date('2026-02-02 10:00:00', "MONDAY 10:00")

if __name__ == "__main__":
    if asyncio.get_event_loop_policy().__class__.__name__ == 'WindowsProactorEventLoopPolicy':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
