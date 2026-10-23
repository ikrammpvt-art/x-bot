"""
Single-run execution script for XBot.
Runs one monitoring cycle and exits cleanly.
Ideal for GitHub Actions scheduled workflows, cron jobs, or test runs.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import config
import database
from twitter_fetcher import TwitterFetcher
from ai_explainer import get_ai_explainer
from telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("xbot.run_once")
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def format_clock_ist(dt: datetime) -> str:
    hour = dt.strftime("%I").lstrip("0")
    if not hour:
        hour = "12"
    return f"{hour}:{dt.strftime('%M %p')}"


def parse_tweet_time_ist(raw_date_str: str) -> str:
    try:
        dt = parsedate_to_datetime(raw_date_str)
        return f"{format_clock_ist(dt.astimezone(IST))} IST"
    except Exception:
        return f"{format_clock_ist(now_ist())} IST"


async def run_single_cycle():
    database.init_db()
    accounts = database.get_all_monitored_accounts()
    logger.info(f"Loaded {len(accounts)} accounts to check.")

    twitter = TwitterFetcher()
    auth_ok = await twitter.authenticate()
    if not auth_ok:
        logger.error("Failed to authenticate with Twitter cookies.")
        return False

    telegram = TelegramNotifier()
    explainer = get_ai_explainer()

    cycle_start = now_ist()
    start_str = format_clock_ist(cycle_start)

    logger.info(f"Scanning {len(accounts)} accounts...")
    raw_tweets = await twitter.search_tweets_batch(accounts, chunk_size=12, count_per_chunk=20)

    new_tweets = []
    seen_ids = set()
    for t in raw_tweets:
        tid = t["id"]
        if tid not in seen_ids and not database.is_tweet_seen(tid):
            seen_ids.add(tid)
            t["time_ist"] = parse_tweet_time_ist(t.get("created_at", ""))
            new_tweets.append(t)

    cycle_end = now_ist()
    end_str = format_clock_ist(cycle_end)

    if new_tweets:
        logger.info(f"Compiling roundup for {len(new_tweets)} new tweets ({start_str} to {end_str} IST)...")
        new_tweets.reverse()
        roundup_html = await explainer.generate_roundup(
            tweets=new_tweets,
            start_time_ist=start_str,
            end_time_ist=end_str
        )
        await telegram.send_message(roundup_html, disable_preview=True)

        for t in new_tweets:
            database.mark_tweet_seen(
                tweet_id=t["id"],
                username=t["screen_name"],
                tweet_text=t["text"],
                tweet_url=t["url"],
                created_at=t["created_at"]
            )
        logger.info(f"Delivered {len(new_tweets)} tweets to Telegram successfully.")
    else:
        logger.info(f"No new tweets detected between {start_str} and {end_str} IST.")

    return True


if __name__ == "__main__":
    asyncio.run(run_single_cycle())
