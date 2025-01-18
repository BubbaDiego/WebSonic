# web_app.py

import os
import uuid
import logging
import json
from datetime import datetime

from flask import Flask, request, jsonify, render_template, redirect, url_for

# DataLocker and CalcServices from your existing code
from data.data_locker import DataLocker
from calc_services import CalcServices

# Pydantic-based config from data/config.py
from data.config import AppConfig

# ------------------------------------------------------------------
# Initialize Flask
# ------------------------------------------------------------------
app = Flask(__name__)

# Optional: set debug in code or rely on environment variables
app.debug = True

# Logging
logger = logging.getLogger("WebAppLogger")
logger.setLevel(logging.DEBUG)

# ------------------------------------------------------------------
# Initialize DataLocker, CalcServices, etc.
# ------------------------------------------------------------------
db_path = os.getenv("DATA_LOCKER_DB", "data/mother_brain.db")
db_path = os.path.abspath(db_path)
print(f"Web app using database at: {db_path}")

data_locker = DataLocker(db_path=db_path)
calc_services = CalcServices()

# ------------------------------------------------------------------
# Root route
# ------------------------------------------------------------------
@app.route("/")
def index():
    """
    Instead of returning a 'dummy success' message,
    we can redirect to /positions or some other page.
    """
    logger.debug("Reached the / (root) route - redirecting to /positions.")
    return redirect(url_for("positions"))

