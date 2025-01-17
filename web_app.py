from flask import Flask, request, jsonify, render_template, redirect, url_for
import os
import uuid
from datetime import datetime

# Import your custom classes
from data.data_locker import DataLocker
from calc_services import CalcServices

# Load your environment variables if you do that
# from environment_variables import load_env_variables
# load_env_variables()

app = Flask(__name__)

# Pick your DB path, e.g. data\mother_brain.db
db_path = os.getenv("DATA_LOCKER_DB", "data/mother_brain.db")
db_path = os.path.abspath(db_path)
print(f"Web app using database at: {db_path}")

# Initialize DataLocker
data_locker = DataLocker(db_path=db_path)

########################################
# Default route -> Positions
########################################
@app.route("/")
def index():
    return redirect(url_for("positions"))

########################################
# POSITIONS
########################################
@app.route("/positions", methods=["GET", "POST"])
def positions():
    """Lists positions, calculates totals, allows adding new positions."""
    if request.method == "POST":
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

    # Read from DB
    positions_data = data_locker.read_positions()
    prices_data = data_locker.read_prices()

    # Calculate totals
    totals = CalcServices.calculate_totals(positions_data)
    # Example: totals = {"total_collateral":..., "total_value":..., "total_size":..., "avg_leverage":..., "avg_travel_percent":..., "avg_heat_points":...}

    # Round your data if desired
    positions_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in pos.items()}
        for pos in positions_data
    ]
    prices_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in price.items()}
        for price in prices_data
    ]
    totals = {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in totals.items()}

    # If you have separate logic for heat or balance metrics, do it here
    try:
        balance_metrics = CalcServices().calculate_balance_metrics(positions_data)
    except Exception as e:
        app.logger.error(f"Error calculating balance metrics: {e}")
        balance_metrics = {}

    return render_template(
        "positions.html",
        positions=positions_data,
        prices=prices_data,
        totals=totals,
        balance_metrics=balance_metrics
    )

########################################
# EDIT POSITION (inline updates: size, collateral)
########################################
@app.route("/edit-position/<position_id>", methods=["POST"])
def edit_position(position_id):
    try:
        size = request.form.get("size")
        collateral = request.form.get("collateral")

        if not size or not collateral:
            return jsonify({"error": "Size and Collateral are required"}), 400

        # Update DB
        data_locker.cursor.execute(
            """
            UPDATE positions
            SET size = ?, collateral = ?
            WHERE id = ?
            """,
            (float(size), float(collateral), position_id)
        )
        data_locker.conn.commit()

        # Possibly sync
        data_locker.sync_dependent_data()
        data_locker.sync_calc_services()

        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error updating position {position_id}: {e}")
        return jsonify({"error": f"Failed to update position: {e}"}), 500

########################################
# DELETE POSITION
########################################
@app.route("/delete-position/<position_id>", methods=["POST"])
def delete_position(position_id):
    try:
        data_locker.cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        data_locker.conn.commit()
        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error deleting position {position_id}: {e}")
        return jsonify({"error": f"Failed to delete position: {e}"}), 500

########################################
# PRICES
########################################
@app.route("/prices", methods=["GET", "POST"])
def prices():
    """Show the Prices page."""
    if request.method == "POST":
        asset = request.form.get("asset")
        price = request.form.get("price")
        data_locker.create_price(asset, float(price), "Manual", None)

    prices_data = data_locker.read_prices()
    prices_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in p.items()}
        for p in prices_data
    ]
    return render_template("prices.html", prices=prices_data)

