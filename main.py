import asyncio
import io
import logging
import random
import sys
from pathlib import Path

import httpx

import config
from sources import MemeAggregator
from pipeline.filter import MemeFilter
from pipeline.downloader import MemeDownloader
from storage.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("meme-bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

CAPTIONS_RU = [
    "когда мем бьёт в самое сердце",
    "золото",
    "слишком реально",
    "я почувствовал это",
    "брех",
    "контент высшего сорта",
    "жиза",
    "ну и где тут логика",
    "легенда",
    "вот это настроение",
    "когда сдал экзамен на 4",
    "нашёл мем отправил",
    "когда в пятницу",
    "жизнь beautiful",
    "мемы на каждый день",
    "чистый компот",
]

HELP_TEXT = """<b>Мем-бот команды:</b>

/new -新鲜 мемы (10-15 шт)
/help - эта справка

Просто напиши &quot;новые&quot; или &quot;ново&quot; - получишь свежую пачку мемов"""


class MemeBot:
    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.aggregator = MemeAggregator()
        self.filter = MemeFilter()
        self.downloader = MemeDownloader()
        self.db = Database()
        self.api = f"https://api.telegram.org/bot{self.token}"
        self._offset = 0

    async def _api(self, method: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.api}/{method}", json=kwargs)
            return resp.json()

    async def _send_text(self, chat_id: int, text: str):
        await self._api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_media_group(self, chat_id: int, file_paths: list[Path], captions: list[str]):
        if not file_paths:
            return

        batch_size = 10
        for i in range(0, len(file_paths), batch_size):
            batch = file_paths[i:i + batch_size]
            batch_captions = captions[i:i + batch_size]

            media = []
            files = {}

            for idx, (fp, cap) in enumerate(zip(batch, batch_captions)):
                key = f"photo{idx}"
                media.append({
                    "type": "photo",
                    "media": f"attach://{key}",
                    "caption": cap[:1024],
                    "parse_mode": "HTML",
                })
                files[key] = (fp.name, open(fp, "rb"), "image/jpeg")

            payload = {
                "chat_id": chat_id,
                "media": str(media).replace("'", '"'),
            }

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.api}/sendMediaGroup",
                    data={"chat_id": chat_id, "media": str(media).replace("'", '"')},
                    files=files,
                )
                result = resp.json()

            for fp in batch:
                try:
                    fp.unlink(missing_ok=True)
                except Exception:
                    pass

            if i + batch_size < len(file_paths):
                await asyncio.sleep(1)

    async def send_photos_one_by_one(self, chat_id: int, file_paths: list[Path], captions: list[str]):
        for fp, cap in zip(file_paths, captions):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    with open(fp, "rb") as f:
                        resp = await client.post(
                            f"{self.api}/sendPhoto",
                            data={
                                "chat_id": chat_id,
                                "caption": cap[:1024],
                                "parse_mode": "HTML",
                            },
                            files={"photo": (fp.name, f, "image/jpeg")},
                        )
                fp.unlink(missing_ok=True)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Error sending photo: {e}")

    async def handle_new_memes(self, chat_id: int):
        await self._send_text(chat_id, "Ищу свежие мемы...")

        memes = await self.aggregator.fetch_memes(limit=25)

        if not memes:
            await self._send_text(chat_id, "Не удалось найти мемы. Попробуй позже.")
            return

        downloaded: list[Path] = []
        captions: list[str] = []

        for meme in memes:
            if await self.db.is_already_posted(meme.id):
                continue

            if not meme.image_url:
                continue

            filepath = await self.downloader.download(meme.image_url, "image")
            if not filepath:
                continue

            if not self.filter.is_valid_image(filepath):
                self.downloader.cleanup(filepath)
                continue

            if self.filter.is_duplicate(filepath):
                self.downloader.cleanup(filepath)
                continue

            caption = random.choice(CAPTIONS_RU)
            downloaded.append(filepath)
            captions.append(caption)

            if len(downloaded) >= 15:
                break

        if not downloaded:
            await self._send_text(chat_id, "Не нашёл новых мемов. Попробуй ещё раз.")
            return

        await self._send_text(chat_id, f"Вот тебе {len(downloaded)} свежих мемов:")

        try:
            await self.send_media_group(chat_id, downloaded, captions)
        except Exception:
            await self.send_photos_one_by_one(chat_id, downloaded, captions)

        for meme in memes[:len(downloaded)]:
            await self.db.save_post(
                meme_id=meme.id,
                source=meme.source,
                caption="batch",
                file_path="",
                telegram_msg_id=0,
            )

        logger.info(f"Sent {len(downloaded)} memes to {chat_id}")

    async def handle_message(self, msg: dict):
        text = msg.get("text", "").lower().strip()
        chat_id = msg["chat"]["id"]

        if text in ("/start", "start"):
            await self._send_text(chat_id, HELP_TEXT)
            return

        if text in ("/help", "help", "помощь"):
            await self._send_text(chat_id, HELP_TEXT)
            return

        if text in ("/new", "new", "новые", "ново", "мемы", "memes", "ещё", "еще", "refresh", "обновить"):
            await self.handle_new_memes(chat_id)
            return

        await self.handle_new_memes(chat_id)

    async def run(self):
        await self.db.initialize()
        logger.info("MemeBot started, polling...")

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
    if not chat_id or chat_id.startswith("ВСТАВЬ"):
        print("ERROR: Set TELEGRAM_CHAT_ID in .env")
        return

    bot = MemeBot()

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        await bot.db.initialize()
        await bot.handle_new_memes(int(chat_id))
    else:
        await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
