# config/sys_config_cli.py (or wherever you want)
import json
import os
import pyfiglet
from rich.console import Console
from rich.table import Table
from data.config import AppConfig

class SysConfigCLI:
    """
    A CLI wrapper that uses AppConfig behind the scenes.
    """
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.app_config = AppConfig.load(config_path)

    def load_config(self):
        self.app_config = AppConfig.load(self.config_path)

    def display_config_table(self):
        """
        Display the config parameters in a nice table.
        """
        console = Console()
        table = Table(title="System Configuration")

        table.add_column("Parameter", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        # System Config
        table.add_row("[bold]System Config[/bold]", "")
        sc = self.app_config.system_config
        table.add_row("  logging_enabled", str(sc.logging_enabled))
        table.add_row("  log_level", str(sc.log_level))
        table.add_row("  console_output", str(sc.console_output))
        table.add_row("  log_file", str(sc.log_file))
        table.add_row("  db_path", str(sc.db_path))
        table.add_row("  price_monitor_enabled", str(sc.price_monitor_enabled))
        table.add_row("  alert_monitor_enabled", str(sc.alert_monitor_enabled))
        table.add_row("  sonic_monitor_loop_time", str(sc.sonic_monitor_loop_time))
        table.add_row("  last_price_update_time", str(sc.last_price_update_time))

        # Price Config
        table.add_row("[bold]Price Config[/bold]", "")
        pc = self.app_config.price_config
        table.add_row("  assets", str(pc.assets))
        table.add_row("  currency", str(pc.currency))
        table.add_row("  fetch_timeout", str(pc.fetch_timeout))
        table.add_row("  backoff", str(pc.backoff))

        # API Config
        table.add_row("[bold]API Config[/bold]", "")
        api = self.app_config.api_config
        table.add_row("  coingecko_api_enabled", str(api.coingecko_api_enabled))
        table.add_row("  kucoin_api_enabled", str(api.kucoin_api_enabled))
        table.add_row("  coinmarketcap_api_enabled", str(api.coinmarketcap_api_enabled))
        table.add_row("  binance_api_enabled", str(api.binance_api_enabled))

        # Alert Ranges
        table.add_row("[bold]Alert Ranges[/bold]", "")
        # Just an example, you might prefer a loop:
        ar = self.app_config.alert_ranges
        table.add_row("  heat_index.low", str(ar.heat_index_ranges.low))
        table.add_row("  heat_index.medium", str(ar.heat_index_ranges.medium))
        table.add_row("  heat_index.high", str(ar.heat_index_ranges.high))
        # And so on for the rest

        console.print(table)

    def import_config(self, import_path):
        """
        Overwrite your existing config with the new config file.
        """
        new_cfg = AppConfig.load(import_path)
        self.app_config = new_cfg
        # Save it to disk if you want
        self.app_config.save(self.config_path)
        print(f"Configuration imported from {import_path}")

    def export_config(self, export_path):
        """
        Export the current config to a specified JSON file in Pydantic form.
        """
        self.app_config.save(export_path)
        print(f"Configuration exported to {export_path}")
