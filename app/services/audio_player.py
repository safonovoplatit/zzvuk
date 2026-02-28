from __future__ import annotations

import random
from enum import Enum

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from app.models.track import Track


class RepeatMode(str, Enum):
    OFF = "Off"
    TRACK = "Repeat Track"
    PLAYLIST = "Repeat Playlist"


class AudioPlayerService(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(str)
    track_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)

        self._playlist: list[Track] = []
        self._current_index: int = -1
        self._shuffle_enabled = False
        self._repeat_mode = RepeatMode.OFF

        self._player.positionChanged.connect(self.position_changed.emit)
        self._player.durationChanged.connect(self.duration_changed.emit)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.playbackStateChanged.connect(
            lambda state: self.state_changed.emit(state.name)
        )

    @property
    def playlist(self) -> list[Track]:
        return self._playlist

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def current_track(self) -> Track | None:
        if 0 <= self._current_index < len(self._playlist):
            return self._playlist[self._current_index]
        return None

    def set_playlist(self, tracks: list[Track], start_index: int = 0) -> None:
        self._playlist = tracks
        if not tracks:
            self._current_index = -1
            self._player.stop()
            return
        self._current_index = max(0, min(start_index, len(tracks) - 1))
        self._load_current_and_play()

    def play_track(self, track: Track, playlist: list[Track] | None = None) -> None:
        if playlist is None:
            playlist = self._playlist
        if not playlist:
            return

        self._playlist = playlist
        for i, t in enumerate(self._playlist):
            if t.path == track.path:
                self._current_index = i
                self._load_current_and_play()
                return

    def play(self) -> None:
        if self._player.source().isEmpty() and self.current_track:
            self._load_current_and_play()
            return
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def toggle_play_pause(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def next(self) -> None:
        if not self._playlist:
            return
        if self._shuffle_enabled and len(self._playlist) > 1:
            choices = [i for i in range(len(self._playlist)) if i != self._current_index]
            self._current_index = random.choice(choices)
            self._load_current_and_play()
            return

        if self._current_index + 1 < len(self._playlist):
            self._current_index += 1
            self._load_current_and_play()
            return

        if self._repeat_mode == RepeatMode.PLAYLIST:
            self._current_index = 0
            self._load_current_and_play()
        else:
            self.stop()

    def previous(self) -> None:
        if not self._playlist:
            return
        if self._player.position() > 3000:
            self.seek(0)
            return

        if self._current_index > 0:
            self._current_index -= 1
        elif self._repeat_mode == RepeatMode.PLAYLIST:
            self._current_index = len(self._playlist) - 1

        self._load_current_and_play()

    def set_volume(self, value_0_100: int) -> None:
        self._audio_output.setVolume(max(0.0, min(1.0, value_0_100 / 100.0)))

    def seek(self, position_ms: int) -> None:
        self._player.setPosition(max(0, position_ms))

    def set_repeat_mode(self, mode: RepeatMode) -> None:
        self._repeat_mode = mode

    def set_shuffle(self, enabled: bool) -> None:
        self._shuffle_enabled = enabled

    def _load_current_and_play(self) -> None:
        track = self.current_track
        if not track:
            return
        self._player.setSource(QUrl.fromLocalFile(str(track.path)))
        self._player.play()
        self.track_changed.emit(track)

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return

        if self._repeat_mode == RepeatMode.TRACK:
            self._load_current_and_play()
            return

        self.next()
