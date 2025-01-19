import sqlite3
import random
import datetime

def populate_fake_prices(db_path: str):
    # Connect to (or create) the SQLite database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create the prices table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset TEXT NOT NULL,
            price REAL NOT NULL,
            source TEXT,
            timestamp DATETIME NOT NULL
        )
    """)

    # Let's insert data for 3 assets (BTC, ETH, SOL) over 10 days
    assets = ["BTC", "ETH", "SOL"]
    days_to_insert = 10

    for asset in assets:
        for i in range(days_to_insert):
            # We'll go back 'days_to_insert' days from now, one step at a time
            fake_date = datetime.datetime.now() - datetime.timedelta(days=(days_to_insert - i))
            
            # Generate a random price
            fake_price = round(random.uniform(100, 50000), 2)

            cursor.execute(
                """
                INSERT INTO prices (asset, price, source, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (asset, fake_price, "FakeData", fake_date)
            )

    conn.commit()
    conn.close()
    print(f"Inserted {len(assets) * days_to_insert} fake price rows into '{db_path}'.")

if __name__ == "__main__":
    # Change this to the path of your DB (e.g., 'C:/WebSonic/data/mother_brain.db')
    DB_PATH = "data/mother_brain.db"
    populate_fake_prices(DB_PATH)
