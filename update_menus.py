import asyncio
import logging
import json
import os
from menu_cache import menu_cache, ALLOWED_MENU_IDS
from presto_api import presto_api

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("🚀 Starting menu update...")
    
    # 1. Force update from Presto
    logger.info("Fetching menus from Presto API...")
    try:
        menus = await menu_cache.load_all_menus(force_update=True)
        success = bool(menus)
    except Exception as e:
        logger.error(f"Error updating menus: {e}")
        success = False
    
    if success:
        logger.info("✅ Menu update successful!")
    else:
        logger.error("❌ Menu update failed!")
        return

    # 2. Verify all_menus_cache.json
    cache_file = 'files/all_menus_cache.json'
    if not os.path.exists(cache_file):
        logger.error(f"❌ Cache file {cache_file} not found!")
        return

    with open(cache_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    all_menus = data.get('all_menus', {})
    logger.info(f"📂 Found {len(all_menus)} menus in cache.")
    
    found_ids = set()
    for m_id, m_data in all_menus.items():
        try:
            m_id_int = int(m_id)
            found_ids.add(m_id_int)
            logger.info(f"   - Menu ID {m_id}: {m_data.get('name')} ({len(m_data.get('categories', {}))} categories)")
        except:
            pass

    # 3. Check against ALLOWED_MENU_IDS
    missing = ALLOWED_MENU_IDS - found_ids
    if missing:
        logger.warning(f"⚠️ Missing ALLOWED IDs in cache: {missing}")
    else:
        logger.info("✅ All ALLOWED IDs are present in cache.")

    # 4. Check for 'Пузырки' and 'Разливное' keywords
    found_keywords = []
    for m_id, m_data in all_menus.items():
        for cat_id, cat in m_data.get('categories', {}).items():
            cat_name = cat.get('name', '').lower()
            if 'пузыр' in cat_name:
                found_keywords.append(f"Пузырки found in {m_data.get('name')}: {cat['name']}")
            if 'разливн' in cat_name:
                found_keywords.append(f"Разливное found in {m_data.get('name')}: {cat['name']}")
            if 'бутылочн' in cat_name:
                found_keywords.append(f"Бутылочное found in {m_data.get('name')}: {cat['name']}")

    if found_keywords:
        logger.info("✅ Found expected keywords in categories:")
        for k in found_keywords:
            logger.info(f"   - {k}")
    else:
        logger.warning("⚠️ Did not find 'пузырки' or 'разливное' in category names. Verify menu content!")

    # 5. Check for broken parent IDs
    logger.info("🔍 Checking for broken parent IDs...")
    broken_parents = []
    for m_id, m_data in all_menus.items():
        categories = m_data.get('categories', {})
        cat_ids = set(categories.keys())
        for cat_id, cat in categories.items():
            parent_id = cat.get('parent_id')
            if parent_id and str(parent_id) not in cat_ids:
                 broken_parents.append(f"Menu {m_id}: Category {cat['name']} ({cat_id}) has missing parent {parent_id}")

    if broken_parents:
        logger.warning(f"⚠️ Found {len(broken_parents)} broken parent references:")
        for bp in broken_parents:
            logger.warning(f"   - {bp}")
    else:
        logger.info("✅ No broken parent references found.")

    # 6. Close Presto API session
    await presto_api.close_session()

if __name__ == "__main__":
    asyncio.run(main())
