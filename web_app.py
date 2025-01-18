import os
import uuid
import logging
import json
from datetime import datetime

from flask import Flask, request, jsonify, render_template, redirect, url_for

# DataLocker and CalcServices from your existing code
from data.data_locker import DataLocker
from calc_services import CalcServices

# Pydantic-based config from data.config import AppConfig
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
@app.route("/positions", methods=["GET", "POST"])
def positions():
    logger.debug("Step 1: Entered /positions route.")

    if request.method == "POST":
        # Your existing "create new position" logic (insert to DB, etc.)
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

    # If GET, read from DB
    logger.debug("Step 2: Reading positions/prices from DB.")
    try:
        positions_data = data_locker.read_positions()
        prices_data = data_locker.read_prices()
        logger.debug(f"Step 2.1: Fetched {len(positions_data)} positions, {len(prices_data)} prices.")
    except Exception as e:
        logger.error(f"DB Error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    # Attempt aggregator logic
    logger.debug("Step 3: Running aggregator logic.")
    try:
        # Calculate any derived fields you need:
        positions_data = calc_services.prepare_positions_for_display(positions_data)
        totals = calc_services.calculate_totals(positions_data)
        logger.debug(f"Computed totals: {totals}")
    except Exception as e:
        logger.error(f"Error in aggregator logic: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    # Load config to get alert_ranges
    try:
        config_data = AppConfig.load("sonic_config.json")
    except Exception as e:
        logger.error(f"Error loading config: {e}", exc_info=True)
        return jsonify({"error": "Failed to load config"}), 500

    # ------------------------------------------------------------------
    # Color-code fields by comparing to alert ranges
    # ------------------------------------------------------------------
    def get_alert_status(value: float, low_threshold: float, medium_threshold: float, high_threshold: float | None) -> str:
        """
        Returns a CSS class based on whether `value` is in low, medium, or high range:
        - '' (empty string): Low (no background color)
        - 'bg-warning': Medium (yellow)
        - 'bg-danger': High (red)
        """
        if high_threshold is None:
            high_threshold = float("inf")

        if value <= low_threshold:
            return ""
        elif value <= medium_threshold:
            return "bg-warning"
        else:
            return "bg-danger"

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

        # Travel Percent
        trav_ranges = config_data.alert_ranges.travel_percent_ranges
        pos["travel_percent_status"] = get_alert_status(
            pos.get("current_travel_percent", 0.0),
            trav_ranges.low or -999999.0,    # for negative possibilities
            trav_ranges.medium or 9999999.0,
            trav_ranges.high
        )

        # If you want to do the same for "leverage" or "liq_distance", do it here as well.

    # ------------------------------------------------------------------
    # Round numeric fields for display (optional)
    # ------------------------------------------------------------------
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
        balance_metrics={},
        config=config_data
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
            # Example of reading form fields -> updating config
            new_heat_index_low = float(request.form["heat_index_low"])
            new_heat_index_medium = float(request.form["heat_index_medium"])
            raw_heat_index_high = request.form.get("heat_index_high", "")
            new_heat_index_high = float(raw_heat_index_high) if raw_heat_index_high else None

            config_data.alert_ranges.heat_index_ranges.low = new_heat_index_low
            config_data.alert_ranges.heat_index_ranges.medium = new_heat_index_medium
            config_data.alert_ranges.heat_index_ranges.high = new_heat_index_high

            # Repeat for other ranges (collateral, value, size, leverage, etc.)

            # After updating all fields...
            data_dict = config_data.model_dump()
            with open("sonic_config.json", "w") as f:
                f.write(json.dumps(data_dict, indent=2))

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
        heat_data = build_heat_data(positions_data)  # an example function
        return render_template("heat.html", heat_data=heat_data)
    except Exception as e:
        logger.error(f"Error generating heat page: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def build_heat_data(positions):
    return {"dummy": "Implement your logic here."}

# ------------------------------------------------------------------
# SYSTEM CONFIG
# ------------------------------------------------------------------
@app.route("/config", methods=["GET", "POST"])
def system_config():
    config_data = AppConfig.load("sonic_config.json")

    if request.method == "POST":
        new_logging_enabled = (request.form.get("logging_enabled") == "on")
        config_data.system_config.logging_enabled = new_logging_enabled
        # etc ...
        with open("sonic_config.json", "w") as f:
            f.write(config_data.json(indent=2))
        return redirect(url_for("system_config"))

    return render_template("system_config.html", config=config_data)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
