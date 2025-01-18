import os
import uuid
from datetime import datetime
import logging

from flask import Flask, request, jsonify, render_template, redirect, url_for

# ------------------------------------------------------------------
# Your custom classes
# ------------------------------------------------------------------
from data.data_locker import DataLocker
from calc_services import CalcServices

# ------------------------------------------------------------------
# Flask App Initialization
# ------------------------------------------------------------------
app = Flask(__name__)

# ------------------------------------------------------------------
# Configure Logging
# ------------------------------------------------------------------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("WebAppLogger")

# ------------------------------------------------------------------
# Database / DataLocker Setup
# ------------------------------------------------------------------
db_path = os.getenv("DATA_LOCKER_DB", "data/mother_brain.db")
db_path = os.path.abspath(db_path)
print(f"Web app using database at: {db_path}")

data_locker = DataLocker(db_path=db_path)
calc_services = CalcServices()

# ------------------------------------------------------------------
# Simple Test Route
# ------------------------------------------------------------------
@app.route("/test")
def test_route():
    logger.debug("Reached the /test route!")
    return "Test route OK", 200

# ------------------------------------------------------------------
# Root Route
# ------------------------------------------------------------------
@app.route("/")
def index():
    logger.debug("Reached the / (root) route - returning dummy success for debugging.")
    return "Root dummy route OK", 200

# ------------------------------------------------------------------
# System Config Route (to match url_for('system_config'))
# ------------------------------------------------------------------
@app.route("/system_config", methods=["GET", "POST"])
def system_config():
    """
    Minimal route for system config to avoid BuildError if 'system_config' was missing.
    """
    logger.debug("Accessed /system_config route.")
    return "System Config route OK", 200

