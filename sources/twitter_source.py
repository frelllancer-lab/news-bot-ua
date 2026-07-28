import asyncio
import logging

from twikit import Client

import config
from .models import Meme

logger = logging.getLogger(__name__)


class TwitterSource:
    QUERIES = [
        "meme filter:images min_faves:300",
        "funny meme filter:media min_faves:200",
        "dank meme filter:images min_faves:150",
        "relatable meme min_faves:200",
        "viral meme filter:media min_faves:500",
        "shitpost min_faves:100",
    ]

    def __init__(self):
        self.client = Client()
        self._logged_in = False

    async def login(self):
        if self._logged_in:
            return

        cookies_file = config.COOKIES_FILE
        if cookies_file.exists():
            try:
                self.client.load_cookies(str(cookies_file))
                self._logged_in = True
                return
            except Exception:
                pass

        if not config.TWITTER_USERNAME:
            raise RuntimeError("Twitter credentials not set")

        await self.client.login(
            auth_info_1=config.TWITTER_USERNAME,
            auth_info_2=config.TWITTER_EMAIL,
            password=config.TWITTER_PASSWORD,
        )
        self._logged_in = True
        self.client.save_cookies(str(cookies_file))

    async def fetch_memes(self, limit: int = 20) -> list[Meme]:
        if not config.TWITTER_USERNAME:
            logger.info("Twitter credentials not set, skipping")
            return []

        await self.login()

        memes: list[Meme] = []
        seen: set[str] = set()

        for query in self.QUERIES:
            try:
                tweets = await self.client.search_tweet(query, "Top")

                for tweet in tweets:
                    if tweet.id in seen:
                        continue
                    seen.add(tweet.id)

                    image_url = None
                    video_url = None

                    if tweet.media:
                        for media in tweet.media:
                            if hasattr(media, "media_url_https"):
                                if media.type == "photo":
                                    image_url = media.media_url_https
                                elif media.type == "video":
                                    variants = getattr(media, "video_info", {}).get("variants", [])
                                    mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
                                    if mp4s:
                                        video_url = mp4s[-1].get("url")

                    if not image_url and not video_url:
                        continue

                    memes.append(Meme(
                        id=f"twitter_{tweet.id}",
                        source="twitter",
                        image_url=image_url,
                        video_url=video_url,
                        gif_url=None,
                        caption=tweet.text[:200] if tweet.text else "meme",
                        score=(tweet.favorite_count or 0) + (tweet.retweet_count or 0) * 2,
                        url=f"https://x.com/i/status/{tweet.id}",
                    ))

                    if len(memes) >= limit:
                        break

            except Exception as e:
                logger.error(f"Twitter search error: {e}")
                continue

            if len(memes) >= limit:
                break
            await asyncio.sleep(2)

        logger.info(f"Twitter: found {len(memes)} memes")
        return memes[:limit]
