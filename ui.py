"""
ui.py
------
Spotify-faithful UI for the Music Player.

Layout mirrors Spotify desktop:
  ┌──────────────────────────────────────────┐
  │  Sidebar (220px) │  Main content (stack) │
  │                  │  ┌──────────────────┐ │
  │  Nav + playlists │  │  Top bar (search)│ │
  │                  │  │  Page content    │ │
  │                  │  └──────────────────┘ │
  ├──────────────────────────────────────────┤
  │  Now-playing bar (90px, full width)      │
  └──────────────────────────────────────────┘
"""

from __future__ import annotations

import os

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
)

# ─────────────────────────────────────────────
# Design tokens — Spotify palette
# ─────────────────────────────────────────────
_BG_BASE      = "#121212"   # page background
_BG_SIDEBAR   = "#000000"   # left sidebar
_BG_CARD      = "#181818"   # card / hover surface
_BG_ELEVATED  = "#282828"   # slightly raised surfaces
_BG_PLAYER    = "#181818"   # bottom bar
_ACCENT       = "#1db954"   # Spotify green
_ACCENT_HOVER = "#1ed760"
_TEXT_PRIMARY = "#ffffff"
_TEXT_MUTED   = "#a7a7a7"
_TEXT_DIM     = "#6a6a6a"
_BORDER       = "#282828"

_FONT_FAMILY  = "Circular, Gotham, 'Segoe UI', sans-serif"
_FONT_MONO    = "'Courier New', monospace"

# ─────────────────────────────────────────────
# Reusable style snippets
# ─────────────────────────────────────────────

def _scroll_style() -> str:
    return f"""
        QScrollArea   {{ border: none; background: transparent; }}
        QScrollBar:vertical {{
            background: transparent; width: 8px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: #404040; border-radius: 4px; min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background: #606060; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """


def _slider_style(accent: str = _ACCENT) -> str:
    return f"""
        QSlider {{ background: transparent; }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: #535353;
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {accent};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {_TEXT_PRIMARY};
            width: 12px; height: 12px;
            border-radius: 6px;
            margin: -4px 0;
            visibility: hidden;
        }}
        QSlider:hover::handle:horizontal {{ visibility: visible; }}
        QSlider:hover::groove:horizontal  {{ height: 6px; }}
        QSlider:hover::sub-page:horizontal {{ border-radius: 3px; }}
    """


def _icon_btn_style(size: int, active_color: str = _TEXT_MUTED) -> str:
    return f"""
        QPushButton {{
            background: transparent;
            color: {_TEXT_MUTED};
            border: none;
            border-radius: {size // 2}px;
            font-size: {size // 2}px;
        }}
        QPushButton:hover   {{ color: {_TEXT_PRIMARY}; }}
        QPushButton:checked {{ color: {active_color};  }}
    """


def _nav_btn_style() -> str:
    return f"""
        QPushButton {{
            background: transparent;
            color: {_TEXT_MUTED};
            border: none;
            text-align: left;
            padding: 4px 8px;
            font-size: 14px;
            font-weight: 700;
            border-radius: 4px;
        }}
        QPushButton:hover   {{ color: {_TEXT_PRIMARY}; }}
        QPushButton:checked {{ color: {_TEXT_PRIMARY}; }}
    """


def _track_row_style() -> str:
    return f"""
        QPushButton {{
            background: transparent;
            color: {_TEXT_PRIMARY};
            border: none;
            border-radius: 4px;
            text-align: left;
        }}
        QPushButton:hover   {{ background: {_BG_ELEVATED}; }}
        QPushButton:checked {{ background: {_BG_ELEVATED};
                               border-left: 3px solid {_ACCENT}; }}
    """


def _bold_font(size: int, weight: int = 700) -> QtGui.QFont:
    f = QtGui.QFont()
    f.setFamily(_FONT_FAMILY)
    f.setPointSize(size)
    f.setWeight(QtGui.QFont.Weight(weight))
    return f


def _label(
    text: str = "",
    size: int = 13,
    color: str = _TEXT_PRIMARY,
    bold: bool = False,
) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setFont(_bold_font(size, 700 if bold else 400))
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


