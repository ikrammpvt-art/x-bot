import sqlite3
from pathlib import Path
from typing import Optional, List, Tuple
from config import DB_PATH, BASE_DIR, ACCOUNTS_FILE


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables for tracking seen tweets and account cache."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Table for storing seen tweets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen_tweets (
                tweet_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                tweet_text TEXT,
                tweet_url TEXT,
                created_at TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table for tracking monitored accounts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monitored_accounts (
                username TEXT PRIMARY KEY,
                user_id TEXT,
                initialized INTEGER DEFAULT 0,
                last_checked_at TIMESTAMP
            )
        """)
        
        conn.commit()
    
    # Sync accounts from accounts.txt into DB if DB table is empty
    sync_from_file_if_empty()


def sync_from_file_if_empty():
    """Seeds monitored_accounts from accounts.txt if the DB table has no accounts."""
    existing = get_all_monitored_accounts()
    if not existing:
        accounts_path = BASE_DIR / ACCOUNTS_FILE
        if accounts_path.exists():
            with open(accounts_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        username = line.lstrip("@").strip()
                        if username:
                            add_monitored_account(username, sync_file=False)


def get_all_monitored_accounts() -> List[str]:
    """Returns list of all active monitored Twitter usernames."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM monitored_accounts ORDER BY username ASC")
        rows = cursor.fetchall()
        return [row["username"] for row in rows]


def add_monitored_account(username: str, sync_file: bool = True) -> bool:
    """Adds a new username to monitored accounts."""
    cleaned = username.lstrip("@").strip()
    if not cleaned:
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO monitored_accounts (username, initialized)
            VALUES (?, 0)
        """, (cleaned,))
        conn.commit()

    if sync_file:
        sync_accounts_to_file()
    return True


def remove_monitored_account(username: str) -> bool:
    """Removes a username from monitored accounts."""
    cleaned = username.lstrip("@").strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM monitored_accounts WHERE LOWER(username) = ?", (cleaned,))
        deleted = cursor.rowcount > 0
        conn.commit()

    if deleted:
        sync_accounts_to_file()
    return deleted


def sync_accounts_to_file():
    """Writes the current DB account list back to accounts.txt for persistence and inspection."""
    accounts = get_all_monitored_accounts()
    accounts_path = BASE_DIR / ACCOUNTS_FILE
    with open(accounts_path, "w", encoding="utf-8") as f:
        f.write("# Accounts to monitor (checked every 30 minutes)\n")
        f.write("# Managed automatically via Telegram (/add and /remove)\n\n")
        for acc in accounts:
            f.write(f"{acc}\n")


def is_tweet_seen(tweet_id: str) -> bool:
    """Checks if a tweet has already been recorded."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM seen_tweets WHERE tweet_id = ?", (str(tweet_id),))
        return cursor.fetchone() is not None


def mark_tweet_seen(
    tweet_id: str,
    username: str,
    tweet_text: str = "",
    tweet_url: str = "",
    created_at: str = ""
):
    """Inserts a tweet into seen_tweets."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO seen_tweets (tweet_id, username, tweet_text, tweet_url, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (str(tweet_id), username.lower(), tweet_text, tweet_url, created_at))
        conn.commit()


def get_cached_user_id(username: str) -> Optional[str]:
    """Retrieves cached Twitter user ID for a username."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM monitored_accounts WHERE LOWER(username) = ?", (username.lower(),))
        row = cursor.fetchone()
        return row["user_id"] if row and row["user_id"] else None


def set_cached_user_id(username: str, user_id: str):
    """Caches Twitter user ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitored_accounts (username, user_id)
            VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET user_id = excluded.user_id
        """, (username, str(user_id)))
        conn.commit()


def is_account_initialized(username: str) -> bool:
    """Returns True if this account has completed initial seeding."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT initialized FROM monitored_accounts WHERE LOWER(username) = ?", (username.lower(),))
        row = cursor.fetchone()
        return bool(row and row["initialized"] == 1)


def set_account_initialized(username: str):
    """Marks that an account has been initialized."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitored_accounts (username, initialized)
            VALUES (?, 1)
            ON CONFLICT(username) DO UPDATE SET initialized = 1
        """, (username,))
        conn.commit()


def update_account_checked(username: str):
    """Updates last_checked_at timestamp."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitored_accounts (username, last_checked_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT(username) DO UPDATE SET last_checked_at = CURRENT_TIMESTAMP
        """, (username,))
        conn.commit()
