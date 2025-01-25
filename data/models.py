from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
from datetime import datetime
from uuid import uuid4

class AssetType(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"

class SourceType(str, Enum):
    AUTO = "Auto"
    MANUAL = "Manual"
    IMPORT = "Import"
    COINGECKO = "CoinGecko"
    COINMARKETCAP = "CoinMarketCap"
    COINPAPRIKA = "CoinPaprika"
    BINANCE = "Binance"

class Status(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"

class AlertType(str, Enum):
    PRICE_THRESHOLD = "PriceThreshold"
    DELTA_CHANGE = "DeltaChange"
    TRAVEL_PERCENT = "TravelPercent"
    TIME = "Time"

class NotificationType(str, Enum):
    EMAIL = "Email"
    SMS = "SMS"
    ACTION = "Action"


class Price(BaseModel):
    id: Optional[str] = None
    asset_type: AssetType
    current_price: float = Field(..., gt=0)
    previous_price: float = Field(0.0, ge=0)
    last_update_time: datetime
    previous_update_time: Optional[datetime]
    source: SourceType

    @field_validator('previous_update_time', mode='after')
    def check_previous_time(cls, v, info):
        if v and v > info.data.get('last_update_time'):
            raise ValueError('previous_update_time cannot be after last_update_time')
        return v


class Alert(BaseModel):
    id: str
    alert_type: AlertType
    trigger_value: float
    notification_type: NotificationType
    last_triggered: Optional[datetime]
    status: Status
    frequency: int
    counter: int
    liquidation_distance: float
    target_travel_percent: float
    liquidation_price: float
    notes: Optional[str]
    position_reference_id: Optional[str]


class Position(BaseModel):
    # Autogenerate an 'id' if not provided
    id: str = Field(default_factory=lambda: str(uuid4()))
    asset_type: AssetType
    position_type: str

    entry_price: float
    liquidation_price: float

    # Provide defaults for numeric fields
    current_travel_percent: float = 0.0
    value: float = 0.0
    collateral: float = 0.0
    size: float = 0.0
    leverage: float = 0.0

    # Provide a default for wallet
    wallet: str = "Default"

    # 'last_updated' gets set to 'now' if not passed
    last_updated: datetime = Field(default_factory=datetime.now)

    # Optional fields can default to None or a numeric default
    alert_reference_id: Optional[str] = None
    hedge_buddy_id: Optional[str] = None
    current_price: Optional[float] = 0.0
    liquidation_distance: Optional[float] = None

    # Provide defaults for heat indexes
    heat_index: float = 0.0
    current_heat_index: float = 0.0

class CryptoWallet:
    """
    Represents a crypto wallet with:
      - name:           e.g., "VaderVault"
      - public_address: a single public address (for demonstration)
      - private_address: not recommended for production usage, but okay for dev
      - image_path:     path or URL to an identifying image
      - balance:        total balance in USD (or any currency you like)
    """

    def __init__(
            self,
            name: str,
            public_address: str,
            private_address: str,
            image_path: str = "",
            balance: float = 0.0
    ):
        self.name = name
        self.public_address = public_address
        self.private_address = private_address
        self.image_path = image_path
        self.balance = balance

    def __repr__(self):
        return (
            f"CryptoWallet(name={self.name!r}, "
            f"public_address={self.public_address!r}, "
            f"private_address={self.private_address!r}, "
            f"image_path={self.image_path!r}, "
            f"balance={self.balance})"
        )

class Broker:
    def __init__(
        self,
        name: str,
        image_path: str,
        web_address: str,
        total_holding: float = 0.0
    ):
        self.name = name
        self.image_path = image_path
        self.web_address = web_address
        self.total_holding = total_holding

    def __repr__(self):
        return (
            f"Broker(name={self.name!r}, "
            f"image_path={self.image_path!r}, "
            f"web_address={self.web_address!r}, "
            f"total_holding={self.total_holding})"
        )

@field_validator('current_travel_percent', mode='after')
def validate_travel_percent(cls, v, info):
    """
    Ensures that current_travel_percent is between -11500 and 1000.
    """
    if not -11500.0 <= v <= 1000.0:
        raise ValueError('current_travel_percent must be between -11500 and 1000')
    return v
