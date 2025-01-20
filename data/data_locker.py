import sqlite3
import logging
from data.models import Price, Alert, Position, AssetType, Status
from typing import List, Dict, Optional
from datetime import datetime
from uuid import uuid4
from pydantic import ValidationError

class DataLocker:
    """
    A synchronous DataLocker that manages database interactions using sqlite3.
    Stores:
      - Multiple rows in the 'prices' table (with 'id' PK, for historical data).
      - 'positions' table,
      - 'alerts' table.
    """

    _instance: Optional['DataLocker'] = None

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = logging.getLogger("DataLockerLogger")
        self.conn = None
        self.cursor = None
        self._initialize_database()

    def _initialize_database(self):
        """
        Initializes the database by creating necessary tables if they do not exist.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # PRICES TABLE
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    id TEXT PRIMARY KEY,
                    asset_type TEXT NOT NULL,
                    current_price REAL NOT NULL,
                    previous_price REAL NOT NULL DEFAULT 0.0,
                    last_update_time DATETIME NOT NULL,
                    previous_update_time DATETIME,
                    source TEXT NOT NULL
                )
            """)

            # POSITIONS TABLE
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    asset_type TEXT NOT NULL,
                    position_type TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    liquidation_price REAL NOT NULL,
                    current_travel_percent REAL NOT NULL DEFAULT 0.0,
                    value REAL NOT NULL DEFAULT 0.0,
                    collateral REAL NOT NULL,
                    size REAL NOT NULL,
                    wallet TEXT NOT NULL DEFAULT 'Default',
                    leverage REAL DEFAULT 0.0,
                    last_updated DATETIME NOT NULL,
                    alert_reference_id TEXT,
                    hedge_buddy_id TEXT,
                    current_price REAL,
                    liquidation_distance REAL,
                    heat_index REAL NOT NULL DEFAULT 0.0,
                    current_heat_index REAL NOT NULL DEFAULT 0.0
                )
            """)

            # ALERTS TABLE
            cursor.execute("""
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

            # NEW TABLE: API STATUS COUNTERS
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_status_counters (
                    api_name TEXT PRIMARY KEY,
                    total_reports INTEGER NOT NULL DEFAULT 0,
                    last_updated DATETIME
                )
            """)

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise

    @classmethod
    def get_instance(cls, db_path: str) -> 'DataLocker':
        """
        Returns a singleton-ish instance of DataLocker.
        Use this if external code calls DataLocker.get_instance(...).
        """
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    # ----------------------------------------------------------------
    # Ensure we have only ONE version of this init helper
    # ----------------------------------------------------------------
    def _init_sqlite_if_needed(self):
        """
        Ensures self.conn and self.cursor are available.
        """
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

        if self.cursor is None:
            self.cursor = self.conn.cursor()

    def get_db_connection(self) -> sqlite3.Connection:
        """
        Returns the underlying sqlite3 Connection, ensuring it's initialized first.
        """
        self._init_sqlite_if_needed()
        return self.conn

    # ----------------------------------------------------------------
    # PRICES (Multi-row, storing historical data)
    # ----------------------------------------------------------------

    def read_api_counters(self) -> List[dict]:
        """
        Returns all rows from `api_status_counters`, including last_updated.
        """
        self._init_sqlite_if_needed()
        self.cursor.execute("""
            SELECT api_name, total_reports, last_updated
              FROM api_status_counters
             ORDER BY api_name
        """)
        rows = self.cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "api_name": r["api_name"],
                "total_reports": r["total_reports"],
                "last_updated": r["last_updated"],  # might be None
            })
        return results

    def reset_api_counters(self):
        """
        Sets total_reports=0 for every row in api_status_counters.
        """
        self._init_sqlite_if_needed()
        self.cursor.execute("UPDATE api_status_counters SET total_reports = 0")
        self.conn.commit()

    def increment_api_report_counter(self, api_name: str) -> None:
        """
        Increments total_reports for the specified api_name by 1.
        Also sets last_updated to the current time.
        """
        self._init_sqlite_if_needed()

        # Check if row exists
        self.cursor.execute(
            "SELECT total_reports FROM api_status_counters WHERE api_name = ?",
            (api_name,)
        )
        row = self.cursor.fetchone()

        now_str = datetime.now().isoformat()

        old_count = row["total_reports"] if row else 0
        self.logger.debug(f"Previous total_reports for {api_name} = {old_count}")

        if row is None:
            # Insert new row
            self.cursor.execute("""
                INSERT INTO api_status_counters (api_name, total_reports, last_updated)
                VALUES (?, 1, ?)
            """, (api_name, now_str))
        else:
            # Increment existing
            self.cursor.execute("""
                UPDATE api_status_counters
                   SET total_reports = total_reports + 1,
                       last_updated = ?
                 WHERE api_name = ?
            """, (now_str, api_name))

        self.conn.commit()
        self.logger.debug(f"Incremented API report counter for {api_name}, set last_updated={now_str}.")

    def insert_price(self, price: Price):
        """
        Inserts a NEW row for this Price. We'll do a lookup for the last row (if any)
        to fill 'previous_price' and 'previous_update_time' automatically,
        unless you supply them in the Price object yourself.
        """
        try:
            price_dict = price.model_dump()

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1) Find the last row for this asset
            cursor.execute("""
                SELECT current_price, last_update_time
                  FROM prices
                 WHERE asset_type = ?
                 ORDER BY last_update_time DESC
                 LIMIT 1
            """, (price.asset_type.value,))
            last_row = cursor.fetchone()

            if last_row:
                if price_dict["previous_price"] == 0.0:
                    price_dict["previous_price"] = float(last_row["current_price"])
                if not price_dict["previous_update_time"]:
                    price_dict["previous_update_time"] = last_row["last_update_time"]
            else:
                # no prior row for this asset
                if price_dict["previous_price"] == 0.0:
                    price_dict["previous_price"] = 0.0
                if not price_dict["previous_update_time"]:
                    price_dict["previous_update_time"] = None

            # 2) Assign an id if none given
            if not price_dict.get("id"):
                price_dict["id"] = str(uuid4())

            # 3) If last_update_time is missing, set it
            if not price_dict.get("last_update_time"):
                price_dict["last_update_time"] = datetime.now()

            # Insert
            cursor.execute("""
                INSERT INTO prices (
                    id,
                    asset_type,
                    current_price,
                    previous_price,
                    last_update_time,
                    previous_update_time,
                    source
                )
                VALUES (
                    :id, :asset_type, :current_price, :previous_price,
                    :last_update_time, :previous_update_time, :source
                )
            """, {
                "id": price_dict["id"],
                "asset_type": price.asset_type.value,
                "current_price": price_dict["current_price"],
                "previous_price": price_dict["previous_price"],
                "last_update_time": price_dict["last_update_time"],
                "previous_update_time": price_dict["previous_update_time"],
                "source": price_dict["source"].value
            })
            conn.commit()
            conn.close()

            self.logger.debug(f"Inserted price row for asset={price.asset_type}, id={price_dict['id']}")

        except ValidationError as ve:
            self.logger.error(f"Price validation error: {ve.json()}")
            raise
        except sqlite3.Error as e:
            self.logger.error(f"Database error during insert_price: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in insert_price: {e}")
            raise

    def get_prices(self, asset_type: Optional[AssetType] = None) -> List[Price]:
        """
        Retrieves rows from 'prices' table. If asset_type is provided, filters by that asset.
        Returns a list of Price objects.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if asset_type:
                cursor.execute("""
                    SELECT *
                      FROM prices
                     WHERE asset_type = ?
                     ORDER BY last_update_time DESC
                """, (asset_type.value,))
            else:
                cursor.execute("""
                    SELECT *
                      FROM prices
                     ORDER BY last_update_time DESC
                """)

            rows = cursor.fetchall()
            conn.close()

            prices = []
            for row in rows:
                row_dict = dict(row)
                row_dict["asset_type"] = AssetType(row_dict["asset_type"])
                p = Price(**row_dict)
                prices.append(p)

            self.logger.debug(f"Retrieved {len(prices)} price rows.")
            return prices

        except sqlite3.Error as e:
            self.logger.error(f"Database error in get_prices: {e}", exc_info=True)
            return []
        except ValidationError as ve:
            self.logger.error(f"Price validation error in get_prices: {ve.json()}")
            return []
        except Exception as e:
            self.logger.exception(f"Unexpected error in get_prices: {e}")
            return []

    def read_prices(self, asset_type: Optional[AssetType] = None) -> List[dict]:
        """
        Legacy method returning a list of dicts, similar to older code.
        Internally calls get_prices() which returns [Price].
        """
        prices = self.get_prices(asset_type)
        return [p.model_dump() for p in prices]

    def get_latest_price(self, asset_type: AssetType) -> Optional[Price]:
        """
        Return the single most recent Price for the given asset, or None.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                  FROM prices
                 WHERE asset_type = ?
                 ORDER BY last_update_time DESC
                 LIMIT 1
            """, (asset_type.value,))
            row = cursor.fetchone()
            conn.close()

            if row:
                row_dict = dict(row)
                row_dict["asset_type"] = AssetType(row_dict["asset_type"])
                return Price(**row_dict)
            else:
                return None

        except sqlite3.Error as e:
            self.logger.error(f"Database error in get_latest_price: {e}", exc_info=True)
            return None
        except ValidationError as ve:
            self.logger.error(f"Price validation error in get_latest_price: {ve.json()}")
            return None
        except Exception as e:
            self.logger.exception(f"Unexpected error in get_latest_price: {e}")
            return None

    def delete_price(self, price_id: str):
        """ Delete a price row by its 'id'. """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM prices WHERE id = ?", (price_id,))
            conn.commit()
            conn.close()
            self.logger.debug(f"Deleted price row with ID={price_id}")
        except sqlite3.Error as e:
            self.logger.error(f"Database error in delete_price: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in delete_price: {e}")
            raise

    # ----------------------------------------------------------------
    # ALERTS CRUD
    # ----------------------------------------------------------------

    def create_alert(self, alert: Alert):
        """
        Inserts a new alert record.
        """
        try:
            alert.model_validate()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            alert_data = alert.model_dump()
            if not alert_data.get("id"):
                alert_data["id"] = str(uuid4())

            cursor.execute("""
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
            """, alert_data)
            conn.commit()
            conn.close()
            self.logger.debug(f"Created alert with ID={alert_data['id']}")

        except ValidationError as ve:
            self.logger.error(f"Alert validation error: {ve.json()}")
        except sqlite3.IntegrityError as ie:
            self.logger.error(f"IntegrityError during alert creation: {ie}", exc_info=True)
        except sqlite3.Error as e:
            self.logger.error(f"Database error in create_alert: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in create_alert: {e}")
            raise

    def get_alerts(self) -> List[Alert]:
        """ Fetch all alerts as a list of Alert objects. """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alerts")
            rows = cursor.fetchall()
            conn.close()

            alerts = []
            for row in rows:
                row_dict = dict(row)
                a = Alert(**row_dict)
                alerts.append(a)

            self.logger.debug(f"Retrieved {len(alerts)} alerts from DB.")
            return alerts

        except sqlite3.Error as e:
            self.logger.error(f"Database error in get_alerts: {e}", exc_info=True)
            return []
        except ValidationError as ve:
            self.logger.error(f"Alert validation error in get_alerts: {ve.json()}")
            return []
        except Exception as e:
            self.logger.exception(f"Unexpected error in get_alerts: {e}")
            return []

    def update_alert_status(self, alert_id: str, new_status: Status):
        """ Update the 'status' of an alert by ID. """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE alerts
                   SET status = ?
                 WHERE id = ?
            """, (new_status.value, alert_id))
            conn.commit()
            conn.close()
            self.logger.debug(f"Updated alert {alert_id} status to {new_status}")
        except sqlite3.Error as e:
            self.logger.error(f"Database error in update_alert_status: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in update_alert_status: {e}")
            raise

    def delete_alert(self, alert_id: str):
        """ Delete an alert by ID. """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
            conn.commit()
            conn.close()
            self.logger.debug(f"Deleted alert ID={alert_id}")
        except sqlite3.Error as e:
            self.logger.error(f"Database error in delete_alert: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in delete_alert: {e}")
            raise

    # ----------------------------------------------------------------
    # FINAL Insert/Update Price Method (No Duplicate)
    # ----------------------------------------------------------------
    def insert_or_update_price(self, asset_type: str, current_price: float, source: str, timestamp=None):
        """
        Link function so PriceMonitor can call data_locker.insert_or_update_price(...)
        without causing an AttributeError. We do a simple check:
          1) If there's an existing row for `asset_type`, we update current_price.
          2) Otherwise, we construct a Price object and call insert_price(...).
        """
        self._init_sqlite_if_needed()

        if timestamp is None:
            timestamp = datetime.now()

        # See if we already have a row for this asset
        self.cursor.execute("SELECT id FROM prices WHERE asset_type = ?", (asset_type,))
        row = self.cursor.fetchone()

        if row:
            # existing row => do an update
            try:
                self.logger.debug(f"Updating existing price row for {asset_type}.")
                self.cursor.execute("""
                    UPDATE prices
                    SET current_price = ?, last_update_time = ?, source = ?
                    WHERE asset_type = ?
                """, (current_price, timestamp.isoformat(), source, asset_type))
                self.conn.commit()
            except Exception as e:
                self.logger.error(f"Error updating existing price row for {asset_type}: {e}", exc_info=True)
        else:
            # no row => build a Price object & call insert_price(...)
            self.logger.debug(f"No existing row for {asset_type}; inserting new price row.")
            from data.models import Price, AssetType, SourceType

            price_obj = Price(
                asset_type=AssetType(asset_type),
                current_price=current_price,
                previous_price=0.0,
                last_update_time=timestamp,
                previous_update_time=None,
                source=SourceType(source)
            )
            self.insert_price(price_obj)

    # ----------------------------------------------------------------
    # POSITIONS CRUD
    # ----------------------------------------------------------------

    def create_position(self, position: Position):
        try:
            # No second validation needed; it's already done
            pos_data = position.model_dump()

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO positions (
                    id, asset_type, position_type,
                    entry_price, liquidation_price, current_travel_percent,
                    value, collateral, size, wallet, leverage, last_updated,
                    alert_reference_id, hedge_buddy_id, current_price,
                    liquidation_distance, heat_index, current_heat_index
                )
                VALUES (
                    :id, :asset_type, :position_type,
                    :entry_price, :liquidation_price, :current_travel_percent,
                    :value, :collateral, :size, :wallet, :leverage, :last_updated,
                    :alert_reference_id, :hedge_buddy_id, :current_price,
                    :liquidation_distance, :heat_index, :current_heat_index
                )
            """, pos_data)
            conn.commit()
            conn.close()

            self.logger.debug(f"Created position with ID={pos_data['id']}")
        except Exception as e:
            self.logger.exception(f"Unexpected error in create_position: {e}")
            raise

    def get_positions(self) -> List[Position]:
        """
        Returns all positions as a list of Position objects.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM positions")
            rows = cursor.fetchall()
            conn.close()

            positions = []
            for row in rows:
                row_dict = dict(row)
                p = Position(**row_dict)
                positions.append(p)

            self.logger.debug(f"Retrieved {len(positions)} positions.")
            return positions

        except sqlite3.Error as e:
            self.logger.error(f"Database error in get_positions: {e}", exc_info=True)
            return []
        except ValidationError as ve:
            self.logger.error(f"Position validation error: {ve.json()}")
            return []
        except Exception as e:
            self.logger.exception(f"Unexpected error in get_positions: {e}")
            return []

    def read_positions(self) -> List[dict]:
        """
        This calls `get_positions()` (returns Pydantic Position objects),
        then converts each Position to a dict.
        """
        position_objs = self.get_positions()
        results = []
        for pos_obj in position_objs:
            results.append(pos_obj.model_dump())
        return results

    # ----------------------------------------------------------------
    # NEW: If you need the raw row-based version, rename the older one:
    # ----------------------------------------------------------------
    def read_positions_raw(self) -> List[Dict]:
        """
        Fetches positions as raw dictionaries directly from SQLite (no Pydantic).
        """
        self._init_sqlite_if_needed()
        results: List[Dict] = []
        try:
            self.logger.debug("Fetching positions as raw dictionaries...")
            self.cursor.execute("SELECT * FROM positions")
            rows = self.cursor.fetchall()

            for row in rows:
                results.append(dict(row))

            self.logger.debug(f"Fetched {len(results)} positions (raw dict).")
            return results

        except Exception as e:
            self.logger.error(f"Error fetching raw dict positions: {e}", exc_info=True)
            return []

    def update_position_size(self, position_id: str, new_size: float):
        """ Update the 'size' field for a given position. """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE positions
                   SET size = ?
                 WHERE id = ?
            """, (new_size, position_id))
            conn.commit()
            conn.close()
            self.logger.debug(f"Updated size of position {position_id} to {new_size}.")

        except sqlite3.Error as e:
            self.logger.error(f"Database error in update_position_size: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in update_position_size: {e}")
            raise

    def delete_position(self, position_id: str):
        """ Delete a position by ID. """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
            conn.commit()
            conn.close()
            self.logger.debug(f"Deleted position with ID={position_id}")
        except sqlite3.Error as e:
            self.logger.error(f"Database error in delete_position: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in delete_position: {e}")
            raise
