from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QThread,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPixmap

from app.models.track import Track
from app.services.audio_player import AudioPlayerService, RepeatMode
from app.services.library_scanner import LibraryScanner


class ScanWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, scanner: LibraryScanner, folders: list[Path]) -> None:
        super().__init__()
        self._scanner = scanner
        self._folders = folders

    @Slot()
    def run(self) -> None:
        try:
            tracks = self._scanner.scan_folders(self._folders)
            self.finished.emit(tracks)
        except Exception as exc:
            self.failed.emit(str(exc))


class TrackTableModel(QAbstractTableModel):
    COLUMNS = ["Title", "Artist", "Album", "Duration"]

    def __init__(self) -> None:
        super().__init__()
        self._tracks: list[Track] = []
        self._active_track_path: str | None = None
        self._listen_counts: dict[str, int] = {}
        self._show_listen_counts = False

    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self._tracks = tracks
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None
        track = self._tracks[index.row()]
        is_active = self._active_track_path == str(track.path)

        if role == Qt.ItemDataRole.BackgroundRole and is_active:
            return QBrush(QColor("#1DB95433"))
        if role == Qt.ItemDataRole.ForegroundRole and is_active:
            return QBrush(QColor("#E9FCEB"))
        if role == Qt.ItemDataRole.DisplayRole:
            col = index.column()
            if col == 0:
                if self._show_listen_counts:
                    listens = self._listen_counts.get(str(track.path), 0)
                    return f"{track.title}  ({listens})" if listens else track.title
                return track.title
            if col == 1:
                return track.artist
            if col == 2:
                return track.album
            if col == 3:
                return track.duration_text
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return self._cover_icon(track, 36)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.COLUMNS):
            return self.COLUMNS[section]
        return super().headerData(section, orientation, role)

    def track_at(self, row: int) -> Track | None:
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None

    def set_active_track(self, path: Path | None) -> None:
        self._active_track_path = str(path) if path else None
        if self._tracks:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._tracks) - 1, len(self.COLUMNS) - 1)
            self.dataChanged.emit(
                top_left,
                bottom_right,
                [
                    Qt.ItemDataRole.BackgroundRole,
                    Qt.ItemDataRole.ForegroundRole,
                    Qt.ItemDataRole.DecorationRole,
                ],
            )

    def set_listen_counts(self, counts: dict[str, int], show_counts: bool) -> None:
        self._listen_counts = counts
        self._show_listen_counts = show_counts
        if self._tracks:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._tracks) - 1, len(self.COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])

    @staticmethod
    def _cover_icon(track: Track, size: int) -> QIcon:
        pixmap = QPixmap(str(track.cover_path)) if track.cover_path else QPixmap()
        if pixmap.isNull():
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            grad = QLinearGradient(0, 0, size, size)
            grad.setColorAt(0.0, QColor("#32413A"))
            grad.setColorAt(1.0, QColor("#171C1A"))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(0, 0, size, size, 8, 8)
            painter.setPen(QColor("#9FB5A5"))
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M")
            painter.end()
        else:
            pixmap = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        return QIcon(pixmap)


