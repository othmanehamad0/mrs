"""
player.py
----------
Application controller for the Music Player.

Responsibilities:
  - Manage playback state (Pygame mixer)
  - Wire UI signals to actions
  - Maintain playlist and library persistence
  - Delegate recommendations to RecommendationModel
  - Extract and display metadata / album art
"""

from __future__ import annotations

import logging
import os
import random
import sys
from pathlib import Path
from typing import Optional

import mutagen
import pygame
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from recommendation_model import RecommendationModel
from ui import PlayerUI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".flac", ".wav", ".ogg", ".m4a"}
)
TICK_INTERVAL_MS = 500          # playback timer resolution
DEFAULT_VOLUME   = 70           # 0–100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_duration(seconds: float) -> str:
    """Convert seconds to ``m:ss`` string."""
    if seconds < 0:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def sanitize_filename(name: str) -> str:
    """Replace filesystem-unsafe characters with underscores."""
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "_")
    return "".join(c for c in name if c.isalnum() or c in " _-").strip() or "unknown"


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

_TAG_LOOKUPS: dict[str, list[str]] = {
    "title":  ["title",  "TIT2", "\xa9nam"],
    "artist": ["artist", "TPE1", "\xa9ART"],
    "album":  ["album",  "TALB", "\xa9alb"],
}


def _first_tag(audio, keys: list[str]) -> str:
    for key in keys:
        try:
            val = audio.get(key)
            if val:
                return str(val[0]) if isinstance(val, list) else str(val)
        except Exception:
            continue
    return ""


def get_song_metadata(path: str) -> dict:
    """Return a dict with title, artist, album, duration, path."""
    stem = os.path.splitext(os.path.basename(path))[0]
    meta = {
        "title": stem,
        "artist": "Unknown Artist",
        "album": "Unknown Album",
        "duration": 0.0,
        "path": path,
    }
    try:
        audio = mutagen.File(path)
        if audio is None:
            return meta
        for field_name, keys in _TAG_LOOKUPS.items():
            value = _first_tag(audio, keys)
            if value:
                meta[field_name] = value
        if hasattr(audio, "info"):
            meta["duration"] = getattr(audio.info, "length", 0.0)
    except Exception as exc:
        logger.warning("Metadata read failed for %s: %s", path, exc)
    return meta


# ---------------------------------------------------------------------------
# Main window / controller
# ---------------------------------------------------------------------------

