"""Desktop UI tests for MERLIN: startup, pages, failures, tray, responsiveness.

Runs headless (``QT_QPA_PLATFORM=offscreen``) so it works on CI and on a
machine with no display. It drives the *real* window, the *real* services and
the *real* backend; only the two external boundaries that cannot be
guaranteed on a test machine -- a working microphone and a configured API key
-- are replaced by explicit stubs, and those stubs are announced in the
output so nothing reads as a capability the product does not have.

Run with:   myprojectenv\\Scripts\\python.exe tests_ui.py
Exit code:  0 = every check passed, 1 = at least one failed.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import types

# Must be set before Qt is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SHOTS = os.path.join(
    os.environ.get("TEMP", ROOT), "merlin_ui_shots"
)

PAGES = ("dashboard", "chat", "voice", "news", "music", "settings")

_failures: list[str] = []
_uncaught: list[str] = []
_checks = 0
_keep: list = []          # holds widgets that must outlive a check


def ensure(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check(name: str, fn) -> bool:
    global _checks
    _checks += 1
    try:
        fn()
    except Exception as exc:
        _failures.append(name)
        detail = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        print(f"  [FAIL] {name}")
        print(f"         {detail}")
        traceback.print_exc()
        return False
    print(f"  [PASS] {name}")
    return True


def pump(seconds: float = 0.05) -> None:
    """Turn the event loop for a fixed wall-clock time."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.004)


