import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Twitter Scraping
TWITTER_AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
TWITTER_CT0 = os.getenv("TWITTER_CT0", "").strip()
TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "").strip()
TWITTER_EMAIL = os.getenv("TWITTER_EMAIL", "").strip()
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD", "").strip()
COOKIES_PATH = STORAGE_DIR / "cookies.json"

# AI Configuration
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower().strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2").strip()

XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
XAI_MODEL = os.getenv("XAI_MODEL", "grok-2-latest").strip()

# Polling & Behaviour
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "15"))
ACCOUNTS_FILE = os.getenv("ACCOUNTS_FILE", "accounts.txt")
INCLUDE_RETWEETS = os.getenv("INCLUDE_RETWEETS", "false").lower() in ("true", "1", "yes")
INCLUDE_REPLIES = os.getenv("INCLUDE_REPLIES", "false").lower() in ("true", "1", "yes")
INITIAL_SEED_ONLY = os.getenv("INITIAL_SEED_ONLY", "true").lower() in ("true", "1", "yes")

# Database Path
DB_PATH = STORAGE_DIR / "xbot.db"


def load_accounts() -> List[str]:
    """Reads accounts to monitor from accounts.txt or environment variable."""
    accounts = []
    file_path = BASE_DIR / ACCOUNTS_FILE
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Remove leading @ if present
                    username = line.lstrip("@").strip()
                    if username and username not in accounts:
                        accounts.append(username)
    
    # Also support comma-separated list in ACCOUNTS_TO_MONITOR env var
    env_accounts = os.getenv("ACCOUNTS_TO_MONITOR", "")
    if env_accounts:
        for acc in env_accounts.split(","):
            cleaned = acc.strip().lstrip("@")
            if cleaned and cleaned not in accounts:
                accounts.append(cleaned)

    return accounts
