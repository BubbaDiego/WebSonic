import os
import logging
import json
import sqlite3
import asyncio
import pytz
from datetime import datetime
from data.data_locker import DataLocker
import requests
from typing import List, Dict
from data.models import Broker
from data.hybrid_config_manager import load_config_hybrid

#DB_PATH = "C:/WebSonic/data/mother_brain.db"
#CONFIG_PATH = "C:/WebSonic/sonic_config.json"

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
from alerts.alert_manager import AlertManagerV2

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
CONFIG_PATH = r"C:\WebSonic\sonic_config.json"
print(f"Using DB at: {db_path}")

# At startup:
db_conn = sqlite3.connect("C:/WebSonic/data/mother_brain.db")
config = load_config_hybrid("sonic_config.json", db_conn)
data_locker = DataLocker(db_path=db_path)
calc_services = CalcServices()

manager = AlertManagerV2(
    db_path=r"C:\WebSonic\data\mother_brain.db",
    poll_interval=60,
    config_path="sonic_config.json"
)


MINT_TO_ASSET = {
    # Example addresses. You might have different ones in Jupiter:
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "BTC",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "ETH",
    "So11111111111111111111111111111111111111112": "SOL"
    # Add more if needed
}


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
    return redirect(url_for("positions"))


# --------------------------------------------------
# Positions
# --------------------------------------------------


def aggregator_positions_dict(positions: List[dict]) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    total_collateral = 0.0
    total_value = 0.0
    total_size = 0.0

    for pos in positions:
        # Overwrite old field
        new_val = pos.get("calculate_travel_percent", 0.0)
        pos["current_travel_percent"] = new_val

        # Update the DB
        cursor.execute("""
            UPDATE positions
               SET current_travel_percent = ?
             WHERE id = ?
        """, (new_val, pos["id"]))

        total_collateral += pos.get("collateral", 0.0)
        total_value      += pos.get("value", 0.0)
        total_size       += pos.get("size", 0.0)

    conn.commit()
    conn.close()

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

        # Now only two arguments
        data_locker.update_position(position_id, size, collateral)

       # data_locker.sync_dependent_data()
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
    Accepts a file upload (JSON or TXT) containing an array of positions,
    each with optional "wallet_name". We'll map "wallet_name" -> "wallet"
    before storing it in the DB.
    """
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file part in request"}), 400

        file = request.files["file"]
        if not file:
            return jsonify({"error": "Empty file"}), 400

        file_contents = file.read().decode("utf-8").strip()
        if not file_contents:
            return jsonify({"error": "Uploaded file is empty"}), 400

        # Parse JSON => list of positions
        positions_list = json.loads(file_contents)
        if not isinstance(positions_list, list):
            return jsonify({"error": "Top-level JSON must be a list"}), 400

        for pos_dict in positions_list:
            # If your JSON has "wallet_name", copy it into "wallet"
            if "wallet_name" in pos_dict:
                pos_dict["wallet"] = pos_dict["wallet_name"]
                # optional: del pos_dict["wallet_name"] if you don't want it lying around

            # Create the position in DB
            data_locker.create_position(pos_dict)

        return jsonify({"message": "Positions uploaded successfully"}), 200

    except Exception as e:
        app.logger.error(f"Error uploading positions: {e}", exc_info=True)
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


@app.route("/positions")
def positions():
    """
    Displays positions in a table, ensuring 'collateral' is always numeric
    and the totals row has the 'collateral' field as well.
    """
    # 1) Read raw positions from DB
    positions_data = data_locker.read_positions()

    # 2) Fill them with newest price if missing
    positions_data = fill_positions_with_latest_price(positions_data)

    # 3) Enrich each position (PnL, leverage, etc.) via aggregator
    updated_positions = calc_services.aggregator_positions(positions_data, DB_PATH)

    # 4) Attach each wallet (optional, only if you have wallet logic)
    for pos in updated_positions:
        # Ensure collateral is always a float, defaulting to 0.0 if missing/None
        pos["collateral"] = float(pos.get("collateral") or 0.0)

        wallet_name = pos.get("wallet_name")
        if wallet_name:
            w = data_locker.get_wallet_by_name(wallet_name)
            pos["wallet_name"] = w
        else:
            pos["wallet_name"] = None

    # 5) Compute overall totals
    totals_dict = calc_services.calculate_totals(updated_positions)

    # 7) Render template
    return render_template(
        "positions.html",
        positions=updated_positions,
        totals=totals_dict
    )

@app.route("/exchanges")
def exchanges():
    # If you have a DB approach:
    brokers_data = data_locker.read_brokers()

    return render_template("exchanges.html", brokers=brokers_data)

def aggregator_positions_dict(positions: List[dict]) -> dict:
    total_collateral = 0.0
    total_value = 0.0
    total_size = 0.0
    for pos in positions:
        total_collateral += pos.get("collateral", 0.0)
        total_value      += pos.get("value", 0.0)
        total_size       += pos.get("size", 0.0)

    return {
        "total_collateral": total_collateral,
        "total_value": total_value,
        "total_size": total_size
    }

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

def _convert_iso_to_pst(iso_str):
    """Converts an ISO datetime string to PST (string). Returns 'N/A' on failure."""
    if not iso_str or iso_str == "N/A":
        return "N/A"

    pst = pytz.timezone("US/Pacific")
    try:
        dt_obj = datetime.fromisoformat(iso_str)
        dt_pst = dt_obj.astimezone(pst)
        return dt_pst.strftime("%Y-%m-%d %H:%M:%S %Z")
    except:
        return "N/A"

def fill_positions_with_latest_price(positions: List[dict]) -> List[dict]:
    """
    For each position, if 'current_price' is 0 or missing,
    do a lookup from your 'prices' table to find the latest price
    for that asset_type. Then store it in pos["current_price"].
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for pos in positions:
        asset = pos.get("asset_type","BTC").upper()
        # If the position already has a non-zero current_price, skip if you want
        if pos.get("current_price", 0.0) > 0:
            continue

        # Check 'prices' for the newest row for that asset
        row = cursor.execute("""
            SELECT current_price
            FROM prices
            WHERE asset_type = ?
            ORDER BY last_update_time DESC
            LIMIT 1
        """, (asset,)).fetchone()

        if row:
            newest_price = float(row["current_price"])
            pos["current_price"] = newest_price
        else:
            # No price data => keep it at 0.0
            pos["current_price"] = 0.0

    conn.close()
    return positions

