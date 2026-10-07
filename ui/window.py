"""The frameless MERLIN window: title bar, navigation rail, page stack, tray.

Two things here are deliberately OS-provided rather than reimplemented:
moving/resizing goes through ``startSystemMove``/``startSystemResize`` so
Windows snap layouts keep working, and hiding-to-tray is a plain ``hide()``
so the taskbar state stays consistent.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMenu,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, APP_TAGLINE, APP_VERSION
from .components.icons import logo
from .components.sidebar import Sidebar
from .components.title_bar import TitleBar
from .state import AppState
from .theme import PALETTES, apply_theme
from .views import (
    ChatView,
    DashboardView,
    MusicView,
    NewsView,
    SettingsView,
    VoiceView,
)

#: Width of the invisible band along each window edge that starts a resize.
EDGE = 7

_PAGE_ORDER = ("dashboard", "chat", "voice", "news", "music", "settings")


class MainWindow(QFrame):
    """Frameless application window."""

    def __init__(self, state: AppState, colors: dict[str, str],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state
        self._colours = colors
        self._current = "dashboard"
        self._torn_down = False
        self._filter_installed = False
        self._tray: QSystemTrayIcon | None = None

        self.setWindowTitle(f"{APP_NAME} — {APP_TAGLINE}")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setObjectName("MainWindowFrame")
        self.setWindowIcon(QIcon(logo(64, colors["accent"])))
        self.setMinimumSize(1000, 650)
        self.resize(1240, 800)
        self._apply_frame_style(colors)

        # ---- chrome -----------------------------------------------------
        self._title_bar = TitleBar(self, colors["accent"])

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = Sidebar(colors)
        self._stack = QStackedWidget()
        body_layout.addWidget(self._sidebar)
        body_layout.addWidget(self._stack, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        root.addWidget(self._title_bar)
        root.addWidget(body, 1)

        # ---- pages --------------------------------------------------------
        self._views: dict[str, QWidget] = {
            "dashboard": DashboardView(state, self.navigate),
            "chat": ChatView(state, self.navigate),
            "voice": VoiceView(state, self.navigate),
            "news": NewsView(state, self.navigate),
            "music": MusicView(state, self.navigate),
            "settings": SettingsView(state, self.navigate),
        }
        for key in _PAGE_ORDER:
            self._stack.addWidget(self._views[key])

        # ---- wiring ---------------------------------------------------------
        self._sidebar.navigate.connect(self.navigate)
        self._sidebar.settingsRequested.connect(
            lambda: self.navigate("settings")
        )

        state.coreStateChanged.connect(lambda *_: self._sync_status())
        state.onlineChanged.connect(lambda *_: self._sync_status())
        state.themeChanged.connect(self._on_theme)
        state.assistant.replyReady.connect(self._maybe_notify)

        self._sync_status()
        self.navigate("dashboard")

        # Deferred so the window paints first: registering a hotkey and
        # showing an icon are both cheap, but neither should delay first
        # paint, and neither may ever stop the app from starting.
        QTimer.singleShot(0, self._late_init)

    # ------------------------------------------------------------------
    # late, non-essential startup
    # ------------------------------------------------------------------
    def _late_init(self) -> None:
        self._install_tray()
        if bool(self._state.settings.get("hotkey", False)):
            self._state.hotkey.enable(QApplication.instance())

    def _install_tray(self, available: bool | None = None) -> None:
        """Create the tray icon and its menu.

        ``available`` exists so tests can exercise the real menu even when
        the platform (offscreen) reports no system tray.
        """
        try:
            if available is None:
                available = QSystemTrayIcon.isSystemTrayAvailable()
            if not available:
                return

            self._tray = QSystemTrayIcon(
                QIcon(logo(64, self._colours["accent"])), self
            )
            self._tray.setToolTip(f"{APP_NAME} {APP_VERSION}")

            menu = QMenu()
            open_action = menu.addAction(f"Open {APP_NAME}")
            voice_action = menu.addAction("Voice command")
            settings_action = menu.addAction("Settings")
            menu.addSeparator()
            quit_action = menu.addAction("Quit")

            open_action.triggered.connect(self.show_from_tray)
            voice_action.triggered.connect(
                lambda: self.navigate("voice", {"listen": True})
            )
            settings_action.triggered.connect(
                lambda: self.navigate("settings")
            )
            quit_action.triggered.connect(self.quit)

            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._on_tray_activation)
            self._tray.show()
        except Exception:
            # The tray is a convenience; losing it must not stop the app.
            self._tray = None

    def _on_tray_activation(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_from_tray()

    def show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def navigate(self, key: str, payload: dict | None = None) -> None:
        view = self._views.get(key)
        if view is None:
            return
        self._stack.setCurrentWidget(view)
        self._sidebar.set_active(key)
        self._current = key

        enter = getattr(view, "on_page_enter", None)
        if callable(enter):
            try:
                enter(payload)
            except Exception:
                pass
        if key == "chat":
            focus = getattr(view, "focus_input", None)
            if callable(focus):
                focus()

    @property
    def current_page(self) -> str:
        return self._current

    # ------------------------------------------------------------------
    # status + theme
    # ------------------------------------------------------------------
    def _sync_status(self) -> None:
        tokens = PALETTES.get(self._state.theme, PALETTES["dark"])
        if self._state.starting:
            self._sidebar.set_status("Starting…", tokens["text_mute"])
        elif not self._state.online:
            self._sidebar.set_status("Offline", tokens["danger"])
        elif self._state.error:
            self._sidebar.set_status("Attention", tokens["warning"])
        else:
            self._sidebar.set_status("Online", tokens["success"])

    def _apply_frame_style(self, colors: dict[str, str]) -> None:
        self.setStyleSheet(
            f"#MainWindowFrame {{ background: {colors['window']};"
            f" border: 1px solid {colors['border']}; }}"
        )

    def _on_theme(self, name: str) -> None:
        app = QApplication.instance()
        colors = apply_theme(app, name) if app is not None else PALETTES[name]
        self._colours = colors
        self._apply_frame_style(colors)
        self._sidebar.set_theme_colors(colors)
        for view in self._views.values():
            apply = getattr(view, "apply_theme", None)
            if callable(apply):
                try:
                    apply(colors)
                except Exception:
                    pass
        self._sync_status()

    def _sync_maximized(self, maximized: bool) -> None:
        self._title_bar.set_maximized(maximized)

    # ------------------------------------------------------------------
    # notifications
    # ------------------------------------------------------------------
    def _maybe_notify(self, _user: str, reply: str) -> None:
        if not bool(self._state.settings.get("notifications", True)):
            return
        if self.isVisible():
            return
        if self._tray is None:
            return
        try:
            text = " ".join((reply or "").split())
            self._tray.showMessage(
                APP_NAME,
                text[:180] + ("…" if len(text) > 180 else ""),
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # edge resizing
    # ------------------------------------------------------------------
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        try:
            kind = event.type()
            if self.isMaximized() or not self.isVisible():
                return super().eventFilter(obj, event)
            if not isinstance(obj, QWidget) or obj.window() is not self:
                return super().eventFilter(obj, event)

            if kind == QEvent.Type.MouseButtonPress:
                mouse = event  # type: QMouseEvent
                if mouse.button() == Qt.MouseButton.LeftButton:
                    edges = self._edges_at(mouse.globalPosition().toPoint())
                    if edges:
                        handle = self.windowHandle()
                        if handle is not None and handle.startSystemResize(
                                edges):
                            event.accept()
                            return True
            elif kind == QEvent.Type.MouseMove:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    return super().eventFilter(obj, event)
                edges = self._edges_at(event.globalPosition().toPoint())
                self.setCursor(self._cursor_for(edges)) if edges else \
                    self.unsetCursor()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _edges_at(self, global_pos):
        geo = self.geometry()
        result = Qt.Edges()
        if global_pos.x() - geo.left() <= EDGE:
            result |= Qt.Edges.LeftEdge
        if geo.right() - global_pos.x() <= EDGE:
            result |= Qt.Edges.RightEdge
        if global_pos.y() - geo.top() <= EDGE:
            result |= Qt.Edges.TopEdge
        if geo.bottom() - global_pos.y() <= EDGE:
            result |= Qt.Edges.BottomEdge
        return result

    @staticmethod
    def _cursor_for(edges):
        if not edges:
            return None
        left, right = bool(edges & Qt.Edges.LeftEdge), \
            bool(edges & Qt.Edges.RightEdge)
        top, bottom = bool(edges & Qt.Edges.TopEdge), \
            bool(edges & Qt.Edges.BottomEdge)
        if left and top or right and bottom:
            return Qt.CursorShape.SizeFDiagCursor
        if right and top or left and bottom:
            return Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        if top or bottom:
            return Qt.CursorShape.SizeVerCursor
        return None

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_maximized(self.isMaximized())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        app = QApplication.instance()
        if app is not None and not self._filter_installed:
            self._filter_installed = True
            app.installEventFilter(self)

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        minimise_to_tray = bool(
            self._state.settings.get("minimize_to_tray", True)
        )
        if (not self._torn_down and minimise_to_tray
                and self._tray is not None and self._tray.isVisible()):
            event.ignore()
            self.hide()
            return
        event.accept()
        self._teardown()
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

    def teardown(self) -> None:
        """Public idempotent shutdown hook for the application runner."""
        self._teardown()

    def quit(self) -> None:
        """Leave regardless of the minimise-to-tray preference."""
        self._teardown()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _teardown(self) -> None:
        if self._torn_down:
            return
        self._torn_down = True
        try:
            self._state.hotkey.disable()
        except Exception:
            pass
        try:
            if self._tray is not None:
                self._tray.hide()
        except Exception:
            pass
        try:
            self._state.shutdown()
        except Exception:
            pass

    # Keep the old name available for anything that expected it.
    @property
    def title_bar(self) -> TitleBar:
        return self._title_bar