# ------------------------------------------------------------------
# POSITIONS
# ------------------------------------------------------------------
@app.route("/positions", methods=["GET", "POST"])
def positions():
    """
    If POST, create a new position from form data.
    If GET, display positions in a template.
    """
    logger.debug("Step 1: Entered /positions route.")

    if request.method == "POST":
        logger.debug("Creating a new position from form data.")
        try:
            data = request.form
            position = {
                "id": data.get("id") or f"pos_{uuid.uuid4().hex[:8]}",
                "asset_type": data.get("asset_type", "BTC"),
                "position_type": data.get("position_type", "Long"),
                "entry_price": float(data.get("entry_price", 0.0)),
                "liquidation_price": float(data.get("liquidation_price", 0.0)),
                "current_travel_percent": float(data.get("current_travel_percent", 0.0)),
                "value": float(data.get("value", 0.0)),
                "collateral": float(data.get("collateral", 0.0)),
                "size": float(data.get("size", 0.0)),
                "wallet": data.get("wallet", "Default"),
                "leverage": float(data.get("leverage", 1.0)),
                "last_updated": None,
                "current_price": None,
                "liquidation_distance": None,
            }
            data_locker.create_position(position)
        except Exception as e:
            logger.error(f"Error creating position: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

        return redirect(url_for("positions"))

    # If GET, read from DB
    logger.debug("Step 2: Reading positions/prices from DB.")
    try:
        positions_data = data_locker.read_positions()
        prices_data = data_locker.read_prices()
        logger.debug(f"Step 2.1: Fetched {len(positions_data)} positions, {len(prices_data)} prices.")
    except Exception as e:
        logger.error(f"DB Error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    # Attempt to run aggregator logic
    logger.debug("Step 3: Running aggregator logic.")
    try:
        # Preprocess positions for display
        positions_data = calc_services.prepare_positions_for_display(positions_data)

        # Calculate totals
        totals = calc_services.calculate_totals(positions_data)
        logger.debug(f"Computed totals: {totals}")
    except Exception as e:
        logger.error(f"Step 3.3: Error in aggregator logic: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    # Round for final display if desired
    def roundify(val):
        return round(val, 2) if isinstance(val, (int, float)) else val

    # Round out positions & prices
    for pos in positions_data:
        for k, v in pos.items():
            pos[k] = roundify(v)
    for pr in prices_data:
        for k, v in pr.items():
            pr[k] = roundify(v)

    totals = {k: roundify(v) for k, v in totals.items()}

    return render_template(
        "positions.html",
        positions=positions_data,
        prices=prices_data,
        totals=totals,
        balance_metrics={}  # or some other info if you want
    )

# ------------------------------------------------------------------
# EDIT POSITION
# ------------------------------------------------------------------
@app.route("/edit-position/<position_id>", methods=["POST"])
def edit_position(position_id):
    logger.debug(f"Editing position {position_id}.")
    try:
        size = float(request.form.get("size", 0.0))
        collateral = float(request.form.get("collateral", 0.0))

        # Suppose you have a method that updates size & collateral
        data_locker.update_position(position_id, new_size=size, new_collateral=collateral)
        data_locker.sync_dependent_data()
        data_locker.sync_calc_services()

        return redirect(url_for("positions"))
    except Exception as e:
        logger.error(f"Error updating position {position_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------
# DELETE POSITION
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# PRICES
# ------------------------------------------------------------------
@app.route("/prices", methods=["GET", "POST"])
def prices():
    logger.debug("Entered /prices route.")
    if request.method == "POST":
        logger.debug("Inserting/Updating a manual price.")
        try:
            asset = request.form.get("asset", "BTC")
            price_val = float(request.form.get("price", 0.0))
            data_locker.insert_or_update_price(asset, price_val, "Manual", datetime.now())
        except Exception as e:
            logger.error(f"Error updating price: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

        return redirect(url_for("prices"))

    # GET request: read from DB
    prices_data = data_locker.read_prices()
    def roundify(val):
        return round(val, 2) if isinstance(val, (int, float)) else val
    for pr in prices_data:
        for k, v in pr.items():
            pr[k] = roundify(v)

    return render_template("prices.html", prices=prices_data)

# ------------------------------------------------------------------
# ALERT OPTIONS
# ------------------------------------------------------------------
@app.route("/alert-options", methods=["GET", "POST"])
@app.route("/alert-options", methods=["GET", "POST"])
def alert_options():
    """
    Loads config from 'sonic_config.json', displays current alert ranges,
    and updates them based on form fields that match alert_options.html.
    """
    config_data = AppConfig.load("sonic_config.json")  # Adjust path if needed

    if request.method == "POST":
        logger.debug("Updating alert ranges from form.")
        try:
            # ---------------------
            # HEAT INDEX
            # ---------------------
            new_heat_index_low = float(request.form["heat_index_low"])
            new_heat_index_medium = float(request.form["heat_index_medium"])
            raw_heat_index_high = request.form.get("heat_index_high", "")
            new_heat_index_high = float(raw_heat_index_high) if raw_heat_index_high else None

            config_data.alert_ranges.heat_index_ranges.low = new_heat_index_low
            config_data.alert_ranges.heat_index_ranges.medium = new_heat_index_medium
            config_data.alert_ranges.heat_index_ranges.high = new_heat_index_high

            # ---------------------
            # COLLATERAL
            # ---------------------
            new_collateral_low = float(request.form["collateral_low"])
            new_collateral_medium = float(request.form["collateral_medium"])
            raw_collateral_high = request.form.get("collateral_high", "")
            new_collateral_high = float(raw_collateral_high) if raw_collateral_high else None

            config_data.alert_ranges.collateral_ranges.low = new_collateral_low
            config_data.alert_ranges.collateral_ranges.medium = new_collateral_medium
            config_data.alert_ranges.collateral_ranges.high = new_collateral_high

            # ---------------------
            # VALUE
            # ---------------------
            new_value_low = float(request.form["value_low"])
            new_value_medium = float(request.form["value_medium"])
            raw_value_high = request.form.get("value_high", "")
            new_value_high = float(raw_value_high) if raw_value_high else None

            config_data.alert_ranges.value_ranges.low = new_value_low
            config_data.alert_ranges.value_ranges.medium = new_value_medium
            config_data.alert_ranges.value_ranges.high = new_value_high

            # ---------------------
            # SIZE
            # ---------------------
            new_size_low = float(request.form["size_low"])
            new_size_medium = float(request.form["size_medium"])
            raw_size_high = request.form.get("size_high", "")
            new_size_high = float(raw_size_high) if raw_size_high else None

            config_data.alert_ranges.size_ranges.low = new_size_low
            config_data.alert_ranges.size_ranges.medium = new_size_medium
            config_data.alert_ranges.size_ranges.high = new_size_high

            # ---------------------
            # LEVERAGE
            # ---------------------
            new_leverage_low = float(request.form["leverage_low"])
            new_leverage_medium = float(request.form["leverage_medium"])
            raw_leverage_high = request.form.get("leverage_high", "")
            new_leverage_high = float(raw_leverage_high) if raw_leverage_high else None

            config_data.alert_ranges.leverage_ranges.low = new_leverage_low
            config_data.alert_ranges.leverage_ranges.medium = new_leverage_medium
            config_data.alert_ranges.leverage_ranges.high = new_leverage_high

            # ---------------------
            # LIQUIDATION DISTANCE
            # ---------------------
            new_liq_dist_low = float(request.form["liq_dist_low"])
            new_liq_dist_medium = float(request.form["liq_dist_medium"])
            raw_liq_dist_high = request.form.get("liq_dist_high", "")
            new_liq_dist_high = float(raw_liq_dist_high) if raw_liq_dist_high else None

            config_data.alert_ranges.liquidation_distance_ranges.low = new_liq_dist_low
            config_data.alert_ranges.liquidation_distance_ranges.medium = new_liq_dist_medium
            config_data.alert_ranges.liquidation_distance_ranges.high = new_liq_dist_high

            # ---------------------
            # TRAVEL PERCENT
            # ---------------------
            new_travel_low = float(request.form["travel_low"])
            new_travel_medium = float(request.form["travel_medium"])
            raw_travel_high = request.form.get("travel_high", "")
            new_travel_high = float(raw_travel_high) if raw_travel_high else None

            config_data.alert_ranges.travel_percent_ranges.low = new_travel_low
            config_data.alert_ranges.travel_percent_ranges.medium = new_travel_medium
            config_data.alert_ranges.travel_percent_ranges.high = new_travel_high

            # ---------------------
            # SAVE TO FILE
            # ---------------------
            data_dict = config_data.model_dump()  # Convert the Pydantic model to a plain dict
            with open("sonic_config.json", "w") as f:
                f.write(json.dumps(data_dict, indent=2))  # Use standard json.dumps with indent=2

            return redirect(url_for("alert_options"))

        except Exception as e:
            logger.error(f"Error updating alert ranges: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # GET request: show the current settings in the form
    return render_template("alert_options.html", config=config_data)



# ------------------------------------------------------------------
# HEAT
# ------------------------------------------------------------------
@app.route("/heat", methods=["GET"])
def heat():
    logger.debug("Entered /heat route.")
    try:
        positions_data = data_locker.read_positions()
        positions_data = calc_services.prepare_positions_for_display(positions_data)
        # Suppose you have a build_heat_data function
        heat_data = build_heat_data(positions_data)
        return render_template("heat.html", heat_data=heat_data)
    except Exception as e:
        logger.error(f"Error generating heat page: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def build_heat_data(positions):
    # Sample logic:
    return {"dummy": "Implement your logic here."}

# ------------------------------------------------------------------
# SYSTEM CONFIG
# ------------------------------------------------------------------
@app.route("/config", methods=["GET", "POST"])
def system_config():
    """
    Example system config page if needed
    """
    config_data = AppConfig.load("sonic_config.json")

    if request.method == "POST":
        # update some system config fields
        new_logging_enabled = (request.form.get("logging_enabled") == "on")
        config_data.system_config.logging_enabled = new_logging_enabled
        # etc ...
        with open("sonic_config.json", "w") as f:
            f.write(config_data.json(indent=2))
        return redirect(url_for("system_config"))

    return render_template("system_config.html", config=config_data)

# ------------------------------------------------------------------
# MAIN ENTRY (if used)
# ------------------------------------------------------------------
if __name__ == "__main__":
    # If you directly run python web_app.py, you can do:
    app.run(debug=True, host="0.0.0.0", port=5000)
