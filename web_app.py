import os
import logging
import json
from datetime import datetime

from flask import Flask, request, jsonify, render_template, redirect, url_for

# Example: DataLocker and CalcServices from your existing code
from data.data_locker import DataLocker
from calc_services import CalcServices

# Pydantic-based config from data.config import AppConfig
from data.config import AppConfig

app = Flask(__name__)
app.debug = True

logger = logging.getLogger("WebAppLogger")
logger.setLevel(logging.DEBUG)

# Path to your database
db_path = os.path.abspath("data/mother_brain.db")
print(f"Using DB at: {db_path}")
data_locker = DataLocker(db_path=db_path)
calc_services = CalcServices()

@app.route("/")
def index():
    logger.debug("Reached / (root). Redirecting to /positions.")
    return redirect(url_for("positions"))

@app.route("/positions", methods=["GET", "POST"])
def positions():
    logger.debug("Entered /positions route.")

    if request.method == "POST":
        # Insert new position from form
        asset_type = request.form.get("asset_type", "BTC")
        position_type = request.form.get("position_type", "Long")
        collateral = float(request.form.get("collateral", 0.0))
        size = float(request.form.get("size", 0.0))
        entry_price = float(request.form.get("entry_price", 0.0))
        liquidation_price = float(request.form.get("liquidation_price", 0.0))

        data_locker.cursor.execute("""
            INSERT INTO positions
            (asset_type, position_type, collateral, size, entry_price, liquidation_price)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (asset_type, position_type, collateral, size, entry_price, liquidation_price))
        data_locker.conn.commit()

        return redirect(url_for("positions"))

    # GET => fetch positions & prices
    logger.debug("Reading positions/prices from DB.")
    positions_data = data_locker.read_positions()
    prices_data = data_locker.read_prices()
    logger.debug(f"Fetched {len(positions_data)} positions, {len(prices_data)} prices.")

    logger.debug("Running aggregator logic.")
    positions_data = calc_services.prepare_positions_for_display(positions_data)
    totals = calc_services.calculate_totals(positions_data)

    # Load config for color-coding
    config_data = AppConfig.load("sonic_config.json")

    def get_alert_status(value, low, medium, high):
        if high is None:
            high = float("inf")
        if value <= low:
            return ""
        elif value <= medium:
            return "bg-warning"
        else:
            return "bg-danger"

    # Apply color-coding to each field
    for pos in positions_data:
        # Value
        val_ranges = config_data.alert_ranges.value_ranges
        pos["value_status"] = get_alert_status(
            pos.get("value", 0.0),
            val_ranges.low or 0.0,
            val_ranges.medium or 9999999.0,
            val_ranges.high
        )
        # Collateral
        col_ranges = config_data.alert_ranges.collateral_ranges
        pos["collateral_status"] = get_alert_status(
            pos.get("collateral", 0.0),
            col_ranges.low or 0.0,
            col_ranges.medium or 9999999.0,
            col_ranges.high
        )
        # Size
        size_ranges = config_data.alert_ranges.size_ranges
        pos["size_status"] = get_alert_status(
            pos.get("size", 0.0),
            size_ranges.low or 0.0,
            size_ranges.medium or 9999999.0,
            size_ranges.high
        )
        # Heat Index
        hi_ranges = config_data.alert_ranges.heat_index_ranges
        pos["heat_index_status"] = get_alert_status(
            pos.get("heat_index", 0.0),
            hi_ranges.low or 0.0,
            hi_ranges.medium or 9999999.0,
            hi_ranges.high
        )
        # Travel %
        trav_ranges = config_data.alert_ranges.travel_percent_ranges
        pos["travel_percent_status"] = get_alert_status(
            pos.get("current_travel_percent", 0.0),
            trav_ranges.low or -999999.0,
            trav_ranges.medium or 9999999.0,
            trav_ranges.high
        )

    # Round numeric fields for display
    def roundify(val):
        return round(val, 2) if isinstance(val, (int, float)) else val

    for pos in positions_data:
        for k, v in pos.items():
            if isinstance(v, (int, float)):
                pos[k] = roundify(v)
    for pr in prices_data:
        for k, v in pr.items():
            if isinstance(v, (int, float)):
                pr[k] = roundify(v)
    totals = {k: roundify(v) for k, v in totals.items()}

    return render_template(
        "positions.html",
        positions=positions_data,
        prices=prices_data,
        totals=totals,
        config=config_data
    )

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

@app.route("/upload-positions", methods=["POST"])
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

        # parse JSON
        json_data = json.load(file)
        if not isinstance(json_data, list):
            logger.error("Uploaded JSON must be a list of positions.")
            return jsonify({"error": "JSON is not a list"}), 400

        # For each item, auto-calc fields using calc_services
        inserted_count = 0
        for item in json_data:
            # item should be a dict with at least 'asset_type', 'position_type', etc.
            # 1) run prepare_positions_for_display on a single-item list:
            prepped_list = calc_services.prepare_positions_for_display([item])
            prepped_item = prepped_list[0]  # now it has 'current_travel_percent', 'heat_index', etc.

            # 2) read back the fields we need to insert
            asset_type = prepped_item.get("asset_type", "BTC")
            position_type = prepped_item.get("position_type", "Long")
            collateral = float(prepped_item.get("collateral", 0.0))
            size = float(prepped_item.get("size", 0.0))
            entry_price = float(prepped_item.get("entry_price", 0.0))
            liquidation_price = float(prepped_item.get("liquidation_price", 0.0))
            current_travel_percent = float(prepped_item.get("current_travel_percent", 0.0))
            heat_index = float(prepped_item.get("heat_index", 0.0))

            # 3) Insert into DB
            # Make sure your table has these columns:
            # current_travel_percent and heat_index
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


@app.route("/prices", methods=["GET", "POST"])
def prices():
    logger.debug("Entered /prices route.")
    if request.method == "POST":
        # 1) Handle form data
        try:
            asset = request.form.get("asset", "BTC")
            price_val = float(request.form.get("price", 0.0))

            # Suppose you have a data_locker method that inserts or updates
            data_locker.insert_or_update_price(asset, price_val, "Manual", datetime.now())

            # Redirect back to /prices after processing the POST
            return redirect(url_for("prices"))

        except Exception as e:
            logger.error(f"Error updating price: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # 2) If GET => read from DB
    logger.debug("Fetching prices from DB.")
    prices_data = data_locker.read_prices()

    # Round or format the data if you want
    def roundify(val):
        return round(val, 2) if isinstance(val, (int, float)) else val
    for pr in prices_data:
        for k, v in pr.items():
            pr[k] = roundify(v)

    # If your sonic_admin.html needs a 'totals' var, pass an empty one so it doesn't crash:
    dummy_totals = {}

    return render_template("prices.html", prices=prices_data, totals=dummy_totals)


@app.route("/alert-options", methods=["GET", "POST"])
def alert_options():
    config_data = AppConfig.load("sonic_config.json")  # or however you load
    if request.method == "POST":
        # e.g. read from form
        new_heat_index_low = float(request.form["heat_index_low"])
        new_heat_index_medium = float(request.form["heat_index_medium"])
        raw_heat_index_high = request.form.get("heat_index_high", "")
        new_heat_index_high = float(raw_heat_index_high) if raw_heat_index_high else None

        # Now store in config_data.alert_ranges (NOT alert_config)
        config_data.alert_ranges.heat_index_ranges.low = new_heat_index_low
        config_data.alert_ranges.heat_index_ranges.medium = new_heat_index_medium
        config_data.alert_ranges.heat_index_ranges.high = new_heat_index_high

        # And so on for the other fields (collateral, value, etc.)

        # Then dump to JSON
        data_dict = config_data.model_dump()
        with open("sonic_config.json", "w") as f:
            json.dump(data_dict, f, indent=2)

        return redirect(url_for("alert_options"))

    return render_template("alert_options.html", config=config_data)
@app.route("/heat", methods=["GET"])
def heat():
    logger.debug("Entered /heat route.")
    try:
        positions_data = data_locker.read_positions()
        positions_data = calc_services.prepare_positions_for_display(positions_data)

        heat_data = build_heat_data(positions_data)
        if heat_data is None:
            heat_data = {}

        # Provide an empty dict for `totals` so `sonic_admin.html` won't crash
        return render_template("heat.html",
                               heat_data=heat_data,
                               totals={})
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

    # We'll accumulate data for each position
    # Example: partial sums to do an average or total
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
        side  = pos.get("position_type","Long").lower()  # "short" or "long"
        if asset not in ["BTC","ETH","SOL"]:
            continue  # skip unknown assets
        key = f"{asset}_{side}"

        partial[key]["collateral"] += pos.get("collateral",0.0)
        partial[key]["value"]      += pos.get("value",0.0)
        partial[key]["size"]       += pos.get("size",0.0)

        # track travel% sum => partial[key]["travel_percent"] += ...
        partial[key]["travel_percent"] += pos.get("current_travel_percent",0.0)

        # track heat => partial[key]["heat_index"] += ...
        partial[key]["heat_index"] += pos.get("heat_index",0.0)
        partial[key]["heat_count"] += 1

        # if you want leverage => partial[key]["lev_count"] => do an average or etc.

    # move partial sums -> structure[asset][side]
    # e.g. if partial["BTC_short"].size>0 => structure["BTC"]["short"] = dict( ... )
    for combo in partial:
        side = "short" if "short" in combo else "long"
        a    = "BTC" if "BTC" in combo else "ETH" if "ETH" in combo else "SOL"

        s_count = partial[combo]["size"]
        if s_count>0:
            structure[a][side] = {
                "asset": a,
                "collateral": partial[combo]["collateral"],
                "value":      partial[combo]["value"],
                "size":       s_count,
                "travel_percent": partial[combo]["travel_percent"]/(1 if partial[combo]["size"]==0 else partial[combo]["size"])*100, # or do your logic
                "heat_index": partial[combo]["heat_index"]/(partial[combo]["heat_count"] or 1),
                "leverage": 0.0  # up to you to calc
            }

    # also fill structure["totals"]["short"] etc.
    # example:
    structure["totals"]["short"]["collateral"] = partial["BTC_short"]["collateral"] + partial["ETH_short"]["collateral"] + partial["SOL_short"]["collateral"]
    structure["totals"]["short"]["value"]      = partial["BTC_short"]["value"]      + partial["ETH_short"]["value"]      + partial["SOL_short"]["value"]
    structure["totals"]["short"]["size"]       = partial["BTC_short"]["size"]       + partial["ETH_short"]["size"]       + partial["SOL_short"]["size"]
    # similarly for "long"

    return structure


@app.route("/config", methods=["GET", "POST"])
def system_config():
    config_data = AppConfig.load("sonic_config.json")
    if request.method == "POST":
        new_logging_enabled = (request.form.get("logging_enabled") == "on")
        config_data.system_config.logging_enabled = new_logging_enabled
        with open("sonic_config.json", "w") as f:
            f.write(config_data.json(indent=2))
        return redirect(url_for("system_config"))
    return render_template("system_config.html", config=config_data)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
