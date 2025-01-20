# prices/price_monitor.py

import asyncio
import logging
from typing import Dict, Optional, List
from data.hybrid_config_manager import load_config_hybrid
from data.data_locker import DataLocker
from prices.coingecko_fetcher import fetch_current_coingecko
from prices.coinmarketcap_fetcher import fetch_current_cmc, fetch_historical_cmc
from prices.coinpaprika_fetcher import fetch_current_coinpaprika
from prices.binance_fetcher import fetch_current_binance

logger = logging.getLogger("PriceMonitorLogger")

class PriceMonitor:
    def __init__(
        self,
        db_path="C:/WebSonic/data/mother_brain.db",
        config_path="C:/WebSonic/sonic_config.json",
    ):
        self.db_path = db_path
        self.config_path = config_path

        # 1) Setup data locker & DB
        self.data_locker = DataLocker(self.db_path)
        self.db_conn = self.data_locker.get_db_connection()

        # 2) Load final config as a pure dict
        self.config = load_config_hybrid(self.config_path, self.db_conn)

        # read config for coinpaprika/binance
        api_cfg = self.config.get("api_config", {})
        self.coinpaprika_enabled = (
            api_cfg.get("coinpaprika_api_enabled") == "ENABLE"
        )
        self.binance_enabled = (api_cfg.get("binance_api_enabled") == "ENABLE")

        # 3) Setup logging
        self.setup_logging()

        # 4) Parse relevant fields from config
        price_cfg = self.config.get("price_config", {})
        self.assets = price_cfg.get("assets", ["BTC", "ETH"])
        self.currency = price_cfg.get("currency", "USD")
        self.cmc_api_key = price_cfg.get("cmc_api_key")  # or from "api_config"

        api_cfg = self.config.get("api_config", {})
        self.coingecko_enabled = (
            api_cfg.get("coingecko_api_enabled") == "ENABLE"
        )
        self.cmc_enabled = (api_cfg.get("coinmarketcap_api_enabled") == "ENABLE")

    def setup_logging(self):
        system_cfg = self.config.get("system_config", {})
        if system_cfg.get("logging_enabled", True):
            log_level_str = system_cfg.get("log_level", "DEBUG").upper()
            log_file = system_cfg.get("log_file", "C:/WebSonic/logs/price_monitor.log")
            console_out = system_cfg.get("console_output", True)

            log_level = getattr(logging, log_level_str, logging.DEBUG)
            handlers = [logging.FileHandler(log_file)]
            if console_out:
                handlers.append(logging.StreamHandler())

            logging.basicConfig(
                level=log_level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                handlers=handlers,
            )
        else:
            logging.basicConfig(level=logging.CRITICAL)

    async def initialize_monitor(self):
        # If you need to do any additional async setup
        logger.info("PriceMonitor initialized with dictionary config.")

    async def update_prices(self):
        logger.info("Starting update_prices...")

        tasks = []
        if self.coingecko_enabled:
            tasks.append(self._fetch_and_store_coingecko())
        if self.cmc_enabled:
            tasks.append(self._fetch_and_store_cmc())
        if self.coinpaprika_enabled:
            tasks.append(self._fetch_and_store_coinpaprika())
        if self.binance_enabled:
            tasks.append(self._fetch_and_store_binance())

        if not tasks:
            logger.warning("No API sources enabled for update_prices.")
            return

        await asyncio.gather(*tasks)
        logger.info("All price updates completed.")

    async def _fetch_and_store_coingecko(self):
        """
        Actually call fetch_current_coingecko, then store results.
        We assume 'assets' are in coingecko 'slug' form or we have a map if needed.
        """
        slug_map = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            # etc...
        }
        slugs = []
        for sym in self.assets:
            if sym.upper() in slug_map:
                slugs.append(slug_map[sym.upper()])
            else:
                logger.warning(f"No slug found for {sym}, skipping.")
        if not slugs:
            return

        logger.info("Fetching Coingecko for assets: %s", slugs)
        cg_data = await fetch_current_coingecko(slugs, self.currency)

        for slug, price in cg_data.items():
            for k, v in slug_map.items():
                if v.upper() == slug.upper():
                    sym = k
                    break
            else:
                sym = slug  # fallback if not found
            self.data_locker.insert_or_update_price(sym, price, "CoinGecko")

        # **Increment the counter for "CoinGecko"**


        self.data_locker.increment_api_report_counter("CoinGecko")

    async def _fetch_and_store_coinpaprika(self):
        logger.info("Fetching CoinPaprika for assets: ...")
        paprika_map = {
            "BTC": "btc-bitcoin",
            "ETH": "eth-ethereum",
            "SOL": "sol-solana",
        }
        ids = []
        for sym in self.assets:
            if sym.upper() in paprika_map:
                ids.append(paprika_map[sym.upper()])
            else:
                logger.warning(f"No paprika ID found for {sym}, skipping.")
        if not ids:
            return

        cp_data = await fetch_current_coinpaprika(ids)
        for sym, price in cp_data.items():
            self.data_locker.insert_or_update_price(sym, price, "CoinPaprika")

        # **Increment the counter for "CoinPaprika"**
        self.data_locker.increment_api_report_counter("CoinPaprika")

    async def _fetch_and_store_binance(self):
        logger.info("Fetching Binance for assets: ...")
        binance_symbols = []
        for sym in self.assets:
            binance_symbols.append(sym.upper() + "USDT")  # naive approach
        bn_data = await fetch_current_binance(binance_symbols)
        for sym, price in bn_data.items():
            self.data_locker.insert_or_update_price(sym, price, "Binance")

        # **Increment the counter for "Binance"**
        self.data_locker.increment_api_report_counter("Binance")

    async def _fetch_and_store_cmc(self):
        logger.info("Fetching CMC for assets: %s", self.assets)
        cmc_data = await fetch_current_cmc(self.assets, self.currency, self.cmc_api_key)
        for sym, price in cmc_data.items():
            self.data_locker.insert_or_update_price(sym, price, "CoinMarketCap")

        # **Increment the counter for "CoinMarketCap"**
        self.data_locker.increment_api_report_counter("CoinMarketCap")

    async def update_historical_cmc(self, symbol: str, start_date: str, end_date: str):
        """
        For a single symbol, fetch daily OHLC from CMC over [start_date, end_date],
        then store in DB (maybe in a new 'historical_prices' table).
        """
        if not self.cmc_enabled:
            logger.warning("CoinMarketCap is not enabled, skipping historical fetch.")
            return
        logger.info(
            f"Fetching historical CMC for {symbol} from {start_date} to {end_date}..."
        )

        records = await fetch_historical_cmc(
            symbol, start_date, end_date, self.currency, self.cmc_api_key
        )
        logger.debug(f"Fetched {len(records)} daily records for {symbol} from CMC.")

        for r in records:
            self.data_locker.insert_historical_ohlc(
                symbol,
                r["time_open"],
                r["open"],
                r["high"],
                r["low"],
                r["close"],
                r["volume"],
            )

if __name__ == "__main__":
    import asyncio

    async def main():
        pm = PriceMonitor(
            db_path="C:/WebSonic/data/mother_brain.db",
            config_path="C:/WebSonic/sonic_config.json",
        )
        await pm.initialize_monitor()
        await pm.update_prices()

        # Example historical:
        start_date = "2024-12-01"
        end_date = "2025-01-19"
        await pm.update_historical_cmc("BTC", start_date, end_date)

    asyncio.run(main())
