import os
import logging
import json
import sqlite3
import asyncio
import pytz
from datetime import datetime
from typing import List, Dict
from data.hybrid_config_manager import load_config_hybrid

DB_PATH = "C:/WebSonic/data/mother_brain.db"
CONFIG_PATH = "C:/WebSonic/sonic_config.json"

from flask import (
    Flask,
    Blueprint,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    flash,
    send_file
)

# Your existing imports for models, data locker, calc, etc.
from data.models import Position
from data.data_locker import DataLocker
from calc_services import CalcServices
from data.config import AppConfig
from prices.price_monitor import PriceMonitor
from alerts.alert_manager import AlertManager

app = Flask(__name__)
app.debug = False  # or True if you prefer
logger = logging.getLogger("WebAppLogger")
logger.setLevel(logging.DEBUG)

app.secret_key = "i-like-lamp"

prices_bp = Blueprint('prices_bp', __name__)

# ----------------------------------------------
#  Database path, DataLocker, AlertManager, etc.
# ----------------------------------------------
db_path = os.path.abspath("data/mother_brain.db")
DB_PATH = "data/mother_brain.db"
print(f"Using DB at: {db_path}")

# At startup:
db_conn = sqlite3.connect("C:/WebSonic/data/mother_brain.db")
config = load_config_hybrid("sonic_config.json", db_conn)
data_locker = DataLocker(db_path=db_path)
calc_services = CalcServices()

alert_manager = AlertManager(
    db_path="C:/WebSonic/data/mother_brain.db",
    poll_interval=60,
    config_path="sonic_config.json"
)

# --------------------------------------------------
# Root route -> Redirect to /positions
# --------------------------------------------------
#@app.route("/")
#def index():
    #"""
    #The main root path: we redirect to /positions,
  #  so the app doesn't start on the audio page by default.
  #  """
  #  logger.debug("Reached / (root). Redirecting to /positions.")
  #  return redirect(url_for("positions"))


##############################
#   Index redirect, etc.
##############################
@app.route("/")
def index():
    return redirect(url_for("prices"))


# --------------------------------------------------
# Positions
# --------------------------------------------------
@app.route("/positions")
def positions():
    logger.debug("Entered /positions route.")
    if request.method == "POST":
        # For example, handle form submissions to create/edit positions
        return redirect(url_for("positions"))

    # GET => fetch from DB
    positions_data = data_locker.get_positions()  # returns List[Position]
    prices_data = data_locker.get_prices()        # returns List[Price]

    logger.debug(f"Fetched {len(positions_data)} positions, {len(prices_data)} prices.")

    price_map = {pr.asset_type.value: pr.current_price for pr in prices_data}
    totals = aggregate_positions(positions_data)

    return render_template(
        "positions.html",
        positions=positions_data,
        price_map=price_map,
        totals=totals
    )

def aggregate_positions(positions: List[Position]) -> Dict[str, float]:
    total_collateral = 0.0
    total_value = 0.0
    total_size = 0.0

    for pos in positions:
        total_collateral += pos.collateral
        total_value += pos.value
        total_size += pos.size

    return {
        "total_collateral": total_collateral,
        "total_value": total_value,
        "total_size": total_size
    }

