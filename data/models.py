from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
from datetime import datetime

class AssetType(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"

class SourceType(str, Enum):
    AUTO = "Auto"
    MANUAL = "Manual"
    IMPORT = "Import"

class Status(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"

class AlertType(str, Enum):
    PRICE_THRESHOLD = "PriceThreshold"
    DELTA_CHANGE = "DeltaChange"
    TRAVEL_PERCENT = "TravelPercent"
    TIME = "Time"

class SourceType(str, Enum):
    AUTO = "Auto"
    MANUAL = "Manual"
    IMPORT = "Import"
    COINGECKO = "CoinGecko"
    COINMARKETCAP = "CoinMarketCap"
    COINPAPRIKA = "CoinPaprika"
    BINANCE = "Binance"


class NotificationType(str, Enum):
    EMAIL = "Email"
    SMS = "SMS"
    ACTION = "Action"

class Price(BaseModel):
    # Optional 'id' if you want to store the DB row's UUID or an internal ID
    id: Optional[str] = None

    asset_type: AssetType
    current_price: float = Field(..., gt=0)
    previous_price: float = Field(0.0, ge=0)
    last_update_time: datetime
    previous_update_time: Optional[datetime]
    source: SourceType

    @field_validator('previous_update_time', mode='after')
    def check_previous_time(cls, v, info):
        """
        Ensures that previous_update_time is not after last_update_time.
        """
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
    id: str
    asset_type: AssetType
    position_type: str
    entry_price: float
    liquidation_price: float
    current_travel_percent: float
    value: float
    collateral: float
    size: float
    wallet: str
    leverage: Optional[float]
    last_updated: datetime
    alert_reference_id: Optional[str]
    hedge_buddy_id: Optional[str]
    current_price: Optional[float]
    liquidation_distance: Optional[float]

    # Renamed from `heat_points` to `heat_index`
    heat_index: float
    # Renamed from `current_heat_points` to `current_heat_index`
    current_heat_index: Optional[float] = 0.0

    @field_validator('current_travel_percent', mode='after')
    def validate_travel_percent(cls, v, info):
        """
        Ensures that current_travel_percent is between -11500 and 1000.
        """
        if not -11500.0 <= v <= 1000.0:
            raise ValueError('current_travel_percent must be between -11500 and 1000')
        return v
