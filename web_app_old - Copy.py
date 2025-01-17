from flask import Flask, request, jsonify, render_template, redirect, url_for
from data.data_locker import DataLocker  # Import your DataLocker class
import os
import uuid
from datetime import datetime
from environment_variables import load_env_variables
from calc_services import CalcServices
# If you have something like `report_generator` for heat, import it too

app = Flask(__name__)

# Load environment variables
load_env_variables()

# Use environment variable for database path or default to "data/mother_brain.db"
db_path = os.getenv("DATA_LOCKER_DB", "data/mother_brain.db")
db_path = os.path.abspath(db_path)
print(f"Web app using database at: {db_path}")

# Initialize DataLocker with the specified database path
data_locker = DataLocker(db_path=db_path)

# ------------------------------------------------------------------------------
#  DEFAULT / HOME
# ------------------------------------------------------------------------------
@app.route("/")
def index():
    # Just redirect to /positions as our “default” page
    return redirect(url_for("positions"))

# ------------------------------------------------------------------------------
#  POSITIONS PAGE
# ------------------------------------------------------------------------------
@app.route("/positions", methods=["GET", "POST"])
def positions():
    """Show the Positions page."""
    if request.method == "POST":
        # If you are allowing creation of new position from this page
        data = request.form
        position = {
            "id": data.get("id"),
            "asset_type": data.get("asset_type"),
            "position_type": data.get("position_type", "Long"),
            "entry_price": data.get("entry_price"),
            "liquidation_price": data.get("liquidation_price"),
            "current_travel_percent": data.get("current_travel_percent"),
            "value": data.get("value"),
            "collateral": data.get("collateral"),
            "size": data.get("size"),
            "wallet": data.get("wallet", "Default"),
            "leverage": data.get("leverage", 1),
            "last_updated": None,
            "current_price": None,
            "liquidation_distance": None,
        }
        data_locker.create_position(position)

    # Read positions and do your calculations
    positions_data = data_locker.read_positions()
    prices_data = data_locker.read_prices()
    totals = CalcServices.calculate_totals(positions_data)

    try:
        balance_metrics = CalcServices().calculate_balance_metrics(positions_data)
    except Exception as e:
        app.logger.error(f"Error calculating balance metrics: {e}")
        balance_metrics = {
            "total_long_size": 0, "total_short_size": 0, "total_size": 0,
            "total_long_value": 0, "total_short_value": 0, "total_value": 0,
            "total_long_collateral": 0, "total_short_collateral": 0, "total_collateral": 0,
        }

    # Round data
    positions_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in pos.items()}
        for pos in positions_data
    ]
    prices_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in price.items()}
        for price in prices_data
    ]
    totals = {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in totals.items()}
    balance_metrics = {k: (round(v, 2) if isinstance(v, (int, float)) else v)
                       for k, v in balance_metrics.items()}

    return render_template(
        "positions.html",
        positions=positions_data,
        prices=prices_data,
        totals=totals,
        balance_metrics=balance_metrics
    )

# ------------------------------------------------------------------------------
#  PRICES PAGE
# ------------------------------------------------------------------------------
@app.route("/prices", methods=["GET", "POST"])
def prices():
    """Show the Prices page."""
    if request.method == "POST":
        asset = request.form.get("asset")
        price = request.form.get("price")
        data_locker.create_price(asset, price, "Manual", None)

    prices_data = data_locker.read_prices()
    # Round data, etc. if needed
    prices_data = [
        {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in p.items()}
        for p in prices_data
    ]
    return render_template("prices.html", prices=prices_data)

# ------------------------------------------------------------------------------
#  HEAT PAGE
# ------------------------------------------------------------------------------
@app.route("/heat", methods=["GET"])
def heat():
    """Render the Heat page."""
    try:
        positions = data_locker.read_positions()
        balance_metrics = CalcServices().calculate_balance_metrics(positions)
        processed_positions = CalcServices().prepare_positions_for_display(positions)
        # If you want to show them in a full page, you can create a "heat.html" 
        # which extends sonic_admin.html and place the heat table / logic there.
        return render_template(
            "heat.html",
            balance_metrics=balance_metrics,
            positions=processed_positions
        )
    except Exception as e:
        app.logger.error(f"Error generating heat report: {e}")
        return jsonify({"error": f"Failed to generate heat report: {e}"}), 500

# ------------------------------------------------------------------------------
#  SYSTEM CONFIG PAGE (Placeholder)
# ------------------------------------------------------------------------------
@app.route("/config", methods=["GET", "POST"])
def system_config():
    """Placeholder for your System Configuration page."""
    if request.method == "POST":
        # Handle saving config if needed
        pass
    return render_template("config.html")

# ------------------------------------------------------------------------------
#  REFRESH DATA
# ------------------------------------------------------------------------------
@app.route("/refresh-data", methods=["POST"])
def refresh_data():
    try:
        # Possibly do everything you did before, or replaced:
        # data_locker.sync_dependent_data()  # Old comment: "we are replacing this"
        data_locker.sync_calc_services()  # Add extra functionality

        app.logger.info("Data refreshed successfully.")
        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error refreshing data: {e}")
        return jsonify({"error": f"Failed to refresh data: {e}"}), 500

