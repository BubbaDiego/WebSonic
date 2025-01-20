-- 1) DROP existing tables if they exist
DROP TABLE IF EXISTS alerts;
DROP TABLE IF EXISTS positions;
DROP TABLE IF EXISTS prices;

-- 2) Recreate the alerts table (no changes if you're happy with it)
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

-- 3) Recreate the positions table with updated columns & defaults
--    - current_travel_percent and value default to 0.0
--    - wallet defaults to 'Default'
--    - leverage defaults to 0.0
--    - heat_index, current_heat_index default to 0.0
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
    leverage REAL NOT NULL DEFAULT 0.0,
    last_updated DATETIME NOT NULL,
    alert_reference_id TEXT,
    hedge_buddy_id TEXT,
    current_price REAL,
    liquidation_distance REAL,
    heat_index REAL NOT NULL DEFAULT 0.0,
    current_heat_index REAL NOT NULL DEFAULT 0.0
);

-- 4) Recreate the prices table for a multi-row history approach
--    - 'id' as the primary key instead of 'asset_type'
--    - Remove avg_1_hour, avg_3_hour, etc. 
--    - Keep 'source' (now required), 'previous_price', 'previous_update_time'
CREATE TABLE IF NOT EXISTS prices (
    id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL,
    current_price REAL NOT NULL,
    previous_price REAL NOT NULL DEFAULT 0.0,
    last_update_time DATETIME NOT NULL,
    previous_update_time DATETIME,
    source TEXT NOT NULL
);
