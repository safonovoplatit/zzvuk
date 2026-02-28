from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QPushButton,
    QSlider,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QMessageBox,
)

from app.services.audio_player import RepeatMode
from app.viewmodels.main_viewmodel import MainViewModel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ZZvuk Music Player")
        self.resize(1200, 760)

        self.vm = MainViewModel()
        self._is_seeking = False

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        central = QWidget(self)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        top_row = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add Folder")
        self.rescan_btn = QPushButton("Rescan")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by track title or artist...")
        self.view_mode = QComboBox()
        self.view_mode.addItems(["List", "Grid"])
        self.count_label = QLabel("Tracks: 0")
        self.scan_status_label = QLabel("")
        top_row.addWidget(self.add_folder_btn)
        top_row.addWidget(self.rescan_btn)
        top_row.addWidget(self.search_edit, 1)
        top_row.addWidget(self.view_mode)
        top_row.addWidget(self.scan_status_label)
        top_row.addWidget(self.count_label)

        self.track_table = QTableView()
        self.track_table.setModel(self.vm.table_model)
        self.track_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.track_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.track_table.setAlternatingRowColors(True)
        self.track_table.horizontalHeader().setStretchLastSection(True)

        self.track_grid = QListView()
        self.track_grid.setModel(self.vm.grid_model)
        self.track_grid.setViewMode(QListView.ViewMode.IconMode)
        self.track_grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.track_grid.setUniformItemSizes(True)
        self.track_grid.setWordWrap(True)
        self.track_grid.setSpacing(10)
        self.track_grid.setGridSize(QSize(180, 210))
        self.track_grid.setIconSize(QSize(140, 140))

        self.views_stack = QStackedWidget()
        self.views_stack.addWidget(self.track_table)
        self.views_stack.addWidget(self.track_grid)

        playback_row = QGridLayout()
        self.now_playing_label = QLabel("Now playing: -")

        self.prev_btn = QPushButton("Previous")
        self.play_btn = QPushButton("Play/Pause")
        self.stop_btn = QPushButton("Stop")
        self.next_btn = QPushButton("Next")

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.current_time_label = QLabel("00:00")
        self.total_time_label = QLabel("00:00")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_label = QLabel("Volume")

        self.repeat_combo = QComboBox()
        self.repeat_combo.addItems(
            [RepeatMode.OFF.value, RepeatMode.TRACK.value, RepeatMode.PLAYLIST.value]
        )
        self.shuffle_check = QCheckBox("Shuffle")

        playback_row.addWidget(self.now_playing_label, 0, 0, 1, 8)
        playback_row.addWidget(self.prev_btn, 1, 0)
        playback_row.addWidget(self.play_btn, 1, 1)
        playback_row.addWidget(self.stop_btn, 1, 2)
        playback_row.addWidget(self.next_btn, 1, 3)
        playback_row.addWidget(self.current_time_label, 1, 4)
        playback_row.addWidget(self.seek_slider, 1, 5)
        playback_row.addWidget(self.total_time_label, 1, 6)

        playback_row.addWidget(self.volume_label, 2, 0)
        playback_row.addWidget(self.volume_slider, 2, 1, 1, 2)
        playback_row.addWidget(QLabel("Repeat"), 2, 3)
        playback_row.addWidget(self.repeat_combo, 2, 4)
        playback_row.addWidget(self.shuffle_check, 2, 5)

        main_layout.addLayout(top_row)
        main_layout.addWidget(self.views_stack, 1)
        main_layout.addLayout(playback_row)

        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.add_folder_btn.clicked.connect(self._choose_folder)
        self.rescan_btn.clicked.connect(self.vm.rescan_library)
        self.search_edit.textChanged.connect(self.vm.set_search_text)
        self.view_mode.currentIndexChanged.connect(self.views_stack.setCurrentIndex)

        self.track_table.doubleClicked.connect(lambda idx: self.vm.play_index(idx.row()))
        self.track_grid.doubleClicked.connect(lambda idx: self.vm.play_index(idx.row()))

        self.play_btn.clicked.connect(self.vm.play_pause)
        self.stop_btn.clicked.connect(self.vm.stop)
        self.next_btn.clicked.connect(self.vm.next)
        self.prev_btn.clicked.connect(self.vm.previous)

        self.volume_slider.valueChanged.connect(self.vm.set_volume)
        self.repeat_combo.currentTextChanged.connect(self.vm.set_repeat_mode)
        self.shuffle_check.toggled.connect(self.vm.set_shuffle)

        self.seek_slider.sliderPressed.connect(self._begin_seek)
        self.seek_slider.sliderReleased.connect(self._end_seek)

        self.vm.player.position_changed.connect(self._on_player_position)
        self.vm.player.duration_changed.connect(self._on_player_duration)

        self.vm.library_changed.connect(self._on_library_changed)
        self.vm.scan_started.connect(self._on_scan_started)
        self.vm.scan_finished.connect(self._on_scan_finished)
        self.vm.scan_failed.connect(self._on_scan_failed)
        self.vm.now_playing_changed.connect(self.now_playing_label.setText)
        self.vm.position_text_changed.connect(self.current_time_label.setText)
        self.vm.duration_text_changed.connect(self.total_time_label.setText)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose Music Folder", str(Path.home()))
        if folder:
            self.vm.add_folder(Path(folder))

    def _on_library_changed(self, count: int) -> None:
        self.count_label.setText(f"Tracks: {count}")
        self.track_table.resizeColumnsToContents()

    def _on_scan_started(self) -> None:
        self.scan_status_label.setText("Scanning library...")
        self.add_folder_btn.setEnabled(False)
        self.rescan_btn.setEnabled(False)

    def _on_scan_finished(self, _count: int) -> None:
        self.scan_status_label.setText("")
        self.add_folder_btn.setEnabled(True)
        self.rescan_btn.setEnabled(True)

    def _on_scan_failed(self, message: str) -> None:
        self._on_scan_finished(0)
        QMessageBox.critical(self, "Scan failed", message)

    def _on_player_position(self, position: int) -> None:
        if not self._is_seeking:
            self.seek_slider.setValue(position)

    def _on_player_duration(self, duration: int) -> None:
        self.seek_slider.setRange(0, max(0, duration))

    def _begin_seek(self) -> None:
        self._is_seeking = True

    def _end_seek(self) -> None:
        self._is_seeking = False
        self.vm.seek(self.seek_slider.value())


def run() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
