from flask import Flask, request, jsonify, render_template, redirect
from data.data_locker import DataLocker  # Import your DataLocker class
import os
from environment_variables import load_env_variables

app = Flask(__name__)

# Load environment variables
load_env_variables()

# Use environment variable for database path or default to "data/mother_brain.db"
db_path = os.getenv("DATA_LOCKER_DB", "data/mother_brain.db")

# Ensure the database path is absolute
db_path = os.path.abspath(db_path)

print(f"Web app using database at: {db_path}")


# Initialize DataLocker with the specified database path
data_locker = DataLocker(db_path=db_path)

@app.route("/", methods=["GET", "POST"])
@app.route("/dash", methods=["GET", "POST"])
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    try:
        if request.method == "POST":
            # Handle form submissions (e.g., adding prices or positions)
            if "asset" in request.form:
                asset = request.form["asset"]
                price = float(request.form["price"])
                data_locker.create_price(asset, price, "Manual", None)
            elif "id" in request.form:
                position = {
                    "id": request.form["id"],
                    "asset_type": request.form["asset_type"],
                    "entry_price": float(request.form["entry_price"]),
                    "size": float(request.form["size"]),
                }
                data_locker.create_position(position)

        # Fetch data for rendering
        prices = data_locker.read_prices()
        positions = data_locker.read_positions()

        return render_template("dashboard.html", prices=prices, positions=positions)
    except Exception as e:
        app.logger.error(f"Error in dashboard: {e}")
        return "An error occurred while processing your request. Check server logs for details.", 500

@app.route("/refresh-data", methods=["POST"])
def refresh_data():
    try:
        data_locker.sync_dependent_data()
        app.logger.info("Data refreshed successfully.")
        return redirect("/dash")
    except Exception as e:
        app.logger.error(f"Error refreshing data: {e}")
        return jsonify({"error": f"Failed to refresh data: {e}"}), 500


@app.route("/manage-data", methods=["GET", "POST"])
def manage_data():
    if request.method == "POST":
        if "asset" in request.form:
            asset = request.form["asset"]
            price = request.form["price"]
            data_locker.create_price(asset, price, "Manual", None)
        elif "id" in request.form:
            position = {
                "id": request.form["id"],
                "asset_type": request.form["asset_type"],
                "entry_price": request.form["entry_price"],
                "size": request.form["size"],
            }
            data_locker.create_position(position)
    prices = data_locker.read_prices()
    positions = data_locker.read_positions()
    return render_template("manage_data.html", prices=prices, positions=positions)

@app.route("/positions", methods=["GET", "POST"])
def positions():
    if request.method == "POST":
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

    positions = data_locker.read_positions()
    heat_report = report_generator.generate_heat_report_data()  # Generate heat data

    # Merge heat data into positions
    for pos in positions:
        heat_data = next((h for h in heat_report if h["asset"] == pos["asset_type"]), {})
        pos.update(heat_data)

    return render_template("manage_data.html", positions=positions)

# Prices
@app.route("/view-prices", methods=["GET"])
def view_prices():
    prices = data_locker.read_prices()
    return jsonify(prices)

@app.route("/add-price", methods=["POST"])
def add_price():
    data = request.json
    asset = data.get("asset")
    price = data.get("price")
    source = data.get("source", "Manual")
    timestamp = data.get("timestamp")
    data_locker.create_price(asset, price, source, timestamp)
    return jsonify({"message": f"Price for {asset} added successfully!"})

# Positions
@app.route("/view-positions", methods=["GET"])
def view_positions():
    positions = data_locker.read_positions()
    return jsonify(positions)

@app.route("/add-position", methods=["POST"])
def add_position():
    data = request.json
    position = {
        "id": data.get("id"),
        "asset_type": data.get("asset_type"),
        "position_type": data.get("position_type"),
        "entry_price": data.get("entry_price"),
        "liquidation_price": data.get("liquidation_price"),
        "current_travel_percent": data.get("current_travel_percent"),
        "value": data.get("value"),
        "collateral": data.get("collateral"),
        "size": data.get("size"),
        "wallet": data.get("wallet"),
        "leverage": data.get("leverage"),
        "last_updated": data.get("last_updated"),
        "current_price": data.get("current_price"),
        "liquidation_distance": data.get("liquidation_distance"),
    }
    data_locker.create_position(position)
    return jsonify({"message": "Position added successfully!"})


@app.route("/delete-position/<position_id>", methods=["POST"])
def delete_position(position_id):
    try:
        data_locker.cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        data_locker.conn.commit()
        app.logger.debug(f"Position deleted: id={position_id}")
        return redirect("/manage-data")
    except Exception as e:
        app.logger.error(f"Error deleting position: {e}")
        return jsonify({"error": f"Failed to delete position: {e}"}), 500

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

@app.route("/prices", methods=["GET", "POST"])
def prices():
    if request.method == "POST":
        data = request.form
        asset = data.get("asset")
        price = data.get("price")
        data_locker.create_price(asset, price, "Manual", None)
    prices = data_locker.read_prices()
    return render_template("prices.html", prices=prices)

@app.route("/delete-price/<asset>", methods=["GET"])
def delete_price(asset):
    data_locker.delete_price(asset)
    return redirect("/prices")

@app.route("/delete-all", methods=["POST"])
def delete_all():
    try:
        data_locker.cursor.execute("DELETE FROM positions")  # Delete all positions
        data_locker.conn.commit()
        app.logger.info("All positions deleted successfully.")
        return redirect("/dashboard")
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

if __name__ == "__main__":
    app.run(debug=True)