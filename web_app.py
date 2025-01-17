import os
import uuid
from datetime import datetime

import asyncio
import logging
from flask import Flask, request, jsonify, render_template, redirect, url_for
from typing import Dict, List, Optional

# ------------------------------------------------------------------
# Import your custom classes
# ------------------------------------------------------------------
from data.data_locker import DataLocker
from calc_services import CalcServices
# If you have a PriceMonitor class to integrate, import here:
# from prices.price_monitor import PriceMonitor  # Example

# Load environment variables if needed
# from environment_variables import load_env_variables
# load_env_variables()

# ------------------------------------------------------------------
# Flask App Initialization
# ------------------------------------------------------------------
app = Flask(__name__)

# ------------------------------------------------------------------
# Database / DataLocker Setup
# ------------------------------------------------------------------
db_path = os.getenv("DATA_LOCKER_DB", "data/mother_brain.db")
db_path = os.path.abspath(db_path)
print(f"Web app using database at: {db_path}")

# Create a single DataLocker instance globally
data_locker = DataLocker(db_path=db_path)

# Optionally set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("WebAppLogger")

# ------------------------------------------------------------------
# Default Route: Redirect to Positions
# ------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("positions"))

# ------------------------------------------------------------------
# POSITIONS ENDPOINT
# ------------------------------------------------------------------
@app.route("/positions", methods=["GET", "POST"])
def positions():
    """
    GET: Renders the positions page, showing a list of positions, prices, and totals.
    POST: Creates a new position using form data.
    """
    if request.method == "POST":
        try:
            # Form data for new position
            data = request.form
            position = {
                "id": data.get("id") or f"pos_{uuid.uuid4().hex[:8]}",
                "asset_type": data.get("asset_type"),
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
            # Create in DB
            data_locker.create_position(position)
        except Exception as e:
            logger.error(f"Error creating position: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # Read data
    positions_data = data_locker.read_positions()
    prices_data = data_locker.read_prices()

    # Calculate totals
    totals = CalcServices.calculate_totals(positions_data)
    totals = {k: (round(v, 2) if isinstance(v, (int, float)) else v)
              for k, v in totals.items()}

    # Round positions and prices for display
    positions_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in pos.items()}
        for pos in positions_data
    ]
    prices_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in price.items()}
        for price in prices_data
    ]

    # Example: calculating additional metrics
    try:
        balance_metrics = CalcServices().calculate_balance_metrics(positions_data)
    except Exception as e:
        logger.error(f"Error calculating balance metrics: {e}", exc_info=True)
        balance_metrics = {}

    return render_template(
        "positions.html",
        positions=positions_data,
        prices=prices_data,
        totals=totals,
        balance_metrics=balance_metrics
    )

# ------------------------------------------------------------------
# EDIT POSITION
# ------------------------------------------------------------------
@app.route("/edit-position/<position_id>", methods=["POST"])
def edit_position(position_id):
    """
    Edits a position's size, collateral, or other fields in DB.
    Uses a dedicated DataLocker method for safety and clarity.
    """
    try:
        size = float(request.form.get("size", 0.0))
        collateral = float(request.form.get("collateral", 0.0))

        data_locker.update_position(position_id, new_size=size, new_collateral=collateral)
        data_locker.sync_dependent_data()
        data_locker.sync_calc_services()

        return redirect(url_for("positions"))
    except Exception as e:
        logger.error(f"Error updating position {position_id}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to update position: {e}"}), 500

# ------------------------------------------------------------------
# DELETE POSITION
# ------------------------------------------------------------------
@app.route("/delete-position/<position_id>", methods=["POST"])
def delete_position(position_id):
    """
    Deletes a position by ID.
    """
    try:
        data_locker.cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        data_locker.conn.commit()
        return redirect(url_for("positions"))
    except Exception as e:
        logger.error(f"Error deleting position {position_id}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to delete position: {e}"}), 500

# ------------------------------------------------------------------
# PRICES ENDPOINT
# ------------------------------------------------------------------
@app.route("/prices", methods=["GET", "POST"])
def prices():
    """
    GET: Renders a page showing all prices from the DB.
    POST: Inserts or updates a price using insert_or_update_price (Manual source).
    """
    if request.method == "POST":
        try:
            asset = request.form.get("asset")
            price_val = float(request.form.get("price", 0.0))
            # Use insert_or_update_price for consistency with auto-fetched updates
            data_locker.insert_or_update_price(asset, price_val, "Manual", datetime.now())
        except Exception as e:
            logger.error(f"Error inserting/updating price: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    prices_data = data_locker.read_prices()
    # Round for display
    prices_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in p.items()}
        for p in prices_data
    ]
    return render_template("prices.html", prices=prices_data)

# ------------------------------------------------------------------
# OPTIONAL: TRIGGER EXTERNAL PRICE FETCH
# ------------------------------------------------------------------
@app.route("/update-prices", methods=["POST"])
def update_prices_now():
    """
    This is optional if you have an async PriceMonitor that fetches external data.
    It synchronously triggers PriceMonitor.update_prices() from the Flask route.
    NOTE: This can block the web server during the fetch. For heavier usage,
    consider Celery, RQ, or a background thread approach.
    """
    # from prices.price_monitor import PriceMonitor  # if you have it
    # config_path = "sonic_config.json"
    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    # try:
    #     pm = PriceMonitor(config_path=config_path)
    #     loop.run_until_complete(pm.update_prices())
    # finally:
    #     loop.close()

    # For now, just do a quick data_locker refresh or log a placeholder
    logger.info("update_prices_now route called - implement your PriceMonitor logic here.")
    return redirect(url_for("prices"))

