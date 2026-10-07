"""News page: real NewsAPI headlines with explicit loading/empty/error states."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..components.async_image import AsyncImage
from ..components.common import Banner, EmptyState, IconButton
from services.news_service import news_info
from .base import PanelPage


class ArticleCard(QWidget):
    def __init__(self, article: dict, accent: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 13, 13, 15)
        layout.setSpacing(9)

        self._image = AsyncImage(accent)
        layout.addWidget(self._image)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        source = QLabel(article["source"])
        source.setStyleSheet(f"color:{accent}; font-size:11px; "
                             "font-weight:600; letter-spacing:0.6px;")
        meta.addWidget(source)
        if article.get("when"):
            when = QLabel(article["when"])
            when.setObjectName("Muted")
            meta.addWidget(when)
        meta.addStretch(1)
        layout.addLayout(meta)

        title = QLabel(article["title"])
        title.setWordWrap(True)
        title_font = title.font()
        title_font.setPixelSize(15)
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        title.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(title)

        description = article.get("description", "")
        if description:
            body = QLabel(description)
            body.setWordWrap(True)
            body.setObjectName("Sub")
            body.setStyleSheet("font-size:12.5px;")
            body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(body)

        layout.addStretch(1)

        if article.get("url"):
            open_button = QPushButton("Open article")
            open_button.clicked.connect(
                lambda _=False, url=article["url"]: self._open(url)
            )
            layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)

        initial = (article["source"] or "·")[:1]
        self._image.set_source(article.get("image", ""), initial)

    @staticmethod
    def _open(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))


class NewsView(PanelPage):
    def __init__(self, state, navigate, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state
        self._navigate = navigate
        self._service = state.news
        self._accent = "#4FD1FF"

        # ---- header ------------------------------------------------------
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(12)

        column = QVBoxLayout()
        column.setSpacing(4)
        title = QLabel("Latest News")
        title.setObjectName("H1")
        column.addWidget(title)
        self._subtitle = QLabel("Top headlines, straight from NewsAPI.")
        self._subtitle.setObjectName("Sub")
        column.addWidget(self._subtitle)
        header_layout.addLayout(column)
        header_layout.addStretch(1)

        self._refresh = IconButton("refresh", "#04121B", 17, 38)
        self._refresh.setObjectName("PrimaryIconButton")
        self._refresh.setToolTip("Refresh headlines")
        self._refresh.clicked.connect(self._service.refresh)
        header_layout.addWidget(self._refresh, 0, Qt.AlignmentFlag.AlignTop)
        self.layout.addWidget(header)

        # ---- banners / loading ---------------------------------------------
        self._banner = Banner("error")
        self.layout.addWidget(self._banner)

        self._loading = QWidget()
        loading_layout = QVBoxLayout(self._loading)
        loading_layout.setContentsMargins(0, 6, 0, 0)
        loading_layout.setSpacing(8)
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setFixedHeight(5)
        loading_layout.addWidget(self._bar)
        loading_label = QLabel("Fetching headlines…")
        loading_label.setObjectName("Muted")
        loading_layout.addWidget(loading_label)
        self.layout.addWidget(self._loading)
        self._loading.hide()

        # ---- articles ---------------------------------------------------------
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 4, 0, 0)
        self._grid.setSpacing(16)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._scroll.setWidget(self._grid_host)

        self._stack = QWidget()
        self._stack_layout = QVBoxLayout(self._stack)
        self._stack_layout.setContentsMargins(0, 0, 0, 0)
        self._stack_layout.setSpacing(0)
        self._stack_layout.addWidget(self._scroll, 1)
        self.layout.addWidget(self._stack, 1)

        self._empty = EmptyState(
            "No headlines yet.",
            "Press Refresh to ask NewsAPI for today's top stories.",
        )
        self._stack_layout.addWidget(self._empty)
        self._scroll.hide()

        # ---- wiring -------------------------------------------------------------
        self._service.busyChanged.connect(self._on_busy)
        self._service.finished.connect(self._on_finished)
        self._service.failed.connect(self._on_failed)

        self._state.backendReady.connect(self._on_backend_ready)
        self._sync_credentials()

    # -- credential banner -------------------------------------------------
    def _sync_credentials(self) -> None:
        info = news_info()
        if info.get("starting"):
            # The backend has not looked at NEWS_API_KEY yet; showing
            # "isn't configured now" would be a guess, not a fact.
            self._banner.clear()
            self._set_empty(True)
        elif not info["configured"]:
            self._on_failed(info["detail"] or (
                "News API key isn't configured yet, so headlines are "
                "unavailable. Set NEWS_API_KEY and restart MERLIN."
            ))
        else:
            self._banner.clear()
            self._set_empty(True)

    def _on_backend_ready(self) -> None:
        self._sync_credentials()

    # -- theme -------------------------------------------------------------
    def apply_theme(self, colours: dict[str, str]) -> None:
        self._accent = colours.get("accent", "#4FD1FF")

    # -- actions ------------------------------------------------------------
    def on_page_enter(self, payload: dict | None = None) -> None:
        if payload and payload.get("refresh"):
            self._service.refresh()

    # -- states ----------------------------------------------------------------
    def _on_busy(self, busy: bool) -> None:
        self._loading.setVisible(busy)
        self._refresh.setEnabled(not busy)

    def _on_finished(self, articles: object) -> None:
        self._banner.clear()
        self._rebuild(list(articles or []))

    def _on_failed(self, message: str) -> None:
        self._loading.hide()
        self._refresh.setEnabled(True)
        self._banner.show_message(message)
        self._rebuild([])

    def _set_empty(self, show_empty: bool) -> None:
        self._empty.setVisible(show_empty)
        self._scroll.setVisible(not show_empty)

    # -- rendering ------------------------------------------------------------
    def _rebuild(self, articles: list[dict]) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._set_empty(not articles)
        for index, article in enumerate(articles):
            card = ArticleCard(article, self._accent)
            self._grid.addWidget(card, index // 2, index % 2)