def reset_api_counters_in_db():
    """
    Example function that sets 'total_reports' to 0 in a table named 'api_status_counters'.
    Modify to match your actual DB schema or config file approach.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE api_status_counters SET total_reports = 0")
    conn.commit()
    conn.close()

def load_app_config():
    """
    Straightforward approach: load JSON from disk, parse into Pydantic model.
    """
    if not os.path.exists(CONFIG_PATH):
        # If no file, create an empty default or raise an error
        return AppConfig()  # or some default
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return AppConfig(**data)

def save_app_config(config: AppConfig):
    """
    Save updated config back to 'sonic_config.json'.
    """
    data = config.model_dump()  # Pydantic v2+ approach
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

@app.route("/edit-position/<position_id>", methods=["POST"])
def edit_position(position_id):
    logger.debug(f"Editing position {position_id}.")
    try:
        size = float(request.form.get("size", 0.0))
        collateral = float(request.form.get("collateral", 0.0))
        data_locker.update_position(position_id, new_size=size, new_collateral=collateral)
        data_locker.sync_dependent_data()
        data_locker.sync_calc_services()
        return redirect(url_for("positions"))
    except Exception as e:
        logger.error(f"Error updating position {position_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/delete-position/<position_id>", methods=["POST"])
def delete_position(position_id):
    logger.debug(f"Deleting position {position_id}")
    try:
        data_locker.cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        data_locker.conn.commit()
        return redirect(url_for("positions"))
    except Exception as e:
        logger.error(f"Error deleting position {position_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/delete-all-positions", methods=["POST"])
def delete_all_positions():
    """
    Delete ALL positions from the DB
    """
    logger.debug("Deleting ALL positions")
    try:
        data_locker.cursor.execute("DELETE FROM positions")
        data_locker.conn.commit()
        return redirect(url_for("positions"))
    except Exception as e:
        logger.error(f"Error deleting all positions: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# Upload route is repeated in your code, so we keep just one version:
@app.route("/upload-positions", methods=["POST"])
def upload_positions():
    """
    Accept JSON (or .txt with JSON) -> auto-calc fields -> insert
    """
    logger.debug("upload_positions route triggered.")
    try:
        if 'file' not in request.files:
            logger.error("No file part in request.")
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']
        if not file or file.filename == '':
            logger.error("File is blank.")
            return jsonify({"error": "No file selected"}), 400

        logger.debug(f"Received file: {file.filename}")
        json_data = json.load(file)
        if not isinstance(json_data, list):
            logger.error("Uploaded JSON must be a list of positions.")
            return jsonify({"error": "JSON is not a list"}), 400

        inserted_count = 0
        for item in json_data:
            prepped_list = calc_services.prepare_positions_for_display([item])
            prepped_item = prepped_list[0]

            asset_type = prepped_item.get("asset_type", "BTC")
            position_type = prepped_item.get("position_type", "Long")
            collateral = float(prepped_item.get("collateral", 0.0))
            size = float(prepped_item.get("size", 0.0))
            entry_price = float(prepped_item.get("entry_price", 0.0))
            liquidation_price = float(prepped_item.get("liquidation_price", 0.0))
            current_travel_percent = float(prepped_item.get("current_travel_percent", 0.0))
            heat_index = float(prepped_item.get("heat_index", 0.0))

            data_locker.cursor.execute("""
                INSERT INTO positions
                (asset_type, position_type, collateral, size, entry_price, liquidation_price,
                 current_travel_percent, heat_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                asset_type, position_type, collateral, size, entry_price, liquidation_price,
                current_travel_percent, heat_index
            ))
            inserted_count += 1

        data_locker.conn.commit()
        logger.debug(f"Positions uploaded successfully. Inserted {inserted_count} rows.")
        return jsonify({"success": True, "inserted": inserted_count}), 200

    except Exception as e:
        logger.error(f"Error uploading positions: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# --------------------------------------------------
# Prices (Blueprint and main route)
# --------------------------------------------------
@prices_bp.route("/prices", methods=["GET", "POST"])
def show_prices():
    data_locker = DataLocker.get_instance(db_path=DB_PATH)

    if request.method == "POST":
        asset = request.form.get("asset", "BTC")
        price_val = float(request.form.get("price", 0.0))
        data_locker.insert_or_update_price(asset, price_val, source="Manual", timestamp=datetime.now())
        return redirect(url_for('prices_bp.show_prices'))

    prices_data = data_locker.read_prices()
    prices_data_sorted = sorted(
        prices_data,
        key=lambda p: p["last_update_time"] or datetime.min,
        reverse=True
    )

    import pytz
    pst_tz = pytz.timezone("US/Pacific")
    for row in prices_data_sorted:
        raw_dt = row.get("last_update_time")
        if raw_dt:
            try:
                dt_obj = datetime.fromisoformat(raw_dt)
                dt_pst = dt_obj.astimezone(pst_tz)
                row["last_update_time_pst"] = dt_pst.strftime("%Y-%m-%d %H:%M:%S %Z")
            except:
                row["last_update_time_pst"] = raw_dt

    return render_template(
        "prices.html",
        prices=prices_data_sorted[:3],
        recent_prices=prices_data_sorted
    )

def aggregator_positions(partial):
    structure = {
        "totals": {
            "long": {"collateral": 0.0, "value": 0.0, "size": 0.0}
        }
    }
    structure["totals"]["long"]["collateral"] = (
        partial["BTC_long"]["collateral"]
        + partial["ETH_long"]["collateral"]
        + partial["SOL_long"]["collateral"]
    )
    structure["totals"]["long"]["value"] = (
        partial["BTC_long"]["value"]
        + partial["ETH_long"]["value"]
        + partial["SOL_long"]["value"]
    )
    structure["totals"]["long"]["size"] = (
        partial["BTC_long"]["size"]
        + partial["ETH_long"]["size"]
        + partial["SOL_long"]["size"]
    )
    return structure

def get_latest_prices_from_db():
    # Query each asset for the newest row
    # Make sure to include last_update_time

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    results = []
    for asset in ["BTC", "ETH", "SOL"]:
        row = cur.execute("""
            SELECT asset_type, current_price, last_update_time
            FROM prices
            WHERE asset_type = ?
            ORDER BY last_update_time DESC
            LIMIT 1
        """, (asset,)).fetchone()
        if row:
            results.append({
               "asset_type": row["asset_type"],
               "current_price": row["current_price"],
               "last_update_time": row["last_update_time"],  # or _pst
            })
        else:
            results.append({
               "asset_type": asset,
               "current_price": 0.0,
               "last_update_time": "N/A"
            })
    return results

def get_recent_prices_from_db(limit=10):
    """
    Returns the MOST RECENT `limit` rows from prices table,
    sorted by last_update_time DESC.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT asset_type, current_price, last_update_time
        FROM prices
        ORDER BY last_update_time DESC
        LIMIT ?
        """,
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    # Convert to list of dict
    recent = []
    for r in rows:
        recent.append({
            "asset_type": r["asset_type"],
            "current_price": r["current_price"],
            "last_update_time_pst": r["last_update_time"]  # or do your PST conversion
        })
    return recent

##############################
#   /prices route
##############################
@app.route("/prices", methods=["GET", "POST"])
def prices():
    logger.debug("Entered /prices route.")

    # 1) If POST => handle the “Add New Price” form
    if request.method == "POST":
        asset = request.form.get("asset", "BTC")
        raw_price = request.form.get("price", "0.0")
        price_val = float(raw_price)

        data_locker.insert_or_update_price(
            asset_type=asset,
            current_price=price_val,
            source="Manual",
            timestamp=datetime.now()
        )
        return redirect(url_for("prices"))

    # 2) On GET => fetch your top boxes & recent logs
    # (We’ll re-use the same "top_prices" + "recent_prices" logic you had.)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # — a) Grab the newest row for BTC, ETH, SOL => "top_prices"
    wanted_assets = ["BTC", "ETH", "SOL"]
    top_prices = []
    for asset in wanted_assets:
        row = cur.execute("""
            SELECT asset_type, current_price, last_update_time
              FROM prices
             WHERE asset_type = ?
             ORDER BY last_update_time DESC
             LIMIT 1
        """, (asset,)).fetchone()
        if row:
            top_prices.append({
                "asset_type": row["asset_type"],
                "current_price": row["current_price"],
                "last_update_time_pst": row["last_update_time"]  # will convert below
            })
        else:
            top_prices.append({
                "asset_type": asset,
                "current_price": 0.0,
                "last_update_time_pst": None
            })

    # — b) Grab up to 15 most recent overall => "recent_prices"
    cur.execute("""
        SELECT asset_type, current_price, last_update_time
          FROM prices
         ORDER BY last_update_time DESC
         LIMIT 15
    """)
    recent_rows = cur.fetchall()
    conn.close()

    recent_prices = []
    for r in recent_rows:
        recent_prices.append({
            "asset_type": r["asset_type"],
            "current_price": r["current_price"],
            "last_update_time": r["last_update_time"]  # for sorting
        })

    # 3) Convert last_update_time => PST string
    pst = pytz.timezone("US/Pacific")

    def convert_to_pststr(iso_str):
        if not iso_str or iso_str == "N/A":
            return "N/A"
        try:
            dt_obj = datetime.fromisoformat(iso_str)
            dt_pst = dt_obj.astimezone(pst)
            return dt_pst.strftime("%Y-%m-%d %H:%M:%S %Z")
        except:
            return "N/A"

    # Convert top_prices
    for t in top_prices:
        iso = t["last_update_time_pst"]
        t["last_update_time_pst"] = convert_to_pststr(iso)

    # Convert recent
    for rp in recent_prices:
        rp["last_update_time_pst"] = convert_to_pststr(rp["last_update_time"])

    # 4) Load API counters
    api_counters = data_locker.read_api_counters()

    # 5) Render
    return render_template(
        "prices.html",
        prices=top_prices,         # for the top boxes
        recent_prices=recent_prices,  # for the “Recent Prices” table
        api_counters=api_counters     # for the “API Status” table
    )


##############################
#   /update-prices route
##############################
@app.route("/update-prices", methods=["POST"])
def update_prices():
    """
    Called by the 'Update Prices' button in 'prices.html'.
    We'll asynchronously fetch from Coingecko, CMC, etc.
    """
    pm = PriceMonitor(db_path=DB_PATH, config_path="C:/WebSonic/sonic_config.json")
    try:
        asyncio.run(pm.update_prices())
    except Exception as e:
        logger.exception(f"Error updating prices: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "ok", "message": "Prices updated successfully"})



# --------------------------------------------------
# Alerts
# --------------------------------------------------
@app.route("/manual-check-alerts", methods=["POST"])
def manual_check_alerts():
    try:
        alert_manager.check_alerts()
        return jsonify({"status": "success", "message":"Alerts checked."}), 200
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)}), 500


