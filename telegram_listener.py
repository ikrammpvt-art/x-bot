import asyncio
import html
import logging
from typing import Optional
import aiohttp

import config
import database

logger = logging.getLogger("xbot.telegram_listener")


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
                "🤖 <b>X Monitor Command Center</b>\n\n"
                "• <code>/list</code> — View all currently monitored accounts\n"
                "• <code>/add &lt;handle&gt;</code> — Add account(s) to monitor\n"
                "  <i>Example:</i> <code>/add PeterSchiff</code>\n"
                "• <code>/remove &lt;handle&gt;</code> — Stop monitoring an account\n"
                "  <i>Example:</i> <code>/remove PeterSchiff</code>\n"
                "• <code>/roundup</code> or <code>/check</code> — Trigger an immediate scan & roundup\n"
                "• <code>/status</code> — Check bot health and account count\n"
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

        elif cmd == "/status":
            accounts = database.get_all_monitored_accounts()
            msg = (
                "🟢 <b>X Monitor Bot Status: Active</b>\n\n"
                f"• <b>Monitored Accounts:</b> {len(accounts)}\n"
                f"• <b>Polling Frequency:</b> Every {config.CHECK_INTERVAL_MINUTES} minutes\n"
                f"• <b>AI Provider:</b> {config.AI_PROVIDER.capitalize()} ({config.GEMINI_MODEL})\n"
                f"• <b>Timezone:</b> Indian Standard Time (IST)\n"
            )
            await self.send_reply(chat_id, msg)

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
                            # Conflict: another instance might be polling
                            await asyncio.sleep(5)
                        else:
                            await asyncio.sleep(2)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"Telegram polling loop exception: {e}")
                    await asyncio.sleep(3)

    def stop(self):
        self.running = False