# ─────────────────────────────────────────────
# PlayerUI
# ─────────────────────────────────────────────

class PlayerUI:
    """
    Constructs the entire Spotify-style window.
    Call ``setup(main_window)`` once.
    """

    def setup(self, window: QtWidgets.QMainWindow) -> None:
        self._build_skeleton(window)
        self._build_sidebar()
        self._build_main_area()
        self._build_player_bar()
        self._finalise(window)

    # ══════════════════════════════════════════
    # Skeleton
    # ══════════════════════════════════════════

    def _build_skeleton(self, window: QtWidgets.QMainWindow) -> None:
        window.setObjectName("MainWindow")
        window.resize(1280, 800)
        window.setMinimumSize(960, 640)
        window.setStyleSheet(f"QMainWindow {{ background: {_BG_BASE}; }}")

        self._central = QtWidgets.QWidget(parent=window)
        self._central.setStyleSheet(f"background: {_BG_BASE};")
        window.setCentralWidget(self._central)

        # Outer: sidebar | content  ╌╌  stacked vertically with player bar
        self._outer = QtWidgets.QVBoxLayout(self._central)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        # Middle row: sidebar + main
        self._middle_row = QtWidgets.QHBoxLayout()
        self._middle_row.setContentsMargins(0, 0, 0, 0)
        self._middle_row.setSpacing(0)
        self._outer.addLayout(self._middle_row, stretch=1)

        # Build menu bar (minimal — Spotify has none, but keep for OS integration)
        self._build_menu_bar(window)

    def _build_menu_bar(self, window: QtWidgets.QMainWindow) -> None:
        bar = QtWidgets.QMenuBar(parent=window)
        bar.setStyleSheet(f"""
            QMenuBar {{ background: {_BG_SIDEBAR}; color: {_TEXT_MUTED};
                        font-size: 12px; padding: 0; }}
            QMenuBar::item:selected {{ background: {_BG_ELEVATED}; color: {_TEXT_PRIMARY}; }}
            QMenu {{ background: {_BG_CARD}; color: {_TEXT_PRIMARY};
                     border: 1px solid {_BORDER}; }}
            QMenu::item:selected {{ background: {_BG_ELEVATED}; }}
        """)

        playback = bar.addMenu("Playback")
        self.play_action  = playback.addAction("Play / Pause")
        self.pause_action = playback.addAction("Pause")
        playback.addSeparator()
        self.next_action  = playback.addAction("Next\tCtrl+Right")
        self.prev_action  = playback.addAction("Previous\tCtrl+Left")

        volume = bar.addMenu("Volume")
        self.vol_actions: dict[int, QtGui.QAction] = {}
        for level in (100, 80, 60, 40, 20, 0):
            label = "Mute" if level == 0 else str(level)
            self.vol_actions[level] = volume.addAction(label)

        # Legacy aliases
        self.action100 = self.vol_actions[100]
        self.action80  = self.vol_actions[80]
        self.action60  = self.vol_actions[60]
        self.action40  = self.vol_actions[40]
        self.action20  = self.vol_actions[20]
        self.action0   = self.vol_actions[0]

        window.setMenuBar(bar)

    # ══════════════════════════════════════════
    # Left sidebar  (Spotify-style)
    # ══════════════════════════════════════════

    def _build_sidebar(self) -> None:
        self.sidebar = QtWidgets.QWidget()
        self.sidebar.setFixedWidth(232)
        self.sidebar.setStyleSheet(f"QWidget {{ background: {_BG_SIDEBAR}; }}")

        layout = QtWidgets.QVBoxLayout(self.sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Logo area ────────────────────────────────
        logo_w = QtWidgets.QWidget()
        logo_w.setFixedHeight(64)
        logo_w.setStyleSheet(f"background: {_BG_SIDEBAR};")
        logo_layout = QtWidgets.QHBoxLayout(logo_w)
        logo_layout.setContentsMargins(24, 0, 24, 0)

        logo_icon = QtWidgets.QLabel("♫")
        logo_icon.setStyleSheet(f"color: {_TEXT_PRIMARY}; font-size: 28px;")
        logo_text = QtWidgets.QLabel("Music Player")
        logo_text.setFont(_bold_font(16, 700))
        logo_text.setStyleSheet(f"color: {_TEXT_PRIMARY};")
        logo_layout.addWidget(logo_icon)
        logo_layout.addWidget(logo_text)
        logo_layout.addStretch()
        layout.addWidget(logo_w)

        # ── Navigation ───────────────────────────────
        nav_w = QtWidgets.QWidget()
        nav_w.setStyleSheet(f"background: {_BG_SIDEBAR};")
        nav_layout = QtWidgets.QVBoxLayout(nav_w)
        nav_layout.setContentsMargins(8, 0, 8, 8)
        nav_layout.setSpacing(2)

        self.homeButton    = self._sidebar_nav_btn("🏠", "Home",        nav_layout)
        self.msearchButton = self._sidebar_nav_btn("🔍", "Search",      nav_layout)
        layout.addWidget(nav_w)

        # ── Library section ──────────────────────────
        lib_header = QtWidgets.QWidget()
        lib_header.setStyleSheet(f"background: {_BG_SIDEBAR};")
        lh = QtWidgets.QHBoxLayout(lib_header)
        lh.setContentsMargins(16, 12, 8, 4)

        lib_icon_btn = QtWidgets.QPushButton("⊞  Your Library")
        lib_icon_btn.setFont(_bold_font(13, 700))
        lib_icon_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_TEXT_MUTED};
                border: none; text-align: left; font-size: 13px;
            }}
            QPushButton:hover {{ color: {_TEXT_PRIMARY}; }}
        """)
        lib_icon_btn.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

        self.addFolderBtn = QtWidgets.QPushButton("＋")
        self.addFolderBtn.setFixedSize(28, 28)
        self.addFolderBtn.setToolTip("Add music folder")
        self.addFolderBtn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_TEXT_MUTED};
                border: none; border-radius: 14px;
                font-size: 18px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_BG_ELEVATED}; color: {_TEXT_PRIMARY}; }}
        """)
        lh.addWidget(lib_icon_btn)
        lh.addStretch()
        lh.addWidget(self.addFolderBtn)
        layout.addWidget(lib_header)

        # Library nav links
        lib_nav = QtWidgets.QWidget()
        lib_nav.setStyleSheet(f"background: {_BG_SIDEBAR};")
        lnl = QtWidgets.QVBoxLayout(lib_nav)
        lnl.setContentsMargins(8, 0, 8, 4)
        lnl.setSpacing(2)
        self.libraryButton = self._sidebar_nav_btn("📚", "Library",      lnl)
        self.playingButton = self._sidebar_nav_btn("▶",  "Now Playing",  lnl)
        layout.addWidget(lib_nav)

        # ── Divider ──────────────────────────────────
        div = QtWidgets.QFrame()
        div.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        div.setStyleSheet(f"color: {_BORDER};")
        div.setFixedHeight(1)
        layout.addWidget(div)
        layout.addStretch()

        # ── Mini now-playing in sidebar ───────────────
        mini = QtWidgets.QWidget()
        mini.setFixedHeight(72)
        mini.setStyleSheet(f"background: {_BG_SIDEBAR};")
        ml = QtWidgets.QHBoxLayout(mini)
        ml.setContentsMargins(12, 8, 12, 8)
        ml.setSpacing(10)

        self._sidebar_art = QtWidgets.QLabel("♪")
        self._sidebar_art.setFixedSize(48, 48)
        self._sidebar_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sidebar_art.setStyleSheet(
            f"background: {_BG_ELEVATED}; color: {_TEXT_MUTED}; "
            f"border-radius: 4px; font-size: 20px;"
        )

        mini_info = QtWidgets.QVBoxLayout()
        mini_info.setSpacing(2)
        self.sidebar_song_label   = _label("No song playing", 11, _TEXT_PRIMARY, bold=True)
        self.sidebar_artist_label = _label("",                10, _TEXT_MUTED)
        self.sidebar_song_label.setWordWrap(False)
        mini_info.addWidget(self.sidebar_song_label)
        mini_info.addWidget(self.sidebar_artist_label)

        ml.addWidget(self._sidebar_art)
        ml.addLayout(mini_info, stretch=1)
        layout.addWidget(mini)

        self._middle_row.addWidget(self.sidebar)

    def _sidebar_nav_btn(
        self, icon: str, label: str, layout: QtWidgets.QVBoxLayout
    ) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton(f"  {icon}  {label}")
        btn.setCheckable(True)
        btn.setMinimumHeight(40)
        btn.setFont(_bold_font(14, 700))
        btn.setStyleSheet(_nav_btn_style())
        btn.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
        layout.addWidget(btn)
        return btn

    # ══════════════════════════════════════════
    # Main content area
    # ══════════════════════════════════════════

    def _build_main_area(self) -> None:
        # Wrapper gives the rounded top-corners effect Spotify has
        wrapper = QtWidgets.QWidget()
        wrapper.setStyleSheet(f"background: {_BG_BASE};")
        wl = QtWidgets.QVBoxLayout(wrapper)
        wl.setContentsMargins(8, 8, 8, 0)
        wl.setSpacing(0)

        # Top navigation bar (back/fwd + page title area)
        self._topbar = self._build_topbar(wrapper)
        wl.addWidget(self._topbar)

        # Page stack
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {_BG_BASE};")
        wl.addWidget(self.stack, stretch=1)

        self._middle_row.addWidget(wrapper, stretch=1)

        self._build_home_page()
        self._build_search_page()
        self._build_library_page()
        self._build_lyrics_page()

    def _build_topbar(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget(parent=parent)
        bar.setFixedHeight(64)
        bar.setStyleSheet(f"background: {_BG_BASE};")
        bl = QtWidgets.QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 24, 0)
        bl.setSpacing(12)

        # Back / Forward
        for icon in ("◀", "▶"):
            btn = QtWidgets.QPushButton(icon)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(0,0,0,.7); color: {_TEXT_PRIMARY};
                    border: none; border-radius: 16px; font-size: 12px;
                }}
                QPushButton:hover {{ background: {_BG_ELEVATED}; }}
            """)
            bl.addWidget(btn)

        bl.addStretch()

        # User avatar pill
        user_pill = QtWidgets.QPushButton("  🎵  Local Player  ")
        user_pill.setFixedHeight(32)
        user_pill.setStyleSheet(f"""
            QPushButton {{
                background: {_BG_ELEVATED}; color: {_TEXT_PRIMARY};
                border: none; border-radius: 16px;
                font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background: #3a3a3a; }}
        """)
        bl.addWidget(user_pill)

        self.deviceOptions = QtWidgets.QComboBox()
        self.deviceOptions.setFixedHeight(28)
        self.deviceOptions.setStyleSheet(f"""
            QComboBox {{
                background: {_BG_ELEVATED}; color: {_TEXT_MUTED};
                border: none; border-radius: 14px;
                padding: 0 12px; font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {_BG_CARD}; color: {_TEXT_PRIMARY};
                selection-background-color: {_BG_ELEVATED};
                border: 1px solid {_BORDER};
            }}
        """)
        self.deviceOptions.addItem("Local Audio Output")
        bl.addWidget(self.deviceOptions)

        return bar

    # ──────────────────────────────────────────
    # Home page
    # ──────────────────────────────────────────

    def _build_home_page(self) -> None:
        page = QtWidgets.QWidget()
        page.setStyleSheet(f"background: {_BG_BASE};")
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Hero gradient header
        hero = QtWidgets.QWidget()
        hero.setFixedHeight(240)
        hero.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #1a5a3a, stop:1 #121212);"
        )
        hl = QtWidgets.QVBoxLayout(hero)
        hl.setContentsMargins(32, 32, 32, 24)
        hl.setSpacing(4)
        self.welcomeLabel = _label("Good evening", 32, _TEXT_PRIMARY, bold=True)
        sub = _label("Here's what we think you'll enjoy", 14, _TEXT_MUTED)
        hl.addStretch()
        hl.addWidget(self.welcomeLabel)
        hl.addWidget(sub)
        v.addWidget(hero)

        # Quick picks grid
        scroll = self._scrollable()
        inner  = scroll.widget()
        iv     = QtWidgets.QVBoxLayout(inner)
        iv.setContentsMargins(24, 24, 24, 24)
        iv.setSpacing(24)

        section_lbl = _label("Recommended for you", 22, _TEXT_PRIMARY, bold=True)
        iv.addWidget(section_lbl)

        self.recoLayout = QtWidgets.QVBoxLayout()
        self.recoLayout.setSpacing(4)
        iv.addLayout(self.recoLayout)
        iv.addStretch()

        v.addWidget(scroll, stretch=1)
        self.stack.addWidget(page)   # index 0

    # ──────────────────────────────────────────
    # Search page
    # ──────────────────────────────────────────

    def _build_search_page(self) -> None:
        page = QtWidgets.QWidget()
        page.setStyleSheet(f"background: {_BG_BASE};")
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Search bar header
        hdr = QtWidgets.QWidget()
        hdr.setFixedHeight(80)
        hdr.setStyleSheet(f"background: {_BG_BASE};")
        hl = QtWidgets.QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.setSpacing(12)

        self.searchText = QtWidgets.QLineEdit()
        self.searchText.setPlaceholderText("What do you want to listen to?")
        self.searchText.setFixedHeight(42)
        self.searchText.setStyleSheet(f"""
            QLineEdit {{
                background: {_TEXT_PRIMARY};
                color: #000;
                border: none;
                border-radius: 21px;
                padding: 0 20px;
                font-size: 14px;
            }}
        """)

        self.searchButton = QtWidgets.QPushButton("Search")
        self.searchButton.setFixedSize(90, 36)
        self.searchButton.setStyleSheet(f"""
            QPushButton {{
                background: {_TEXT_PRIMARY}; color: #000;
                border: none; border-radius: 18px;
                font-size: 13px; font-weight: 700;
            }}
            QPushButton:hover {{ background: #e0e0e0; }}
        """)

        hl.addWidget(self.searchText, stretch=1)
        hl.addWidget(self.searchButton)
        v.addWidget(hdr)

        scroll = self._scrollable()
        inner  = scroll.widget()
        iv     = QtWidgets.QVBoxLayout(inner)
        iv.setContentsMargins(24, 8, 24, 24)
        iv.setSpacing(4)
        self.searchResultsLayout = iv
        iv.addStretch()
        v.addWidget(scroll, stretch=1)

        self.stack.addWidget(page)   # index 1

    # ──────────────────────────────────────────
    # Library page
    # ──────────────────────────────────────────

    def _build_library_page(self) -> None:
        page = QtWidgets.QWidget()
        page.setStyleSheet(f"background: {_BG_BASE};")
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Library header
        hdr = QtWidgets.QWidget()
        hdr.setFixedHeight(120)
        hdr.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #3a2070, stop:1 #121212);"
        )
        hl = QtWidgets.QVBoxLayout(hdr)
        hl.setContentsMargins(32, 0, 32, 16)
        hl.addStretch()
        title = _label("Library", 28, _TEXT_PRIMARY, bold=True)
        self.trackCountLabel = _label("0 songs", 13, _TEXT_MUTED)
        hl.addWidget(title)
        hl.addWidget(self.trackCountLabel)
        v.addWidget(hdr)

        # Column header row
        col_hdr = QtWidgets.QWidget()
        col_hdr.setFixedHeight(36)
        col_hdr.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {_BORDER};"
        )
        ch = QtWidgets.QHBoxLayout(col_hdr)
        ch.setContentsMargins(16, 0, 16, 0)
        ch.setSpacing(0)

        def _col(txt: str, w: int | None = None, align=Qt.AlignmentFlag.AlignLeft) -> None:
            lbl = _label(txt, 11, _TEXT_DIM)
            lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            if w:
                lbl.setFixedWidth(w)
            else:
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            ch.addWidget(lbl)

        _col("#",  28)
        _col("",   52)   # art placeholder
        _col("Title")
        _col("Artist", 180)
        _col("Album",  180)
        _col("⏱",      60, Qt.AlignmentFlag.AlignRight)
        v.addWidget(col_hdr)

        # Track list
        scroll = self._scrollable()
        inner  = scroll.widget()
        self.verticalLayout_22 = QtWidgets.QVBoxLayout(inner)
        self.verticalLayout_22.setContentsMargins(8, 8, 8, 8)
        self.verticalLayout_22.setSpacing(2)
        self.verticalLayout_22.addStretch()
        self.trackContainer = inner
        v.addWidget(scroll, stretch=1)

        self.stack.addWidget(page)   # index 2

    # ──────────────────────────────────────────
    # Lyrics page
    # ──────────────────────────────────────────

    def _build_lyrics_page(self) -> None:
        page = QtWidgets.QWidget()
        page.setStyleSheet("background: #1a1a2e;")
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        hdr = QtWidgets.QWidget()
        hdr.setFixedHeight(80)
        hdr.setStyleSheet("background: transparent;")
        hl = QtWidgets.QHBoxLayout(hdr)
        hl.setContentsMargins(32, 0, 32, 0)
        hl.addWidget(_label("Lyrics", 28, _TEXT_PRIMARY, bold=True),
                     alignment=Qt.AlignmentFlag.AlignBottom)
        v.addWidget(hdr)

        scroll = self._scrollable()
        scroll.setStyleSheet(scroll.styleSheet() + "background: transparent;")
        inner = scroll.widget()
        inner.setStyleSheet("background: transparent;")
        il = QtWidgets.QVBoxLayout(inner)
        il.setContentsMargins(48, 24, 48, 48)

        self.lyricsMain = QtWidgets.QLabel(
            "Select a song to play.\n\nLyrics will appear here if a .lrc file is found."
        )
        self.lyricsMain.setFont(_bold_font(18, 700))
        self.lyricsMain.setStyleSheet(f"color: {_TEXT_PRIMARY}; background: transparent;")
        self.lyricsMain.setWordWrap(True)
        self.lyricsMain.setAlignment(Qt.AlignmentFlag.AlignTop)
        il.addWidget(self.lyricsMain)
        il.addStretch()

        v.addWidget(scroll, stretch=1)
        self.stack.addWidget(page)   # index 3

    # ──────────────────────────────────────────
    # Shared scroll-area factory
    # ──────────────────────────────────────────

    def _scrollable(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(_scroll_style())
        inner = QtWidgets.QWidget()
        inner.setStyleSheet(f"background: {_BG_BASE};")
        scroll.setWidget(inner)
        return scroll

    # ══════════════════════════════════════════
    # Bottom now-playing bar  (like Spotify)
    # ══════════════════════════════════════════

    def _build_player_bar(self) -> None:
        bar = QtWidgets.QWidget()
        bar.setFixedHeight(90)
        bar.setStyleSheet(f"""
            QWidget {{
                background: {_BG_PLAYER};
                border-top: 1px solid {_BORDER};
            }}
        """)
        root = QtWidgets.QHBoxLayout(bar)
        root.setContentsMargins(16, 0, 16, 0)
        root.setSpacing(0)

        # ── Left: song info ───────────────────────
        left = QtWidgets.QHBoxLayout()
        left.setSpacing(12)

        self.albumArtLabel = QtWidgets.QLabel("♪")
        self.albumArtLabel.setFixedSize(56, 56)
        self.albumArtLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.albumArtLabel.setStyleSheet(
            f"background: {_BG_ELEVATED}; color: {_TEXT_MUTED}; "
            f"border-radius: 4px; font-size: 22px;"
        )

        song_col = QtWidgets.QVBoxLayout()
        song_col.setSpacing(2)
        self.songName   = _label("No song playing", 13, _TEXT_PRIMARY, bold=True)
        self.artistName = _label("",                11, _TEXT_MUTED)
        self.songName.setMaximumWidth(200)
        self.artistName.setMaximumWidth(200)
        song_col.addWidget(self.songName)
        song_col.addWidget(self.artistName)

        # Heart button
        self._heart_btn = QtWidgets.QPushButton("♡")
        self._heart_btn.setFixedSize(32, 32)
        self._heart_btn.setCheckable(True)
        self._heart_btn.setStyleSheet(_icon_btn_style(32, _ACCENT))

        left.addWidget(self.albumArtLabel)
        left.addLayout(song_col)
        left.addWidget(self._heart_btn)
        left.addStretch()

        # ── Centre: playback controls ─────────────
        centre = QtWidgets.QVBoxLayout()
        centre.setSpacing(6)
        centre.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        ctrl_row = QtWidgets.QHBoxLayout()
        ctrl_row.setSpacing(8)
        ctrl_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.shuffleButton   = self._player_icon_btn("⇄",  28)
        self.shuffleButton.setCheckable(True)
        self.prevSong        = self._player_icon_btn("⏮",  32)
        self.pausePlayButton = self._player_play_btn("▶")
        self.nextSong        = self._player_icon_btn("⏭",  32)
        # BUG FIX: set the initial repeat icon directly (no-repeat state = "⇁")
        self.repeatButton    = self._player_icon_btn("⇁", 28)
        self.repeatButton.setCheckable(True)

        for w in (self.shuffleButton, self.prevSong,
                  self.pausePlayButton, self.nextSong, self.repeatButton):
            ctrl_row.addWidget(w)

        # Progress row
        prog_row = QtWidgets.QHBoxLayout()
        prog_row.setSpacing(8)
        self.currentTimeLabel = _label("0:00", 11, _TEXT_MUTED)
        self.totalTimeLabel   = _label("0:00", 11, _TEXT_MUTED)
        self.progressSlider   = QSlider(Qt.Orientation.Horizontal)
        self.progressSlider.setRange(0, 100)
        self.progressSlider.setValue(0)
        self.progressSlider.setFixedWidth(480)
        self.progressSlider.setStyleSheet(_slider_style())
        prog_row.addWidget(self.currentTimeLabel)
        prog_row.addWidget(self.progressSlider, stretch=1)
        prog_row.addWidget(self.totalTimeLabel)

        centre.addLayout(ctrl_row)
        centre.addLayout(prog_row)

        # ── Right: volume + extras ────────────────
        right = QtWidgets.QHBoxLayout()
        right.setSpacing(8)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.lyricsSong  = self._player_icon_btn("📝", 28)
        self.lyricsSong.setToolTip("Lyrics")
        self._queue_btn  = self._player_icon_btn("☰",  28)
        vol_icon         = _label("🔉", 14, _TEXT_MUTED)
        self.volSlider   = QSlider(Qt.Orientation.Horizontal)
        self.volSlider.setRange(0, 100)
        self.volSlider.setValue(70)
        self.volSlider.setFixedWidth(100)
        self.volSlider.setStyleSheet(_slider_style(_TEXT_PRIMARY))

        right.addStretch()
        right.addWidget(self.lyricsSong)
        right.addWidget(self._queue_btn)
        right.addWidget(vol_icon)
        right.addWidget(self.volSlider)

        # Assemble bar (equal thirds)
        root.addLayout(left,   stretch=3)
        root.addLayout(centre, stretch=4)
        root.addLayout(right,  stretch=3)

        self._outer.addWidget(bar)

    def _player_icon_btn(self, icon: str, size: int) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton(icon)
        btn.setFixedSize(size, size)
        btn.setStyleSheet(_icon_btn_style(size))
        btn.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
        return btn

    def _player_play_btn(self, icon: str) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton(icon)
        btn.setFixedSize(40, 40)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_TEXT_PRIMARY};
                color: #000;
                border: none;
                border-radius: 20px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #e0e0e0; transform: scale(1.05); }}
            QPushButton:pressed {{ background: #c0c0c0; }}
        """)
        btn.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
        return btn

    # ══════════════════════════════════════════
    # Finalise
    # ══════════════════════════════════════════

    def _finalise(self, window: QtWidgets.QMainWindow) -> None:
        # Now-playing page is gone — the bar IS the now-playing surface.
        # Map playingButton → home (index 0) so it still works if clicked.
        self.stack.setCurrentIndex(0)
        self.homeButton.setChecked(True)

        # Page indices used by player.py navigate():
        #   0 = Home, 1 = Search, 2 = Library, 3 = Lyrics
        # (No separate "Now Playing" page — controls live in bottom bar)