# --------------------------------------------------
# Alert / System Config
# --------------------------------------------------
@app.route("/alert-options", methods=["GET", "POST"])
def alert_options():
    config_data = AppConfig.load("sonic_config.json")
    if request.method == "POST":
        new_heat_index_low = float(request.form["heat_index_low"])
        new_heat_index_medium = float(request.form["heat_index_medium"])
        raw_heat_index_high = request.form.get("heat_index_high", "")
        new_heat_index_high = float(raw_heat_index_high) if raw_heat_index_high else None

        config_data.alert_ranges.heat_index_ranges.low = new_heat_index_low
        config_data.alert_ranges.heat_index_ranges.medium = new_heat_index_medium
        config_data.alert_ranges.heat_index_ranges.high = new_heat_index_high

        data_dict = config_data.model_dump()
        with open("sonic_config.json", "w") as f:
            json.dump(data_dict, f, indent=2)
        return redirect(url_for("alert_options"))

    return render_template("alert_options.html", config=config_data)

@app.route("/system-options", methods=["GET", "POST"])
@app.route("/system-options", methods=["GET", "POST"])
def system_options():
    """
    Displays and updates system options. If user clicks “Reset API Counters”,
    we call data_locker.reset_api_counters(). Otherwise, we save updated
    config fields to sonic_config.json.
    """
    data_locker = DataLocker(DB_PATH)  # So we can call data_locker.reset_api_counters()

    if request.method == "POST":
        # 1) Load existing config from disk (keeping your same approach)
        config = load_app_config()

        # 2) Check the form "action" param
        form_action = request.form.get("action")
        if form_action == "reset_counters":
            # If the user clicked the “Reset API Counters” button
            data_locker.reset_api_counters()  # sets total_reports=0 for each row
            flash("API report counters have been reset!", "success")
            return redirect(url_for("system_options"))

        else:
            # 3) “Save All Changes” path: parse form fields, update config
            # NOTE: You can uncomment if you want to handle logging_enabled:
            # config.system_config.logging_enabled = ("logging_enabled" in request.form)
            config.system_config.log_level = request.form.get("log_level", "INFO")
            config.system_config.db_path = request.form.get("db_path", config.system_config.db_path)
            # etc. parse all the other fields...

            # For assets:
            assets_str = request.form.get("assets", "")
            config.price_config.assets = [a.strip() for a in assets_str.split(",") if a.strip()]

            # For currency, fetch_timeout...
            config.price_config.currency = request.form.get("currency", "USD")
            config.price_config.fetch_timeout = int(request.form.get("fetch_timeout", 10))

            # For coingecko/binance enable
            config.api_config.coingecko_api_enabled = request.form.get("coingecko_api_enabled", "ENABLE")
            config.api_config.binance_api_enabled = request.form.get("binance_api_enabled", "ENABLE")

            # For coinmarketcap key
            config.api_config.coinmarketcap_api_key = request.form.get("coinmarketcap_api_key", "")

            # ... handle alert ranges, import_file, etc. if needed

            # 4) Save updated config
            save_app_config(config)

            flash("System options saved!", "success")
            return redirect(url_for("system_options"))

    # GET request: just load the config and render
    config = load_app_config()
    return render_template("system_options.html", config=config)


