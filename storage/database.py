import logging
from datetime import datetime, timezone

import aiosqlite

import config

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.db_path = config.DATABASE_PATH

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS posted_memes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meme_id TEXT UNIQUE NOT NULL,
                    source TEXT,
                    caption TEXT,
                    file_path TEXT,
                    telegram_msg_id INTEGER,
                    posted_at TEXT NOT NULL
                )
            """)
            await db.commit()
        logger.info("Database initialized")

    async def save_post(self, meme_id: str, source: str, caption: str,
                        file_path: str, telegram_msg_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR IGNORE INTO posted_memes
                   (meme_id, source, caption, file_path, telegram_msg_id, posted_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (meme_id, source, caption, file_path, telegram_msg_id,
                 datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def is_already_posted(self, meme_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM posted_memes WHERE meme_id = ?", (meme_id,)
            )
            row = await cursor.fetchone()
            return row is not None

    async def get_posts_today(self) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM posted_memes WHERE posted_at LIKE ?",
                (f"{today}%",),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_total_posts(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM posted_memes")
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_recent(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM posted_memes ORDER BY posted_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
