from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QInputDialog,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.services.audio_player import RepeatMode
from app.viewmodels.main_viewmodel import MainViewModel
from app.viewmodels.main_viewmodel import TrackTableModel
from app.views.playlist_widgets import (
    PLAYLIST_ID_ROLE,
    PLAYLIST_KIND_ROLE,
    PlaylistListItemWidget,
    PlaylistListWidget,
)


class SeekSlider(QSlider):
    quickSeek = Signal(int)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().hitTestComplexControl(
            QStyle.ComplexControl.CC_Slider,
            option,
            event.position().toPoint(),
            self,
        )
        if handle == QStyle.SubControl.SC_SliderHandle:
            super().mousePressEvent(event)
            return

        value = self._value_from_click(event.position().toPoint())
        self.setValue(value)
        self.quickSeek.emit(value)
        self.sliderMoved.emit(value)
        event.accept()

    def _value_from_click(self, pos):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )

        if self.orientation() == Qt.Orientation.Horizontal:
            slider_length = handle.width()
            slider_min = groove.x()
            slider_max = groove.right() - slider_length + 1
            pos_value = pos.x() - slider_length // 2
        else:
            slider_length = handle.height()
            slider_min = groove.y()
            slider_max = groove.bottom() - slider_length + 1
            pos_value = pos.y() - slider_length // 2

        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            pos_value - slider_min,
            max(1, slider_max - slider_min),
            option.upsideDown,
        )


