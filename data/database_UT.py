# init_db.py
import os
import sqlite3

def create_fresh_db(db_path: str):
    # 1) If there's an existing DB file, rename it
    if os.path.exists(db_path):
        backup_path = db_path + ".backup"
        print(f"Found existing DB at '{db_path}'. Renaming to '{backup_path}'...")
        #os.rename(db_path, backup_path)

    # 2) Create fresh DB and make tables
    print(f"Creating new DB at '{db_path}'...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Example table creation statements:
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

    # If you also have the config_overrides table:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config_overrides (
            id INTEGER PRIMARY KEY,
            overrides TEXT
        )
    """)
    # Make sure there's a row with id=1
    cursor.execute("""
        INSERT OR IGNORE INTO config_overrides (id, overrides)
        VALUES (1, '{}')
    """)

    conn.commit()
    conn.close()
    print(f"Fresh DB created at '{db_path}'.")

if __name__ == "__main__":
    DB_PATH = "C:/WebSonic/data/mother_brain.db"
    create_fresh_db(DB_PATH)
