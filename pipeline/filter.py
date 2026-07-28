import hashlib
import logging
from pathlib import Path

import imagehash
from PIL import Image

import config

logger = logging.getLogger(__name__)


class MemeFilter:
    def __init__(self):
        self.seen_hashes: set[str] = set()
        self.hash_size = config.DEDUP_HASH_SIZE
        self._load_hashes()

    def _hashes_file(self) -> Path:
        return config.SEEN_HASHES_FILE

    def _load_hashes(self):
        path = self._hashes_file()
        if path.exists():
            self.seen_hashes = set(path.read_text().splitlines())
            logger.info(f"Loaded {len(self.seen_hashes)} seen hashes")

    def _save_hashes(self):
        path = self._hashes_file()
        path.write_text("\n".join(self.seen_hashes))

    def compute_hash(self, image_path: Path) -> str:
        try:
            img = Image.open(image_path)
            phash = imagehash.phash(img, hash_size=self.hash_size)
            return str(phash)
        except Exception:
            fallback = hashlib.md5(image_path.read_bytes()).hexdigest()
            return fallback

    def is_duplicate(self, image_path: Path) -> bool:
        h = self.compute_hash(image_path)
        if h in self.seen_hashes:
            return True
        self.seen_hashes.add(h)
        self._save_hashes()
        return False

    def is_valid_image(self, image_path: Path) -> bool:
        try:
            img = Image.open(image_path)
            w, h = img.size
            if w < 100 or h < 100:
                return False
            if w > 5000 or h > 5000:
                return False
            return True
        except Exception:
            return False
