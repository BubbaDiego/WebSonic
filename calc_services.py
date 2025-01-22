# calc_services.py

from typing import Optional, List, Dict
import sqlite3

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

    def calculate_value(self, position):
        # Since size is *already* in USD, just return it
        size = float(position.get("size", 0.0))
        return round(size, 2)

    def calculate_leverage(self, size: float, collateral: float) -> float:
        if size <= 0 or collateral <= 0:
            return 0.0
        return round(size / collateral, 2)

    def calculate_travel_percent(
            self,
            position_type: str,
            entry_price: float,
            current_price: float,
            liquidation_price: float,
            profit_price: float
    ) -> float:
        """
        Example function that calculates travel_percent for both LONG and SHORT.
        Adjust as needed to fit your exact logic.
        """
        ptype = position_type.upper()

        # Basic checks
        if entry_price <= 0 or liquidation_price <= 0:
            return 0.0

        # Helper to avoid dividing by zero
        def pct_of_range(numer, denom):
            return (numer / denom) * 100 if denom else 0.0

        # Default to 0.0 so we always have something to return
        travel_percent = 0.0

        if ptype == "LONG":
            if current_price < entry_price:
                # Negative side => -100% at liquidation
                denom = (entry_price - liquidation_price)
                numer = (current_price - entry_price)
                travel_percent = pct_of_range(numer, -abs(denom))
            else:
                # Positive side => +100% at profit_price
                denom = (profit_price - entry_price)
                numer = (current_price - entry_price)
                travel_percent = pct_of_range(numer, denom)
        else:  # SHORT
            if current_price > entry_price:
                # Negative side => -100% at liquidation
                denom = (liquidation_price - entry_price)
                numer = (entry_price - current_price)
                travel_percent = pct_of_range(numer, -abs(denom))
            else:
                # Positive side => +100% at profit_price
                denom = abs(entry_price - profit_price)
                numer = (entry_price - current_price)
                travel_percent = pct_of_range(numer, denom)

        return travel_percent

    def aggregator_positions(
            self,
            positions: List[dict],
            db_path: str
    ) -> List[dict]:
        """
        Does it all:
          1) Derives profit_price if necessary,
          2) Calculates travel_percent,
          3) Overwrites positions in-memory,
          4) Updates DB so 'current_travel_percent' is persisted,
          5) Returns the updated list of positions.
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for pos in positions:
            position_type = (pos.get("position_type") or "LONG").upper()
            entry_price = float(pos.get("entry_price", 0.0))
            current_price = float(pos.get("current_price", 0.0))
            liquidation_price = float(pos.get("liquidation_price", 0.0))

            # 1) Derive or pick a profit_price
            if position_type == "LONG":
                profit_price = entry_price * 2
            else:
                profit_price = entry_price / 2

            # 2) Calculate
            travel_percent = self.calculate_travel_percent(
                position_type,
                entry_price,
                current_price,
                liquidation_price,
                profit_price
            )

            # 3) Overwrite in-memory
            pos["current_travel_percent"] = travel_percent

            # 4) Update DB
            try:
                cursor.execute("""
                    UPDATE positions
                       SET current_travel_percent = ?
                     WHERE id = ?
                """, (travel_percent, pos["id"]))
            except Exception as e:
                print(f"Error updating travel_percent for position {pos['id']}: {e}")

        conn.commit()
        conn.close()

        # 5) Return updated positions
        return positions

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
        processed_positions = []

        for idx, pos in enumerate(positions, start=1):
            print(f"\n[DEBUG] Position #{idx} BEFORE aggregator => {pos}")

            # 1) Position type logic
            raw_ptype = pos.get("position_type", "LONG")
            ptype_lower = raw_ptype.strip().lower()
            if "short" in ptype_lower:
                position_type = "SHORT"
            else:
                position_type = "LONG"

            # 2) Grab fields
            entry_price = float(pos.get("entry_price", 0.0))
            current_price = float(pos.get("current_price", 0.0))
            collateral = float(pos.get("collateral", 0.0))
            size = float(pos.get("size", 0.0))
            liquidation_price = float(pos.get("liquidation_price", 0.0))

            # 3) Calculate 'calculate_travel_percent'
            pos["calculate_travel_percent"] = self.calculate_travel_percent(
                position_type,
                entry_price,
                current_price,
                liquidation_price,
                profit_price=pos.get("profit_price")
            )

            # ---------------------------
            # NEW CODE HERE
            # Overwrite current_travel_percent with that newly computed value:
            # ---------------------------
            pos["current_travel_percent"] = pos["calculate_travel_percent"]
            # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
            # This is the missing link: now 'current_travel_percent' won't stay at zero!
            # ---------------------------

            print(f"[DEBUG] Normalized => type={position_type}, "
                  f"entry={entry_price}, current={current_price}, "
                  f"collat={collateral}, size={size}, "
                  f"travel_percent={pos['calculate_travel_percent']}")

            # (rest of aggregator logic)...
            # PnL, value, leverage, heat_index, etc.
            if entry_price <= 0:
                pnl = 0.0
            else:
                token_count = size / entry_price
                if position_type == "LONG":
                    pnl = (current_price - entry_price) * token_count
                else:
                    pnl = (entry_price - current_price) * token_count

            pos["value"] = round(collateral + pnl, 2)
            if collateral > 0:
                pos["leverage"] = round(size / collateral, 2)
            else:
                pos["leverage"] = 0.0

            pos["heat_index"] = self.calculate_heat_index(pos) or 0.0

            print(f"[DEBUG] Position #{idx} AFTER aggregator => {pos}")

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
