"""Left navigation rail: brand, page buttons, separator, status."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme import BASE_FONT
from .common import StatusDot
from .icons import icon, logo

PAGES = (
    ("dashboard", "Dashboard", "dashboard"),
    ("chat", "Chat", "chat"),
    ("voice", "Voice", "mic"),
    ("news", "News", "news"),
    ("music", "Music", "music"),
)


class NavButton(QPushButton):
    """Checkable nav entry with a thin accent bar marking the active page."""

    def __init__(self, text: str, glyph: str, colour: str,
                 parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(icon(glyph, colour, 18))
        self.setIconSize(QSize(18, 18))

        self._indicator = QWidget(self)
        self._indicator.setFixedSize(3, 16)
        self._indicator.setStyleSheet(
            "background:#4FD1FF; border-radius:1px;"
        )
        self._indicator.hide()

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self._indicator.setVisible(active)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._indicator.move(6, (self.height() - self._indicator.height()) // 2)


class Sidebar(QWidget):
    """Navigation rail. Emits the page key that was chosen."""

    navigate = Signal(str)
    settingsRequested = Signal()

    def __init__(self, colors: dict[str, str],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(218)
        self.setStyleSheet(
            f"#Sidebar {{ background: {colors['sidebar']}; "
            f"border-right: 1px solid {colors['border_soft']}; }}"
        )

        self._colours = colors
        self._buttons: dict[str, NavButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(4)

        # ---- brand ------------------------------------------------------
        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(6, 0, 0, 14)
        brand_layout.setSpacing(11)
        mark = QLabel()
        mark.setPixmap(logo(34, colors["accent"]))
        brand_layout.addWidget(mark)

        text = QVBoxLayout()
        text.setSpacing(0)
        wordmark = QLabel("MERLIN")
        font = QFont(BASE_FONT)
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.DemiBold)
        wordmark.setFont(font)
        text.addWidget(wordmark)
        tagline = QLabel("Desktop companion")
        tagline.setObjectName("Muted")
        text.addWidget(tagline)
        brand_layout.addLayout(text, 1)
        layout.addWidget(brand)
        layout.addSpacing(8)

        # ---- navigation -------------------------------------------------
        for key, label, glyph in PAGES:
            button = NavButton(label, glyph, colors["text_dim"])
            button.clicked.connect(
                lambda _=False, k=key: self.navigate.emit(k)
            )
            self._buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)

        # ---- separator --------------------------------------------------
        separator = QFrame()
        separator.setObjectName("Separator")
        separator.setFixedHeight(1)
        separator.setStyleSheet(
            f"background:{colors['border']}; max-height:1px;"
        )
        layout.addWidget(separator)
        layout.addSpacing(8)

        # ---- settings ---------------------------------------------------
        settings = NavButton("Settings", "settings", colors["text_dim"])
        settings.clicked.connect(self.settingsRequested.emit)
        self._buttons["settings"] = settings
        layout.addWidget(settings)
        layout.addSpacing(14)

        # ---- status -----------------------------------------------------
        status_row = QWidget()
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(8, 0, 0, 0)
        status_layout.setSpacing(0)
        self.status = StatusDot("Starting…", colors["text_mute"])
        status_layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignVCenter)
        status_layout.addStretch(1)
        layout.addWidget(status_row)

        self.set_status("Online", colors["success"])
        self.set_active("dashboard")

    # -- public ------------------------------------------------------------
    def set_active(self, key: str) -> None:
        for name, button in self._buttons.items():
            button.set_active(name == key)

    def set_status(self, text: str, colour: str) -> None:
        self.status.set_status(text, colour)

    def set_theme_colors(self, colours: dict[str, str]) -> None:
        self._colours = colours
        self.setStyleSheet(
            f"#Sidebar {{ background: {colours['sidebar']}; "
            f"border-right: 1px solid {colours['border_soft']}; }}"
        )
        for key, button in self._buttons.items():
            glyph = dict(
                (k, g) for k, _l, g in PAGES
            ).get(key, "settings" if key == "settings" else "dashboard")
            button.setIcon(icon(glyph, colours["text_dim"], 18))
