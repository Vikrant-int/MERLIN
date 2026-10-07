"""One place where backend signals become the states the UI renders.

Views never reach into services to work out what the orb should do; they
subscribe to `coreStateChanged` and paint. That keeps the mapping honest --
there is a single function deciding what MERLIN is currently doing, and it
can only report what the backend actually reported.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from services.assistant_service import AssistantService
from services.core import BACKEND_ERROR, SpeechEngine, backend_ready
from services.music_service import MusicService
from services.news_service import NewsService
from services.settings_store import SettingsStore, set_startup
from services.voice_service import (
    DISCONNECTED,
    ERROR as VOICE_ERROR,
    LISTENING as VOICE_LISTENING,
    NO_MICROPHONE,
    PROCESSING as VOICE_PROCESSING,
    READY as VOICE_READY,
    VoiceService,
)
from .hotkey import GlobalHotkey
from .theme import prefers_reduced_motion

# Assistant-core states.
OFFLINE = "OFFLINE"
ERROR = "ERROR"
SPEAKING = "SPEAKING"
THINKING = "THINKING"
LISTENING = "LISTENING"
IDLE = "IDLE"

MAX_ACTIVITY = 14


class AppState(QObject):
    """Owns the services, the recent-activity log and the derived states."""

    coreStateChanged = Signal(str)
    activityChanged = Signal()
    onlineChanged = Signal(bool)
    themeChanged = Signal(str)
    #: Emitted once the backend import has finished, either way. Pages use
    #: it to upgrade their "still starting" status to the real answer.
    backendReady = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # Constructed here so ordering is explicit: the speech engine is the
        # only object allowed to import `main`, and everything else waits
        # for it.
        self.speech = SpeechEngine(self)
        self.assistant = AssistantService(self)
        self.voice = VoiceService(self.speech, self)
        self.news = NewsService(self)
        self.music = MusicService(self.speech, self)

        self.activity: list[dict] = []
        self.settings = SettingsStore(parent=self)
        self.hotkey = GlobalHotkey(self)
        self.theme = str(self.settings.get("theme", "dark"))

        self._core = IDLE
        self._error = ""
        self._error_sticky = False
        # False until the speech thread publishes the backend, so the first
        # `_set_online(True)` actually emits `onlineChanged` and the sidebar
        # leaves "Starting…" behind.
        self._online = False
        self._starting = True

        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.setInterval(6000)
        self._error_timer.timeout.connect(self.clear_error)

        self.speech.failed.connect(self._on_backend_failed)
        self.speech.busyChanged.connect(self._refresh)
        self.speech.ready.connect(self._on_ready)

        self.assistant.busyChanged.connect(self._refresh)
        self.assistant.replyReady.connect(
            lambda _u, _r: (self.clear_error(), self._refresh())
        )
        self.assistant.failed.connect(self._on_assistant_failed)

        self.voice.stateChanged.connect(self._on_voice_state)
        self.news.busyChanged.connect(self._refresh)
        self.news.finished.connect(
            lambda _a: (self.clear_error(), self._refresh())
        )
        self.news.failed.connect(self._on_news_failed)

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Kick off the speech thread.

        Deliberately non-blocking: importing the backend takes a few seconds
        and the window must paint (and report "Starting…") while it happens.
        The UI learns the outcome from `speech.ready` / `speech.failed`.
        """
        self._starting = True
        self.speech.start_async()
        self._refresh()

    def shutdown(self) -> None:
        self.voice.shutdown()
        self.speech.shutdown()

    # -- theme ---------------------------------------------------------------
    def set_theme(self, name: str) -> None:
        if name not in ("dark", "light"):
            return
        if name == self.theme:
            return
        self.theme = name
        self.settings.set("theme", name)
        self.themeChanged.emit(name)

    def apply_startup_preference(self) -> bool:
        """Keep the Windows Run key in step with the user's choice."""
        wanted = bool(self.settings.get("start_with_windows", False))
        return set_startup(wanted)

    # -- derived assistant state -------------------------------------------
    @property
    def core_state(self) -> str:
        return self._core

    @property
    def online(self) -> bool:
        return self._online

    @property
    def error(self) -> str:
        return self._error

    @property
    def backend_available(self) -> bool:
        return backend_ready(0) and not BACKEND_ERROR

    @property
    def starting(self) -> bool:
        return self._starting

    def _refresh(self, *_args) -> None:
        if self._starting:
            # Nothing has failed yet, so claiming OFFLINE would be a lie.
            self._set_core(IDLE)
            return
        if BACKEND_ERROR or not backend_ready(0):
            self._set_core(OFFLINE)
            return

        voice_state = self.voice.state
        if self._error:
            self._set_core(ERROR)
        elif self.speech.busy:
            self._set_core(SPEAKING)
        elif self.assistant.busy or voice_state == VOICE_PROCESSING:
            self._set_core(THINKING)
        elif voice_state == VOICE_LISTENING:
            self._set_core(LISTENING)
        else:
            self._set_core(IDLE)

    def _set_core(self, state: str) -> None:
        if state != self._core:
            self._core = state
            self.coreStateChanged.emit(state)

    def _set_online(self, value: bool) -> None:
        if value != self._online:
            self._online = value
            self.onlineChanged.emit(value)

    # -- errors ------------------------------------------------------------
    def set_error(self, message: str, sticky: bool = False) -> None:
        self._error = message or "Something went wrong."
        self._error_sticky = sticky
        self._error_timer.stop()
        if not sticky:
            self._error_timer.start()
        self._refresh()

    def clear_error(self) -> None:
        if self._error:
            self._error = ""
            self._error_sticky = False
            self._error_timer.stop()
            self._refresh()

    def _on_backend_failed(self, message: str) -> None:
        self._starting = False
        self.set_error(message or "MERLIN's backend failed to start.", True)
        self._set_online(False)
        self.backendReady.emit()

    def _on_ready(self) -> None:
        self._starting = False
        self._set_online(True)
        self.clear_error()
        self.backendReady.emit()
        if not self.voice.devices:
            self.voice.refresh_devices()

    def _on_assistant_failed(self, _user: str, message: str) -> None:
        self.set_error(message)

    def _on_news_failed(self, message: str) -> None:
        self.set_error(message)

    def _on_voice_state(self, state: str) -> None:
        if state in (NO_MICROPHONE, DISCONNECTED, VOICE_ERROR):
            self.set_error(self.voice.status, sticky=True)
        elif state in (VOICE_READY, VOICE_LISTENING):
            if self._error_sticky:
                self.clear_error()
        self._refresh()

    # -- recent activity ---------------------------------------------------
    def log_activity(self, kind: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if len(text) > 96:
            text = text[:93] + "…"
        self.activity.insert(
            0,
            {
                "kind": kind,
                "text": text,
                "time": datetime.now().strftime("%I:%M %p").lstrip("0"),
            },
        )
        del self.activity[MAX_ACTIVITY:]
        self.activityChanged.emit()

    def clear_activity(self) -> None:
        self.activity.clear()
        self.activityChanged.emit()

    # -- motion preferences -------------------------------------------------
    @staticmethod
    def reduced_motion() -> bool:
        return prefers_reduced_motion()
