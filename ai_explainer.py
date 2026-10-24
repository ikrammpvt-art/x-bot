import json
import logging
from typing import Dict, Any, List, Optional
import aiohttp

import config

logger = logging.getLogger("xbot.ai")

SYSTEM_PROMPT = """You are an intelligent, witty, and objective social media analyst like Grok.
Your mission is to explain tweets in simple, crystal-clear English with essential background context.

Users follow industry leaders, tech founders, politicians, and influencers whose posts are often cryptic, full of jargon, memes, sarcasm, or references to breaking news.

When given a tweet, your response MUST follow this exact format:

💡 <b>Plain English:</b>
A 1-2 sentence translation of what the person is actually saying, stripping away all fluff, buzzwords, and cryptic phrasing.

🔍 <b>Context & Background:</b>
2-3 bullet points explaining the backstory: What event, news, ongoing debate, controversy, technology release, or market movement prompted this post? Explain any memes, abbreviations, or inside jokes.

🎯 <b>Why It Matters:</b>
1-2 concise sentences on why people care, the implications, or the takeaway for followers/the industry.

Rules:
- Be concise, direct, and conversational.
- Do not make things up. If context is uncertain, state the most likely interpretation.
- Use simple HTML tags compatible with Telegram (<b>bold</b>, <i>italic</i>). Do NOT use markdown asterisks (* or **).
"""

ROUNDUP_SYSTEM_PROMPT = """You are an elite geopolitical and macroeconomic intelligence briefing writer.
You synthesize incoming tweets into an executive "X roundup" newsletter/digest.

Your output MUST match this exact style and structure:

<b>X roundup, {start_time} to {end_time} IST. The big story is {one concise sentence summarizing the main breaking event}.</b>

{Category 1 (e.g. Iran, Middle East, Russia-Ukraine, etc.)}

<a href="{url}">@{username}</a> at {time} IST: {Concise plain English summary in 1 sentence. Include critical context or skepticism if unconfirmed}.

{If multiple accounts report the same event, combine them:}
<a href="{url1}">@{user1}</a> at {time1} IST and <a href="{url2}">@{user2}</a> at {time2} IST: {Unified summary}.

<i>Context: {1-2 sentences clarifying what is confirmed vs unverified rumors, why it matters, or missing context.}</i>

Financial Markets & Macro (CRITICAL: If any tweets relate to stocks, S&P 500, yields, commodities, currencies, or market depth—such as from @FinanceLancelot, @PeterSchiff, @NorthstarCharts, @DeItaone—you MUST include this section and summarize them!)

<a href="{url}">@{username}</a> at {time} IST: {Summary of market movement, indicators, or analysis}.

Rules:
- Strictly use Telegram-compatible HTML tags: <b>bold</b>, <i>italic</i>, and <a href="...">clickable links</a>.
- Every username MUST be a clickable link using the exact URL provided in the input, formatted as <a href="{tweet_url}">@{username}</a>.
- Write in simple, natural English (no corporate jargon or robotic phrasing).
- Be skeptical and journalistic: clearly distinguish confirmed official claims from unverified scanner chatter.
- Do NOT omit financial or market commentary if present in the input. Give both defense/geopolitics and macro finance their proper sections.
- Do NOT use markdown formatting like ** or *. Use <b> and <i> only.
"""



class BaseExplainer:
    async def explain(self, tweet: Dict[str, Any]) -> str:
        raise NotImplementedError

    async def generate_roundup(self, tweets: List[Dict[str, Any]], start_time_ist: str, end_time_ist: str) -> str:
        raise NotImplementedError


