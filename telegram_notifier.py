import html
import logging
from typing import Dict, Any, Optional
import aiohttp

import config

logger = logging.getLogger("xbot.telegram")


class TelegramNotifier:
    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send_message(self, text: str, disable_preview: bool = True) -> bool:
        """Sends an HTML formatted message to the configured Telegram chat."""
        if not self.is_configured():
            logger.error("Telegram is not configured. Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
            return False

        # Telegram message character limit is 4096
        if len(text) > 4000:
            text = text[:3990] + "...\n<i>(truncated)</i>"

        endpoint = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=15) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get("ok"):
                        return True
                    else:
                        logger.error(f"Telegram API error ({resp.status}): {data.get('description')}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def notify_tweet(self, tweet: Dict[str, Any], explanation: str) -> bool:
        """Formats and delivers a new tweet notification with its AI breakdown."""
        author = html.escape(tweet.get("author_name", "Author"))
        handle = html.escape(tweet.get("screen_name", "unknown"))
        raw_text = tweet.get("text", "")
        escaped_text = html.escape(raw_text)
        tweet_url = tweet.get("url", f"https://x.com/{handle}")

        # Post type badge
        badge = "🚨 <b>New Post</b>"
        if tweet.get("is_quote"):
            badge = "💬 <b>Quote Post</b>"
        elif tweet.get("is_retweet"):
            badge = "🔄 <b>Retweet</b>"

        message = (
            f"{badge} from <b>{author}</b> (@{handle})\n\n"
            f"📝 <b>Original Tweet:</b>\n"
            f"<i>\"{escaped_text}\"</i>\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Grok-Style Breakdown & Context:</b>\n"
            f"{explanation}\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔗 <a href=\"{tweet_url}\">View on X</a>"
        )

        return await self.send_message(message)

    async def send_startup_ping(self, accounts_count: int, interval_minutes: int) -> bool:
        """Sends a startup notification to confirm bot is active."""
        msg = (
            "🤖 <b>X Monitoring Bot Started!</b>\n\n"
            f"• <b>Monitored Accounts:</b> {accounts_count}\n"
            f"• <b>Check Frequency:</b> Every {interval_minutes} minutes\n"
            f"• <b>AI Explainer:</b> {config.AI_PROVIDER.capitalize()}\n\n"
            "Standing by to break down incoming tweets in simple English! 🚀"
        )
        return await self.send_message(msg)
