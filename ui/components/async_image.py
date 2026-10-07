"""Article image that loads asynchronously and degrades to a placeholder.

Failures are invisible by design: a blocked network or a dead image URL
simply leaves the neutral placeholder in place, so a card never breaks.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..theme import BASE_FONT

_MANAGER: QNetworkAccessManager | None = None


def _manager() -> QNetworkAccessManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = QNetworkAccessManager()
    return _MANAGER


class AsyncImage(QFrame):
    def __init__(self, accent: str = "#4FD1FF", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CardFlat")
        self.setMinimumHeight(132)
        self.setMaximumHeight(160)
        self.setMinimumWidth(180)
        self._accent = accent
        self._original: QPixmap | None = None
        self._reply: QNetworkReply | None = None
        self._initial = "·"
        self._placeholder_size = QSize(-1, -1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)
        self._placeholder()

    # -- public ------------------------------------------------------------
    def set_source(self, url: str, initial: str = "·") -> None:
        self._initial = (initial or "·")[:1].upper() or "·"
        self._cancel()
        self._original = None
        if not url:
            self._placeholder()
            return

        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,
                          "MERLIN desktop/1.0")
        reply = _manager().get(request)
        reply.finished.connect(lambda: self._on_finished(reply))
        self._reply = reply

    def clear(self) -> None:
        self._cancel()
        self._original = None
        self._placeholder()

    # -- internals ---------------------------------------------------------
    def _cancel(self) -> None:
        if self._reply is not None:
            try:
                self._reply.abort()
                self._reply.deleteLater()
            except Exception:
                pass
            self._reply = None

    def _on_finished(self, reply: QNetworkReply) -> None:
        if reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                if pixmap.loadFromData(data.data()) and not pixmap.isNull():
                    self._original = pixmap
                    self._rescale()
                    reply.deleteLater()
                    return
            reply.deleteLater()
        except Exception:
            pass
        self._placeholder()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._original is not None:
            self._rescale()
        else:
            # Keep the neutral placeholder sized to the card.
            self._placeholder()

    def _rescale(self) -> None:
        if self._original is None:
            return
        size = self._label.size()
        if size.width() < 4 or size.height() < 4:
            return
        scaled = self._original.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def _placeholder(self) -> None:
        # Guard against a resize feedback loop: the label's size hint changes
        # with the pixmap, which can drive another layout pass.
        size = self.size()
        if size == self._placeholder_size or size.width() < 4 \
                or size.height() < 4:
            return
        self._placeholder_size = size

        width, height = size.width(), size.height()
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        base = QColor(self._accent)
        gradient = QLinearGradient(0, 0, width, height)
        gradient.setColorAt(0.0, QColor(base.red(), base.green(),
                                        base.blue(), 46))
        gradient.setColorAt(1.0, QColor(18, 22, 31, 255))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRect(0, 0, width, height)

        painter.setPen(QColor(255, 255, 255, 52))
        font = QFont(BASE_FONT)
        font.setPixelSize(max(12, int(min(width, height) * 0.34)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter,
                         self._initial)
        painter.end()

        self._label.setPixmap(pixmap)

    def sizeHint(self) -> QSize:
        return QSize(320, 144)
