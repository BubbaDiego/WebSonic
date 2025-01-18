# prices/price_monitor.py

import asyncio
import logging
from data.data_locker import DataLocker  # Correct import
from data.config import AppConfig
from typing import Dict, List, Optional

logger = logging.getLogger("PriceMonitorLogger")


class PriceMonitor:
    def __init__(self, config_path: str = 'sonic_config.json'):
        self.config_path = config_path
        self.config = self.load_config()
        self.setup_logging()
        self.assets = self.config.price_config.assets
        self.currency = self.config.price_config.currency
        self.data_locker = None  # Will be initialized asynchronously

    def load_config(self) -> AppConfig:
        config = AppConfig.load(self.config_path)
        return config

    def setup_logging(self):
        # Setup logging based on system_config
        if self.config.system_config.logging_enabled:
            log_level = getattr(logging, self.config.system_config.log_level.upper(), logging.DEBUG)
            logging.basicConfig(
                level=log_level,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(self.config.system_config.log_file),
                    logging.StreamHandler() if self.config.system_config.console_output else logging.NullHandler()
                ]
            )
        else:
            logging.basicConfig(level=logging.CRITICAL)  # Suppress logs if disabled

    async def initialize_monitor(self):
        try:
            # Initialize DataLocker
            self.data_locker = DataLocker.get_instance(self.config.system_config.db_path)
            logger.info("PriceMonitor initialized with configuration.")
        except Exception as e:
            logger.error(f"Failed to initialize DataLocker: {e}")
            raise

    async def get_previous_prices(self) -> Dict[str, float]:
        try:
            previous_prices = self.data_locker.get_latest_prices()
            return previous_prices
        except AttributeError as e:
            logger.error(f"'DataLocker' object has no attribute 'get_latest_prices': {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching previous prices: {e}")
            raise

    async def update_prices(self):
        try:
            previous_prices = self.get_previous_prices()
            # Logic to fetch new prices from APIs
            # For demonstration, we'll use mock data
            new_prices = {
                "BTC": 50000.0,
                "ETH": 4000.0,
                "SOL": 150.0
            }
            for asset, price in new_prices.items():
                self.data_locker.insert_or_update_price(asset, price, "CoinGecko")
            logger.info("Prices updated successfully.")
        except Exception as e:
            logger.error(f"Error updating prices: {e}")

    async def run_monitor_loop(self):
        while True:
            await self.update_prices()
            await asyncio.sleep(self.config.system_config.sonic_monitor_loop_time)


# Main execution
if __name__ == "__main__":
    monitor = PriceMonitor()
    try:
        asyncio.run(monitor.initialize_monitor())
        asyncio.run(monitor.run_monitor_loop())
    except Exception as e:
        logger.critical(f"PriceMonitor failed to start: {e}")
