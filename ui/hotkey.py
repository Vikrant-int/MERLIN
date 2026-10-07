"""Optional system-wide hotkey, registered through the Windows API.

Off by default, and every failure path degrades to "the hotkey is
unavailable" rather than raising -- a missing registration must never stop
MERLIN from starting.

With a ``NULL`` window handle, ``RegisterHotKey`` posts ``WM_HOTKEY`` to the
registering thread's own queue, which is Qt's GUI thread, so a native event
filter is all that is needed to receive it. No polling, no hooks, no
injected input: that is what makes it non-fragile.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
HOTKEY_ID = 0x4D45  # arbitrary but unique within this process

COMBO_LABEL = "Ctrl+Alt+M"
VK_M = 0x4D


def _win32():
    import ctypes  # noqa: PLC0415

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_uint),
            ("wParam", ctypes.c_wparam),
            ("lParam", ctypes.c_lparam),
            ("time", ctypes.c_uint32),
            ("pt", POINT),
            ("lPrivate", ctypes.c_uint32),
        ]

    return ctypes, MSG


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner: "GlobalHotkey"):
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, eventType, message):
        try:
            kind = eventType.decode() if isinstance(eventType, bytes) \
                else str(eventType)
            if kind not in ("windows_generic_MSG", "windows_dispatcher_MSG"):
                return False, 0

            ctypes, MSG = _win32()
            try:
                address = int(message)
            except (TypeError, ValueError):
                address = message.address()
            msg = MSG.from_address(address)
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._owner._fire()
                return True, 0
        except Exception:
            # Never let a malformed event take the application down.
            return False, 0
        return False, 0


class GlobalHotkey(QObject):
    """Registers Ctrl+Alt+M and emits once per press while enabled."""

    activated = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._registered = False
        self._reason = "The hotkey is off."
        self._filter: _Filter | None = None
        self._app = None

    @property
    def registered(self) -> bool:
        return self._registered

    @property
    def reason(self) -> str:
        return self._reason

    def enable(self, app) -> bool:
        """Try to register the hotkey; ``app`` is the QApplication."""
        if self._registered:
            return True
        try:
            import sys  # noqa: PLC0415

            if sys.platform != "win32":
                self._reason = "Global hotkeys are Windows-only."
                return False

            import ctypes  # noqa: PLC0415

            user32 = ctypes.windll.user32
            ok = user32.RegisterHotKey(
                None, HOTKEY_ID,
                MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_M,
            )
            if not ok:
                self._reason = "Ctrl+Alt+M is already used by another app."
                return False

            self._filter = _Filter(self)
            app.installNativeEventFilter(self._filter)
            self._app = app
            self._registered = True
            self._reason = "Ctrl+Alt+M is active."
            return True
        except Exception as exc:
            self._reason = f"The hotkey could not be registered ({exc})."
            self._registered = False
            return False

    def disable(self) -> None:
        if not self._registered:
            return
        try:
            import ctypes  # noqa: PLC0415

            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception:
            pass
        if self._app is not None and self._filter is not None:
            try:
                self._app.removeNativeEventFilter(self._filter)
            except Exception:
                pass
        self._filter = None
        self._app = None
        self._registered = False
        self._reason = "The hotkey is off."

    def _fire(self) -> None:
        try:
            self.activated.emit()
        except Exception:
            pass