# ------------------------------------------------------------------
# POSITIONS ENDPOINT - with incremental debug
# ------------------------------------------------------------------
@app.route("/positions", methods=["GET", "POST"])
def positions():
    logger.debug("Step 1: Entered /positions route.")

    if request.method == "POST":
        logger.debug("Step 1.1: Handling POST to /positions.")
        try:
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
            logger.debug(f"Step 1.2: New position form data: {position}")
            data_locker.create_position(position)
            logger.debug("Step 1.3: Position created successfully.")
        except Exception as e:
            logger.error(f"Step 1.4: Error creating position: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # If you suspect the route or template is causing a 500,
    # you can comment out or re-enable pieces in steps 2-4 below.
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    # # (Uncomment this if you want a minimal success path first)
    # logger.debug("Step 2: Minimal route returning success.")
    # return "Positions minimal route OK", 200

    logger.debug("Step 2: Reading positions/prices from DB.")
    try:
        positions_data = data_locker.read_positions()
        prices_data = data_locker.read_prices()
        logger.debug(f"Step 2.1: Fetched {len(positions_data)} positions, {len(prices_data)} prices.")
    except Exception as e:
        logger.error(f"Step 2.2: Error fetching from DB: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    logger.debug("Step 3: Running aggregator logic.")
    try:
        positions_data = calc_services.prepare_positions_for_display(positions_data)
        logger.debug("Step 3.1: positions prepared.")
        totals = calc_services.calculate_totals(positions_data)
        logger.debug(f"Step 3.2: Calculated totals: {totals}")
    except Exception as e:
        logger.error(f"Step 3.3: Error in aggregator logic: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    logger.debug("Step 4: Rounding data & rendering template.")
    def roundify(item):
        return round(item, 2) if isinstance(item, (int, float)) else item

    positions_data = [
        {k: roundify(v) for k, v in pos.items()}
        for pos in positions_data
    ]
    prices_data = [
        {k: roundify(v) for k, v in p.items()}
        for p in prices_data
    ]
    totals = {k: roundify(v) for k, v in totals.items()}

    logger.debug(f"Step 4.1: Rounding done. Rendering positions.html now.")
    return render_template(
        "positions.html",
        positions=positions_data,
        prices=prices_data,
        totals=totals,
        balance_metrics={}  # or use calc_services.calculate_balance_metrics(positions_data)
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
    logger.debug(f"Deleting position {position_id}.")
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
    logger.debug("Accessed /prices route.")
    if request.method == "POST":
        logger.debug("Handling POST to /prices (Manual insert/update).")
        try:
            asset = request.form.get("asset")
            price_val = float(request.form.get("price", 0.0))
            data_locker.insert_or_update_price(asset, price_val, "Manual", datetime.now())
            logger.debug(f"Price inserted/updated for asset={asset}, price={price_val}")
        except Exception as e:
            logger.error(f"Error inserting/updating price: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    logger.debug("Reading prices from DB for display.")
    prices_data = data_locker.read_prices()
    def roundify(item):
        return round(item, 2) if isinstance(item, (int, float)) else item
    prices_data = [
        {k: roundify(v) for k, v in p.items()}
        for p in prices_data
    ]
    logger.debug(f"Fetched {len(prices_data)} prices. Rendering prices.html.")
    return render_template("prices.html", prices=prices_data)

# ------------------------------------------------------------------
# HEAT ENDPOINT
# ------------------------------------------------------------------
@app.route("/heat", methods=["GET"])
def heat():
    logger.debug("Accessed /heat route.")
    try:
        positions = data_locker.read_positions()
        positions = calc_services.prepare_positions_for_display(positions)
        heat_data = build_heat_data(positions)
        return render_template("heat.html", heat_data=heat_data)
    except Exception as e:
        logger.error(f"Error generating heat report: {e}", exc_info=True)
        return jsonify({"error": f"Failed to generate heat report: {e}"}), 500

def build_heat_data(positions):
    logger.debug("Building heat data aggregator structure.")
    assets = ["BTC", "ETH", "SOL"]
    heat_data = {asset: {"short": None, "long": None} for asset in assets}
    heat_data["totals"] = {
        "short": {"collateral": 0, "value": 0, "leverage": 0, "travel_percent": 0, "heat_index": 0, "size": 0},
        "long": {"collateral": 0, "value": 0, "leverage": 0, "travel_percent": 0, "heat_index": 0, "size": 0}
    }

    def aggregate_positions(pos_list):
        if not pos_list:
            return None
        agg = {"collateral": 0.0, "value": 0.0, "leverage": 0.0, "travel_percent": 0.0, "heat_index": 0.0, "size": 0.0}
        count = len(pos_list)
        for pos in pos_list:
            pos.setdefault("heat_index", 0.0)
            agg["collateral"] += pos.get("collateral", 0.0)
            agg["value"] += pos.get("value", 0.0)
            agg["size"] += pos.get("size", 0.0)
            agg["heat_index"] += pos.get("heat_index", 0.0)
            agg["travel_percent"] += pos.get("current_travel_percent", 0.0)
            agg["leverage"] += pos.get("leverage", 0.0)

        if count > 0:
            agg["leverage"] /= count
            agg["travel_percent"] /= count
        return agg

    short_positions = {asset: [] for asset in assets}
    long_positions = {asset: [] for asset in assets}

    for pos in positions:
        asset = pos.get("asset_type", "").upper()
        ptype = pos.get("position_type", "Long").capitalize()
        pos.setdefault("heat_index", 0.0)
        if asset in assets:
            if ptype == "Short":
                short_positions[asset].append(pos)
            else:
                long_positions[asset].append(pos)

    # For each asset, aggregate short/long
    for asset in assets:
        s_agg = aggregate_positions(short_positions[asset])
        l_agg = aggregate_positions(long_positions[asset])
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
# OPTIONAL PRICE FETCH
# ------------------------------------------------------------------
@app.route("/update-prices", methods=["POST"])
def update_prices_now():
    logger.info("update_prices_now route called - stub for external PriceMonitor logic.")
    return redirect(url_for("prices"))

# ------------------------------------------------------------------
# If you want to run it directly (not via 'flask run'):
# ------------------------------------------------------------------
if __name__ == "__main__":
    logger.debug("Running web_app.py directly - enabling debug=True.")
    app.run(debug=True)
