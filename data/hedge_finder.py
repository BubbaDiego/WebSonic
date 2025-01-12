#from data.data_locker import DataLocker
from utils.big_screen import BigScreen
from views.heat_view import HeatView  # Import the HeatView class
from rich.table import Table
from rich.text import Text
#import logging

class HedgeFinder:
    def __init__(self):
        #self.data_locker = data_locker
        self.big_screen = BigScreen.get_instance()
        self.data_locker = self.big_screen.get_data_locker()
        self.console = self.big_screen.get_console()
        self.logger = self.big_screen.get_logger()
        self.heat_view = HeatView()#self.data_locker, self.console, self.logger)  # Initialize HeatView
       # self.logger.setLevel(logging.CRITICAL)
        #self.console.setLevel(logging.CRITICAL)

    def assign_buddy(self, long_position_id: str, short_position_id: str):
        self.logger.setLevel(logging.CRITICAL)
        try:
           # self.console.print(f"[DEBUG] assign_buddy called with long_position_id={long_position_id}, short_position_id={short_position_id}")
            positions = self.data_locker.read_positions()
           # self.console.print(f"[DEBUG] positions read: {positions}")
            long_position = next((pos for pos in positions if pos['id'] == long_position_id), None)
            short_position = next((pos for pos in positions if pos['id'] == short_position_id), None)
            #self.console.print(f"[DEBUG] long_position found: {long_position}, short_position found: {short_position}")

            if long_position and short_position and long_position['asset_type'] == short_position['asset_type']:
                # Assign hedge buddy IDs
                long_position['hedge_buddy_id'] = short_position_id
                short_position['hedge_buddy_id'] = long_position_id
               # self.console.print(f"[DEBUG] hedge_buddy_ids assigned: long_position={long_position}, short_position={short_position}")

                # Update positions in the database
              #  self.console.print(f"[DEBUG] Updating long_position: {long_position}")
                self.data_locker.update_position(long_position_id, long_position['size'])
               # self.console.print(f"[DEBUG] Updating short_position: {short_position}")
                self.data_locker.update_position(short_position_id, short_position['size'])

                # Verify updates
                updated_positions = self.data_locker.read_positions()
              #  self.console.print(f"[DEBUG] updated positions: {updated_positions}")

                self.logger.info(f"Hedge buddies assigned: {long_position_id} <--> {short_position_id}")
                self.console.print(f"[bold green]Hedge buddies assigned: {long_position_id} <--> {short_position_id}[/bold green]")
            else:
                self.logger.error("Positions not found or asset types do not match")
                self.console.print("[bold red]Positions not found or asset types do not match[/bold red]")
        except Exception as e:
            self.logger.error(f"Error assigning hedge buddies: {e}", exc_info=True)
            self.console.print(f"[bold red]Error assigning hedge buddies: {e}[/bold red]")

    def unlink_hedges(self, position_id: str):
        try:
        #    self.console.print(f"[DEBUG] unlink_hedges called with position_id={position_id}")
            positions = self.data_locker.read_positions()
         #   self.console.print(f"[DEBUG] positions read: {positions}")
            position = next((pos for pos in positions if pos['id'] == position_id), None)
         #   self.console.print(f"[DEBUG] position found: {position}")

            if position and position['hedge_buddy_id']:
                hedge_buddy_id = position['hedge_buddy_id']
                hedge_buddy_position = next((pos for pos in positions if pos['id'] == hedge_buddy_id), None)
        #        self.console.print(f"[DEBUG] hedge_buddy_position found: {hedge_buddy_position}")

                # Remove hedge buddy IDs
                position['hedge_buddy_id'] = None
                if hedge_buddy_position:
                    hedge_buddy_position['hedge_buddy_id'] = None
                    self.data_locker.update_position(hedge_buddy_id, hedge_buddy_position['size'])
      #              self.console.print(f"[DEBUG] hedge_buddy_position updated in database: {hedge_buddy_position}")

                self.data_locker.update_position(position_id, position['size'])
      #          self.console.print(f"[DEBUG] position updated in database: {position}")

                # Verify updates
                updated_positions = self.data_locker.read_positions()
        #        self.console.print(f"[DEBUG] updated positions: {updated_positions}")

                self.logger.info(f"Hedge buddy removed for position: {position_id}")
                self.console.print(f"[bold green]Hedge buddy removed for position: {position_id}[/bold green]")
            else:
                self.logger.error("Position not found or no hedge buddy to remove")
                self.console.print("[bold red]Position not found or no hedge buddy to remove[/bold red]")
        except Exception as e:
            self.logger.error(f"Error removing hedge buddy: {e}", exc_info=True)
            self.console.print(f"[bold red]Error removing hedge buddy: {e}[/bold red]")

    def unlink_all_hedges(self):
        try:
  #          self.console.print(f"[DEBUG] unlink_all_hedges called")
            positions = self.data_locker.read_positions()
            for position in positions:
                if position['hedge_buddy_id']:
                    hedge_buddy_id = position['hedge_buddy_id']
                    hedge_buddy_position = next((pos for pos in positions if pos['id'] == hedge_buddy_id), None)
                    position['hedge_buddy_id'] = None
                    if hedge_buddy_position:
                        hedge_buddy_position['hedge_buddy_id'] = None
                        self.data_locker.update_position(hedge_buddy_id, hedge_buddy_position['size'])
     #                   self.console.print(f"[DEBUG] hedge_buddy_position updated in database: {hedge_buddy_position}")

                    self.data_locker.update_position(position['id'], position['size'])
    #                self.console.print(f"[DEBUG] position updated in database: {position}")

            # Verify updates
            updated_positions = self.data_locker.read_positions()
   #         self.console.print(f"[DEBUG] updated positions: {updated_positions}")

            self.logger.info("All hedge buddies removed")
            self.console.print("[bold green]All hedge buddies removed[/bold green]")
        except Exception as e:
            self.logger.error(f"Error removing all hedge buddies: {e}", exc_info=True)
            self.console.print(f"[bold red]Error removing all hedge buddies: {e}[/bold red]")

    def look_for_hedges(self):
        try:
 #           self.console.print(f"[DEBUG] look_for_hedges called")
            positions = self.data_locker.read_positions()
 #          self.console.print(f"[DEBUG] positions read: {positions}")
            long_positions = [pos for pos in positions if
                              pos['position_type'].lower() == 'long' and not pos['hedge_buddy_id']]
            short_positions = [pos for pos in positions if
                               pos['position_type'].lower() == 'short' and not pos['hedge_buddy_id']]
  #          self.console.print(f"[DEBUG] long_positions: {long_positions}")
  #          self.console.print(f"[DEBUG] short_positions: {short_positions}")

            for long_position in long_positions:
                for short_position in short_positions:
                    if long_position['asset_type'] == short_position['asset_type']:
                        self.assign_buddy(long_position['id'], short_position['id'])
      #                  self.console.print(f"[DEBUG] Assigned hedge buddies: Long Position ID: {long_position['id']} Short Position ID: {short_position['id']}")
                        break

            self.link_hedges()  # Call link_hedges after the lookup occurs

            self.logger.info("Hedge buddy assignment completed")
            self.console.print("[bold green]Hedge buddy assignment completed[/bold green]")
        except Exception as e:
            self.logger.error(f"Error looking for hedges: {e}", exc_info=True)
            self.console.print(f"[bold red]Error looking for hedges: {e}[/bold red]")

    def link_hedges(self):
        """
        Link position pairs of the same asset type by setting each other's hedge_buddy_id.
        """
        try:
   #         self.console.print(f"[DEBUG] link_hedges called")
            positions = self.data_locker.read_positions()
 #           self.console.print(f"[DEBUG] positions read: {positions}")

            # Dictionary to hold positions by asset type
            asset_dict = {}

            for position in positions:
                asset_type = position['asset_type']
                if asset_type not in asset_dict:
                    asset_dict[asset_type] = []
                asset_dict[asset_type].append(position)
  #          self.console.print(f"[DEBUG] asset_dict: {asset_dict}")

            # Iterate through positions to find and link hedges
            for asset_type, pos_list in asset_dict.items():
                for i, pos1 in enumerate(pos_list):
                    for j, pos2 in enumerate(pos_list):
                        if i != j and pos1['position_type'] != pos2['position_type']:
                            pos1_id = pos1['id']
                            pos2_id = pos2['id']
                            self.data_locker.cursor.execute(
                                'UPDATE positions SET hedge_buddy_id = ? WHERE id = ?',
                                (pos2_id, pos1_id)
                            )
                            self.data_locker.cursor.execute(
                                'UPDATE positions SET hedge_buddy_id = ? WHERE id = ?',
                                (pos1_id, pos2_id)
                            )
                            self.data_locker.conn.commit()
                        #    self.logger.info(f"Linked hedge buddies: {pos1_id} <-> {pos2_id}")
                          #  self.console.print(f"[DEBUG] Linked hedge buddies: {pos1_id} <-> {pos2_id}")

            # Verify updates
            updated_positions = self.data_locker.read_positions()
     #       self.console.print(f"[DEBUG] updated positions: {updated_positions}")

        except Exception as e:
            self.logger.error(f"Error linking hedges: {e}", exc_info=True)
            self.console.print(f"[bold red]Error linking hedges: {e}[/bold red]")

    def get_hedges(self):
        """
        Confirm that referenced hedge positions still exist.
        """
        try:
   #         self.console.print(f"[DEBUG] get_hedges called")
            positions = self.data_locker.read_positions()
   #         self.console.print(f"[DEBUG] positions read: {positions}")
            valid_hedges = []

            for position in positions:
                hedge_buddy_id = position.get('hedge_buddy_id')
                if hedge_buddy_id:
                    self.data_locker.cursor.execute('SELECT * FROM positions WHERE id = ?', (hedge_buddy_id,))
                    hedge_buddy = self.data_locker.cursor.fetchone()
                    if hedge_buddy:
                        valid_hedges.append((position['id'], hedge_buddy_id))
                    else:
                        self.logger.warning(f"Hedge buddy not found for position: {position['id']}")
      #                  self.console.print(f"[DEBUG] Hedge buddy not found for position: {position['id']}")

   #         self.logger.info(f"Valid hedges found: {valid_hedges}")
  #          self.console.print(f"[DEBUG] Valid hedges found: {valid_hedges}")
            return valid_hedges

        except Exception as e:
            self.logger.error(f"Error getting hedges: {e}", exc_info=True)
            self.console.print(f"[bold red]Error getting hedges: {e}[/bold red]")



    def calculate_heat_points(self, position):
        """
        Calculate heat points for a given position.
        """
        try:
            size = position.get('size', 0)
            leverage = position.get('leverage', 0)
            collateral = position.get('collateral', 0)
            if collateral == 0:
                return None
            heat_points = (size * leverage) / collateral
            return heat_points
        except Exception as e:
            self.logger.error(f"Error calculating heat points for position {position['id']}: {e}", exc_info=True)
            return None


    def calculate_current_heat_points(self, long_position, short_position):
        """
        Calculate heat ratio for a given hedge pair.
        """
        try:
            long_heat_points = self.calculate_heat_points(long_position)
            short_heat_points = self.calculate_heat_points(short_position)
            long_travel_percent = long_position.get('current_travel_percent', 0) / 100
            short_travel_percent = short_position.get('current_travel_percent', 0) / 100

            if long_heat_points is not None and short_heat_points is not None:
                adjusted_long_heat_points = long_heat_points * (1 - long_travel_percent)
                adjusted_short_heat_points = short_heat_points * (1 - short_travel_percent)
                return adjusted_long_heat_points, adjusted_short_heat_points
            else:
                return None, None
        except Exception as e:
            self.logger.error(f"Error calculating heat ratio: {e}", exc_info=True)
            return None, None

    def generate_heat_report(self):
        """
        Generate a report of all positions with heat metrics.
        """
        self.heat_view.generate_heat_report()  # Use HeatView to generate the heat report

    def view_positions(self):
        """
        Display all positions from the database.
        """
        try:
            self.console.print(f"[DEBUG] view_positions called")
            positions = self.data_locker.read_positions()
            if positions:
                for position in positions:
                    self.console.print(f"ID: {position['id']}, Asset: {position['asset_type']}, Type: {position['position_type']}, Size: {position['size']}, Value: {position['value']}")
            else:
                self.console.print("[bold red]No positions found.[/bold red]")

        except Exception as e:
            self.logger.error(f"Error viewing positions: {e}", exc_info=True)
            self.console.print(f"[bold red]Error viewing positions: {e}[/bold red]")

    def main_menu(self):
        while True:
            self.console.print(f"[bold blue]===== Buddy System Menu =====[/bold blue]")
            self.console.print("1) 🔥 Heat Report")
            self.console.print("2) 🔗 Link Positions")
            self.console.print("3) 📄 View Positions")
            self.console.print("4) 🚪 Exit")
            choice = self.console.input("Enter your choice: ")

            if choice == "1":
                self.generate_heat_report()
            elif choice == "2":
                self.look_for_hedges()
            elif choice == "3":
                self.view_positions()
            elif choice == "4":
                break
            else:
                self.console.print("[bold red]❌ Invalid choice, please try again.[/bold red]")

    def select_position_to_unlink(self):
        try:
            positions = self.data_locker.read_positions()
            if not positions:
                self.console.print("[bold red]No positions available to unlink.[/bold red]")
                return

            self.console.print("[bold yellow]Select a position to unlink:[/bold yellow]")
            for idx, position in enumerate(positions):
                self.console.print(f"{idx + 1}) ID: {position['id']}, Asset: {position['asset_type']}, Type: {position['position_type']}")

            choice = self.console.input("Enter the number of the position to unlink: ")
            try:
                index = int(choice) - 1
                if 0 <= index < len(positions):
                    self.unlink_hedges(positions[index]['id'])
                else:
                    self.console.print("[bold red]Invalid selection, please try again.[/bold red]")
            except ValueError:
                self.console.print("[bold red]Invalid input, please enter a number.[/bold red]")

        except Exception as e:
            self.logger.error(f"Error selecting position to unlink: {e}", exc_info=True)
            self.console.print(f"[bold red]Error selecting position to unlink: {e}[/bold red]")

# Example usage
if __name__ == "__main__":
   # data_locker = DataLocker()
    buddy_system = HedgeFinder()
    buddy_system.main_menu()
