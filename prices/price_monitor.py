import aiohttp
import asyncio
import logging
from datetime import datetime
from data.data_locker import DataLocker

class PriceMonitor:
    def __init__(self):
        self.logger = logging.getLogger("PriceMonitorLogger")
        self.logger.setLevel(logging.DEBUG)

        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)

        self.data_locker = DataLocker()
        self.logger.info("PriceMonitor initialized for headless mode.")

    async def fetch_prices_from_coingecko(self):
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": "bitcoin,ethereum,solana", "vs_currencies": "usd"}
        return await self._fetch_prices(url, params, "CoinGecko")

    async def fetch_prices_from_kucoin(self):
        url = "https://api.kucoin.com/api/v1/prices"
        return await self._fetch_prices(url, {}, "KuCoin")

    async def fetch_prices_from_coinmarketcap(self):
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
        headers = {"X-CMC_PRO_API_KEY": "your_coinmarketcap_api_key"}
        return await self._fetch_prices(url, {}, "CoinMarketCap", headers)

    async def _fetch_prices(self, url, params, source_name, headers=None):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.info(f"Prices fetched successfully from {source_name}.")
                        return data
                    else:
                        self.logger.error(f"Failed to fetch prices from {source_name}. Status: {response.status}")
                        return {}
        except Exception as e:
            self.logger.error(f"Error during {source_name} fetch: {e}", exc_info=True)
            return {}

    def parse_prices(self, source, raw_data):
        if source == "CoinGecko":
            return {
                "BTC": raw_data.get("bitcoin", {}).get("usd", 0),
                "ETH": raw_data.get("ethereum", {}).get("usd", 0),
                "SOL": raw_data.get("solana", {}).get("usd", 0),
            }
        elif source == "KuCoin":
            return {
                "BTC": float(raw_data.get("BTC", 0)),
                "ETH": float(raw_data.get("ETH", 0)),
                "SOL": float(raw_data.get("SOL", 0)),
            }
        elif source == "CoinMarketCap":
            return {item["symbol"]: item["quote"]["USD"]["price"] for item in raw_data.get("data", [])}
        else:
            self.logger.warning(f"Unknown source for parsing prices: {source}")
            return {}

    def store_prices(self, prices, source):
        try:
            for asset, price in prices.items():
                if price > 0:
                    self.data_locker.insert_price(
                        asset=asset, price=price, source=source, timestamp=datetime.now()
                    )
                    self.logger.info(f"Stored {asset} price from {source}: ${price:.2f}")
                else:
                    self.logger.warning(f"Skipping invalid price for {asset}: {price}")
        except Exception as e:
            self.logger.error(f"Error storing prices: {e}", exc_info=True)

    async def update_prices(self):
        sources = [
            ("CoinGecko", self.fetch_prices_from_coingecko),
            ("KuCoin", self.fetch_prices_from_kucoin),
            ("CoinMarketCap", self.fetch_prices_from_coinmarketcap)
        ]

        for source_name, fetch_method in sources:
            raw_data = await fetch_method()
            if raw_data:
                prices = self.parse_prices(source_name, raw_data)
                self.store_prices(prices, source_name)
            else:
                self.logger.warning(f"No data fetched from {source_name}. Skipping storage.")

if __name__ == "__main__":
    monitor = PriceMonitor()
    asyncio.run(monitor.update_prices())
