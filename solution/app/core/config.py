import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]

load_dotenv(ROOT_DIR / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://au_user:au_local_password@localhost:5437/campaign_dispatcher",
)

PROVIDER_URL = os.getenv(
    "PROVIDER_URL",
    "http://127.0.0.1:8099",
)

CALLBACK_URL = os.getenv(
    "CALLBACK_URL",
    "http://127.0.0.1:8200/webhooks/telephony",
)

APP_HOST = "0.0.0.0"
APP_PORT = 8200