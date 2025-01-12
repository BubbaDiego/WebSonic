-- Drop existing tables if they exist
DROP TABLE IF EXISTS alerts;
DROP TABLE IF EXISTS positions;
DROP TABLE IF EXISTS prices;

-- Recreate the alerts table
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
);

-- Recreate the positions table
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
);

-- Recreate the prices table
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
    previous_update_time DATETIME,  -- Added column
    source TEXT
);
