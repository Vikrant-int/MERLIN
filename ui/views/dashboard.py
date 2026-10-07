"""Dashboard: greeting, assistant core, quick actions and recent activity."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..components.assistant_core import AssistantCore
from ..components.common import Card, EmptyState, ToolButton
from ..theme import BASE_FONT
from .base import Page

_GREETINGS = (
    (5, "Good evening."),
    (12, "Good morning."),
    (17, "Good afternoon."),
    (24, "Good evening."),
)


def greeting_for(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    for limit, text in _GREETINGS:
        if hour < limit:
            return text
    return "Good evening."


_CAPTIONS = {
    "IDLE": "Idle — say “Merlin”, or ask me anything.",
    "LISTENING": "Listening…",
    "THINKING": "Thinking…",
    "SPEAKING": "Speaking…",
    "ERROR": "Something needs your attention.",
    "OFFLINE": "MERLIN's backend isn't available.",
}

_ACTIVITY_ICONS = {"chat": "chat", "voice": "mic", "news": "news",
                   "music": "music"}


class DashboardView(Page):
    def __init__(self, state, navigate, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state
        self._navigate = navigate
        self._colours = {}

        # ---- header -----------------------------------------------------
        self._greeting = QLabel(greeting_for())
        self._greeting.setObjectName("H1")
        prompt = QLabel("What can I do for you?")
        prompt.setObjectName("Sub")
        header = QWidget()
        column = QVBoxLayout(header)
        column.setContentsMargins(0, 0, 0, 4)
        column.setSpacing(5)
        column.addWidget(self._greeting)
        column.addWidget(prompt)
        self.layout.addWidget(header)

        self.layout.addSpacing(4)

        # ---- assistant core ---------------------------------------------
        self._core = AssistantCore()
        self._core.setFixedSize(252, 252)

        core_row = QHBoxLayout()
        core_row.addStretch(1)
        core_row.addWidget(self._core, 0, Qt.AlignmentFlag.AlignCenter)
        core_row.addStretch(1)
        self.layout.addLayout(core_row)

        self._caption = QLabel(_CAPTIONS[state.core_state])
        self._caption.setObjectName("Sub")
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self._caption)

        self._detail = QLabel("")
        self._detail.setObjectName("DangerText")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setVisible(False)
        self.layout.addWidget(self._detail)

        self.layout.addStretch(1)

        # ---- quick actions ----------------------------------------------
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        actions_layout.addStretch(1)
        for label, glyph, key in (
            ("Ask MERLIN", "chat", "chat"),
            ("Voice Command", "mic", "voice"),
            ("Latest News", "news", "news"),
            ("Play Music", "music", "music"),
        ):
            button = ToolButton(label, glyph)
            button.setMinimumWidth(158)
            button.clicked.connect(
                lambda _=False, k=key: self._on_quick_action(k)
            )
            actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        self.layout.addWidget(actions)

        self.layout.addSpacing(6)

        # ---- recent activity ---------------------------------------------
        self._activity_card = Card()
        card_layout = QVBoxLayout(self._activity_card)
        card_layout.setContentsMargins(18, 15, 18, 15)
        card_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("Recent activity")
        title.setObjectName("H3")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._clear_button = QPushButton("Clear")
        self._clear_button.setObjectName("GhostButton")
        self._clear_button.clicked.connect(state.clear_activity)
        title_row.addWidget(self._clear_button)
        card_layout.addLayout(title_row)

        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        card_layout.addWidget(self._list)

        self._empty = EmptyState(
            "Nothing yet.",
            "Your conversations and commands will show up here as you use "
            "MERLIN.",
        )
        card_layout.addWidget(self._empty)

        self.layout.addWidget(self._activity_card)

        # ---- wiring --------------------------------------------------------
        state.coreStateChanged.connect(self._on_core_state)
        state.activityChanged.connect(self._rebuild_activity)
        self._rebuild_activity()
        self._on_core_state(state.core_state)

    # -- theme -------------------------------------------------------------
    def apply_theme(self, colours: dict[str, str]) -> None:
        self._colours = colours

    # -- quick actions -----------------------------------------------------
    def _on_quick_action(self, key: str) -> None:
        if key == "news":
            self._navigate("news", {"refresh": True})
        elif key == "music":
            self._navigate("music", {"autoplay": True})
        elif key == "voice":
            self._navigate("voice", {"listen": True})
        else:
            self._navigate(key)

    # -- assistant core ----------------------------------------------------
    def _on_core_state(self, state_name: str) -> None:
        self._core.set_state(state_name)
        self._caption.setText(
            _CAPTIONS.get(state_name, "Ready when you are.")
        )
        error = self._state.error
        if state_name in ("ERROR", "OFFLINE") and error:
            self._detail.setText(error)
            self._detail.setVisible(True)
        else:
            self._detail.setVisible(False)

    # -- activity ----------------------------------------------------------
    def _rebuild_activity(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        entries = self._state.activity
        self._empty.setVisible(not entries)
        self._clear_button.setVisible(bool(entries))
        self._list.setVisible(bool(entries))

        for entry in entries:
            self._list_layout.addWidget(self._activity_row(entry))

    @staticmethod
    def _activity_row(entry: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 7, 4, 7)
        layout.setSpacing(14)

        time_label = QLabel(entry["time"])
        time_label.setObjectName("Muted")
        font = QFont(BASE_FONT)
        font.setPixelSize(11)
        time_label.setFont(font)
        time_label.setFixedWidth(72)
        layout.addWidget(time_label, 0, Qt.AlignmentFlag.AlignTop)

        kind = entry["kind"]
        pill = QLabel(kind.capitalize())
        pill.setObjectName("Pill")
        pill.setFixedWidth(66)
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)

        text = QLabel(entry["text"])
        text.setWordWrap(True)
        text.setStyleSheet("color:#9AA4B8; font-size:13px;")
        layout.addWidget(text, 1)
        return row
