"""Backend handle, background task runner and the speech thread.

Why a dedicated speech thread
-----------------------------
`main.py` creates a `pyttsx3` engine at import time, and SAPI delivers its
completion events through the message queue of the thread that created it.
Running `speak()` anywhere else leaves `runAndWait()` waiting for an event
that never arrives, so the call hangs forever. Creating a *second* engine on
another thread hangs too.

So the rule is: `main` is imported exactly once, on `SpeechEngine`'s own
thread, and every call that can touch the speech engine (`speak`,
`processCommand`) is marshalled onto that same thread. Everything that is
provably COM-free (Gemini, NewsAPI, device enumeration) runs on a normal
thread pool instead, which keeps the GUI responsive.
"""
from __future__ import annotations

import queue
import sys
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

# Set once `main` has been imported on the speech thread. Anything that needs
# the backend waits on this rather than importing `main` itself, because the
# importing thread is what ends up owning the speech engine.
BACKEND_READY = threading.Event()
BACKEND_ERROR: list[str] = []


class BackendNotReady(RuntimeError):
    """The backend has not finished importing yet (or it failed to)."""


def get_main():
    """The existing backend module -- never an import.

    Importing `main` is what creates the pyttsx3 engine, so it may only ever
    happen on the speech thread (see the module docstring). A helper that
    lazily imported would hand ownership of the speech engine to whichever
    thread asked first -- and in the desktop app that is the GUI thread,
    which both freezes the window for the length of the import and breaks
    every later `speak()`.

    So this returns the module only after the speech thread has published it,
    and raises :class:`BackendNotReady` before that. Every caller already
    reports a friendly failure when this happens.
    """
    if BACKEND_READY.is_set():
        module = sys.modules.get("main")
        if module is not None:
            return module
        raise BackendNotReady(
            BACKEND_ERROR[-1] if BACKEND_ERROR
            else "MERLIN's backend could not be loaded."
        )
    raise BackendNotReady("MERLIN's backend is still starting up.")


def backend_ready(timeout: float = 90.0) -> bool:
    return BACKEND_READY.wait(timeout)


