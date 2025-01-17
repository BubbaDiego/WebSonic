# data/config.py

from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import Optional, List, Dict
import json
import os
import logging

# Configure basic logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("ConfigLoader")


class PriceConfig(BaseModel):
    assets: List[str] = Field(default_factory=lambda: ["BTC", "ETH", "LTC"])
    currency: str = "USD"
    fetch_timeout: int = 10  # seconds
    backoff: Dict[str, int] = Field(default_factory=lambda: {
        "max_tries": 5,
        "factor": 2,
        "max_time": 60
    })


class EmailConfig(BaseModel):
    sender: str = "your_email@example.com"
    recipient: str = "recipient_email@example.com"
    smtp_server: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_username: Optional[str] = "your_smtp_username"
    smtp_password: Optional[str] = "your_smtp_password"
    start_tls: bool = True


class SystemConfig(BaseModel):
    logging_enabled: bool = True
    log_level: str = "DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    console_output: bool = True
    log_file: Optional[str] = "C:\\WebSonic\\logs\\price_monitor.log"
    db_path: str = "C:\\WebSonic\\data\\mother_brain.db"
    price_monitor_enabled: bool = True
    alert_monitor_enabled: bool = True
    sonic_monitor_loop_time: int = 300  # seconds
    last_price_update_time: Optional[str] = None
    email_config: Optional[EmailConfig] = EmailConfig()


class APIConfig(BaseModel):
    coingecko_api_enabled: str = "ENABLE"  # ENABLE or DISABLE
    kucoin_api_enabled: str = "ENABLE"
    coinmarketcap_api_enabled: str = "ENABLE"
    coinmarketcap_api_key: Optional[str] = "YOUR_CMC_API_KEY"
    binance_api_enabled: str = "ENABLE"


class AlertSubRange(BaseModel):
    low: Optional[float] = 0.0
    medium: Optional[float] = 100.0
    high: Optional[float] = None  # Use None if not applicable

    @field_validator('high', mode='before')
    def validate_high(cls, v):
        if isinstance(v, list):
            logger.warning(f"Invalid type for 'high': {v}. Setting 'high' to None.")
            return None
        return v


class AlertRanges(BaseModel):
    heat_index_ranges: AlertSubRange = AlertSubRange(low=0.0, medium=200.0, high=None)
    collateral_ranges: AlertSubRange = AlertSubRange(low=0.0, medium=1000.0, high=None)
    value_ranges: AlertSubRange = AlertSubRange(low=0.0, medium=2000.0, high=None)
    size_ranges: AlertSubRange = AlertSubRange(low=0.0, medium=15000.0, high=None)
    leverage_ranges: AlertSubRange = AlertSubRange(low=0.0, medium=5.0, high=None)
    liquidation_distance_ranges: AlertSubRange = AlertSubRange(low=0.0, medium=2.0, high=None)
    travel_percent_ranges: AlertSubRange = AlertSubRange(low=-50.0, medium=-20.0, high=None)


class AppConfig(BaseModel):
    price_config: PriceConfig = PriceConfig()
    system_config: SystemConfig = SystemConfig()
    api_config: APIConfig = APIConfig()
    alert_ranges: Optional[AlertRanges] = AlertRanges()

    @classmethod
    def load(cls, config_path: str = 'sonic_config.json') -> 'AppConfig':
        """
        Loads configuration from a JSON file.

        Args:
            config_path (str): Path to the configuration JSON file.

        Returns:
            AppConfig: An instance of AppConfig populated with data from the JSON file.

        Raises:
            Exception: If loading or parsing the configuration fails.
        """
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            logger.debug("Loaded configuration data:")
            logger.debug(json.dumps(data, indent=4))
            return cls(**data)
        except FileNotFoundError:
            logger.error(f"Configuration file '{config_path}' not found. Loading default configuration.")
            return cls()
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON from '{config_path}': {e}. Loading default configuration.")
            return cls()
        except ValidationError as e:
            logger.error(f"Validation error while loading configuration: {e}. Loading default configuration.")
            return cls()
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}. Loading default configuration.")
            return cls()
