import logging
import uuid
from pathlib import Path

import httpx

import config

logger = logging.getLogger(__name__)


class MemeDownloader:
    def __init__(self):
        self.download_dir = config.ASSETS_DIR
        self.download_dir.mkdir(exist_ok=True)

    async def download(self, url: str, media_type: str = "image") -> Path | None:
        if not url:
            return None

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")

                if media_type == "video" or "video" in content_type:
                    ext = ".mp4"
                elif media_type == "gif" or "gif" in content_type or url.endswith(".gif"):
                    ext = ".gif"
                elif "png" in content_type or url.endswith(".png"):
                    ext = ".png"
                elif "webp" in content_type or url.endswith(".webp"):
                    ext = ".webp"
                else:
                    ext = ".jpg"

                prefix = {"image": "img", "video": "vid", "gif": "gif"}.get(media_type, "meme")
                filename = f"{prefix}_{uuid.uuid4().hex[:10]}{ext}"
                filepath = self.download_dir / filename
                filepath.write_bytes(response.content)

                size_kb = len(response.content) / 1024
                logger.info(f"Downloaded: {filename} ({size_kb:.0f} KB)")
                return filepath

        except Exception as e:
            logger.error(f"Download failed from {url}: {e}")
            return None

    def cleanup(self, file_path: Path):
        try:
            if file_path and file_path.exists():
                file_path.unlink()
        except Exception:
            pass
