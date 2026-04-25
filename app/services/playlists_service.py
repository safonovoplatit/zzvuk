from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.playlist import Playlist


class PlaylistsService:
    """Manage user playlists persisted as JSON on disk."""

    def __init__(self, storage_path: Path | None = None):
        self._storage_path = storage_path or Path.home() / ".zzvuk" / "playlists_data.json"
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._playlists = self._load()

    def all(self) -> list[Playlist]:
        return [
            Playlist(
                id=playlist.id,
                name=playlist.name,
                created_at=playlist.created_at,
                tracks=list(playlist.tracks),
            )
            for playlist in self._playlists
        ]

    def create(self, raw_name: str) -> Playlist:
        name = self._validate_new_name(raw_name)
        playlist = Playlist(
            id=str(uuid4()),
            name=name,
            created_at=datetime.now(timezone.utc).isoformat(),
            tracks=[],
        )
        self._playlists.append(playlist)
        self._playlists.sort(key=lambda item: item.name.lower())
        self._save()
        return playlist

    def delete(self, playlist_id: str) -> bool:
        before = len(self._playlists)
        self._playlists = [item for item in self._playlists if item.id != playlist_id]
        changed = len(self._playlists) != before
        if changed:
            self._save()
        return changed

    def add_track(self, playlist_id: str, track_id: str) -> str:
        playlist = self._find_required(playlist_id)
        if track_id in playlist.tracks:
            return "duplicate"
        playlist.tracks.append(track_id)
        self._save()
        return "added"

    def remove_track(self, playlist_id: str, track_id: str) -> bool:
        playlist = self._find_required(playlist_id)
        before = len(playlist.tracks)
        playlist.tracks = [item for item in playlist.tracks if item != track_id]
        changed = len(playlist.tracks) != before
        if changed:
            self._save()
        return changed

    def reorder_tracks(self, playlist_id: str, source_index: int, target_index: int) -> bool:
        playlist = self._find_required(playlist_id)
        track_count = len(playlist.tracks)
        if not (0 <= source_index < track_count):
            return False

        bounded_target = max(0, min(target_index, track_count - 1))
        if bounded_target == source_index:
            return False

        track_id = playlist.tracks.pop(source_index)
        playlist.tracks.insert(bounded_target, track_id)
        self._save()
        return True

    def playlist_by_id(self, playlist_id: str) -> Playlist | None:
        for playlist in self._playlists:
            if playlist.id == playlist_id:
                return Playlist(
                    id=playlist.id,
                    name=playlist.name,
                    created_at=playlist.created_at,
                    tracks=list(playlist.tracks),
                )
        return None

    def _find_required(self, playlist_id: str) -> Playlist:
        for playlist in self._playlists:
            if playlist.id == playlist_id:
                return playlist
        raise ValueError("Playlist not found")

    def _validate_new_name(self, raw_name: str) -> str:
        name = " ".join((raw_name or "").split()).strip()
        if not name:
            raise ValueError("Playlist name cannot be empty.")
        if any(item.name.lower() == name.lower() for item in self._playlists):
            raise ValueError("A playlist with this name already exists.")
        return name[:120]

    def _load(self) -> list[Playlist]:
        if not self._storage_path.exists():
            return []
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if not isinstance(payload, dict):
            return []
        raw_playlists = payload.get("playlists")
        if not isinstance(raw_playlists, list):
            return []

        playlists = []
        for entry in raw_playlists:
            playlist = self._deserialize_playlist(entry)
            if playlist is not None:
                playlists.append(playlist)
        playlists.sort(key=lambda item: item.name.lower())
        return playlists

    def _save(self) -> None:
        payload = {"playlists": [playlist.to_dict() for playlist in self._playlists]}
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _deserialize_playlist(entry: object) -> Playlist | None:
        if not isinstance(entry, dict):
            return None

        playlist_id = entry.get("id")
        name = entry.get("name")
        created_at = entry.get("createdAt")
        tracks = entry.get("tracks")

        if not isinstance(playlist_id, str) or not playlist_id.strip():
            return None
        if not isinstance(name, str) or not name.strip():
            return None
        if not isinstance(created_at, str) or not created_at.strip():
            return None
        if not isinstance(tracks, list):
            return None

        clean_tracks = [track_id for track_id in tracks if isinstance(track_id, str) and track_id]
        return Playlist(
            id=playlist_id,
            name=name.strip()[:120],
            created_at=created_at,
            tracks=clean_tracks,
        )
