import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set in .env file")

DOWNLOAD_DIR = Path.home() / "Downloads" / "telegram-youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
