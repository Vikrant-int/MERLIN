"""Settings page: real toggles backed by a real store, plus honest status."""
from __future__ import annotations

import platform
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..components.common import StatusDot
from services.assistant_service import gemini_info
from services.news_service import news_info
from .base import Page


def _control_row(title: str, description: str, control) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(18)

    column = QVBoxLayout()
    column.setSpacing(3)
    label = QLabel(title)
    label.setObjectName("H3")
    column.addWidget(label)
    if description:
        detail = QLabel(description)
        detail.setObjectName("Sub")
        detail.setWordWrap(True)
        column.addWidget(detail)
    layout.addLayout(column, 1)
    layout.addWidget(control, 0, Qt.AlignmentFlag.AlignTop)
    return row


class StatusRow(QWidget):
    """A configured / not-configured line that can be answered again later.

    The credential information only becomes true once the backend has
    finished importing, so the row starts out saying ``Starting…`` and
    re-renders on ``AppState.backendReady`` instead of telling the user
    their key is missing while it simply has not looked yet.
    """

    def __init__(self, title: str, description: str, info: dict,
                 parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        column = QVBoxLayout()
        column.setSpacing(3)
        heading = QLabel(title)
        heading.setObjectName("H3")
        column.addWidget(heading)
        if description:
            sub = QLabel(description)
            sub.setObjectName("Sub")
            sub.setWordWrap(True)
            column.addWidget(sub)
        layout.addLayout(column, 1)

        right = QVBoxLayout()
        right.setSpacing(5)
        status = QHBoxLayout()
        status.setSpacing(7)
        status.addStretch(1)
        self._dot = StatusDot("", "#9AA4B8")
        self._pill = QLabel("Starting…")
        self._pill.setObjectName("Pill")
        status.addWidget(self._dot)
        status.addWidget(self._pill)
        right.addLayout(status)
        self._note = QLabel("")
        self._note.setObjectName("Muted")
        self._note.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._note.setWordWrap(True)
        right.addWidget(self._note)
        self._note.hide()
        layout.addLayout(right, 0)

        self.set_status(info)

    def set_status(self, info: dict) -> None:
        # Qt reads an 8-digit hex as #AARRGGBB, not #RRGGBBAA, so the border
        # colour has to be spelled out rather than derived with an alpha.
        if info.get("starting"):
            label, colour, edge = "Starting…", "#9AA4B8", "#2A2F3A"
        elif info.get("configured"):
            if info.get("detail"):
                label, colour, edge = "Needs attention", "#FF6B7A", "#3A1E22"
            else:
                label, colour, edge = "Configured", "#4ADE80", "#1E3A2A"
        else:
            label, colour, edge = "Not configured", "#FBBF24", "#3A2F1E"

        self._pill.setText(label)
        self._pill.setStyleSheet(f"color:{colour}; border-color:{edge};")
        self._dot.set_status("", colour)

        note = info.get("detail") or info.get("backend") or ""
        self._note.setText(str(note))
        self._note.setVisible(bool(note))


class SettingsView(Page):
    def __init__(self, state, navigate, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state
        self._navigate = navigate
        self._store = state.settings
        self._voice = state.voice

        self.add_header(
            "Settings",
            "Preferences are stored outside the repository, in "
            "%LOCALAPPDATA%\\MERLIN. API keys are read from the environment "
            "and are never shown or saved here.",
        )

        # ---- general ------------------------------------------------------
        self._section("GENERAL")

        self._startup = QCheckBox()
        self._startup.setChecked(
            bool(self._store.get("start_with_windows", False))
        )
        self._startup.toggled.connect(self._on_startup)
        self.layout.addWidget(_control_row(
            "Start with Windows",
            "Adds MERLIN to this user's startup list. Nothing is registered "
            "unless you switch this on.",
            self._startup,
        ))

        self._tray = QCheckBox()
        self._tray.setChecked(bool(self._store.get("minimize_to_tray", True)))
        self._tray.toggled.connect(
            lambda value: self._store.set("minimize_to_tray", value)
        )
        self.layout.addWidget(_control_row(
            "Minimise to tray",
            "Closing the window keeps MERLIN running in the system tray.",
            self._tray,
        ))

        self._notifications = QCheckBox()
        self._notifications.setChecked(
            bool(self._store.get("notifications", True))
        )
        self._notifications.toggled.connect(
            lambda value: self._store.set("notifications", value)
        )
        self.layout.addWidget(_control_row(
            "Notifications",
            "Allow tray notifications when MERLIN finishes something you "
            "asked for in the background.",
            self._notifications,
        ))

        theme = QComboBox()
        theme.addItem("Dark", "dark")
        theme.addItem("Light", "light")
        index = 0 if self._store.get("theme", "dark") == "dark" else 1
        theme.setCurrentIndex(index)
        theme.currentIndexChanged.connect(
            lambda i, box=theme: self._state.set_theme(box.itemData(i))
        )
        self.layout.addWidget(_control_row(
            "Theme",
            "Two palettes ship with MERLIN; no transparency effects, so it "
            "stays readable on any wallpaper.",
            theme,
        ))

        self._hotkey = QCheckBox()
        self._hotkey.setChecked(bool(self._store.get("hotkey", False)))
        self._hotkey.toggled.connect(self._on_hotkey)
        self.layout.addWidget(_control_row(
            "Global hotkey",
            "Ctrl+Alt+M brings MERLIN forward from anywhere in Windows. "
            "Off by default; if another app owns the combination MERLIN "
            "simply says so.",
            self._hotkey,
        ))

        self._hotkey_note = QLabel(state.hotkey.reason)
        self._hotkey_note.setObjectName("Muted")
        self._hotkey_note.setWordWrap(True)
        self.layout.addWidget(self._hotkey_note)

        self._startup_note = QLabel("")
        self._startup_note.setObjectName("DangerText")
        self._startup_note.setWordWrap(True)
        self.layout.addWidget(self._startup_note)

        self._separator()

        # ---- voice --------------------------------------------------------
        self._section("VOICE")

        self._microphone = QComboBox()
        self._microphone.currentIndexChanged.connect(self._on_mic)
        self.layout.addWidget(_control_row(
            "Microphone",
            "The Windows input MERLIN listens on. Automatic lets the backend "
            "run its own liveness checks.",
            self._microphone,
        ))

        wake = QCheckBox()
        wake.setChecked(bool(self._store.get("wake_word", True)))
        wake.toggled.connect(self._on_wake)
        self.layout.addWidget(_control_row(
            "Require the wake word",
            "When on, MERLIN waits for “Merlin” before acting, exactly like "
            "the command-line assistant.",
            wake,
        ))

        self._volume = self._slider(0, 100)
        self._volume.setValue(
            int(self._store.get("voice_volume", 100))
        )
        self._volume.valueChanged.connect(self._on_voice_volume)
        volume_widget, self._volume_label = self._slider_row(
            self._volume, f"{self._volume.value()}%"
        )
        self.layout.addWidget(_control_row(
            "Voice volume",
            "How loudly MERLIN speaks. This sets the Windows speech engine "
            "directly.",
            volume_widget,
        ))

        self._rate = self._slider(100, 300)
        self._rate.setValue(int(self._store.get("voice_rate", 200)))
        self._rate.valueChanged.connect(self._on_voice_rate)
        rate_widget, self._rate_label = self._slider_row(
            self._rate, str(self._rate.value())
        )
        self.layout.addWidget(_control_row(
            "Speech rate",
            "Words per minute for MERLIN's voice. 200 is the default.",
            rate_widget,
        ))

        self._separator()

        # ---- AI ------------------------------------------------------------
        self._section("AI")

        info = gemini_info()
        self._gemini_row = StatusRow(
            "Gemini",
            "Answers come from the Gemini API using GEMINI_API_KEY.",
            info,
        )
        self.layout.addWidget(self._gemini_row)

        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(18)
        model_layout.addWidget(QLabel("Model"))
        model_layout.addStretch(1)
        self._model_label = QLabel(info.get("model", ""))
        self._model_label.setObjectName("Muted")
        model_layout.addWidget(self._model_label)
        self.layout.addWidget(model_row)

        self._separator()

        # ---- news -----------------------------------------------------------
        self._section("NEWS")

        self._news_row = StatusRow(
            "News API",
            "Headlines come from NewsAPI using NEWS_API_KEY.",
            news_info(),
        )
        self.layout.addWidget(self._news_row)

        self._separator()

        # ---- about -----------------------------------------------------------
        self._section("ABOUT")

        about = QWidget()
        about_layout = QVBoxLayout(about)
        about_layout.setContentsMargins(0, 0, 0, 0)
        about_layout.setSpacing(7)

        name = QLabel(f"{APP_NAME} {APP_VERSION}")
        name.setObjectName("H2")
        about_layout.addWidget(name)

        tagline = QLabel(self._tagline())
        tagline.setObjectName("Sub")
        about_layout.addWidget(tagline)

        for key, value in (
            ("Python", platform.python_version()),
            ("Qt", self._qt_version()),
            ("Platform", f"{platform.system()} {platform.release()}"),
            ("Settings file", self._store.path),
        ):
            line = QWidget()
            line_layout = QHBoxLayout(line)
            line_layout.setContentsMargins(0, 2, 0, 2)
            line_layout.setSpacing(12)
            caption = QLabel(key)
            caption.setObjectName("Muted")
            caption.setFixedWidth(110)
            line_layout.addWidget(caption)
            value_label = QLabel(value)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            line_layout.addWidget(value_label, 1)
            about_layout.addWidget(line)

        self.layout.addWidget(about)
        self.layout.addStretch(1)

        # ---- wiring ------------------------------------------------------------
        self._state.backendReady.connect(self._on_backend_ready)
        self._voice.devicesReady.connect(self._on_devices)
        self._voice.selectedChanged.connect(self._on_selected)
        if self._voice.devices:
            self._on_devices(self._voice.devices)
        else:
            self._voice.refresh_devices()

    def _on_backend_ready(self) -> None:
        """The status rows were rendered before the backend finished."""
        try:
            info = gemini_info()
            self._gemini_row.set_status(info)
            self._model_label.setText(info.get("model", ""))
            self._news_row.set_status(news_info())
        except Exception:      # never let a status refresh break the page
            return

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def _tagline() -> str:
        from .. import APP_TAGLINE  # noqa: PLC0415

        return APP_TAGLINE

    @staticmethod
    def _qt_version() -> str:
        try:
            from PySide6 import __version__  # noqa: PLC0415

            return f"PySide6 {__version__}"
        except Exception:
            return "PySide6"

    def _section(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("Eyebrow")
        self.layout.addSpacing(6)
        self.layout.addWidget(label)

    def _separator(self) -> None:
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#1E2431;")
        self.layout.addSpacing(8)
        self.layout.addWidget(line)
        self.layout.addSpacing(4)

    @staticmethod
    def _slider(low: int, high: int) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setFixedWidth(190)
        return slider

    @staticmethod
    def _slider_row(slider: QSlider, suffix: str):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(slider)
        label = QLabel(suffix)
        label.setObjectName("Muted")
        label.setFixedWidth(48)
        layout.addWidget(label)
        return widget, label

    # -- handlers -----------------------------------------------------------------
    def _on_hotkey(self, value: bool) -> None:
        if value:
            ok = self._state.hotkey.enable(QApplication.instance())
            self._hotkey_note.setStyleSheet(
                "" if ok else "color:#FF6B7A; font-size:12px;"
            )
            self._hotkey_note.setText(self._state.hotkey.reason)
            if not ok:
                # Nothing is listening, so don't pretend the preference stuck.
                self._store.set("hotkey", False)
                self._hotkey.blockSignals(True)
                self._hotkey.setChecked(False)
                self._hotkey.blockSignals(False)
        else:
            self._state.hotkey.disable()
            self._hotkey_note.setStyleSheet("")
            self._hotkey_note.setText(self._state.hotkey.reason)
            self._store.set("hotkey", False)

    def _on_startup(self, value: bool) -> None:
        self._store.set("start_with_windows", value)
        if not self._state.apply_startup_preference() and value:
            self._startup_note.setText(
                "Windows refused the startup entry. You can add MERLIN "
                "manually from Task Manager → Startup apps."
            )
        else:
            self._startup_note.setText("")

    def _on_wake(self, value: bool) -> None:
        self._store.set("wake_word", value)
        self._voice.set_wake_required(value)

    def _on_voice_volume(self, value: int) -> None:
        self._store.set("voice_volume", int(value))
        self._volume_label.setText(f"{value}%")
        self._apply_tts()

    def _on_voice_rate(self, value: int) -> None:
        self._store.set("voice_rate", int(value))
        self._rate_label.setText(str(value))
        self._apply_tts()

    def _apply_tts(self) -> None:
        volume = int(self._store.get("voice_volume", 100)) / 100.0
        rate = int(self._store.get("voice_rate", 200))

        def job(backend):
            engine = backend.engine
            engine.setProperty("volume", max(0.0, min(1.0, volume)))
            engine.setProperty("rate", max(60, min(400, rate)))
            return True

        self._state.speech.submit("settings.tts", job)

    def _on_mic(self, index: int) -> None:
        if index < 0:
            return
        data = self._microphone.itemData(index)
        if data is None:
            return
        self._voice.select_device(int(data))

    def _on_devices(self, devices: object) -> None:
        devices = list(devices or [])
        current = self._voice.selected_index
        self._microphone.blockSignals(True)
        self._microphone.clear()
        self._microphone.addItem("Automatic (MERLIN chooses)", -1)
        for device in devices:
            suffix = "" if device.get("real", True) else "  — not a mic"
            self._microphone.addItem(
                f"{device['name']}{suffix}", device["index"]
            )
        self._microphone.blockSignals(False)
        if current == -1:
            self._microphone.setCurrentIndex(0)
        else:
            for row in range(self._microphone.count()):
                if self._microphone.itemData(row) == current:
                    self._microphone.setCurrentIndex(row)
                    break

    def _on_selected(self, index: int, _name: str) -> None:
        for row in range(self._microphone.count()):
            if self._microphone.itemData(row) == index:
                if self._microphone.currentIndex() != row:
                    self._microphone.blockSignals(True)
                    self._microphone.setCurrentIndex(row)
                    self._microphone.blockSignals(False)
                break
