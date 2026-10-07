"""Music library and playback queue for the UI.

Playback itself is the backend's existing behaviour -- `main.play_song()`
matches the title against `musicLibrary.music` and opens the URL in the
system browser while speaking the confirmation. This service only adds the
queue bookkeeping the UI needs; it never invents transport controls the
backend cannot honour, so there is no fake position/seek/album metadata.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .core import SpeechEngine


class MusicService(QObject):
    """Ordered queue over `musicLibrary.music`."""

    currentChanged = Signal(int)      # -1 when nothing is selected
    played = Signal(str)              # title handed to the backend

    def __init__(self, speech: SpeechEngine, parent: QObject | None = None):
        super().__init__(parent)
        self._speech = speech
        self._tracks: list[tuple[str, str]] = []
        self._position = -1
        self.reload()

    # -- library -----------------------------------------------------------
    def reload(self) -> list[tuple[str, str]]:
        try:
            import musicLibrary  # noqa: PLC0415

            items = getattr(musicLibrary, "music", {}) or {}
            self._tracks = [(str(k), str(v)) for k, v in items.items()]
        except Exception:
            self._tracks = []
        if self._position >= len(self._tracks):
            self._position = -1
        return list(self._tracks)

    @property
    def tracks(self) -> list[tuple[str, str]]:
        return list(self._tracks)

    @property
    def position(self) -> int:
        return self._position

    def title_at(self, index: int) -> str:
        if 0 <= index < len(self._tracks):
            return self._tracks[index][0]
        return ""

    # -- transport ---------------------------------------------------------
    def play(self, index: int) -> None:
        if not (0 <= index < len(self._tracks)):
            return
        self._position = index
        self.currentChanged.emit(index)
        title = self._tracks[index][0]
        # Hand the whole command to the backend so lookup, browser launch
        # and the spoken confirmation all stay exactly as they are today.
        self._speech.submit(
            "music.play",
            lambda backend: backend.play_song(["play", *title.split()]),
        )
        self.played.emit(title)

    def next(self) -> None:
        if not self._tracks:
            return
        self.play((self._position + 1) % len(self._tracks))

    def previous(self) -> None:
        if not self._tracks:
            return
        index = self._position - 1 if self._position > 0 else len(self._tracks) - 1
        self.play(index)

    def stop(self) -> None:
        """Clear the selection; playback itself lives in the browser."""
        self._position = -1
        self.currentChanged.emit(-1)
