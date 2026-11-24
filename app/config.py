import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def parse_ids(value):
    return {
        int(item.strip())
        for item in value.split(",")
        if item.strip()
    }


#Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

ADMIN_IDS = parse_ids(os.getenv("ADMIN_IDS", ""))
ALLOWED_CHAT_IDS = parse_ids(os.getenv("ALLOWED_CHAT_IDS", ""))

#PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "telegram_aggregator_db")
DB_USER = os.getenv("DB_USER", "tg_aggregator")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

#Хранилища
STORAGE_DIR = BASE_DIR / os.getenv("STORAGE_DIR", "storage")
EXPORT_DIR = BASE_DIR / os.getenv("EXPORT_DIR", "exports")

TIMEZONE = os.getenv("TIMEZONE", "UTC")

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)