# --------------------------------------------------------------------------
# Speech thread
# --------------------------------------------------------------------------
class SpeechEngine(QObject):
    """Serialises every speech-related job onto one worker thread."""

    ready = Signal()
    failed = Signal(str)
    #: tag, ok, payload  -- payload is the result or an error description
    finished = Signal(str, bool, object)
    busyChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._q: "queue.Queue[tuple[str, object] | None]" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="merlin-speech"
        )
        self._started = False
        self._busy = False
        # Result hand-off for the audio thread, which cannot wait on a Qt
        # signal (it would be queued back into the GUI thread).
        self._lock = threading.Lock()
        self._waiters: dict[str, list[threading.Event]] = {}
        self._last: dict[str, tuple[bool, object]] = {}

    # -- lifecycle ---------------------------------------------------------
    def start_async(self) -> None:
        """Start the speech thread without blocking the calling thread.

        This is what the GUI uses: importing `main` takes a few seconds, and
        the window shows itself (and a "Starting…" status) while it happens.
        """
        if not self._started:
            self._started = True
            self._thread.start()

    def start(self, timeout: float = 90.0) -> bool:
        """Start and block until the backend is ready (used by tests)."""
        self.start_async()
        return backend_ready(timeout)

    def shutdown(self, timeout: float = 5.0) -> None:
        if not self._started:
            return
        self._q.put(None)
        self._thread.join(timeout)

    @property
    def busy(self) -> bool:
        return self._busy

    # -- submission --------------------------------------------------------
    def submit(self, tag: str, fn) -> None:
        """Queue ``fn(backend)`` to run on the speech thread."""
        self._q.put((tag, fn))

    def speak(self, text: str, force: bool = False, tag: str = "speak") -> None:
        if text is None:
            return
        self.submit(tag, lambda backend: backend.speak(text, force=force))

    def wait_idle(self, timeout: float = 30.0) -> bool:
        """Block the *calling* (non-GUI) thread until the queue drains.

        Used by the audio thread when it only needs silence rather than a
        result. Never called from the GUI.
        """
        import time  # noqa: PLC0415

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._q.empty() and not self._busy:
                return True
            time.sleep(0.05)
        return self._q.empty() and not self._busy

    def call(self, tag: str, fn, timeout: float = 60.0) -> tuple[bool, object]:
        """Run ``fn(backend)`` on the speech thread and wait for its outcome.

        Returns ``(ok, payload)`` where payload is the result or a friendly
        error string. Only ever called from a worker thread, never the GUI.
        """
        waiter = threading.Event()
        with self._lock:
            self._waiters.setdefault(tag, []).append(waiter)
        self._q.put((tag, fn))

        if not waiter.wait(timeout):
            with self._lock:
                waiters = self._waiters.get(tag, [])
                if waiter in waiters:
                    waiters.remove(waiter)
            return False, "That took too long and was abandoned."

        with self._lock:
            return self._last.get(tag, (False, "No result was produced."))

    def _publish(self, tag: str, ok: bool, payload) -> None:
        with self._lock:
            self._last[tag] = (ok, payload)
            waiters = self._waiters.pop(tag, [])
        for waiter in waiters:
            waiter.set()

    # -- worker ------------------------------------------------------------
    def _run(self) -> None:
        try:
            import main as backend  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - import-time failure
            BACKEND_ERROR.append(f"{type(exc).__name__}: {exc}")
            BACKEND_READY.set()
            # Release anything already queued, or those callers hang forever.
            with self._lock:
                pending = [w for group in self._waiters.values() for w in group]
                self._waiters.clear()
            for waiter in pending:
                waiter.set()
            self.failed.emit(BACKEND_ERROR[-1])
            return

        BACKEND_READY.set()
        self.ready.emit()

        while True:
            job = self._q.get()
            if job is None:
                return
            tag, fn = job
            self._set_busy(True)
            try:
                result = fn(backend)
            except SystemExit:
                # `processCommand("quit")` calls sys.exit(); in a desktop app
                # that must not take the thread down.
                self._publish(tag, False, "__exit__")
                self.finished.emit(tag, False, "__exit__")
            except Exception as exc:
                self._publish(tag, False, f"{type(exc).__name__}: {exc}")
                self.finished.emit(tag, False, f"{type(exc).__name__}: {exc}")
            else:
                self._publish(tag, True, result)
                self.finished.emit(tag, True, result)
            finally:
                self._set_busy(False)

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit(value)


# --------------------------------------------------------------------------
# Thread pool for COM-free work (Gemini, NewsAPI, enumeration)
# --------------------------------------------------------------------------
class TaskSignals(QObject):
    done = Signal(str, bool, object)


class Task(QRunnable):
    def __init__(self, tag: str, fn):
        super().__init__()
        self.tag = tag
        self.fn = fn
        self.signals = TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:
            self._emit(False, f"{type(exc).__name__}: {exc}")
        else:
            self._emit(True, result)

    def _emit(self, ok: bool, payload) -> None:
        # A task can outlive its runner during shutdown; nobody needs the
        # result by then, and a deleted QObject must not raise in a worker.
        try:
            self.signals.done.emit(self.tag, ok, payload)
        except RuntimeError:
            pass


class TaskRunner(QObject):
    """Runs blocking work off the GUI thread and reports back by signal."""

    finished = Signal(str, bool, object)

    def __init__(self, parent: QObject | None = None, threads: int = 4):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, threads))
        self._live: set[Task] = set()

    def submit(self, tag: str, fn) -> None:
        task = Task(tag, fn)
        self._live.add(task)
        task.signals.done.connect(self._on_done)
        self._pool.start(task)

    @Slot(str, bool, object)
    def _on_done(self, tag: str, ok: bool, payload) -> None:
        # Drop the reference once the result has been handed to the GUI.
        for task in list(self._live):
            if task.tag == tag:
                self._live.discard(task)
                break
        self.finished.emit(tag, ok, payload)

    def wait(self, ms: int = 5000) -> bool:
        return self._pool.waitForDone(ms)

    def shutdown(self, ms: int = 4000) -> bool:
        """Drop queued work and wait a *bounded* time for running work.

        Bounded on purpose: a pool thread parked on the device lock must
        never be able to hang the application on exit.
        """
        try:
            self._pool.clear()
        except Exception:
            pass
        return self.wait(ms)
