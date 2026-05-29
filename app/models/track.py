from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Track:
    path: Path
    title: str
    artist: str
    album: str
    genre: str
    duration_seconds: float
    cover_path: Path | None = None
    stream_url: str | None = None

    @property
    def id(self):
        if self.stream_url:
            return self.stream_url
        return str(self.path)

    @property
    def is_stream(self):
        return bool(self.stream_url)

    @property
    def duration_text(self):
        if self.stream_url:
            return "LIVE"
        total = int(self.duration_seconds or 0)
        minutes, seconds = divmod(total, 60)
        return f"{minutes:02d}:{seconds:02d}"
