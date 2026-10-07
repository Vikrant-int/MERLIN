"""Application bootstrap: build the window, start the backend, run the loop.

Nothing here blocks. `state.start()` only kicks off the thread that imports
`main`; the UI finds out whether that worked from `SpeechEngine.ready` or
`.failed`, which is why the window can be shown immediately.
"""
from __future__ import annotations

import sys


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Stable taskbar/grouping identity; purely cosmetic and never fatal.
    try:
        import ctypes  # noqa: PLC0415

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MERLIN.Desktop"
        )
    except Exception:
        pass

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import APP_NAME, APP_TAGLINE, APP_VERSION
    from .state import AppState
    from .theme import apply_theme
    from .window import MainWindow

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    app.setOrganizationDomain("merlin.local")
    # Hiding to tray must not look like "the app quit" to Windows.
    app.setQuitOnLastWindowClosed(False)

    window: MainWindow | None = None
    state: AppState | None = None
    code = 1

    try:
        state = AppState()
        colors = apply_theme(app, state.theme)
        window = MainWindow(state, colors)
        window.show()
        state.start()
        code = int(app.exec())
    except Exception as exc:  # pragma: no cover - last line of defence
        try:
            QMessageBox.critical(
                None,
                f"{APP_NAME} couldn't start",
                f"{APP_NAME} {APP_VERSION} hit an unexpected problem and "
                f"couldn't continue.\n\n{type(exc).__name__}: {exc}\n\n"
                f"{APP_TAGLINE}.",
            )
        except Exception:
            pass
        code = 1
    finally:
        if window is not None:
            try:
                window.teardown()
            except Exception:
                pass
        elif state is not None:
            try:
                state.shutdown()
            except Exception:
                pass

    return code
