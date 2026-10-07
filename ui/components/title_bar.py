"""Custom title bar: branding on the left, window controls on the right.

Dragging empty space hands the move to the OS (`startSystemMove`), so Windows
keeps its normal snap/maximise behaviour instead of us reimplementing it.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ..theme import BASE_FONT
from .icons import icon, logo


class WindowButton(QPushButton):
    """A chrome-free title-bar button whose glyph recolours on hover."""

    def __init__(self, glyph: str, close: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._glyph = glyph
        self._close = close
        self.setObjectName("TitleClose" if close else "TitleButton")
        self.setFixedSize(44, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()

    def set_glyph(self, glyph: str) -> None:
        self._glyph = glyph
        self._refresh()

    def _refresh(self, hovered: bool = False) -> None:
        if self._close and hovered:
            colour = "#FFFFFF"
        elif hovered:
            colour = "#E8ECF4"
        else:
            colour = "#9AA4B8"
        self.setIcon(icon(self._glyph, colour, 13))
        self.setIconSize(QSize(13, 13))

    def enterEvent(self, event) -> None:
        self._refresh(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._refresh(False)
        super().leaveEvent(event)


class TitleBar(QWidget):
    def __init__(self, window, accent: str = "#4FD1FF",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._window = window
        self.setFixedHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 4, 0)
        layout.setSpacing(10)

        mark = QLabel()
        mark.setPixmap(logo(22, accent))
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)

        name = QLabel("MERLIN")
        font = QFont(BASE_FONT)
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        name.setFont(font)
        layout.addWidget(name, 0, Qt.AlignmentFlag.AlignVCenter)

        subtitle = QLabel("Your intelligent desktop companion")
        subtitle.setObjectName("Muted")
        layout.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

        self.min_button = WindowButton("minimize")
        self.max_button = WindowButton("maximize")
        self.close_button = WindowButton("close", close=True)

        self.min_button.clicked.connect(self._window.showMinimized)
        self.max_button.clicked.connect(self.toggle_maximize)
        self.close_button.clicked.connect(self._window.close)

        layout.addWidget(self.min_button)
        layout.addWidget(self.max_button)
        layout.addWidget(self.close_button)

    # -- state -------------------------------------------------------------
    def set_maximized(self, maximized: bool) -> None:
        self.max_button.set_glyph("restore" if maximized else "maximize")

    def toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
