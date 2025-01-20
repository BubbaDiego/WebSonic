import os
import logging
import json
import sqlite3
import asyncio
import pytz
from datetime import datetime
from typing import List, Dict
from data.hybrid_config_manager import load_config_hybrid


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
@app.route("/")
def index():
    """
    The main root path: we redirect to /positions,
    so the app doesn't start on the audio page by default.
    """
    logger.debug("Reached / (root). Redirecting to /positions.")
    return redirect(url_for("positions"))

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

@app.route("/prices", methods=["GET", "POST"])
def prices():
    logger.debug("Entered /prices route.")

    # 1) If a POST => handle new price
    if request.method == "POST":
        asset = request.form.get("asset", "BTC")
        price_val = float(request.form.get("price", 0.0))
        data_locker.insert_or_update_price(
            asset_type=asset,
            current_price=price_val,
            source="Manual",
            timestamp=datetime.now()  # store real time
        )
        return redirect(url_for("prices"))

    # 2) GET => read from DB
    logger.debug("Fetching prices from DB.")
    prices_data = data_locker.read_prices()

    # 3) Sort them descending by last_update_time
    def parse_dt(row):
        raw_dt = row.get("last_update_time")
        if not raw_dt:
            return datetime.min
        try:
            return datetime.fromisoformat(raw_dt)
        except:
            return datetime.min

    prices_data_sorted = sorted(prices_data, key=parse_dt, reverse=True)

    # 4) Convert to PST or local time
    pst_tz = pytz.timezone("US/Pacific")
    for row in prices_data_sorted:
        raw_dt = row.get("last_update_time")
        if raw_dt:
            try:
                dt_obj = datetime.fromisoformat(raw_dt)
                dt_pst = dt_obj.astimezone(pst_tz)
                row["last_update_time_pst"] = dt_pst.strftime("%Y-%m-%d %H:%M:%S %Z")
            except:
                row["last_update_time_pst"] = "N/A"
        else:
            row["last_update_time_pst"] = "N/A"

    # 5) Distinct newest row for BTC, ETH, SOL:
    distinct_latest = {}
    for row in prices_data_sorted:
        asset_type = row["asset_type"]
        # The first time we see an asset in descending order is the newest row
        if asset_type not in distinct_latest:
            distinct_latest[asset_type] = row

    # 6) Build top boxes in the order you want
    top_boxes = []
    for want_asset in ["BTC", "ETH", "SOL"]:
        if want_asset in distinct_latest:
            top_boxes.append(distinct_latest[want_asset])

    # 7) Render template
    return render_template(
        "prices.html",
        prices=top_boxes,              # for the 3 big boxes
        recent_prices=prices_data_sorted  # entire sorted list
    )


    distinct_latest = {}
    for row in prices_data_sorted:
        asset = row["asset_type"]
        if asset not in distinct_latest:
            distinct_latest[asset] = row

    top_boxes = []
    for want_asset in ["BTC", "ETH", "SOL"]:
        if want_asset in distinct_latest:
            top_boxes.append(distinct_latest[want_asset])

    return render_template(
        "prices.html",
        prices=top_boxes,
        recent_prices=prices_data_sorted
    )

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

@app.route("/update-prices", methods=["POST"])
def update_prices():
    logger.debug("Manual price update triggered.")
    try:
        pm = PriceMonitor()
        asyncio.run(pm.initialize_monitor())
        asyncio.run(pm.update_prices())
        logger.info("Manual price update succeeded.")
        return redirect(url_for("prices"))
    except Exception as e:
        logger.error(f"Error during manual price update: {e}", exc_info=True)
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
def system_options():
    config = AppConfig.load("sonic_config.json")

    if request.method == "POST":
        # Possibly handle config file import
        if "import_file" in request.files:
            file = request.files["import_file"]
            if file and file.filename:
                if file.filename.lower().endswith(".json"):
                    try:
                        import_data = json.load(file)
                        new_config = AppConfig(**import_data)
                        new_config.save("sonic_config.json")
                        flash("Config imported successfully!", "success")
                        return redirect(url_for("system_options"))
                    except Exception as e:
                        logger.error(f"Error importing config: {e}", exc_info=True)
                        flash(f"Error importing config: {e}", "danger")
                        return redirect(url_for("system_options"))
                else:
                    flash("Please upload a valid JSON file.", "warning")
                    return redirect(url_for("system_options"))

        config.system_config.logging_enabled = (request.form.get("logging_enabled") == "on")
        config.system_config.price_monitor_enabled = (request.form.get("price_monitor_enabled") == "on")
        config.system_config.alert_monitor_enabled = (request.form.get("alert_monitor_enabled") == "on")
        config.system_config.log_level = request.form.get("log_level", "DEBUG")
        config.system_config.db_path = request.form.get("db_path", "")
        config.system_config.log_file = request.form.get("log_file", "")
        config.system_config.last_price_update_time = request.form.get("last_price_update_time", None)

        try:
            loop_time_str = request.form.get("sonic_monitor_loop_time", "300")
            config.system_config.sonic_monitor_loop_time = int(loop_time_str)
        except ValueError:
            flash("Invalid loop time. Using default of 300.", "warning")
            config.system_config.sonic_monitor_loop_time = 300

        assets_str = request.form.get("assets", "BTC,ETH")
        config.price_config.assets = [x.strip() for x in assets_str.split(",")]
        config.price_config.currency = request.form.get("currency", "USD")

        try:
            config.price_config.fetch_timeout = int(request.form.get("fetch_timeout", "10"))
        except ValueError:
            config.price_config.fetch_timeout = 10

        config.api_config.coingecko_api_enabled = request.form.get("coingecko_api_enabled", "ENABLE")
        config.api_config.binance_api_enabled = request.form.get("binance_api_enabled", "ENABLE")
        config.api_config.coinmarketcap_api_key = request.form.get("coinmarketcap_api_key", "")

        try:
            config.alert_ranges.heat_index_ranges.low = float(request.form.get("heat_index_low", "0.0"))
            config.alert_ranges.heat_index_ranges.medium = float(request.form.get("heat_index_medium", "200.0"))
            hi_high = request.form.get("heat_index_high", "")
            config.alert_ranges.heat_index_ranges.high = float(hi_high) if hi_high else None
        except ValueError:
            pass

        config.save("sonic_config.json")
        flash("System options saved!", "success")
        return redirect(url_for("system_options"))

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
