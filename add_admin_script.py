import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from database import init_database, add_admin, is_admin

async def main():
    print("Checking admin status...")
    init_database()
    
    target_id = 584326661
    
    if is_admin(target_id):
        print(f"User {target_id} is already an admin.")
    else:
        print(f"Adding user {target_id} as admin...")
        success = add_admin(target_id)
        if success:
            print(f"Successfully added admin {target_id}")
        else:
            print(f"Failed to add admin {target_id}")

if __name__ == "__main__":
    asyncio.run(main())
