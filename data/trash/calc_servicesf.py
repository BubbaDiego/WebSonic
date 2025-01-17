from typing import Optional, List, Dict

class CalcServices:
    def __init__(self):
        # Ranges for color mapping
        self.color_ranges = {
            "travel_percent": [(0, 25, "green"), (25, 50, "yellow"), (50, 75, "orange"), (75, 100, "red")],
            "heat_index": [(0, 20, "blue"), (20, 40, "green"), (40, 60, "yellow"), (60, 80, "orange"), (80, 100, "red")],
            "collateral": [(0, 500, "lightgreen"), (500, 1000, "yellow"), (1000, 2000, "orange"), (2000, 10000, "red")]
        }

    def calculate_value(self, position: dict) -> float:
        """
        Calculate the value of a position based on size, entry price, current price, and position type.
        Supports both long and short positions.
        """
        size = float(position.get("size", 0))
        entry_price = float(position.get("entry_price", 0))
        current_price = float(position.get("current_price", 0))
        position_type = position.get("position_type", "long").lower()

        if size <= 0 or current_price <= 0:
            raise ValueError("Size and current price must be greater than zero.")

        if position_type == "long":
            return round(size * current_price, 2)
        elif position_type == "short":
            # For short positions: Value = Size * (2 * Entry Price - Current Price)
            return round(size * (2 * entry_price - current_price), 2)
        else:
            raise ValueError(f"Unsupported position type: {position_type}")

    def calculate_leverage(self, size: float, collateral: float) -> Optional[float]:
        """
        Calculate leverage based on size and collateral.
        """
        if size <= 0 or collateral <= 0:
            return None
        return round(size / collateral, 2)

    def calculate_liquid_distance(self, current_price: float, liquidation_price: float) -> float:
        """
        Calculate the distance between the current price and liquidation price.
        """
        return round(abs(liquidation_price - current_price), 2)

    def calculate_travel_percent(self, entry_price: float, current_price: float, liquidation_price: float) -> Optional[float]:
        """
        Calculate the travel percentage based on entry price, current price, and liquidation price.
        """
        denominator = abs(entry_price - liquidation_price)
        if denominator == 0:
            return None  # Avoid division by zero
        travel_percent = ((current_price - entry_price) / (entry_price - liquidation_price)) * 100
        return round(travel_percent, 2)

    def calculate_heat_points(self, position: dict) -> Optional[float]:
        """
        Calculate heat points based on size, leverage, and collateral.
        """
        size = position.get('size', 0)
        leverage = position.get('leverage', 0)
        collateral = position.get('collateral', 0)
        if collateral == 0:
            return None  # Avoid division by zero
        heat_points = (size * leverage) / collateral
        return round(heat_points, 2)

    def calculate_value(self, position: dict) -> float:
        """
        Calculate position value based on size and current price.
        """
        size = position.get("size", 0)
        current_price = position.get("current_price", 0)
        position_type = position.get("position_type", "long").lower()

        if position_type == "long":
            return round(size * current_price, 2)
        elif position_type == "short":
            return round(size * (2 * position.get("entry_price", 0) - current_price), 2)
        return 0.0

    def get_color(self, value: float, metric: str) -> str:
        """
        Map a value to a color based on predefined ranges for the metric.
        """
        if metric not in self.color_ranges:
            return "white"  # Default color if no range defined

        for lower, upper, color in self.color_ranges[metric]:
            if lower <= value < upper:
                return color

        return "red"  # Default to red for out-of-range values

    def validate_position(self, position: dict):
        """
        Validate a position's required fields and ensure no invalid values.
        """
        required_fields = ["asset", "position_type", "leverage", "value", "size", "collateral", "entry_price"]
        missing_fields = [field for field in required_fields if field not in position]

        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        # Additional checks
        if float(position.get("size", 0)) <= 0:
            raise ValueError("Size must be greater than zero.")
        if float(position.get("collateral", 0)) <= 0:
            raise ValueError("Collateral must be greater than zero.")

    def prepare_positions_for_display(self, positions: list) -> list:
        """
        Preprocess positions to include calculated fields (e.g., heat index, colors).
        """
        processed_positions = []
        for pos in positions:
            # Validate position
            self.validate_position(pos)

            # Add calculated fields
            pos["heat_points"] = self.calculate_heat_points(pos)
            pos["travel_percent_color"] = self.get_color(pos.get("travel_percent", 0), "travel_percent")
            pos["heat_index_color"] = self.get_color(pos["heat_points"], "heat_index")
            pos["collateral_color"] = self.get_color(pos.get("collateral", 0), "collateral")
            pos["liquid_distance"] = self.calculate_liquid_distance(
                pos.get("current_price", 0), pos.get("liquidation_price", 0)
            )
            pos["value"] = self.calculate_value(pos)

            processed_positions.append(pos)

        return processed_positions

