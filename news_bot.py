import asyncio
import logging
import random
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
import trafilatura
from deep_translator import GoogleTranslator
from telegraph import Telegraph

import config
from storage.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("news-bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    id: str
    title: str
    summary: str
    full_text: str
    url: str
    image_url: str | None
    source: str
    published: str


RSS_FEEDS = {
    "Україна": [
        "https://rss.unian.net/site/news_ukr.rss",
        "https://nv.ua/ukr/rss/all.xml",
        "https://www.bbc.com/ukrainian/index.xml",
    ],
    "Світ": [
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/xml/rss-en-world",
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

SOURCE_NAMES = {
    "rss.unian.net": "UNIAN",
    "nv.ua": "NV.ua",
    "www.bbc.com": "BBC",
    "rss.nytimes.com": "NY Times",
    "feeds.bbci.co.uk": "BBC World",
    "www.aljazeera.com": "Al Jazeera",
    "rss.dw.com": "DW",
}

EN_SOURCES = {"NY Times", "BBC World", "Al Jazeera", "DW"}

translator = GoogleTranslator(source="en", target="uk")


class NewsBot:
    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.db = Database()
        self.api = f"https://api.telegram.org/bot{self.token}"
        self._offset = 0
        self.http = httpx.AsyncClient(follow_redirects=True, timeout=30, headers=HEADERS)
        self.telegraph = Telegraph()
        self.telegraph.create_account(short_name="NewsBot")

    async def _api(self, method: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.api}/{method}", json=kwargs)
            return resp.json()

    async def _send_text(self, chat_id: int, text: str):
        await self._api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")

    def _extract_source_name(self, feed_url: str) -> str:
        host = feed_url.split("//")[1].split("/")[0].replace("www.", "")
        return SOURCE_NAMES.get(host, host)

    def _parse_rss(self, xml_text: str, source_name: str) -> list[NewsItem]:
        items: list[NewsItem] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return items

        for item_el in root.iter("item"):
            title = item_el.findtext("title", "").strip()
            if not title:
                continue

            link = item_el.findtext("link", "").strip()
            desc = item_el.findtext("description", "").strip()
            pub = item_el.findtext("pubDate", "").strip()

            desc_clean = re.sub(r"<[^>]+>", "", desc)[:300]

            image_url = None
            for media in item_el.iter():
                tag = media.tag.lower()
                if "url" in tag and ("image" in tag or "thumbnail" in tag):
                    image_url = media.get("url")
                    break
                if media.tag == "media:content" and media.get("medium") == "image":
                    image_url = media.get("url")
                    break
                if media.tag == "enclosure" and "image" in media.get("type", ""):
                    image_url = media.get("url")
                    break

            if not image_url and "<img" in desc.lower():
                match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc, re.IGNORECASE)
                if match:
                    image_url = match.group(1)

            item_id = f"{source_name}_{hash(title)}"
            items.append(NewsItem(
                id=item_id,
                title=title,
                summary=desc_clean,
                full_text="",
                url=link,
                image_url=image_url,
                source=source_name,
                published=pub,
            ))

        return items

    async def fetch_full_text(self, url: str) -> str:
        try:
            resp = await self.http.get(url)
            if resp.status_code != 200:
                return ""
            extracted = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_precision=False,
            )
            return extracted or ""
        except Exception as e:
            logger.debug(f"Full text fetch failed for {url}: {e}")
            return ""

    def _translate_text(self, text: str, source: str) -> str:
        if source not in EN_SOURCES or not text:
            return text
        try:
            chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
            translated = []
            for chunk in chunks:
                t = translator.translate(chunk)
                translated.append(t)
            return " ".join(translated)
        except Exception as e:
            logger.debug(f"Translation failed: {e}")
            return text

    def _translate_item(self, item: NewsItem) -> NewsItem:
        if item.source not in EN_SOURCES:
            return item
        item.title = self._translate_text(item.title, item.source)
        if item.full_text:
            item.full_text = self._translate_text(item.full_text, item.source)
        else:
            item.summary = self._translate_text(item.summary, item.source)
        return item

    async def fetch_news(self, category: str = "all", limit: int = 15) -> list[NewsItem]:
        feeds = []
        if category in ("all", "ukraine"):
            feeds.extend(RSS_FEEDS.get("Україна", []))
        if category in ("all", "world"):
            feeds.extend(RSS_FEEDS.get("Світ", []))

        all_news: list[NewsItem] = []

        for feed_url in feeds:
            try:
                resp = await self.http.get(feed_url)
                resp.raise_for_status()
                source_name = self._extract_source_name(feed_url)
                news = self._parse_rss(resp.text, source_name)
                all_news.extend(news)
            except Exception as e:
                logger.error(f"RSS error {feed_url}: {e}")
                continue

        seen_titles: set[str] = set()
        unique: list[NewsItem] = []
        for n in all_news:
            key = n.title.lower()[:50]
            if key in seen_titles:
                continue
            seen_titles.add(key)
            unique.append(n)

        random.shuffle(unique)
        logger.info(f"Fetched {len(unique)} news items, fetching full text...")

        for item in unique[:limit + 5]:
            item.full_text = await self.fetch_full_text(item.url)
            self._translate_item(item)
            await asyncio.sleep(0.3)

        en_count = sum(1 for i in unique[:limit+5] if i.source in EN_SOURCES)
        logger.info(f"Full text fetched for {sum(1 for i in unique[:limit+5] if i.full_text)} items, translated {en_count} EN sources")
        return unique[:limit]

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'www\.\S+', '', text)
        text = re.sub(r't\.me/\S+', '', text)
        text = re.sub(r'@[\w]+', '', text)
        text = re.sub(r'\b(?:twitter|facebook|instagram|youtube|tiktok|telegram|tiktok)\b.*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(?:підписуйтесь|підписатися|читайте також|дізнавайтесь більше|більше новин|за посиланням|у нашому каналі|на нашому сайті|у Telegram|в Instagram|на YouTube|читайте в нас|ми в Telegram|наш канал)[^.!]*[.!\n]?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(?:subscribe|follow|read more|click here|more news|join us|stay tuned|our channel|on our site)[^.!]*[.!\n]?', '', text, flags=re.IGNORECASE)
        source_names = [
            r'UNIAN', r'УНІАН', r'NV\.ua', r'НВ', r'BBC', r'Бі-бі-сі',
            r'NY Times', r'New York Times', r'Al Jazeera', r'Аль-Джазіра',
            r'DW', r'Deutsche Welle', r'Правда', r'Українська правда',
            r'Укрінформ', r'Інтерфакс', r'РБК-Україна', r'Суспільне',
            r'TSN', r'1plus1', r'СТБ', r'Інтер', r'5 канал',
            r'(?:джерело|джерела|за даними|інформація від|посилання на)[^.!]*',
        ]
        for pat in source_names:
            text = re.sub(pat, '', text, flags=re.IGNORECASE)
        footer_lines = [
            r'Про розділ.*', r'Для преси.*', r'Авторські права.*', r'Зв\'?язатися з нами.*',
            r'Для авторів.*', r'Для рекламодавців.*', r'Для розробників.*', r'Умови.*',
            r'Конфіденційність.*', r'Правила.*', r'Як працює.*', r'Спробувати.*',
            r'©\s*\d{4}\s*\w+.*', r'All rights reserved.*', r'Privacy Policy.*',
            r'Terms of (?:Service|Use|Conditions).*', r'Cookie Policy.*',
            r'(?:Share|Tweet|Pin|Email)\s', r'(?:Сподіватися|Розділити|Надіслати).*',
        ]
        for pat in footer_lines:
            text = re.sub(pat, '', text, flags=re.IGNORECASE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _text_to_paragraphs(self, text: str) -> list[dict]:
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        return [{"tag": "p", "children": [p]} for p in paragraphs]

    def _create_telegraph(self, title: str, content: str) -> str | None:
        try:
            paragraphs = self._text_to_paragraphs(content)
            resp = self.telegraph.create_page(
                title=title[:256],
                author_name="NewsBot",
                content=paragraphs,
            )
            return resp["url"]
        except Exception as e:
            logger.error(f"Telegraph error: {e}")
            return None

    def _format_news_text(self, item: NewsItem) -> str:
        text = f"<b>{item.title}</b>\n\n"

        if item.full_text:
            clean = self._clean_text(item.full_text)
            if len(clean) > 400:
                telegraph_url = self._create_telegraph(item.title, clean)
                if telegraph_url:
                    preview = clean[:350].rsplit(' ', 1)[0] + "..."
                    text += preview + f"\n\nЧитати далі: {telegraph_url}"
                else:
                    text += clean[:3500]
            else:
                text += clean
        elif item.summary:
            text += self._clean_text(item.summary)
        else:
            text += "Деталі за посиланням нижче."

        if config.GROUP_INVITE_LINK:
            text += f"\n\n<a href=\"{config.GROUP_INVITE_LINK}\">Підписатися на групу</a>"

        return text

    async def send_news_batch(self, chat_id: int, news: list[NewsItem]):
        sent = 0
        for item in news:
            if await self.db.is_already_posted(item.id):
                continue

            text = self._format_news_text(item)

            try:
                if item.image_url:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                        img_resp = await client.get(item.image_url)
                        if img_resp.status_code == 200:
                            ct = img_resp.headers.get("content-type", "")
                            if "image" in ct:
                                async with httpx.AsyncClient(timeout=60) as up:
                                    resp = await up.post(
                                        f"{self.api}/sendPhoto",
                                        data={
                                            "chat_id": chat_id,
                                            "caption": text[:1024],
                                            "parse_mode": "HTML",
                                        },
                                        files={"photo": ("news.jpg", img_resp.content, "image/jpeg")},
                                    )
                                sent += 1
                                await self.db.save_post(
                                    meme_id=item.id, source=item.source,
                                    caption=item.title[:100], file_path="", telegram_msg_id=0,
                                )

                                if item.full_text and len(text) > 1024:
                                    remaining = text[1024:]
                                    chunks = [remaining[i:i+4000] for i in range(0, len(remaining), 4000)]
                                    for chunk in chunks:
                                        await self._send_text(chat_id, chunk)
                                        await asyncio.sleep(0.3)

                                await asyncio.sleep(0.5)
                                continue

                await self._send_text(chat_id, text)
                sent += 1
                await self.db.save_post(
                    meme_id=item.id, source=item.source,
                    caption=item.title[:100], file_path="", telegram_msg_id=0,
                )
                await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"Send error: {e}")

        return sent

    async def handle_new_news(self, chat_id: int, category: str = "all"):
        await self._send_text(chat_id, "Завантажую новини...")

        news = await self.fetch_news(category, limit=20)

        if not news:
            await self._send_text(chat_id, "Не вдалося завантажити новини. Спробуй пізніше.")
            return

        sent = await self.send_news_batch(chat_id, news)

        if sent > 0:
            await self._send_text(chat_id, f"Відправлено {sent} новин")
        else:
            await self._send_text(chat_id, "Нових новин поки немає")

    async def handle_message(self, msg: dict):
        text = msg.get("text", "").lower().strip()
        chat_id = msg["chat"]["id"]

        if text in ("/start", "start"):
            await self._send_text(chat_id,
                "<b>Новинний бот</b>\n\n"
                "Команди:\n"
                "/all - Україна + світ\n"
                "/ukraine - тільки Україна\n"
                "/world - тільки світ\n\n"
                "Або напиши що завгодно - отримаєш свіжі новини"
            )
            return

        if text in ("/ukraine", "україна", "ukraine", "укр"):
            await self.handle_new_news(chat_id, "ukraine")
            return

        if text in ("/world", "світ", "world", "світ"):
            await self.handle_new_news(chat_id, "world")
            return

        await self.handle_new_news(chat_id, "all")

    async def run(self):
        await self.db.initialize()
        logger.info("NewsBot started, polling...")

        async def auto_post():
            while True:
                await asyncio.sleep(1800)
                try:
                    chat_id = int(self.chat_id)
                    news = await self.fetch_news("all", limit=10)
                    if news:
                        sent = await self.send_news_batch(chat_id, news)
                        logger.info(f"Auto-posted {sent} news items")
                except Exception as e:
                    logger.error(f"Auto-post error: {e}")

        asyncio.create_task(auto_post())

        while True:
            try:
                resp = await self._api("getUpdates", offset=self._offset, timeout=30)
                if not resp.get("ok"):
                    await asyncio.sleep(5)
                    continue

                for update in resp.get("result", []):
                    self._offset = update["update_id"] + 1
                    msg = update.get("message")
                    if msg:
                        asyncio.create_task(self.handle_message(msg))

            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)


async def main():
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not token or token.startswith("ВСТАВЬ"):
        print("ERROR: Set TELEGRAM_BOT_TOKEN in .env")
        return

    bot = NewsBot()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        await bot.db.initialize()
        if cmd == "--ukraine":
            await bot.handle_new_news(int(chat_id), "ukraine")
        elif cmd == "--world":
            await bot.handle_new_news(int(chat_id), "world")
        else:
            await bot.handle_new_news(int(chat_id), "all")
    else:
        await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