########################################
# HEAT
########################################
def build_heat_data(positions):
    assets = ["BTC", "ETH", "SOL"]
    heat_data = {
        "BTC": {"short": None, "long": None},
        "ETH": {"short": None, "long": None},
        "SOL": {"short": None, "long": None},
        "totals": {
            "short": {
                "asset": "",
                "type": "Short",
                "collateral": 0,
                "value": 0,
                "leverage": 0,
                "travel_percent": 0,
                "heat_index": 0,
                "size": 0,
            },
            "long": {
                "asset": "",
                "type": "Long",
                "collateral": 0,
                "value": 0,
                "leverage": 0,
                "travel_percent": 0,
                "heat_index": 0,
                "size": 0,
            }
        }
    }

    def aggregate_positions(positions_list, position_type):
        if not positions_list:
            return None
        agg = {
            "asset": positions_list[0].get("asset_type", ""),
            "type": position_type,
            "collateral": 0.0,
            "value": 0.0,
            "leverage": 0.0,
            "travel_percent": 0.0,
            "heat_index": 0.0,
            "size": 0.0,
        }
        count = len(positions_list)
        for pos in positions_list:
            agg["collateral"] += pos.get("collateral", 0.0)
            agg["value"] += pos.get("value", 0.0)
            agg["size"] += pos.get("size", 0.0)
            agg["heat_index"] += pos.get("heat_points", 0.0) or 0.0
            agg["travel_percent"] += pos.get("current_travel_percent", 0.0) or 0.0
            agg["leverage"] += pos.get("leverage", 0.0)
        if count > 0:
            agg["leverage"] /= count
            agg["travel_percent"] /= count
            # For heat_index you might do sum or average, choose your logic.
            # e.g. agg["heat_index"] /= count
        return agg

    short_positions = {"BTC": [], "ETH": [], "SOL": []}
    long_positions = {"BTC": [], "ETH": [], "SOL": []}

    for pos in positions:
        asset = pos.get("asset_type", "").upper()
        ptype = pos.get("position_type", "Long").capitalize()
        if "heat_points" not in pos:
            pos["heat_points"] = 0.0
        if asset in assets:
            if ptype == "Short":
                short_positions[asset].append(pos)
            else:
                long_positions[asset].append(pos)

    for asset in assets:
        s_agg = aggregate_positions(short_positions[asset], "Short")
        l_agg = aggregate_positions(long_positions[asset], "Long")
        heat_data[asset]["short"] = s_agg
        heat_data[asset]["long"] = l_agg

    # Sum up for totals
    for asset in assets:
        s_agg = heat_data[asset]["short"]
        if s_agg:
            heat_data["totals"]["short"]["collateral"] += s_agg["collateral"]
            heat_data["totals"]["short"]["value"] += s_agg["value"]
            heat_data["totals"]["short"]["size"] += s_agg["size"]
            heat_data["totals"]["short"]["heat_index"] += s_agg["heat_index"]
            heat_data["totals"]["short"]["travel_percent"] += s_agg["travel_percent"]
            heat_data["totals"]["short"]["leverage"] += s_agg["leverage"]

        l_agg = heat_data[asset]["long"]
        if l_agg:
            heat_data["totals"]["long"]["collateral"] += l_agg["collateral"]
            heat_data["totals"]["long"]["value"] += l_agg["value"]
            heat_data["totals"]["long"]["size"] += l_agg["size"]
            heat_data["totals"]["long"]["heat_index"] += l_agg["heat_index"]
            heat_data["totals"]["long"]["travel_percent"] += l_agg["travel_percent"]
            heat_data["totals"]["long"]["leverage"] += l_agg["leverage"]

    return heat_data


@app.route("/heat", methods=["GET"])
def heat():
    """Heat page: side-by-side short vs long for BTC, ETH, SOL."""
    try:
        positions = data_locker.read_positions()
        # Build specialized structure
        heat_data = build_heat_data(positions)
        return render_template("heat.html", heat_data=heat_data)
    except Exception as e:
        app.logger.error(f"Error generating heat report: {e}")
        return jsonify({"error": f"Failed to generate heat report: {e}"}), 500

@app.route("/upload-positions", methods=["POST"])
def upload_positions():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    import json
    try:
        # Load and process JSON
        data = json.load(file)
        if "positions" not in data or not isinstance(data["positions"], list):
            return jsonify({"error": "Invalid JSON structure"}), 400

        data_locker.import_portfolio_data(data)  # Use DataLocker to process
        return redirect("/dashboard")
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format."}), 400
    except Exception as e:
        app.logger.error(f"Error importing positions: {e}")
        return jsonify({"error": f"Failed to process file: {e}"}), 500


########################################
# SYSTEM CONFIG
########################################
@app.route("/config", methods=["GET", "POST"])
def system_config():
    """Placeholder system config page."""
    if request.method == "POST":
        # do something
        pass
    return render_template("config.html")

########################################
# REFRESH DATA / SYNC
########################################
@app.route("/refresh-data", methods=["POST"])
def refresh_data():
    try:
        data_locker.sync_calc_services()
        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error refreshing data: {e}")
        return jsonify({"error": f"Failed to refresh data: {e}"}), 500

########################################
# MAIN RUN
########################################
if __name__ == "__main__":
    app.run(debug=False)  # or debug=True if you like