@app.route("/export-config")
def export_config():
    config_path = os.path.join(os.getcwd(), "sonic_config.json")
    return send_file(
        config_path,
        as_attachment=True,
        download_name="sonic_config.json",
        mimetype="application/json"
    )

# --------------------------------------------------
# Heat
# --------------------------------------------------
@app.route("/heat", methods=["GET"])
def heat():
    logger.debug("Entered /heat route.")
    try:
        positions_data = data_locker.read_positions()
        positions_data = calc_services.prepare_positions_for_display(positions_data)
        heat_data = build_heat_data(positions_data) or {}
        return render_template("heat.html", heat_data=heat_data, totals={})
    except Exception as e:
        logger.error(f"Error generating heat page: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def build_heat_data(positions):
    structure = {
        "BTC": {"short": None, "long": None},
        "ETH": {"short": None, "long": None},
        "SOL": {"short": None, "long": None},
        "totals": {
            "short": {
                "asset": "Short",
                "collateral": 0.0,
                "value": 0.0,
                "leverage": 0.0,
                "travel_percent": 0.0,
                "heat_index": 0.0,
                "size": 0.0
            },
            "long": {
                "asset": "Long",
                "collateral": 0.0,
                "value": 0.0,
                "leverage": 0.0,
                "travel_percent": 0.0,
                "heat_index": 0.0,
                "size": 0.0
            }
        }
    }
    partial = {
        "BTC_short": {"asset":"BTC","collateral":0,"value":0,"size":0,"travel_percent":0,"heat_index":0,"lev_count":0,"heat_count":0},
        "BTC_long":  {"asset":"BTC","collateral":0,"value":0,"size":0,"travel_percent":0,"heat_index":0,"lev_count":0,"heat_count":0},
        "ETH_short": {"asset":"ETH","collateral":0,"value":0,"size":0,"travel_percent":0,"heat_index":0,"lev_count":0,"heat_count":0},
        "ETH_long":  {"asset":"ETH","collateral":0,"value":0,"size":0,"travel_percent":0,"heat_index":0,"lev_count":0,"heat_count":0},
        "SOL_short": {"asset":"SOL","collateral":0,"value":0,"size":0,"travel_percent":0,"heat_index":0,"lev_count":0,"heat_count":0},
        "SOL_long":  {"asset":"SOL","collateral":0,"value":0,"size":0,"travel_percent":0,"heat_index":0,"lev_count":0,"heat_count":0},
    }

    for pos in positions:
        asset = pos.get("asset_type","BTC").upper()
        side  = pos.get("position_type","Long").lower()
        if asset not in ["BTC","ETH","SOL"]:
            continue
        key = f"{asset}_{side}"

        partial[key]["collateral"] += pos.get("collateral",0.0)
        partial[key]["value"]      += pos.get("value",0.0)
        partial[key]["size"]       += pos.get("size",0.0)
        partial[key]["travel_percent"] += pos.get("current_travel_percent",0.0)
        partial[key]["heat_index"] += pos.get("heat_index",0.0)
        partial[key]["heat_count"] += 1

    for combo in partial:
        side = "short" if "short" in combo else "long"
        a = "BTC" if "BTC" in combo else "ETH" if "ETH" in combo else "SOL"
        s_count = partial[combo]["size"]
        if s_count > 0:
            structure[a][side] = {
                "asset": a,
                "collateral": partial[combo]["collateral"],
                "value": partial[combo]["value"],
                "size": s_count,
                "travel_percent": partial[combo]["travel_percent"] / s_count * 100,
                "heat_index": partial[combo]["heat_index"] / (partial[combo]["heat_count"] or 1),
                "leverage": 0.0
            }

    structure["totals"]["short"]["collateral"] = (
        partial["BTC_short"]["collateral"]
        + partial["ETH_short"]["collateral"]
        + partial["SOL_short"]["collateral"]
    )
    structure["totals"]["short"]["value"] = (
        partial["BTC_short"]["value"]
        + partial["ETH_short"]["value"]
        + partial["SOL_short"]["value"]
    )
    structure["totals"]["short"]["size"] = (
        partial["BTC_short"]["size"]
        + partial["ETH_short"]["size"]
        + partial["SOL_short"]["size"]
    )

    structure["totals"]["long"]["collateral"] = (
        partial["BTC_long"]["collateral"]
        + partial["ETH_long"]["collateral"]
        + partial["SOL_long"]["collateral"]
    )
    structure["totals"]["long"]["value"] = (
        partial["BTC_long"]["value"]
        + partial["ETH_long"]["value"]
        + partial["SOL_long"]["value"]
    )
    structure["totals"]["long"]["size"] = (
        partial["BTC_long"]["size"]
        + partial["ETH_long"]["size"]
        + partial["SOL_long"]["size"]
    )

    return structure

# --------------------------------------------------
# Audio Tester (NEW)
# --------------------------------------------------

# ------------------------
# Audio Tester -> /audio-tester
# ------------------------
@app.route("/audio-tester")
def audio_tester():
    """
    This route renders the 'audio_tester.html' template,
    which includes your in-browser MP3 playback test card.
    """
    return render_template("audio_tester.html")

# --------------------------------------------------
# Database Viewer
# --------------------------------------------------
@app.route("/database-viewer")
def database_viewer():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all non-system table names
    cur.execute("""
        SELECT name 
        FROM sqlite_master 
        WHERE type='table' 
          AND name NOT LIKE 'sqlite_%' 
        ORDER BY name
    """)
    tables = [row["name"] for row in cur.fetchall()]

    db_data = {}
    for table in tables:
        cur.execute(f"PRAGMA table_info({table})")
        columns = [col["name"] for col in cur.fetchall()]

        cur.execute(f"SELECT * FROM {table}")
        rows_raw = cur.fetchall()
        rows = [dict(row) for row in rows_raw]

        db_data[table] = {
            "columns": columns,
            "rows": rows
        }

    conn.close()
    return render_template("database_viewer.html", db_data=db_data)

# --------------------------------------------------
# Main
# --------------------------------------------------
if __name__ == "__main__":
    # Start the Flask server
    app.run(debug=True, host="0.0.0.0", port=5000)
