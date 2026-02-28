from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Track:
    path: Path
    title: str
    artist: str
    album: str
    genre: str
    duration_seconds: float
    cover_path: Path | None = None

    @property
    def duration_text(self) -> str:
        total = int(self.duration_seconds or 0)
        minutes, seconds = divmod(total, 60)
        return f"{minutes:02d}:{seconds:02d}"
