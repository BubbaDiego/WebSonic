# calc_services.py

from typing import Optional, List, Dict
import math

class CalcServices:
    def __init__(self):
        # Ranges for color mapping
        self.color_ranges = {
            "travel_percent": [
                (0, 25, "green"),
                (25, 50, "yellow"),
                (50, 75, "orange"),
                (75, 100, "red")
            ],
            "heat_index": [
                (0, 20, "blue"),
                (20, 40, "green"),
                (40, 60, "yellow"),
                (60, 80, "orange"),
                (80, 100, "red")
            ],
            "collateral": [
                (0, 500, "lightgreen"),
                (500, 1000, "yellow"),
                (1000, 2000, "orange"),
                (2000, 10000, "red")
            ]
        }

    def calculate_value(self, position: dict) -> float:
        """
        Calculate the value of a position based on size, entry price, current price, and position type.
        Supports both long and short positions.
        """
        size = float(position.get("size", 0))
        entry_price = float(position.get("entry_price", 0))
        current_price = float(position.get("current_price", 0))
        position_type = position.get("position_type", "Long").lower()

        if size <= 0 or current_price <= 0:
            # Optionally skip or raise an error, but we'll raise here:
            raise ValueError("Size and current_price must be > 0 for a valid position value calculation.")

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
        Safely calculate the absolute difference between liquidation and current price,
        defaulting to 0.0 if either is None or not numeric.
        """
        # Force them to numeric in case they're None
        current_price = current_price if current_price is not None else 0.0
        liquidation_price = liquidation_price if liquidation_price is not None else 0.0

        return round(abs(liquidation_price - current_price), 2)

    def calculate_travel_percent(self, entry_price: float, current_price: float, liquidation_price: float) -> Optional[float]:
        """
        Calculate the travel percentage based on entry price, current price, and liquidation price.
        Returns None if denominator is zero to avoid division by zero.
        """
        # Also guard against None:
        entry_price = entry_price if entry_price is not None else 0.0
        current_price = current_price if current_price is not None else 0.0
        liquidation_price = liquidation_price if liquidation_price is not None else 0.0

        denominator = abs(entry_price - liquidation_price)
        if denominator == 0:
            return None
        travel_percent = ((current_price - entry_price) / (entry_price - liquidation_price)) * 100
        return round(travel_percent, 2)

    def calculate_heat_index(self, position: dict) -> Optional[float]:
        """
        Replaces 'heat_points' logic with 'heat_index'.
        Based on size, leverage, and collateral. Returns None if invalid.
        """
        size = position.get('size', 0)
        leverage = position.get('leverage', 0)
        collateral = position.get('collateral', 0)

        if not collateral or float(collateral) <= 0:
            return None
        heat_index = (size * leverage) / collateral
        return round(heat_index, 2)

    @staticmethod
    def calculate_totals(positions):
        """
        Aggregates totals for size, value, collateral, plus avg_leverage, avg_travel_percent, and avg_heat_index.
        """
        total_size = 0.0
        total_value = 0.0
        total_collateral = 0.0
        total_heat_index = 0.0
        heat_index_count = 0

        weighted_leverage_sum = 0.0
        weighted_travel_percent_sum = 0.0

        for pos in positions:
            size = pos.get("size", 0.0)
            value = pos.get("value", 0.0)
            collateral = pos.get("collateral", 0.0)
            leverage = pos.get("leverage", 0.0)
            travel_percent = pos.get("current_travel_percent", 0.0)
            heat_index = pos.get("heat_index", 0.0)

            total_size += size
            total_value += value
            total_collateral += collateral

            if heat_index:
                total_heat_index += heat_index
                heat_index_count += 1

            weighted_leverage_sum += (leverage * size)
            weighted_travel_percent_sum += (travel_percent * size)

        avg_heat_index = total_heat_index / heat_index_count if heat_index_count else 0.0
        avg_leverage = weighted_leverage_sum / total_size if total_size else 0.0
        avg_travel_percent = weighted_travel_percent_sum / total_size if total_size else 0.0

        return {
            "total_size": total_size,
            "total_value": total_value,
            "total_collateral": total_collateral,
            "avg_leverage": avg_leverage,
            "avg_travel_percent": avg_travel_percent,
            "avg_heat_index": avg_heat_index,
        }

    def get_color(self, value: float, metric: str) -> str:
        """
        Map a numeric value to a color based on predefined ranges for that metric.
        """
        if metric not in self.color_ranges:
            return "white"
        for lower, upper, color in self.color_ranges[metric]:
            if lower <= value < upper:
                return color
        return "red"

    def validate_position(self, position: dict):
        """
        Validate required fields, ensuring no invalid or missing data.
        """
        required_fields = [
            "asset_type",
            "position_type",
            "leverage",
            "value",
            "size",
            "collateral",
            "entry_price",
        ]
        missing_fields = [f for f in required_fields if f not in position]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        if float(position.get("size", 0)) <= 0:
            raise ValueError("Size must be greater than zero.")
        if float(position.get("collateral", 0)) <= 0:
            raise ValueError("Collateral must be greater than zero.")

    def prepare_positions_for_display(self, positions: list) -> list:
        """
        Preprocess each position to ensure numeric heat_index, travel_percent, etc.
        This is typically called before rendering templates, so Jinja doesn't see undefined or None fields.
        """
        processed_positions = []
        for pos in positions:
            # Validate required fields (optional, if you want to skip invalid data):
            # self.validate_position(pos)

            # Safely compute travel_percent if not present
            if "current_travel_percent" not in pos or pos["current_travel_percent"] is None:
                entry_price = pos.get("entry_price") or 0.0
                current_price = pos.get("current_price") or 0.0
                liquidation_price = pos.get("liquidation_price") or 0.0
                pos["current_travel_percent"] = self.calculate_travel_percent(
                    entry_price, current_price, liquidation_price
                ) or 0.0

            # Heat index
            pos["heat_index"] = self.calculate_heat_index(pos) or 0.0

            # Re-calc or confirm 'value'
            # If 'value' is missing or 0, you might recalc:
            if not pos.get("value"):
                pos["value"] = 0.0
                try:
                    pos["value"] = self.calculate_value(pos)
                except ValueError:
                    pass

            # Liquid distance
            current_price = pos.get("current_price", 0.0)
            liquidation_price = pos.get("liquidation_price", 0.0)
            pos["liquid_distance"] = self.calculate_liquid_distance(
                current_price,
                liquidation_price
            )

            # Example color-coded fields:
            pos["travel_percent_color"] = self.get_color(pos["current_travel_percent"], "travel_percent")
            pos["heat_index_color"] = self.get_color(pos["heat_index"], "heat_index")

            processed_positions.append(pos)

        return processed_positions
