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
    """
    Root route -> redirect to /positions
    """
    logger.debug("Reached / (root). Redirecting to /positions.")
    return redirect(url_for("positions"))

@app.route("/positions", methods=["GET", "POST"])
def positions():
    """
    GET: Show positions table
    POST: Create a new position from form data
    """
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

    # Else it's a GET
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
        # color-coded logic based on thresholds
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
        # You can do more fields if needed

    # Round numeric values for display
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
    """
    Update an existing position (collateral/size)
    """
    logger.debug(f"Editing position {position_id}")
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
    """
    Delete a single position
    """
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
def upload_positions():
    """
    Accept JSON file -> insert positions
    """
    logger.debug("Uploading positions from JSON.")
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        # parse JSON
        json_data = json.load(file)
        for item in json_data:
            asset_type = item.get("asset_type", "BTC")
            position_type = item.get("position_type", "Long")
            collateral = float(item.get("collateral", 0.0))
            size = float(item.get("size", 0.0))
            entry_price = float(item.get("entry_price", 0.0))
            liquidation_price = float(item.get("liquidation_price", 0.0))

            data_locker.cursor.execute("""
                INSERT INTO positions
                (asset_type, position_type, collateral, size, entry_price, liquidation_price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (asset_type, position_type, collateral, size, entry_price, liquidation_price))

        data_locker.conn.commit()
        logger.debug("Positions uploaded successfully.")
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error uploading positions: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/prices", methods=["GET", "POST"])
def prices():
    """
    Example route for updating or listing prices
    """
    logger.debug("Entered /prices route.")
    if request.method == "POST":
        try:
            asset = request.form.get("asset", "BTC")
            price_val = float(request.form.get("price", 0.0))
            data_locker.insert_or_update_price(asset, price_val, "Manual", datetime.now())
        except Exception as e:
            logger.error(f"Error updating price: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
        return redirect(url_for("prices"))

    prices_data = data_locker.read_prices()
    def roundify(val):
        return round(val, 2) if isinstance(val, (int, float)) else val

    for pr in prices_data:
        for k, v in pr.items():
            pr[k] = roundify(v)
    return render_template("prices.html", prices=prices_data)


@app.route("/alert-options", methods=["GET", "POST"])
def alert_options():
    """
    Example route to update your alert ranges
    """
    config_data = AppConfig.load("sonic_config.json")
    if request.method == "POST":
        try:
            # update heat_index as example
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
        except Exception as e:
            logger.error(f"Error updating alert ranges: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    return render_template("alert_options.html", config=config_data)

@app.route("/heat", methods=["GET"])
def heat():
    """
    Example route for a 'heat' page
    """
    logger.debug("Entered /heat route.")
    try:
        positions_data = data_locker.read_positions()
        positions_data = calc_services.prepare_positions_for_display(positions_data)
        # if you have a real build_heat_data
        heat_data = build_heat_data(positions_data)
        return render_template("heat.html", heat_data=heat_data)
    except Exception as e:
        logger.error(f"Error generating heat page: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def build_heat_data(positions):
    # placeholder
    return {"dummy": "Implement your logic here."}

@app.route("/config", methods=["GET", "POST"])
def system_config():
    """
    Example route for system config
    """
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
