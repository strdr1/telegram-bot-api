import database
import logging

logging.basicConfig(level=logging.INFO)

try:
    point_id = database.get_setting('presto_point_id')
    print(f"DB Point ID: {point_id}")
except Exception as e:
    print(f"Error: {e}")
