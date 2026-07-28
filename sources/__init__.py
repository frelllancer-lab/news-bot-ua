import asyncio
import logging
import random

from .models import Meme
from .reddit import RedditSource
from .twitter_source import TwitterSource

logger = logging.getLogger(__name__)


class MemeAggregator:
    def __init__(self):
        self.reddit = RedditSource()
        self.twitter = TwitterSource()

    async def close(self):
        pass

    async def fetch_memes(self, limit: int = 30) -> list[Meme]:
        tasks = [
            self._safe_fetch(self.reddit.fetch_memes, limit // 2),
            self._safe_fetch(self.twitter.fetch_memes, limit // 2),
        ]
        results = await asyncio.gather(*tasks)

        all_memes: list[Meme] = []
        for memes in results:
            if memes:
                all_memes.extend(memes)

        random.shuffle(all_memes)
        logger.info(f"Aggregated {len(all_memes)} memes from all sources")
        return all_memes[:limit]

    async def _safe_fetch(self, func, limit: int) -> list[Meme]:
        try:
            return await func(limit)
        except Exception as e:
            logger.error(f"Source error: {e}")
            return []
