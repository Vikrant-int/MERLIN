"""NewsAPI access for the UI, on top of the existing backend fetcher."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .core import BACKEND_ERROR, BACKEND_READY, TaskRunner, get_main

NOT_CONFIGURED = (
    "News API key isn't configured yet, so headlines are unavailable. "
    "Set NEWS_API_KEY and restart MERLIN."
)
NO_HEADLINES = "No headlines are available right now."
NO_CONNECTION = "Unable to connect to the news service."


def news_info() -> dict:
    """Non-sensitive NewsAPI status. The key value is never read out."""
    if not BACKEND_READY.is_set():
        # Asking now would import `main` on this (the GUI) thread.
        return {
            "configured": False,
            "available": False,
            "starting": not bool(BACKEND_ERROR),
            "country": "",
            "query": "",
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
            "country": "",
            "query": "",
            "detail": f"{type(exc).__name__}: {exc}",
        }

    configured = bool(getattr(backend, "NEWS_API_KEY", None))
    return {
        "configured": configured,
        "available": configured,
        "starting": False,
        "country": getattr(backend, "NEWS_COUNTRY", ""),
        "query": getattr(backend, "NEWS_QUERY", ""),
        "detail": "" if configured else NOT_CONFIGURED,
    }


def normalise(article) -> dict | None:
    """Turn one NewsAPI article into the shape the UI card expects."""
    if not isinstance(article, dict):
        return None
    title = (article.get("title") or "").strip()
    if not title or title.lower() == "[removed]":
        return None
    source = article.get("source")
    source_name = ""
    if isinstance(source, dict):
        source_name = (source.get("name") or "").strip()
    elif isinstance(source, str):
        source_name = source.strip()

    description = (article.get("description") or "").strip()
    url = (article.get("url") or "").strip()
    image = (article.get("urlToImage") or "").strip()
    published = (article.get("publishedAt") or "").strip()

    return {
        "title": title,
        "description": description,
        "source": source_name or "Unknown source",
        "url": url,
        "image": image,
        "published": published,
    }


def _when(published: str) -> str:
    """Short, human '2 h ago' style label from an ISO timestamp."""
    if not published:
        return ""
    try:
        from datetime import datetime, timezone

        stamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - stamp
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return stamp.strftime("%d %b")
        if seconds < 3600:
            return f"{max(1, seconds // 60)} min ago"
        if seconds < 86400:
            return f"{seconds // 3600} h ago"
        if seconds < 86400 * 7:
            return f"{seconds // 86400} d ago"
        return stamp.strftime("%d %b")
    except Exception:
        return ""


class NewsService(QObject):
    """Fetches headlines off the GUI thread and reports friendly states."""

    busyChanged = Signal(bool)
    finished = Signal(object)   # list[dict] of normalised articles
    failed = Signal(str)        # user-facing reason

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._runner = TaskRunner(self, threads=2)
        self._runner.finished.connect(self._on_task)
        self._busy = False
        self.articles: list[dict] = []

    @property
    def busy(self) -> bool:
        return self._busy

    def refresh(self) -> None:
        if self._busy:
            return
        info = news_info()
        if not info["available"]:
            # No point making a request with an absent key.
            self.failed.emit(info["detail"] or NOT_CONFIGURED)
            return

        self._busy = True
        self.busyChanged.emit(True)
        self._runner.submit("news.refresh", self._fetch_blocking)

    def _fetch_blocking(self):
        backend = get_main()
        return backend.fetch_news_articles()

    def _on_task(self, tag: str, ok: bool, payload) -> None:
        if tag != "news.refresh":
            return
        self._busy = False
        self.busyChanged.emit(False)

        if not ok:
            self.articles = []
            self.failed.emit(NO_CONNECTION)
            return
        if payload is None:
            # The backend returns None only when every request failed.
            self.articles = []
            self.failed.emit(NO_CONNECTION)
            return
        if not payload:
            self.articles = []
            self.failed.emit(NO_HEADLINES)
            return

        cards = []
        for raw in payload:
            card = normalise(raw)
            if card:
                card["when"] = _when(card["published"])
                cards.append(card)
        self.articles = cards
        if not cards:
            self.failed.emit(NO_HEADLINES)
            return
        self.finished.emit(cards)
