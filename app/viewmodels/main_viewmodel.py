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

from app.models.playlist import Playlist
from app.models.track import Track
from app.services.audio_player import AudioPlayerService, RepeatMode
from app.services.library_scanner import LibraryScanner
from app.services.playlists_service import PlaylistsService
from app.services.settings_service import SettingsService


class ScanWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, scanner, folders):
        super().__init__()
        self._scanner = scanner
        self._folders = folders

    @Slot()
    def run(self):
        try:
            tracks = self._scanner.scan_folders(self._folders)
            self.finished.emit(tracks)
        except Exception as exc:
            self.failed.emit(str(exc))


class TrackTableModel(QAbstractTableModel):
    COLUMNS = ["Title", "Artist", "Album", "Genre", "Duration"]
    MIME_TYPE = "application/x-zzvuk-track-id"

    def __init__(self):
        super().__init__()
        self._tracks = []
        self._active_track_path = None
        self._listen_counts = {}
        self._show_listen_counts = False
        self._reorder_enabled = False
        self._reorder_callback = None

    def set_tracks(self, tracks):
        self.beginResetModel()
        self._tracks = tracks
        self.endResetModel()

    def rowCount(self, parent = QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._tracks)

    def columnCount(self, parent = QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def data(self, index, role = Qt.ItemDataRole.DisplayRole):
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
                prefix = "≡  " if self._reorder_enabled else ""
                if self._show_listen_counts:
                    listens = self._listen_counts.get(str(track.path), 0)
                    title = f"{track.title}  ({listens})" if listens else track.title
                    return f"{prefix}{title}"
                return f"{prefix}{track.title}"
            if col == 1:
                return track.artist
            if col == 2:
                return track.album
            if col == 3:
                return track.genre
            if col == 4:
                return track.duration_text
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return self._cover_icon(track, 36)
        return None

    def headerData(self, section, orientation, role = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.COLUMNS):
            return self.COLUMNS[section]
        return super().headerData(section, orientation, role)

    def track_at(self, row):
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None

    def set_active_track(self, path):
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

    def set_listen_counts(self, counts, show_counts: bool):
        self._listen_counts = counts
        self._show_listen_counts = show_counts
        if self._tracks:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._tracks) - 1, len(self.COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])

    def set_reorder_enabled(self, enabled: bool, reorder_callback = None):
        self._reorder_enabled = enabled
        self._reorder_callback = reorder_callback if enabled else None
        if self._tracks:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._tracks) - 1, len(self.COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])

    def flags(self, index):
        base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid():
            if self._reorder_enabled:
                return base_flags | Qt.ItemFlag.ItemIsDropEnabled
            return base_flags

        flags = base_flags | Qt.ItemFlag.ItemIsDragEnabled
        if self._reorder_enabled:
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        return flags

    def mimeTypes(self):
        return [self.MIME_TYPE]

    def mimeData(self, indexes):
        mime_data = super().mimeData(indexes)
        rows = sorted({index.row() for index in indexes if index.isValid()})
        if not rows:
            return mime_data
        track_ids = [self._tracks[row].id for row in rows if 0 <= row < len(self._tracks)]
        mime_data.setData(self.MIME_TYPE, "\n".join(track_ids).encode("utf-8"))
        return mime_data

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def dropMimeData(self, data, action, row, column, parent):
        if not self._reorder_enabled or action == Qt.DropAction.IgnoreAction:
            return False
        if not data.hasFormat(self.MIME_TYPE):
            return False

        raw_ids = bytes(data.data(self.MIME_TYPE)).decode("utf-8")
        track_ids = [value for value in raw_ids.splitlines() if value]
        if len(track_ids) != 1:
            return False

        source_row = next(
            (idx for idx, track in enumerate(self._tracks) if track.id == track_ids[0]),
            -1,
        )
        if source_row < 0:
            return False

        if row < 0:
            if parent.isValid():
                row = parent.row()
            else:
                row = len(self._tracks)
        target_row = row - 1 if row > source_row else row
        if self._reorder_callback is None:
            return False
        return bool(self._reorder_callback(source_row, target_row))

    @staticmethod
    def _cover_icon(track, size):
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
    def __init__(self):
        super().__init__()
        self._tracks = []

    def set_tracks(self, tracks):
        self.beginResetModel()
        self._tracks = tracks
        self.endResetModel()

    def rowCount(self, parent = QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._tracks)

    def data(self, index, role = Qt.ItemDataRole.DisplayRole):
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

    def track_at(self, row):
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
    playlists_changed = Signal(object)
    playlist_feedback = Signal(str)
    collection_mode_changed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._scanner = LibraryScanner()
        self._player = AudioPlayerService()
        self._playlists = PlaylistsService()
        self._settings = SettingsService()

        self._folders = self._settings.library_folders()
        self._all_tracks = []
        self._filtered_tracks = []
        self._tracks_by_id = {}
        self._search_text = ""
        self._collection_mode = "Library"
        self._current_playlist_id = None
        self._listen_counts = {}
        self._favourites = set()

        self.table_model = TrackTableModel()
        self.grid_model = TrackGridModel()

        self._player.track_changed.connect(self._on_track_changed)
        self._player.position_changed.connect(self._on_position_changed)
        self._player.duration_changed.connect(self._on_duration_changed)

        self._last_duration_ms = 0
        self._scan_thread = None
        self._scan_worker = None
        self._emit_playlists_changed()
        self._sync_table_capabilities()
        if self._folders:
            self.rescan_library()

    @property
    def player(self):
        return self._player

    @property
    def playlists(self):
        return self._playlists.all()

    def add_folder(self, folder):
        resolved = folder.expanduser().resolve()
        if resolved in self._folders:
            return
        self._folders.append(resolved)
        self._settings.set_library_folders(self._folders)
        self.rescan_library()

    def rescan_library(self):
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

    def set_search_text(self, text):
        self._search_text = text.strip().lower()
        self._apply_filter()

    def set_collection_mode(self, mode):
        valid = {"Library", "Daily Mix", "Top Hits", "Favourites"}
        self._current_playlist_id = None
        self._collection_mode = mode if mode in valid else "Library"
        self.collection_mode_changed.emit(self._collection_mode, "")
        self._sync_table_capabilities()
        self._apply_filter()

    def set_playlist_collection(self, playlist_id: str):
        playlist = self._playlists.playlist_by_id(playlist_id)
        if playlist is None:
            self.set_collection_mode("Library")
            self.playlist_feedback.emit("Playlist no longer exists.")
            return
        self._collection_mode = "Playlist"
        self._current_playlist_id = playlist.id
        self.collection_mode_changed.emit("Playlist", playlist.id)
        self._sync_table_capabilities()
        self._apply_filter()

    def create_playlist(self, name: str) -> bool:
        try:
            playlist = self._playlists.create(name)
        except ValueError as exc:
            self.playlist_feedback.emit(str(exc))
            return False

        self._emit_playlists_changed()
        self.set_playlist_collection(playlist.id)
        self.playlist_feedback.emit(f"Created playlist: {playlist.name}")
        return True

    def delete_playlist(self, playlist_id: str) -> bool:
        deleted = self._playlists.delete(playlist_id)
        if not deleted:
            self.playlist_feedback.emit("Playlist could not be deleted.")
            return False

        was_active = self._current_playlist_id == playlist_id
        self._emit_playlists_changed()
        if was_active:
            self.set_collection_mode("Library")
        else:
            self._apply_filter()
        self.playlist_feedback.emit("Playlist deleted.")
        return True

    def add_track_to_playlist(self, playlist_id: str, track_id: str) -> bool:
        try:
            result = self._playlists.add_track(playlist_id, track_id)
        except ValueError:
            self.playlist_feedback.emit("Playlist not found.")
            return False

        if result == "duplicate":
            self.playlist_feedback.emit("Track is already in that playlist.")
            return False

        if self._current_playlist_id == playlist_id:
            self._apply_filter()
        self._emit_playlists_changed()
        self.playlist_feedback.emit("Track added to playlist.")
        return True

    def reorder_current_playlist(self, source_index: int, target_index: int) -> bool:
        if self._current_playlist_id is None:
            return False
        changed = self._playlists.reorder_tracks(
            self._current_playlist_id,
            source_index,
            target_index,
        )
        if changed:
            self._apply_filter()
        return changed

    def current_playlist_id(self) -> str | None:
        return self._current_playlist_id

    def custom_playlist_name(self, playlist_id: str) -> str | None:
        playlist = self._playlists.playlist_by_id(playlist_id)
        return None if playlist is None else playlist.name

    def custom_playlists(self) -> list[Playlist]:
        return self._playlists.all()

    def current_collection_mode(self) -> str:
        return self._collection_mode

    def track_id_at(self, row: int) -> str | None:
        track = self.table_model.track_at(row)
        return None if track is None else track.id

    def is_custom_playlist_mode(self) -> bool:
        return self._current_playlist_id is not None

    def can_reorder_current_collection(self) -> bool:
        return self.is_custom_playlist_mode() and not self._search_text

    def toggle_current_track_favourite(self):
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

    def _apply_filter(self):
        if self._current_playlist_id is not None:
            playlist = self._playlists.playlist_by_id(self._current_playlist_id)
            track_ids = [] if playlist is None else playlist.tracks
            base_tracks = [
                self._tracks_by_id[track_id]
                for track_id in track_ids
                if track_id in self._tracks_by_id
            ]
        elif self._collection_mode == "Daily Mix":
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
                if needle in t.title.lower() or needle in t.artist.lower() or needle in t.album.lower() or needle in t.genre.lower()
            ]

        show_counts = self._collection_mode == "Top Hits"
        self.table_model.set_listen_counts(self._listen_counts, show_counts=show_counts)
        self.table_model.set_tracks(self._filtered_tracks)
        self.grid_model.set_tracks(self._filtered_tracks)
        self.library_changed.emit(len(self._filtered_tracks))
        self.collection_info_changed.emit(self._collection_info_text())

    def play_index(self, row):
        if not (0 <= row < len(self._filtered_tracks)):
            return
        self._player.set_playlist(self._filtered_tracks, start_index=row)

    def play_pause(self):
        if self._player.current_track is None and self._filtered_tracks:
            self._player.set_playlist(self._filtered_tracks, start_index=0)
            return
        self._player.toggle_play_pause()

    def stop(self):
        self._player.stop()

    def next(self):
        self._player.next()

    def previous(self):
        self._player.previous()

    def set_volume(self, value):
        self._player.set_volume(value)

    def seek(self, position_ms):
        self._player.seek(position_ms)

    def set_shuffle(self, enabled):
        self._player.set_shuffle(enabled)

    def set_repeat_mode(self, text):
        mapping = {
            RepeatMode.OFF.value: RepeatMode.OFF,
            RepeatMode.TRACK.value: RepeatMode.TRACK,
            RepeatMode.PLAYLIST.value: RepeatMode.PLAYLIST,
        }
        self._player.set_repeat_mode(mapping.get(text, RepeatMode.OFF))

    @staticmethod
    def ms_to_time(ms):
        total_sec = max(0, int(ms // 1000))
        minutes, seconds = divmod(total_sec, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _on_track_changed(self, track):
        key = str(track.path)
        self._listen_counts[key] = self._listen_counts.get(key, 0) + 1
        self.favourite_state_changed.emit(key in self._favourites)
        self.table_model.set_active_track(track.path)
        self.now_playing_changed.emit(f"Now playing: {track.title} - {track.artist}")
        if self._collection_mode == "Top Hits":
            self._apply_filter()

    def _on_position_changed(self, position_ms):
        self.position_text_changed.emit(self.ms_to_time(position_ms))

    def _on_duration_changed(self, duration_ms):
        self._last_duration_ms = duration_ms
        self.duration_text_changed.emit(self.ms_to_time(duration_ms))

    @Slot(object)
    def _on_scan_finished(self, tracks):
        self._all_tracks = tracks
        self._tracks_by_id = {track.id: track for track in self._all_tracks}
        self._apply_filter()
        self.scan_finished.emit(len(self._all_tracks))

    @Slot(str)
    def _on_scan_failed(self, message):
        self.scan_failed.emit(message or "Unknown scan error")

    @Slot()
    def _cleanup_scan(self):
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

    def _daily_mix_tracks(self):
        if len(self._all_tracks) <= 10:
            return list(self._all_tracks)
        seed = date.today().toordinal() + len(self._all_tracks)
        rng = random.Random(seed)
        return rng.sample(self._all_tracks, 10)

    def _top_hit_tracks(self):
        sorted_tracks = sorted(
            self._all_tracks,
            key=lambda t: (-self._listen_counts.get(str(t.path), 0), t.title.lower()),
        )
        # Show only listened tracks first; if no listens yet, show a small seed list.
        listened = [t for t in sorted_tracks if self._listen_counts.get(str(t.path), 0) > 0]
        if listened:
            return listened
        return sorted_tracks[: min(20, len(sorted_tracks))]

    def _collection_info_text(self):
        if self._current_playlist_id is not None:
            playlist = self._playlists.playlist_by_id(self._current_playlist_id)
            if playlist is None:
                return "Playlist unavailable"
            available_count = sum(1 for track_id in playlist.tracks if track_id in self._tracks_by_id)
            missing_count = len(playlist.tracks) - available_count
            if missing_count > 0:
                return f"{playlist.name}: {available_count} available, {missing_count} missing"
            return f"{playlist.name}: {available_count} tracks"
        if self._collection_mode == "Daily Mix":
            return "Daily Mix: up to 10 tracks"
        if self._collection_mode == "Top Hits":
            total = sum(self._listen_counts.values())
            return f"Top Hits total listens: {total}"
        if self._collection_mode == "Favourites":
            return f"Favourites: {len(self._favourites)}"
        return "Library"

    def _emit_playlists_changed(self):
        self.playlists_changed.emit(self._playlists.all())

    def _sync_table_capabilities(self):
        self.table_model.set_reorder_enabled(
            self.is_custom_playlist_mode(),
            self.reorder_current_playlist,
        )
