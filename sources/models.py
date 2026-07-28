from dataclasses import dataclass


@dataclass
class Meme:
    id: str
    source: str
    image_url: str | None
    video_url: str | None
    gif_url: str | None
    caption: str
    score: int
    url: str