class MainWindow(QMainWindow):
    BUILTIN_COLLECTIONS = ["Library", "Daily Mix", "Top Hits", "Favourites"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZZvuk")
        self.resize(1360, 860)

        self.vm = MainViewModel()
        self._is_seeking = False
        self._progress_anim = QPropertyAnimation()
        self._repeat_modes = [RepeatMode.OFF, RepeatMode.TRACK, RepeatMode.PLAYLIST]
        self._repeat_index = 0
        self._playlist_sync_in_progress = False
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._fade_feedback_out)
        self._feedback_anim = None

        self._build_ui()
        self._connect_signals()
        self._apply_styles()
        self._apply_depth()
        self._refresh_playlist_items(self.vm.custom_playlists())
        self._sync_playlist_selection("Library", "")
        self._update_track_table_drag_mode()
        self._update_empty_playlist_state()
        self._sync_folder_actions()
        self._refresh_queue(self.vm.queue_tracks(), self.vm.current_queue_index())

    def _build_ui(self):
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)

        self.sidebar = self._build_sidebar()
        self.center = self._build_center_panel()
        self.queue_panel = self._build_queue_panel()

        content_row.addWidget(self.sidebar)
        content_row.addWidget(self.center, 1)
        content_row.addWidget(self.queue_panel)

        self.player_bar = self._build_player_bar()

        root_layout.addLayout(content_row, 1)
        root_layout.addWidget(self.player_bar)
        self.setCentralWidget(root)

    def _build_sidebar(self):
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(260)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        brand_wrap = QWidget()
        brand_row = QHBoxLayout(brand_wrap)
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(10)

        brand_logo = QLabel()
        brand_logo.setObjectName("brandLogo")
        brand_logo.setFixedSize(48, 48)

        try: # PyInstaller
            base_path = Path(sys._MEIPASS).resolve()
        except Exception:
            base_path = Path(__file__).resolve().parents[2]
        logo_path = base_path / "photos/logo.jpg"
        if logo_path.exists():
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                brand_logo.setPixmap(
                    pix.scaled(
                        48,
                        48,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.setWindowIcon(QIcon(pix))
            else:
                brand_logo.setText("paste_here.png")
        else:
            brand_logo.setText("paste_here.png")
        brand_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        brand = QLabel("Z Zvuk (alpha)")
        brand.setObjectName("brand")
        brand_row.addWidget(brand_logo)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)

        self.home_btn = QPushButton("Home")
        self.home_btn.setObjectName("navPill")
        self.home_btn.setCheckable(True)
        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("navPill")
        self.search_btn.setCheckable(True)
        self.library_btn = QPushButton("Library")
        self.library_btn.setObjectName("navPill")
        self.library_btn.setCheckable(True)
        self.library_btn.setChecked(True)

        nav_head = QWidget()
        nav_head_row = QHBoxLayout(nav_head)
        nav_head_row.setContentsMargins(0, 0, 0, 0)
        nav_head_row.setSpacing(8)

        nav_title = QLabel("Playlists")
        nav_title.setObjectName("sectionTitle")

        self.new_playlist_btn = QPushButton("New Playlist")
        self.new_playlist_btn.setObjectName("compactButton")

        nav_head_row.addWidget(nav_title)
        nav_head_row.addStretch(1)
        nav_head_row.addWidget(self.new_playlist_btn)

        self.playlist_list = PlaylistListWidget(TrackTableModel.MIME_TYPE)
        self.playlist_list.setObjectName("playlistList")
        self.playlist_list.setSpacing(2)

        self.add_folder_btn = QPushButton("Add Folder")
        self.remove_folder_btn = QPushButton("Remove Folder")
        self.rescan_btn = QPushButton("Rescan")

        layout.addWidget(brand_wrap)
        layout.addWidget(self.home_btn)
        layout.addWidget(self.search_btn)
        layout.addWidget(self.library_btn)
        layout.addSpacing(12)
        layout.addWidget(nav_head)
        layout.addWidget(self.playlist_list, 1)
        layout.addWidget(self.add_folder_btn)
        layout.addWidget(self.remove_folder_btn)
        layout.addWidget(self.rescan_btn)
        return frame

    def _build_center_panel(self):
        frame = QFrame()
        frame.setObjectName("centerPanel")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search tracks, artists, genres")
        self.count_label = QLabel("0 tracks")
        self.scan_status_label = QLabel("")
        self.scan_status_label.setObjectName("scanStatus")
        self.collection_info_label = QLabel("Library")
        self.collection_info_label.setObjectName("collectionInfo")
        self.feedback_label = QLabel("")
        self.feedback_label.setObjectName("feedbackLabel")
        self.feedback_label.hide()
        self._feedback_opacity = QGraphicsOpacityEffect(self.feedback_label)
        self._feedback_opacity.setOpacity(0.0)
        self.feedback_label.setGraphicsEffect(self._feedback_opacity)

        top_bar.addWidget(self.search_edit, 1)
        top_bar.addWidget(self.collection_info_label)
        top_bar.addWidget(self.feedback_label)
        top_bar.addWidget(self.scan_status_label)
        top_bar.addWidget(self.count_label)

        self.track_table = QTableView()
        self.track_table.setModel(self.vm.table_model)
        self.track_table.setObjectName("trackTable")
        self.track_table.setIconSize(QSize(36, 36))
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.track_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_table.setAlternatingRowColors(False)
        self.track_table.setShowGrid(False)
        self.track_table.setMouseTracking(True)
        self.track_table.setDragEnabled(True)
        self.track_table.setAcceptDrops(True)
        self.track_table.setDropIndicatorShown(True)
        self.track_table.setDragDropOverwriteMode(False)
        self.track_table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.track_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.verticalHeader().setDefaultSectionSize(48)

        header = self.track_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.empty_playlist_label = QLabel("Drag tracks here or use right-click menu")
        self.empty_playlist_label.setObjectName("emptyPlaylistState")
        self.empty_playlist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_playlist_label.hide()

        layout.addLayout(top_bar)
        layout.addWidget(self.track_table, 1)
        layout.addWidget(self.empty_playlist_label)
        return frame

    def _build_queue_panel(self):
        frame = QFrame()
        frame.setObjectName("queuePanel")
        frame.setFixedWidth(300)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("Now Playing")
        title.setObjectName("sectionTitle")

        self.queue_clear_btn = QPushButton("Clear Queue")
        self.queue_clear_btn.setObjectName("compactButton")

        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.queue_clear_btn)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queueList")

        self.queue_remove_btn = QPushButton("Remove Selected")
        self.queue_remove_btn.setObjectName("compactButton")

        layout.addLayout(header)
        layout.addWidget(self.queue_list, 1)
        layout.addWidget(self.queue_remove_btn)
        return frame

    def _build_player_bar(self):
        frame = QFrame()
        frame.setObjectName("playerBar")
        frame.setFixedHeight(132)

        layout = QGridLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(6)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(72, 72)
        self.cover_label.setObjectName("coverLabel")

        self.now_playing_label = QLabel("Nothing playing")
        self.now_playing_label.setObjectName("nowPlaying")
        self.meta_label = QLabel("Pick a track to start")
        self.meta_label.setObjectName("meta")

        left_col = QVBoxLayout()
        left_col.setSpacing(2)
        left_col.addWidget(self.now_playing_label)
        left_col.addWidget(self.meta_label)

        self.shuffle_btn = self._make_transport_button("⇄", "Shuffle")
        self.shuffle_btn.setCheckable(True)
        self.favourite_btn = self._make_transport_button("♡", "Add to favourites")
        self.favourite_btn.setCheckable(True)
        self.prev_btn = self._make_transport_button("⏮", "Previous")
        self.play_btn = self._make_transport_button("▶", "Play/Pause", play=True)
        self.next_btn = self._make_transport_button("⏭", "Next")
        self.repeat_btn = self._make_transport_button("↻", "Repeat: Off")
        self.repeat_btn.setCheckable(True)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addStretch(1)
        controls.addWidget(self.favourite_btn)
        controls.addWidget(self.shuffle_btn)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.repeat_btn)
        controls.addStretch(1)

        timeline = QHBoxLayout()
        timeline.setSpacing(8)
        self.current_time_label = QLabel("00:00")
        self.total_time_label = QLabel("00:00")
        self.seek_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setObjectName("seekSlider")

        timeline.addWidget(self.current_time_label)
        timeline.addWidget(self.seek_slider, 1)
        timeline.addWidget(self.total_time_label)

        center_col = QVBoxLayout()
        center_col.setSpacing(4)
        center_col.addLayout(controls)
        center_col.addLayout(timeline)

        right_col = QHBoxLayout()
        right_col.setSpacing(8)
        self.volume_text = QLabel("Volume")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(130)
        right_col.addWidget(self.volume_text)
        right_col.addWidget(self.volume_slider)

        layout.addWidget(self.cover_label, 0, 0, 2, 1)
        layout.addLayout(left_col, 0, 1, 2, 1)
        layout.addLayout(center_col, 0, 2, 2, 1)
        layout.addLayout(right_col, 0, 3, 2, 1)
        layout.setColumnStretch(2, 1)

        self._set_placeholder_cover()
        return frame

    @staticmethod
    def _make_transport_button(icon_text, tooltip, play = False):
        btn = QPushButton(icon_text)
        btn.setToolTip(tooltip)
        btn.setObjectName("playCircle" if play else "iconCircle")
        btn.setFixedSize(52, 52) if play else btn.setFixedSize(40, 40)
        return btn

    def _apply_styles(self):
        self.setStyleSheet(
            """
            /* Material 3 expressive dark tokens */
            QWidget {
                color: #E8E0F0;
                font-family: Inter, "SF Pro Text", Arial;
                font-size: 13px;
            }
            * {
                selection-background-color: #6DDA92;
            }
            QMainWindow {
                background: qradialgradient(cx:0.05, cy:0.0, radius:1.2,
                                            fx:0.05, fy:0.0,
                                            stop:0 #273428,
                                            stop:0.22 #1C1A21,
                                            stop:1 #141218);
            }
            QFrame#sidebar, QFrame#centerPanel, QFrame#playerBar, QFrame#queuePanel {
                background: rgba(35, 33, 43, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 28px;
            }
            QLabel#brand {
                font-size: 24px;
                font-weight: 800;
                color: #F6EEFF;
                padding: 2px 2px 10px 2px;
            }
            QLabel#brandLogo {
                background: rgba(255, 255, 255, 0.05);
                border: 1px dashed rgba(126, 227, 154, 0.5);
                border-radius: 12px;
                color: #CFECD8;
                font-size: 10px;
                padding: 2px;
            }
            QLabel#sectionTitle {
                color: #B8AEC8;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1px;
                padding-top: 10px;
            }
            QLabel#scanStatus {
                color: #7EE39A;
                font-weight: 700;
            }
            QLabel#collectionInfo {
                color: #D5CDE1;
                background: rgba(126, 227, 154, 0.16);
                border: 1px solid rgba(126, 227, 154, 0.42);
                border-radius: 14px;
                padding: 4px 10px;
                font-weight: 700;
            }
            QPushButton {
                background: rgba(208, 188, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 18px;
                padding: 9px 14px;
                color: #F2EAFB;
            }
            QPushButton#compactButton,
            QPushButton#playlistDeleteButton {
                border-radius: 14px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(126, 227, 154, 0.20);
                border: 1px solid rgba(126, 227, 154, 0.65);
            }
            QPushButton:pressed {
                background: rgba(126, 227, 154, 0.30);
            }
            QPushButton#navPill {
                text-align: left;
                font-weight: 700;
                border-radius: 22px;
                padding: 10px 14px;
                background: rgba(255, 255, 255, 0.04);
                color: #DCD2E9;
            }
            QPushButton#navPill:checked {
                background: rgba(126, 227, 154, 0.24);
                border: 1px solid rgba(126, 227, 154, 0.68);
                border-radius: 22px;
                color: #F2FFF5;
            }
            QPushButton#iconCircle {
                border-radius: 20px;
                padding: 0px;
                font-size: 16px;
                font-weight: 600;
            }
            QPushButton#playCircle {
                border-radius: 26px;
                padding: 0px;
                font-size: 18px;
                font-weight: 700;
                background: #7EE39A;
                border: 1px solid #7EE39A;
                color: #132117;
            }
            QPushButton#playCircle:hover {
                background: #94EEAE;
                border: 1px solid #94EEAE;
            }
            QPushButton#playCircle:pressed {
                background: #5DCC7E;
                border: 1px solid #5DCC7E;
            }
            QPushButton#iconCircle:checked {
                background: rgba(126, 227, 154, 0.30);
                border: 1px solid rgba(126, 227, 154, 0.85);
                color: #EDFFF2;
            }
            QLineEdit {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.11);
                border-radius: 18px;
                padding: 11px 14px;
                color: #F4EEFB;
                selection-color: #132117;
            }
            QLineEdit:focus {
                border: 1px solid rgba(126, 227, 154, 0.9);
            }
            QDialog,
            QMessageBox,
            QInputDialog,
            QFileDialog,
            QMenu {
                background: #211E27;
                color: #F4EEFB;
            }
            QDialog QLabel,
            QMessageBox QLabel,
            QInputDialog QLabel,
            QFileDialog QLabel {
                color: #F4EEFB;
            }
            QDialog QPushButton,
            QMessageBox QPushButton,
            QInputDialog QPushButton,
            QFileDialog QPushButton {
                min-width: 88px;
            }
            QDialog QLineEdit,
            QInputDialog QLineEdit,
            QFileDialog QLineEdit {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.14);
            }
            QFileDialog QListView,
            QFileDialog QTreeView,
            QFileDialog QTableView,
            QFileDialog QSidebar {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                color: #F4EEFB;
                selection-background-color: rgba(126, 227, 154, 0.32);
                selection-color: #F4FFF7;
            }
            QInputDialog QComboBox,
            QInputDialog QAbstractSpinBox,
            QFileDialog QComboBox,
            QFileDialog QAbstractSpinBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 12px;
                padding: 6px 10px;
                color: #F4EEFB;
            }
            QInputDialog QAbstractItemView {
                background: #211E27;
                border: 1px solid rgba(255, 255, 255, 0.10);
                color: #F4EEFB;
                selection-background-color: rgba(126, 227, 154, 0.32);
                selection-color: #F4FFF7;
            }
            QMenu {
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 14px;
                padding: 8px;
            }
            QMenu::item {
                padding: 8px 14px;
                border-radius: 10px;
                color: #F4EEFB;
            }
            QMenu::item:selected {
                background: rgba(126, 227, 154, 0.24);
                color: #F4FFF7;
            }
            QMenu::item:disabled {
                color: #8E859C;
            }
            QListWidget#playlistList {
                background: transparent;
                border: none;
                border-radius: 18px;
                padding: 2px;
            }
            QListWidget#queueList {
                background: rgba(25, 23, 31, 0.82);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 22px;
                padding: 8px;
                outline: none;
            }
            QListWidget#queueList::item {
                background: transparent;
                border: none;
                margin: 2px 0px;
                padding: 10px 12px;
                border-radius: 16px;
                color: #DCD2E9;
            }
            QListWidget#queueList::item:selected {
                background: rgba(126, 227, 154, 0.24);
                color: #F4FFF7;
            }
            QListWidget#playlistList::item {
                background: transparent;
                border: none;
                margin: 2px 0px;
            }
            QWidget#playlistRow {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 15px;
            }
            QWidget#playlistRow[selected="true"] {
                background: rgba(126, 227, 154, 0.28);
                border: 1px solid rgba(126, 227, 154, 0.62);
            }
            QLabel#playlistRowName {
                color: #D3C8E1;
                font-weight: 600;
            }
            QWidget#playlistRow[selected="true"] QLabel#playlistRowName {
                color: #F6FFF8;
            }
            QTableView#trackTable {
                background: rgba(25, 23, 31, 0.82);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 24px;
                padding: 8px;
                alternate-background-color: transparent;
                selection-background-color: rgba(126, 227, 154, 0.24);
                selection-color: #F5FFF7;
            }
            QHeaderView::section {
                background: transparent;
                color: #B7ABC6;
                border: none;
                padding: 10px 8px;
                font-weight: 700;
            }
            QTableView#trackTable::item {
                border: none;
                padding: 10px 8px;
                margin: 2px;
                border-radius: 16px;
                background: transparent;
            }
            QTableView#trackTable::item:hover {
                background: rgba(255, 255, 255, 0.08);
            }
            QLabel#coverLabel {
                border-radius: 20px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #324A38, stop:1 #1C2A20);
                border: 1px solid rgba(255, 255, 255, 0.12);
            }
            QLabel#nowPlaying {
                font-size: 15px;
                font-weight: 700;
                color: #F7EEFF;
            }
            QLabel#meta {
                color: #C6BAD5;
                font-size: 12px;
            }
            QLabel#feedbackLabel {
                color: #DDF9E5;
                background: rgba(126, 227, 154, 0.18);
                border: 1px solid rgba(126, 227, 154, 0.45);
                border-radius: 14px;
                padding: 4px 10px;
                font-weight: 700;
            }
            QLabel#emptyPlaylistState {
                color: #B8AEC8;
                border: 1px dashed rgba(255, 255, 255, 0.14);
                border-radius: 18px;
                padding: 16px;
                background: rgba(255, 255, 255, 0.04);
            }
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                border-radius: 3px;
                background: rgba(255, 255, 255, 0.24);
            }
            QSlider#seekSlider::sub-page:horizontal,
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #58C778, stop:1 #91EDA8);
                border-radius: 3px;
            }
            QSlider::add-page:horizontal {
                background: rgba(255, 255, 255, 0.20);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #EAFBEF;
                border: 2px solid #72D890;
                width: 16px;
                margin: -7px 0;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #FFFFFF;
            }
            """
        )

    def _apply_depth(self):
        for widget in (self.sidebar, self.center, self.player_bar, self.queue_panel):
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(36)
            shadow.setOffset(0, 10)
            shadow.setColor(QColor(0, 0, 0, 120))
            widget.setGraphicsEffect(shadow)

    def _connect_signals(self):
        self.add_folder_btn.clicked.connect(self._choose_folder)
        self.remove_folder_btn.clicked.connect(self._remove_folder)
        self.rescan_btn.clicked.connect(self.vm.rescan_library)
        self.new_playlist_btn.clicked.connect(self._create_playlist)
        self.search_edit.textChanged.connect(self.vm.set_search_text)
        self.playlist_list.currentItemChanged.connect(self._on_playlist_selected)
        self.playlist_list.itemDoubleClicked.connect(self._enqueue_playlist_item)
        self.playlist_list.track_dropped.connect(self._on_track_dropped_to_playlist)
        self.home_btn.clicked.connect(lambda: self._set_mode("Library"))
        self.library_btn.clicked.connect(lambda: self._set_mode("Library"))
        self.search_btn.clicked.connect(self._focus_search)

        self.track_table.doubleClicked.connect(self._enqueue_selected_tracks)
        self.track_table.customContextMenuRequested.connect(self._open_track_context_menu)
        self.queue_list.itemDoubleClicked.connect(self._play_queue_item)
        self.queue_list.itemSelectionChanged.connect(self._sync_queue_actions)
        self.queue_remove_btn.clicked.connect(self._remove_selected_queue_item)
        self.queue_clear_btn.clicked.connect(self.vm.clear_queue)

        self.play_btn.clicked.connect(self.vm.play_pause)
        self.next_btn.clicked.connect(self.vm.next)
        self.prev_btn.clicked.connect(self.vm.previous)
        self.shuffle_btn.toggled.connect(self.vm.set_shuffle)
        self.favourite_btn.clicked.connect(self.vm.toggle_current_track_favourite)
        self.repeat_btn.clicked.connect(self._cycle_repeat_mode)

        self.volume_slider.valueChanged.connect(self.vm.set_volume)

        self.seek_slider.sliderPressed.connect(self._begin_seek)
        self.seek_slider.sliderReleased.connect(self._end_seek)
        self.seek_slider.quickSeek.connect(self.vm.seek)

        self.vm.player.position_changed.connect(self._on_player_position)
        self.vm.player.duration_changed.connect(self._on_player_duration)
        self.vm.player.state_changed.connect(self._on_playback_state_changed)

        self.vm.library_changed.connect(self._on_library_changed)
        self.vm.scan_started.connect(self._on_scan_started)
        self.vm.scan_finished.connect(self._on_scan_finished)
        self.vm.scan_failed.connect(self._on_scan_failed)
        self.vm.collection_info_changed.connect(self.collection_info_label.setText)
        self.vm.favourite_state_changed.connect(self._on_favourite_state_changed)
        self.vm.now_playing_changed.connect(self._on_now_playing_text)
        self.vm.position_text_changed.connect(self.current_time_label.setText)
        self.vm.duration_text_changed.connect(self.total_time_label.setText)
        self.vm.player.track_changed.connect(self._on_track_changed)
        self.vm.playlists_changed.connect(self._refresh_playlist_items)
        self.vm.playlist_feedback.connect(self._show_feedback)
        self.vm.collection_mode_changed.connect(self._sync_playlist_selection)
        self.vm.queue_changed.connect(self._refresh_queue)

    def _choose_folder(self):
        dialog = QFileDialog(self, "Choose Music Folder", str(Path.home()))
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        if dialog.exec():
            selected = dialog.selectedFiles()
            if selected:
                self.vm.add_folder(Path(selected[0]))
                self._sync_folder_actions()

    def _remove_folder(self):
        folders = self.vm.library_folders()
        if not folders:
            QMessageBox.information(self, "Remove Folder", "No library folders saved yet.")
            return

        labels = [str(folder) for folder in folders]
        selected, accepted = QInputDialog.getItem(
            self,
            "Remove Library Folder",
            "Choose a folder to remove from the library:",
            labels,
            0,
            False,
        )
        if not accepted or not selected:
            return

        confirmed = QMessageBox.question(
            self,
            "Remove Folder",
            f'Remove "{selected}" from your library?\n\nFiles on disk will stay untouched.',
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        if self.vm.remove_folder(Path(selected)):
            self._sync_folder_actions()
            self._show_feedback("Library folder removed.")

    def _set_mode(self, mode):
        self.vm.set_collection_mode(mode)
        self.library_btn.setChecked(mode == "Library")
        self.home_btn.setChecked(mode == "Library")
        self.search_btn.setChecked(False)
        self._sync_playlist_selection(mode, "")

    def _on_playlist_selected(self, item, _previous = None):
        if self._playlist_sync_in_progress or item is None:
            return
        kind = item.data(PLAYLIST_KIND_ROLE)
        value = item.data(PLAYLIST_ID_ROLE)
        if kind == "custom":
            self.vm.set_playlist_collection(value)
            self.library_btn.setChecked(False)
            self.home_btn.setChecked(False)
            self.search_btn.setChecked(False)
            return
        self._set_mode(value)

    def _enqueue_playlist_item(self, item):
        if item is None:
            return
        kind = item.data(PLAYLIST_KIND_ROLE)
        value = item.data(PLAYLIST_ID_ROLE)
        if kind == "custom":
            self.vm.enqueue_collection("Playlist", value)
            return
        self.vm.enqueue_collection(value)

    def _focus_search(self):
        self.search_btn.setChecked(True)
        self.home_btn.setChecked(False)
        self.library_btn.setChecked(False)
        self.search_edit.setFocus()

    def _on_library_changed(self, count):
        self.count_label.setText(f"{count} tracks")
        self._update_track_table_drag_mode()
        self._update_empty_playlist_state()

    def _on_scan_started(self):
        self.scan_status_label.setText("Scanning...")
        self.add_folder_btn.setEnabled(False)
        self.remove_folder_btn.setEnabled(False)
        self.rescan_btn.setEnabled(False)

    def _on_scan_finished(self, _count):
        self.scan_status_label.setText("")
        self.add_folder_btn.setEnabled(True)
        self.rescan_btn.setEnabled(True)
        self._sync_folder_actions()

    def _on_scan_failed(self, message):
        self._on_scan_finished(0)
        QMessageBox.critical(self, "Scan failed", message)

    def _sync_folder_actions(self):
        self.remove_folder_btn.setEnabled(bool(self.vm.library_folders()))

    def _on_player_position(self, position):
        if self._is_seeking:
            return
        self._animate_progress(position)

    def _on_player_duration(self, duration):
        self.seek_slider.setRange(0, max(0, duration))

    def _begin_seek(self):
        self._is_seeking = True

    def _end_seek(self):
        self._is_seeking = False
        self.vm.seek(self.seek_slider.value())

    def _on_now_playing_text(self, text):
        self.now_playing_label.setText(text.replace("Now playing: ", ""))

    def _on_playback_state_changed(self, state_name):
        if state_name == "PlayingState":
            self.play_btn.setText("⏸")
            self.play_btn.setToolTip("Pause")
        else:
            self.play_btn.setText("▶")
            self.play_btn.setToolTip("Play")

    def _on_favourite_state_changed(self, is_fav):
        self.favourite_btn.setChecked(is_fav)
        self.favourite_btn.setText("♥" if is_fav else "♡")
        self.favourite_btn.setToolTip(
            "Remove from favourites" if is_fav else "Add to favourites"
        )

    def _on_track_changed(self, track):
        if track is None:
            self.meta_label.setText("Pick a track to start")
            self._set_placeholder_cover()
            return
        self.meta_label.setText(f"{track.album}  |  {track.genre}")
        if track.cover_path and track.cover_path.exists():
            pix = QPixmap(str(track.cover_path)).scaled(
                72,
                72,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cover_label.setPixmap(pix)
            return
        self._set_placeholder_cover()

    def _set_placeholder_cover(self):
        pix = QPixmap(72, 72)
        pix.fill(Qt.GlobalColor.transparent)
        self.cover_label.setPixmap(pix)

    def _animate_progress(self, target_value):
        self._progress_anim.stop()
        self._progress_anim = QPropertyAnimation(self.seek_slider, b"value", self)
        self._progress_anim.setDuration(180)
        self._progress_anim.setStartValue(self.seek_slider.value())
        self._progress_anim.setEndValue(target_value)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._progress_anim.start()

    def _cycle_repeat_mode(self):
        self._repeat_index = (self._repeat_index + 1) % len(self._repeat_modes)
        mode = self._repeat_modes[self._repeat_index]
        self.vm.set_repeat_mode(mode.value)

        if mode == RepeatMode.OFF:
            self.repeat_btn.setChecked(False)
            self.repeat_btn.setText("↻")
            self.repeat_btn.setToolTip("Repeat: Off")
        elif mode == RepeatMode.TRACK:
            self.repeat_btn.setChecked(True)
            self.repeat_btn.setText("↻1")
            self.repeat_btn.setToolTip("Repeat")
        else:
            self.repeat_btn.setChecked(True)
            self.repeat_btn.setText("↻")
            self.repeat_btn.setToolTip("Repeat: Playlist")

    def _refresh_playlist_items(self, playlists):
        current_kind = "custom" if self.vm.current_playlist_id() else "builtin"
        current_value = self.vm.current_playlist_id() or self.vm.current_collection_mode()

        self._playlist_sync_in_progress = True
        self.playlist_list.clear()

        for name in self.BUILTIN_COLLECTIONS:
            self._add_playlist_item(name=name, kind="builtin", value=name, removable=False)

        for playlist in playlists:
            self._add_playlist_item(
                name=playlist.name,
                kind="custom",
                value=playlist.id,
                removable=True,
            )

        self._playlist_sync_in_progress = False
        self._sync_playlist_selection(
            "Playlist" if current_kind == "custom" else current_value,
            current_value if current_kind == "custom" else "",
        )

    def _add_playlist_item(self, name: str, kind: str, value: str, removable: bool):
        item = QListWidgetItem()
        item.setData(PLAYLIST_KIND_ROLE, kind)
        item.setData(PLAYLIST_ID_ROLE, value)
        widget = PlaylistListItemWidget(
            name=name,
            playlist_id=value if kind == "custom" else None,
            removable=removable,
        )
        widget.delete_requested.connect(self._confirm_delete_playlist)
        item.setSizeHint(widget.sizeHint())
        self.playlist_list.addItem(item)
        self.playlist_list.setItemWidget(item, widget)

    def _sync_playlist_selection(self, mode: str, playlist_id: str):
        self._playlist_sync_in_progress = True
        for row in range(self.playlist_list.count()):
            item = self.playlist_list.item(row)
            widget = self.playlist_list.itemWidget(item)
            is_match = False
            if mode == "Playlist":
                is_match = item.data(PLAYLIST_KIND_ROLE) == "custom" and item.data(PLAYLIST_ID_ROLE) == playlist_id
            else:
                is_match = item.data(PLAYLIST_KIND_ROLE) == "builtin" and item.data(PLAYLIST_ID_ROLE) == mode
            if widget is not None:
                widget.set_selected(is_match)
            if is_match:
                self.playlist_list.setCurrentItem(item)
        self._playlist_sync_in_progress = False
        self._update_track_table_drag_mode()
        self._update_empty_playlist_state()

    def _create_playlist(self):
        name, accepted = QInputDialog.getText(
            self,
            "New Playlist",
            "Playlist name:",
            text="",
        )
        if accepted:
            self.vm.create_playlist(name)

    def _confirm_delete_playlist(self, playlist_id: str):
        name = self.vm.custom_playlist_name(playlist_id) or "this playlist"
        result = QMessageBox.question(
            self,
            "Delete Playlist",
            f'Delete "{name}"? Tracks stay in your library.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.vm.delete_playlist(playlist_id)

    def _on_track_dropped_to_playlist(self, track_id: str, playlist_id: str):
        self.vm.add_track_to_playlist(playlist_id, track_id)

    def _enqueue_selected_tracks(self, index):
        if not index.isValid():
            return

        selected_rows = sorted(
            model_index.row()
            for model_index in self.track_table.selectionModel().selectedRows()
        )
        if len(selected_rows) <= 1 or index.row() not in selected_rows:
            selected_rows = [index.row()]
        self.vm.enqueue_rows(selected_rows)

    def _open_track_context_menu(self, pos):
        index = self.track_table.indexAt(pos)
        if not index.isValid():
            return

        track_id = self.vm.track_id_at(index.row())
        if track_id is None:
            return

        menu = QMenu(self)
        add_menu = menu.addMenu("Add to playlist")
        playlists = self.vm.custom_playlists()
        if not playlists:
            empty_action = add_menu.addAction("No playlists yet")
            empty_action.setEnabled(False)
        for playlist in playlists:
            action = add_menu.addAction(playlist.name)
            action.triggered.connect(
                lambda _checked = False, pid = playlist.id, tid = track_id: self.vm.add_track_to_playlist(pid, tid)
            )

        menu.exec(self.track_table.viewport().mapToGlobal(pos))

    def _update_track_table_drag_mode(self):
        if self.vm.can_reorder_current_collection():
            self.track_table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            return
        self.track_table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def _update_empty_playlist_state(self):
        is_empty_playlist = self.vm.is_custom_playlist_mode() and self.vm.table_model.rowCount() == 0
        self.empty_playlist_label.setVisible(is_empty_playlist)

    def _show_feedback(self, message: str):
        if not message:
            return
        self._feedback_timer.stop()
        if self._feedback_anim is not None:
            self._feedback_anim.stop()
        self.feedback_label.setText(message)
        self.feedback_label.show()
        self._feedback_opacity.setOpacity(0.0)
        self._feedback_anim = QPropertyAnimation(self._feedback_opacity, b"opacity", self)
        self._feedback_anim.setDuration(180)
        self._feedback_anim.setStartValue(0.0)
        self._feedback_anim.setEndValue(1.0)
        self._feedback_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._feedback_anim.start()
        self._feedback_timer.start(2400)

    def _fade_feedback_out(self):
        if self._feedback_anim is not None:
            self._feedback_anim.stop()
        self._feedback_anim = QPropertyAnimation(self._feedback_opacity, b"opacity", self)
        self._feedback_anim.setDuration(220)
        self._feedback_anim.setStartValue(self._feedback_opacity.opacity())
        self._feedback_anim.setEndValue(0.0)
        self._feedback_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._feedback_anim.finished.connect(self.feedback_label.hide)
        self._feedback_anim.start()

    def _refresh_queue(self, tracks, current_index):
        self.queue_list.clear()
        for row, track in enumerate(tracks):
            prefix = "▶ " if row == current_index else ""
            text = f"{prefix}{track.title}\n{track.artist} | {track.duration_text}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, row)
            if row == current_index:
                item.setForeground(QColor("#F4FFF7"))
                item.setBackground(QColor("#1DB95433"))
            self.queue_list.addItem(item)

        has_tracks = bool(tracks)
        self.queue_clear_btn.setEnabled(has_tracks)
        self.queue_remove_btn.setEnabled(has_tracks and self.queue_list.currentItem() is not None)

        if 0 <= current_index < self.queue_list.count():
            self.queue_list.setCurrentRow(current_index)

    def _remove_selected_queue_item(self):
        item = self.queue_list.currentItem()
        if item is None:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
        if row is not None:
            self.vm.remove_queue_index(int(row))

    def _play_queue_item(self, item):
        row = item.data(Qt.ItemDataRole.UserRole)
        if row is not None:
            self.vm.play_queue_index(int(row))

    def _sync_queue_actions(self):
        self.queue_remove_btn.setEnabled(self.queue_list.currentItem() is not None)


def run():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
