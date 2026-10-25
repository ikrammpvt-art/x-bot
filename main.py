import os
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import config
import database
from twitter_fetcher import TwitterFetcher
from ai_explainer import get_ai_explainer
from telegram_notifier import TelegramNotifier
from telegram_listener import TelegramCommandHandler
from aiohttp import web
import collections

log_buffer = collections.deque(maxlen=200)

class BufferHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            log_buffer.append(log_entry)
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
buffer_handler = BufferHandler()
buffer_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
logging.getLogger().addHandler(buffer_handler)
logger = logging.getLogger("xbot.main")

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def format_clock_ist(dt: datetime) -> str:
    """Formats datetime as e.g. '6:39 AM'."""
    hour = dt.strftime("%I").lstrip("0")
    if not hour:
        hour = "12"
    minute_p = dt.strftime("%M %p")
    return f"{hour}:{minute_p}"


def parse_tweet_time_ist(raw_date_str: str) -> str:
    """Converts a Twitter created_at string to '6:39 AM IST'."""
    try:
        dt = parsedate_to_datetime(raw_date_str)
        dt_ist = dt.astimezone(IST)
        return f"{format_clock_ist(dt_ist)} IST"
    except Exception:
        return f"{format_clock_ist(now_ist())} IST"


class XBotMonitor:
    def __init__(self):
        self.running = False
        self.accounts = []
        self.twitter = TwitterFetcher()
        self.telegram = TelegramNotifier()
        self.listener = None
        self.explainer = None
        self._scan_lock = asyncio.Lock()
        self.last_cycle_end_ist: Optional[datetime] = None

    def validate_environment(self) -> bool:
        """Validates configuration before starting."""
        valid = True

        if not self.telegram.is_configured():
            logger.error("❌ Telegram configuration missing! Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
            valid = False

        if not (config.TWITTER_AUTH_TOKEN and config.TWITTER_CT0) and not (config.TWITTER_USERNAME and config.TWITTER_PASSWORD) and not config.COOKIES_PATH.exists():
            logger.error("❌ Twitter credentials/cookies missing! Provide TWITTER_AUTH_TOKEN and TWITTER_CT0 in .env")
            valid = False

        if config.AI_PROVIDER == "gemini" and not config.GEMINI_API_KEY:
            logger.error("❌ GEMINI_API_KEY is missing! Get a free key at https://aistudio.google.com/app/apikey")
            valid = False

        return valid

    async def initialize(self):
        """Initializes database, AI engine, Twitter session, and Telegram command listener."""
        database.init_db()
        self.explainer = get_ai_explainer()
        self.accounts = database.get_all_monitored_accounts()

        logger.info(f"Loaded {len(self.accounts)} accounts to monitor: {', '.join(self.accounts)}")

        auth_success = await self.twitter.authenticate()
        if not auth_success:
            logger.warning("Twitter authentication was not immediately successful. Will retry during scan.")

        if config.INITIAL_SEED_ONLY:
            await self.seed_initial_history()

        # Start interactive Telegram command listener
        if self.telegram.is_configured():
            self.listener = TelegramCommandHandler(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                authorized_chat_id=config.TELEGRAM_CHAT_ID,
                monitor_instance=self
            )
            asyncio.create_task(self.listener.start())
            await self.telegram.send_startup_ping(len(self.accounts), config.CHECK_INTERVAL_MINUTES)

        # Start optional cloud health server and keep-warm pinger for cloud platforms (Render, Hugging Face, Koyeb, Railway)
        if os.getenv("PORT") or os.getenv("RENDER") or os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENABLE_HEALTH_SERVER", "false").lower() in ("true", "1", "yes"):
            asyncio.create_task(self.start_health_server())
            if os.getenv("RENDER") or os.getenv("KEEP_WARM_URL"):
                asyncio.create_task(self.start_keep_alive_pinger())

    async def start_keep_alive_pinger(self):
        """Pings the public health endpoint every 9 minutes to prevent Render free tier from sleeping."""
        base_url = (
            os.getenv("KEEP_WARM_URL")
            or os.getenv("RENDER_EXTERNAL_URL")
            or "https://xbot-intelligence.onrender.com"
        )
        ping_url = f"{base_url.rstrip('/')}/health"
        logger.info(f"Keep-warm pinger initialized for {ping_url}")

        # Wait 2 minutes after startup before sending first ping
        await asyncio.sleep(120)

        while self.running:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(ping_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        if resp.status == 200:
                            logger.info(f"🏓 Keep-warm ping to {ping_url} succeeded (200 OK)")
                        else:
                            logger.warning(f"Keep-warm ping returned status {resp.status}")
            except Exception as e:
                logger.warning(f"Keep-warm ping notice: {e}")

            # Sleep 9 minutes (540s) so Render's 15-minute inactivity shutdown timer never triggers
            await asyncio.sleep(540)

    async def start_health_server(self):
        """Starts minimal HTTP health check server for cloud platforms (Hugging Face, Render, Koyeb)."""
        port = int(os.getenv("PORT", "7860"))

        async def handle_health(request):
            accounts = database.get_all_monitored_accounts()
            return web.json_response({
                "status": "healthy",
                "service": "XBot Intelligence Digest",
                "accounts_monitored": len(accounts),
                "check_interval_mins": config.CHECK_INTERVAL_MINUTES
            })

        async def handle_debug_twitter(request):
            try:
                auth = self.twitter.is_authenticated
                if not auth:
                    auth = await self.twitter.authenticate()

                raw_resp, _ = await self.twitter.client.gql.home_latest_timeline(20, None, None)
                from twikit.utils import find_dict
                from twikit.tweet import tweet_from_data
                entries = find_dict(raw_resp, "entries", find_one=True)
                items = entries[0] if entries else []

                item_diagnostics = []
                for idx, item in enumerate(items[:15]):
                    has_content = "content" in item
                    has_item_content = "itemContent" in item.get("content", {})
                    entry_type = item.get("content", {}).get("entryType", "unknown")
                    err = None
                    tweet_obj = None
                    try:
                        tweet_obj = tweet_from_data(self.twitter.client, item)
                    except Exception as ex:
                        import traceback
                        err = f"{type(ex).__name__}: {ex}\n{traceback.format_exc()}"
                    item_diagnostics.append({
                        "idx": idx,
                        "entryType": entry_type,
                        "has_content": has_content,
                        "has_item_content": has_item_content,
                        "tweet_created": tweet_obj is not None,
                        "error": err
                    })

                parsed = await self.twitter.fetch_following_timeline(count=20)

                return web.json_response({
                    "authenticated": auth,
                    "entries_count": len(items),
                    "parsed_tweets_count": len(parsed),
                    "diagnostics": item_diagnostics
                })
            except Exception as e:
                import traceback
                return web.json_response({
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }, status=500)

        async def handle_trigger(request):
            asyncio.create_task(self.run_cycle(manual_trigger=True))
            return web.json_response({"status": "cycle_triggered"})

        async def handle_logs(request):
            return web.json_response({
                "count": len(log_buffer),
                "logs": list(log_buffer)
            })

        async def handle_trigger_digest(request):
            hours_str = request.query.get("hours", "2")
            try:
                hours = float(hours_str)
            except ValueError:
                hours = 2.0
            if self.listener:
                asyncio.create_task(self.listener.generate_on_demand_digest(config.TELEGRAM_CHAT_ID, hours=hours, macro_only=False))
                return web.json_response({"status": f"digest_triggered_for_{hours}h"})
            else:
                return web.json_response({"error": "listener_not_ready"}, status=500)

        app = web.Application()
        app.router.add_get("/", handle_health)
        app.router.add_get("/health", handle_health)
        app.router.add_get("/debug-twitter", handle_debug_twitter)
        app.router.add_get("/trigger", handle_trigger)
        app.router.add_get("/trigger-digest", handle_trigger_digest)
        app.router.add_get("/logs", handle_logs)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        try:
            await site.start()
            logger.info(f"Cloud health server active on http://0.0.0.0:{port}")
        except Exception as e:
            logger.warning(f"Could not start HTTP health server on port {port}: {e}")


    async def seed_initial_history(self):
        """Seeds currently existing tweets using batch search so we only notify on genuinely new tweets going forward."""
        uninit = [acc for acc in self.accounts if not database.is_account_initialized(acc)]
        if not uninit:
            logger.info("All accounts already initialized.")
            return

        logger.info(f"Establishing baseline for {len(uninit)} uninitialized accounts...")
        try:
            # 1. Seed from following timeline
            timeline_tweets = await self.twitter.fetch_following_timeline(count=100)
            for tweet in timeline_tweets:
                database.mark_tweet_seen(
                    tweet_id=tweet["id"],
                    username=tweet["screen_name"],
                    tweet_text=tweet["text"],
                    tweet_url=tweet["url"],
                    created_at=tweet["created_at"]
                )

            # 2. Seed from batch search if available
            try:
                batch_tweets = await self.twitter.search_tweets_batch(uninit, chunk_size=12, count_per_chunk=10)
                for tweet in batch_tweets:
                    database.mark_tweet_seen(
                        tweet_id=tweet["id"],
                        username=tweet["screen_name"],
                        tweet_text=tweet["text"],
                        tweet_url=tweet["url"],
                        created_at=tweet["created_at"]
                    )
            except Exception:
                pass

            for acc in uninit:
                database.set_account_initialized(acc)
            logger.info(f"Account baselines established ({len(timeline_tweets)} baseline tweets recorded).")
        except Exception as e:
            logger.error(f"Error seeding baselines: {e}")


    async def fetch_new_tweets_for_account(self, username: str):
        """Fetches tweets and filters for unseen ones."""
        logger.info(f"🔍 Checking @{username}...")
        recent_tweets = await self.twitter.fetch_recent_tweets(username, count=10)

        new_tweets = []
        for tweet in recent_tweets:
            if not database.is_tweet_seen(tweet["id"]):
                tweet["time_ist"] = parse_tweet_time_ist(tweet.get("created_at", ""))
                new_tweets.append(tweet)

        return new_tweets

    async def run_cycle(self, manual_trigger: bool = False):
        """Runs one full monitoring cycle across all accounts using efficient multi-account batch search."""
        async with self._scan_lock:
            # Refresh accounts list from database
            self.accounts = database.get_all_monitored_accounts()
            now_dt = now_ist()

            # Default window start: previous cycle completion or CHECK_INTERVAL_MINUTES ago
            default_start = now_dt - timedelta(minutes=config.CHECK_INTERVAL_MINUTES)
            cycle_start_ist = self.last_cycle_end_ist or default_start

            # Cap if previous cycle was excessively old (e.g. server restart)
            if (now_dt - cycle_start_ist).total_seconds() > 86400:
                cycle_start_ist = now_dt - timedelta(hours=2)

            start_str = format_clock_ist(cycle_start_ist)

            logger.info(f"=== Starting dual-source monitoring cycle for {len(self.accounts)} accounts at {start_str} IST (Manual={manual_trigger}) ===")

            all_raw = []
            # 1. Fetch live Following feed (ensures all followed accounts including macro analysts are captured)
            try:
                timeline_tweets = await self.twitter.fetch_following_timeline(count=60)
                all_raw.extend(timeline_tweets)
                logger.info(f"Fetched {len(timeline_tweets)} tweets from Following timeline.")
            except Exception as e:
                logger.warning(f"Error fetching following timeline: {e}")

            # 2. Queries watchlist accounts using batch search
            try:
                batch_tweets = await self.twitter.search_tweets_batch(self.accounts, chunk_size=8, count_per_chunk=20)
                all_raw.extend(batch_tweets)
                logger.info(f"Fetched {len(batch_tweets)} tweets from batch search.")
            except Exception as e:
                logger.error(f"Error during batch tweet search: {e}", exc_info=True)

            cycle_new_tweets = []
            seen_in_cycle = set()

            for tweet in all_raw:
                tid = tweet["id"]
                if tid not in seen_in_cycle and not database.is_tweet_seen(tid):
                    seen_in_cycle.add(tid)
                    tweet["time_ist"] = parse_tweet_time_ist(tweet.get("created_at", ""))
                    try:
                        tweet["dt"] = parsedate_to_datetime(tweet.get("created_at", "")).astimezone(IST)
                    except Exception:
                        tweet["dt"] = now_dt
                    cycle_new_tweets.append(tweet)

            cycle_end_ist = now_ist()

            # Expand window start if any tweet was published earlier
            if cycle_new_tweets:
                earliest_tweet_dt = min(t.get("dt", now_dt) for t in cycle_new_tweets)
                if earliest_tweet_dt < cycle_start_ist:
                    cycle_start_ist = earliest_tweet_dt

            start_str = format_clock_ist(cycle_start_ist)
            end_str = format_clock_ist(cycle_end_ist)

            # Guaranteed fix for timing glitch: start_str and end_str must NEVER be identical
            if start_str == end_str:
                interval_mins = max(config.CHECK_INTERVAL_MINUTES, 30)
                start_str = format_clock_ist(cycle_end_ist - timedelta(minutes=interval_mins))

            if cycle_new_tweets:
                logger.info(f"📰 Compiling X Roundup for {len(cycle_new_tweets)} new tweets from {start_str} to {end_str} IST...")

                # Strict chronological sequence: earliest tweet to latest tweet
                cycle_new_tweets.sort(key=lambda t: t.get("dt", now_dt))

                # Generate intelligence roundup
                roundup_html = await self.explainer.generate_roundup(
                    tweets=cycle_new_tweets,
                    start_time_ist=start_str,
                    end_time_ist=end_str
                )

                # Send to Telegram
                logger.info(f"Delivering X Roundup to Telegram chat {config.TELEGRAM_CHAT_ID}...")
                sent = await self.telegram.send_message(roundup_html, disable_preview=True)

                # Record all as seen
                for tweet in cycle_new_tweets:
                    database.mark_tweet_seen(
                        tweet_id=tweet["id"],
                        username=tweet["screen_name"],
                        tweet_text=tweet["text"],
                        tweet_url=tweet["url"],
                        created_at=tweet["created_at"]
                    )

                if sent:
                    logger.info("Successfully delivered X Roundup to Telegram.")
                else:
                    logger.warning("Could not deliver Roundup to Telegram.")
            else:
                msg = f"No new tweets across accounts between {start_str} and {end_str} IST."
                logger.info(msg)
                if manual_trigger:
                    await self.telegram.send_message(f"ℹ️ <b>Manual Check:</b> {msg}")

            self.last_cycle_end_ist = cycle_end_ist
            logger.info(f"=== Cycle finished. Next check in {config.CHECK_INTERVAL_MINUTES} minutes. ===")

    async def start(self):
        """Main loop that runs every CHECK_INTERVAL_MINUTES."""
        if not self.validate_environment():
            logger.error("Configuration validation failed. Please check the errors above.")
            return

        self.running = True
        await self.initialize()

        logger.info(f"XBot is actively monitoring every {config.CHECK_INTERVAL_MINUTES} minutes. Press Ctrl+C to stop.")

        while self.running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Unexpected error in monitoring cycle: {e}", exc_info=True)

            interval_seconds = config.CHECK_INTERVAL_MINUTES * 60
            for _ in range(interval_seconds):
                if not self.running:
                    break
                await asyncio.sleep(1)

    def stop(self):
        logger.info("Stopping XBot...")
        self.running = False
        if self.listener:
            self.listener.stop()


async def main():
    monitor = XBotMonitor()

    def handle_exit(sig, frame):
        logger.info(f"Received exit signal ({sig})...")
        monitor.stop()

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    await monitor.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot exited gracefully.")
