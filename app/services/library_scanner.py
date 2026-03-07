from __future__ import annotations

import hashlib
import os
import wave
from pathlib import Path
from typing import Iterable

from mutagen.aac import AAC
from mutagen.flac import FLAC
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from app.models.track import Track

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".m4a"}


class LibraryScanner:
    def __init__(self, cover_cache_dir = None):
        base = Path.home() / ".zzvuk" / "covers"
        self._cover_cache_dir = cover_cache_dir or base
        self._cover_cache_dir.mkdir(parents=True, exist_ok=True)

    def scan_folders(self, folders):
        tracks = []
        seen = set()

        for folder in folders:
            folder = folder.expanduser().resolve()
            if not folder.exists() or not folder.is_dir():
                continue

            for root, _, files in os.walk(folder):
                root_path = Path(root)
                for filename in files:
                    path = root_path / filename
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

    def _parse_track(self, path):
        suffix = path.suffix.lower()
        title = path.stem
        artist = "Unknown Artist"
        album = "Unknown Album"
        genre = "Unknown"
        duration = 0.0

        try:
            if suffix == ".mp3":
                mp3 = MP3(str(path))
                duration = float(getattr(mp3.info, "length", 0.0) or 0.0)
                if mp3.tags:
                    title = self._id3_value(mp3, "TIT2", title)
                    artist = self._id3_value(mp3, "TPE1", artist)
                    album = self._id3_value(mp3, "TALB", album)
                    genre = self._id3_value(mp3, "TCON", genre)
            elif suffix == ".flac":
                flac = FLAC(str(path))
                duration = float(getattr(flac.info, "length", 0.0) or 0.0)
                title = self._first_text(flac.get("title"), title)
                artist = self._first_text(flac.get("artist"), artist)
                album = self._first_text(flac.get("album"), album)
                genre = self._first_text(flac.get("genre"), genre)
            elif suffix in {".m4a", ".aac"}:
                try:
                    mp4 = MP4(str(path))
                    duration = float(getattr(mp4.info, "length", 0.0) or 0.0)
                    if mp4.tags:
                        title = self._first_text(mp4.tags.get("\xa9nam"), title)
                        artist = self._first_text(mp4.tags.get("\xa9ART"), artist)
                        album = self._first_text(mp4.tags.get("\xa9alb"), album)
                        genre = self._first_text(mp4.tags.get("\xa9gen"), genre)
                except Exception:
                    # Some AAC files are ADTS streams without MP4 container metadata.
                    aac = AAC(str(path))
                    duration = float(getattr(aac.info, "length", 0.0) or 0.0)
            elif suffix == ".wav":
                with wave.open(str(path), "rb") as wav_file:
                    frames = wav_file.getnframes()
                    framerate = wav_file.getframerate()
                    if framerate > 0:
                        duration = float(frames) / float(framerate)
        except Exception:
            return None

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
    def _first_text(values, fallback):
        if not values:
            return fallback
        first = values[0]
        return str(first).strip() if first else fallback

    @staticmethod
    def _id3_value(audio, frame_name, fallback):
        if not audio.tags:
            return fallback
        frames = audio.tags.getall(frame_name)
        if not frames:
            return fallback
        text = getattr(frames[0], "text", None)
        if not text:
            return fallback
        return str(text[0]).strip() if text[0] else fallback

    def _extract_embedded_cover(self, path):
        suffix = path.suffix.lower()
        data = None
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
    def _find_folder_cover(folder):
        for name in ("cover.jpg", "cover.jpeg", "cover.png", "folder.jpg"):
            candidate = folder / name
            if candidate.exists() and candidate.is_file():
                return candidate
        return None
