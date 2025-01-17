

################################################################################
#                            🌀  data_locker.py 🌀                                   #
################################################################################
# 🦔  File Name:        data_locker.py
# ☠️  Author:           Bubbadiego
# 🌵  Description:      keep out of my mind
################################################################################

import os
import sqlite3
import random
import json
import uuid
from pytz import timezone
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from threading import local
from enum import Enum
from rich.console import Console
import logging
import subprocess
from environment_variables import load_env_variables
from flask import request, current_app
from calc_services import CalcServices


## Initialize Rich console and logger
console = Console()
logger = logging.getLogger("DataLockerLogger")
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)#CRITICAL)
handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)#CRITICAL)


# Enums for different types
class AssetType(Enum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"

class SourceType(Enum):
    AUTO = "Auto"
    MANUAL = "Manual"
    IMPORT = "Import"

class AlertType(Enum):
    PRICE_THRESHOLD = "PriceThreshold"
    DELTA_CHANGE = "DeltaChange"
    TRAVEL_PERCENT = "TravelPercent"
    TIME = "Time"

class NotificationType(Enum):
    EMAIL = "Email"
    SMS = "SMS"
    ACTION = "Action"

class Status(Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"

# Data classes
class Price:
    def __init__(
        self,
        asset_type: AssetType,
        current_price: float,
        previous_price: float,
        avg_daily_swing: float,
        avg_1_hour: float,
        avg_3_hour: float,
        avg_6_hour: float,
        avg_24_hour: float,
        last_update_time: datetime,
        previous_update_time: datetime,
        source: SourceType
    ):
        self.asset_type = asset_type
        self.current_price = current_price
        self.previous_price = previous_price
        self.avg_daily_swing = avg_daily_swing
        self.avg_1_hour = avg_1_hour
        self.avg_3_hour = avg_3_hour
        self.avg_6_hour = avg_6_hour
        self.avg_24_hour = avg_24_hour
        self.last_update_time = last_update_time
        self.previous_update_time = previous_update_time
        self.source = source

    def to_dict(self):
        return {
            "asset_type": self.asset_type.value,
            "current_price": self.current_price,
            "previous_price": self.previous_price,
            "avg_daily_swing": self.avg_daily_swing,
            "avg_1_hour": self.avg_1_hour,
            "avg_3_hour": self.avg_3_hour,
            "avg_6_hour": self.avg_6_hour,
            "avg_24_hour": self.avg_24_hour,
            "last_update_time": self.last_update_time.isoformat(),
            "previous_update_time": self.previous_update_time.isoformat() if self.previous_update_time else None,
            "source": self.source.value
        }


class Alert:
    def __init__(self, id: str, alert_type: AlertType, trigger_value: float, notification_type: NotificationType, last_triggered: Optional[datetime], status: Status, frequency: int, counter: int, liquidation_distance: float, target_travel_percent: float, liquidation_price: float, notes: Optional[str], position_reference_id: Optional[str]):
        self.id = id
        self.alert_type = alert_type
        self.trigger_value = trigger_value
        self.notification_type = notification_type
        self.last_triggered = last_triggered
        self.status = status
        self.frequency = frequency
        self.counter = counter
        self.liquidation_distance = liquidation_distance
        self.target_travel_percent = target_travel_percent
        self.liquidation_price = liquidation_price
        self.notes = notes
        self.position_reference_id = position_reference_id

    def to_dict(self):
        return {
            "id": self.id,
            "alert_type": self.alert_type.value,
            "trigger_value": self.trigger_value,
            "notification_type": self.notification_type.value,
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
            "status": self.status.value,
            "frequency": self.frequency,
            "counter": self.counter,
            "liquidation_distance": self.liquidation_distance,
            "target_travel_percent": self.target_travel_percent,
            "liquidation_price": self.liquidation_price,
            "notes": self.notes,
            "position_reference_id": self.position_reference_id
        }

class Position:
    def __init__(self, id: str, asset_type: AssetType, position_type: str, entry_price: float, liquidation_price: float, current_travel_percent: float, value: float, collateral: float, size: float, wallet: str, leverage: Optional[float], last_updated: datetime, alert_reference_id: Optional[str], hedge_buddy_id: Optional[str], current_price: Optional[float] = None, liquidation_distance: Optional[float] = None, heat_points: int = 0, current_heat_points: int = 0.0):
        self.id = id
        self.asset_type = asset_type
        self.position_type = position_type
        self.entry_price = entry_price
        self.liquidation_price = liquidation_price
        self.current_travel_percent = current_travel_percent
        self.value = value
        self.collateral = collateral
        self.size = size
        self.wallet = wallet
        self.leverage = leverage
        self.last_updated = last_updated
        self.alert_reference_id = alert_reference_id
        self.hedge_buddy_id = hedge_buddy_id
        self.current_price = current_price
        self.liquidation_distance = liquidation_distance
        self.heat_points = heat_points
        self.current_heat_points = current_heat_points

    def to_dict(self):
        return {
            "id": self.id,
            "asset_type": self.asset_type.value,
            "position_type": self.position_type,
            "entry_price": self.entry_price,
            "liquidation_price": self.liquidation_price,
            "current_travel_percent": self.current_travel_percent,
            "value": self.value,
            "collateral": self.collateral,
            "size": self.size,
            "wallet": self.wallet,
            "leverage": self.leverage,
            "last_updated": self.last_updated.isoformat(),
            "alert_reference_id": self.alert_reference_id,
            "hedge_buddy_id": self.hedge_buddy_id,
            "current_price": self.current_price,
            "liquidation_distance": self.liquidation_distance,
            "heat_points": self.heat_points,
            "current_heat_points": self.current_heat_points
        }

class DataLocker:
    _instance = None

    def __init__(self, db_path: str = None):
        # Load environment variables
        load_env_variables()

        # Resolve the database path
        db_path = r"C:\websonic\data\mother_brain.db"

        # Ensure the database path is valid
        if not db_path:
            raise ValueError("Database path cannot be None or empty.")

        self.db_path = os.path.abspath(db_path)

        # Ensure the 'data' directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        print(f"Using database at: {self.db_path}")

        # Initialize SQLite connection
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._initialize_db()

        # Set up logging
        self.local_data = local()
        self.console = Console()
        self.logger = logging.getLogger("DataLockerLogger")
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
        )
        self.logger.addHandler(handler)
        self.logger.debug("DataLocker initialized successfully")

    @staticmethod
    def get_instance():
        if DataLocker._instance is None:
            DataLocker._instance = DataLocker()
        return DataLocker._instance

    def get_connection(self):
        """Retrieve or create a thread-local SQLite connection."""
        if not hasattr(self.local_data, "connection"):
            self.local_data.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self.local_data.connection.row_factory = sqlite3.Row  # Enable dictionary-like access
        return self.local_data.connection

    def close_connection(self):
        """Close the thread-local SQLite connection."""
        if hasattr(self.local_data, "connection"):
            self.local_data.connection.close()
            del self.local_data.connection

    def _initialize_db(self):
        """
        Initializes the database tables if they do not already exist.
        """
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
                value REAL NOT NULL,
                collateral REAL NOT NULL,
                size REAL NOT NULL,
                wallet TEXT NOT NULL,
                leverage REAL NOT NULL,
                last_updated DATETIME NOT NULL,
                alert_reference_id TEXT,
                hedge_buddy_id TEXT,
                current_price REAL,
                liquidation_distance REAL,
                heat_points REAL,
                current_heat_points REAL
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

    def close(self):
        self.conn.close()
        self.logger.info("Database connection closed")

    # CRUD Operations for Prices
    def create_price(self, asset, price, source, timestamp):
        """
        Inserts or updates the price for a given asset in the database.
        If the asset already exists, it updates the price and timestamps.
        """
        query_insert = """
        INSERT INTO prices (asset_type, current_price, previous_price, avg_daily_swing, avg_1_hour, avg_3_hour,
                            avg_6_hour, avg_24_hour, last_update_time, previous_update_time, source)
        VALUES (?, ?, 0, 0, 0, 0, 0, 0, ?, NULL, ?)
        ON CONFLICT(asset_type) DO UPDATE SET
            previous_price = current_price,
            previous_update_time = last_update_time,
            current_price = excluded.current_price,
            last_update_time = excluded.last_update_time,
            source = excluded.source
        """
        try:
            iso_timestamp = timestamp.isoformat()  # Convert datetime to ISO string
            self.cursor.execute(query_insert, (asset, price, iso_timestamp, source))
            self.conn.commit()
            self.logger.debug(f"Inserted or updated price for {asset} successfully.")
        except sqlite3.Error as e:
            self.logger.error(f"Error creating price: {e}")

    def read_prices(self) -> List[Dict]:
        """
        Reads all prices from the database, including current and previous update times.
        """
        self.logger.debug("Fetching prices from the database")
        self.cursor.execute('SELECT asset_type, current_price, previous_price, avg_daily_swing, avg_1_hour, '
                            'avg_3_hour, avg_6_hour, avg_24_hour, last_update_time, previous_update_time, source FROM prices')
        rows = self.cursor.fetchall()
        self.logger.debug(f"Fetched prices: {rows}")
        return [
            {
                "asset_type": row[0],
                "current_price": row[1],
                "previous_price": row[2],
                "avg_daily_swing": row[3],
                "avg_1_hour": row[4],
                "avg_3_hour": row[5],
                "avg_6_hour": row[6],
                "avg_24_hour": row[7],
                "last_update_time": datetime.fromisoformat(row[8]) if row[8] else None,
                "previous_update_time": datetime.fromisoformat(row[9]) if row[9] else None,
                "source": row[10]
            }
            for row in rows
        ]

    def read_positions(self):
        self.logger.debug("Fetching positions from the database")
        self.cursor.execute("SELECT * FROM positions")
        rows = self.cursor.fetchall()
        valid_positions = []
        for row in rows:
            position = dict(row)
            missing_fields = [
                field for field in ["asset_type", "entry_price", "current_price", "liquidation_price"]
                if not position.get(field)
            ]
            if missing_fields:
                self.logger.warning(
                    f"Skipping position ID {position.get('id', 'unknown')}: Missing fields {missing_fields}")
            else:
                valid_positions.append(position)
        return valid_positions

    def update_price(self, price_id: int, new_price: float):
        try:
            self.cursor.execute('UPDATE prices SET current_price = ? WHERE id = ?', (new_price, price_id))
            self.conn.commit()
            self.logger.debug(f"Price updated: id={price_id}, new_price={new_price}")
        except Exception as e:
            self.logger.error(f"Error updating price: {e}", exc_info=True)

    def delete_price(self, price_id: int):
        try:
            self.cursor.execute('DELETE FROM prices WHERE id = ?', (price_id,))
            self.conn.commit()
            self.logger.debug(f"Price deleted: id={price_id}")
        except Exception as e:
            self.logger.error(f"Error deleting price: {e}", exc_info=True)

    def insert_price(self, asset, price, source, timestamp, delta_threshold=0.01):
        """
        Inserts or updates price data in the database with delta checks.
        Updates previous_price and previous_update_time before overwriting.
        """
        query_select = "SELECT current_price, last_update_time FROM prices WHERE asset_type = ?"
        query_update = """
            UPDATE prices
            SET previous_price = current_price,
                previous_update_time = last_update_time,
                current_price = ?,
                last_update_time = ?,
                source = ?
            WHERE asset_type = ?
        """
        query_insert = """
            INSERT INTO prices (asset_type, current_price, previous_price, avg_daily_swing, avg_1_hour,
                                avg_3_hour, avg_6_hour, avg_24_hour, last_update_time, previous_update_time, source)
            VALUES (?, ?, 0, 0, 0, 0, 0, 0, ?, NULL, ?)
        """

        try:
            # Fetch existing price data
            self.cursor.execute(query_select, (asset,))
            result = self.cursor.fetchone()

            if result:
                current_price, last_update_time = result
                price_delta = abs((price - current_price) / current_price) if current_price != 0 else float('inf')

                # Only update if the delta exceeds the threshold
                if price_delta > delta_threshold:
                    self.cursor.execute(query_update, (price, timestamp, source, asset))
                    self.conn.commit()
                    print(f"[DEBUG] Updated price for {asset}: {price} (Delta: {price_delta:.4f})")
                else:
                    print(f"[DEBUG] Price delta too small for {asset}. No update performed.")
            else:
                # Insert new price if the asset is not already in the database
                self.cursor.execute(query_insert, (asset, price, timestamp, source))
                self.conn.commit()
                print(f"[DEBUG] Inserted new price for {asset}: {price}")

        except sqlite3.Error as e:
            print(f"[ERROR] SQLite error during price update: {e}")

    # CRUD Operations for Alerts
    def create_alert(self, alert: Alert):
        try:
            self.cursor.execute('''
                INSERT INTO alerts (id, alert_type, trigger_value, notification_type, last_triggered, status, frequency, counter, liquidation_distance, target_travel_percent, liquidation_price, notes, position_reference_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (alert.id, alert.alert_type.value, alert.trigger_value, alert.notification_type.value,
                  alert.last_triggered.isoformat() if alert.last_triggered else None,
                  alert.status.value, alert.frequency, alert.counter, alert.liquidation_distance,
                  alert.target_travel_percent, alert.liquidation_price, alert.notes, alert.position_reference_id))
            self.conn.commit()
            self.logger.debug(f"Alert created: {alert.to_dict()}")
        except Exception as e:
            self.logger.error(f"Error creating alert: {e}", exc_info=True)

    def read_alerts(self) -> List[Dict]:
        try:
            self.cursor.execute('SELECT * FROM alerts')
            alerts = [dict(row) for row in self.cursor.fetchall()]
            self.logger.debug(f"Alerts read: {alerts}")
            return alerts
        except Exception as e:
            self.logger.error(f"Error reading alerts: {e}", exc_info=True)
            return []

    def update_alert(self, alert_id: str, new_status: Status):
        try:
            self.cursor.execute('UPDATE alerts SET status = ? WHERE id = ?', (new_status.value, alert_id))
            self.conn.commit()
            self.logger.debug(f"Alert updated: id={alert_id}, new_status={new_status.value}")
        except Exception as e:
            self.logger.error(f"Error updating alert: {e}", exc_info=True)

    def delete_alert(self, alert_id: str):
        try:
            self.cursor.execute('DELETE FROM alerts WHERE id = ?', (alert_id,))
            self.conn.commit()
            self.logger.debug(f"Alert deleted: id={alert_id}")
        except Exception as e:
            self.logger.error(f"Error deleting alert: {e}", exc_info=True)

    # CRUD Operations for Positions
    def create_position(self, position):
        """
        Adds a position to the database. Accepts a dictionary representing the position.
        """
        try:
            # Log the position dictionary directly
            self.logger.debug(f"Creating position: {position}")

            # Insert into the database
            self.cursor.execute('''
                INSERT INTO positions (id, asset_type, position_type, entry_price, liquidation_price, current_travel_percent, value, collateral, size, wallet, leverage, last_updated, current_price, liquidation_distance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                position.get("id", f"pos_{uuid.uuid4().hex[:8]}"),
                position["asset_type"],
                position["position_type"],
                position.get("entry_price", 0.0),
                position.get("liquidation_price", 0.0),
                position.get("current_travel_percent", 0.0),
                position.get("value", position["collateral"] * position["size"]),
                position["collateral"],
                position["size"],
                position.get("wallet", "Default"),
                position.get("leverage", position["size"] / position["collateral"] if position["collateral"] else 1.0),
                position.get("last_updated", datetime.now().isoformat()),
                position.get("current_price", None),
                position.get("liquidation_distance", None),
            ))
            self.conn.commit()
            self.logger.info(f"Position created successfully: {position}")
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: positions.id" in str(e):
                new_id = f"pos_{uuid.uuid4().hex[:8]}"
                self.logger.warning(f"Duplicate ID detected: {position['id']}. Generating a new ID: {new_id}")
                position["id"] = new_id
                self.create_position(position)
            else:
                self.logger.error(f"IntegrityError creating position: {e}", exc_info=True)
                raise
        except Exception as e:
            self.logger.error(f"Error creating position: {e}", exc_info=True)
            raise

    def add_position(self, position):
        """Add a new position to the database."""
        try:
            # Normalize field names
            position["asset_type"] = position.pop("asset", position.get("asset_type"))

            # Check if the asset_type already exists in the database
            self.cursor.execute('SELECT 1 FROM positions WHERE asset_type = ?', (position["asset_type"],))
            if self.cursor.fetchone():
                self.logger.info(f"Position for asset_type {position['asset_type']} already exists. Skipping.")
                return

            # Insert the new position into the database
            self.cursor.execute('''
                INSERT INTO positions (
                    asset_type, position_type, value, size, collateral, entry_price, 
                    mark_price, liquidation_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                position["asset_type"],
                position["position_type"],
                position["value"],
                position["size"],
                position["collateral"],
                position["entry_price"],
                position["mark_price"],
                position["liquidation_price"]
            ))
            self.conn.commit()
            self.logger.info(f"Position added to database: {position}")
        except sqlite3.Error as e:
            self.logger.error(f"Error adding position to database: {e}", exc_info=True)

    def read_positions(self):
        """Fetch all positions from the database in a thread-safe manner."""
        query = "SELECT * FROM positions"
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            # Rows will now be sqlite3.Row objects; convert to dict if needed
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            self.logger.error(f"SQLite error in read_positions: {e}")
            raise
        finally:
            cursor.close()

    def import_portfolio_data(self, portfolio):
        for pos in portfolio["positions"]:
            try:
                asset_type_str = pos["asset"].upper()
                if asset_type_str == "WBTC":
                    asset_type_str = "BTC"

                asset_type = AssetType[asset_type_str]
                position_type = pos["position_type"].capitalize()
                entry_price = pos["entry_price"]
                current_price = pos["mark_price"]
                liquidation_price = pos["liquidation_price"]
                size = pos["size"]
                collateral = pos["collateral"]
                value = pos["value"]

                unique_id = f"pos_{uuid.uuid4().hex[:8]}"
                leverage = size / collateral if collateral > 0 else None
                liquidation_distance = abs(current_price - liquidation_price)
                current_travel_percent = ((current_price - entry_price) / (entry_price - liquidation_price)) * 100 if (
                                                                                                                                  entry_price - liquidation_price) != 0 else 0.0

                new_position = Position(
                    id=unique_id,
                    asset_type=asset_type,
                    position_type=position_type,
                    entry_price=entry_price,
                    liquidation_price=liquidation_price,
                    current_travel_percent=current_travel_percent,
                    value=value,
                    collateral=collateral,
                    size=size,
                    wallet="Imported",
                    leverage=leverage,
                    last_updated=datetime.now(),
                    alert_reference_id=None,
                    hedge_buddy_id=None,
                    current_price=current_price,
                    liquidation_distance=liquidation_distance,
                    heat_points=pos.get("heat_points", 0),
                    current_heat_points=pos.get("current_heat_points", 0)
                )

                self.create_position(new_position)
                console.print(f"Position added: {asset_type.value} ({position_type})")
            except KeyError as e:
                console.print(f"Invalid asset type in position: {pos}")
            except Exception as e:
                console.print(f"Error processing position: {pos} -> {e}")

        console.print("Portfolio data imported successfully.")

    def update_position(self, position_id: str, new_size: float):
        try:
            self.cursor.execute('UPDATE positions SET size = ? WHERE id = ?', (new_size, position_id))
            self.conn.commit()
            self.logger.debug(f"Position updated: id={position_id}, new_size={new_size}")
        except Exception as e:
            self.logger.error(f"Error updating position: {e}", exc_info=True)

    @staticmethod
    def calculate_liquid_distance(current_price: float, liquidation_price: float) -> float:
        """
        Calculate the absolute value of the difference between the liquidation price and the current price.
        :param current_price: The current price of the asset.
        :param liquidation_price: The liquidation price of the asset.
        :return: The absolute value of the difference between the liquidation price and the current price.
        """
        return abs(liquidation_price - current_price)

    def calculate_leverage(self, size: float, collateral: float) -> Optional[float]:
        """
        Calculate leverage based on size and collateral.
        Args:
            size (float): The size of the position.
            collateral (float): The collateral for the position.
        Returns:
            Optional[float]: The calculated leverage, or None if inputs are invalid.
        """
        try:
            if size <= 0 or collateral <= 0:
                self.logger.error(f"Invalid size ({size}) or collateral ({collateral})")
                return None
            leverage = size / collateral
            return leverage
        except Exception as e:
            self.logger.error(f"Error calculating leverage: {e}", exc_info=True)
            return None

    def calculate_heat_points(self, position):
        """
        Calculate heat points for a given position.
        """
        try:
            size = position.get('size', 0)
            leverage = position.get('leverage', 0)
            collateral = position.get('collateral', 0)
            if collateral == 0:
                return None
            heat_points = (size * leverage) / collateral
            return heat_points
        except Exception as e:
            self.logger.error(f"Error calculating heat points for position {position['id']}: {e}", exc_info=True)
            return None


    def calculate_current_heat_points(self, long_position, short_position):
        """
        Calculate heat ratio for a given hedge pair.
        """
        try:
            long_heat_points = self.calculate_heat_points(long_position)
            short_heat_points = self.calculate_heat_points(short_position)
            long_travel_percent = long_position.get('current_travel_percent', 0) / 100
            short_travel_percent = short_position.get('current_travel_percent', 0) / 100

            if long_heat_points is not None and short_heat_points is not None:
                adjusted_long_heat_points = long_heat_points * (1 - long_travel_percent)
                adjusted_short_heat_points = short_heat_points * (1 - short_travel_percent)
                return adjusted_long_heat_points, adjusted_short_heat_points
            else:
                return None, None
        except Exception as e:
            self.logger.error(f"Error calculating heat ratio: {e}", exc_info=True)
            return None, None

    def calculate_value(self, position: dict) -> float:
        """
        Calculate the value of a position using CalcServices.
        """
        calc = CalcServices()
        try:
            return calc.calculate_value(position)
        except ValueError as e:
            self.logger.error(f"Error calculating value for position {position.get('id')}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error calculating value for position {position.get('id', 'unknown')}: {e}",
                              exc_info=True)
            return 0.0

    def calculate_travel_percent(self, entry_price: float, current_price: float, liquidation_price: float) -> Optional[
        float]:
        """
        Calculate the percentage of travel relative to liquidation or profit price.

        - For long positions: Negative travel percent means moving towards liquidation.
        - For short positions: Negative travel percent means moving towards liquidation.

        Args:
            entry_price (float): The price at which the position was entered.
            current_price (float): The current market price.
            liquidation_price (float): The liquidation threshold.

        Returns:
            Optional[float]: The travel percent, positive or negative, or None for errors.
        """
        try:
            denominator = abs(entry_price - liquidation_price)
            if denominator == 0:
                self.logger.error("Division by zero in calculate_travel_percent.")
                return None

            # For long positions: (current price - entry price) / (entry price - liquidation price)
            # For short positions: (entry price - current price) / (entry price - liquidation price)
            if current_price > entry_price:  # Long position scenario
                travel_percent = ((current_price - entry_price) / (entry_price - liquidation_price)) * 100
            else:  # Short position scenario
                travel_percent = ((current_price - entry_price) / (entry_price - liquidation_price)) * 100

            return travel_percent
        except Exception as e:
            self.logger.error(f"Error calculating travel percent: {e}", exc_info=True)
            return None


    def drop_tables(self):
        self.cursor.execute("DROP TABLE IF EXISTS prices")
        self.cursor.execute("DROP TABLE IF EXISTS alerts")
        self.cursor.execute("DROP TABLE IF EXISTS positions")
        self.conn.commit()

    def sync_calc_services(self):
        """
        Update all positions in the database using CalcServices for calculations.
        """
        try:
            self.cursor.execute("SELECT * FROM positions")
            positions = [dict(row) for row in self.cursor.fetchall()]

            for position in positions:
                # Skip positions with missing critical fields
                if any(position[field] is None for field in ["collateral", "size", "entry_price"]):
                    self.logger.warning(f"Skipping position with missing fields: {position}")
                    continue

                # Perform calculations
                position["value"] = position["collateral"] * position["size"]
                position["current_travel_percent"] = 0.0  # Example placeholder logic

                # Update the database
                self.cursor.execute('''
                    UPDATE positions
                    SET value = ?, current_travel_percent = ?
                    WHERE id = ?
                ''', (position["value"], position["current_travel_percent"], position["id"]))

            self.conn.commit()
        except Exception as e:
            self.logger.error(f"Error syncing calc services: {e}", exc_info=True)

    def sync_dependent_data(self):
        """
        Sync dependent data by recalculating dynamically changing fields
        (e.g., travel percent, liquidation distance, leverage, value, heat points, and heat ratio).
        This ensures the database reflects up-to-date computed values.
        """
        try:
            pacific_tz = timezone("US/Pacific")

            def convert_to_pst(dt):
                if dt:
                    return dt.astimezone(pacific_tz).strftime('%I:%M %p PST')
                return "Never"

            # Fetch all positions from the database
            self.logger.debug("Fetching positions from the database")
            positions = self.read_positions()
            prices = self.read_prices()
            price_dict = {price['asset_type']: price['current_price'] for price in prices}

            for position in positions:
                # Validate and log missing fields
                required_fields = ["asset_type", "entry_price", "current_price", "liquidation_price"]
                missing_fields = [field for field in required_fields if not position.get(field)]
                if missing_fields:
                    self.logger.warning(f"Position ID {position.get('id', 'unknown')} missing fields: {missing_fields}")
                    continue

                # Update current price using the price dictionary
                position['current_price'] = price_dict.get(position['asset_type'], 0)
                if position['current_price'] == 0:
                    self.logger.warning(f"Missing current price for asset: {position['asset_type']}")
                    continue

                self.sync_calc_services()

                # Update the database with recalculated values
                try:
                    self.cursor.execute('''
                        UPDATE positions
                        SET current_price = ?,
                            value = ?,
                            current_travel_percent = ?,
                            liquidation_distance = ?,
                            heat_points = ?,
                            last_updated = ?
                        WHERE id = ?
                    ''', (
                        position['current_price'],
                        position['value'],
                        position['current_travel_percent'],
                        position['liquidation_distance'],
                        position['heat_points'],
                        position['last_updated'],
                        position['id']
                    ))
                except sqlite3.Error as db_error:
                    self.logger.error(f"Database update failed for position ID {position.get('id', 'unknown')}: {db_error}")

            # Commit all changes to the database
            self.conn.commit()
            self.logger.info("Dependent data synced successfully.")

        except Exception as e:
            self.logger.error(f"Error syncing dependent data: {e}", exc_info=True)

    def create_random_position(self):
        try:
            position_id = f"pos_{random.randint(1000, 9999)}"
            asset_type = random.choice(list(AssetType))
            position_type = random.choice(["Long", "Short"])
            entry_price = round(random.uniform(1000.0, 50000.0), 2)
            current_price = round(random.uniform(entry_price - 5000.0, entry_price + 5000.0), 2)
            liquidation_price = round(entry_price - random.uniform(500.0, 10000.0),
                                      2) if position_type == "Long" else round(
                entry_price + random.uniform(500.0, 10000.0), 2)
            size = round(random.uniform(0.01, 10.0), 2)
            collateral = round(size * random.uniform(500.0, 2000.0), 2)
            leverage = round(size / collateral, 2) if collateral > 0 else 0.0
            wallet = f"wallet_{random.randint(100, 999)}"
            value = collateral + (size * (current_price - entry_price)) if position_type == "Long" else collateral + (
                        size * (entry_price - current_price))
            current_travel_percent = (current_price - entry_price) / (entry_price - liquidation_price) * 100 if (
                                                                                                                            entry_price - liquidation_price) != 0 else 0.0
            liquidation_distance = abs(liquidation_price - current_price)
            last_updated = datetime.now() - timedelta(minutes=random.randint(0, 1440))

            random_position = {
                "id": position_id,
                "asset_type": asset_type.value,
                "position_type": position_type,
                "entry_price": entry_price,
                "liquidation_price": liquidation_price,
                "current_price": current_price,
                "size": size,
                "collateral": collateral,
                "wallet": wallet,
                "leverage": leverage,
                "value": value,
                "current_travel_percent": current_travel_percent,
                "liquidation_distance": liquidation_distance,
                "last_updated": last_updated.isoformat(),
            }

            self.cursor.execute('''
                INSERT INTO positions (id, asset_type, position_type, entry_price, liquidation_price, current_travel_percent, value, collateral, size, wallet, leverage, last_updated, current_price, liquidation_distance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                random_position["id"],
                random_position["asset_type"],
                random_position["position_type"],
                random_position["entry_price"],
                random_position["liquidation_price"],
                random_position["current_travel_percent"],
                random_position["value"],
                random_position["collateral"],
                random_position["size"],
                random_position["wallet"],
                random_position["leverage"],
                random_position["last_updated"],
                random_position["current_price"],
                random_position["liquidation_distance"]
            ))
            self.conn.commit()
            self.logger.info(f"Random position created: {random_position}")
        except Exception as e:
            self.logger.error(f"Error creating random position: {e}", exc_info=True)

def main_menu():
    while True:

        console.print("[bold cyan]Main Menu[/bold cyan]")
        console.print("1) 📈 View Prices")
        console.print("2) 📊 View Positions")
        console.print("3) ⚠️ View Alerts")
        console.print("4) 🔄 Sync Data")
        console.print("5) 📋 View BD Tables")
        console.print("6) 🎲 Create Random Position")
        console.print("7) 🗑️ Delete")
        console.print("8) 💰 Add Prices")
        console.print("9) 📂 Import Portfolio Data")
        console.print("10) 🧪 Run Unit Tests")
        console.print("11) 🚪 Back/Exit")
        choice = console.input("Enter your choice: ")

        if choice == "1":
            locker = DataLocker()
            console.print(locker.read_prices())
        elif choice == "2":
            locker = DataLocker()
            console.print(locker.read_positions())
        elif choice == "3":
            locker = DataLocker()
            console.print(locker.read_alerts())
        elif choice == "4":
            locker = DataLocker()
            console.print("[bold cyan]🔄 Synchronizing dependent data...[/bold cyan]")
            locker.sync_dependent_data()
            console.print("[bold green]✅ Data synchronized successfully.[/bold green]")
        elif choice == "5":
            view_bd_tables()
        elif choice == "6":
            locker = DataLocker()
            console.print("[bold cyan]🎲 Creating a random position...[/bold cyan]")
            locker.create_random_position()
            console.print("[bold green]✅ Random position created successfully.[/bold green]")
        elif choice == "7":
            delete_menu()
        elif choice == "8":
            add_prices_menu()
        elif choice == "9":
            import_portfolio_data()
        elif choice == "10":
            run_unit_tests()
        elif choice == "11":
            console.print("Exiting...")
            break
        else:
            console.print("[bold red]Invalid choice, please try again.[/bold red]")


def add_prices_menu():
    locker = DataLocker()  # Ensure DataLocker is instantiated
    while True:
        print("Add Prices Menu")
        print("1) 🟡 BTC (Gold Circle)")
        print("2) 🔷 ETH (Blue Diamond)")
        print("3) 🟣 SOL (Purple Circle)")
        print("4) 🔙 Back")
        choice = input("Enter your choice: ")

        if choice == "1":
            asset = "BTC"
        elif choice == "2":
            asset = "ETH"
        elif choice == "3":
            asset = "SOL"
        elif choice == "4":
            return  # Exit the menu
        else:
            print("Invalid choice. Please try again.")
            continue

        try:
            price = float(input(f"Enter the current price for {asset}: "))
            source = "Manual Update"  # Specify the source
            timestamp = datetime.now()  # Get the current timestamp
            locker.create_price(asset, price, source, timestamp)
            print(f"✅ {asset} price added successfully!")
        except ValueError:
            print("Invalid price. Please enter a valid number.")
        except Exception as e:
            print(f"Error adding price: {e}")

def delete_menu():
    locker = DataLocker()
    while True:
        console.print("[bold cyan]Delete Menu[/bold cyan]")
        console.print("1) 🗑️ Delete All Positions")
        console.print("2) 🗑️ Delete All Alerts")
        console.print("3) 🗑️ Delete All Prices")
        console.print("4) 🗑️ Delete EVERYTHING")
        console.print("5) 🔙 Back")
        choice = console.input("Enter your choice: ")

        if choice == "1":
            locker.cursor.execute("DELETE FROM positions")
            locker.conn.commit()
            console.print("[bold green]✅ All positions deleted successfully.[/bold green]")
        elif choice == "2":
            locker.cursor.execute("DELETE FROM alerts")
            locker.conn.commit()
            console.print("[bold green]✅ All alerts deleted successfully.[/bold green]")
        elif choice == "3":
            locker.cursor.execute("DELETE FROM prices")
            locker.conn.commit()
            console.print("[bold green]✅ All prices deleted successfully.[/bold green]")
        elif choice == "4":
            locker.cursor.execute("DELETE FROM positions")
            locker.cursor.execute("DELETE FROM alerts")
            locker.cursor.execute("DELETE FROM prices")
            locker.conn.commit()
            console.print("[bold green]✅ All data deleted successfully.[/bold green]")
        elif choice == "5":
            break
        else:
            console.print("[bold red]Invalid choice, please try again.[/bold red]")


def view_bd_tables():
    locker = DataLocker()
    console.print("[bold cyan]BD Tables Submenu[/bold cyan]")
    console.print("1) Prices")
    console.print("2) Positions")
    console.print("3) Alerts")
    console.print("4) Back")
    choice = console.input("Enter your choice: ")

    if choice == "1":
        console.print(locker.read_prices())
    elif choice == "2":
        console.print(locker.read_positions())
    elif choice == "3":
        console.print(locker.read_alerts())
    elif choice == "4":
        main_menu()
    else:
        console.print("[bold red]Invalid choice, please try again.[/bold red]")
        view_bd_tables()

def bless_database():
    db_path = "mother_brain.db"
    if not os.path.exists(db_path):
        locker = DataLocker(db_path)
        console.print("[bold green]Database created and blessed![/bold green]")
        locker.close()
    else:
        console.print("[bold yellow]Database already exists.[/bold yellow]")

def test_update_price(self):
    # Create a price record
    price = Price(
        asset_type=AssetType.BTC,
        current_price=50000.0,
        previous_price=49000.0,
        avg_daily_swing=1000.0,
        avg_1_hour=500.0,
        avg_3_hour=1500.0,
        avg_6_hour=3000.0,
        avg_24_hour=4000.0,
        last_update_time=datetime.now(),
        source=SourceType.AUTO
    )
    self.locker.create_price(price)

    # Confirm price record exists
    prices = self.locker.read_prices()
    self.assertGreater(len(prices), 0, "No price records found in the database after creation.")

    # Update the price
    self.locker.update_price(prices[0]['id'], 51000.0)
    updated_prices = self.locker.read_prices()
    self.assertEqual(updated_prices[0]['current_price'], 51000.0)


def run_unit_tests():
    console.print("[bold cyan]Running Unit Tests[/bold cyan]")
    result = subprocess.run(["python", "UT_data_locker.py"], capture_output=True, text=True)
    console.print(result.stdout)
    if result.returncode != 0:
        console.print("[bold red]Unit tests failed![/bold red]")
        console.print(result.stderr)
    else:
        console.print("[bold green]All unit tests passed![/bold green]")


if __name__ == "__main__":
    # Load environment variables
    load_env_variables()

    # Initialize the DataLocker class
    locker = DataLocker()
    print(f"Database initialized at: {locker.db_path}")

    main_menu()
