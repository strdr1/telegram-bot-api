import asyncio
import logging
import json
from presto_api import presto_api

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("🚀 Starting full menu scan...")
    
    try:
        # 1. Get ALL price lists directly
        price_lists = await presto_api.get_price_lists()
        
        if not price_lists:
             logger.error("❌ No price lists found!")
             return

        logger.info(f"📋 Found {len(price_lists)} price lists. Scanning ALL of them...")
        
        found_pasta = []
        found_breakfast = []
        
        # Create a mapping for ID -> Name
        pl_map = {int(pl['id']): pl['name'] for pl in price_lists}
        
        for pl_id, pl_name in pl_map.items():
            logger.info(f"🔍 Scanning Menu {pl_id}: {pl_name}...")
            
            # Fetch menu data for this ID specifically
            menu_data = await presto_api.get_menu_by_id(pl_id, {pl_id: {'name': pl_name, 'id': pl_id}})
            
            if not menu_data:
                logger.warning(f"   ⚠️ Menu {pl_id} is empty or failed to load.")
                continue

            categories = menu_data
            # categories is a dict: {cat_id: {name: ..., items: [...]}}
            if isinstance(categories, dict) and 'categories' in categories: # Handle if it returns structured menu wrapper
                categories = categories['categories']
            
            total_items = sum(len(cat.get('items', [])) for cat in categories.values())
            logger.info(f"   ✅ Loaded {len(categories)} categories, {total_items} items.")
            
            # Check for pasta and breakfast
            for cat_id, cat in categories.items():
                cat_name = cat.get('name', '').lower()
                
                if 'паст' in cat_name or 'pasta' in cat_name:
                    logger.info(f"     🍝 FOUND PASTA CATEGORY: '{cat['name']}' (ID {cat_id}) in Menu {pl_id}")
                    items = cat.get('items', [])
                    logger.info(f"        Items count: {len(items)}")
                    found_pasta.append(f"Menu {pl_id} ('{pl_name}') -> Category '{cat['name']}'")
                
                if 'завтрак' in cat_name:
                     logger.info(f"     🍳 FOUND BREAKFAST CATEGORY: '{cat['name']}' (ID {cat_id}) in Menu {pl_id}")
                     items = cat.get('items', [])
                     logger.info(f"        Items count: {len(items)}")
                     found_breakfast.append(f"Menu {pl_id} ('{pl_name}') -> Category '{cat['name']}'")

                # Check for breakfast items directly
                for item in cat.get('items', []):
                    item_name = item.get('name', '').lower()
                    if any(x in item_name for x in ['омлет', 'сырники', 'каша', 'яйцо']):
                        logger.info(f"     🥚 FOUND BREAKFAST ITEM: '{item['name']}' in Menu {pl_id} (Category '{cat['name']}')")
                        found_breakfast.append(f"Menu {pl_id} ('{pl_name}') -> Item '{item['name']}'")

        logger.info("-" * 50)
        if found_pasta:
            logger.info("✅ Pasta locations found:")
            for loc in found_pasta:
                logger.info(f"   - {loc}")
        else:
            logger.warning("❌ 'Pasta' category NOT found in ANY menu!")

        if found_breakfast:
            logger.info("✅ Breakfast locations found:")
            for loc in found_breakfast:
                logger.info(f"   - {loc}")
        else:
            logger.warning("❌ 'Breakfast' category NOT found in ANY menu!")

    except Exception as e:
        logger.error(f"Error fetching menus: {e}")

if __name__ == "__main__":
    asyncio.run(main())