import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
STORAGE_DIR = BASE_DIR / "storage"
ASSETS_DIR.mkdir(exist_ok=True)
STORAGE_DIR.mkdir(exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "")
TWITTER_EMAIL = os.getenv("TWITTER_EMAIL", "")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD", "")

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "meme-bot/1.0")

POSTS_PER_DAY = int(os.getenv("POSTS_PER_DAY", "5"))
POST_INTERVAL_MINUTES = int(os.getenv("POST_INTERVAL_MINUTES", "120"))
MIN_SCORE = int(os.getenv("MIN_SCORE", "500"))
DEDUP_HASH_SIZE = int(os.getenv("DEDUP_HASH_SIZE", "16"))

DATABASE_PATH = STORAGE_DIR / "memes.db"
COOKIES_FILE = STORAGE_DIR / "twikit_cookies.json"
SEEN_HASHES_FILE = STORAGE_DIR / "seen_hashes.txt"
