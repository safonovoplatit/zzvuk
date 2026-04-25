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

    @property
    def id(self):
        return str(self.path)

    @property
    def duration_text(self):
        total = int(self.duration_seconds or 0)
        minutes, seconds = divmod(total, 60)
        return f"{minutes:02d}:{seconds:02d}"