def _get_top_prices_for_assets(db_path, assets=None):
    """
    For each asset in `assets`, get the newest row from the 'prices' table.
    Return a list of dicts with keys: asset_type, current_price, last_update_time_pst
    """
    if assets is None:
        assets = ["BTC", "ETH", "SOL"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    results = []
    for asset in assets:
        row = cur.execute("""
            SELECT asset_type, current_price, last_update_time
              FROM prices
             WHERE asset_type = ?
             ORDER BY last_update_time DESC
             LIMIT 1
        """, (asset,)).fetchone()

        if row:
            # Convert last_update_time => PST
            iso = row["last_update_time"]
            results.append({
                "asset_type": row["asset_type"],
                "current_price": row["current_price"],
                "last_update_time_pst": _convert_iso_to_pst(iso)
            })
        else:
            # No data => set zero / no time
            results.append({
                "asset_type": asset,
                "current_price": 0.0,
                "last_update_time_pst": "N/A"
            })

    conn.close()
    return results

def _get_recent_prices(db_path, limit=15):
    """
    Grab up to `limit` most recent rows from 'prices'.
    Return list of dicts with asset_type, current_price, and last_update_time_pst.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(f"""
        SELECT asset_type, current_price, last_update_time
          FROM prices
         ORDER BY last_update_time DESC
         LIMIT {limit}
    """)
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        iso = r["last_update_time"]
        results.append({
            "asset_type": r["asset_type"],
            "current_price": r["current_price"],
            "last_update_time_pst": _convert_iso_to_pst(iso)
        })
    return results


@app.route("/prices", methods=["GET", "POST"])
def prices():
    logger.debug("Entered /prices route.")

    # 1) If POST => handle “Add New Price” form
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

    # 2) Build your "top prices" list (BTC/ETH/SOL) from DB
    top_prices = _get_top_prices_for_assets(DB_PATH, ["BTC", "ETH", "SOL"])

    # 3) Build "recent_prices" from DB
    recent_prices = _get_recent_prices(DB_PATH, limit=15)

    # 4) Read API counters
    api_counters = data_locker.read_api_counters()

    # 5) Render your 'prices.html'
    return render_template(
        "prices.html",
        prices=top_prices,            # top boxes
        recent_prices=recent_prices,  # “Recent Prices” table
        api_counters=api_counters     # “API Status” table
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
# Alert / System Config
# --------------------------------------------------
@app.route("/alert-options", methods=["GET", "POST"])
@app.route("/alert-options", methods=["GET", "POST"])
def alert_options():
    """
    Example route that loads config from 'sonic_config.json' with standard JSON,
    then constructs an AppConfig(...) object from it (Pydantic).
    On POST, we parse form fields, update the config, and save back to JSON.
    """
    try:
        # 1) Load JSON from disk
        with open("sonic_config.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        # 2) Parse into Pydantic model
        config_data = AppConfig(**data)

        if request.method == "POST":
            # 3) Parse form fields, update the config
            new_heat_index_low = float(request.form.get("heat_index_low", 0.0))
            new_heat_index_medium = float(request.form.get("heat_index_medium", 0.0))
            new_heat_index_high_str = request.form.get("heat_index_high", "")
            new_heat_index_high = float(new_heat_index_high_str) if new_heat_index_high_str else None

            # Example: if AppConfig has nested fields like `config_data.alert_ranges.heat_index_ranges.low`
            # we update them:
            config_data.alert_ranges.heat_index_ranges.low = new_heat_index_low
            config_data.alert_ranges.heat_index_ranges.medium = new_heat_index_medium
            config_data.alert_ranges.heat_index_ranges.high = new_heat_index_high

            # 4) Save updated config back to disk
            with open("sonic_config.json", "w", encoding="utf-8") as f:
                json.dump(config_data.model_dump(), f, indent=2)

            flash("Alert settings updated!", "success")
            return redirect(url_for("alert_options"))

        # GET -> just show the form with current config_data
        return render_template("alert_options.html", config=config_data)

    except FileNotFoundError:
        # If sonic_config.json is missing
        return jsonify({"error": "sonic_config.json not found"}), 404
    except json.JSONDecodeError:
        # If file is invalid JSON
        return jsonify({"error": "Invalid JSON in config file"}), 400
    except Exception as e:
        app.logger.error(f"Error handling /alert-options: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

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
    positions_data = data_locker.read_positions()

    # fill them with the newest price
    positions_data = fill_positions_with_latest_price(positions_data)

    # do aggregator calculations
    positions_data = calc_services.prepare_positions_for_display(positions_data)

    # build heat data
    heat_data = build_heat_data(positions_data)
    return render_template("heat.html", heat_data=heat_data)

def build_heat_data(positions: List[dict]) -> dict:
    """
    positions: a list of dicts from `data_locker.read_positions()`.
      Each dict should have keys like:
        "asset_type" -> "BTC"/"ETH"/"SOL"
        "position_type" -> "LONG" or "SHORT"
        "collateral", "value", "size", "leverage", "current_travel_percent",
        "heat_index", etc.
    Returns a nested dictionary matching the 'heat.html' template's expectations.
    """

    # Initialize the big structure
    structure = {
       "BTC":  {"short": {}, "long": {}},
       "ETH":  {"short": {}, "long": {}},
       "SOL":  {"short": {}, "long": {}},
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

    # For each position in the DB, map it into this structure
    for pos in positions:
        # e.g. pos["asset_type"] = "BTC", pos["position_type"] = "SHORT"
        asset = pos.get("asset_type", "BTC").upper()  # "BTC"/"ETH"/"SOL"
        side  = pos.get("position_type", "LONG").lower()  # "short" / "long"

        # If the position isn't one of the 3 assets or is spelled weird, skip it
        if asset not in ["BTC", "ETH", "SOL"]:
            continue
        if side not in ["short", "long"]:
            continue

        # Build the dictionary the template expects
        row = {
          "asset": asset,
          "collateral": float(pos.get("collateral", 0.0)),
          "value": float(pos.get("value", 0.0)),
          "leverage": float(pos.get("leverage", 0.0)),
          "travel_percent": float(pos.get("current_travel_percent", 0.0)),
          "heat_index": float(pos.get("heat_index", 0.0)),
          "size": float(pos.get("size", 0.0))
        }

        # Place it in structure[asset][side]
        structure[asset][side] = row

        # Also accumulate totals
        totals_side = structure["totals"][side]
        totals_side["collateral"] += row["collateral"]
        totals_side["value"]      += row["value"]
        totals_side["size"]       += row["size"]
        totals_side["travel_percent"] += row["travel_percent"]
        totals_side["heat_index"] += row["heat_index"]
        # If you want to do an *average* leverage or travel_percent, you'd
        # need to track how many positions contributed. But we’ll just sum
        # them here. It’s up to you.

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


##############################
#  Alerts Route
##############################
@app.route("/alerts")
def alerts_page():
    # Example data
    alerts_data = [
      {"alert_type": "PRICE_THRESHOLD", "trigger_value": 3000,
       "last_triggered": "2025-01-25 12:00 PST", "status": "Active"},
      # ...
    ]
    api_data = [
      {"api_name": "AlertEngine", "last_updated": "2025-01-25 11:59 PST", "total_reports": 17},
      # ...
    ]
    return render_template(
      "alerts.html",
      active_alerts_count=5,
      triggered_today_count=2,
      disabled_alerts_count=1,
      recent_alerts=alerts_data,
      api_counters=api_data
    )

@app.route("/alerts")
def alerts():
    """
    Main alerts page: displays 'alerts.html'.
    We'll pass in some mock data for demonstration.
    """
    # Example: count of different statuses
    active_count = 5
    triggered_today = 2
    disabled_count = 1

    # Example: recent alerts
    recent_alerts_data = [
        {
            "alert_type": "PRICE_THRESHOLD",
            "trigger_value": 3000,
            "last_triggered": "2025-01-25 11:00 PST",
            "status": "Active"
        },
        {
            "alert_type": "TRAVEL_PERCENT",
            "trigger_value": -25,
            "last_triggered": "2025-01-25 08:15 PST",
            "status": "Active"
        },
        {
            "alert_type": "DELTA_CHANGE",
            "trigger_value": 10,
            "last_triggered": None,
            "status": "Disabled"
        }
    ]

    # Example: API counters (similar to what you do for prices)
    api_counters = [
        {
            "api_name": "AlertEngine",
            "last_updated": "2025-01-25 10:55 PST",
            "total_reports": 13
        },
        {
            "api_name": "OtherAPI",
            "last_updated": "N/A",
            "total_reports": 0
        }
    ]

    # Render the new 'alerts.html' page
    return render_template(
        "alerts.html",
        active_alerts_count=active_count,
        triggered_today_count=triggered_today,
        disabled_alerts_count=disabled_count,
        recent_alerts=recent_alerts_data,
        api_counters=api_counters
    )


@app.route("/alerts/create", methods=["POST"])
def alerts_create():
    """
    Handles the 'Add New Alert' form submission from 'alerts.html'.
    We'll parse the form fields, create the alert in DB, then redirect.
    """
    alert_type = request.form.get("alert_type", "")
    trigger_value_str = request.form.get("trigger_value", "0")
    status = request.form.get("status", "Active")
    notification_type = request.form.get("notification_type", "SMS")
    position_ref = request.form.get("position_reference_id", "")

    # Convert numeric
    try:
        trigger_value = float(trigger_value_str)
    except ValueError:
        trigger_value = 0.0

    # TODO: Insert into your 'alerts' table or use your Alert model
    # e.g., data_locker.create_alert(...)
    # Something like:
    # new_alert = {
    #   "alert_type": alert_type,
    #   "trigger_value": trigger_value,
    #   "status": status,
    #   "notification_type": notification_type,
    #   "position_reference_id": position_ref,
    #   ...
    # }
    # data_locker.create_alert(new_alert)

    app.logger.info(f"Created alert: type={alert_type}, value={trigger_value}, status={status}")

    # After creation, redirect back to /alerts
    flash("New alert created successfully!", "success")
    return redirect(url_for("alerts"))


@app.route("/manual-check-alerts", methods=["POST"])
def manual_check_alerts():
    """
    Called by the "Check Alerts" button in 'alerts.html'.
    We'll call our alert_manager to do a manual check, then
    respond with JSON so the page can refresh.
    """
    try:
        # e.g. alert_manager.check_alerts()
        # For now, mock a "success" result
        message = "Alerts checked OK."
        return jsonify({"status": "success", "message": message}), 200
    except Exception as e:
        app.logger.error(f"Error checking alerts: {e}", exc_info=True)
        return jsonify({"status":"error", "message":str(e)}), 500



@app.route("/jupiter-perps-proxy", methods=["GET"])
def jupiter_perps_proxy():
    """
    A simple GET route that fetches the positions JSON from Jupiter's Perps API
    and returns it to the client.

    Usage example:
      /jupiter-perps-proxy?walletAddress=YourWalletHere

    If you don't specify a walletAddress, it defaults to a known test wallet.
    """
    # 1) Get walletAddress from query param (or default it)
    wallet_address = request.args.get("walletAddress", "6vMjsGU63evYuwwGsDHBRnKs1stALR7SYN5V57VZLXca")

    # 2) Construct Jupiter's API URL
    jupiter_url = f"https://perps-api.jup.ag/v1/positions?walletAddress={wallet_address}&showTpslRequests=true"

    try:
        # 3) Make the request to Jupiter
        response = requests.get(jupiter_url)
        response.raise_for_status()  # Raise HTTPError if bad status
        data = response.json()

        # 4) Return the fetched data as JSON
        return jsonify(data), 200

    except requests.exceptions.HTTPError as http_err:
        app.logger.error(f"HTTP error while fetching Jupiter positions: {http_err}")
        return jsonify({"error": f"HTTP {response.status_code}: {response.text}"}), 500
    except Exception as e:
        app.logger.error(f"Error fetching Jupiter positions: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def map_jupiter_item_to_position(item: dict) -> Position:
    asset_type = MINT_TO_ASSET.get(item["marketMint"], AssetType.BTC)
    pos_type = item["side"].lower()  # "short" or "long"

    # Convert epoch to datetime
    updated_dt = datetime.fromtimestamp(int(item["updatedTime"]))

    return Position(
        asset_type=asset_type,
        position_type=pos_type,
        entry_price=float(item["entryPrice"]),
        liquidation_price=float(item["liquidationPrice"]),
        collateral=float(item["collateral"]),
        size=float(item["size"]),
        leverage=float(item["leverage"]),
        value=float(item["value"]),
        last_updated=updated_dt
        # wallet="someWallet" if you want
        # or other optional fields
    )

@app.route("/update_jupiter", methods=["POST"])
def update_jupiter():
    """
    Calls update_jupiter_positions() (which returns a tuple)
    and update_prices() (which returns a Flask Response).
    If either fails, we return an error. Otherwise, success.
    """
    # 1) Unpack the tuple from update_jupiter_positions()
    jupiter_resp, jupiter_code = update_jupiter_positions()
    if jupiter_code != 200:
        # Return the same response & code => bubble up the error
        return jupiter_resp, jupiter_code

    # 2) update_prices() returns a single Flask Response object
    prices_resp = update_prices()
    if prices_resp.status_code != 200:
        return prices_resp  # bubble up that error

    # 3) If both succeeded
    return jsonify({"message": "Jupiter positions + Prices updated successfully!"}), 200

@app.route("/update-jupiter-positions", methods=["POST"])
def update_jupiter_positions():
    """
    Fetches fresh positions from Jupiter Perps API for ALL wallets in the 'wallets' table,
    then maps them to our local Position model, storing them in the DB.
    Now we add a check to avoid re-importing the same data over and over.
    """
    try:
        wallets_list = data_locker.read_wallets()
        if not wallets_list:
            app.logger.info("No wallets found in DB. Nothing to update from Jupiter.")
            return jsonify({"message": "No wallets found in DB"}), 200

        total_positions_imported = 0

        for w in wallets_list:
            public_addr = w.get("public_address", "").strip()
            if not public_addr:
                app.logger.info(f"Skipping wallet '{w['name']}' because no public_address is set.")
                continue

            jupiter_url = (
                "https://perps-api.jup.ag/v1/positions"
                f"?walletAddress={public_addr}"
                "&showTpslRequests=true"
            )
            resp = requests.get(jupiter_url)
            resp.raise_for_status()
            data = resp.json()

            data_list = data.get("dataList", [])
            if not data_list:
                app.logger.info(f"No positions returned for wallet {w['name']} ({public_addr})")
                continue

            new_positions = []
            for item in data_list:
                try:
                    epoch_time = float(item.get("updatedTime", 0))
                    updated_dt = datetime.fromtimestamp(epoch_time)

                    mint = item.get("marketMint", "")
                    asset_type = MINT_TO_ASSET.get(mint, "BTC")
                    side = item.get("side", "short").capitalize()

                    pos_dict = {
                        "asset_type": asset_type,
                        "position_type": side,
                        "entry_price": float(item.get("entryPrice", 0.0)),
                        "liquidation_price": float(item.get("liquidationPrice", 0.0)),
                        "collateral": float(item.get("collateral", 0.0)),
                        "size": float(item.get("size", 0.0)),
                        "leverage": float(item.get("leverage", 0.0)),
                        "value": float(item.get("value", 0.0)),
                        "last_updated": updated_dt.isoformat(),
                        "wallet_name": w["name"],
                    }
                    new_positions.append(pos_dict)

                except Exception as map_err:
                    app.logger.warning(
                        f"Skipping item for wallet {w['name']} due to mapping error: {map_err}"
                    )

            # -- HERE: minimal duplicate check before inserting --
            for p in new_positions:
                # Check if we already have the same wallet/asset/side/size/time, etc.
                # Adjust columns as needed to match your "uniqueness" definition.
                duplicate_check = data_locker.cursor.execute(
                    """
                    SELECT COUNT(*) FROM positions
                     WHERE wallet_name = ?
                       AND asset_type = ?
                       AND position_type = ?
                       AND ABS(size - ?) < 0.000001
                       AND ABS(collateral - ?) < 0.000001
                       AND last_updated = ?
                    """,
                    (
                        p["wallet_name"],
                        p["asset_type"],
                        p["position_type"],
                        p["size"],
                        p["collateral"],
                        p["last_updated"],
                    )
                ).fetchone()

                already_exists = (duplicate_check[0] > 0)
                if not already_exists:
                    # Insert only if it's not a duplicate
                    data_locker.create_position(p)
                    total_positions_imported += 1
                else:
                    app.logger.info(
                        f"Skipping duplicate Jupiter position for wallet={p['wallet_name']}, "
                        f"asset={p['asset_type']}, side={p['position_type']}"
                    )

        return jsonify({
            "message": f"Imported {total_positions_imported} new position(s) from all Jupiter wallets."
        }), 200

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching from Jupiter: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/test-jupiter-perps-proxy")
def test_jupiter_perps_proxy():
    """
    Renders a simple page with a button to fetch Jupiter data
    from our Flask proxy.
    """
    return render_template("test_jupiter_perps.html")

@app.route("/console-test")
def console_test():
    return render_template("console_test.html")

@app.route("/test-jupiter-swap", methods=["GET"])
def test_jupiter_swap():
    return render_template("test_jupiter_swap.html")
# --------------------------------------------------
# Main
# --------------------------------------------------
if __name__ == "__main__":
    # Start the Flask server
    app.run(debug=True, host="0.0.0.0", port=5000)
