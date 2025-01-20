# main.py

import asyncio
import logging
from data.data_locker import DataLocker  # Ensure correct import path
from data.models import Price, AssetType, SourceType
from datetime import datetime, timedelta, timezone  # Updated import

def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),               # Outputs to console
            logging.FileHandler("datalocker.log")  # Outputs to a log file
        ]
    )

async def main():
    # Configure logging
    configure_logging()

    # Initialize the DataLocker singleton instance
    locker = await DataLocker.get_instance(db_path="data_locker.db")  # Specify your desired DB path

    # Example: Create a new Price entry
    price = Price(
        asset_type=AssetType.BTC,
        current_price=50000.0,
        previous_price=49000.0,
        avg_daily_swing=1000.0,
        avg_1_hour=500.0,
        avg_3_hour=1500.0,
        avg_6_hour=3000.0,
        avg_24_hour=4000.0,
        last_update_time=datetime.now(timezone.utc),  # Updated to timezone-aware datetime
        previous_update_time=datetime.now(timezone.utc) - timedelta(days=1),  # Updated to timezone-aware datetime
        source=SourceType.AUTO
    )

    await locker.insert_or_update_price(price)
    print(f"Inserted/Updated price for {price.asset_type.value}")

    # Example: Retrieve all Prices
    prices = await locker.get_prices()
    for p in prices:
        print(p)

    # Example: Delete a Price
    await locker.delete_price(AssetType.BTC)
    print(f"Deleted price for {AssetType.BTC.value}")

if __name__ == "__main__":
    asyncio.run(main())