class TrackGridModel(QAbstractListModel):
    def __init__(self) -> None:
        super().__init__()
        self._tracks: list[Track] = []

    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self._tracks = tracks
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._tracks)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None
        track = self._tracks[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return f"{track.title}\n{track.artist}"

        if role == Qt.ItemDataRole.DecorationRole:
            pixmap = QPixmap(str(track.cover_path)) if track.cover_path else QPixmap()
            if pixmap.isNull():
                pixmap = QPixmap(140, 140)
                pixmap.fill(Qt.GlobalColor.darkGray)
            else:
                pixmap = pixmap.scaled(
                    140,
                    140,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            return QIcon(pixmap)

        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{track.title}\n{track.artist}\n{track.album}\n{track.duration_text}"

        return None

    def track_at(self, row: int) -> Track | None:
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None


class MainViewModel(QObject):
    library_changed = Signal(int)
    now_playing_changed = Signal(str)
    position_text_changed = Signal(str)
    duration_text_changed = Signal(str)
    scan_started = Signal()
    scan_finished = Signal(int)
    scan_failed = Signal(str)
    collection_info_changed = Signal(str)
    favourite_state_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._scanner = LibraryScanner()
        self._player = AudioPlayerService()

        self._folders: list[Path] = []
        self._all_tracks: list[Track] = []
        self._filtered_tracks: list[Track] = []
        self._search_text = ""
        self._collection_mode = "Library"
        self._listen_counts: dict[str, int] = {}
        self._favourites: set[str] = set()

        self.table_model = TrackTableModel()
        self.grid_model = TrackGridModel()

        self._player.track_changed.connect(self._on_track_changed)
        self._player.position_changed.connect(self._on_position_changed)
        self._player.duration_changed.connect(self._on_duration_changed)

        self._last_duration_ms = 0
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None

    @property
    def player(self) -> AudioPlayerService:
        return self._player

    def add_folder(self, folder: Path) -> None:
        resolved = folder.expanduser().resolve()
        if resolved in self._folders:
            return
        self._folders.append(resolved)
        self.rescan_library()

    def rescan_library(self) -> None:
        if self._scan_thread is not None:
            return

        self.scan_started.emit()
        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(self._scanner, list(self._folders))
        self._scan_worker.moveToThread(self._scan_thread)

        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.finished.connect(self._cleanup_scan)
        self._scan_worker.failed.connect(self._cleanup_scan)
        self._scan_thread.start()

    def set_search_text(self, text: str) -> None:
        self._search_text = text.strip().lower()
        self._apply_filter()

    def set_collection_mode(self, mode: str) -> None:
        valid = {"Library", "Daily Mix", "Top Hits", "Favourites"}
        self._collection_mode = mode if mode in valid else "Library"
        self._apply_filter()

    def toggle_current_track_favourite(self) -> None:
        track = self._player.current_track
        if track is None:
            return
        key = str(track.path)
        if key in self._favourites:
            self._favourites.remove(key)
            self.favourite_state_changed.emit(False)
        else:
            self._favourites.add(key)
            self.favourite_state_changed.emit(True)
        if self._collection_mode == "Favourites":
            self._apply_filter()

    def _apply_filter(self) -> None:
        if self._collection_mode == "Daily Mix":
            base_tracks = self._daily_mix_tracks()
        elif self._collection_mode == "Top Hits":
            base_tracks = self._top_hit_tracks()
        elif self._collection_mode == "Favourites":
            base_tracks = [t for t in self._all_tracks if str(t.path) in self._favourites]
        else:
            base_tracks = list(self._all_tracks)

        if not self._search_text:
            self._filtered_tracks = list(base_tracks)
        else:
            needle = self._search_text
            self._filtered_tracks = [
                t
                for t in base_tracks
                if needle in t.title.lower() or needle in t.artist.lower()
            ]

        show_counts = self._collection_mode == "Top Hits"
        self.table_model.set_listen_counts(self._listen_counts, show_counts=show_counts)
        self.table_model.set_tracks(self._filtered_tracks)
        self.grid_model.set_tracks(self._filtered_tracks)
        self.library_changed.emit(len(self._filtered_tracks))
        self.collection_info_changed.emit(self._collection_info_text())

    def play_index(self, row: int) -> None:
        if not (0 <= row < len(self._filtered_tracks)):
            return
        self._player.set_playlist(self._filtered_tracks, start_index=row)

    def play_pause(self) -> None:
        if self._player.current_track is None and self._filtered_tracks:
            self._player.set_playlist(self._filtered_tracks, start_index=0)
            return
        self._player.toggle_play_pause()

    def stop(self) -> None:
        self._player.stop()

    def next(self) -> None:
        self._player.next()

    def previous(self) -> None:
        self._player.previous()

    def set_volume(self, value: int) -> None:
        self._player.set_volume(value)

    def seek(self, position_ms: int) -> None:
        self._player.seek(position_ms)

    def set_shuffle(self, enabled: bool) -> None:
        self._player.set_shuffle(enabled)

    def set_repeat_mode(self, text: str) -> None:
        mapping = {
            RepeatMode.OFF.value: RepeatMode.OFF,
            RepeatMode.TRACK.value: RepeatMode.TRACK,
            RepeatMode.PLAYLIST.value: RepeatMode.PLAYLIST,
        }
        self._player.set_repeat_mode(mapping.get(text, RepeatMode.OFF))

    @staticmethod
    def ms_to_time(ms: int) -> str:
        total_sec = max(0, int(ms // 1000))
        minutes, seconds = divmod(total_sec, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _on_track_changed(self, track: Track) -> None:
        key = str(track.path)
        self._listen_counts[key] = self._listen_counts.get(key, 0) + 1
        self.favourite_state_changed.emit(key in self._favourites)
        self.table_model.set_active_track(track.path)
        self.now_playing_changed.emit(f"Now playing: {track.title} - {track.artist}")
        if self._collection_mode == "Top Hits":
            self._apply_filter()

    def _on_position_changed(self, position_ms: int) -> None:
        self.position_text_changed.emit(self.ms_to_time(position_ms))

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._last_duration_ms = duration_ms
        self.duration_text_changed.emit(self.ms_to_time(duration_ms))

    @Slot(object)
    def _on_scan_finished(self, tracks: list[Track]) -> None:
        self._all_tracks = tracks
        self._apply_filter()
        self.scan_finished.emit(len(self._all_tracks))

    @Slot(str)
    def _on_scan_failed(self, message: str) -> None:
        self.scan_failed.emit(message or "Unknown scan error")

    @Slot()
    def _cleanup_scan(self) -> None:
        if self._scan_thread is None:
            return
        thread = self._scan_thread
        worker = self._scan_worker
        self._scan_thread = None
        self._scan_worker = None
        thread.quit()
        thread.wait()
        thread.deleteLater()
        if worker is not None:
            worker.deleteLater()

    def _daily_mix_tracks(self) -> list[Track]:
        if len(self._all_tracks) <= 10:
            return list(self._all_tracks)
        seed = date.today().toordinal() + len(self._all_tracks)
        rng = random.Random(seed)
        return rng.sample(self._all_tracks, 10)

    def _top_hit_tracks(self) -> list[Track]:
        sorted_tracks = sorted(
            self._all_tracks,
            key=lambda t: (-self._listen_counts.get(str(t.path), 0), t.title.lower()),
        )
        # Show only listened tracks first; if no listens yet, show a small seed list.
        listened = [t for t in sorted_tracks if self._listen_counts.get(str(t.path), 0) > 0]
        if listened:
            return listened
        return sorted_tracks[: min(20, len(sorted_tracks))]

    def _collection_info_text(self) -> str:
        if self._collection_mode == "Daily Mix":
            return "Daily Mix: up to 10 tracks"
        if self._collection_mode == "Top Hits":
            total = sum(self._listen_counts.values())
            return f"Top Hits total listens: {total}"
        if self._collection_mode == "Favourites":
            return f"Favourites: {len(self._favourites)}"
        return "Library"
