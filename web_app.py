from flask import Flask, request, jsonify, render_template, redirect
from data.data_locker import DataLocker  # Import your DataLocker class
import requests
import os
import asyncio
import pytz
from datetime import datetime
from prices.price_monitor import PriceMonitor
from environment_variables import load_env_variables
from calc_services import CalcServices

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
@app.route('/dashboard')
def dashboard():
    positions = data_locker.read_positions()
    prices = data_locker.read_prices()



    totals = CalcServices.calculate_totals(positions)

    try:
        balance_metrics = CalcServices().calculate_balance_metrics(positions)
    except Exception as e:
        app.logger.error(f"Error calculating balance metrics: {e}")
        balance_metrics = {
            "total_long_size": 0,
            "total_short_size": 0,
            "total_size": 0,
            "total_long_value": 0,
            "total_short_value": 0,
            "total_value": 0,
            "total_long_collateral": 0,
            "total_short_collateral": 0,
            "total_collateral": 0,
        }

    # Limit all numbers to two decimal places
    positions = [{k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in pos.items()} for pos in positions]
    prices = [{k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in price.items()} for price in prices]
    totals = {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in totals.items()}
    balance_metrics = {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in balance_metrics.items()}

    return render_template(
        'dashboard.html',
        positions=positions,
        prices=prices,
        totals=totals,
        balance_metrics=balance_metrics
    )


@app.route("/refresh-data", methods=["POST"])
def refresh_data():
    try:
        #data_locker.sync_dependent_data()  # we are replacing this
        data_locker.sync_calc_services()  # add this functionality.
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

@app.route("/edit-position/<position_id>", methods=["POST"])
def edit_position(position_id):
    try:
        size = request.form.get("size")
        collateral = request.form.get("collateral")

        # Validate inputs
        if not size or not collateral:
            return jsonify({"error": "Size and Collateral are required"}), 400

        # Update the database
        data_locker.cursor.execute(
            """
            UPDATE positions
            SET size = ?, collateral = ?
            WHERE id = ?
            """,
            (float(size), float(collateral), position_id)
        )
        data_locker.conn.commit()

        # GENO REFRESH TEST
        data_locker.sync_dependent_data()
        data_locker.sync_calc_services()

        app.logger.info(f"Position {position_id} updated successfully.")
        return redirect("/dashboard")
    except Exception as e:
        app.logger.error(f"Error updating position {position_id}: {e}")
        return jsonify({"error": f"Failed to update position: {e}"}), 500


@app.route("/heat", methods=["GET"])
def heat():
    """
    Render the heat report combining heat and balance data.
    """
    try:
        positions = data_locker.read_positions()
        balance_metrics = CalcServices().calculate_balance_metrics(positions)
        processed_positions = CalcServices().prepare_positions_for_display(positions)

        return render_template(
            "heat_display.html",
            balance_metrics=balance_metrics,
            positions=processed_positions
        )
    except Exception as e:
        app.logger.error(f"Error generating heat report: {e}")
        return jsonify({"error": f"Failed to generate heat report: {e}"}), 500

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

@app.route('/add-price', methods=['POST'])
def add_price():
    """
    Adds or updates a price in the database using form-data.
    """
    locker = DataLocker.get_instance()

    try:
        # Extract form-data from the request
        asset = request.form.get('asset')
        price = request.form.get('price')
        source = "Manual Update"  # Default source
        timestamp = datetime.now()  # Use the imported datetime module

        # Validate required fields
        if not asset or not price:
            return jsonify({"error": "Missing 'asset' or 'price' field in form data"}), 400

        # Use the DataLocker to create or update the price
        locker.create_price(asset, float(price), source, timestamp)

        return redirect('/dashboard')  # Redirect back to the dashboard

    except Exception as e:
        app.logger.error(f"Error adding price: {e}")
        return jsonify({"error": f"Failed to add price: {str(e)}"}), 500

# Positions
@app.route("/view-positions", methods=["GET"])
def view_positions():
    positions = data_locker.read_positions()
    return jsonify(positions)

@app.route("/add-position", methods=["POST"])
def add_position():
    data = request.json

    print("HIIIIIIIIIIIIIII")
    print(asset)

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
        app.logger.info(f"Position {position_id} deleted successfully.")
        return redirect("/dashboard")
    except Exception as e:
        app.logger.error(f"Error deleting position {position_id}: {e}")
        return jsonify({"error": f"Failed to delete position: {e}"}), 500

if __name__ == "__main__":
    app.run(debug=True)


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
@app.route('/update-prices', methods=['POST'])
def update_prices():
    """
    Fetch current prices for BTC, ETH, and SOL using the PriceMonitor class.
    """
    try:
        from prices.price_monitor import PriceMonitor
        monitor = PriceMonitor()
        asyncio.run(monitor.update_prices())

        app.logger.info("Prices updated successfully using PriceMonitor.")
        return redirect("/dashboard")
    except Exception as e:
        app.logger.error(f"Unexpected error while updating prices: {e}")
        return jsonify({"error": f"Failed to update prices: {e}"}), 500


# Administrative Tasks
@app.route("/drop-tables", methods=["POST"])
def drop_tables():
    data_locker.drop_tables()
    return jsonify({"message": "All tables dropped successfully!"})

if __name__ == "__main__":
    app.run(debug=True)