# ------------------------------------------------------------------------------
#  CRUD ENDPOINTS (Positions, Prices, Alerts, etc.)
# ------------------------------------------------------------------------------
@app.route("/edit-position/<position_id>", methods=["POST"])
def edit_position(position_id):
    try:
        size = request.form.get("size")
        collateral = request.form.get("collateral")

        if not size or not collateral:
            return jsonify({"error": "Size and Collateral are required"}), 400

        data_locker.cursor.execute(
            """UPDATE positions
               SET size = ?, collateral = ?
               WHERE id = ?""",
            (float(size), float(collateral), position_id)
        )
        data_locker.conn.commit()

        data_locker.sync_dependent_data()
        data_locker.sync_calc_services()

        app.logger.info(f"Position {position_id} updated successfully.")
        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error updating position {position_id}: {e}")
        return jsonify({"error": f"Failed to update position: {e}"}), 500

@app.route("/upload-positions", methods=["POST"])
def upload_positions():
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
        return redirect(url_for("positions"))
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format."}), 400
    except Exception as e:
        app.logger.error(f"Error importing positions: {e}")
        return jsonify({"error": f"Failed to process file: {e}"}), 500

@app.route("/view-prices", methods=["GET"])
def view_prices():
    prices = data_locker.read_prices()
    return jsonify(prices)

@app.route('/add-price', methods=['POST'])
def add_price():
    try:
        asset = request.form.get('asset')
        price = request.form.get('price')
        source = "Manual Update"
        timestamp = datetime.now()

        if not asset or not price:
            return jsonify({"error": "Missing 'asset' or 'price'"}), 400

        data_locker.create_price(asset, float(price), source, timestamp)
        return redirect(url_for("positions"))  # or "/prices"
    except Exception as e:
        app.logger.error(f"Error adding price: {e}")
        return jsonify({"error": f"Failed to add price: {str(e)}"}), 500

@app.route("/delete-price/<asset>", methods=["GET"])
def delete_price(asset):
    data_locker.delete_price(asset)
    return redirect(url_for("prices"))

@app.route("/create-position", methods=["POST"])
@app.route("/new-position", methods=["POST"])
def create_position():
    try:
        asset = request.form.get("asset")
        position_type = request.form.get("position_type")
        collateral = float(request.form.get("collateral"))
        size = float(request.form.get("size"))
        entry_price = float(request.form.get("entry_price", 0.0))
        liquidation_price = float(request.form.get("liquidation_price", 0.0))

        position = {
            "id": f"pos_{uuid.uuid4().hex[:8]}",
            "asset_type": asset,
            "position_type": position_type,
            "entry_price": entry_price,
            "liquidation_price": liquidation_price,
            "collateral": collateral,
            "size": size,
            "value": collateral * size,
            "wallet": "Default",
            "leverage": size / collateral if collateral else 1.0,
            "current_travel_percent": 0.0,
            "last_updated": datetime.now().isoformat(),
            "current_price": None,
            "liquidation_distance": None,
        }

        data_locker.create_position(position)
        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error adding position: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/view-positions", methods=["GET"])
def view_positions():
    positions = data_locker.read_positions()
    return jsonify(positions)

@app.route("/add-position", methods=["POST"])
def add_position():
    try:
        position = {
            "id": f"pos_{uuid.uuid4().hex[:8]}",
            "asset_type": request.form.get("asset"),
            "position_type": request.form.get("position_type"),
            "entry_price": float(request.form.get("entry_price", 0.0)),
            "liquidation_price": float(request.form.get("liquidation_price", 0.0)),
            "collateral": float(request.form.get("collateral")),
            "size": float(request.form.get("size")),
            "wallet": "Default",
            "leverage": float(request.form.get("size")) / float(request.form.get("collateral")),
        }
        data_locker.create_position(position)
        return redirect(url_for("positions"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/delete-position/<position_id>", methods=["POST"])
def delete_position(position_id):
    try:
        data_locker.cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        data_locker.conn.commit()
        app.logger.info(f"Position {position_id} deleted successfully.")
        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error deleting position {position_id}: {e}")
        return jsonify({"error": f"Failed to delete position: {e}"}), 500

# Alerts
@app.route("/view-alerts", methods=["GET"])
def view_alerts():
    alerts = data_locker.read_alerts()
    return jsonify(alerts)

@app.route("/add-alert", methods=["POST"])
def add_alert():
    data = request.json
    alert = {
        "id": data.get("id"),
        "alert_type": data.get("alert_type"),
        "trigger_value": data.get("trigger_value"),
        "notification_type": data.get("notification_type"),
        "last_triggered": data.get("last_triggered"),
        "status": data.get("status"),
        "frequency": data.get("frequency"),
        "counter": data.get("counter"),
        "liquidation_distance": data.get("liquidation_distance"),
        "target_travel_percent": data.get("target_travel_percent"),
        "liquidation_price": data.get("liquidation_price"),
        "notes": data.get("notes"),
        "position_reference_id": data.get("position_reference_id"),
    }
    data_locker.create_alert(alert)
    return jsonify({"message": "Alert added successfully!"})

# Delete everything
@app.route("/delete-all", methods=["POST"])
def delete_all():
    try:
        data_locker.cursor.execute("DELETE FROM positions")
        data_locker.conn.commit()
        app.logger.info("All positions deleted successfully.")
        return redirect(url_for("positions"))
    except Exception as e:
        app.logger.error(f"Error deleting all positions: {e}")
        return jsonify({"error": f"Failed to delete all positions: {e}"}), 500

# Sync
@app.route("/sync-data", methods=["POST"])
def sync_data():
    data_locker.sync_dependent_data()
    return jsonify({"message": "Data synchronization completed successfully!"})

# Administrative Tasks
@app.route("/drop-tables", methods=["POST"])
def drop_tables():
    data_locker.drop_tables()
    return jsonify({"message": "All tables dropped successfully!"})

# ------------------------------------------------------------------------------
#  RUN
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
