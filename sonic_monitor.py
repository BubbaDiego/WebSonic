import time
import os
import asyncio
import json
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from pytz import timezone as pytz_timezone
from rich.console import Console
from playsound import playsound
import pygame
from rich.box import HEAVY_EDGE
from utils.alert_manager import AlertManager
from utils.spin_city import SpinCity
from utils.paper_boy import PaperBoy
from views.dashboard_view import DashboardView
from views.monitor_table_view import MonitorTableView
from data.data_locker import DataLocker
from launch_pad import LaunchPad
from views.heat_view import HeatView
from views.heat_report_email import HeatReportConsole
from views.inline_price_view import InlinePriceView
from views.report_generator_html import ReportGeneratorHTML
#from views.balance_bar_view import BalanceView  # Ensure BalanceView is imported
from prices.price_monitor import PriceMonitor

from config.path_config import CONFIG_FILE_PATH, PORTFOLIO_FILE_PATH, PLEASANT_SOUND
from config.path_config import BIG_PICTURE_REPORT, SUCCESS_SOUND

# Path to the portfolio.json file
#PORTFOLIO_FILE_PATH = "portfolio.json"

class SonicMonitor:
    CONFIG_FILE_PATH = CONFIG_FILE_PATH

    def __init__(self, loop_time_minutes: int = .5):
        self.loop_time_minutes = 1 # loop_time_minutes
        self.loop_counter = 0
        self.launch_pad = LaunchPad()
        self.console = Console()
        self.notified_positions = set()
        self.monitor_view = MonitorTableView()
        self.data_locker = DataLocker()
        self.alert_manager = AlertManager(self.data_locker)
        self.PORTFOLIO_FILE_PATH = "portfolio.json"
        self.data_locker = DataLocker.get_instance()  # Use database
        self.price_monitor = PriceMonitor(self.data_locker)
        self.inline_price_view = InlinePriceView(self.data_locker)
        self.heat_view = HeatView()
        self.heat_report_console = HeatReportConsole()
        self.report_generator = ReportGeneratorHTML()
        self.dashboard_view = DashboardView(self.data_locker)
        self.paper_boy = PaperBoy()
        self.thresholds = {
            'negative': [-25, -50],
            'positive': [25, 50]
        }
        self.notified_positions = set()  # Initialize with empty set
        self.PORTFOLIO_FILE_PATH = "portfolio.json"  # Instance-level file path
        self.set_initial_alerts()
        self.config = self.load_config()

        # Configurable parameters
        self.sonic_cycle_time_mins = self.config.get("sonic_cycle_time_mins", 1)
        self.heat_report_interval = self.config.get("heat_report_interval", 60)
        self.heat_report_methods = self.config.get("heat_report_methods", ["LOCAL_HTML"])
        self.launch_web_station_on_startup = self.config.get("launch_web_station_on_startup", False)
        self.last_heat_report_time = datetime.now(timezone.utc)
       # self.play_sound(SUCCESS_SOUND)

    def play_sound(self, file_path):
        """Play a sound file using pygame."""
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                continue
        except Exception as e:
            print(f"Failed to play sound: {e}")

    def load_config(self):
        """Load configuration from the JSON file."""
        if os.path.exists(self.CONFIG_FILE_PATH):
            try:
                with open(self.CONFIG_FILE_PATH, "r") as file:
                    return json.load(file)
            except Exception as e:
                self.console.print(f"[ERROR] Failed to load config: {e}", style="bold red")
        return {}

    def set_initial_alerts(self):
        """Set all positions to known or triggered state on startup."""
        positions = self.data_locker.read_positions()  # Assuming a method to get all positions
        for position in positions:
            self.notified_positions.add(position['id'])

    def risk_management_check(self, positions):
        triggered_positions = {'negative': [], 'positive': []}
        for position in positions:
            travel_percent = position['current_travel_percent']
            if travel_percent <= self.thresholds['negative'][0]:
                triggered_positions['negative'].append(position)
            elif travel_percent <= self.thresholds['negative'][1]:
                triggered_positions['negative'].append(position)
            elif travel_percent >= self.thresholds['positive'][0]:
                triggered_positions['positive'].append(position)
            elif travel_percent >= self.thresholds['positive'][1]:
                triggered_positions['positive'].append(position)

        if triggered_positions['negative'] or triggered_positions['positive']:
            self.send_combined_notifications(triggered_positions)

    def send_combined_notifications(self, triggered_positions):
        messages = []
        for position in triggered_positions['negative']:
            messages.append(
                f"🚨 {position.get('asset', 'Unknown Asset')} ({position.get('position_type', 'Unknown Position')}): exceeded the negative threshold with travel percent of {position['current_travel_percent']:.2f}%."
            )
        for position in triggered_positions['positive']:
            messages.append(
                f"🚨 {position.get('asset', 'Unknown Asset')} ({position.get('position_type', 'Unknown Position')}): exceeded the positive threshold with travel percent of {position['current_travel_percent']:.2f}%."
            )

    def clear_console(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    async def get_latest_prices(self):
        latest_prices = await self.price_monitor.update_prices()
        return latest_prices

    def import_data(self):
        """Import new data from portfolio.json."""
        portfolio = self.read_portfolio_file()  # Read portfolio.json

        if True:# self.should_import_data(portfolio):  # Pass the portfolio to the method
            print("Processing new data...")
            for position in portfolio["positions"]:
                print(f"Processing position: {position}")
                self.data_locker.add_position(position)  # Add position to DataLocker

            # Update the imported timestamp
            portfolio["imported_timestamp"] = datetime.now(timezone.utc).isoformat()

            self.write_portfolio_file(portfolio)
            print(f"Data imported successfully. `imported_timestamp` updated to {portfolio['imported_timestamp']}.")
        else:
            print("No new data to import.")

    def send_heat_report_email(self):
        """Send a heat report email using PaperBoy."""
        self.paper_boy.send_heat_report()

    async def monitoring_loop(self):
        while True:

            self.loop_counter += 1
            #self.clear_console()
            self.console.print(f"Loop count: {self.loop_counter}", style="bold blue")

            # Import new data if available
            self.import_data()


            self.launch_pad.easy_button()  # Assuming easy_button does not need arguments and is synchronous

            latest_prices = await self.get_latest_prices()

            # Sync dependent data
            self.data_locker.sync_dependent_data()

            # Calculate and display the next heat report time in PST
            now = datetime.now(timezone.utc)
            next_heat_report_time = self.last_heat_report_time + timedelta(minutes=self.heat_report_interval)
            pst = pytz_timezone("US/Pacific")
            next_heat_report_pst = next_heat_report_time.astimezone(pst)
            self.console.print(
                f"Next Heat Report Time (PST): {next_heat_report_pst.strftime('%Y-%m-%d %I:%M:%S %p %Z')}",
                style="bold green")

            self.inline_price_view.display_prices()

            # Generate HTML reports
           # self.report_generator.generate_hedge_report_html()
           # self.report_generator.generate_heat_report_html()
            #self.report_generator.generate_big_picture_report_html()

            # Generate and display heat reports
            self.heat_view.generate_heat_report()
            self.heat_view.side_by_side_heat()
            self.dashboard_view.render_panels()

            # 🔥 Heat Report 🔥 - Check if it's time for a heat report
            now = datetime.now(timezone.utc)
            time_to_heat_report = max(
                0, self.heat_report_interval * 60 - (now - self.last_heat_report_time).total_seconds()
            )
            if time_to_heat_report == 0:
                await self.publish_heat_report()
                self.last_heat_report_time = now

            # Check risks and send alerts
            self.risk_management_check(self.data_locker.read_positions())

            #self.alert_manager.monitor_alerts()

            # Countdown for the next loop
            #await self.countdown_with_loading_bar(time_to_heat_report, label="Heat Report Countdown")
            await self.countdown_with_loading_bar(self.sonic_cycle_time_mins  * 60)

            #await SpinCity.run_spinner(spinner_type="Dots", text="Monitoring", duration=5)

    def start_monitoring(self):
        # Play launch sequence sound
        try:
            play_sound(LAUNCH_SEQUENCE_SOUND)#r"C:\\SonicInSpace\\sounds\\launch_sequence.mp3")
           # play_sound(r"C:\\SonicInSpace\\sounds\\launch_sequence.mp3")
          #  playsound(r"c:\\SonicInSpace\\sounds\\launch_sequence.mp3")
        except Exception as e:
            self.console.print(f"[ERROR] Failed to play sound: {e}", style="bold red")

        # Launch web station if enabled in settings.  This will allow for remote updates
        if self.launch_web_station_on_startup:
            self.console.print("[bold cyan]Launching Sonic Web Station on startup...[/bold cyan]")
            self.launch_pad.start_sonic_web_station()

        asyncio.run(self.monitoring_loop())



if __name__ == "__main__":
    # Create SonicMonitor instance and start monitoring
    monitor = SonicMonitor(loop_time_minutes=1)
    monitor.start_monitoring()