class GeminiExplainer(BaseExplainer):
    def __init__(self):
        from google import genai
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment or .env")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model = config.GEMINI_MODEL

    async def explain(self, tweet: Dict[str, Any]) -> str:
        author = tweet.get("author_name", "User")
        handle = tweet.get("screen_name", "unknown")
        text = tweet.get("text", "")

        user_content = f"""Author: {author} (@{handle})
Tweet text:
"{text}"

Please provide a Grok-style plain English explanation and background context for this tweet."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=f"{SYSTEM_PROMPT}\n\n{user_content}"
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return f"💡 <b>Plain English:</b> {text}\n\n⚠️ <i>(AI explanation unavailable: {str(e)[:100]})</i>"

    async def _generate_single_batch(self, tweets: List[Dict[str, Any]], start_time_ist: str, end_time_ist: str, is_first: bool = True) -> str:
        tweet_items = []
        for i, t in enumerate(tweets, 1):
            handle = t.get("screen_name", "user")
            url = t.get("url", f"https://x.com/{handle}")
            time_ist = t.get("time_ist", "")
            text = t.get("text", "").replace("\n", " ")
            tweet_items.append(f"{i}. Author: @{handle} | URL: {url} | Time: {time_ist} | Text: {text}")

        instruction = ""
        if not is_first:
            instruction = "\nNote: This is a continuation section. Do NOT repeat the main 'X roundup... The big story is...' headline. Output directly with the category headers and entries.\n"

        prompt = (
            f"{ROUNDUP_SYSTEM_PROMPT}\n\n"
            f"{instruction}"
            f"Start Time: {start_time_ist}\n"
            f"End Time: {end_time_ist}\n\n"
            f"Input Tweets ({len(tweets)} total - ensure 100% of these are covered):\n" + "\n".join(tweet_items)
        )

        try:
            import asyncio
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini roundup generation error: {e}")
            lines = []
            if is_first:
                lines.append(f"<b>X roundup, {start_time_ist} to {end_time_ist} IST.</b>\n")
            for t in tweets:
                h = t.get("screen_name", "user")
                u = t.get("url", f"https://x.com/{h}")
                tm = t.get("time_ist", "")
                tx = t.get("text", "")[:120]
                lines.append(f"<a href=\"{u}\">@{h}</a> at {tm}: {tx}...")
            return "\n".join(lines)

    async def generate_roundup(self, tweets: List[Dict[str, Any]], start_time_ist: str, end_time_ist: str) -> str:
        import asyncio
        if not tweets:
            return f"<b>X roundup, {start_time_ist} to {end_time_ist} IST.</b>\nNo new posts detected."

        # If 30 or fewer tweets, single batch ensures full cohesive narrative
        if len(tweets) <= 30:
            return await self._generate_single_batch(tweets, start_time_ist, end_time_ist, is_first=True)

        # For large volumes (multi-hour windows), chunk and run parallel with asyncio.gather
        chunk_size = 30
        chunks = [tweets[i:i + chunk_size] for i in range(0, len(tweets), chunk_size)]
        tasks = [
            self._generate_single_batch(chunk, start_time_ist, end_time_ist, is_first=(idx == 0))
            for idx, chunk in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks)
        return "\n\n".join(results)



class GroqExplainer(BaseExplainer):
    def __init__(self):
        from groq import AsyncGroq
        if not config.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set in environment or .env")
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY)
        self.model = config.GROQ_MODEL

    async def explain(self, tweet: Dict[str, Any]) -> str:
        author = tweet.get("author_name", "User")
        handle = tweet.get("screen_name", "unknown")
        text = tweet.get("text", "")

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Author: {author} (@{handle})\nTweet: {text}"}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq generation error: {e}")
            return f"💡 <b>Plain English:</b> {text}"

    async def generate_roundup(self, tweets: List[Dict[str, Any]], start_time_ist: str, end_time_ist: str) -> str:
        tweet_items = [
            f"- @{t.get('screen_name')} ({t.get('time_ist')}): {t.get('text')} [URL: {t.get('url')}]"
            for t in tweets
        ]
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ROUNDUP_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Roundup from {start_time_ist} to {end_time_ist} IST:\n" + "\n".join(tweet_items)}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq roundup error: {e}")
            return f"<b>X roundup, {start_time_ist} to {end_time_ist} IST</b>\n" + "\n".join(tweet_items)


class OllamaExplainer(BaseExplainer):
    def __init__(self):
        self.base_url = config.OLLAMA_BASE_URL.rstrip("/")
        self.model = config.OLLAMA_MODEL

    async def explain(self, tweet: Dict[str, Any]) -> str:
        return f"💡 <b>Plain English:</b> {tweet.get('text', '')}"

    async def generate_roundup(self, tweets: List[Dict[str, Any]], start_time_ist: str, end_time_ist: str) -> str:
        return f"<b>X roundup, {start_time_ist} to {end_time_ist} IST</b>"


class XAIExplainer(BaseExplainer):
    def __init__(self):
        if not config.XAI_API_KEY:
            raise ValueError("XAI_API_KEY is not set in environment or .env")
        self.api_key = config.XAI_API_KEY
        self.model = config.XAI_MODEL

    async def explain(self, tweet: Dict[str, Any]) -> str:
        return f"💡 <b>Plain English:</b> {tweet.get('text', '')}"

    async def generate_roundup(self, tweets: List[Dict[str, Any]], start_time_ist: str, end_time_ist: str) -> str:
        return f"<b>X roundup, {start_time_ist} to {end_time_ist} IST</b>"


def get_ai_explainer() -> BaseExplainer:
    provider = config.AI_PROVIDER
    if provider == "gemini":
        return GeminiExplainer()
    elif provider == "groq":
        return GroqExplainer()
    elif provider == "ollama":
        return OllamaExplainer()
    elif provider in ("xai", "grok"):
        return XAIExplainer()
    else:
        return GeminiExplainer()
