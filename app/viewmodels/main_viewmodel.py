from __future__ import annotations

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
from PySide6.QtGui import QIcon, QPixmap

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
    COLUMNS = ["Title", "Artist", "Album", "Genre", "Duration", "Path"]

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

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None
        track = self._tracks[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            col = index.column()
            if col == 0:
                return track.title
            if col == 1:
                return track.artist
            if col == 2:
                return track.album
            if col == 3:
                return track.genre
            if col == 4:
                return track.duration_text
            if col == 5:
                return str(track.path)
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

    def __init__(self) -> None:
        super().__init__()
        self._scanner = LibraryScanner()
        self._player = AudioPlayerService()

        self._folders: list[Path] = []
        self._all_tracks: list[Track] = []
        self._filtered_tracks: list[Track] = []
        self._search_text = ""

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

    def _apply_filter(self) -> None:
        if not self._search_text:
            self._filtered_tracks = list(self._all_tracks)
        else:
            needle = self._search_text
            self._filtered_tracks = [
                t
                for t in self._all_tracks
                if needle in t.title.lower() or needle in t.artist.lower()
            ]

        self.table_model.set_tracks(self._filtered_tracks)
        self.grid_model.set_tracks(self._filtered_tracks)
        self.library_changed.emit(len(self._filtered_tracks))

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
        self.now_playing_changed.emit(f"Now playing: {track.title} - {track.artist}")

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
