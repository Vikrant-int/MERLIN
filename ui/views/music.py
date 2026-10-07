"""Music page: queue over `musicLibrary`, with real Windows volume control.

The backend's only playback capability is "open this URL and say the title",
so the UI never pretends to know the browser's position or state: Previous
and Next move MERLIN's own queue, pause is handed to the Windows media key,
and the slider drives Core Audio system volume.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..components.common import Card, EmptyState, IconButton
from ..components.icons import icon
from services import system_audio
from .base import Page


class MusicView(Page):
    def __init__(self, state, navigate, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state
        self._navigate = navigate
        self._service = state.music
        self._muted = False

        self.add_header(
            "Music",
            "Your library from musicLibrary.py. MERLIN opens a track in "
            "your browser and reads the title aloud.",
        )

        # ---- now playing ----------------------------------------------------
        now = Card()
        now_layout = QVBoxLayout(now)
        now_layout.setContentsMargins(20, 17, 20, 19)
        now_layout.setSpacing(14)

        eyebrow = QLabel("NOW PLAYING")
        eyebrow.setObjectName("Eyebrow")
        now_layout.addWidget(eyebrow)

        self._track = QLabel("Nothing selected")
        self._track.setObjectName("H2")
        self._track.setWordWrap(True)
        now_layout.addWidget(self._track)

        self._note = QLabel(
            "Playback happens in your browser, so pause and volume are "
            "handled through Windows."
        )
        self._note.setObjectName("Muted")
        self._note.setWordWrap(True)
        now_layout.addWidget(self._note)

        transport = QHBoxLayout()
        transport.setSpacing(9)
        transport.addStretch(1)

        self._previous = IconButton("prev", "#E8ECF4", 17, 42)
        self._previous.setToolTip("Previous track in MERLIN's queue")
        self._previous.clicked.connect(self._service.previous)
        transport.addWidget(self._previous)

        self._play = QPushButton("Play")
        self._play.setObjectName("PrimaryButton")
        self._play.setMinimumWidth(132)
        self._play.clicked.connect(self._play_current)
        transport.addWidget(self._play)

        self._next = IconButton("next", "#E8ECF4", 17, 42)
        self._next.setToolTip("Next track in MERLIN's queue")
        self._next.clicked.connect(self._service.next)
        transport.addWidget(self._next)

        transport.addSpacing(16)

        self._pause = IconButton("pause", "#E8ECF4", 16, 42)
        self._pause.setToolTip("Pause or resume whatever is playing "
                               "(Windows media key)")
        self._pause.clicked.connect(self._toggle_playback)
        transport.addWidget(self._pause)

        transport.addStretch(1)
        now_layout.addLayout(transport)

        # ---- volume -----------------------------------------------------------
        volume_row = QHBoxLayout()
        volume_row.setSpacing(11)
        volume_icon = QLabel()
        volume_icon.setPixmap(icon("volume", "#9AA4B8", 16))
        volume_row.addWidget(volume_icon)

        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setFixedWidth(220)
        self._volume.valueChanged.connect(self._on_volume)
        self._volume.setToolTip("System volume")
        volume_row.addWidget(self._volume)

        self._volume_value = QLabel("—")
        self._volume_value.setObjectName("Muted")
        self._volume_value.setFixedWidth(44)
        volume_row.addWidget(self._volume_value)

        self._mute = QPushButton("Mute")
        self._mute.clicked.connect(self._toggle_mute)
        volume_row.addWidget(self._mute)

        volume_row.addStretch(1)
        now_layout.addLayout(volume_row)

        self._volume_unavailable = QLabel(
            "System volume isn't available on this device."
        )
        self._volume_unavailable.setObjectName("DangerText")
        self._volume_unavailable.hide()
        now_layout.addWidget(self._volume_unavailable)

        self.layout.addWidget(now)

        # ---- library ------------------------------------------------------------
        library = Card()
        library_layout = QVBoxLayout(library)
        library_layout.setContentsMargins(20, 17, 20, 19)
        library_layout.setSpacing(12)

        title_row = QHBoxLayout()
        library_title = QLabel("Library")
        library_title.setObjectName("H3")
        title_row.addWidget(library_title)
        title_row.addStretch(1)
        count = QLabel("")
        count.setObjectName("Muted")
        self._count = count
        title_row.addWidget(count)
        library_layout.addLayout(title_row)

        self._list = QListWidget()
        self._list.setMinimumHeight(150)
        self._list.itemClicked.connect(self._on_item)
        library_layout.addWidget(self._list)

        self._empty = EmptyState(
            "No tracks yet.",
            "Add entries to musicLibrary.py and they will appear here.",
        )
        library_layout.addWidget(self._empty)

        self.layout.addWidget(library, 1)

        # ---- wiring ------------------------------------------------------------
        self._service.currentChanged.connect(self._on_current)
        self._reload()
        self._play.setEnabled(bool(self._service.tracks))
        self._init_volume()

    # -- library --------------------------------------------------------------
    def _reload(self) -> None:
        tracks = self._service.tracks
        self._list.clear()
        for position, (name, _url) in enumerate(tracks):
            item = QListWidgetItem(f"   {position + 1}.  {name}")
            item.setToolTip(_url)
            self._list.addItem(item)
        self._empty.setVisible(not tracks)
        self._list.setVisible(bool(tracks))
        self._count.setText(f"{len(tracks)} track(s)")

    def _on_item(self, item: QListWidgetItem) -> None:
        self._service.play(self._list.row(item))

    def _play_current(self) -> None:
        index = self._service.position
        if index < 0:
            if self._service.tracks:
                index = 0
            else:
                return
        self._service.play(index)

    def _on_current(self, index: int) -> None:
        title = self._service.title_at(index)
        if index < 0 or not title:
            self._track.setText("Nothing selected")
            self._play.setEnabled(bool(self._service.tracks))
            if 0 <= self._list.currentRow() < self._list.count():
                self._list.setCurrentRow(-1)
            return
        self._track.setText(title)
        self._play.setEnabled(True)
        if self._list.currentRow() != index:
            self._list.setCurrentRow(index)
        self._state.log_activity("music", title)

    # -- playback / volume ----------------------------------------------------
    def _toggle_playback(self) -> None:
        if system_audio.toggle_playback():
            self._note.setText(
                "Sent a pause/resume command to Windows for whatever is "
                "currently playing."
            )
        else:
            self._note.setText(
                "Windows wouldn't accept a media command — use the player "
                "controls in your browser."
            )

    def _init_volume(self) -> None:
        if not system_audio.available():
            self._volume.hide()
            self._volume_value.hide()
            self._mute.hide()
            self._volume_unavailable.setText(system_audio.reason())
            self._volume_unavailable.show()
            return
        level = system_audio.get_volume()
        if level is None:
            self._volume.hide()
            self._volume_value.hide()
            self._mute.hide()
            self._volume_unavailable.setText(system_audio.reason())
            self._volume_unavailable.show()
            return
        self._volume.blockSignals(True)
        self._volume.setValue(int(round(level * 100)))
        self._volume.blockSignals(False)
        self._volume_value.setText(f"{int(round(level * 100))}%")
        self._muted = bool(system_audio.get_mute())
        self._mute.setText("Unmute" if self._muted else "Mute")

    def _on_volume(self, value: int) -> None:
        if system_audio.set_volume(value / 100.0):
            self._volume_value.setText(f"{value}%")
            if self._muted:
                self._muted = False
                system_audio.set_mute(False)
                self._mute.setText("Mute")

    def _toggle_mute(self) -> None:
        target = not self._muted
        if system_audio.set_mute(target):
            self._muted = target
            self._mute.setText("Unmute" if target else "Mute")

    def on_page_enter(self, payload: dict | None = None) -> None:
        if payload and payload.get("autoplay"):
            if self._service.position < 0 and self._service.tracks:
                self._service.play(0)
