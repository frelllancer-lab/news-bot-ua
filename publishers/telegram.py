import logging
from pathlib import Path

import httpx

import config

logger = logging.getLogger(__name__)


class TelegramPublisher:
    API = "https://api.telegram.org/bot{token}"

    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

    async def send_photo(self, file_path: Path, caption: str = "") -> dict | None:
        if not self.enabled:
            logger.error("Telegram not configured")
            return None

        url = f"{self.API.format(token=self.token)}/sendPhoto"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        url,
                        data={
                            "chat_id": self.chat_id,
                            "caption": caption[:1024],
                            "parse_mode": "HTML",
                        },
                        files={"photo": ("meme.jpg", f, "image/jpeg")},
                    )
                    response.raise_for_status()
                    result = response.json()
                    msg_id = result["result"]["message_id"]
                    logger.info(f"Photo sent to Telegram: message_id={msg_id}")
                    return {"message_id": msg_id, "ok": True}

        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
            return None

    async def send_video(self, file_path: Path, caption: str = "") -> dict | None:
        if not self.enabled:
            return None

        url = f"{self.API.format(token=self.token)}/sendVideo"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        url,
                        data={
                            "chat_id": self.chat_id,
                            "caption": caption[:1024],
                            "parse_mode": "HTML",
                        },
                        files={"video": ("meme.mp4", f, "video/mp4")},
                    )
                    response.raise_for_status()
                    result = response.json()
                    msg_id = result["result"]["message_id"]
                    logger.info(f"Video sent to Telegram: message_id={msg_id}")
                    return {"message_id": msg_id, "ok": True}

        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram video error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Failed to send video: {e}")
            return None

    async def send_animation(self, file_path: Path, caption: str = "") -> dict | None:
        if not self.enabled:
            return None

        url = f"{self.API.format(token=self.token)}/sendAnimation"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        url,
                        data={
                            "chat_id": self.chat_id,
                            "caption": caption[:1024],
                            "parse_mode": "HTML",
                        },
                        files={"animation": ("meme.gif", f, "image/gif")},
                    )
                    response.raise_for_status()
                    result = response.json()
                    msg_id = result["result"]["message_id"]
                    logger.info(f"GIF sent to Telegram: message_id={msg_id}")
                    return {"message_id": msg_id, "ok": True}

        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram GIF error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Failed to send GIF: {e}")
            return None

    async def send_text(self, text: str) -> dict | None:
        if not self.enabled:
            return None

        url = f"{self.API.format(token=self.token)}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                })
                response.raise_for_status()
                return {"ok": True}
        except Exception as e:
            logger.error(f"Failed to send text: {e}")
            return None
