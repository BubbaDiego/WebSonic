from data_locker import DataLocker
from data.models import Broker

# 1) Get your DataLocker instance
# Use a raw string (r" ... ") or double backslashes:
db_path = r"C:\WebSonic\data\mother_brain.db"
# or db_path = "C:\\WebSonic\\data\\mother_brain.db"

data_locker = DataLocker.get_instance(db_path)

# 2) Create a few broker objects
aave_broker = Broker(
    name="Aave",
    image_path="/static/images/aave.jpg",
    web_address="https://aave.com",
    total_holding=0.0
)

raydium_broker = Broker(
    name="Raydium",
    image_path="/static/images/raydium.jpg",
    web_address="https://raydium.io",
    total_holding=0.0
)

jupiter_broker = Broker(
    name="Jupiter",
    image_path="/static/images/jupiter.jpg",
    web_address="https://jup.ag/",
    total_holding=0.0
)

# 3) Insert them one by one (or in a loop)
data_locker.create_broker(aave_broker)
data_locker.create_broker(raydium_broker)
data_locker.create_broker(jupiter_broker)

print("Successfully created brokers in the DB!")
input()
