"""MongoDB initialization."""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

users_col = db["users"]
trades_col = db["trades"]
positions_col = db["positions"]
audit_col = db["audit_logs"]
costs_col = db["costs"]
config_col = db["bot_config"]
state_col = db["bot_state"]
candles_col = db["candles"]


async def ensure_indexes():
    await users_col.create_index("email", unique=True)
    await trades_col.create_index([("closed_at", -1)])
    await positions_col.create_index("status")
    await audit_col.create_index([("ts", -1)])
    await costs_col.create_index([("date", -1)])
    await candles_col.create_index([("symbol", 1), ("ts", -1)])
