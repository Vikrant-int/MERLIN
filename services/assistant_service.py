"""Gemini chat, wrapped for the UI.

Only the *presence* of a credential is ever inspected -- never its value --
and nothing here prints to stdout, so a key can never reach a log or screen.
"""
from __future__ import annotations

import threading
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from .core import (
    BACKEND_ERROR,
    BACKEND_READY,
    BackendNotReady,
    TaskRunner,
    get_main,
)

# Phrases `GeminiChat.send()` returns instead of raising when it cannot get
# an answer. They are how the UI tells "not configured / offline" apart from
# a genuine model reply, without inventing a response of its own.
_BACKEND_FAILURES = (
    "could not reach gemini",
    "gemini_api_key is not set",
    "no usable gemini sdk",
    "empty reply",
)


def gemini_info() -> dict:
    """Non-sensitive status of the Gemini integration."""
    if not BACKEND_READY.is_set():
        # Asking now would import `main` on this (the GUI) thread.
        return {
            "configured": False,
            "available": False,
            "starting": not bool(BACKEND_ERROR),
            "backend": "starting" if not BACKEND_ERROR else "unavailable",
            "model": "",
            "detail": (BACKEND_ERROR[-1] if BACKEND_ERROR
                       else "MERLIN is still starting up."),
        }

    try:
        backend = get_main()
    except Exception as exc:
        return {
            "configured": False,
            "available": False,
            "starting": False,
            "backend": "unavailable",
            "model": "",
            "detail": f"{type(exc).__name__}: {exc}",
        }

    configured = bool(getattr(backend, "API_KEY", None))
    detail = getattr(backend.gemini, "_config_error", None) or ""
    return {
        "configured": configured,
        "available": configured and not detail,
        "starting": False,
        "backend": getattr(backend.gemini, "backend", "unknown"),
        "model": getattr(backend, "MODEL_NAME", ""),
        # A config error explains how to *set* the key; it never contains it.
        "detail": detail,
    }


def is_backend_failure(reply: str) -> bool:
    low = (reply or "").lower()
    return any(marker in low for marker in _BACKEND_FAILURES)


def _now() -> str:
    return datetime.now().strftime("%I:%M %p").lstrip("0")


class AssistantService(QObject):
    """Conversation history plus send/reset, run off the GUI thread."""

    replyReady = Signal(str, str)    # user text, assistant text
    failed = Signal(str, str)        # user text, friendly error
    resetDone = Signal()
    busyChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._runner = TaskRunner(self, threads=2)
        self._runner.finished.connect(self._on_task)
        # GeminiChat keeps one live conversation object, so concurrent sends
        # would interleave its history. One at a time, ever.
        self._lock = threading.Lock()
        self._pending = ""
        self.history: list[dict] = []  # {"role", "text", "time"}

    # -- public API --------------------------------------------------------
    @property
    def busy(self) -> bool:
        return bool(self._pending)

    def send(self, text: str) -> None:
        text = (text or "").strip()
        if not text or self._pending:
            return
        if not BACKEND_READY.is_set():
            # Honest, immediate answer instead of a blocking import.
            self.failed.emit(
                text,
                (BACKEND_ERROR[-1] if BACKEND_ERROR
                 else "MERLIN is still starting up. Try again in a moment."),
            )
            return
        self._pending = text
        self.busyChanged.emit(True)
        self._runner.submit("chat.send", lambda: self._send_blocking(text))

    def reset(self) -> None:
        if not BACKEND_READY.is_set():
            # Nothing has been asked of Gemini yet, so there is nothing to
            # clear there either -- just tidy the transcript.
            self.history.clear()
            self.resetDone.emit()
            return
        self._runner.submit("chat.reset", self._reset_blocking)

    # -- worker ------------------------------------------------------------
    def _send_blocking(self, text: str) -> str:
        backend = get_main()
        with self._lock:
            return backend.gemini.send(text)

    def _reset_blocking(self) -> bool:
        backend = get_main()
        with self._lock:
            backend.gemini.reset()
        return True

    # -- results -----------------------------------------------------------
    def _on_task(self, tag: str, ok: bool, payload) -> None:
        if tag == "chat.reset":
            if ok:
                self.history.clear()
                self.resetDone.emit()
            return
        if tag != "chat.send":
            return

        user = self._pending
        self._pending = ""
        self.busyChanged.emit(False)

        if not ok:
            self.failed.emit(
                user, "Something went wrong while contacting Gemini."
            )
            return

        reply = str(payload).strip() or "Gemini returned an empty reply."
        if is_backend_failure(reply):
            # Real backend text explaining a missing key or failed request.
            self.failed.emit(user, reply)
            return

        stamp = _now()
        self.history.append({"role": "user", "text": user, "time": stamp})
        self.history.append({"role": "assistant", "text": reply, "time": stamp})
        self.replyReady.emit(user, reply)
