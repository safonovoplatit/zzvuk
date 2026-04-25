from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QWidget


PLAYLIST_KIND_ROLE = Qt.ItemDataRole.UserRole
PLAYLIST_ID_ROLE = Qt.ItemDataRole.UserRole + 1


class PlaylistListItemWidget(QWidget):
    delete_requested = Signal(str)

    def __init__(self, name: str, playlist_id: str | None = None, removable: bool = False):
        super().__init__()
        self._playlist_id = playlist_id
        self._selected = False

        self.setObjectName("playlistRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.name_label = QLabel(name)
        self.name_label.setObjectName("playlistRowName")
        self.name_label.setWordWrap(False)
        layout.addWidget(self.name_label, 1)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("playlistDeleteButton")
        self.delete_btn.setVisible(removable)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(self._emit_delete)
        layout.addWidget(self.delete_btn)

        self._apply_state()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_state()

    def _emit_delete(self):
        if self._playlist_id:
            self.delete_requested.emit(self._playlist_id)

    def _apply_state(self):
        self.setProperty("selected", self._selected)
        self.style().unpolish(self)
        self.style().polish(self)


class PlaylistListWidget(QListWidget):
    track_dropped = Signal(str, str)

    def __init__(self, mime_type: str, parent = None):
        super().__init__(parent)
        self._mime_type = mime_type
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self._mime_type):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item and item.data(PLAYLIST_KIND_ROLE) == "custom" and event.mimeData().hasFormat(self._mime_type):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item is None or item.data(PLAYLIST_KIND_ROLE) != "custom":
            event.ignore()
            return
        if not event.mimeData().hasFormat(self._mime_type):
            event.ignore()
            return

        raw_ids = bytes(event.mimeData().data(self._mime_type)).decode("utf-8")
        track_ids = [value for value in raw_ids.splitlines() if value]
        playlist_id = item.data(PLAYLIST_ID_ROLE)
        for track_id in track_ids:
            self.track_dropped.emit(track_id, playlist_id)
        event.acceptProposedAction()
