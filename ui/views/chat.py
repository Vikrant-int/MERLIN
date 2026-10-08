"""Chat page: the real Gemini conversation with honest failure states."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..components.common import Banner, EmptyState, IconButton
from ..theme import BASE_FONT
from .base import PanelPage


class ChatInput(QTextEdit):
    """Enter sends, Shift+Enter inserts a newline."""

    submitted = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def _now() -> str:
    return datetime.now().strftime("%I:%M %p").lstrip("0")


class ChatView(PanelPage):
    def __init__(self, state, navigate, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state
        self._navigate = navigate
        self._service = state.assistant
        self._messages: list[dict] = []
        self._colours = {}

        # ---- header -----------------------------------------------------
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(12)

        title_column = QVBoxLayout()
        title_column.setSpacing(4)
        title = QLabel("Chat with MERLIN")
        title.setObjectName("H1")
        title_column.addWidget(title)
        self._subtitle = QLabel("Powered by your Gemini connection.")
        self._subtitle.setObjectName("Sub")
        title_column.addWidget(self._subtitle)
        header_layout.addLayout(title_column)
        header_layout.addStretch(1)

        self._status = QLabel("Checking…")
        self._status.setObjectName("Pill")
        header_layout.addWidget(self._status, 0, Qt.AlignmentFlag.AlignTop)

        self._clear = QPushButton("Clear conversation")
        self._clear.setObjectName("GhostButton")
        self._clear.clicked.connect(self._service.reset)
        header_layout.addWidget(self._clear, 0, Qt.AlignmentFlag.AlignTop)
        self.layout.addWidget(header)

        # ---- banners ------------------------------------------------------
        self._config_banner = Banner("info")
        self._config_banner._action.clicked.connect(
            lambda: self._navigate("settings")
        )
        self.layout.addWidget(self._config_banner)

        self._error_banner = Banner("error")
        self.layout.addWidget(self._error_banner)

        # ---- transcript ----------------------------------------------------
        self._transcript_card = QFrame()
        self._transcript_card.setObjectName("Card")
        card_layout = QVBoxLayout(self._transcript_card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._stream = QWidget()
        self._stream_layout = QVBoxLayout(self._stream)
        self._stream_layout.setContentsMargins(18, 14, 18, 14)
        self._stream_layout.setSpacing(2)
        self._stream_layout.addStretch(1)
        self._scroll.setWidget(self._stream)
        card_layout.addWidget(self._scroll)
        self.layout.addWidget(self._transcript_card, 1)

        self._empty = EmptyState(
            "Start a conversation.",
            "Ask MERLIN anything. Messages stay on this device and are sent "
            "to Gemini only when you press Send.",
        )
        self._stream_layout.insertWidget(0, self._empty)

        self._thinking = QLabel("MERLIN is thinking…")
        self._thinking.setObjectName("Muted")
        self._thinking.setContentsMargins(4, 4, 4, 4)
        self._thinking.hide()
        self._stream_layout.insertWidget(1, self._thinking)

        # ---- composer -------------------------------------------------------
        composer = QWidget()
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(0, 4, 0, 0)
        composer_layout.setSpacing(10)

        self._input = ChatInput()
        self._input.setPlaceholderText("Ask MERLIN anything…")
        self._input.setFixedHeight(56)
        self._input.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._input.submitted.connect(self._send)
        composer_layout.addWidget(self._input, 1)

        self._mic_button = IconButton("mic", "#4FD1FF", 18, 40)
        self._mic_button.setToolTip("Dictate a message")
        self._mic_button.clicked.connect(self._dictate)
        composer_layout.addWidget(self._mic_button)

        self._send_button = IconButton("send", "#04121B", 18, 40)
        self._send_button.setObjectName("PrimaryIconButton")
        self._send_button.setToolTip("Send  (Enter)")
        self._send_button.clicked.connect(self._send)
        composer_layout.addWidget(self._send_button)
        self.layout.addWidget(composer)

        hint = QLabel("Enter to send  ·  Shift+Enter for a new line")
        hint.setObjectName("Muted")
        self.layout.addWidget(hint)

        # ---- wiring ----------------------------------------------------------
        self._service.replyReady.connect(self._on_reply)
        self._service.failed.connect(self._on_failed)
        self._service.resetDone.connect(self._on_reset)
        self._service.busyChanged.connect(self._on_busy)
        state.voice.heardOnce.connect(self._on_dictated)
        state.backendReady.connect(self.refresh_credentials)
        # Switching the AI provider must update the pill/subtitle immediately.
        state.providerChanged.connect(self.refresh_credentials)

        for entry in self._service.history:
            self._messages.append(dict(entry))
        self._rebuild()

        self.refresh_credentials()

    # -- theme -------------------------------------------------------------
    def apply_theme(self, colours: dict[str, str]) -> None:
        self._colours = colours

    # -- credential / error banners -----------------------------------------
    def refresh_credentials(self) -> None:
        from services.assistant_service import gemini_info  # noqa: PLC0415

        if self._state.provider == "mock":
            self._render_dev_mode()
            return
        self._render_gemini_status(gemini_info())

    def _render_dev_mode(self) -> None:
        """Mock provider: every indicator says "development", nothing hides it."""
        self._subtitle.setText("Development mode — local placeholder answers.")
        self._status.setText("Mock (dev)")
        self._config_banner.show_message(
            "Development mode: AI Provider Mock",
            "Answers here are local placeholder replies written by the Mock "
            "provider — never real Gemini answers. Switch to Auto or Gemini "
            "in Settings to connect the Gemini API.",
            "Open Settings",
        )
        self._empty.set_detail(
            "Messages stay on this device and are answered by the local Mock "
            "provider while development mode is on; nothing is sent to "
            "Gemini."
        )

    def _render_gemini_status(self, info: dict) -> None:
        self._subtitle.setText("Powered by your Gemini connection.")
        self._empty.set_detail(
            "Ask MERLIN anything. Messages stay on this device and are sent "
            "to Gemini only when you press Send."
        )
        if info.get("starting"):
            # The backend import is still running; say so rather than
            # claiming the key is missing.
            self._config_banner.show_message(
                "MERLIN is starting up.",
                "The assistant is still loading. Chat will be ready in a "
                "moment.",
            )
        elif not info["configured"]:
            self._config_banner.show_message(
                "Gemini isn't configured yet.",
                "Set GEMINI_API_KEY, then restart MERLIN. Until then, chat "
                "will tell you rather than pretend to answer.",
                "Open Settings",
            )
        elif info["detail"]:
            self._config_banner.show_message(
                "Gemini needs attention.",
                info["detail"],
                "Open Settings",
            )
        else:
            self._config_banner.clear()

        if info.get("starting"):
            self._status.setText("Starting…")
        elif not info["configured"]:
            self._status.setText("Not configured")
        elif info["available"]:
            self._status.setText("Configured")
        else:
            self._status.setText("Unavailable")

    def show_error(self, message: str) -> None:
        self._error_banner.show_message(message)

    def clear_error(self) -> None:
        self._error_banner.clear()

    # -- sending -------------------------------------------------------------
    def _send(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or self._service.busy:
            return
        self._input.clear()
        self._error_banner.clear()
        self._service.send(text)
        self._state.log_activity("chat", text)

    def _dictate(self) -> None:
        if self._service.busy:
            return
        self._mic_button.setEnabled(False)
        self._input.setPlaceholderText("Listening…")
        self._state.voice.listen_once()

    def _on_dictated(self, text: str) -> None:
        self._mic_button.setEnabled(True)
        self._input.setPlaceholderText("Ask MERLIN anything…")
        if text:
            current = self._input.toPlainText()
            joined = f"{current} {text}".strip() if current else text
            self._input.setPlainText(joined)
            self._input.moveCursor(self._input.textCursor().End)

    def focus_input(self) -> None:
        self._input.setFocus()

    # -- results --------------------------------------------------------------
    def _on_reply(self, user: str, reply: str) -> None:
        self._error_banner.clear()
        self._append({"role": "user", "text": user, "time": _now()})
        self._append({"role": "assistant", "text": reply, "time": _now()})

    def _on_failed(self, user: str, message: str) -> None:
        self._append({"role": "user", "text": user, "time": _now()})
        self._append({"role": "error", "text": message, "time": _now()})
        self.show_error(message)

    def _on_reset(self) -> None:
        self._messages.clear()
        self._error_banner.clear()
        self._rebuild()

    def _on_busy(self, busy: bool) -> None:
        self._thinking.setVisible(busy)
        self._send_button.setEnabled(not busy)
        if busy:
            bar = self._scroll.verticalScrollBar()
            bar.setValue(bar.maximum())

    # -- rendering --------------------------------------------------------------
    def _append(self, message: dict) -> None:
        self._messages.append(message)
        widget = self._bubble(message)
        index = self._stream_layout.count() - 1  # before the trailing stretch
        self._stream_layout.insertWidget(index, widget)
        self._empty.hide()
        self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        )

    def _rebuild(self) -> None:
        while self._stream_layout.count() > 1:
            item = self._stream_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget not in (self._empty,
                                                      self._thinking):
                widget.deleteLater()
        self._stream_layout.insertWidget(0, self._empty)
        self._stream_layout.insertWidget(1, self._thinking)

        self._empty.setVisible(not self._messages)
        self._thinking.setVisible(self._service.busy)
        self._clear.setEnabled(bool(self._messages))
        for message in self._messages:
            index = self._stream_layout.count() - 1
            self._stream_layout.insertWidget(index, self._bubble(message))

    def _bubble(self, message: dict) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 5, 0, 5)
        row_layout.setSpacing(0)

        role = message.get("role", "assistant")
        text = message.get("text", "")
        when = message.get("time", "")

        bubble = QFrame()
        if role == "user":
            bubble.setObjectName("ChatBubbleUser")
        elif role == "error":
            bubble.setObjectName("ChatBubbleError")
        else:
            bubble.setObjectName("ChatBubbleAssistant")
        bubble.setMaximumWidth(640)

        column = QVBoxLayout(bubble)
        column.setContentsMargins(15, 11, 15, 9)
        column.setSpacing(5)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        if role == "error":
            body.setStyleSheet("color:#FFB3BC; font-size:13px;")
        column.addWidget(body)

        stamp = QLabel(when)
        stamp.setObjectName("Muted")
        font = QFont(BASE_FONT)
        font.setPixelSize(10)
        stamp.setFont(font)
        if role == "error":
            stamp.setStyleSheet("color:#FF6B7A; font-size:10px;")
        column.addWidget(stamp, 0, Qt.AlignmentFlag.AlignRight)

        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        else:
            row_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            row_layout.addStretch(1)
        return row
