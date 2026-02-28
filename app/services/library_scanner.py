from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from mutagen import File
from mutagen.flac import FLAC
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from app.models.track import Track

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".m4a"}


class LibraryScanner:
    def __init__(self, cover_cache_dir: Path | None = None) -> None:
        base = Path.home() / ".zzvuk" / "covers"
        self._cover_cache_dir = cover_cache_dir or base
        self._cover_cache_dir.mkdir(parents=True, exist_ok=True)

    def scan_folders(self, folders: Iterable[Path]) -> list[Track]:
        tracks: list[Track] = []
        seen: set[Path] = set()

        for folder in folders:
            folder = folder.expanduser().resolve()
            if not folder.exists() or not folder.is_dir():
                continue

            for path in folder.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                track = self._parse_track(resolved)
                if track:
                    tracks.append(track)

        tracks.sort(key=lambda t: (t.artist.lower(), t.album.lower(), t.title.lower()))
        return tracks

    def _parse_track(self, path: Path) -> Track | None:
        audio_easy = File(str(path), easy=True)
        if audio_easy is None:
            return None

        title = self._first_tag(audio_easy, "title", fallback=path.stem)
        artist = self._first_tag(audio_easy, "artist", fallback="Unknown Artist")
        album = self._first_tag(audio_easy, "album", fallback="Unknown Album")
        genre = self._first_tag(audio_easy, "genre", fallback="Unknown")
        duration = float(getattr(getattr(audio_easy, "info", None), "length", 0.0) or 0.0)

        cover_path = self._extract_embedded_cover(path)
        if not cover_path:
            cover_path = self._find_folder_cover(path.parent)

        return Track(
            path=path,
            title=title,
            artist=artist,
            album=album,
            genre=genre,
            duration_seconds=duration,
            cover_path=cover_path,
        )

    @staticmethod
    def _first_tag(audio, key: str, fallback: str) -> str:
        values = audio.get(key)
        if not values:
            return fallback
        first = values[0]
        return str(first).strip() if first else fallback

    def _extract_embedded_cover(self, path: Path) -> Path | None:
        suffix = path.suffix.lower()
        data: bytes | None = None
        ext = ".jpg"

        if suffix == ".mp3":
            try:
                mp3 = MP3(str(path))
                if mp3.tags:
                    for key in mp3.tags.keys():
                        if key.startswith("APIC"):
                            frame = mp3.tags[key]
                            data = frame.data
                            mime = (frame.mime or "").lower()
                            ext = ".png" if "png" in mime else ".jpg"
                            break
            except ID3NoHeaderError:
                data = None
            except Exception:
                data = None
        elif suffix == ".flac":
            try:
                flac = FLAC(str(path))
                if flac.pictures:
                    pic = flac.pictures[0]
                    data = pic.data
                    mime = (pic.mime or "").lower()
                    ext = ".png" if "png" in mime else ".jpg"
            except Exception:
                data = None
        elif suffix in {".aac", ".m4a"}:
            try:
                mp4 = MP4(str(path))
                covers = mp4.tags.get("covr") if mp4.tags else None
                if covers:
                    data = bytes(covers[0])
                    ext = ".jpg"
            except Exception:
                data = None

        if not data:
            return None

        digest = hashlib.sha1(str(path).encode("utf-8") + data[:256]).hexdigest()
        out = self._cover_cache_dir / f"{digest}{ext}"
        if not out.exists():
            out.write_bytes(data)
        return out

    @staticmethod
    def _find_folder_cover(folder: Path) -> Path | None:
        for name in ("cover.jpg", "cover.jpeg", "cover.png", "folder.jpg"):
            candidate = folder / name
            if candidate.exists() and candidate.is_file():
                return candidate
        return None
