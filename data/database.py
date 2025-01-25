import aiosqlite
import logging
from models import Price, Alert, Position, AssetType, Status
from typing import List, Dict, Optional
from datetime import datetime
from uuid import uuid4
from asyncio import Lock
from pydantic import ValidationError
import asyncio

class DataLocker:
    """
    DataLocker is responsible for managing all database interactions (async version).
    It ensures a single instance (Singleton) and provides asynchronous CRUD operations.
    """
    _instance: Optional['DataLocker'] = None
    _lock: Lock = Lock()

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = logging.getLogger("DataLockerLogger")
        self.logger.debug(f"DataLocker initialized with database path: {self.db_path}")

    @classmethod
    async def get_instance(cls, db_path: str):
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls(db_path)
                await cls._instance.initialize_database()
        return cls._instance

    async def initialize_database(self):
        """
        Initializes the database by creating necessary tables if they do not exist.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS prices (
                        asset_type TEXT PRIMARY KEY,
                        current_price REAL,
                        previous_price REAL,
                        avg_daily_swing REAL,
                        avg_1_hour REAL,
                        avg_3_hour REAL,
                        avg_6_hour REAL,
                        avg_24_hour REAL,
                        last_update_time DATETIME,
                        previous_update_time DATETIME,
                        source TEXT
                    )
                """)

                await db.execute("""
                    CREATE TABLE IF NOT EXISTS positions (
                        id TEXT PRIMARY KEY,
                        asset_type TEXT NOT NULL,
                        position_type TEXT NOT NULL,
                        entry_price REAL NOT NULL,
                        liquidation_price REAL NOT NULL,
                        current_travel_percent REAL NOT NULL,
                        value REAL NOT NULL,
                        collateral REAL NOT NULL,
                        size REAL NOT NULL,
                        wallet TEXT NOT NULL,
                        leverage REAL,
                        last_updated DATETIME NOT NULL,
                        alert_reference_id TEXT,
                        hedge_buddy_id TEXT,
                        current_price REAL,
                        liquidation_distance REAL,
                        heat_index INTEGER NOT NULL,
                        current_heat_index REAL NOT NULL
                    )
                """)

                await db.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id TEXT PRIMARY KEY,
                        alert_type TEXT NOT NULL,
                        trigger_value REAL NOT NULL,
                        notification_type TEXT NOT NULL,
                        last_triggered DATETIME,
                        status TEXT NOT NULL,
                        frequency INTEGER NOT NULL,
                        counter INTEGER NOT NULL,
                        liquidation_distance REAL NOT NULL,
                        target_travel_percent REAL NOT NULL,
                        liquidation_price REAL NOT NULL,
                        notes TEXT,
                        position_reference_id TEXT
                    )
                """)
                await db.commit()
                self.logger.debug("Database initialized and tables ensured.")
        except aiosqlite.Error as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise

    # ----------------------------------------------------------------
    # CRUD for Prices
    # ----------------------------------------------------------------

    async def insert_or_update_price(self, price: Price):
        try:
            await self.validate_price(price)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO prices (
                        asset_type, current_price, previous_price, avg_daily_swing, 
                        avg_1_hour, avg_3_hour, avg_6_hour, avg_24_hour,
                        last_update_time, previous_update_time, source
                    )
                    VALUES (
                        :asset_type, :current_price, :previous_price, :avg_daily_swing,
                        :avg_1_hour, :avg_3_hour, :avg_6_hour, :avg_24_hour,
                        :last_update_time, :previous_update_time, :source
                    )
                    ON CONFLICT(asset_type) DO UPDATE SET
                        previous_price = prices.current_price,
                        previous_update_time = prices.last_update_time,
                        current_price = excluded.current_price,
                        last_update_time = excluded.last_update_time,
                        source = excluded.source
                """, price.dict())
                await db.commit()
                self.logger.debug(f"Inserted/Updated price for {price.asset_type.value} successfully.")
        except ValidationError as ve:
            self.logger.error(f"Price validation error: {ve.json()}")
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during insert/update price: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error during insert/update price: {e}")
            raise

    async def get_prices(self) -> List[Price]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM prices") as cursor:
                    rows = await cursor.fetchall()
                    prices = [Price(**dict(row)) for row in rows]
                    self.logger.debug(f"Retrieved {len(prices)} prices from the database.")
                    return prices
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during fetching prices: {e}", exc_info=True)
            return []
        except ValidationError as ve:
            self.logger.error(f"Price data validation error: {ve.json()}")
            return []
        except Exception as e:
            self.logger.exception(f"Unexpected error during fetching prices: {e}")
            return []

    async def delete_price(self, asset_type: AssetType):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM prices WHERE asset_type = ?", (asset_type.value,))
                await db.commit()
                self.logger.debug(f"Deleted price for {asset_type.value} successfully.")
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during deleting price: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error during deleting price: {e}")
            raise

    # ----------------------------------------------------------------
    # CRUD for Alerts
    # ----------------------------------------------------------------

    async def create_alert(self, alert: Alert):
        try:
            await self.validate_alert(alert)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO alerts (
                        id, alert_type, trigger_value, notification_type, last_triggered, 
                        status, frequency, counter, liquidation_distance, target_travel_percent, 
                        liquidation_price, notes, position_reference_id
                    )
                    VALUES (
                        :id, :alert_type, :trigger_value, :notification_type, :last_triggered,
                        :status, :frequency, :counter, :liquidation_distance, :target_travel_percent,
                        :liquidation_price, :notes, :position_reference_id
                    )
                """, alert.dict())
                await db.commit()
                self.logger.debug(f"Created alert with ID {alert.id} successfully.")
        except ValidationError as ve:
            self.logger.error(f"Alert validation error: {ve.json()}")
        except aiosqlite.IntegrityError as ie:
            self.logger.error(f"Integrity error during alert creation: {ie}", exc_info=True)
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during alert creation: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error during alert creation: {e}")
            raise

    async def get_alerts(self) -> List[Alert]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM alerts") as cursor:
                    rows = await cursor.fetchall()
                    alerts = [Alert(**dict(row)) for row in rows]
                    self.logger.debug(f"Retrieved {len(alerts)} alerts from the database.")
                    return alerts
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during fetching alerts: {e}", exc_info=True)
            return []
        except ValidationError as ve:
            self.logger.error(f"Alert data validation error: {ve.json()}")
            return []
        except Exception as e:
            self.logger.exception(f"Unexpected error during fetching alerts: {e}")
            return []

    async def update_alert_status(self, alert_id: str, new_status: Status):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE alerts SET status = ? WHERE id = ?", (new_status.value, alert_id))
                await db.commit()
                self.logger.debug(f"Updated status of alert ID {alert_id} to {new_status.value}.")
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during updating alert status: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error during updating alert status: {e}")
            raise

    async def delete_alert(self, alert_id: str):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
                await db.commit()
                self.logger.debug(f"Deleted alert with ID {alert_id} successfully.")
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during deleting alert: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error during deleting alert: {e}")
            raise

    # ----------------------------------------------------------------
    # CRUD for Positions
    # ----------------------------------------------------------------

    async def create_position(self, position: Position):
        """
        Inserts a new position into the database.
        If position.id is missing or empty, generate a UUID automatically.
        """
        try:
            # Convert Pydantic model to dict so we can manipulate
            pos_data = position.dict()

            # If no ID => generate one
            if not pos_data.get("id"):
                pos_data["id"] = str(uuid4())

            await self.validate_position(position)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO positions (
                        id, asset_type, position_type, entry_price, liquidation_price, 
                        current_travel_percent, value, collateral, size, wallet, leverage, 
                        last_updated, alert_reference_id, hedge_buddy_id, current_price, 
                        liquidation_distance, heat_index, current_heat_index
                    )
                    VALUES (
                        :id, :asset_type, :position_type, :entry_price, :liquidation_price,
                        :current_travel_percent, :value, :collateral, :size, :wallet, :leverage,
                        :last_updated, :alert_reference_id, :hedge_buddy_id, :current_price,
                        :liquidation_distance, :heat_index, :current_heat_index
                    )
                """, pos_data)
                await db.commit()
                self.logger.debug(f"Created position with ID {pos_data['id']} successfully.")
        except ValidationError as ve:
            self.logger.error(f"Position validation error: {ve.json()}")
        except aiosqlite.IntegrityError as ie:
            self.logger.error(f"Integrity error during position creation: {ie}", exc_info=True)
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during position creation: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error during position creation: {e}")
            raise

    async def get_positions(self) -> List[Position]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM positions") as cursor:
                    rows = await cursor.fetchall()
                    positions = [Position(**dict(row)) for row in rows]
                    self.logger.debug(f"Retrieved {len(positions)} positions from the database.")
                    return positions
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during fetching positions: {e}", exc_info=True)
            return []
        except ValidationError as ve:
            self.logger.error(f"Position data validation error: {ve.json()}")
            return []
        except Exception as e:
            self.logger.exception(f"Unexpected error during fetching positions: {e}")
            return []

    async def update_position_size(self, position_id: str, new_size: float):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE positions SET size = ? WHERE id = ?", (new_size, position_id))
                await db.commit()
                self.logger.debug(f"Updated size of position ID {position_id} to {new_size}.")
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during updating position size: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error during updating position size: {e}")
            raise

    async def delete_position(self, position_id: str):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM positions WHERE id = ?", (position_id,))
                await db.commit()
                self.logger.debug(f"Deleted position with ID {position_id} successfully.")
        except aiosqlite.Error as e:
            self.logger.error(f"Database error during deleting position: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error during deleting position: {e}")
            raise

    def read_wallets(self) -> List[dict]:
        """
        Returns all rows from `wallets` as a list of dicts.
        Each dict includes fields: name, public_address, private_address, image_path, balance.
        """
        self._init_sqlite_if_needed()
        self.cursor.execute("""SELECT * FROM wallets""")
        rows = self.cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                "name": row["name"],
                "public_address": row["public_address"],
                "private_address": row["private_address"],
                "image_path": row["image_path"],
                "balance": row["balance"]
            })
        return results

    # -------------------
    # Utility Validation
    # -------------------

    async def validate_price(self, price: Price):
        # Optional extra logic
        pass

    async def validate_alert(self, alert: Alert):
        # Optional extra logic
        pass

    async def validate_position(self, position: Position):
        # Pydantic already does basic validation on instantiation
        pass

    # -------------------
    # Bulk Insert Example
    # -------------------

    async def bulk_insert_prices(self, prices: List[Price]):
        try:
            await asyncio.gather(*(self.insert_or_update_price(price) for price in prices))
            self.logger.debug(f"Bulk inserted/updated {len(prices)} prices successfully.")
        except Exception as e:
            self.logger.exception(f"Error during bulk insert/update prices: {e}")
            raise
