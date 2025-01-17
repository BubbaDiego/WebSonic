# test_price_monitor.py

import pytest
import asyncio
from data.data_locker import DataLocker
from data.config import AppConfig
from price_monitor import PriceMonitor
from datetime import datetime, timezone
import json
import os

@pytest.fixture(scope="module")
async def locker():
    locker_instance = await DataLocker.get_instance(db_path=":memory:")
    yield locker_instance
    await locker_instance.close()

@pytest.fixture(scope="module")
def config(tmp_path):
    config_data = {
        "price_config": {
            "assets": ["BTC"],
            "currency": "USD",
            "fetch_timeout": 10,
            "backoff": {
                "max_tries": 3,
                "factor": 2,
                "max_time": 30
            }
        },
        "system_config": {
            "logging_enabled": False,
            "log_level": "DEBUG",
            "console_output": False,
            "log_file": null,
            "db_path": "data/mother_brain.db",
            "price_monitor_enabled": False,
            "alert_monitor_enabled": False,
            "sonic_monitor_loop_time": 10,
            "last_price_update_time": null,
            "email_config": null
        },
        "api_config": {
            "coingecko_api_enabled": "ENABLE",
            "kucoin_api_enabled": "ENABLE",
            "coinmarketcap_api_enabled": "ENABLE",
            "coinmarketcap_api_key": "TEST_KEY",
            "binance_api_enabled": "ENABLE"
        },
        "alert_ranges": {
            "heat_index_ranges": {
                "low": 0,
                "medium": 200,
                "high": null
            },
            "collateral_ranges": {
                "low": 0,
                "medium": 1000,
                "high": null
            },
            "value_ranges": {
                "low": 0,
                "medium": 2000,
                "high": null
            },
            "size_ranges": {
                "low": 0,
                "medium": 15000,
                "high": null
            },
            "leverage_ranges": {
                "low": 0,
                "medium": 5,
                "high": null
            },
            "liquidation_distance_ranges": {
                "low": 0,
                "medium": 2,
                "high": null
            },
            "travel_percent_ranges": {
                "low": -50,
                "medium": -20,
                "high": null
            }
        }
    }
    config_file = tmp_path / "sonic_config.json"
    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=4)
    return AppConfig.load(str(config_file))

@pytest.mark.asyncio
async def test_price_monitor_initialization(locker, config):
    monitor = PriceMonitor(config_path=str(config.config_path))
    monitor.config = config
    monitor.logger = logging.getLogger("TestLogger")
    monitor.logger.addHandler(logging.NullHandler())  # Suppress logs
    monitor.data_locker = locker
    assert monitor.assets == ["BTC"]
    assert monitor.currency == "USD"
    await monitor.store_prices({"BTC": 50000.0}, "CoinGecko")
    prices = await locker.get_latest_prices()
    assert prices["BTC"] == 50000.0
