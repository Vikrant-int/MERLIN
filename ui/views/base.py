"""Shared page scaffold so every screen lines up with the same margins."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

CONTENT_MAX_WIDTH = 1180


class Page(QScrollArea):
    """Scrolling page body, centred and capped so wide screens stay readable.

    Subclasses fill ``self.body`` (a QVBoxLayout) with their content.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setWidgetResizable(True)

        outer = QWidget()
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addStretch(1)

        self.body = QWidget()
        self.body.setMaximumWidth(CONTENT_MAX_WIDTH)
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(44, 34, 44, 42)
        self.layout.setSpacing(16)
        outer_layout.addWidget(self.body)
        outer_layout.addStretch(1)

        self.setWidget(outer)

    # -- helpers -----------------------------------------------------------
    def add_header(self, title: str, subtitle: str = "") -> QWidget:
        block = QWidget()
        column = QVBoxLayout(block)
        column.setContentsMargins(0, 0, 0, 4)
        column.setSpacing(5)

        heading = QLabel(title)
        heading.setObjectName("H1")
        column.addWidget(heading)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("Sub")
            sub.setWordWrap(True)
            column.addWidget(sub)

        self.layout.addWidget(block)
        return block

    def add_row(self, spacing: int = 12) -> QHBoxLayout:
        """A horizontal row appended to the page body."""
        row = QHBoxLayout()
        row.setSpacing(spacing)
        self.layout.addLayout(row)
        return row

    def add_stretch(self) -> None:
        self.layout.addStretch(1)

    def add_widget(self, widget: QWidget) -> QWidget:
        self.layout.addWidget(widget)
        return widget

    def add_spacing(self, px: int) -> None:
        self.layout.addSpacing(px)


class PanelPage(QWidget):
    """Non-scrolling page with the same margins as :class:`Page`.

    Used where a child widget owns the scrolling (Chat, News), so headers
    and toolbars stay pinned instead of scrolling out of reach.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PanelPage")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        self.body = QWidget()
        self.body.setMaximumWidth(CONTENT_MAX_WIDTH)
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(44, 34, 44, 42)
        self.layout.setSpacing(14)
        outer.addWidget(self.body)
        outer.addStretch(1)

    add_header = Page.add_header
    add_row = Page.add_row
    add_widget = Page.add_widget
    add_spacing = Page.add_spacing
    add_stretch = Page.add_stretch
