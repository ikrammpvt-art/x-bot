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

    @staticmethod
    def sanitize_and_balance_html(text: str) -> str:
        """Sanitizes raw AI text for Telegram's strict HTML parser and auto-closes broken tags."""
        import re

        # 1. Escape stray ampersands not part of standard HTML entities
        text = re.sub(r'&(?!(?:amp|lt|gt|quot);)', '&amp;', text)

        # 2. Fix malformed <a href=...> without quotes
        text = re.sub(r'<a\s+href=([^\s\"<>]+)>', r'<a href="\1">', text)

        # 3. Strip any unsupported HTML tags like <p>, </p>, <br>, <div>, etc.
        text = re.sub(r'</?(?:p|div|span|ul|ol|li|br|h\d)[^>]*>', '\n', text, flags=re.IGNORECASE)

        # 4. Auto-balance and close unclosed Telegram tags
        tag_names = ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'code', 'pre', 'a']
        tokens = re.findall(r'(</?([a-zA-Z]+)(?:\s+[^>]*?)?>)', text)
        open_stack = []
        for full_tag, name in tokens:
            name_lower = name.lower()
            if name_lower not in tag_names:
                continue
            if full_tag.startswith('</'):
                if open_stack and open_stack[-1] == name_lower:
                    open_stack.pop()
                elif name_lower in open_stack:
                    while open_stack and open_stack[-1] != name_lower:
                        open_stack.pop()
                    if open_stack:
                        open_stack.pop()
            else:
                open_stack.append(name_lower)

        for tag in reversed(open_stack):
            text += f'</{tag}>'

        # Clean multiple blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _split_text(self, text: str, max_length: int = 3500) -> list:
        """Splits long message into chunks along paragraph boundaries, auto-balancing HTML in each chunk."""
        if len(text) <= max_length:
            return [self.sanitize_and_balance_html(text)]

        chunks = []
        current_chunk = []
        current_len = 0

        paragraphs = text.split("\n\n")
        for p in paragraphs:
            p_len = len(p) + 2
            if current_len + p_len > max_length:
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append(self.sanitize_and_balance_html(chunk_text))
                    current_chunk = [p]
                    current_len = len(p)
                else:
                    lines = p.split("\n")
                    sub_chunk = []
                    sub_len = 0
                    for line in lines:
                        if sub_len + len(line) + 1 > max_length:
                            chunks.append(self.sanitize_and_balance_html("\n".join(sub_chunk)))
                            sub_chunk = [line]
                            sub_len = len(line)
                        else:
                            sub_chunk.append(line)
                            sub_len += len(line) + 1
                    if sub_chunk:
                        current_chunk = ["\n".join(sub_chunk)]
                        current_len = len(current_chunk[0])
            else:
                current_chunk.append(p)
                current_len += p_len

        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(self.sanitize_and_balance_html(chunk_text))

        return chunks


    async def _send_single(self, text: str, disable_preview: bool = True) -> bool:
        import re
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
                    elif "can't parse entities" in str(data.get("description", "")).lower():
                        logger.warning("Telegram HTML entity parsing failed, retrying with clean plain text...")
                        # Strip HTML tags and send cleanly as plain text so message is NEVER lost
                        clean_text = re.sub(r"<[^>]+>", "", text)
                        clean_payload = {
                            "chat_id": self.chat_id,
                            "text": clean_text,
                            "disable_web_page_preview": disable_preview
                        }
                        async with session.post(endpoint, json=clean_payload, timeout=15) as resp2:
                            data2 = await resp2.json()
                            if resp2.status == 200 and data2.get("ok"):
                                return True
                            logger.error(f"Plain text fallback also failed: {data2.get('description')}")
                            return False
                    else:
                        logger.error(f"Telegram API error ({resp.status}): {data.get('description')}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_message(self, text: str, disable_preview: bool = True) -> bool:
        """Sends an HTML formatted message to Telegram, automatically splitting into parts if long."""
        if not self.is_configured():
            logger.error("Telegram is not configured. Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
            return False

        chunks = self._split_text(text, max_length=3800)
        total = len(chunks)
        all_ok = True

        for i, chunk in enumerate(chunks, 1):
            msg = chunk
            if total > 1:
                msg = f"<b>[Part {i}/{total}]</b>\n\n{chunk}"
            ok = await self._send_single(msg, disable_preview)
            if not ok:
                all_ok = False
            if total > 1:
                import asyncio
                await asyncio.sleep(0.5)

        if all_ok:
            logger.info(f"Successfully delivered {total} message chunk(s) to Telegram chat {self.chat_id}.")

        return all_ok


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
