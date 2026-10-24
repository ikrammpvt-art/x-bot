import asyncio
import html
import logging
from typing import Optional
import aiohttp

from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import config
import database

logger = logging.getLogger("xbot.telegram_listener")

IST = timezone(timedelta(hours=5, minutes=30))


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
        now_dt = datetime.now(IST)
        hour = now_dt.strftime("%I").lstrip("0")
        return f"{hour}:{now_dt.strftime('%M %p')} IST"


class TelegramCommandHandler:

    def __init__(self, bot_token: str, authorized_chat_id: str, monitor_instance):
        self.bot_token = bot_token
        self.authorized_chat_id = str(authorized_chat_id)
        self.monitor = monitor_instance
        self.running = False
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.last_update_id = 0

    async def send_reply(self, chat_id: str, text: str):
        """Sends a message back to the user."""
        endpoint = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=10) as resp:
                    pass
        except Exception as e:
            logger.error(f"Error sending reply to Telegram: {e}")

    def clean_handle(self, text: str) -> str:
        """Strips @, urls, and slashes from handle input."""
        cleaned = text.strip()
        if "x.com/" in cleaned or "twitter.com/" in cleaned:
            cleaned = cleaned.rstrip("/").split("/")[-1]
        cleaned = cleaned.lstrip("@").strip()
        return cleaned

    async def handle_command(self, chat_id: str, text: str):
        parts = text.strip().split()
        if not parts:
            return

        cmd = parts[0].lower().split("@")[0]  # strip @botname if in group
        args = parts[1:]

        if cmd in ("/start", "/help"):
            msg = (
                "🤖 <b>X Intelligence Command Center</b>\n\n"
                "<b>📊 On-Demand Briefings:</b>\n"
                "• <code>/digest</code> — Instant 2-hour executive briefing\n"
                "• <code>/digest 1h</code> / <code>/digest 4h</code> / <code>/digest 24h</code> — Custom window\n"
                "• <code>/macro</code> or <code>/macro 4h</code> — Focused financial & market intelligence\n"
                "• <code>/roundup</code> or <code>/check</code> — Trigger scheduled cycle right now\n\n"
                "<b>📋 Watchlist Management:</b>\n"
                "• <code>/list</code> — View all currently monitored accounts\n"
                "• <code>/add &lt;handle&gt;</code> — Add account(s) to monitor\n"
                "• <code>/remove &lt;handle&gt;</code> — Stop monitoring an account\n"
                "• <code>/status</code> — System health, uptime & cloud status\n"
            )
            await self.send_reply(chat_id, msg)


        elif cmd == "/list":
            accounts = database.get_all_monitored_accounts()
            if not accounts:
                await self.send_reply(chat_id, "📋 No accounts are currently monitored.\nAdd one with <code>/add &lt;username&gt;</code>")
                return

            lines = [f"📋 <b>Currently Monitored Accounts ({len(accounts)}):</b>\n"]
            for i, acc in enumerate(accounts, 1):
                lines.append(f"{i}. <a href=\"https://x.com/{acc}\">@{acc}</a>")
            lines.append("\n<i>Tip: Use <code>/add &lt;handle&gt;</code> to add more, or <code>/remove &lt;handle&gt;</code> to delete.</i>")
            await self.send_reply(chat_id, "\n".join(lines))

        elif cmd == "/add":
            if not args:
                await self.send_reply(chat_id, "⚠️ Please provide a handle. Example:\n<code>/add PeterSchiff</code>")
                return

            # Support comma-separated or space-separated handles
            raw_input = " ".join(args).replace(",", " ")
            handles = [self.clean_handle(h) for h in raw_input.split() if self.clean_handle(h)]

            added = []
            for handle in handles:
                if database.add_monitored_account(handle):
                    added.append(handle)


            # Refresh monitor's active list
            self.monitor.accounts = database.get_all_monitored_accounts()

            if len(added) == 1:
                msg = f"✅ Added <b>@{added[0]}</b> to monitoring list! Total: {len(self.monitor.accounts)} accounts."
            else:
                msg = f"✅ Added {len(added)} accounts: {', '.join(['@' + h for h in added])}! Total: {len(self.monitor.accounts)} accounts."
            await self.send_reply(chat_id, msg)

        elif cmd == "/remove":
            if not args:
                await self.send_reply(chat_id, "⚠️ Please provide a handle to remove. Example:\n<code>/remove PeterSchiff</code>")
                return

            raw_input = " ".join(args).replace(",", " ")
            handles = [self.clean_handle(h) for h in raw_input.split() if self.clean_handle(h)]

            removed = []
            for handle in handles:
                if database.remove_monitored_account(handle):
                    removed.append(handle)

            # Refresh monitor's active list
            self.monitor.accounts = database.get_all_monitored_accounts()

            if removed:
                msg = f"🗑️ Removed {', '.join(['@' + h for h in removed])} from monitoring list. Remaining: {len(self.monitor.accounts)} accounts."
            else:
                msg = "⚠️ Account(s) not found in the monitoring list."
            await self.send_reply(chat_id, msg)

        elif cmd in ("/roundup", "/check"):
            count = len(database.get_all_monitored_accounts())
            await self.send_reply(chat_id, f"🔍 Triggering instant scan across {count} accounts... Stand by for your roundup!")
            # Run scan in background task
            asyncio.create_task(self.monitor.run_cycle(manual_trigger=True))

        elif cmd in ("/digest", "/summary"):
            hours = 2.0
            if args:
                arg = args[0].lower().strip()
                if arg.endswith("m"):
                    try:
                        hours = max(0.1, float(arg[:-1]) / 60.0)
                    except ValueError:
                        pass
                elif arg.endswith("h"):
                    try:
                        hours = max(0.25, min(48.0, float(arg[:-1])))
                    except ValueError:
                        pass
                else:
                    try:
                        hours = max(0.25, min(48.0, float(arg)))
                    except ValueError:
                        pass
            asyncio.create_task(self.generate_on_demand_digest(chat_id, hours=hours, macro_only=False))

        elif cmd == "/macro":
            hours = 4.0
            if args:
                arg = args[0].lower().strip()
                if arg.endswith("h"):
                    try:
                        hours = max(0.5, min(48.0, float(arg[:-1])))
                    except ValueError:
                        pass
                else:
                    try:
                        hours = max(0.5, min(48.0, float(arg)))
                    except ValueError:
                        pass
            asyncio.create_task(self.generate_on_demand_digest(chat_id, hours=hours, macro_only=True))

        elif cmd == "/status":
            accounts = database.get_all_monitored_accounts()
            msg = (
                "🟢 <b>X Monitor Bot Status: Active (Cloud 24/7)</b>\n\n"
                f"• <b>Monitored Watchlist:</b> {len(accounts)} accounts\n"
                f"• <b>Following Timeline Ingestion:</b> Active\n"
                f"• <b>Polling Frequency:</b> Every {config.CHECK_INTERVAL_MINUTES} minutes\n"
                f"• <b>AI Provider:</b> {config.AI_PROVIDER.capitalize()} ({config.GEMINI_MODEL})\n"
                f"• <b>Timezone:</b> Indian Standard Time (IST)\n"
            )
            await self.send_reply(chat_id, msg)

    async def generate_on_demand_digest(self, chat_id: str, hours: float, macro_only: bool = False):
        """Generates and delivers an on-demand briefing for the specified time window."""
        label = "Financial & Macro" if macro_only else "Executive"
        await self.send_reply(chat_id, f"🔍 Gathering tweets from the last {hours:g} hour(s)... Gemini is synthesizing your {label} Briefing!")

        from datetime import datetime, timezone, timedelta
        from email.utils import parsedate_to_datetime

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)

        try:
            # 1. Timeline
            timeline = await self.monitor.twitter.fetch_following_timeline(count=100)
            seen = set()
            recent = []
            for t in timeline:
                dt = parsedate_to_datetime(t["created_at"])
                if dt >= cutoff and t["id"] not in seen:
                    seen.add(t["id"])
                    t["dt"] = dt
                    t["time_ist"] = parse_tweet_time_ist(t.get("created_at", ""))
                    recent.append(t)

            # 2. Batch search
            try:
                batch = await self.monitor.twitter.search_tweets_batch(self.monitor.accounts, chunk_size=8, count_per_chunk=20)
                for t in batch:
                    dt = parsedate_to_datetime(t.get("created_at", ""))
                    if dt >= cutoff and t["id"] not in seen:
                        seen.add(t["id"])
                        t["dt"] = dt
                        t["time_ist"] = parse_tweet_time_ist(t.get("created_at", ""))
                        recent.append(t)
            except Exception as be:
                logger.debug(f"On-demand batch search notice: {be}")

            if macro_only:
                macro_handles = {"financelancelot", "northstarcharts", "peterschiff", "deitaone", "ekwufinance", "macropaperr", "michaeljburry"}
                macro_keywords = ["s&p", "nasdaq", "fed", "inflation", "yield", "rate", "stock", "stocks", "uvix", "cpi", "gdp", "rally", "recession"]
                recent = [
                    t for t in recent
                    if t.get("screen_name", "").lower() in macro_handles
                    or any(w in t.get("text", "").lower() for w in macro_keywords)
                ]

            if not recent:
                await self.send_reply(chat_id, f"ℹ️ No matching tweets found in the last {hours:g} hour(s).")
                return

            recent.sort(key=lambda x: x["dt"])
            IST = timezone(timedelta(hours=5, minutes=30))
            start_str = format_clock_ist(cutoff.astimezone(IST))
            end_str = format_clock_ist(now.astimezone(IST))
            if start_str == end_str:
                start_str = format_clock_ist((now - timedelta(minutes=max(15, int(hours * 60)))).astimezone(IST))

            digest = await self.monitor.explainer.generate_roundup(recent, start_str, end_str)
            sent = await self.monitor.telegram.send_message(digest, disable_preview=True)
            if sent:
                logger.info(f"Successfully generated and delivered {hours:g}h digest ({len(recent)} tweets) to Telegram.")
            else:
                logger.warning(f"Failed to deliver {hours:g}h digest to Telegram.")
        except Exception as e:
            logger.error(f"Error generating on-demand digest: {e}", exc_info=True)
            await self.send_reply(chat_id, f"⚠️ Error generating digest: {str(e)[:150]}")


    async def start(self):
        """Long-polling loop for incoming Telegram commands."""
        self.running = True
        logger.info("Telegram command listener started.")

        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    url = f"{self.api_url}/getUpdates"
                    params = {
                        "offset": self.last_update_id + 1,
                        "timeout": 10
                    }
                    async with session.get(url, params=params, timeout=20) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for update in data.get("result", []):
                                self.last_update_id = update["update_id"]
                                msg = update.get("message")
                                if not msg or "text" not in msg:
                                    continue

                                chat_id = str(msg["chat"]["id"])
                                # Only respond to authorized chat id
                                if chat_id != self.authorized_chat_id:
                                    logger.warning(f"Ignoring message from unauthorized chat ID: {chat_id}")
                                    continue

                                text = msg["text"].strip()
                                if text.startswith("/"):
                                    logger.info(f"Received Telegram command: {text}")
                                    await self.handle_command(chat_id, text)
                        elif resp.status == 409:
                            logger.warning("Telegram polling 409 Conflict: another instance is polling getUpdates.")
                            await asyncio.sleep(5)
                        else:
                            logger.warning(f"Telegram getUpdates returned unexpected status {resp.status}")
                            await asyncio.sleep(2)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"Telegram polling loop exception: {e}")
                    await asyncio.sleep(3)

    def stop(self):
        self.running = False
