# ZZvuk Music Player (PySide6 + MVVM)

Desktop music player built in Python with an object-oriented MVVM architecture.

## Features

- Library scanning from local folders
- Supported formats: MP3, WAV, FLAC, AAC, M4A
- Metadata display: Title, Artist, Album, Genre, Duration
- Album covers:
  - Embedded covers from tags (MP3/FLAC/M4A/AAC where available)
  - Fallback to `cover.jpg` / `cover.png` / `folder.jpg` in album folder
- Live filtering by track title or artist
- Playback controls: Play/Pause, Stop, Next, Previous
- Volume slider (0-100%)
- Seek slider with current and total time
- Repeat modes: Off, Repeat Track, Repeat Playlist
- Shuffle toggle
- List and grid library views

## Project structure (MVVM)

- `app/models/track.py`: domain model (`Track`)
- `app/services/library_scanner.py`: model/service layer for scanning and metadata extraction
- `app/services/audio_player.py`: playback service
- `app/viewmodels/main_viewmodel.py`: state + UI commands + filtering logic
- `app/views/main_window.py`: Qt widgets and bindings to ViewModel
- `main.py`: application entry point

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python3 main.py
```

## Notes

- Cover cache is stored under `~/.zzvuk/covers`.
- WAV metadata depends on file tagging quality.
