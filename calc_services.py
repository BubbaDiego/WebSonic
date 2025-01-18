from typing import Optional, List, Dict

class CalcServices:
    def __init__(self):
        # Ranges for color mapping
        self.color_ranges = {
            "travel_percent": [(0, 25, "green"), (25, 50, "yellow"), (50, 75, "orange"), (75, 100, "red")],
            "heat_index": [(0, 20, "blue"), (20, 40, "green"), (40, 60, "yellow"), (60, 80, "orange"), (80, 100, "red")],
            "collateral": [(0, 500, "lightgreen"), (500, 1000, "yellow"), (1000, 2000, "orange"), (2000, 10000, "red")]
        }

    # calc_services.py

    def calculate_value(self, position: dict) -> float:
        """
        Safely calculates the position value. If size <= 0 or current_price <= 0,
        logs a warning and returns 0.0 instead of raising.
        """
        size = position.get("size", 0.0)
        current_price = position.get("current_price", 0.0)
        entry_price = position.get("entry_price", 0.0)
        position_type = position.get("position_type", "Long").lower()

        if size <= 0 or current_price <= 0:
            print(f"[WARNING] Invalid size or current_price (size={size}, current_price={current_price}). "
                  "Returning value=0.0.")
            return 0.0

        if position_type == "long":
            return round(size * current_price, 2)
        elif position_type == "short":
            return round(size * (2 * entry_price - current_price), 2)
        else:
            print(f"[WARNING] Unsupported position type: {position_type}. Returning value=0.0.")
            return 0.0

    def calculate_leverage(self, size: float, collateral: float) -> Optional[float]:
        """
        Calculate leverage based on size and collateral.
        """
        if size <= 0 or collateral <= 0:
            return None
        return round(size / collateral, 2)

    def calculate_liquid_distance(self, current_price: float, liquidation_price: float) -> float:
        current_price = current_price if current_price is not None else 0.0
        liquidation_price = liquidation_price if liquidation_price is not None else 0.0
        return round(abs(liquidation_price - current_price), 2)

    @staticmethod
    def calculate_travel_percent(entry_price, current_price, liquidation_price, debug=False):
        try:
            # Validate inputs
            if entry_price is None or liquidation_price is None:
                raise ValueError("Entry price and liquidation price must be provided.")
            if not isinstance(entry_price, (int, float)) or not isinstance(liquidation_price,
                                                                           (int, float)) or not isinstance(
                    current_price, (int, float)):
                raise TypeError("All price inputs must be numeric.")

            # Calculate distances
            distance = liquidation_price - entry_price
            current_travel = current_price - entry_price

            # Avoid division by zero
            if distance == 0:
                raise ZeroDivisionError("Liquidation price and entry price cannot be equal.")

            # Calculate travel percentage
            travel_percent = (current_travel / distance) * 100

            # Optional debug logs
            if debug:
                print(
                    f"Entry Price: {entry_price}, Current Price: {current_price}, Liquidation Price: {liquidation_price}")
                print(f"Distance: {distance}, Current Travel: {current_travel}, Travel Percent: {travel_percent}")

            return travel_percent

        except Exception as e:
            # Log error and return 0.0 on failure
            print(f"Error calculating travel percent: {e}")
            return 0.0

    def calculate_heat_index(self, position: dict) -> Optional[float]:
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

    @staticmethod
    def calculate_totals(positions):
        """
        Calculate totals and averages for positions.
        """
        total_size = total_value = total_collateral = total_heat_index = 0
        total_heat_index_count = 0
        weighted_leverage_sum = weighted_travel_percent_sum = 0

        for pos in positions:
            try:
                size = pos.get('size', 0) or 0
                value = pos.get('value', 0) or 0
                collateral = pos.get('collateral', 0) or 0
                leverage = pos.get('leverage', 0) or 0
                travel_percent = pos.get('current_travel_percent', 0) or 0
                heat_index = pos.get('heat_points', 0) or 0

                total_size += size
                total_value += value
                total_collateral += collateral

                if heat_index:
                    total_heat_index += heat_index
                    total_heat_index_count += 1

                weighted_leverage_sum += leverage * size
                weighted_travel_percent_sum += travel_percent * size
            except Exception as e:
                print(f"Error calculating totals for position {pos.get('id', 'unknown')}: {e}")

        avg_heat_index = total_heat_index / total_heat_index_count if total_heat_index_count else 0
        avg_leverage = weighted_leverage_sum / total_size if total_size else 0
        avg_travel_percent = weighted_travel_percent_sum / total_size if total_size else 0

        return {
            "total_size": total_size,
            "total_value": total_value,
            "total_collateral": total_collateral,
            "avg_leverage": avg_leverage,
            "avg_travel_percent": avg_travel_percent,
            "avg_heat_index": avg_heat_index
        }

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
        required_fields = ["asset_type", "position_type", "leverage", "value", "size", "collateral", "entry_price"]
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
        For each position, skip or default if current_price/size is missing/zero,
        then fill aggregator fields like 'value', 'heat_index', etc.
        """
        processed_positions = []
        for pos in positions:
            # 2.1) If current_price is missing (None) or <= 0, you can decide how to handle:
            current_price = pos.get("current_price")
            size = pos.get("size", 0.0)

            if not current_price or current_price <= 0:
                # EITHER skip the full aggregator logic
                # or set pos["value"] to 0.0 explicitly here:
                pos["value"] = 0.0
                print(
                    f"[INFO] Skipping full aggregator for pos id={pos.get('id')} due to invalid current_price={current_price}")
            else:
                # 2.2) Otherwise, do normal aggregator logic:
                # => calls our new safe calculate_value
                pos["value"] = self.calculate_value(pos)

            # 2.3) Example: if you also want to compute heat_index anyway:
            pos["heat_index"] = self.calculate_heat_index(pos) or 0.0

            # 2.4) Travel percent logic, etc.
            if "current_travel_percent" not in pos or pos["current_travel_percent"] is None:
                pos["current_travel_percent"] = self.calculate_travel_percent(
                    pos.get("entry_price", 0.0),
                    pos.get("current_price", 0.0),
                    pos.get("liquidation_price", 0.0)
                ) or 0.0

            # 2.5) Liquid distance
            pos["liquid_distance"] = self.calculate_liquid_distance(
                pos.get("current_price", 0.0),
                pos.get("liquidation_price", 0.0)
            )

            # 2.6) Example color-coded fields
            pos["travel_percent_color"] = self.get_color(pos["current_travel_percent"], "travel_percent")
            pos["heat_index_color"] = self.get_color(pos["heat_index"], "heat_index")

            processed_positions.append(pos)

        return processed_positions
    def calculate_balance_metrics(self, positions: List[Dict]) -> Dict:
        """
        Calculate metrics for the balance report (short vs. long comparisons).
        """
        total_short_size = total_short_collateral = total_short_value = 0
        total_long_size = total_long_collateral = total_long_value = 0

        for pos in positions:
            size = pos.get("size", 0)
            collateral = pos.get("collateral", 0)
            value = pos.get("value", 0)
            if pos["position_type"].lower() == "short":
                total_short_size += size
                total_short_collateral += collateral
                total_short_value += value
            elif pos["position_type"].lower() == "long":
                total_long_size += size
                total_long_collateral += collateral
                total_long_value += value

        total_size = total_short_size + total_long_size
        total_collateral = total_short_collateral + total_long_collateral
        total_value = total_short_value + total_long_value

        return {
            "total_short_size": total_short_size,
            "total_long_size": total_long_size,
            "total_short_collateral": total_short_collateral,
            "total_long_collateral": total_long_collateral,
            "total_short_value": total_short_value,
            "total_long_value": total_long_value,
            "total_size": total_size,
            "total_collateral": total_collateral,
            "total_value": total_value
        }