# ------------------------------------------------------------------
# HEAT ENDPOINT
# ------------------------------------------------------------------
@app.route("/heat", methods=["GET"])
def heat():
    """
    Heat page: side-by-side short vs long for BTC, ETH, SOL, or other logic.
    The code calls build_heat_data to create a specialized structure.
    """
    try:
        positions = data_locker.read_positions()
        heat_data = build_heat_data(positions)
        return render_template("heat.html", heat_data=heat_data)
    except Exception as e:
        logger.error(f"Error generating heat report: {e}", exc_info=True)
        return jsonify({"error": f"Failed to generate heat report: {e}"}), 500

def build_heat_data(positions):
    # Example from your original code, simplified/unchanged except minor tweaks
    assets = ["BTC", "ETH", "SOL"]
    heat_data = {
        asset: {"short": None, "long": None} for asset in assets
    }
    heat_data["totals"] = {
        "short": {"collateral": 0, "value": 0, "leverage": 0, "travel_percent": 0, "heat_index": 0, "size": 0},
        "long": {"collateral": 0, "value": 0, "leverage": 0, "travel_percent": 0, "heat_index": 0, "size": 0}
    }

    def aggregate_positions(pos_list, ptype):
        if not pos_list:
            return None
        agg = {"collateral": 0.0, "value": 0.0, "leverage": 0.0, "travel_percent": 0.0, "heat_index": 0.0, "size": 0.0}
        count = len(pos_list)
        for pos in pos_list:
            agg["collateral"] += pos.get("collateral", 0.0)
            agg["value"] += pos.get("value", 0.0)
            agg["size"] += pos.get("size", 0.0)
            agg["heat_index"] += (pos.get("heat_points") or 0.0)
            agg["travel_percent"] += (pos.get("current_travel_percent") or 0.0)
            agg["leverage"] += (pos.get("leverage") or 0.0)

        if count > 0:
            agg["leverage"] /= count
            agg["travel_percent"] /= count
        return agg

    short_positions = {asset: [] for asset in assets}
    long_positions = {asset: [] for asset in assets}

    for pos in positions:
        asset = pos.get("asset_type", "").upper()
        ptype = pos.get("position_type", "Long").capitalize()
        pos.setdefault("heat_points", 0.0)
        if asset in assets:
            if ptype == "Short":
                short_positions[asset].append(pos)
            else:
                long_positions[asset].append(pos)

    # Aggregate for each asset
    for asset in assets:
        s_agg = aggregate_positions(short_positions[asset], "Short")
        l_agg = aggregate_positions(long_positions[asset], "Long")
        heat_data[asset]["short"] = s_agg
        heat_data[asset]["long"] = l_agg

        if s_agg:
            heat_data["totals"]["short"]["collateral"] += s_agg["collateral"]
            heat_data["totals"]["short"]["value"] += s_agg["value"]
            heat_data["totals"]["short"]["size"] += s_agg["size"]
            heat_data["totals"]["short"]["heat_index"] += s_agg["heat_index"]
            heat_data["totals"]["short"]["travel_percent"] += s_agg["travel_percent"]
            heat_data["totals"]["short"]["leverage"] += s_agg["leverage"]
        if l_agg:
            heat_data["totals"]["long"]["collateral"] += l_agg["collateral"]
            heat_data["totals"]["long"]["value"] += l_agg["value"]
            heat_data["totals"]["long"]["size"] += l_agg["size"]
            heat_data["totals"]["long"]["heat_index"] += l_agg["heat_index"]
            heat_data["totals"]["long"]["travel_percent"] += l_agg["travel_percent"]
            heat_data["totals"]["long"]["leverage"] += l_agg["leverage"]

    return heat_data

# ------------------------------------------------------------------
# UPLOAD POSITIONS
# ------------------------------------------------------------------
@app.route("/upload-positions", methods=["POST"])
def upload_positions():
    """
    Expects a JSON file with a 'positions' list. Uses DataLocker.import_portfolio_data.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    import json
    try:
        data = json.load(file)
        if "positions" not in data or not isinstance(data["positions"], list):
            return jsonify({"error": "Invalid JSON structure"}), 400

        data_locker.import_portfolio_data(data)
        return redirect("/positions")
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format."}), 400
    except Exception as e:
        app.logger.error(f"Error importing positions: {e}", exc_info=True)
        return jsonify({"error": f"Failed to process file: {e}"}), 500

# ------------------------------------------------------------------
# SYSTEM CONFIG ROUTE
# ------------------------------------------------------------------
@app.route("/config", methods=["GET", "POST"])
def system_config():
    """
    Example placeholder system config page.
    GET: Show config or form to change config
    POST: Modify config
    """
    if request.method == "POST":
        # do something with request.form
        pass
    return render_template("config.html")

# ------------------------------------------------------------------
# REFRESH DATA / SYNC
# ------------------------------------------------------------------
@app.route("/refresh-data", methods=["POST"])
def refresh_data():
    """
    Calls data_locker sync methods for recalculations, etc.
    """
    try:
        data_locker.sync_calc_services()
        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error refreshing data: {e}", exc_info=True)
        return jsonify({"error": f"Failed to refresh data: {e}"}), 500

# ------------------------------------------------------------------
# FLASK MAIN
# ------------------------------------------------------------------
if __name__ == "__main__":
    # If you want to run debug mode, set debug=True. Otherwise, set it to False for production.
    app.run(debug=False, host="0.0.0.0", port=5000)
