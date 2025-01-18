import os
import aiosqlite
import sqlite3  # If you also do some synchronous calls
import logging
import datetime
from typing import Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("DataLockerLogger")

class DataLocker:
    _instance = None

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = logger

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

        self.initialize_database_sync()

    @classmethod
    def get_instance(cls, db_path: str = "data/mother_brain.db") -> 'DataLocker':
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def initialize_database_sync(self):
        self.logger.debug(f"Initializing database (sync) at {self.db_path}")

        self.cursor.execute('''
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
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                asset_type TEXT NOT NULL,
                position_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                liquidation_price REAL NOT NULL,
                current_travel_percent REAL NOT NULL,
                value REAL NOT NULL DEFAULT 0.0,
                collateral REAL NOT NULL,
                size REAL NOT NULL,
                wallet TEXT NOT NULL DEFAULT 'Default',
                leverage REAL,
                last_updated DATETIME,
                alert_reference_id TEXT,
                hedge_buddy_id TEXT,
                current_price REAL,
                liquidation_distance REAL,
                heat_index REAL,
                current_heat_index REAL
            )
        ''')

        self.cursor.execute('''
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
        ''')
        self.conn.commit()
        self.logger.debug("Database tables ensured (sync).")

    # ----------------------------------------------------------------
    # POSITIONS
    # ----------------------------------------------------------------
    def create_position(self, position: dict):
        """
        Inserts a position into the DB. 
        - Auto-generate a UUID if `id` is missing.
        - If 'value' is missing, auto-calc from size*current_price.
        - If 'wallet' is missing, fallback to 'Default'.
        - If size or current_price <= 0, raise ValueError.
        """
        if not position.get("id"):
            position["id"] = str(uuid4())

        size = float(position.get("size", 0.0))
        current_price = float(position.get("current_price", 0.0))

        if size <= 0:
            raise ValueError(f"Refusing to create invalid position: size={size}")
        if current_price <= 0:
            raise ValueError(f"Refusing to create invalid position: current_price={current_price}")

        if "value" not in position or position["value"] is None:
            position["value"] = size * current_price

        if "wallet" not in position or not position["wallet"]:
            position["wallet"] = "Default"

        try:
            self.cursor.execute('''
                INSERT INTO positions (
                    id, asset_type, position_type, entry_price, liquidation_price,
                    current_travel_percent, value, collateral, size, wallet,
                    leverage, last_updated, current_price, liquidation_distance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                position["id"],
                position.get("asset_type"),
                position.get("position_type"),
                float(position.get("entry_price", 0.0)),
                float(position.get("liquidation_price", 0.0)),
                float(position.get("current_travel_percent", 0.0)),
                float(position["value"]),
                float(position.get("collateral", 0.0)),
                size,
                position["wallet"],
                float(position.get("leverage", 1.0)),
                position.get("last_updated") or datetime.datetime.now().isoformat(),
                current_price,
                position.get("liquidation_distance")
            ))
            self.conn.commit()
            self.logger.debug(f"Position created successfully: {position}")
        except sqlite3.IntegrityError as e:
            self.logger.error(f"IntegrityError creating position: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Error creating position: {e}", exc_info=True)

    def update_position(self, position_id: str, new_size: float = None, new_collateral: float = None):
        try:
            self.cursor.execute('''
                UPDATE positions
                SET size = ?, collateral = ?
                WHERE id = ?
            ''', (new_size, new_collateral, position_id))
            self.conn.commit()
            self.logger.debug(f"Position {position_id} updated: size={new_size}, collateral={new_collateral}")
        except Exception as e:
            self.logger.error(f"Error updating position {position_id}: {e}", exc_info=True)
            raise

    def read_positions(self) -> List[dict]:
        """
        Reads all positions from the DB. 
        If any row has an id = None or empty, we assign a UUID and update it,
        ensuring every position returned to the caller has a valid 'id'.
        """
        try:
            self.logger.debug("Reading positions from DB.")
            self.cursor.execute("SELECT rowid, * FROM positions")
            rows = self.cursor.fetchall()

            positions = []
            for row in rows:
                pos_dict = dict(row)  # Convert row to a dict
                # rowid is included so we can update that row if ID is missing
                rowid = pos_dict["rowid"]
                current_id = pos_dict.get("id")

                if not current_id:
                    # Generate a new UUID for this record
                    new_id = str(uuid4())
                    pos_dict["id"] = new_id

                    # Update the DB row in place
                    self.cursor.execute(
                        "UPDATE positions SET id=? WHERE rowid=?",
                        (new_id, rowid)
                    )
                    self.conn.commit()
                    self.logger.debug(f"Assigned new ID={new_id} to position rowid={rowid} previously had None/empty.")

                positions.append(pos_dict)

            return positions

        except Exception as e:
            self.logger.error(f"Error reading positions: {e}", exc_info=True)
            return []

    def import_portfolio_data(self, portfolio):
        if "positions" not in portfolio:
            self.logger.error("No 'positions' key in imported portfolio data.")
            return

        for pos in portfolio["positions"]:
            self.create_position(pos)

        self.logger.info("Portfolio data imported successfully.")

    # ----------------------------------------------------------------
    # PRICES
    # ----------------------------------------------------------------
    def read_prices(self) -> List[dict]:
        try:
            self.logger.debug("Reading prices from DB.")
            self.cursor.execute('SELECT * FROM prices')
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"Error reading prices: {e}", exc_info=True)
            return []

    def insert_or_update_price(self, asset_type: str, current_price: float, source: str,
                               timestamp: Optional[datetime.datetime] = None):
        if timestamp is None:
            timestamp = datetime.datetime.now()
        try:
            self.cursor.execute('''
                INSERT INTO prices (
                    asset_type, current_price, previous_price, avg_daily_swing, avg_1_hour, 
                    avg_3_hour, avg_6_hour, avg_24_hour, last_update_time, previous_update_time, source
                )
                VALUES (?, ?, 0, 0, 0, 0, 0, 0, ?, NULL, ?)
                ON CONFLICT(asset_type) DO UPDATE SET
                    previous_price = prices.current_price,
                    previous_update_time = prices.last_update_time,
                    current_price = excluded.current_price,
                    last_update_time = excluded.last_update_time,
                    source = excluded.source
            ''', (asset_type, current_price, timestamp.isoformat(), source))
            self.conn.commit()
            self.logger.debug(f"Inserted/Updated price for {asset_type} at {current_price}, source={source}")
        except Exception as e:
            self.logger.error(f"Error inserting/updating price for {asset_type}: {e}", exc_info=True)

    def create_price(self, asset_type: str, price: float, source: str, timestamp: Optional[datetime.datetime]):
        self.insert_or_update_price(asset_type, price, source, timestamp)

    # ----------------------------------------------------------------
    # Sync / Dependent Data
    # ----------------------------------------------------------------
    def sync_dependent_data(self):
        self.logger.debug("sync_dependent_data called - implement your logic here if needed.")

    def sync_calc_services(self):
        self.logger.debug("sync_calc_services called - implement your logic here if needed.")

    # ----------------------------------------------------------------
    # Closing / Cleanup
    # ----------------------------------------------------------------
    def close(self):
        if self.conn:
            self.conn.close()
            self.logger.debug("Database connection closed.")
