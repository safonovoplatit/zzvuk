from __future__ import annotations

import hashlib
from pathlib import Path

try:
    from mutagen import File as MutagenFile
except ModuleNotFoundError:
    MutagenFile = None

from app.models.track import Track


class LibraryScanner:
    SUPPORTED_EXTENSIONS = {
        ".aac",
        ".aif",
        ".aiff",
        ".alac",
        ".flac",
        ".m4a",
        ".mp3",
        ".mp4",
        ".oga",
        ".ogg",
        ".opus",
        ".wav",
        ".wma",
    }
    COVER_FILE_NAMES = ("cover.jpg", "cover.png", "folder.jpg", "folder.png")
    TAG_ALIASES = {
        "album": ("album", "talb", "\xa9alb"),
        "album_artist": ("albumartist", "album_artist", "tpe2", "aART"),
        "artist": ("artist", "tpe1", "\xa9art"),
        "genre": ("genre", "tcon", "\xa9gen"),
        "title": ("title", "tit2", "\xa9nam"),
    }

    def __init__(self, cover_cache_path: Path | None = None):
        self._cover_cache_path = cover_cache_path or Path.home() / ".zzvuk" / "covers"
        self._cover_cache_path.mkdir(parents=True, exist_ok=True)

    def scan_folders(self, folders: list[Path]) -> list[Track]:
        tracks: list[Track] = []
        seen_paths: set[Path] = set()

        for folder in folders:
            if not folder.exists() or not folder.is_dir():
                continue
            for path in folder.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                    continue
                resolved = path.expanduser().resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                tracks.append(self._track_from_path(resolved))

        tracks.sort(key=lambda track: (track.artist.lower(), track.album.lower(), track.title.lower()))
        return tracks

    def _track_from_path(self, path: Path) -> Track:
        audio = self._read_audio(path)
        title = path.stem
        artist = "Unknown Artist"
        album = "Unknown Album"
        genre = "Unknown Genre"
        duration_seconds = 0.0
        cover_path = self._folder_cover(path)

        if audio is not None:
            duration_seconds = float(getattr(getattr(audio, "info", None), "length", 0.0) or 0.0)
            title = self._first_tag(audio, "title") or title
            artist = self._first_tag(audio, "artist", "album_artist") or artist
            album = self._first_tag(audio, "album") or album
            genre = self._first_tag(audio, "genre") or genre
            embedded_cover = self._extract_cover(audio, path)
            if embedded_cover is not None:
                cover_path = embedded_cover

        return Track(
            path=path,
            title=title,
            artist=artist,
            album=album,
            genre=genre,
            duration_seconds=duration_seconds,
            cover_path=cover_path,
        )

    @staticmethod
    def _read_audio(path: Path):
        if MutagenFile is None:
            return None
        try:
            return MutagenFile(path)
        except Exception:
            return None

    @staticmethod
    def _first_tag(audio, *names: str) -> str | None:
        tags = getattr(audio, "tags", None)
        if not tags:
            return None

        lowered = {str(key).lower(): value for key, value in tags.items()}
        lookup_keys: list[str] = []
        for name in names:
            lookup_keys.extend(LibraryScanner.TAG_ALIASES.get(name, (name,)))
        normalized_lookup_keys = {key.lower() for key in lookup_keys}

        for key in lookup_keys:
            value = lowered.get(key.lower())
            text = LibraryScanner._tag_to_text(value)
            if text:
                return text

        for key, value in lowered.items():
            normalized = key.split(":")[-1]
            if normalized in normalized_lookup_keys:
                text = LibraryScanner._tag_to_text(value)
                if text:
                    return text
        return None

    @staticmethod
    def _tag_to_text(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            if not value:
                return None
            value = value[0]
        if hasattr(value, "text"):
            text_value = value.text
            if isinstance(text_value, (list, tuple)):
                value = text_value[0] if text_value else None
            else:
                value = text_value
        text = str(value).strip() if value is not None else ""
        return text or None

    def _folder_cover(self, path: Path) -> Path | None:
        for name in self.COVER_FILE_NAMES:
            cover = path.parent / name
            if cover.exists() and cover.is_file():
                return cover
        return None

    def _extract_cover(self, audio, path: Path) -> Path | None:
        image_data, extension = self._cover_bytes(audio)
        if not image_data:
            return None

        digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
        cover_path = self._cover_cache_path / f"{digest}.{extension}"
        if not cover_path.exists():
            try:
                cover_path.write_bytes(image_data)
            except OSError:
                return None
        return cover_path

    @staticmethod
    def _cover_bytes(audio) -> tuple[bytes | None, str]:
        tags = getattr(audio, "tags", None)
        if not tags:
            return None, "jpg"

        for value in tags.values():
            if hasattr(value, "data") and hasattr(value, "mime"):
                mime = str(value.mime).lower()
                return value.data, "png" if "png" in mime else "jpg"

            if isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, bytes):
                        return item, "jpg"
                    if hasattr(item, "data") and hasattr(item, "mime"):
                        mime = str(item.mime).lower()
                        return item.data, "png" if "png" in mime else "jpg"

            if isinstance(value, bytes):
                return value, "jpg"

        pictures = getattr(audio, "pictures", None)
        if pictures:
            picture = pictures[0]
            mime = str(getattr(picture, "mime", "")).lower()
            return getattr(picture, "data", None), "png" if "png" in mime else "jpg"

        return None, "jpg"
