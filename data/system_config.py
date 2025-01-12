
import os
import json
import pyfiglet
from rich.console import Console
from rich.table import Table

class SysConfig:
    """
    A class to handle system configuration by reading various files from different paths and storing them as attributes.
    """

    def __init__(self, config_path):
        self.config_path = config_path
        self.system_config = {}
        self.api_config = {}
        self.notification_config = {}
        self.price_config = {}
        self.alert_config = {}
        self.input_paths = {}
        self.output_paths = {}
        self.load_config()

    def load_config(self):
        """
        Load the configuration from the specified path and parse it into the class attributes.
        """
        with open(self.config_path, 'r') as file:
            config_data = json.load(file)
            self.system_config = config_data.get('system_config', {})
            self.api_config = config_data.get('api_config', {})
            self.notification_config = config_data.get('notification_config', {})
            self.price_config = config_data.get('price_config', {})
            self.alert_config = config_data.get('alert_config', {})
            self.input_paths = config_data.get('input_paths', {})
            self.output_paths = config_data.get('output_paths', {})

    def import_config(self, import_path):
        """
        Import configuration from a specified JSON file.
        """
        with open(import_path, 'r') as file:
            config_data = json.load(file)
            self.system_config.update(config_data.get('system_config', {}))
            self.api_config.update(config_data.get('api_config', {}))
            self.notification_config.update(config_data.get('notification_config', {}))
            self.price_config.update(config_data.get('price_config', {}))
            self.alert_config.update(config_data.get('alert_config', {}))
            self.input_paths.update(config_data.get('input_paths', {}))
            self.output_paths.update(config_data.get('output_paths', {}))
        print(f"Configuration imported from {import_path}")

    def export_config(self, export_path):
        """
        Export the current configuration to a specified JSON file.
        """
        with open(export_path, 'w') as file:
            json.dump({
                'system_config': self.system_config,
                'api_config': self.api_config,
                'notification_config': self.notification_config,
                'price_config': self.price_config,
                'alert_config': self.alert_config,
                'input_paths': self.input_paths,
                'output_paths': self.output_paths
            }, file, indent=4)
        print(f"Configuration exported to {export_path}")

    def display_config_table(self):
        """
        Display the configuration parameters in a table.
        """
        console = Console()
        table = Table(title="System Configuration")

        table.add_column("Parameter", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        for section, config in {
            "System Config": self.system_config,
            "API Config": self.api_config,
            "Notification Config": self.notification_config,
            "Price Config": self.price_config,
            "Alert Config": self.alert_config,
            "Input Paths": self.input_paths,
            "Output Paths": self.output_paths,
        }.items():
            table.add_row(f"[bold]{section}[/bold]", "")
            for key, value in config.items():
                table.add_row(f"  {key}", str(value))

        console.print(table)

def main_menu():
    console = Console()
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')  # Clear screen for better UX
        title = pyfiglet.figlet_format("SysConfig", font="slant")
        console.print(f"[bold cyan]{title}[/bold cyan]", justify="center")
        console.print("[bold magenta]Main Menu[/bold magenta]", justify="center")
        menu = """
        ┌──────────── Main Menu ────────────┐
        │  1    View System Configurations  │
        │  2    Refresh Database            │
        │  3    Exit                        │
        └───────────────────────────────────┘
        """
        console.print(menu)

        choice = console.input("Select an option (1-3): ").strip()
        if choice == '1':
            config = SysConfig("C:/LaunchPad/data/sonic_config.json")
            config.display_config_table()
            console.input("Press Enter to return to the main menu...")
        elif choice == '2':
            console.print("[yellow]Refresh Database functionality not implemented yet.[/yellow]")
            console.input("Press Enter to return to the main menu...")
        elif choice == '3':
            console.print("[bold green]Exiting...[/bold green]")
            break
        else:
            console.print("[red]Invalid choice. Please select a valid option (1-3).[/red]")

if __name__ == "__main__":
    main_menu()