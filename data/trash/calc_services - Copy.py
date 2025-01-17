import unittest
from calc_services import CalcServices

class TestCalcServices(unittest.TestCase):

    def setUp(self):
        self.calc = CalcServices()

    def test_calculate_travel_percent_long(self):
        # Test for a long position
        entry_price = 100.0
        current_price = 110.0
        liquidation_price = 80.0
        expected_percent = ((current_price - entry_price) / (entry_price - liquidation_price)) * 100
        result = self.calc.calculate_travel_percent(entry_price, current_price, liquidation_price)
        self.assertAlmostEqual(result, expected_percent, places=2, msg="Travel percent for long position is incorrect")

    def test_calculate_travel_percent_short(self):
        # Test for a short position
        entry_price = 100.0
        current_price = 90.0
        liquidation_price = 120.0
        expected_percent = ((current_price - entry_price) / (entry_price - liquidation_price)) * 100
        result = self.calc.calculate_travel_percent(entry_price, current_price, liquidation_price)
        self.assertAlmostEqual(result, expected_percent, places=2, msg="Travel percent for short position is incorrect")

    def test_calculate_travel_percent_division_by_zero(self):
        # Test to ensure no division by zero
        entry_price = 100.0
        current_price = 110.0
        liquidation_price = 100.0  # Denominator becomes zero
        result = self.calc.calculate_travel_percent(entry_price, current_price, liquidation_price)
        self.assertIsNone(result, "Travel percent should be None when division by zero occurs")

    def test_calculate_heat_points(self):
        # Test valid heat points calculation
        position = {
            "size": 10.0,
            "leverage": 5.0,
            "collateral": 200.0
        }
        expected_heat_points = (position["size"] * position["leverage"]) / position["collateral"]
        result = self.calc.calculate_heat_points(position)
        self.assertAlmostEqual(result, expected_heat_points, places=2, msg="Heat points calculation is incorrect")

    def test_calculate_heat_points_zero_collateral(self):
        # Test heat points with zero collateral
        position = {
            "size": 10.0,
            "leverage": 5.0,
            "collateral": 0.0  # Division by zero
        }
        result = self.calc.calculate_heat_points(position)
        self.assertIsNone(result, "Heat points should be None when collateral is zero")

    def test_get_color_for_travel_percent(self):
        # Test color mapping for travel_percent
        self.assertEqual(self.calc.get_color(10, "travel_percent"), "green")
        self.assertEqual(self.calc.get_color(30, "travel_percent"), "yellow")
        self.assertEqual(self.calc.get_color(60, "travel_percent"), "orange")
        self.assertEqual(self.calc.get_color(90, "travel_percent"), "red")

    def test_get_color_for_heat_index(self):
        # Test color mapping for heat_index
        self.assertEqual(self.calc.get_color(10, "heat_index"), "blue")
        self.assertEqual(self.calc.get_color(30, "heat_index"), "green")
        self.assertEqual(self.calc.get_color(50, "heat_index"), "yellow")
        self.assertEqual(self.calc.get_color(70, "heat_index"), "orange")
        self.assertEqual(self.calc.get_color(90, "heat_index"), "red")

if __name__ == "__main__":
    unittest.main()
