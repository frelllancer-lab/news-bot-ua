import logging
import random

import httpx

from .models import Meme

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


class RedditSource:
    async def fetch_memes(self, limit: int = 20) -> list[Meme]:
        memes: list[Meme] = []
        tasks = [
            self._fetch_imgflip(limit),
            self._fetch_memegen(limit),
            self._fetch_imgur(limit),
            self._fetch_random_doge(limit),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                memes.extend(r)

        random.shuffle(memes)
        logger.info(f"Found {len(memes)} memes total")
        return memes[:limit]

    async def _fetch_imgflip(self, limit: int = 15) -> list[Meme]:
        memes: list[Meme] = []
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=HEADERS) as client:
            resp = await client.get("https://api.imgflip.com/get_memes")
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("data", {}).get("memes", []):
                if not item.get("url"):
                    continue
                memes.append(Meme(
                    id=f"imgflip_{item['id']}",
                    source="imgflip",
                    image_url=item["url"],
                    video_url=None,
                    gif_url=None,
                    caption=item.get("name", "meme"),
                    score=random.randint(100, 10000),
                    url=item.get("page_url", item["url"]),
                ))
                if len(memes) >= limit:
                    break
        return memes

    async def _fetch_memegen(self, limit: int = 10) -> list[Meme]:
        memes: list[Meme] = []
        templates = [
            ("drake", "normal", "big brain"),
            ("buzz", "old", "new"),
            ("doge", "much meme", "very funny"),
            ("crying", "when mom checks phone", "when she sees chat"),
            ("change", "my mind", "borscht is best soup"),
            ("uno", "do homework", "reverse card - do it yourself"),
            ("panik", "exam tomorrow", "kalm - google translate"),
            ("expanding", "brain", "using calculator for 2+2"),
            ("distracted", "homework", "youtube shorts"),
            ("woman-yelling", "why no homework", "cat sitting calmly"),
            ("two-buttons", "sleep", "one more episode"),
            ("this-is-fine", "everything is fine", "grades D D D"),
        ]

        async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=HEADERS) as client:
            for template_name, top_text, bottom_text in templates[:limit]:
                try:
                    top = top_text.replace(" ", "_").replace("?", "~q").replace("'", "~aq")
                    bot = bottom_text.replace(" ", "_").replace("?", "~q").replace("'", "~aq")
                    url = f"https://api.memegen.link/images/{template_name}/{top}/{bot}.jpg"
                    resp = await client.head(url)
                    if resp.status_code == 200:
                        memes.append(Meme(
                            id=f"memegen_{template_name}_{random.randint(1000,9999)}",
                            source="memegen",
                            image_url=url,
                            video_url=None,
                            gif_url=None,
                            caption=f"{top_text} / {bottom_text}",
                            score=random.randint(50, 5000),
                            url=url,
                        ))
                except Exception:
                    continue
                if len(memes) >= limit:
                    break
        return memes

    async def _fetch_imgur(self, limit: int = 10) -> list[Meme]:
        memes: list[Meme] = []
        gallery_ids = [
            "a/6S6w3t", "r/funny", "r/memes", "r/dankmemes",
            "a/y6wGJ", "r/me_irl", "r/ProgrammerHumor",
        ]

        async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=HEADERS) as client:
            for gallery in random.sample(gallery_ids, min(3, len(gallery_ids))):
                try:
                    resp = await client.get(f"https://imgur.com/gallery/{gallery}/hot/viral.json")
                    if resp.status_code != 200:
                        continue
                    items = resp.json().get("data", [])
                    for item in items[:5]:
                        if item.get("animated"):
                            gif_url = item.get("mp4") or item.get("gifv", "").replace(".gifv", ".gif")
                            memes.append(Meme(
                                id=f"imgur_{item.get('id', random.randint(1,99999))}",
                                source="imgur",
                                image_url=None,
                                video_url=None,
                                gif_url=gif_url,
                                caption=item.get("title", "meme"),
                                score=item.get("points", random.randint(100, 5000)),
                                url=item.get("link", ""),
                            ))
                        else:
                            img_url = f"https://i.imgur.com/{item.get('id', '')}.jpg"
                            memes.append(Meme(
                                id=f"imgur_{item.get('id', random.randint(1,99999))}",
                                source="imgur",
                                image_url=img_url,
                                video_url=None,
                                gif_url=None,
                                caption=item.get("title", "meme"),
                                score=item.get("points", random.randint(100, 5000)),
                                url=item.get("link", ""),
                            ))
                        if len(memes) >= limit:
                            break
                except Exception as e:
                    logger.error(f"Imgur error: {e}")
                    continue
                if len(memes) >= limit:
                    break
        return memes

    async def _fetch_random_doge(self, limit: int = 5) -> list[Meme]:
        memes: list[Meme] = []
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=HEADERS) as client:
            for _ in range(limit):
                try:
                    resp = await client.get("https://random.dog/woof.json")
                    if resp.status_code == 200:
                        data = resp.json()
                        url = data.get("url", "")
                        if url.endswith((".jpg", ".png", ".gif", ".jpeg")):
                            full_url = f"https://random.dog{url}" if not url.startswith("http") else url
                            memes.append(Meme(
                                id=f"doge_{random.randint(1,999999)}",
                                source="random.dog",
                                image_url=full_url,
                                video_url=None,
                                gif_url=None,
                                caption="random doggo",
                                score=random.randint(1, 1000),
                                url=full_url,
                            ))
                except Exception:
                    continue
        return memes


import asyncio
