"""
force_counters_to_seven.py

A quick standalone script to set total_reports=7 for each API
in your api_status_counters table.
"""

import sqlite3

DB_PATH = "C:/WebSonic/data/mother_brain.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # The APIs you want to ensure exist in the table
    apis = ["CoinGecko", "CoinMarketCap", "CoinPaprika", "Binance"]

    for api in apis:
        # Check if the row exists
        cursor.execute("SELECT total_reports FROM api_status_counters WHERE api_name = ?", (api,))
        row = cursor.fetchone()

        if row is None:
            # Insert a new row with total_reports=7
            cursor.execute("""
                INSERT INTO api_status_counters (api_name, total_reports)
                VALUES (?, 7)
            """, (api,))
        else:
            # Row exists => set total_reports=7
            cursor.execute("""
                UPDATE api_status_counters
                   SET total_reports = 7
                 WHERE api_name = ?
            """, (api,))

    conn.commit()
    conn.close()
    print("All counters forcibly set to 7. Check your front end to see if it displays 7 now.")

if __name__ == "__main__":
    main()
