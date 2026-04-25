from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Playlist:
    id: str
    name: str
    created_at: str
    tracks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "createdAt": self.created_at,
            "tracks": list(self.tracks),
        }
