"""Voice page: device selection, live state and the listen controls."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..components.assistant_core import AssistantCore, OFFLINE
from ..components.common import Banner, Card, IconButton
from services.voice_service import (
    DISCONNECTED,
    ERROR,
    LISTENING,
    NO_MICROPHONE,
    PROCESSING,
    READY,
    open_sound_settings,
)
from .base import Page

_STATE_LABEL = {
    READY: "READY",
    LISTENING: "LISTENING",
    PROCESSING: "PROCESSING",
    NO_MICROPHONE: "NO MICROPHONE",
    DISCONNECTED: "DISCONNECTED",
    ERROR: "ERROR",
    "SPEAKING": "SPEAKING",
}

_STATE_TINT = {
    READY: "#4ADE80",
    LISTENING: "#5B8CFF",
    PROCESSING: "#7C6CFF",
    NO_MICROPHONE: "#FBBF24",
    DISCONNECTED: "#FBBF24",
    ERROR: "#FF6B7A",
    "SPEAKING": "#4FD1FF",
}


class VoiceView(Page):
    def __init__(self, state, navigate, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state
        self._navigate = navigate
        self._voice = state.voice

        self.add_header(
            "Voice",
            "MERLIN listens through the input device Windows reports as "
            "usable. Nothing is claimed to work until the backend says so.",
        )

        # ---- banner ------------------------------------------------------
        self._banner = Banner("error")
        self.layout.addWidget(self._banner)

        # ---- core ---------------------------------------------------------
        self._core = AssistantCore()
        self._core.setFixedSize(224, 224)
        core_row = QHBoxLayout()
        core_row.addStretch(1)
        core_row.addWidget(self._core, 0, Qt.AlignmentFlag.AlignCenter)
        core_row.addStretch(1)
        self.layout.addLayout(core_row)

        headline = QWidget()
        headline_layout = QVBoxLayout(headline)
        headline_layout.setContentsMargins(0, 0, 0, 0)
        headline_layout.setSpacing(6)

        self._state_pill = QLabel("READY")
        self._state_pill.setObjectName("Pill")
        self._state_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_pill.setFixedWidth(150)
        pill_row = QHBoxLayout()
        pill_row.addStretch(1)
        pill_row.addWidget(self._state_pill)
        pill_row.addStretch(1)
        headline_layout.addLayout(pill_row)

        self._status = QLabel(self._voice.status)
        self._status.setObjectName("H3")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        headline_layout.addWidget(self._status)

        self._device_line = QLabel("No device selected yet.")
        self._device_line.setObjectName("Muted")
        self._device_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline_layout.addWidget(self._device_line)

        center_row = QHBoxLayout()
        center_row.addStretch(1)
        center_row.addWidget(headline, 1)
        center_row.addStretch(1)
        self.layout.addLayout(center_row)

        self.layout.addSpacing(4)

        # ---- controls ------------------------------------------------------
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)
        controls_layout.addStretch(1)

        self._start = QPushButton("Start Listening")
        self._start.setObjectName("PrimaryButton")
        self._start.setMinimumWidth(170)
        self._start.clicked.connect(self._start_listening)
        controls_layout.addWidget(self._start)

        self._stop = QPushButton("Stop")
        self._stop.setObjectName("DangerButton")
        self._stop.setMinimumWidth(110)
        self._stop.clicked.connect(self._voice.stop)
        controls_layout.addWidget(self._stop)

        self._settings = QPushButton("Open Microphone Settings")
        self._settings.clicked.connect(self._open_settings)
        controls_layout.addWidget(self._settings)

        controls_layout.addStretch(1)
        self.layout.addWidget(controls)

        self.layout.addSpacing(6)

        # ---- device card ----------------------------------------------------
        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 17, 20, 19)
        card_layout.setSpacing(13)

        title_row = QHBoxLayout()
        title = QLabel("Input device")
        title.setObjectName("H3")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._probe = QPushButton("Test device")
        self._probe.clicked.connect(self._voice.probe)
        title_row.addWidget(self._probe)
        self._refresh = IconButton("refresh", "#9AA4B8", 16, 32)
        self._refresh.setToolTip("Re-scan input devices")
        self._refresh.clicked.connect(self._voice.refresh_devices)
        title_row.addWidget(self._refresh)
        card_layout.addLayout(title_row)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(10)
        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_combo)
        pick_row.addWidget(self._combo, 1)
        card_layout.addLayout(pick_row)

        self._probe_result = QLabel(
            "Press “Test device” to ask the backend whether any input "
            "actually carries live audio."
        )
        self._probe_result.setObjectName("Sub")
        self._probe_result.setWordWrap(True)
        card_layout.addWidget(self._probe_result)

        self.layout.addWidget(card)
        self.layout.addStretch(1)

        # ---- wiring ----------------------------------------------------------
        self._voice.stateChanged.connect(lambda *_: self._sync())
        self._voice.statusChanged.connect(lambda *_: self._sync())
        self._voice.devicesReady.connect(self._on_devices)
        self._voice.selectedChanged.connect(self._on_selected)
        self._voice.probeFinished.connect(self._on_probe)
        state.speech.busyChanged.connect(lambda *_: self._sync())
        state.coreStateChanged.connect(self._on_core)

        self._voice.refresh_devices()
        self._sync()

    # -- actions -------------------------------------------------------------
    def _start_listening(self) -> None:
        self._voice.start()
        self._sync()

    def _open_settings(self) -> None:
        if not open_sound_settings():
            self._banner.show_message(
                "Couldn't open Windows sound settings.",
                "Open it yourself from the taskbar search box.",
            )

    def _on_combo(self, index: int) -> None:
        if index < 0:
            return
        data = self._combo.itemData(index)
        if data is None:
            return
        self._voice.select_device(int(data))

    # -- results ------------------------------------------------------------
    def _on_devices(self, devices: object) -> None:
        devices = list(devices or [])
        current = self._voice.selected_index

        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem("Automatic (MERLIN chooses)", -1)
        for device in devices:
            suffix = "" if device.get("real", True) else "  — not a microphone"
            rate = f"  ·  {device['rate']} Hz" if device.get("rate") else ""
            self._combo.addItem(
                f"{device['name']}{rate}{suffix}", device["index"]
            )
        self._combo.blockSignals(False)

        if current == -1:
            self._combo.setCurrentIndex(0)
        else:
            for row in range(self._combo.count()):
                if self._combo.itemData(row) == current:
                    self._combo.setCurrentIndex(row)
                    break
        self._sync()

    def _on_selected(self, index: int, name: str) -> None:
        for row in range(self._combo.count()):
            if self._combo.itemData(row) == index:
                if self._combo.currentIndex() != row:
                    self._combo.blockSignals(True)
                    self._combo.setCurrentIndex(row)
                    self._combo.blockSignals(False)
                break
        self._sync()

    def _on_probe(self, ok: bool, message: str, level: float) -> None:
        self._probe_result.setText(message)
        if ok:
            self._probe_result.setStyleSheet("color:#4ADE80; font-size:13px;")
        else:
            self._probe_result.setStyleSheet("color:#FF6B7A; font-size:13px;")

    def _on_core(self, _state_name: str) -> None:
        self._sync()

    # -- presentation ----------------------------------------------------------
    def _display_state(self) -> str:
        if not self._state.backend_available:
            return OFFLINE
        if self._state.speech.busy:
            return "SPEAKING"
        return self._voice.state

    def _sync(self) -> None:
        display = self._display_state()
        self._state_pill.setText(_STATE_LABEL.get(display, display))
        self._state_pill.setStyleSheet(
            f"color:{_STATE_TINT.get(display, '#9AA4B8')};"
            f" border-color:{_STATE_TINT.get(display, '#1E2431')};"
        )
        self._core.set_state(
            OFFLINE if display == OFFLINE else (
                "SPEAKING" if display == "SPEAKING" else (
                    "LISTENING" if display == LISTENING else (
                        "THINKING" if display == PROCESSING else (
                            "ERROR" if display in (ERROR, NO_MICROPHONE,
                                                   DISCONNECTED) else "IDLE"
                        )
                    )
                )
            )
        )

        self._status.setText(self._voice.status)
        active = self._voice.listening
        self._start.setEnabled(not active and not self._voice.busy_audio)
        self._stop.setEnabled(active)

        if display in (NO_MICROPHONE, DISCONNECTED, ERROR):
            self._banner.show_message(self._voice.status)
        else:
            self._banner.clear()

        index = self._voice.selected_index
        count = len(self._voice.devices)
        if index >= 0:
            self._device_line.setText(
                f"Selected: {self._voice.selected_name}  ·  {count} detected"
            )
        elif count:
            self._device_line.setText(
                f"{count} input device(s) detected — automatic selection"
            )
        else:
            self._device_line.setText("No input devices detected yet.")

    def on_page_enter(self, payload: dict | None = None) -> None:
        if payload and payload.get("listen"):
            self._voice.start()
            self._sync()
        self._sync()
