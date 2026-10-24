import asyncio
import logging
import random
from typing import List, Optional, Dict, Any
from twikit import Client
from twikit.errors import TwitterException

import config
import database

logger = logging.getLogger("xbot.twitter")


class TwitterFetcher:
    def __init__(self):
        self.client = Client("en-US")
        self.is_authenticated = False

    async def authenticate(self) -> bool:
        """Authenticates with Twitter using cookies or credentials."""
        # Method 1: Use auth_token and ct0 from environment if provided
        if config.TWITTER_AUTH_TOKEN and config.TWITTER_CT0:
            logger.info("Authenticating with Twitter cookies from environment...")
            try:
                self.client.set_cookies({
                    "auth_token": config.TWITTER_AUTH_TOKEN,
                    "ct0": config.TWITTER_CT0
                })
                # Save cookies to file for persistence
                self.client.save_cookies(str(config.COOKIES_PATH))
                self.is_authenticated = True
                logger.info("Successfully configured Twitter cookies from environment.")
                return True
            except Exception as e:
                logger.error(f"Failed to set Twitter cookies: {e}")

        # Method 2: Load existing saved cookies.json file
        if config.COOKIES_PATH.exists():
            try:
                logger.info(f"Loading existing session from {config.COOKIES_PATH}...")
                self.client.load_cookies(str(config.COOKIES_PATH))
                self.is_authenticated = True
                logger.info("Loaded saved Twitter cookies.")
                return True
            except Exception as e:
                logger.warning(f"Could not load cookies.json: {e}")

        # Method 3: Login using username/email/password
        if config.TWITTER_USERNAME and config.TWITTER_PASSWORD:
            logger.info(f"Logging in as Twitter user @{config.TWITTER_USERNAME}...")
            try:
                await self.client.login(
                    auth_info_1=config.TWITTER_USERNAME,
                    auth_info_2=config.TWITTER_EMAIL,
                    password=config.TWITTER_PASSWORD,
                    cookies_file=str(config.COOKIES_PATH)
                )
                self.is_authenticated = True
                logger.info("Twitter login successful!")
                return True
            except Exception as e:
                logger.error(f"Twitter login failed: {e}")
                return False

        logger.error(
            "No Twitter credentials or cookies found! "
            "Please provide TWITTER_AUTH_TOKEN and TWITTER_CT0 (or TWITTER_USERNAME/PASSWORD) in .env"
        )
        return False

    async def get_user_id(self, screen_name: str) -> Optional[str]:
        """Gets user_id for screen_name, checking SQLite cache first."""
        cached_id = database.get_cached_user_id(screen_name)
        if cached_id:
            return cached_id

        try:
            user = await self.client.get_user_by_screen_name(screen_name)
            if user and hasattr(user, "id"):
                database.set_cached_user_id(screen_name, user.id)
                return str(user.id)
        except Exception as e:
            logger.error(f"Failed to resolve user ID for @{screen_name}: {e}")
            return None

    async def fetch_recent_tweets(self, screen_name: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        Fetches the latest tweets for a user.
        Filters out replies or retweets if configured.
        """
        if not self.is_authenticated:
            success = await self.authenticate()
            if not success:
                logger.error("Cannot fetch tweets: Not authenticated.")
                return []

        user_id = await self.get_user_id(screen_name)
        if not user_id:
            logger.warning(f"Could not retrieve user ID for @{screen_name}")
            return []

        try:
            # tweet_type='Tweets' gets user tweets + retweets
            result = await self.client.get_user_tweets(user_id, tweet_type="Tweets", count=count)
        except TwitterException as te:
            logger.error(f"Twitter API error fetching @{screen_name}: {te}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching tweets for @{screen_name}: {e}")
            return []

        parsed_tweets = []
        for tweet in result:
            tweet_id = str(tweet.id)
            is_retweet = getattr(tweet, "retweeted_tweet", None) is not None
            is_reply = getattr(tweet, "in_reply_to", None) is not None
            is_quote = getattr(tweet, "is_quote_status", False)

            # Apply filters based on configuration
            if is_retweet and not config.INCLUDE_RETWEETS:
                continue
            if is_reply and not config.INCLUDE_REPLIES:
                continue

            # Resolve author name & handle
            author_name = screen_name
            if hasattr(tweet, "user") and tweet.user:
                author_name = getattr(tweet.user, "name", screen_name)

            tweet_text = getattr(tweet, "text", "") or getattr(tweet, "full_text", "")
            tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
            created_at = str(getattr(tweet, "created_at", ""))

            # Extract media URLs if any
            media_urls = []
            if hasattr(tweet, "media") and tweet.media:
                for m in tweet.media:
                    media_url = getattr(m, "media_url_https", None) or getattr(m, "url", None)
                    if media_url:
                        media_urls.append(media_url)

            parsed_tweets.append({
                "id": tweet_id,
                "screen_name": screen_name,
                "author_name": author_name,
                "text": tweet_text,
                "url": tweet_url,
                "created_at": created_at,
                "is_retweet": is_retweet,
                "is_quote": is_quote,
                "is_reply": is_reply,
                "media_urls": media_urls
            })

        database.update_account_checked(screen_name)
        return parsed_tweets

    async def search_tweets_batch(self, usernames: List[str], chunk_size: int = 12, count_per_chunk: int = 20) -> List[Dict[str, Any]]:
        """
        Uses Twitter search with 'from:user1 OR from:user2' syntax.
        Queries 12 accounts per single request, drastically reducing API calls and avoiding 429 rate limits.
        """
        if not self.is_authenticated:
            success = await self.authenticate()
            if not success:
                logger.error("Cannot search tweets: Not authenticated.")
                return []

        all_parsed = []
        search_available = True
        for i in range(0, len(usernames), chunk_size):
            if not search_available:
                break
            chunk = usernames[i:i + chunk_size]
            query = " OR ".join([f"from:{u}" for u in chunk])
            logger.info(f"Querying batch of {len(chunk)} accounts ({chunk[0]}...)...")

            try:
                results = await self.client.search_tweet(query, "Latest", count=count_per_chunk)
            except TwitterException as te:
                if "404" in str(te):
                    logger.info("Twitter SearchTimeline is not available on datacenter IP (404). Following timeline feed is active as primary ingestion.")
                    search_available = False
                    break
                logger.error(f"Search API error on batch: {te}")
                continue
            except Exception as e:
                logger.error(f"Search unexpected error on batch: {e}")
                continue

            for tweet in results:
                try:
                    tweet_id = str(tweet.id)
                    is_retweet = getattr(tweet, "retweeted_tweet", None) is not None
                    is_reply = getattr(tweet, "in_reply_to", None) is not None
                    is_quote = getattr(tweet, "is_quote_status", False)

                    if is_retweet and not config.INCLUDE_RETWEETS:
                        continue
                    if is_reply and not config.INCLUDE_REPLIES:
                        continue

                    screen_name = "unknown"
                    author_name = "User"
                    if hasattr(tweet, "user") and tweet.user:
                        screen_name = getattr(tweet.user, "screen_name", "unknown")
                        author_name = getattr(tweet.user, "name", screen_name)

                    tweet_text = getattr(tweet, "text", "") or getattr(tweet, "full_text", "")
                    tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
                    created_at = str(getattr(tweet, "created_at", ""))

                    all_parsed.append({
                        "id": tweet_id,
                        "screen_name": screen_name,
                        "author_name": author_name,
                        "text": tweet_text,
                        "url": tweet_url,
                        "created_at": created_at,
                        "is_retweet": is_retweet,
                        "is_quote": is_quote,
                        "is_reply": is_reply
                    })
                except Exception:
                    continue

            await self.polite_delay(1.5, 3.0)

        return all_parsed

    async def polite_delay(self, min_seconds: float = 2.0, max_seconds: float = 4.0):
        """Introduces a small random delay between account queries to avoid bot detection."""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    async def fetch_following_timeline(self, count: int = 70) -> List[Dict[str, Any]]:
        """
        Fetches the chronological Following feed from the authenticated Twitter account.
        Ensures that any account the user follows on X is captured in real-time,
        even if not yet added to the watchlist.
        """
        if not self.is_authenticated:
            success = await self.authenticate()
            if not success:
                logger.error("Cannot fetch following timeline: Not authenticated.")
                return []

        timeline = []
        try:
            timeline = await self.client.get_latest_timeline(count=count)
        except Exception as e:
            logger.warning(f"get_latest_timeline notice ({e}), trying fallback get_timeline...")
            try:
                timeline = await self.client.get_timeline(count=count)
            except Exception as e2:
                logger.error(f"Both timeline endpoints failed: {e2}")
                return []

        parsed = []
        for tweet in timeline:
            try:
                tweet_id = str(tweet.id)
                is_retweet = getattr(tweet, "retweeted_tweet", None) is not None
                is_reply = getattr(tweet, "in_reply_to", None) is not None
                is_quote = getattr(tweet, "is_quote_status", False)

                if is_retweet and not config.INCLUDE_RETWEETS:
                    continue
                if is_reply and not config.INCLUDE_REPLIES:
                    continue

                screen_name = "unknown"
                author_name = "User"
                if hasattr(tweet, "user") and tweet.user:
                    screen_name = getattr(tweet.user, "screen_name", "unknown")
                    author_name = getattr(tweet.user, "name", screen_name)

                tweet_text = getattr(tweet, "text", "") or getattr(tweet, "full_text", "")
                tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
                created_at = str(getattr(tweet, "created_at", ""))

                parsed.append({
                    "id": tweet_id,
                    "screen_name": screen_name,
                    "author_name": author_name,
                    "text": tweet_text,
                    "url": tweet_url,
                    "created_at": created_at,
                    "is_retweet": is_retweet,
                    "is_quote": is_quote,
                    "is_reply": is_reply
                })
            except Exception as pe:
                logger.debug(f"Skipped timeline item due to parse error: {pe}")
                continue

        return parsed


