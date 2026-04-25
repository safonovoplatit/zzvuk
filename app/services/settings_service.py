from __future__ import annotations

import json
from pathlib import Path


class SettingsService:
    """Persist lightweight user settings on disk."""

    def __init__(self, storage_path: Path | None = None):
        self._storage_path = storage_path or Path.home() / ".zzvuk" / "settings.json"
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings = self._load()

    def library_folders(self) -> list[Path]:
        raw_folders = self._settings.get("libraryFolders", [])
        folders = []
        for raw_path in raw_folders:
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            try:
                folders.append(Path(raw_path).expanduser().resolve())
            except Exception:
                continue
        return folders

    def set_library_folders(self, folders: list[Path]) -> None:
        self._settings["libraryFolders"] = [str(folder) for folder in folders]
        self._save()

    def _load(self) -> dict:
        if not self._storage_path.exists():
            return {}
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self) -> None:
        self._storage_path.write_text(
            json.dumps(self._settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