class MusicPlayer(QMainWindow):
    """
    Top-level application window.

    Inherits QMainWindow and delegates all widget construction to
    ``PlayerUI``, keeping layout concerns separate from logic.
    """

    def __init__(self, parent: Optional[QMainWindow] = None) -> None:
        super().__init__(parent)

        # ---- Build UI -------------------------------------------------------
        self._ui = PlayerUI()
        self._ui.setup(self)

        # ---- Directories ----------------------------------------------------
        base = Path(__file__).resolve().parent
        self._album_art_dir = base / "album_art"
        self._playlists_dir = base / "playlists"
        self._album_art_dir.mkdir(exist_ok=True)
        self._playlists_dir.mkdir(exist_ok=True)

        # ---- Music folder ---------------------------------------------------
        self._music_folder = Path(
            r"C:\Users\one\Downloads\music-recommendation-system-refactored (1)\data"
        )

        # ---- Pygame mixer ---------------------------------------------------
        pygame.mixer.init()

        # ---- Playback state -------------------------------------------------
        self._playlist: list[str]   = []
        self._current_index: int    = -1
        self._is_playing: bool      = False
        self._is_paused: bool       = False
        # BUG FIX: track seek_offset separately so that get_pos() (which is
        # relative to the last play() call) gives correct absolute position.
        self._seek_offset_s: float  = 0.0
        self._current_pos_s: float  = 0.0
        self._song_duration_s: float = 0.0
        self._volume: int           = DEFAULT_VOLUME
        self._repeat_mode: str      = "none"   # none | one | all
        self._shuffle: bool         = False

        pygame.mixer.music.set_volume(self._volume / 100)

        # ---- Recommendation model -------------------------------------------
        csv_path = self._music_folder / "data_w_genres.csv"
        self._model = RecommendationModel(
            csv_path=str(csv_path) if csv_path.exists() else None
        )

        # ---- Timers ---------------------------------------------------------
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

        # ---- Wire signals ---------------------------------------------------
        self._connect_signals()

        # ---- Initial state --------------------------------------------------
        self._update_greeting()
        self._load_library()
        self._ui.deviceOptions.clear()
        self._ui.deviceOptions.addItem("Local Audio Output")
        self._timer.start()

    # ==========================================================================
    # Signal wiring
    # ==========================================================================

    def _connect_signals(self) -> None:
        ui = self._ui

        # Navigation — page indices: 0=Home 1=Search 2=Library 3=Lyrics
        ui.homeButton.clicked.connect(lambda: self._navigate(0))
        ui.msearchButton.clicked.connect(lambda: self._navigate(1))
        ui.libraryButton.clicked.connect(lambda: self._navigate(2))
        # BUG FIX: playingButton maps to Library (index 2), not a separate page
        ui.playingButton.clicked.connect(lambda: self._navigate(2))
        ui.lyricsSong.clicked.connect(lambda: self._navigate(3))

        # Playback controls
        ui.pausePlayButton.clicked.connect(self._toggle_play_pause)
        ui.nextSong.clicked.connect(self._next_track)
        ui.prevSong.clicked.connect(self._prev_track)
        ui.shuffleButton.toggled.connect(self._set_shuffle)
        ui.repeatButton.clicked.connect(self._cycle_repeat)
        ui.volSlider.valueChanged.connect(self._on_volume_changed)
        ui.progressSlider.sliderMoved.connect(self._on_seek)

        # Library
        ui.addFolderBtn.clicked.connect(self._prompt_add_folder)

        # Search
        ui.searchButton.clicked.connect(self._search)
        ui.searchText.returnPressed.connect(self._search)

        # Menu bar
        ui.play_action.triggered.connect(self._toggle_play_pause)
        ui.pause_action.triggered.connect(self._toggle_play_pause)
        ui.next_action.triggered.connect(self._next_track)
        ui.prev_action.triggered.connect(self._prev_track)
        for level, action in ui.vol_actions.items():
            action.triggered.connect(lambda _, v=level: self._set_volume(v))

    # ==========================================================================
    # Navigation
    # ==========================================================================

    def _navigate(self, index: int) -> None:
        self._ui.stack.setCurrentIndex(index)
        # BUG FIX: lyrics page (index 3) has no corresponding nav button,
        # so only update buttons for indices 0-2 to avoid index errors.
        nav_btns = [
            self._ui.homeButton,
            self._ui.msearchButton,
            self._ui.libraryButton,
        ]
        for i, btn in enumerate(nav_btns):
            btn.setChecked(i == index)

    # ==========================================================================
    # Greeting
    # ==========================================================================

    def _update_greeting(self) -> None:
        from datetime import datetime
        hour = datetime.now().hour
        part = (
            "morning"   if hour < 12 else
            "afternoon" if hour < 17 else
            "evening"   if hour < 21 else
            "night"
        )
        self._ui.welcomeLabel.setText(f"Good {part}!")

    # ==========================================================================
    # Library management
    # ==========================================================================

    def _library_file(self) -> Path:
        return self._playlists_dir / "library.txt"

    def _load_library(self) -> None:
        """Load saved library or prompt the user to add a folder."""
        lib_file = self._library_file()
        if lib_file.exists():
            paths = [
                line.strip()
                for line in lib_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            # Silently drop stale paths
            self._playlist = [p for p in paths if os.path.isfile(p)]
            if self._playlist:
                self._refresh_library_view()
                self._refresh_recommendations()
                return

        # First run — auto-scan the configured music folder
        if self._music_folder.exists():
            self._scan_folder(str(self._music_folder))
        else:
            reply = QMessageBox.question(
                self, "Music Library",
                "No library found.\nWould you like to select a music folder?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._prompt_add_folder()

    def _prompt_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Music Folder", os.path.expanduser("~")
        )
        if folder:
            self._scan_folder(folder)

    def _scan_folder(self, folder: str) -> None:
        found: list[str] = []
        for root, _, files in os.walk(folder):
            for fname in files:
                if Path(fname).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                    found.append(os.path.join(root, fname))

        if not found:
            QMessageBox.warning(
                self, "No Music Found",
                "No supported audio files found in the selected folder.",
            )
            return

        # Merge without duplicates, preserving order
        existing = set(self._playlist)
        self._playlist.extend(p for p in found if p not in existing)
        self._save_library()
        self._refresh_library_view()
        self._refresh_recommendations()
        QMessageBox.information(
            self, "Scan Complete",
            f"Added {len(found)} songs.  Library total: {len(self._playlist)}",
        )

    def _save_library(self) -> None:
        try:
            self._library_file().write_text(
                "\n".join(self._playlist), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Could not save library: %s", exc)

    # ==========================================================================
    # Library / track list rendering
    # ==========================================================================

    def _clear_layout(self, layout: QtWidgets.QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _refresh_library_view(self) -> None:
        layout = self._ui.verticalLayout_22
        self._clear_layout(layout)

        for idx, path in enumerate(self._playlist):
            meta = get_song_metadata(path)
            btn  = self._make_track_button(idx, meta, layout.parentWidget())
            layout.addWidget(btn)

        layout.addStretch()
        self._ui.trackCountLabel.setText(f"{len(self._playlist)} songs")

    def _make_track_button(
        self,
        idx: int,
        meta: dict,
        parent: QtWidgets.QWidget,
    ) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton(parent=parent)
        btn.setMinimumHeight(52)
        btn.setMaximumHeight(52)
        btn.setCheckable(True)
        btn.setStyleSheet(self._track_row_style())

        row = QtWidgets.QHBoxLayout(btn)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(12)

        num = QtWidgets.QLabel(str(idx + 1))
        num.setFixedWidth(28)
        num.setStyleSheet("color: #888; font-size: 12px;")

        art_label = QtWidgets.QLabel()
        art_label.setFixedSize(38, 38)
        art_path = self._extract_album_art(meta["path"], meta["title"])
        if art_path and os.path.exists(art_path):
            px = QPixmap(art_path).scaled(
                38, 38,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            art_label.setPixmap(px)
        else:
            art_label.setText("♪")
            art_label.setStyleSheet("color: #888; font-size: 18px;")
        art_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        title_lbl  = self._elided_label(meta["title"],  200)
        artist_lbl = self._elided_label(meta["artist"], 160, muted=True)
        album_lbl  = self._elided_label(meta["album"],  160, muted=True)
        dur_lbl    = QtWidgets.QLabel(format_duration(meta["duration"]))
        dur_lbl.setStyleSheet("color: #888; font-size: 12px;")
        dur_lbl.setFixedWidth(50)
        dur_lbl.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        row.addWidget(num)
        row.addWidget(art_label)
        row.addWidget(title_lbl, 3)
        row.addWidget(artist_lbl, 2)
        row.addWidget(album_lbl, 2)
        row.addWidget(dur_lbl)

        btn.clicked.connect(lambda _checked, i=idx: self._play_song(i))
        return btn

    @staticmethod
    def _elided_label(text: str, max_width: int, muted: bool = False) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setMaximumWidth(max_width)
        color = "#b3b3b3" if muted else "#fff"
        lbl.setStyleSheet(f"color: {color}; font-size: 13px;")
        return lbl

    @staticmethod
    def _track_row_style() -> str:
        return """
            QPushButton {
                background: transparent;
                color: #fff;
                border: none;
                border-radius: 4px;
                text-align: left;
            }
            QPushButton:hover  { background: #282828; }
            QPushButton:checked { background: #333; border-left: 3px solid #1db954; }
        """

    # ==========================================================================
    # Album art extraction
    # ==========================================================================

    def _extract_album_art(self, song_path: str, title: str) -> Optional[str]:
        safe_name = sanitize_filename(title)
        art_path  = str(self._album_art_dir / f"{safe_name}.png")

        if os.path.exists(art_path):
            return art_path

        try:
            audio = mutagen.File(song_path)

            # FLAC / OGG — Vorbis picture block
            if hasattr(audio, "pictures"):
                for pic in audio.pictures:
                    if pic.type == 3:
                        with open(art_path, "wb") as f:
                            f.write(pic.data)
                        return art_path

            # MP4 / M4A
            if hasattr(audio, "tags") and audio.tags and "covr" in audio.tags:
                with open(art_path, "wb") as f:
                    f.write(bytes(audio.tags["covr"][0]))
                return art_path

            # ID3 APIC tag (MP3)
            if audio:
                for tag in audio.values():
                    if hasattr(tag, "data") and hasattr(tag, "type") and tag.type == 3:
                        with open(art_path, "wb") as f:
                            f.write(tag.data)
                        return art_path

            # BUG FIX: PIL import moved to where it's actually needed (folder cover)
            song_dir = os.path.dirname(song_path)
            for candidate in ("cover.jpg", "cover.png", "folder.jpg", "albumart.jpg"):
                cand_path = os.path.join(song_dir, candidate)
                if os.path.exists(cand_path):
                    from PIL import Image
                    img = Image.open(cand_path)
                    img.save(art_path)
                    return art_path

        except Exception as exc:
            logger.debug("Album art extraction failed for %s: %s", song_path, exc)

        return None

    # ==========================================================================
    # Playback
    # ==========================================================================

    def _play_song(self, index: int) -> None:
        if not (0 <= index < len(self._playlist)):
            return

        self._current_index    = index
        path                   = self._playlist[index]
        meta                   = get_song_metadata(path)
        self._song_duration_s  = meta["duration"]
        # BUG FIX: reset seek offset when starting a new song
        self._seek_offset_s    = 0.0
        self._current_pos_s    = 0.0

        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            self._is_playing = True
            self._is_paused  = False
        except Exception as exc:
            QMessageBox.warning(self, "Playback Error", f"Could not play:\n{exc}")
            return

        self._update_now_playing_ui(meta)
        self._refresh_recommendations(meta["title"])
        self._highlight_track(index)

    def _highlight_track(self, index: int) -> None:
        layout = self._ui.verticalLayout_22
        for i in range(layout.count()):
            item = layout.itemAt(i)
            # BUG FIX: skip stretch items (item.widget() is None for QSpacerItem)
            if item and item.widget() and isinstance(item.widget(), QtWidgets.QPushButton):
                item.widget().setChecked(False)
        item = layout.itemAt(index)
        if item and item.widget() and isinstance(item.widget(), QtWidgets.QPushButton):
            item.widget().setChecked(True)

    def _update_now_playing_ui(self, meta: dict) -> None:
        self._ui.songName.setText(meta["title"])
        self._ui.artistName.setText(meta["artist"])
        self._ui.pausePlayButton.setText("⏸")
        self._ui.totalTimeLabel.setText(format_duration(self._song_duration_s))

        # Sidebar mini-player
        self._ui.sidebar_song_label.setText(meta["title"])
        self._ui.sidebar_artist_label.setText(meta["artist"])

        # Album art — bottom bar + sidebar thumbnail
        art_path = self._extract_album_art(meta["path"], meta["title"])
        if art_path and os.path.exists(art_path):
            px_bar = QPixmap(art_path).scaled(
                56, 56,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self._ui.albumArtLabel.setPixmap(px_bar)

            px_side = QPixmap(art_path).scaled(
                48, 48,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self._ui._sidebar_art.setPixmap(px_side)
        else:
            self._ui.albumArtLabel.setText("♪")
            self._ui.albumArtLabel.setPixmap(QPixmap())
            self._ui._sidebar_art.setText("♪")
            self._ui._sidebar_art.setPixmap(QPixmap())

        self._load_lyrics(meta)

    def _toggle_play_pause(self) -> None:
        # BUG FIX: guard against empty playlist before trying to play index 0
        if self._current_index < 0:
            if self._playlist:
                self._play_song(0)
            return

        if self._is_playing and not self._is_paused:
            pygame.mixer.music.pause()
            self._is_paused = True
            self._ui.pausePlayButton.setText("▶")
        elif self._is_paused:
            pygame.mixer.music.unpause()
            self._is_paused = False
            self._ui.pausePlayButton.setText("⏸")

    def _next_track(self) -> None:
        if not self._playlist:
            return
        if self._shuffle:
            candidates = [i for i in range(len(self._playlist)) if i != self._current_index]
            next_idx = random.choice(candidates) if candidates else self._current_index
        else:
            next_idx = (self._current_index + 1) % len(self._playlist)
        self._play_song(next_idx)

    def _prev_track(self) -> None:
        if not self._playlist:
            return
        if self._current_pos_s > 3:
            self._play_song(self._current_index)
        else:
            prev_idx = (self._current_index - 1) % len(self._playlist)
            self._play_song(prev_idx)

    def _on_volume_changed(self, value: int) -> None:
        self._volume = value
        pygame.mixer.music.set_volume(value / 100)

    def _set_volume(self, value: int) -> None:
        self._ui.volSlider.setValue(value)

    def _on_seek(self, position: int) -> None:
        """Seek to the slider position (percentage)."""
        if self._song_duration_s > 0 and self._is_playing:
            target = (position / 100) * self._song_duration_s
            try:
                pygame.mixer.music.set_pos(target)
                self._seek_offset_s = target
                self._current_pos_s = target
            except pygame.error as exc:
                logger.warning("Seek failed: %s", exc)

    def _set_shuffle(self, enabled: bool) -> None:
        self._shuffle = enabled

    def _cycle_repeat(self) -> None:
        modes = ("none", "one", "all")
        self._repeat_mode = modes[(modes.index(self._repeat_mode) + 1) % len(modes)]
        icons = {"none": "⇁", "one": "🔂", "all": "🔁"}
        self._ui.repeatButton.setText(icons[self._repeat_mode])
        self._ui.repeatButton.setChecked(self._repeat_mode != "none")

    # ==========================================================================
    # Playback tick (timer)
    # ==========================================================================

    def _on_tick(self) -> None:
        if not self._is_playing or self._is_paused:
            return

        if pygame.mixer.music.get_busy():
            pos_ms = pygame.mixer.music.get_pos()
            if pos_ms >= 0:
                # BUG FIX: get_pos() is relative to the last play()/set_pos()
                # call — add seek_offset_s for the true absolute position.
                self._current_pos_s = self._seek_offset_s + pos_ms / 1000
            if self._song_duration_s > 0:
                progress = min(
                    int((self._current_pos_s / self._song_duration_s) * 100), 100
                )
                self._ui.progressSlider.setValue(progress)
                self._ui.currentTimeLabel.setText(format_duration(self._current_pos_s))
        else:
            # Song ended
            self._on_song_ended()

    def _on_song_ended(self) -> None:
        if self._repeat_mode == "one":
            self._play_song(self._current_index)
        elif self._repeat_mode == "all" or self._shuffle:
            self._next_track()
        elif 0 <= self._current_index < len(self._playlist) - 1:
            self._next_track()
        else:
            self._is_playing = False
            self._ui.pausePlayButton.setText("▶")

    # ==========================================================================
    # Lyrics
    # ==========================================================================

    def _load_lyrics(self, meta: dict) -> None:
        if self._current_index < 0:
            self._ui.lyricsMain.setText("No song playing.")
            return

        song_path = self._playlist[self._current_index]
        lrc_path  = Path(song_path).with_suffix(".lrc")

        if lrc_path.exists():
            try:
                self._ui.lyricsMain.setText(lrc_path.read_text(encoding="utf-8"))
                return
            except OSError:
                pass

        # Also try a file named after the title in the same directory
        title_lrc = Path(song_path).parent / f"{meta['title']}.lrc"
        if title_lrc.exists():
            try:
                self._ui.lyricsMain.setText(title_lrc.read_text(encoding="utf-8"))
                return
            except OSError:
                pass

        self._ui.lyricsMain.setText(
            f"No lyrics found for:\n{meta['title']}\nby {meta['artist']}\n\n"
            f"Add a .lrc file next to the audio file to display lyrics."
        )

    # ==========================================================================
    # Search
    # ==========================================================================

    def _search(self) -> None:
        query = self._ui.searchText.text().strip().lower()
        layout = self._ui.searchResultsLayout
        self._clear_layout(layout)

        if not query:
            layout.addStretch()
            return

        # BUG FIX: call get_song_metadata once per path (was called 3× per song
        # in the filter expression, causing redundant file reads)
        results: list[tuple[int, dict]] = []
        for path in self._playlist:
            meta = get_song_metadata(path)
            if (
                query in meta["title"].lower()
                or query in meta["artist"].lower()
                or query in meta["album"].lower()
            ):
                results.append((self._playlist.index(path), meta))

        if not results:
            no_res = QtWidgets.QLabel("No results found.")
            no_res.setStyleSheet("color: #888; font-size: 14px; padding: 16px;")
            layout.addWidget(no_res)
        else:
            for idx, meta in results:
                # BUG FIX: reuse already-fetched meta instead of calling
                # get_song_metadata again inside _make_track_button indirectly
                btn = self._make_track_button(idx, meta, layout.parentWidget())
                layout.addWidget(btn)

        layout.addStretch()

    # ==========================================================================
    # Recommendations
    # ==========================================================================

    def _refresh_recommendations(self, current_title: Optional[str] = None) -> None:
        reco_paths = self._model.get_recommendations(
            self._playlist, current_title, n=5
        )
        layout = self._ui.recoLayout
        self._clear_layout(layout)

        for path in reco_paths:
            meta = get_song_metadata(path)
            try:
                idx = self._playlist.index(path)
            except ValueError:
                continue
            btn = self._make_track_button(idx, meta, layout.parentWidget())
            layout.addWidget(btn)

        layout.addStretch()

    # ==========================================================================
    # Window lifecycle
    # ==========================================================================

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        reply = QMessageBox.question(
            self, "Exit", "Are you sure you want to exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._timer.stop()
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            # BUG FIX: also call pygame.quit() to fully release the pygame subsystem
            pygame.quit()
            event.accept()
        else:
            event.ignore()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Music Player")
    app.setStyle("Fusion")
    window = MusicPlayer()
    window.setWindowTitle("Music Player")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()