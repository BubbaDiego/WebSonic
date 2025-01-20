import time
import logging
import os
from typing import List, Dict, Any, Optional
import json
from data.data_locker import DataLocker
from calc_services import CalcServices
from data.config import AppConfig
from data.hybrid_config_manager import load_config_hybrid

logger = logging.getLogger("AlertManagerLogger")
logger.setLevel(logging.DEBUG)


class AlertManager:
    def __init__(self,
                 db_path: str = "data/mother_brain.db",
                 poll_interval: int = 60,
                 config_path: str = "sonic_config.json"):
        """
        :param db_path: Path to your SQLite DB.
        :param poll_interval: How often (seconds) to poll the DB for alert checks.
        :param config_path: Path to your sonic_config JSON.
        """
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.config_path = config_path

        # Setup data locker, calc, etc.
        self.data_locker = DataLocker(db_path=self.db_path)
        self.calc_services = CalcServices()

        # Load hybrid config using the function from hybrid_config_manager
        self.db_conn = self.data_locker.get_db_connection()
        self.config_data = load_config_hybrid(self.config_path, self.db_conn)


        # If you want a quick and dirty enable/disable map per metric:
        # (you could also store these directly in your config JSON).
        self.alert_enabled_flags = {
            "heat_index": True,
            "travel_percent": True,
            "value": True,
            "collateral": True,
            "size": True,
            "liquidation_distance": True,
            "leverage": True,
        }

        # Keep track of last triggered to avoid spam
        self.last_triggered_times = {}  # e.g. { (pos_id, metric_name): timestamp }

        logger.info("AlertManager initialized with poll_interval=%s, config_path=%s",
                    poll_interval, config_path)

    def run(self):
        """ Continuously polls for alerts, respecting config. """
        while True:
            try:
                self.check_alerts()
            except Exception as e:
                logger.error("Error in check_alerts loop: %s", e, exc_info=True)
            time.sleep(self.poll_interval)

    def check_alerts(self):
        """
        Main logic to:
          1) Check if alert monitoring is enabled
          2) Read positions, do aggregator
          3) Compare to threshold ranges in config
          4) Fire notifications if out of range
        """

        # 1) Check if alert monitoring is globally enabled
        if not self.config_data.system_config.alert_monitor_enabled:
            logger.debug("Alert monitoring disabled by config. Skipping checks.")
            return

        logger.debug("Polling DB for positions/prices...")

        # 2) Read positions from DB
        positions_data = self.data_locker.read_positions()

        # Optionally read prices if you need them:
        # prices_data = self.data_locker.read_prices()

        # Prepare positions with aggregator logic
        positions_data = self.calc_services.prepare_positions_for_display(positions_data)

        # 3) Evaluate conditions for each position/metric using ranges from config
        #    We'll replicate the same approach as web_app's get_alert_status or similar.
        for pos in positions_data:
            pos_id = pos.get("id")
            self.check_metric_alert(
                pos_id, pos, "heat_index", self.config_data.alert_ranges.heat_index_ranges
            )
            self.check_metric_alert(
                pos_id, pos, "collateral", self.config_data.alert_ranges.collateral_ranges
            )
            self.check_metric_alert(
                pos_id, pos, "value", self.config_data.alert_ranges.value_ranges
            )
            self.check_metric_alert(
                pos_id, pos, "size", self.config_data.alert_ranges.size_ranges
            )
            self.check_metric_alert(
                pos_id, pos, "current_travel_percent", self.config_data.alert_ranges.travel_percent_ranges,
                metric_key="travel_percent"  # a small override for naming
            )
            # If you track liquidation_distance or something else
            self.check_metric_alert(
                pos_id, pos, "liquid_distance", self.config_data.alert_ranges.liquidation_distance_ranges,
                metric_key="liquidation_distance"
            )
            # If you store a 'leverage' field in the position or you can recalc it
            if "leverage" in pos:
                self.check_metric_alert(
                    pos_id, pos, "leverage", self.config_data.alert_ranges.leverage_ranges
                )

    def check_metric_alert(self,
                           pos_id: str,
                           position: Dict[str, Any],
                           field_name: str,
                           range_obj,
                           metric_key: Optional[str] = None):
        """
        For a given position and metric, check if it's in 'warning' or 'danger' range.
        If so, trigger an alert unless it's disabled or on cooldown.
        :param pos_id: The ID of the position
        :param position: The entire position dict
        :param field_name: The key in `position` (like 'heat_index', 'value', 'size')
        :param range_obj: The relevant config object, e.g. self.config_data.alert_ranges.value_ranges
        :param metric_key: If the name in `alert_enabled_flags` differs from `field_name`, supply it here.
        """
        if metric_key is None:
            metric_key = field_name  # fallback

        # Check if this metric is globally enabled
        if not self.alert_enabled_flags.get(metric_key, False):
            return  # skip

        val = float(position.get(field_name, 0.0))
        if val == 0.0:
            return  # or handle zero specially

        # We'll adapt from your "get_alert_status" logic:
        low = range_obj.low if range_obj.low is not None else 0.0
        medium = range_obj.medium if range_obj.medium is not None else 0.0
        high = range_obj.high if range_obj.high is not None else float("inf")

        # Example if the logic is "if value <= low => normal; if <= medium => warning; else => danger"
        # But watch out for negative ranges like travel_percent. Adjust as needed:
        alert_status = self.get_alert_status(val, low, medium, high)

        if alert_status == "bg-warning":
            # Maybe you only do an email or log for warnings
            self.trigger_alert(pos_id, metric_key, val, alert_level="warning",
                               channel_list=["Log", "Email"])
        elif alert_status == "bg-danger":
            # Danger might mean all channels
            self.trigger_alert(pos_id, metric_key, val, alert_level="danger",
                               channel_list=["SMS", "Email", "Log", "Local"])

    def get_alert_status(self, value: float, low: float, medium: float, high: float) -> str:
        """
        Mimics your web_app approach:
          - if value <= low => normal/no alert
          - elif value <= medium => 'bg-warning'
          - else => 'bg-danger'
        Adjust logic for negative thresholds if needed.
        """
        if high is None:
            high = float("inf")

        # *Important*: If your travel % ranges have negative low/medium,
        # you might want a different approach (like if value < -50 => danger).
        # For simplicity, I'm just reusing the function from your example logic:
        if value <= low:
            return ""  # normal
        elif value <= medium:
            return "bg-warning"
        else:
            return "bg-danger"

    def trigger_alert(self,
                      position_id: str,
                      metric_key: str,
                      current_value: float,
                      alert_level: str,
                      channel_list: List[str]):
        """
        Fire an alert for a given position/metric if not on cooldown.
        """
        # 1) Check cooldown
        key = (position_id, metric_key)
        now = time.time()
        cooldown = 600  # 10 min for example
        last_trig = self.last_triggered_times.get(key, 0)
        if (now - last_trig) < cooldown:
            logger.debug("Alert for (pos=%s, metric=%s) suppressed due to cooldown.", position_id, metric_key)
            return

        self.last_triggered_times[key] = now

        # 2) Format a message
        message = f"Alert: Position {position_id} metric={metric_key} value={current_value:.2f} is in '{alert_level}' range."

        # 3) Send via desired channels
        for channel in channel_list:
            if channel == "SMS":
                self.send_sms(message)
            elif channel == "Email":
                self.send_email(message)
            elif channel == "Local":
                self.send_local_notification(message)
            elif channel == "Log":
                self.send_log_alert(message)
            else:
                logger.warning("Unknown channel: %s", channel)

    # --------------------------------------------------------
    # Notification Channels
    # --------------------------------------------------------
    def send_sms(self, message: str):
        logger.warning("[SMS Alert] %s", message)
        # Twilio or other SMS logic goes here

    def send_email(self, message: str):
        logger.warning("[Email Alert] %s", message)
        # SMTP or other email logic goes here
        # You might use self.config_data.system_config.email_config for details

    def send_local_notification(self, message: str):
        logger.warning("[Local Notification] %s", message)
        # Windows beep or cross-platform notification goes here

    def send_log_alert(self, message: str):
        logger.warning("[Log Alert] %s", message)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    manager = AlertManager(
        db_path=os.path.abspath("data/mother_brain.db"),
        poll_interval=60,  # poll every minute
        config_path="sonic_config.json"
    )
    manager.run()
