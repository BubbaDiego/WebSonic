from flask import Flask, jsonify, request
from data.data_locker import DataLocker  # Import your DataLocker class

app = Flask(__name__)

# Initialize DataLocker
data_locker = DataLocker()

@app.route("/")
def home():
    return "Welcome to Data Locker! Use the available endpoints to manage your data."

@app.route("/view-prices", methods=["GET"])
def view_prices():
    prices = data_locker.read_prices()
    return jsonify(prices)

@app.route("/create-random-position", methods=["POST"])
def create_random_position():
    data_locker.create_random_position()
    return jsonify({"message": "Random position created successfully!"})

@app.route("/view-positions", methods=["GET"])
def view_positions():
    positions = data_locker.read_positions()
    return jsonify(positions)

if __name__ == "__main__":
    app.run(debug=True)
