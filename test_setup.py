import asyncio
import sys
import config
from telegram_notifier import TelegramNotifier
from ai_explainer import get_ai_explainer
from twitter_fetcher import TwitterFetcher


async def test_telegram():
    print("\n--- 1. Testing Telegram Bot ---")
    notifier = TelegramNotifier()
    if not notifier.is_configured():
        print("❌ FAIL: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env")
        return False

    print("Sending test message to your Telegram chat...")
    success = await notifier.send_message(
        "👋 <b>XBOT Diagnostic Test</b>\n\n"
        "If you are reading this, your Telegram bot token and chat ID are working perfectly! ✅"
    )
    if success:
        print("✅ SUCCESS: Telegram test message sent! Check your Telegram app.")
        return True
    else:
        print("❌ FAIL: Could not send Telegram message. Check token, chat ID, or bot permissions.")
        return False


async def test_ai():
    print(f"\n--- 2. Testing AI Explainer ({config.AI_PROVIDER.capitalize()}) ---")
    try:
        explainer = get_ai_explainer()
    except Exception as e:
        print(f"❌ FAIL: Could not initialize AI provider: {e}")
        return False

    sample_tweet = {
        "author_name": "Elon Musk",
        "screen_name": "elonmusk",
        "text": "Starship Flight 7 propellant loading underway. Exciting times ahead!",
        "url": "https://x.com/elonmusk"
    }

    print("Generating Grok-style sample explanation...")
    try:
        explanation = await explainer.explain(sample_tweet)
        print("\n" + "=" * 40)
        print(explanation)
        print("=" * 40)
        print("✅ SUCCESS: AI explainer generated breakdown successfully!")
        return True
    except Exception as e:
        print(f"❌ FAIL: AI generation error: {e}")
        return False


async def test_twitter():
    print("\n--- 3. Testing Twitter Connection & Scraping ---")
    fetcher = TwitterFetcher()
    print("Authenticating with Twitter...")
    authenticated = await fetcher.authenticate()
    if not authenticated:
        print("❌ FAIL: Could not authenticate with Twitter. Verify TWITTER_AUTH_TOKEN and TWITTER_CT0 in .env")
        return False

    test_account = "OpenAI"
    print(f"Fetching latest tweet from @{test_account}...")
    tweets = await fetcher.fetch_recent_tweets(test_account, count=3)
    if tweets:
        print(f"✅ SUCCESS: Retrieved {len(tweets)} tweets from @{test_account}!")
        latest = tweets[0]
        print(f"Latest tweet ID: {latest['id']}")
        print(f"Text snippet: {latest['text'][:120]}...")
        return True
    else:
        print("⚠️ WARNING: Authentication succeeded, but no tweets were retrieved. Check account or rate limits.")
        return False


async def main():
    print("========================================")
    print("      XBOT Diagnostic & Setup Test      ")
    print("========================================")

    telegram_ok = await test_telegram()
    ai_ok = await test_ai()
    twitter_ok = await test_twitter()

    print("\n========================================")
    print("              Summary                   ")
    print("========================================")
    print(f"Telegram Bot:     {'✅ OK' if telegram_ok else '❌ Action Required'}")
    print(f"AI Explainer:     {'✅ OK' if ai_ok else '❌ Action Required'}")
    print(f"Twitter Scraping: {'✅ OK' if twitter_ok else '❌ Action Required'}")
    print("========================================\n")


if __name__ == "__main__":
    asyncio.run(main())
