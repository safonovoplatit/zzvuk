from __future__ import annotations

import configparser
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from app.models.radio_station import RadioStation


class RadioService:
    SUPPORTED_STREAM_FORMATS = {"MP3", "AAC", "OGG"}
    DEFAULT_PRESETS = [
        RadioStation("BBC Radio 1", "https://stream.live.vc.bbcmedia.co.uk/bbc_radio_one", "AAC", "Preset"),
        RadioStation("BBC World Service", "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service", "AAC", "Preset"),
        RadioStation("NPR Program Stream", "https://npr-ice.streamguys1.com/live.mp3", "MP3", "Preset"),
        RadioStation("KEXP 90.3 FM", "https://kexp-mp3-128.streamguys1.com/kexp128.mp3", "MP3", "Preset"),
        RadioStation("SomaFM Groove Salad", "https://ice1.somafm.com/groovesalad-128-mp3", "MP3", "Preset"),
        RadioStation("SomaFM Drone Zone", "https://ice1.somafm.com/dronezone-128-mp3", "MP3", "Preset"),
    ]

    def __init__(self, storage_path: Path | None = None):
        self._storage_path = storage_path or Path.home() / ".zzvuk" / "radio_stations.json"
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._custom_stations: list[RadioStation] = []
        self._preset_stations: list[RadioStation] = list(self.DEFAULT_PRESETS)
        self._load()

    def all(self) -> list[RadioStation]:
        stations_by_url: dict[str, RadioStation] = {}
        for station in [*self._preset_stations, *self._custom_stations]:
            if station.is_valid() and station.stream_format.upper() in self.SUPPORTED_STREAM_FORMATS:
                stations_by_url[station.url] = station
        return sorted(stations_by_url.values(), key=lambda station: (station.source, station.name.lower()))

    def add_station(self, name: str, url: str, stream_format: str = "MP3") -> bool:
        station = RadioStation(
            name=name.strip(),
            url=url.strip(),
            stream_format=stream_format.strip().upper() or "MP3",
            source="Custom",
        )
        if not station.is_valid() or station.stream_format not in self.SUPPORTED_STREAM_FORMATS:
            return False
        if any(existing.url == station.url for existing in self._custom_stations):
            return False
        self._custom_stations.append(station)
        self._save()
        return True

    def import_file(self, path: Path) -> int:
        suffix = path.suffix.lower()
        if suffix == ".m3u" or suffix == ".m3u8":
            stations = self._parse_m3u(path)
        elif suffix == ".pls":
            stations = self._parse_pls(path)
        else:
            return 0

        added_count = 0
        known_urls = {station.url for station in self._custom_stations}
        for station in stations:
            if station.url in known_urls:
                continue
            self._custom_stations.append(station)
            known_urls.add(station.url)
            added_count += 1
        if added_count:
            self._save()
        return added_count

    def update_presets_from_url(self, url: str) -> int:
        with urlopen(url, timeout=12) as response:
            payload = response.read().decode("utf-8", errors="replace")

        if url.lower().split("?")[0].endswith((".m3u", ".m3u8")):
            stations = self._parse_m3u_text(payload)
        elif url.lower().split("?")[0].endswith(".pls"):
            stations = self._parse_pls_text(payload)
        else:
            raw = json.loads(payload)
            entries = raw.get("stations", raw) if isinstance(raw, dict) else raw
            stations = [
                station
                for station in (RadioStation.from_dict(entry, default_source="Preset") for entry in entries)
                if station is not None
            ]

        stations = [
            RadioStation(station.name, station.url, station.stream_format.upper(), "Preset")
            for station in stations
            if station.stream_format.upper() in self.SUPPORTED_STREAM_FORMATS
        ]
        if not stations:
            return 0

        self._preset_stations = stations
        self._save()
        return len(stations)

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return

        custom = payload.get("customStations", [])
        presets = payload.get("presetStations", [])
        self._custom_stations = [
            station
            for station in (RadioStation.from_dict(entry) for entry in custom)
            if station is not None
        ]
        loaded_presets = [
            station
            for station in (RadioStation.from_dict(entry, default_source="Preset") for entry in presets)
            if station is not None
        ]
        if loaded_presets:
            self._preset_stations = loaded_presets

    def _save(self) -> None:
        payload = {
            "presetStations": [station.to_dict() for station in self._preset_stations],
            "customStations": [station.to_dict() for station in self._custom_stations],
        }
        self._storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def _parse_m3u(cls, path: Path) -> list[RadioStation]:
        return cls._parse_m3u_text(path.read_text(encoding="utf-8", errors="replace"))

    @classmethod
    def _parse_m3u_text(cls, text: str) -> list[RadioStation]:
        stations: list[RadioStation] = []
        pending_name: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                pending_name = line.rsplit(",", 1)[-1].strip() or None
                continue
            if line.startswith("#"):
                continue
            fmt = cls._guess_format(line)
            station = RadioStation(pending_name or cls._name_from_url(line), line, fmt, "Custom")
            if station.is_valid() and fmt in cls.SUPPORTED_STREAM_FORMATS:
                stations.append(station)
            pending_name = None
        return stations

    @classmethod
    def _parse_pls(cls, path: Path) -> list[RadioStation]:
        return cls._parse_pls_text(path.read_text(encoding="utf-8", errors="replace"))

    @classmethod
    def _parse_pls_text(cls, text: str) -> list[RadioStation]:
        parser = configparser.ConfigParser()
        parser.read_string(text)
        if not parser.has_section("playlist"):
            return []

        section = parser["playlist"]
        stations: list[RadioStation] = []
        index = 1
        while f"file{index}" in section:
            url = section.get(f"file{index}", "").strip()
            name = section.get(f"title{index}", "").strip() or url
            fmt = cls._guess_format(url)
            station = RadioStation(name, url, fmt, "Custom")
            if station.is_valid() and fmt in cls.SUPPORTED_STREAM_FORMATS:
                stations.append(station)
            index += 1
        return stations

    @staticmethod
    def _guess_format(url: str) -> str:
        lowered = url.lower().split("?")[0]
        if lowered.endswith((".aac", ".m4a")):
            return "AAC"
        if lowered.endswith((".ogg", ".oga", ".opus")):
            return "OGG"
        return "MP3"

    @staticmethod
    def _name_from_url(url: str) -> str:
        parsed = urlparse(url)
        path_name = Path(parsed.path).stem
        return path_name or parsed.netloc or url
