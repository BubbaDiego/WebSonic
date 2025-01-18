# calc_services.py

from typing import Optional, List, Dict

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
        Safely calculate the position value based on size, entry_price, current_price, and position_type.
        Logs a warning and returns 0.0 if size <= 0 or current_price <= 0 (instead of raising an error).
        Supports both long and short positions.
        """
        size = float(position.get("size", 0.0))
        current_price = float(position.get("current_price", 0.0))
        entry_price = float(position.get("entry_price", 0.0))
        position_type = position.get("position_type", "Long").lower()

        if size <= 0 or current_price <= 0:
            print(f"[WARNING] Invalid size={size} or current_price={current_price}. Returning value=0.0.")
            return 0.0

        if position_type == "long":
            return round(size * current_price, 2)
        elif position_type == "short":
            # snippet #1 and #2 both used the same short formula:
            return round(size * (2 * entry_price - current_price), 2)
        else:
            print(f"[WARNING] Unsupported position type: {position_type}. Returning value=0.0.")
            return 0.0

    def calculate_leverage(self, size: float, collateral: float) -> Optional[float]:
        """
        Calculate leverage based on size and collateral.
        Returns None if size <= 0 or collateral <= 0.
        """
        if size <= 0 or collateral <= 0:
            return None
        return round(size / collateral, 2)

    def calculate_liquid_distance(self, current_price: float, liquidation_price: float) -> float:
        """
        Safely calculate the absolute difference between liquidation and current price,
        defaulting to 0.0 if either is None.
        """
        if current_price is None:
            current_price = 0.0
        if liquidation_price is None:
            liquidation_price = 0.0
        return round(abs(liquidation_price - current_price), 2)

    def calculate_travel_percent(self, entry_price, current_price, liquidation_price, debug=False) -> float:
        """
        Attempt to calculate the travel percentage. Returns 0.0 if there's any error
        or if denominator is zero. Use snippet #1's try/except style for robust handling.
        """
        try:
            if entry_price is None or liquidation_price is None:
                raise ValueError("Entry price and liquidation price must be provided.")
            # ensure numeric
            if not all(isinstance(x, (int, float)) for x in [entry_price, current_price, liquidation_price]):
                raise TypeError("All price inputs must be numeric.")

            distance = liquidation_price - entry_price
            current_travel = current_price - entry_price

            if distance == 0:
                raise ZeroDivisionError("liquidation_price and entry_price cannot be equal.")

            travel_percent = (current_travel / distance) * 100

            if debug:
                print(f"entry={entry_price}, current={current_price}, liq={liquidation_price}, travel%={travel_percent}")
            return travel_percent

        except Exception as e:
            print(f"[ERROR] calculate_travel_percent failed: {e}. Returning 0.0.")
            return 0.0

    def calculate_heat_index(self, position: dict) -> Optional[float]:
        """
        Calculate heat_index based on size, leverage, and collateral.
        Gracefully handle None by treating them as 0.0.
        """
        size = float(position.get('size', 0.0) or 0.0)
        leverage = float(position.get('leverage', 0.0) or 0.0)
        collateral = float(position.get('collateral', 0.0) or 0.0)

        if collateral <= 0:
            return None
        heat_index = (size * leverage) / collateral
        return round(heat_index, 2)


    @staticmethod
    def calculate_totals(positions: List[dict]) -> dict:
        """
        Aggregates totals for size, value, collateral, plus avg_leverage,
        avg_travel_percent, and avg_heat_index.
        Safely converts None to 0.0 for each numeric field.
        """
        total_size = 0.0
        total_value = 0.0
        total_collateral = 0.0
        total_heat_index = 0.0
        heat_index_count = 0

        weighted_leverage_sum = 0.0
        weighted_travel_percent_sum = 0.0

        for pos in positions:
            # Safely convert possibly None fields to 0.0
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
        Merges snippet #1 and #2 approach.
        """
        required_fields = [
            "asset_type",
            "position_type",
            "leverage",
            "value",
            "size",
            "collateral",
            "entry_price"
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
        Merges snippet #1 and #2 logic:
          - If current_price <= 0 => skip aggregator logic, set 'value' = 0.0 (like snippet #1).
          - Otherwise, recalc value, heat_index, travel_percent, etc. (like snippet #2).
        """
        processed_positions = []
        for pos in positions:
            current_price = float(pos.get("current_price") or 0.0)
            size = float(pos.get("size", 0.0))

            # If invalid current_price, skip aggregator
            if current_price <= 0:
                pos["value"] = 0.0
                print(f"[INFO] Skipping aggregator for pos id={pos.get('id')} due to invalid current_price={current_price}")
            else:
                # Normal aggregator logic
                pos["value"] = self.calculate_value(pos)

            # Heat index
            pos["heat_index"] = self.calculate_heat_index(pos) or 0.0

            # Travel percent
            if "current_travel_percent" not in pos or pos["current_travel_percent"] is None:
                entry_price = float(pos.get("entry_price", 0.0))
                liquidation_price = float(pos.get("liquidation_price", 0.0))
                pos["current_travel_percent"] = self.calculate_travel_percent(
                    entry_price, current_price, liquidation_price
                )

            # Liquid distance
            pos["liquid_distance"] = self.calculate_liquid_distance(current_price, pos.get("liquidation_price", 0.0))

            # Example color-coded fields:
            pos["travel_percent_color"] = self.get_color(pos["current_travel_percent"], "travel_percent")
            pos["heat_index_color"] = self.get_color(pos["heat_index"], "heat_index")

            processed_positions.append(pos)

        return processed_positions

    def calculate_balance_metrics(self, positions: List[Dict]) -> Dict:
        """
        Preserves snippet #1's optional method to differentiate short vs long totals.
        """
        total_short_size = total_short_collateral = total_short_value = 0.0
        total_long_size = total_long_collateral = total_long_value = 0.0

        for pos in positions:
            size = float(pos.get("size", 0.0))
            collateral = float(pos.get("collateral", 0.0))
            value = float(pos.get("value", 0.0))
            ptype = pos.get("position_type", "Long").lower()

            if ptype == "short":
                total_short_size += size
                total_short_collateral += collateral
                total_short_value += value
            elif ptype == "long":
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
