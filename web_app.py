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

app = Flask(__name__)
app.debug = True

logger = logging.getLogger("WebAppLogger")
logger.setLevel(logging.DEBUG)

db_path = os.getenv("DATA_LOCKER_DB", "data/mother_brain.db")
db_path = os.path.abspath(db_path)
print(f"Web app using database at: {db_path}")

data_locker = DataLocker(db_path=db_path)
calc_services = CalcServices()

@app.route("/")
def index():
    logger.debug("Reached the / (root) route - redirecting to /positions.")
    return redirect(url_for("positions"))

@app.route("/positions", methods=["GET", "POST"])
@app.route("/positions", methods=["GET", "POST"])
def positions():
    logger.debug("Step 1: Entered /positions route.")

    if request.method == "POST":
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

    logger.debug("Step 2: Reading positions/prices from DB.")
    try:
        positions_data = data_locker.read_positions()
        prices_data = data_locker.read_prices()
        logger.debug(f"Step 2.1: Fetched {len(positions_data)} positions, {len(prices_data)} prices.")
    except Exception as e:
        logger.error(f"DB Error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    logger.debug("Step 3: Running aggregator logic.")
    try:
        positions_data = calc_services.prepare_positions_for_display(positions_data)
        totals = calc_services.calculate_totals(positions_data)
        logger.debug(f"Computed totals: {totals}")
    except Exception as e:
        logger.error(f"Error in aggregator logic: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    try:
        config_data = AppConfig.load("sonic_config.json")
    except Exception as e:
        logger.error(f"Error loading config: {e}", exc_info=True)
        return jsonify({"error": "Failed to load config"}), 500

    def get_alert_status(value: float, low_threshold: float, medium_threshold: float, high_threshold: float|None) -> str:
        if high_threshold is None:
            high_threshold = float("inf")

        if value <= low_threshold:
            return ""
        elif value <= medium_threshold:
            return "bg-warning"
        else:
            return "bg-danger"

    # Color-code each position field
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
            trav_ranges.low or -999999.0,
            trav_ranges.medium or 9999999.0,
            trav_ranges.high
        )
        # (Leverage or anything else if you want to color-code more)

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

    prices_data = data_locker.read_prices()
    def roundify(val):
        return round(val, 2) if isinstance(val, (int, float)) else val
    for pr in prices_data:
        for k, v in pr.items():
            pr[k] = roundify(v)

    return render_template("prices.html", prices=prices_data)

@app.route("/alert-options", methods=["GET", "POST"])
@app.route("/alert-options", methods=["GET", "POST"])
def alert_options():
    config_data = AppConfig.load("sonic_config.json")
    if request.method == "POST":
        logger.debug("Updating alert ranges from form.")
        try:
            # sample for heat_index, repeat for other fields
            new_heat_index_low = float(request.form["heat_index_low"])
            new_heat_index_medium = float(request.form["heat_index_medium"])
            raw_heat_index_high = request.form.get("heat_index_high", "")
            new_heat_index_high = float(raw_heat_index_high) if raw_heat_index_high else None

            config_data.alert_ranges.heat_index_ranges.low = new_heat_index_low
            config_data.alert_ranges.heat_index_ranges.medium = new_heat_index_medium
            config_data.alert_ranges.heat_index_ranges.high = new_heat_index_high

            data_dict = config_data.model_dump()
            with open("sonic_config.json", "w") as f:
                f.write(json.dumps(data_dict, indent=2))

            return redirect(url_for("alert_options"))
        except Exception as e:
            logger.error(f"Error updating alert ranges: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    return render_template("alert_options.html", config=config_data)

@app.route("/heat", methods=["GET"])
def heat():
    logger.debug("Entered /heat route.")
    try:
        positions_data = data_locker.read_positions()
        positions_data = calc_services.prepare_positions_for_display(positions_data)
        # Now we actually build a real dictionary, not just {"dummy": ...}
        heat_data = build_heat_data(positions_data)

        return render_template("heat.html", heat_data=heat_data)
    except Exception as e:
        logger.error(f"Error generating heat page: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def build_heat_data(positions):
    """
    Build a structure so that:
      heat_data["BTC"]["short"] -> dict or None
      heat_data["BTC"]["long"]  -> dict or None
      heat_data["ETH"]["short"] -> dict or None
      ...
      heat_data["totals"]["short"] -> dict
      heat_data["totals"]["long"]  -> dict

    We’ll sum up collateral/value/size. For leverage/travel_percent/heat_index, we do an average.
    If there's no short or long positions for a given asset, set that to None.
    """
    # Initialize a holder for per-asset short/long
    structure = {
        "BTC": {"short": None, "long": None},
        "ETH": {"short": None, "long": None},
        "SOL": {"short": None, "long": None},
        "totals": {
            "short": {
                "asset": None,
                "collateral": 0.0,
                "value": 0.0,
                "leverage": 0.0,
                "travel_percent": 0.0,
                "heat_index": 0.0,
                "size": 0.0
            },
            "long": {
                "asset": None,
                "collateral": 0.0,
                "value": 0.0,
                "leverage": 0.0,
                "travel_percent": 0.0,
                "heat_index": 0.0,
                "size": 0.0
            }
        }
    }

    # We'll accumulate partial sums for each (asset, side).
    # Then we compute average for leverage, travel%, heat_index.
    partial = {
        "BTC_short": {"asset": "BTC", "collateral":0,"value":0,"leverage":0,"travel_percent":0,"heat_index":0,"size":0, "lev_count":0, "trav_count":0, "heat_count":0},
        "BTC_long":  {"asset": "BTC", "collateral":0,"value":0,"leverage":0,"travel_percent":0,"heat_index":0,"size":0, "lev_count":0, "trav_count":0, "heat_count":0},

        "ETH_short": {"asset": "ETH", "collateral":0,"value":0,"leverage":0,"travel_percent":0,"heat_index":0,"size":0, "lev_count":0, "trav_count":0, "heat_count":0},
        "ETH_long":  {"asset": "ETH", "collateral":0,"value":0,"leverage":0,"travel_percent":0,"heat_index":0,"size":0, "lev_count":0, "trav_count":0, "heat_count":0},

        "SOL_short": {"asset": "SOL", "collateral":0,"value":0,"leverage":0,"travel_percent":0,"heat_index":0,"size":0, "lev_count":0, "trav_count":0, "heat_count":0},
        "SOL_long":  {"asset": "SOL", "collateral":0,"value":0,"leverage":0,"travel_percent":0,"heat_index":0,"size":0, "lev_count":0, "trav_count":0, "heat_count":0},
    }

    # Populate partial sums
    for pos in positions:
        asset = pos.get("asset_type", "BTC")
        side  = pos.get("position_type", "Long").lower()  # "short" or "long"
        if asset not in ["BTC","ETH","SOL"]:
            continue  # skip if not in those three assets
        key = f"{asset}_{side}"

        partial[key]["collateral"] += pos.get("collateral", 0.0)
        partial[key]["value"]      += pos.get("value", 0.0)
        partial[key]["size"]       += pos.get("size", 0.0)

        # For leverage, travel%, heat, we'll do an average. So we keep track separately.
        lev_val = pos.get("leverage")
        if lev_val is not None:
            partial[key]["leverage"] += lev_val
            partial[key]["lev_count"] += 1

        trav_val = pos.get("current_travel_percent")
        if trav_val is not None:
            partial[key]["travel_percent"] += trav_val
            partial[key]["trav_count"] += 1

        heat_val = pos.get("heat_index")
        if heat_val is not None:
            partial[key]["heat_index"] += heat_val
            partial[key]["heat_count"] += 1

    # Compute the average for those we have a count for
    def finalize_average(row):
        if row["lev_count"]>0:
            row["leverage"] = row["leverage"]/row["lev_count"]
        else:
            row["leverage"] = 0

        if row["trav_count"]>0:
            row["travel_percent"] = row["travel_percent"]/row["trav_count"]
        else:
            row["travel_percent"] = 0

        if row["heat_count"]>0:
            row["heat_index"] = row["heat_index"]/row["heat_count"]
        else:
            row["heat_index"] = 0

        return row

    # For each partial entry, finalize average
    for k in partial:
        partial[k] = finalize_average(partial[k])

    # Put them back into structure if there's a nonzero size
    for asset in ["BTC","ETH","SOL"]:
        for side in ["short","long"]:
            key = f"{asset}_{side}"
            if partial[key]["size"] > 0:
                structure[asset][side] = {
                    "asset": asset,
                    "collateral": partial[key]["collateral"],
                    "value": partial[key]["value"],
                    "size": partial[key]["size"],
                    "leverage": partial[key]["leverage"],
                    "travel_percent": partial[key]["travel_percent"],
                    "heat_index": partial[key]["heat_index"]
                }
            else:
                # If no positions => None => template shows blank row
                structure[asset][side] = None

    # Now compute totals across all short or all long
    def sum_side(side):
        # sum collateral, value, size
        c = partial[f"BTC_{side}"]["collateral"] + partial[f"ETH_{side}"]["collateral"] + partial[f"SOL_{side}"]["collateral"]
        v = partial[f"BTC_{side}"]["value"]      + partial[f"ETH_{side}"]["value"]      + partial[f"SOL_{side}"]["value"]
        s = partial[f"BTC_{side}"]["size"]       + partial[f"ETH_{side}"]["size"]       + partial[f"SOL_{side}"]["size"]

        # Weighted average for leverage, travel_percent, heat_index
        # Weighted by the counts or by size?
        # We'll just do sum-of-averages approach * counts:
        lev_sum  = partial[f"BTC_{side}"]["leverage"]*partial[f"BTC_{side}"]["lev_count"] \
                 + partial[f"ETH_{side}"]["leverage"]*partial[f"ETH_{side}"]["lev_count"] \
                 + partial[f"SOL_{side}"]["leverage"]*partial[f"SOL_{side}"]["lev_count"]
        lev_count = partial[f"BTC_{side}"]["lev_count"] + partial[f"ETH_{side}"]["lev_count"] + partial[f"SOL_{side}"]["lev_count"]
        lev_final = lev_sum / lev_count if lev_count>0 else 0

        trav_sum  = partial[f"BTC_{side}"]["travel_percent"]*partial[f"BTC_{side}"]["trav_count"] \
                  + partial[f"ETH_{side}"]["travel_percent"]*partial[f"ETH_{side}"]["trav_count"] \
                  + partial[f"SOL_{side}"]["travel_percent"]*partial[f"SOL_{side}"]["trav_count"]
        trav_count = partial[f"BTC_{side}"]["trav_count"] + partial[f"ETH_{side}"]["trav_count"] + partial[f"SOL_{side}"]["trav_count"]
        trav_final = trav_sum / trav_count if trav_count>0 else 0

        heat_sum  = partial[f"BTC_{side}"]["heat_index"]*partial[f"BTC_{side}"]["heat_count"] \
                  + partial[f"ETH_{side}"]["heat_index"]*partial[f"ETH_{side}"]["heat_count"] \
                  + partial[f"SOL_{side}"]["heat_index"]*partial[f"SOL_{side}"]["heat_count"]
        heat_count = partial[f"BTC_{side}"]["heat_count"] + partial[f"ETH_{side}"]["heat_count"] + partial[f"SOL_{side}"]["heat_count"]
        heat_final = heat_sum / heat_count if heat_count>0 else 0

        return {
            "asset": None,  # or side.title()
            "collateral": c,
            "value": v,
            "size": s,
            "leverage": lev_final,
            "travel_percent": trav_final,
            "heat_index": heat_final
        }

    structure["totals"]["short"] = sum_side("short")
    structure["totals"]["long"]  = sum_side("long")

    return structure

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
