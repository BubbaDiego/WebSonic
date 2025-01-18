#!/usr/bin/env python3

"""
reset_db.py
-----------
Removes 'mother_brain.db' entirely and recreates the necessary tables
with the new schema definitions. All old data is lost.
"""

import os
import sqlite3

DB_PATH = os.path.abspath("data/mother_brain.db")

def main():
    # 1) If the DB file exists, delete it to start fresh
    if os.path.exists(DB_PATH):
        print(f"Removing old database at: {DB_PATH}")
        os.remove(DB_PATH)

    # 2) Recreate a fresh, empty DB
    print(f"Creating new database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 3) Create the tables from scratch
    #    Price table
    cursor.execute("""
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

    #    Positions table
    #    Notice 'heat_index' & 'current_heat_index' columns and 'value' has DEFAULT 0.0
    cursor.execute("""
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
            wallet TEXT NOT NULL,
            leverage REAL,
            last_updated DATETIME,
            alert_reference_id TEXT,
            hedge_buddy_id TEXT,
            current_price REAL,
            liquidation_distance REAL,
            heat_index REAL,
            current_heat_index REAL
        )
    """)

    #    Alerts table
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

    conn.commit()
    conn.close()

    print("Database was rebuilt successfully with new schema!")

if __name__ == "__main__":
    main()
