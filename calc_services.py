# calc_services.py

from typing import Optional, List, Dict

class CalcServices:
    """
    This class provides all aggregator/analytics logic for positions:
     - Calculating value (long/short),
     - Leverage,
     - Travel %,
     - Heat index,
     - Summaries/Totals,
     - Optional color coding for display.
    """

    def __init__(self):
        # Ranges for color coding (used by get_color).
        # Adjust as needed or remove if you don't want color-coded fields.
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
        Safely calculates a position's value based on:
          - size,
          - current_price,
          - entry_price,
          - position_type (long/short).
        If size or current_price <= 0, returns 0.0 with a warning.
        """
        size = float(position.get("size", 0.0))
        current_price = float(position.get("current_price", 0.0))
        entry_price = float(position.get("entry_price", 0.0))
        position_type = position.get("position_type", "Long").lower()

        if size <= 0 or current_price <= 0:
            print(f"[WARNING] Invalid size={size} or current_price={current_price}. Returning value=0.0.")
            return 0.0

        if position_type == "long":
            # Simple: value = size * current_price
            return round(size * current_price, 2)
        elif position_type == "short":
            # Example short formula: size * (2*entry_price - current_price)
            # Adjust as needed for your actual short logic
            return round(size * (2 * entry_price - current_price), 2)
        else:
            print(f"[WARNING] Unsupported position type: {position_type}. Returning value=0.0.")
            return 0.0

    def calculate_leverage(self, size: float, collateral: float) -> Optional[float]:
        """
        Leverage = size / collateral (assuming 'size' is notional).
        Returns None if size <= 0 or collateral <= 0 to avoid dividing by zero.
        """
        if size <= 0 or collateral <= 0:
            return None
        return round(size / collateral, 2)

    def calculate_travel_percent(self,
                                 entry_price: float,
                                 current_price: float,
                                 liquidation_price: float,
                                 debug=False) -> float:
        """
        Calculate how far along we are between entry_price and liquidation_price,
        as a percentage.
        travel% = ((current_price - entry_price) / (liquidation_price - entry_price)) * 100
        Returns 0.0 if there's any error (zero/negative distance, bad inputs, etc.).
        """
        try:
            if entry_price is None or liquidation_price is None:
                raise ValueError("Entry price and liquidation price must be provided.")

            if not all(isinstance(x, (int, float)) for x in [entry_price, current_price, liquidation_price]):
                raise TypeError("All price inputs must be numeric.")

            distance = liquidation_price - entry_price
            current_travel = current_price - entry_price

            if distance == 0:
                raise ZeroDivisionError("liquidation_price and entry_price cannot be equal.")

            travel_percent = (current_travel / distance) * 100
            if debug:
                print(f"[DEBUG] entry={entry_price}, current={current_price}, liq={liquidation_price}, travel%={travel_percent}")

            return travel_percent

        except Exception as e:
            print(f"[ERROR] calculate_travel_percent failed: {e}. Returning 0.0.")
            return 0.0

    def calculate_liquid_distance(self, current_price: float, liquidation_price: float) -> float:
        """
        Absolute difference between current_price and liquidation_price.
        Defaults to 0.0 if either is missing.
        """
        if current_price is None:
            current_price = 0.0
        if liquidation_price is None:
            liquidation_price = 0.0
        return round(abs(liquidation_price - current_price), 2)

    def calculate_heat_index(self, position: dict) -> Optional[float]:
        """
        Example "heat index" = (size * leverage) / collateral, or some variation.
        Returns None if collateral <= 0, else a float.
        """
        size = float(position.get("size", 0.0) or 0.0)
        leverage = float(position.get("leverage", 0.0) or 0.0)
        collateral = float(position.get("collateral", 0.0) or 0.0)

        if collateral <= 0:
            return None  # or 0.0, depending on your preference
        hi = (size * leverage) / collateral
        return round(hi, 2)

    def prepare_positions_for_display(self, positions: List[dict]) -> List[dict]:
        """
        Main aggregator entry point:
         - Merges the above calculations (value, leverage, heat index, travel_percent).
         - Optionally applies color coding to certain fields (e.g. travel %).
         - Returns a list of processed position dicts with aggregator fields set.
        """
        processed_positions = []
        for pos in positions:
            # 1) Value
            current_price = float(pos.get("current_price") or 0.0)
            if current_price > 0:
                pos["value"] = self.calculate_value(pos)
            else:
                pos["value"] = 0.0  # skip aggregator logic if price is invalid

            # 2) Leverage
            size = float(pos.get("size", 0.0))
            collateral = float(pos.get("collateral", 0.0))
            pos["leverage"] = self.calculate_leverage(size, collateral) or 0.0

            # 3) Heat Index
            pos["heat_index"] = self.calculate_heat_index(pos) or 0.0

            # 4) Travel %
            # if current_travel_percent isn't already set or is None, compute it
            if "current_travel_percent" not in pos or pos["current_travel_percent"] is None:
                entry_price = float(pos.get("entry_price", 0.0))
                liquidation_price = float(pos.get("liquidation_price", 0.0))
                pos["current_travel_percent"] = self.calculate_travel_percent(
                    entry_price, current_price, liquidation_price
                )

            # 5) Liquid distance
            pos["liquid_distance"] = self.calculate_liquid_distance(
                current_price, pos.get("liquidation_price", 0.0)
            )

            # 6) Color-coded fields (optional)
            pos["travel_percent_color"] = self.get_color(pos["current_travel_percent"], "travel_percent")
            pos["heat_index_color"] = self.get_color(pos["heat_index"], "heat_index")

            processed_positions.append(pos)

        return processed_positions

    def calculate_totals(self, positions: List[dict]) -> dict:
        """
        Aggregates totals/averages across all positions, e.g. sum of size/value,
        average leverage, average travel percent, etc.
        """
        total_size = 0.0
        total_value = 0.0
        total_collateral = 0.0
        total_heat_index = 0.0
        heat_index_count = 0

        # We'll do "weighted" sums for leverage/travel% if that makes sense
        weighted_leverage_sum = 0.0
        weighted_travel_percent_sum = 0.0

        for pos in positions:
            size = float(pos.get("size") or 0.0)
            value = float(pos.get("value") or 0.0)
            collateral = float(pos.get("collateral") or 0.0)
            leverage = float(pos.get("leverage") or 0.0)
            travel_percent = float(pos.get("current_travel_percent") or 0.0)
            heat_index = float(pos.get("heat_index") or 0.0)

            total_size += size
            total_value += value
            total_collateral += collateral

            if heat_index != 0.0:
                total_heat_index += heat_index
                heat_index_count += 1

            weighted_leverage_sum += (leverage * size)
            weighted_travel_percent_sum += (travel_percent * size)

        # Calculate averages
        avg_heat_index = total_heat_index / heat_index_count if heat_index_count > 0 else 0.0
        avg_leverage = weighted_leverage_sum / total_size if total_size > 0 else 0.0
        avg_travel_percent = weighted_travel_percent_sum / total_size if total_size > 0 else 0.0

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
        Returns a color string based on the metric's predefined ranges in self.color_ranges.
        If the metric isn't found, defaults to "white".
        """
        if metric not in self.color_ranges:
            return "white"
        for (lower, upper, color) in self.color_ranges[metric]:
            if lower <= value < upper:
                return color
        # If it exceeds all upper bounds, default to the last color or "red"
        return "red"
