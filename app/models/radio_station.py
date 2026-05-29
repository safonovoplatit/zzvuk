from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from urllib.parse import urlparse

from app.models.track import Track


@dataclass
class RadioStation:
    name: str
    url: str
    stream_format: str = "MP3"
    source: str = "Custom"

    @property
    def id(self) -> str:
        return self.url

    def to_track(self) -> Track:
        digest = hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]
        return Track(
            path=Path(f"radio-{digest}"),
            title=self.name,
            artist="Internet Radio",
            album=self.source,
            genre=self.stream_format.upper(),
            duration_seconds=0,
            stream_url=self.url,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "streamFormat": self.stream_format,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: object, default_source: str = "Custom") -> "RadioStation | None":
        if not isinstance(payload, dict):
            return None
        name = payload.get("name")
        url = payload.get("url")
        stream_format = payload.get("streamFormat") or payload.get("format") or "MP3"
        source = payload.get("source") or default_source
        if not isinstance(name, str) or not isinstance(url, str):
            return None
        station = cls(name=name.strip(), url=url.strip(), stream_format=str(stream_format), source=str(source))
        return station if station.is_valid() else None

    def is_valid(self) -> bool:
        parsed = urlparse(self.url)
        return bool(self.name and parsed.scheme in {"http", "https"} and parsed.netloc)
