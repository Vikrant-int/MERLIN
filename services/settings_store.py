"""Session preferences (never credentials) and Windows startup registration.

Preferences live in ``%LOCALAPPDATA%\\MERLIN\\settings.json`` so nothing is
written into the repository. Secrets are deliberately not part of this file
and are never read or written here -- they come from the environment.
"""
from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import QObject, Signal

DEFAULTS: dict[str, object] = {
    "theme": "dark",
    "start_with_windows": False,
    "minimize_to_tray": True,
    "notifications": True,
    "wake_word": True,
    "hotkey": False,
    "voice_volume": 100,
    "voice_rate": 200,
}

# Keys that must never appear in this file, even by accident.
FORBIDDEN = ("api_key", "key", "token", "secret", "password")


def settings_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    directory = os.path.join(base, "MERLIN")
    return os.path.join(directory, "settings.json")


class SettingsStore(QObject):
    changed = Signal(str, object)

    def __init__(self, path: str | None = None,
                 parent: QObject | None = None):
        super().__init__(parent)
        # Guard against the classic Qt mistake of passing a parent as the
        # first positional argument; a non-string path would silently break
        # every save (the file I/O is best-effort by design).
        if not isinstance(path, str):
            path = None
        self._path = path or settings_path()
        self._values: dict[str, object] = dict(DEFAULTS)
        self._load()

    # -- storage -----------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if key not in DEFAULTS:
                continue
            if isinstance(DEFAULTS[key], bool):
                self._values[key] = bool(value)
            elif isinstance(DEFAULTS[key], int):
                try:
                    self._values[key] = int(value)
                except (TypeError, ValueError):
                    pass
            elif isinstance(DEFAULTS[key], str):
                self._values[key] = str(value)

    def _save(self) -> None:
        try:
            directory = os.path.dirname(self._path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            # Defence in depth: refuse to persist anything key-shaped.
            payload = {
                k: v for k, v in self._values.items()
                if not any(bad in k.lower() for bad in FORBIDDEN)
            }
            with open(self._path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
        except Exception:
            # Losing a preference must never break the application.
            pass

    # -- access ------------------------------------------------------------
    def get(self, key: str, default=None):
        return self._values.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        if key not in DEFAULTS:
            return
        current = self._values.get(key)
        if current == value:
            return
        self._values[key] = value
        self._save()
        self.changed.emit(key, value)

    @property
    def path(self) -> str:
        return self._path


# --------------------------------------------------------------------------
# Windows startup
# --------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_VALUE_NAME = "MERLIN"


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.abspath(sys.argv[0]) if sys.argv else ""
    return f'"{sys.executable}" "{script}"'


def startup_enabled() -> bool:
    try:
        import winreg  # noqa: PLC0415

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_VALUE_NAME)
        return True
    except Exception:
        return False


def set_startup(enabled: bool) -> bool:
    """Register (or remove) MERLIN in the current user's Run key."""
    try:
        import winreg  # noqa: PLC0415

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_VALUE_NAME, 0, winreg.REG_SZ,
                                  startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False
