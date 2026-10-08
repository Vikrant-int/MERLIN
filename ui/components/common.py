"""Small shared widgets: cards, banners, buttons and status dots."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .icons import icon


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, flat: bool = False):
        super().__init__(parent)
        self.setObjectName("CardFlat" if flat else "Card")


class IconButton(QPushButton):
    """Square, chrome-free button that shows a line icon."""

    def __init__(self, name: str, color: str, size: int = 18,
                 px: int = 34, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("IconButton")
        self.setIcon(icon(name, color, size))
        self.setIconSize(QSize(size, size))
        self.setFixedSize(px, px)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class ToolButton(QPushButton):
    """Icon + label button used for quick actions and transports."""

    def __init__(self, text: str, icon_name: str = "", parent=None,
                 primary: bool = False):
        super().__init__(parent)
        self.setObjectName("PrimaryButton" if primary else "")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(8)
        if icon_name:
            pixmap = icon(icon_name, "#E8ECF4" if not primary else "#04121B", 17)
            label = QLabel()
            label.setPixmap(pixmap)
            layout.addWidget(label)
        text_label = QLabel(text)
        if primary:
            text_label.setStyleSheet("font-weight:600;")
        layout.addWidget(text_label)
        layout.addStretch(1)


def dot(color: str, size: int = 9) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return pixmap


class StatusDot(QFrame):
    """A coloured dot followed by a short status word."""

    def __init__(self, text: str = "", color: str = "#6B7488",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dot = QLabel()
        self._text = QLabel()
        self._text.setObjectName("Sub")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._text, 0, Qt.AlignmentFlag.AlignVCenter)
        self.set_status(text, color)

    def set_status(self, text: str, color: str) -> None:
        self._dot.setPixmap(dot(color, 9))
        self._text.setText(text)
        self.setToolTip(text)


class Pill(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("Pill")


class Banner(QFrame):
    """A single-line contextual message with an optional action button."""

    def __init__(self, kind: str = "info", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BannerError" if kind == "error" else "BannerInfo")
        self._kind = kind
        self._colour = "#FF6B7A" if kind == "error" else "#4FD1FF"

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(14, 11, 12, 11)
        self._layout.setSpacing(11)

        self._icon = QLabel()
        self._layout.addWidget(self._icon)

        column = QVBoxLayout()
        column.setSpacing(2)
        self._title = QLabel()
        self._title.setObjectName("H3")
        self._title.setWordWrap(True)
        self._detail = QLabel()
        self._detail.setObjectName("Sub")
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(f"color:{self._colour}; font-size:12.5px;")
        column.addWidget(self._title)
        column.addWidget(self._detail)
        self._layout.addLayout(column, 1)

        self._action = QPushButton()
        self._action.hide()
        self._layout.addWidget(self._action, 0, Qt.AlignmentFlag.AlignVCenter)

        self.hide()

    def show_message(self, title: str, detail: str = "",
                     action_text: str = "") -> None:
        self._title.setText(title)
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        name = "alert" if self._kind == "error" else "alert"
        self._icon.setPixmap(icon(name, self._colour, 17))
        if action_text:
            self._action.setText(action_text)
            self._action.show()
        else:
            self._action.hide()
        self.show()

    def clear(self) -> None:
        self.hide()


class EmptyState(QWidget):
    """Placeholder shown when a list has nothing to display."""

    def __init__(self, title: str, detail: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("H3")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        self._detail: QLabel | None = None
        if detail:
            self.set_detail(detail)

    def set_detail(self, text: str) -> None:
        """Replace the caption under the title (used for provider-aware text)."""
        if self._detail is None:
            self._detail = QLabel("")
            self._detail.setObjectName("Sub")
            self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._detail.setWordWrap(True)
            self._detail.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Preferred)
            self.layout().addWidget(self._detail)
        self._detail.setText(text)
        self._detail.setVisible(bool(text))


def section_header(title: str, subtitle: str = "") -> QWidget:
    """Eyebrow + heading block used at the top of every page."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    heading = QLabel(title)
    heading.setObjectName("H1")
    layout.addWidget(heading)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("Sub")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    return widget