def wait_until(predicate, timeout: float = 10.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def collect_text(root) -> list[str]:
    """Every user-visible string under ``root`` (labels, buttons, edits…).

    PySide6 exposes ``text``/``toolTip``/… as *methods*, so they have to be
    called; ``getattr`` alone would hand back a bound method and the whole
    scan would look like it found nothing.
    """
    from PySide6.QtWidgets import QWidget

    out: list[str] = []
    for widget in root.findChildren(QWidget):
        for attr in (
            "text", "toolTip", "statusTip", "placeholderText", "windowTitle",
            "currentText",
        ):
            value = getattr(widget, attr, None)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    value = None
            if isinstance(value, str) and value:
                out.append(value)
        getter = getattr(widget, "toPlainText", None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                value = ""
            if value:
                out.append(value)
    return out


# ==========================================================================
# 1. startup
# ==========================================================================
print("\n== startup ==")

from PySide6.QtCore import QTimer, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from services import assistant_service as asvc  # noqa: E402
from services import news_service as nsvc  # noqa: E402
from services import voice_service as vsvc  # noqa: E402
import services.core as coremod  # noqa: E402


# Record anything that escapes as an unhandled exception.
def _hook(kind, value, tb):  # noqa: ANN001
    _uncaught.append("".join(traceback.format_exception(kind, value, tb)))


def _thread_hook(args):  # noqa: ANN001
    _uncaught.append("".join(traceback.format_exception(
        args.exc_type, args.exc_value, args.exc_traceback)))


sys.excepthook = _hook
threading.excepthook = _thread_hook

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from ui import APP_NAME, APP_VERSION  # noqa: E402
from ui.state import AppState  # noqa: E402
from ui.theme import apply_theme  # noqa: E402
from ui.views.settings import SettingsView  # noqa: E402
from ui.window import MainWindow  # noqa: E402

state = AppState()
# The suite writes to the real settings file; put everything back afterwards.
_ORIGINAL_SETTINGS = {
    key: state.settings.get(key, default)
    for key, default in (
        ("minimize_to_tray", True),
        ("theme", "dark"),
    )
}
colors = apply_theme(app, state.theme)
window = MainWindow(state, colors)
window.show()
pump(0.2)

check("window is created and visible",
      lambda: ensure(window.isVisible(), "window is not visible"))
check("window is frameless",
      lambda: ensure(bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint),
                     "window has a system frame"))
check("window minimum size is at least 1000x650",
      lambda: ensure(window.minimumWidth() >= 1000
                     and window.minimumHeight() >= 650,
                     f"min {window.minimumWidth()}x{window.minimumHeight()}"))
check("window title names the product",
      lambda: ensure(APP_NAME in window.windowTitle(),
                     repr(window.windowTitle())))
check("window is resizable below its own size without collapsing",
      lambda: (window.resize(500, 400), pump(0.1),
               ensure(window.width() >= 1000,
                      f"width collapsed to {window.width()}"),
               window.resize(1240, 800), pump(0.1)))

# The backend import is the slow part (~3s); it must never block the GUI.
_ticks = {"n": 0}
tick_timer = QTimer()
tick_timer.setInterval(10)
tick_timer.timeout.connect(lambda: _ticks.__setitem__("n", _ticks["n"] + 1))
tick_timer.start()

_ticks["n"] = 0
_started = time.monotonic()
state.start()
start_elapsed = time.monotonic() - _started

settled = wait_until(lambda: not state.starting, timeout=90)
ticks_during_import = _ticks["n"]
tick_timer.stop()
print(f"       start() returned in {start_elapsed:.2f}s, GUI ticked "
      f"{ticks_during_import} times while the backend imported")
check("start() returns without blocking",
      lambda: ensure(start_elapsed < 1.0,
                     f"start() took {start_elapsed:.2f}s"))
check("GUI keeps running while the backend imports",
      lambda: ensure(ticks_during_import >= 30,
                     f"GUI ticked only {ticks_during_import} times "
                     "during the import"))
print(f"       backend settled={settled} starting={state.starting} "
      f"online={state.online} core={state.core_state}")
check("backend settles while the GUI keeps running",
      lambda: ensure(settled, "backend never finished starting"))
check("no backend import error",
      lambda: ensure(not coremod.BACKEND_ERROR, coremod.BACKEND_ERROR))
check("assistant core reaches a known state",
      lambda: ensure(state.core_state in
                     ("IDLE", "LISTENING", "THINKING", "SPEAKING",
                      "ERROR", "OFFLINE"),
                     state.core_state))
pump(0.3)
check("sidebar reports Online once the backend is up",
      lambda: ensure(
          any("Online" in t for t in collect_text(window._sidebar)),
          f"sidebar text: {collect_text(window._sidebar)!r}"))


# ==========================================================================
# 2. pages and navigation
# ==========================================================================
print("\n== pages and navigation ==")

check("stack holds all six pages",
      lambda: ensure(window._stack.count() == len(PAGES),
                     f"{window._stack.count()} pages"))
check("sidebar lists five destinations",
      lambda: ensure(len(window._views) == len(PAGES),
                     f"{len(window._views)} views"))

for key in PAGES:
    def _go(k=key):
        window.navigate(k)
        pump(0.05)
        ensure(window.current_page == k,
               f"current_page is {window.current_page!r}")
        ensure(window._stack.currentWidget() is window._views[k],
               "stack is showing the wrong widget")
    check(f"navigate to {key}", _go)


def _sidebar_signal():
    window.navigate("dashboard")
    pump(0.05)
    window._sidebar.navigate.emit("news")
    pump(0.1)
    ensure(window.current_page == "news",
           f"current_page is {window.current_page!r}")
    window._sidebar.settingsRequested.emit()
    pump(0.1)
    ensure(window.current_page == "settings",
           f"current_page is {window.current_page!r}")
check("sidebar signals drive navigation", _sidebar_signal)


def _page_payload():
    # The Voice page forwards {"listen": True} to the service; stub `start`
    # so this stays a wiring test instead of grabbing the microphone.
    real_start = state.voice.start
    seen = []
    state.voice.start = lambda: seen.append("start")
    try:
        window.navigate("voice", {"listen": True})
        pump(0.1)
        ensure(seen == ["start"], f"voice.start called {len(seen)} times")
    finally:
        state.voice.start = real_start
        window.navigate("voice")
        pump(0.05)
check("voice page honours a listen payload", _page_payload)


def _news_payload():
    real_refresh = state.news.refresh
    seen = []
    state.news.refresh = lambda: seen.append("refresh")
    try:
        window.navigate("news", {"refresh": True})
        pump(0.1)
        ensure(seen == ["refresh"], f"news.refresh called {len(seen)} times")
    finally:
        state.news.refresh = real_refresh
        window.navigate("news")
        pump(0.05)
check("news page honours a refresh payload", _news_payload)


def _unknown_page():
    window.navigate("does-not-exist")
    pump(0.05)
    ensure(window.current_page in PAGES,
           f"current_page became {window.current_page!r}")
check("unknown page key is ignored", _unknown_page)


# ==========================================================================
# 3. screenshots (clean state, before any failure is injected)
# ==========================================================================
print("\n== screenshots ==")

os.makedirs(SHOTS, exist_ok=True)
_shots: list[str] = []


def _shot(label: str) -> None:
    from PySide6.QtGui import QImage

    path = os.path.join(SHOTS, f"{label}.png")
    pix = window.grab()
    ensure(not pix.isNull(), "grab() returned a null pixmap")
    ensure(pix.width() >= 1000 and pix.height() >= 650,
           f"grab is {pix.width()}x{pix.height()}")
    ensure(pix.save(path), f"could not write {path}")

    image = QImage(path)
    ensure(not image.isNull(), "saved PNG could not be read back")
    ensure(os.path.getsize(path) > 10_000,
           f"{label}.png is only {os.path.getsize(path)} bytes "
           "(looks blank)")

    small = image.scaled(96, 60, Qt.IgnoreAspectRatio,
                         Qt.FastTransformation)
    buckets: dict[tuple, int] = {}
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            key = (c.red() // 16, c.green() // 16, c.blue() // 16)
            buckets[key] = buckets.get(key, 0) + 1
    total = sum(buckets.values())
    top = max(buckets.values()) / total
    ensure(len(buckets) >= 6,
           f"{label}: only {len(buckets)} distinct colour buckets")
    ensure(top <= 0.99,
           f"{label}: one colour covers {top:.0%} of the window")
    _shots.append(path)


for theme in ("dark", "light"):
    state.set_theme(theme)
    pump(0.15)
    check(f"theme switched to {theme}",
          lambda: ensure(state.theme == theme, state.theme))
    for page in PAGES:
        def _snap(t=theme, p=page):
            window.navigate(p)
            pump(0.25)
            _shot(f"{t}-{p}")
        check(f"screenshot {theme}/{page}", _snap)

state.set_theme("dark")
pump(0.1)
window.navigate("dashboard")
pump(0.1)
print(f"       wrote {len(_shots)} screenshots to {SHOTS}")


# ==========================================================================
# 4. no secret ever reaches the screen
# ==========================================================================
print("\n== secret leakage ==")


def _no_secrets():
    everything = "\n".join(collect_text(window)) + "\n" + window.windowTitle()
    leaked = []
    for name in ("GEMINI_API_KEY", "NEWS_API_KEY"):
        value = os.environ.get(name) or ""
        if len(value) >= 6 and value in everything:
            leaked.append(name)
    ensure(not leaked, f"{', '.join(leaked)} value rendered in the UI")
    ensure("Traceback" not in everything, "a stack trace is on screen")
    ensure('File "' not in everything, "a stack trace is on screen")
check("no API key value and no stack trace is rendered", _no_secrets)


# ==========================================================================
# 5. Gemini is not configured
# ==========================================================================
print("\n== missing Gemini key ==")

_MISSING_GEMINI = (
    "GEMINI_API_KEY is not set. Create one at "
    "https://aistudio.google.com/apikey and run: "
    'setx GEMINI_API_KEY "<your key>" (then open a new terminal)'
)


class _UnconfiguredGemini:
    backend = "unconfigured"
    _config_error = _MISSING_GEMINI

    def send(self, message, retries=2):  # noqa: ANN001, ARG002
        return self._config_error

    def reset(self):
        return None


def _backend_without_keys():
    return types.SimpleNamespace(
        API_KEY=None,
        MODEL_NAME="gemini-2.0-flash",
        NEWS_API_KEY=None,
        NEWS_COUNTRY="in",
        NEWS_QUERY="technology",
        gemini=_UnconfiguredGemini(),
    )


real_asvc_get_main = asvc.get_main
asvc.get_main = _backend_without_keys
try:
    check("gemini_info reports 'not configured' without a key",
          lambda: ensure(asvc.gemini_info()["configured"] is False,
                         "configured flag is True"))

    def _build_settings():
        fresh = SettingsView(state, window.navigate)
        _keep.append(fresh)
        pump(0.15)
        text = "\n".join(collect_text(fresh))
        ensure("Not configured" in text,
               "settings page does not say 'Not configured'")
        ensure("GEMINI_API_KEY" in text,
               "settings page gives no guidance on where the key comes from")
        ensure("Needs attention" not in text,
               "an unconfigured key should not read as a warning")
    check("settings page shows an honest Gemini status", _build_settings)

    chat_box = {}

    def _send_without_key():
        window.navigate("chat")
        pump(0.1)
        chat = window._views["chat"]
        chat._input.setPlainText("what is the capital of France?")
        chat._send()
        # Checked before any event is processed: this stub replies in
        # microseconds, so the busy window closes again almost at once.
        ensure(state.assistant.busy, "assistant never became busy")
        ensure(not chat._send_button.isEnabled(),
               "send button stayed enabled while busy")
        ok = wait_until(lambda: not state.assistant.busy, timeout=15)
        ensure(ok, "assistant never finished")
        pump(0.2)
        text = "\n".join(collect_text(chat))
        chat_box["text"] = text
        ensure("GEMINI_API_KEY is not set" in text,
               "chat did not show the missing-key message")
        ensure("Traceback" not in text, "chat shows a stack trace")
        names = [w.objectName() for w in chat.findChildren(QWidget)]
        ensure("ChatBubbleError" in names, "no error bubble in transcript")
    check("chat answers a missing key with a friendly message",
          _send_without_key)
finally:
    asvc.get_main = real_asvc_get_main

check("missing key raises a visible app-level error state",
      lambda: ensure(bool(state.error),
                     "no error was surfaced to AppState"))
state.clear_error()
pump(0.1)


# ==========================================================================
# 6. News API is not configured / the request fails
# ==========================================================================
print("\n== missing News key ==")

real_nsvc_get_main = nsvc.get_main
nsvc.get_main = _backend_without_keys
seen_failures: list[str] = []
state.news.failed.connect(seen_failures.append)
try:
    check("news_info reports 'not configured' without a key",
          lambda: ensure(nsvc.news_info()["configured"] is False,
                         "configured flag is True"))

    def _refresh_without_key():
        seen_failures.clear()
        window.navigate("news")
        pump(0.1)
        state.news.refresh()
        pump(0.2)
        ensure(seen_failures, "no failure was reported for a missing key")
        ensure("NEWS_API_KEY" in seen_failures[0],
               f"message is {seen_failures[0]!r}")
        text = "\n".join(collect_text(window._views["news"]))
        ensure("NEWS_API_KEY" in text, "news page shows no guidance")
        ensure("Traceback" not in text, "news page shows a stack trace")
    check("news page explains a missing key", _refresh_without_key)
finally:
    nsvc.get_main = real_nsvc_get_main


def _news_none_payload():
    # What the backend really returns when every request fails.
    seen_failures.clear()
    state.news.articles = [{"title": "placeholder"}]
    state.news._on_task("news.refresh", True, None)
    pump(0.2)
    ensure(state.news.articles == [], "stale articles were kept")
    ensure(seen_failures, "no failure emitted for a None payload")
    ensure("Unable to connect" in seen_failures[-1],
           seen_failures[-1])
    text = "\n".join(collect_text(window._views["news"]))
    ensure("Unable to connect to the news service." in text,
           "news page does not show the real reason")
    ensure("None" not in text, "'None' leaked to the UI")
check("news handles a failed request without crashing", _news_none_payload)
state.clear_error()
pump(0.1)


# ==========================================================================
# 6b. development / mock provider mode
# ==========================================================================
print("\n== development / mock provider ==")

from PySide6.QtWidgets import QComboBox  # noqa: E402

_original_provider = state.settings.get("ai_provider", "auto")
try:
    def _mock_reply_in_chat():
        window.navigate("chat")
        pump(0.1)
        chat = window._views["chat"]
        # Start from a clean transcript through the real reset path.
        state.assistant.history.clear()
        chat._service.reset()
        ensure(wait_until(lambda: not chat._messages, timeout=15),
               "transcript did not reset before the mock test")

        state.set_provider("mock")
        pump(0.1)
        ensure(state.provider == "mock", "provider did not switch to mock")
        ensure(state.assistant.provider_mode == "mock",
               "assistant did not inherit the mock provider")

        chat._input.setPlainText("hello")
        chat._send()
        ok = wait_until(lambda: not state.assistant.busy, timeout=15)
        ensure(ok, "mock reply never arrived")
        pump(0.2)
        text = "\n".join(collect_text(chat))
        ensure("development mode" in text.lower(),
               f"no development-mode reply: {text[:200]!r}")
        ensure("Mock" in text, "chat does not name the Mock provider")
        ensure("Traceback" not in text, "chat shows a stack trace")
        names = [w.objectName() for w in chat.findChildren(QWidget)]
        ensure("ChatBubbleAssistant" in names,
               "no assistant bubble in the transcript")
    check("mock provider answers in the chat transcript", _mock_reply_in_chat)

    def _mock_identity_visible():
        # No part of the UI may pretend the Mock provider is Gemini.
        window.navigate("chat")
        pump(0.15)
        text = "\n".join(collect_text(window._views["chat"]))
        ensure("Powered by your Gemini connection." not in text,
               "subtitle still claims a live Gemini connection")
        ensure("Mock (dev)" in text, "chat pill does not say Mock (dev)")
        ensure("Development mode" in text,
               "chat does not announce development mode")

        window.navigate("dashboard")
        pump(0.15)
        dash = window._views["dashboard"]
        ensure(dash._mode_pill.isVisible(),
               "dashboard hides the development pill in mock mode")
        dtext = "\n".join(collect_text(dash))
        ensure("Development mode" in dtext,
               "dashboard does not announce development mode")
        ensure("AI Provider: Mock" in dash._mode_pill.text(),
               "dashboard pill does not name the Mock provider")
    check("development mode is visible throughout the UI", _mock_identity_visible)

    def _settings_provider_selector():
        state.set_provider("auto")
        pump(0.1)
        fresh = SettingsView(state, window.navigate)
        _keep.append(fresh)
        pump(0.15)
        text = "\n".join(collect_text(fresh))
        ensure("AI provider" in text, "settings has no provider selector")

        combo = None
        for widget in fresh.findChildren(QComboBox):
            if (widget.findData("auto") >= 0
                    and widget.findData("mock") >= 0
                    and widget.findData("gemini") >= 0):
                combo = widget
                break
        ensure(combo is not None, "provider combo not found")
        items = [combo.itemText(i) for i in range(combo.count())]
        ensure(any("Mock" in item for item in items),
               "settings does not offer Mock mode")
        combo.setCurrentIndex(combo.findData("mock"))
        pump(0.15)
        ensure(state.provider == "mock",
               "choosing Mock in Settings did not switch the provider")
    check("settings selects the AI provider", _settings_provider_selector)

    def _mock_clear_history():
        window.navigate("chat")
        pump(0.1)
        chat = window._views["chat"]
        state.assistant.history.clear()
        chat._messages = []

        chat._input.setPlainText("first question")
        chat._send()
        ensure(wait_until(lambda: not state.assistant.busy, timeout=15),
               "first mock reply never arrived")
        chat._input.setPlainText("second question")
        chat._send()
        ensure(wait_until(lambda: not state.assistant.busy, timeout=15),
               "second mock reply never arrived")
        pump(0.2)
        ensure(len(chat._messages) >= 4, "transcript did not accumulate")

        chat._service.reset()
        ensure(wait_until(lambda: len(chat._messages) == 0, timeout=15),
               "reset did not clear the transcript")
        pump(0.2)
        text = "\n".join(collect_text(chat))
        ensure("first question" not in text and "second question" not in text,
               "cleared messages are still visible")
    check("clearing the conversation works in mock mode", _mock_clear_history)
finally:
    state.set_provider(_original_provider)
    pump(0.1)


# ==========================================================================
# 7. no microphone
# ==========================================================================
print("\n== microphone unavailable ==")

real_vsvc_get_main = vsvc.get_main


class _NoMicrophoneBackend:
    """A machine with no usable input device, from the backend's own API."""

    API_KEY = None

    @staticmethod
    def candidate_devices():
        return []

    @staticmethod
    def is_real_microphone(name):  # noqa: ANN001
        return False

    @staticmethod
    def find_working_microphone():
        return (None, "")


vsvc.get_main = lambda: _NoMicrophoneBackend
try:
    def _refresh_no_mic():
        state.voice._listing = False
        state.voice.refresh_devices()
        ensure(wait_until(lambda: not state.voice._listing, timeout=15),
               "device scan never returned")
        pump(0.2)
        ensure(state.voice.devices == [], state.voice.devices)
        ensure(state.voice.state == vsvc.NO_MICROPHONE,
               f"state is {state.voice.state!r}")
        ensure(bool(state.error), "no error surfaced")
        window.navigate("voice")
        pump(0.2)
        text = "\n".join(collect_text(window._views["voice"]))
        ensure("No microphone" in text,
               f"voice page text: {text[:200]!r}")
        ensure("Traceback" not in text, "voice page shows a stack trace")
    check("no microphone produces a friendly Voice state", _refresh_no_mic)

    def _probe_no_mic():
        seen_probes: list = []

        def _on_probe(ok, message, level):  # noqa: ANN001
            seen_probes.append((ok, message, level))

        state.voice.probeFinished.connect(_on_probe)
        try:
            state.voice.probe()
            ensure(wait_until(lambda: bool(seen_probes), timeout=15),
                   "probe never reported back")
            ok, message, _level = seen_probes[-1]
            ensure(ok is False, f"probe claimed success: {message!r}")
            ensure(state.voice.state in
                   (vsvc.NO_MICROPHONE, vsvc.DISCONNECTED, vsvc.ERROR),
                   f"state is {state.voice.state!r}")
            ensure(bool(message), "probe gave no explanation")
            pump(0.2)
            text = "\n".join(collect_text(window._views["voice"]))
            ensure("Traceback" not in text, "voice page shows a stack trace")
            ensure(bool(state.error), "probe failure not surfaced")
        finally:
            state.voice.probeFinished.disconnect(_on_probe)
    check("probe failure is reported honestly", _probe_no_mic)
finally:
    vsvc.get_main = real_vsvc_get_main

state.clear_error()
state.voice._listing = False
state.voice.refresh_devices()   # restore the real device list
wait_until(lambda: not state.voice._listing, timeout=20)
pump(0.2)


# ==========================================================================
# 8. the GUI stays responsive while the backend works
# ==========================================================================
print("\n== responsiveness ==")


class _SlowGemini:
    backend = "stub"
    _config_error = None

    def send(self, message, retries=2):  # noqa: ANN001, ARG002
        time.sleep(1.5)
        return "A real answer that took 1.5 seconds to arrive."

    def reset(self):
        return None


real_slow_get_main = asvc.get_main
asvc.get_main = lambda: types.SimpleNamespace(
    API_KEY="stub", MODEL_NAME="stub", gemini=_SlowGemini())


def _gui_never_freezes():
    _ticks["n"] = 0
    tick_timer.start()
    chat = window._views["chat"]
    window.navigate("chat")
    pump(0.1)

    chat._input.setPlainText("tell me something slow")
    chat._send()
    ensure(state.assistant.busy, "assistant never became busy")

    end = time.monotonic() + 2.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.004)
    tick_timer.stop()

    ticks = _ticks["n"]
    ensure(ticks >= 60,
           f"GUI timer only ticked {ticks} times in 2s (frozen?)")
    ensure(wait_until(lambda: not state.assistant.busy, timeout=10),
           "slow call never returned")
    pump(0.2)
    ensure(chat._send_button.isEnabled(), "send button stayed disabled")
    text = "\n".join(collect_text(chat))
    ensure("A real answer that took 1.5 seconds" in text,
           "reply never reached the transcript")
    print(f"       GUI ticked {ticks} times during a 1.5s blocking call")


check("GUI stays responsive during a slow backend call", _gui_never_freezes)
asvc.get_main = real_asvc_get_main

# Leave the transcript tidy for anyone opening the app afterwards.
state.assistant.history.clear()
state.assistant.reset()
pump(0.2)


# ==========================================================================
# 9. optional global hotkey
# ==========================================================================
print("\n== optional hotkey ==")


def _hotkey_off_by_default():
    ensure(state.settings.get("hotkey", False) is False,
           "the hotkey setting does not default to off")
    ensure(not state.hotkey.registered,
           "a global hotkey was registered without being asked for")
check("hotkey is off by default", _hotkey_off_by_default)


def _hotkey_registers():
    try:
        ok = state.hotkey.enable(app)
        if ok:
            ensure(state.hotkey.registered,
                   "enable() reported success but nothing is registered")
            ensure("Ctrl+Alt+M" in state.hotkey.reason, state.hotkey.reason)
        else:
            # Another application may legitimately own Ctrl+Alt+M. What
            # matters is that the UI is given a sentence to show instead of
            # a silent failure.
            ensure(not state.hotkey.registered, "half-registered state")
            ensure(bool(state.hotkey.reason),
                   "registration failed with no explanation")
    finally:
        state.hotkey.disable()
    ensure(not state.hotkey.registered, "disable() did not unregister")
    ensure(bool(state.hotkey.reason), "no explanation after disabling")
check("hotkey registers, explains itself and unregisters", _hotkey_registers)


def _hotkey_persists():
    store = state.settings
    original = store.get("hotkey", False)
    try:
        store.set("hotkey", True)
        ensure(store.get("hotkey") is True, "value was not stored")
    finally:
        store.set("hotkey", original)
    ensure(store.get("hotkey") == original, "value was not restored")
check("hotkey preference persists", _hotkey_persists)


# ==========================================================================
# 10. window controls
# ==========================================================================
print("\n== window controls ==")


def _minimise():
    window.showMinimized()
    pump(0.2)
    ensure(bool(window.windowState() & Qt.WindowState.WindowMinimized),
           "minimise was ignored")
    window.showNormal()
    pump(0.2)
    ensure(not window.isMinimized(), "restore failed")
check("minimise and restore", _minimise)


def _maximise():
    window.showMaximized()
    pump(0.2)
    ensure(window.isMaximized(), "maximise was ignored")
    window.showNormal()
    pump(0.2)
    ensure(not window.isMaximized(), "restore failed")
check("maximise and restore", _maximise)


def _resize_floor():
    window.resize(320, 200)
    pump(0.15)
    ensure(window.width() >= 1000 and window.height() >= 650,
           f"window shrank to {window.width()}x{window.height()}")
    window.resize(1240, 800)
    pump(0.15)
check("window never goes below its minimum", _resize_floor)


# ==========================================================================
# 11. system tray
# ==========================================================================
print("\n== system tray ==")

window._install_tray(available=True)
pump(0.2)


def _tray_exists():
    ensure(window._tray is not None, "tray was not created")
    ensure(window._tray.isVisible(), "tray icon is not visible")
    menu = window._tray.contextMenu()
    ensure(menu is not None, "tray has no menu")
    labels = [a.text() for a in menu.actions() if a.text()]
    ensure(any("Open" in t for t in labels), f"menu: {labels}")
    ensure(any("Voice" in t for t in labels), f"menu: {labels}")
    ensure(any("Settings" in t for t in labels), f"menu: {labels}")
    ensure(any("Quit" in t for t in labels), f"menu: {labels}")
check("tray icon and menu exist", _tray_exists)


def _tray_actions():
    menu = window._tray.contextMenu()
    actions = [a for a in menu.actions() if a.text()]

    window.navigate("dashboard")
    pump(0.1)
    actions[1].trigger()          # Voice command
    pump(0.2)
    ensure(window.current_page == "voice",
           f"current_page is {window.current_page!r}")

    actions[2].trigger()          # Settings
    pump(0.2)
    ensure(window.current_page == "settings",
           f"current_page is {window.current_page!r}")

    window.hide()
    pump(0.1)
    actions[0].trigger()          # Open MERLIN
    pump(0.2)
    ensure(window.isVisible(), "Open MERLIN did not restore the window")
check("tray menu actions work", _tray_actions)


def _close_to_tray():
    state.settings.set("minimize_to_tray", True)
    window.close()
    pump(0.2)
    ensure(not window.isVisible(), "window stayed visible after close")
    ensure(not window._torn_down, "closing to tray shut the services down")
    # The app is still fully functional while hidden.
    ensure(window.current_page in PAGES, "page lost while hidden")
    window.show()
    pump(0.2)
    ensure(window.isVisible(), "window did not come back")
check("close hides to tray instead of quitting", _close_to_tray)


def _close_quits_when_tray_disabled():
    state.settings.set("minimize_to_tray", False)
    # `app.quit()` outside exec() only records an exit code, so the suite
    # can still assert that a real close tore everything down.
    window.close()
    pump(0.3)
    ensure(window._torn_down, "close did not shut the services down")
    ensure(not window.isVisible(), "window still visible after closing")
check("close quits when minimise-to-tray is off",
      _close_quits_when_tray_disabled)


# ==========================================================================
# 12. shutdown
# ==========================================================================
print("\n== shutdown ==")

# Put the machine back exactly as the suite found it.
state.settings.set("theme", _ORIGINAL_SETTINGS["theme"])
state.settings.set("minimize_to_tray",
                   _ORIGINAL_SETTINGS["minimize_to_tray"])
print(f"       restored settings: {_ORIGINAL_SETTINGS}")


def _quit_action_is_safe():
    window.quit()               # idempotent after the close above
    window.teardown()
    pump(0.1)
    ensure(window._torn_down, "teardown did not complete")
check("quit action is safe and idempotent", _quit_action_is_safe)

check("no unhandled exception escaped", lambda: ensure(
    not _uncaught,
    f"{len(_uncaught)} unhandled exception(s):\n" + (_uncaught[0] if _uncaught else ""),
))


# ==========================================================================
print(f"\n{_checks - len(_failures)}/{_checks} UI checks passed")
if _failures:
    print("Failed:")
    for name in _failures:
        print(f"  - {name}")
    sys.exit(1)
print("ALL UI CHECKS PASSED")
sys.exit(0)
