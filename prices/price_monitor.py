import asyncio
import logging
from typing import Dict, Optional
import aiohttp  # <-- for async HTTP requests

from data.data_locker import DataLocker
from data.config import AppConfig

logger = logging.getLogger("PriceMonitorLogger")


class PriceMonitor:
    def __init__(self, config_path: str = 'sonic_config.json'):
        self.config_path = config_path
        self.config = self.load_config()
        self.setup_logging()
        self.assets = self.config.price_config.assets  # e.g. ["BTC", "ETH", "SOL"]
        self.currency = self.config.price_config.currency  # e.g. "USD"
        self.data_locker: Optional[DataLocker] = None

        # For CoinGecko, we need to map your asset symbols to their slugs
        self.coingecko_map = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            # add more if you want
        }

    def load_config(self) -> AppConfig:
        return AppConfig.load(self.config_path)

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
            self.data_locker = DataLocker.get_instance(self.config.system_config.db_path)
            logger.info("PriceMonitor initialized with configuration.")
        except Exception as e:
            logger.error(f"Failed to initialize DataLocker: {e}")
            raise

    async def get_previous_prices(self) -> Dict[str, float]:
        """
        If you have a data_locker method for reading existing prices, call it here.
        Otherwise, this method can simply return an empty dict or your last-known prices.
        """
        try:
            # Example: if you have data_locker.get_latest_prices() returning { "BTC": 12345.67, ... }
            previous_prices = self.data_locker.get_latest_prices()
            return previous_prices
        except AttributeError:
            logger.warning("'DataLocker' object has no attribute 'get_latest_prices'. Returning empty.")
            return {}
        except Exception as e:
            logger.error(f"Error fetching previous prices: {e}")
            return {}

    async def update_prices(self):
        """
        Fetch real prices from CoinGecko for each asset in self.assets,
        then store them in the database via insert_or_update_price().
        """
        try:
            # first see what we had before
            previous_prices = await self.get_previous_prices()
            logger.debug(f"Previous prices: {previous_prices}")

            async with aiohttp.ClientSession() as session:
                # We'll build one big list of asset IDs (like "bitcoin,ethereum,solana")
                # so we can call one request to /simple/price with multiple IDs.
                cg_ids = []
                for asset in self.assets:
                    cg_id = self.coingecko_map.get(asset.upper())
                    if cg_id:
                        cg_ids.append(cg_id)
                    else:
                        logger.warning(f"No CoinGecko mapping found for asset '{asset}'. Skipping.")

                if not cg_ids:
                    logger.error("No valid CoinGecko asset IDs found in config.assets. Nothing to update.")
                    return

                # Construct the API URL
                # e.g. https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd
                url = "https://api.coingecko.com/api/v3/simple/price"
                params = {
                    "ids": ",".join(cg_ids),
                    "vs_currencies": self.currency.lower(),
                    "include_last_updated_at": "true"
                }

                logger.info(f"Fetching CoinGecko prices for IDs={params['ids']}, currency={self.currency}")
                async with session.get(url, params=params, timeout=15) as resp:
                    resp.raise_for_status()  # raise exception if not 200
                    data = await resp.json()

                # Example data looks like:
                # {
                #   "bitcoin": {"usd": 27342, "last_updated_at": 1674049532},
                #   "ethereum": {"usd": 1852, "last_updated_at": 1674049532}
                #   ...
                # }
                for asset in self.assets:
                    cg_id = self.coingecko_map.get(asset.upper())
                    if not cg_id or cg_id not in data:
                        logger.warning(f"No data returned for asset '{asset}' (CG id={cg_id}). Skipping.")
                        continue

                    # e.g. data["bitcoin"]["usd"]
                    new_price = data[cg_id].get(self.currency.lower())
                    if new_price is None:
                        logger.warning(f"No price found in data for {asset}, skipping.")
                        continue

                    # Insert or update DB
                    self.data_locker.insert_or_update_price(asset, float(new_price), "CoinGecko")

                    logger.info(f"Updated {asset} price to {new_price} {self.currency} (CoinGecko).")

            logger.info("Prices updated successfully from CoinGecko.")

        except asyncio.TimeoutError:
            logger.error("Timed out fetching prices from CoinGecko.")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error fetching prices: {e}")
        except Exception as e:
            logger.error(f"General error updating prices: {e}")

    async def run_monitor_loop(self):
        """
        Runs update_prices() in a loop, sleeping in between
        based on config.system_config.sonic_monitor_loop_time.
        """
        while True:
            await self.update_prices()
            await asyncio.sleep(self.config.system_config.sonic_monitor_loop_time)


if __name__ == "__main__":
    monitor = PriceMonitor()
    try:
        asyncio.run(monitor.initialize_monitor())
        asyncio.run(monitor.run_monitor_loop())
    except Exception as e:
        logger.critical(f"PriceMonitor failed to start: {e}")
