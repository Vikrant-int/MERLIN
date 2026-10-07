"""Microphone handling for the UI, driven by the existing backend.

Nothing here decides on its own whether a microphone works: device ranking,
the liveness gates and the wake-word rule all come from `main.py`. This
service only sequences those calls on a dedicated audio thread and reports
what the backend concluded, so the UI can never claim audio is working when
it is not.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Signal

from .audio_lock import DEVICE_LOCK
from .core import SpeechEngine, TaskRunner, backend_ready, get_main

# States surfaced to the Voice page.
READY = "READY"
LISTENING = "LISTENING"
PROCESSING = "PROCESSING"
NO_MICROPHONE = "NO MICROPHONE"
DISCONNECTED = "DISCONNECTED"
ERROR = "ERROR"

_AUTO = -1  # "let MERLIN choose", i.e. no MIC_DEVICE_INDEX override


def open_sound_settings() -> bool:
    """Open the Windows sound control panel (Recording tab is manual)."""
    try:
        subprocess.Popen(["control.exe", "mmsys.cpl"])
        return True
    except Exception:
        return False


class VoiceService(QObject):
    """Owns the microphone: enumeration, probing and the listen loop."""

    stateChanged = Signal(str)            # one of the state constants above
    statusChanged = Signal(str)           # friendly sentence for the page
    devicesReady = Signal(object)         # list[dict]
    selectedChanged = Signal(int, str)    # index, human name
    heard = Signal(str)                   # an utterance that was transcribed
    heardOnce = Signal(str)               # one-shot result for the Chat page
    probeFinished = Signal(bool, str, float)  # ok, message, level
    jobFinished = Signal(str, bool, str)  # tag, ok, message

    def __init__(self, speech: SpeechEngine, parent: QObject | None = None):
        super().__init__(parent)
        self._speech = speech
        self._runner = TaskRunner(self, threads=2)
        self._runner.finished.connect(self._on_task)

        self._state = READY
        self._status = "Ready when you are."
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._once: threading.Thread | None = None
        self._wake_required = True
        self._selected = _AUTO
        self._selected_name = ""
        self._devices: list[dict] = []
        self._has_had_device = False
        self._listing = False

    # -- state -------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def status(self) -> str:
        return self._status

    @property
    def listening(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def busy_audio(self) -> bool:
        """True while any thread holds the microphone."""
        for thread in (self._thread, self._once):
            if thread is not None and thread.is_alive():
                return True
        return False

    @property
    def wake_required(self) -> bool:
        return self._wake_required

    @property
    def selected_index(self) -> int:
        return self._selected

    @property
    def selected_name(self) -> str:
        return self._selected_name

    @property
    def devices(self) -> list[dict]:
        return list(self._devices)

    def _set_state(self, state: str, status: str | None = None) -> None:
        changed = state != self._state
        self._state = state
        if status is not None:
            self._status = status
        if changed or status is not None:
            self.stateChanged.emit(state)
            self.statusChanged.emit(self._status)

    # -- devices -----------------------------------------------------------
    def refresh_devices(self) -> None:
        """Rescan inputs, unless a capture already owns the device.

        Enumerating while the microphone is open would both block on the
        device lock and risk showing a list that Windows has since
        renumbered, so during a capture the current list is simply repeated.
        """
        if self.busy_audio:
            self.devicesReady.emit(list(self._devices))
            return
        if not backend_ready(0):
            # `main` is not imported yet; AppState refreshes the moment it
            # is, so asking now would only produce a failed probe.
            self.devicesReady.emit(list(self._devices))
            return
        if self._listing:
            return
        self._listing = True
        self._runner.submit("voice.devices", self._list_devices_blocking)

    @staticmethod
    def _list_devices_blocking() -> list[dict]:
        # PortAudio's initialiser is not thread-safe, and several pages ask
        # for the device list at the same moment the backend comes up.
        with DEVICE_LOCK:
            backend = get_main()
            try:
                import mic_check  # noqa: PLC0415 - safe: work sits in main()
            except Exception:
                mic_check = None

            out = []
            for index, name in backend.candidate_devices():
                rate = 0
                if mic_check is not None:
                    try:
                        rate = mic_check.device_rate(index)
                    except Exception:
                        rate = 0
                out.append(
                    {
                        "index": index,
                        "name": name,
                        "rate": rate,
                        "real": backend.is_real_microphone(name),
                    }
                )
            return out

    def select_device(self, index: int) -> None:
        """Pin an input device using the backend's own MIC_DEVICE_INDEX."""
        self._selected = int(index)
        if self._selected == _AUTO:
            os.environ.pop("MIC_DEVICE_INDEX", None)
            self._selected_name = "Automatic (MERLIN chooses)"
        else:
            os.environ["MIC_DEVICE_INDEX"] = str(self._selected)
            for device in self._devices:
                if device["index"] == self._selected:
                    self._selected_name = device["name"]
                    break
            else:
                self._selected_name = f"Device {self._selected}"
        self.selectedChanged.emit(self._selected, self._selected_name)
        if self.busy_audio:
            # Restart so an active loop picks up the new device.
            self.stop()

    def set_wake_required(self, value: bool) -> None:
        self._wake_required = bool(value)

    # -- probing -----------------------------------------------------------
    def probe(self) -> None:
        """Ask the backend whether any input actually carries live audio."""
        if not backend_ready(30):
            self.probeFinished.emit(False, "MERLIN's backend did not start.", 0.0)
            return
        if self.busy_audio:
            self.probeFinished.emit(False, "Stop listening before probing.",
                                     0.0)
            return
        self._set_state(PROCESSING, "Checking your input devices…")
        self._runner.submit("voice.probe", self._probe_blocking)

    @staticmethod
    def _probe_blocking():
        with DEVICE_LOCK:
            backend = get_main()
            index, name = backend.find_working_microphone()
            if index is None:
                return (False, "", 0.0)

            # find_working_microphone() prints the level but does not return
            # it, so measure the winner once more to show a number on screen.
            level = 0.0
            try:
                source = backend.open_microphone(index)
                try:
                    level = backend.measure_device(source) or 0.0
                finally:
                    backend.close_microphone(source)
            except Exception:
                level = 0.0
            return (True, name or "", float(level), int(index))

    def _on_task(self, tag: str, ok: bool, payload) -> None:
        if tag == "voice.devices":
            # Always release the "a scan is already running" flag first, so
            # an enumeration failure cannot leave refresh permanently stuck.
            self._listing = False
            if ok:
                self._devices = list(payload or [])
                self.devicesReady.emit(self._devices)
                if not self.listening:
                    if not self._devices:
                        self._set_state(
                            NO_MICROPHONE,
                            "No microphone was detected. Connect one, then refresh.",
                        )
                    elif self._state in (NO_MICROPHONE, DISCONNECTED, ERROR):
                        self._set_state(READY, "Ready when you are.")
            return

        if tag == "voice.probe":
            if not ok:
                self._set_state(ERROR, str(payload))
                self.probeFinished.emit(False, str(payload), 0.0)
                return
            # payload is (ok, name, level) or (False, "", 0.0)
            probe_ok, name, level = payload[0], payload[1], payload[2]
            index = payload[3] if len(payload) > 3 else -1
            if probe_ok:
                self._has_had_device = True
                message = (
                    f"Device passes MERLIN's liveness probe: {name} "
                    f"(level {level:.0f})."
                )
                self._set_state(READY, message)
                self.probeFinished.emit(True, message, level)
                if index >= 0:
                    self.selectedChanged.emit(index, name)
            else:
                has_devices = bool(self._devices)
                state = DISCONNECTED if has_devices else NO_MICROPHONE
                message = (
                    "Your microphone is connected but is not delivering live "
                    "audio. Check it in Windows Sound settings."
                    if has_devices
                    else "No microphone was detected. Connect one, then refresh."
                )
                self._set_state(state, message)
                self.probeFinished.emit(False, message, 0.0)
            return

        if tag == "voice.stop":
            self.jobFinished.emit(tag, ok, str(payload) if payload else "")

    # -- listen loop -------------------------------------------------------
    def start(self) -> None:
        if self.listening:
            return
        if not backend_ready(30):
            self._set_state(ERROR, "MERLIN's backend did not start.")
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="merlin-listen"
        )
        self._thread.start()

    def stop(self, status: str = "Stopping…") -> None:
        self._stop.set()
        if self._thread is None:
            self._set_state(READY, "Ready when you are.")
            return
        self._set_state(self._state, status)

    def shutdown(self) -> None:
        """Stop listening and release the microphone, bounded in time.

        One shared deadline for both threads rather than one join each: a
        capture already inside ``recognizer.listen()`` can take ~15 s to
        return on its own, and quitting must never turn that into a 30 s
        freeze of the GUI thread.
        """
        self._stop.set()
        deadline = time.monotonic() + 10
        for thread in (self._thread, self._once):
            if thread is not None and thread.is_alive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                thread.join(timeout=remaining)
        self._runner.shutdown(3000)

    # -- one-shot capture (Chat page microphone button) --------------------
    def listen_once(self) -> None:
        """Capture exactly one utterance and report it, without dispatching.

        Used by the Chat page's mic button: the result becomes draft text the
        user still has to send, so nothing is executed behind their back.
        """
        if self.busy_audio:
            self.heardOnce.emit("")
            self.statusChanged.emit(
                "MERLIN is already using the microphone."
            )
            return
        if not backend_ready(30):
            self.heardOnce.emit("")
            self.statusChanged.emit("MERLIN's backend did not start.")
            return
        self._once = threading.Thread(
            target=self._once_loop, daemon=True, name="merlin-once"
        )
        self._once.start()

    def _once_loop(self) -> None:
        try:
            backend = get_main()
            index, _name = self._resolve_device(backend)
            if index is None:
                self.heardOnce.emit("")
                return
            self._set_state(LISTENING, "Listening…")
            try:
                text = self._capture(backend, index, timeout=6, phrase=8)
            except Exception as exc:
                self._set_state(ERROR, f"{type(exc).__name__}: {exc}")
                self.heardOnce.emit("")
                return
            if not text:
                self._set_state(READY, "I didn't catch that.")
                self.heardOnce.emit("")
                return
            self.heard.emit(text)
            self._set_state(READY, "Ready when you are.")
            self.heardOnce.emit(text)
        except Exception as exc:
            self._set_state(ERROR, f"{type(exc).__name__}: {exc}")
            self.heardOnce.emit("")

    # -- the loop ----------------------------------------------------------
    def _loop(self) -> None:
        try:
            self._run_loop()
        except Exception as exc:  # never let the thread die silently
            self._set_state(ERROR, f"{type(exc).__name__}: {exc}")
        finally:
            if self._state not in (NO_MICROPHONE, DISCONNECTED, ERROR):
                self._set_state(READY, "Ready when you are.")

    def _run_loop(self) -> None:
        backend = get_main()
        index, name = self._resolve_device(backend)
        if index is None:
            return

        failures = 0
        misses = 0

        while not self._stop.is_set():
            # ---- phase 1: wake word -----------------------------------
            if self._wake_required:
                self._set_state(
                    LISTENING, 'Listening… say “Merlin” to wake me.'
                )
            else:
                self._set_state(LISTENING, "Listening…")

            try:
                text = self._capture(backend, index, timeout=5, phrase=6)
            except _NoDevice:
                failures += 1
                if failures >= 3:
                    self._set_state(
                        DISCONNECTED,
                        "The microphone stopped delivering audio.",
                    )
                    index, name = self._resolve_device(backend)
                    if index is None:
                        return
                    failures = 0
                continue
            except _MicGone as exc:
                self._set_state(DISCONNECTED, str(exc))
                return
            except Exception as exc:
                self._set_state(ERROR, f"{type(exc).__name__}: {exc}")
                return

            failures = 0
            if self._stop.is_set():
                break
            if not text:
                misses += 1
                continue
            misses = 0
            self.heard.emit(text)

            if self._wake_required and not backend.contains_wake_word(text):
                continue

            # ---- phase 2: confirm -------------------------------------
            ok, _ = self._speech.call(
                "voice.confirm",
                lambda b: b.speak("Yes master", force=True),
                timeout=20,
            )
            if not ok:
                # Speech engine unavailable: keep listening, but say so.
                self.statusChanged.emit(
                    "I can hear you, but speech output isn't responding."
                )

            # ---- phase 3: command -------------------------------------
            self._set_state(LISTENING, "Listening for your command…")
            try:
                command = self._capture(backend, index, timeout=6, phrase=8)
            except Exception as exc:
                if isinstance(exc, (_NoDevice, _MicGone)):
                    self._set_state(DISCONNECTED, str(exc) or "Microphone lost.")
                    return
                self._set_state(ERROR, f"{type(exc).__name__}: {exc}")
                return

            if self._stop.is_set():
                break
            if not command:
                self._set_state(READY, "I didn't catch a command.")
                continue

            self.heard.emit(command)
            self._dispatch(backend, command)

        self._set_state(READY, "Ready when you are.")

    # -- helpers -----------------------------------------------------------
    def _resolve_device(self, backend):
        self._set_state(PROCESSING, "Checking your input devices…")
        with DEVICE_LOCK:
            index, name = backend.find_working_microphone()
        if index is None:
            if not self._devices and self._has_had_device:
                state, message = DISCONNECTED, (
                    "Your microphone disconnected. Reconnect it and try again."
                )
            elif not self._devices:
                state, message = NO_MICROPHONE, (
                    "No microphone was detected. Connect one, then refresh."
                )
            else:
                state, message = DISCONNECTED, (
                    "Your microphone isn't delivering live audio. Check it in "
                    "Windows Sound settings, then try again."
                )
            self._set_state(state, message)
            return None, None
        self._has_had_device = True
        if name:
            self.selectedChanged.emit(index, name)
        return index, name

    @staticmethod
    def _capture(backend, index: int, timeout: int, phrase: int):
        """Open, listen once, recognise, close. Returns '' on silence.

        Held under the device lock for its whole duration: PortAudio must
        not be initialised or torn down underneath an open stream, and the
        Windows device list can renumber while a capture is in flight.
        """
        with DEVICE_LOCK:
            source = None
            try:
                source = backend.open_microphone(index)
            except backend.MicUnavailableError as exc:
                raise _MicGone(str(exc)) from exc
            except Exception as exc:
                raise _NoDevice() from exc

            try:
                try:
                    backend.recognizer.adjust_for_ambient_noise(
                        source, duration=1
                    )
                    audio = backend.recognizer.listen(
                        source, timeout=timeout, phrase_time_limit=phrase
                    )
                except backend.sr.WaitTimeoutError:
                    return ""
                try:
                    text = backend.recognizer.recognize_google(audio) or ""
                    return text.strip()
                except backend.sr.UnknownValueError:
                    return ""
                except backend.sr.RequestError as exc:
                    raise RuntimeError(
                        "Speech recognition is unavailable. "
                        "Check your connection."
                    ) from exc
            finally:
                backend.close_microphone(source)

    def _dispatch(self, backend, command: str) -> None:
        self._set_state(PROCESSING, "Working on it…")
        low = command.strip().lower().rstrip("?.!")
        if low in backend.EXIT_REQUESTS:
            # sys.exit() must never run inside the desktop process.
            self._stop.set()
            self._set_state(READY, "Shutdown requested — use Close to exit.")
            return

        ok, payload = self._speech.call(
            "voice.command",
            lambda b: b.processCommand(command),
            timeout=90,
        )
        if self._stop.is_set():
            return
        if not ok:
            text = str(payload or "")
            if text == "__exit__":
                self._set_state(READY, "Shutdown requested — use Close to exit.")
            else:
                self._set_state(
                    ERROR,
                    text or "That command could not be completed.",
                )
            return
        self._set_state(READY, "Ready when you are.")


class _MicGone(Exception):
    """The chosen device stopped working mid-session."""


class _NoDevice(Exception):
    """The device could not be opened at all."""
