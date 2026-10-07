"""Full regression suite for MERLIN.

Runs without a microphone and without touching real audio hardware by
stubbing pyttsx3 before importing main. Exercises command dispatch, the
Gemini wrapper, news fallback, speech cleanup and the main loop's
failure handling.

Run:  myprojectenv\\Scripts\\python.exe test_merlin.py
"""
import sys
import types
import os
import struct

# --- stub audio output before importing main -------------------------------
_spoken = []
fake_engine = types.SimpleNamespace(
    say=lambda t: _spoken.append(t), runAndWait=lambda: None
)
fake_pyttsx3 = types.ModuleType("pyttsx3")
fake_pyttsx3.init = lambda *a, **k: fake_engine
sys.modules["pyttsx3"] = fake_pyttsx3

sys.path.insert(0, ".")
import main  # noqa: E402

main.engine = fake_engine

# Stub the network-backed layers so the suite is fast, offline-safe and
# deterministic. Anything that falls through to Gemini returns "ANSWER",
# which is how we assert "this was NOT treated as a command".
main.gemini.send = lambda text, retries=2: "ANSWER"

_results = []


def check(label, cond, detail=""):
    _results.append((label, bool(cond), detail))
    status = "PASS" if cond else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f"  ({detail})"
    print(line)


def section(name):
    print(f"\n--- {name} ---")


def spoken_now():
    out = list(_spoken)
    _spoken.clear()
    return out


def act(fn, *args, **kwargs):
    """Clear captured speech, run fn, then return what was spoken.

    Capturing after the call matters: capturing before gives an off-by-one
    that can make a failing check look like it passed.
    """
    _spoken.clear()
    fn(*args, **kwargs)
    return list(_spoken)


# =========================================================================
section("1. command dispatch: websites")

opened = []
main.webbrowser.open = lambda u: opened.append(u)

for name, frag in [("google", "google.com"), ("youtube", "youtube.com"),
                   ("facebook", "facebook.com"), ("instagram", "instagram.com"),
                   ("leetcode", "leetcode.com"), ("github", "github.com")]:
    opened.clear(); spoken_now()
    main.processCommand(f"open {name}")
    check(f"open {name}", len(opened) == 1 and frag in opened[0])

for verb in ["launch", "browse", "visit", "go"]:
    opened.clear(); spoken_now()
    main.processCommand(f"{verb} github")
    check(f"verb '{verb}' opens site", len(opened) == 1 and "github" in opened[0])

opened.clear()
s = act(main.processCommand, "open wikipedia")
check("unknown site asks which", opened == [] and s == ["Which site should I open?"])

opened.clear()
s = act(main.processCommand, "openers and closers are people")
check("'openers' does not trigger open", opened == [] and s == ["ANSWER"])

opened.clear()
s = act(main.processCommand, "Open GitHub")
check("case-insensitive open", len(opened) == 1)

# =========================================================================
section("2. command dispatch: songs")

opened.clear(); spoken_now()
main.processCommand("play Ganga ke kinare")
check("play mixed-case song", len(opened) == 1 and "ocRzt5NvI7A" in opened[0])

opened.clear(); spoken_now()
main.processCommand("play krishnavataram")
check("play second song", len(opened) == 1 and "Hcr7gDD_nX8" in opened[0])

opened.clear(); spoken_now()
main.processCommand("play  ganga   ke  kinare")
check("play tolerates odd spacing", len(opened) == 1 and "ocRzt5NvI7A" in opened[0])

opened.clear()
s = act(main.processCommand, "play")
check("bare play asks which song", opened == [] and s == ["Which song to play?"])

opened.clear()
s = act(main.processCommand, "play some unknown song")
check("unknown song -> Song not found", opened == [] and s == ["Song not found"])

for bad in ["players are the best", "playground", "playback speed"]:
    opened.clear()
    s = act(main.processCommand, bad)
    check(f"'{bad}' falls through to Gemini",
          opened == [] and s == ["ANSWER"])

# =========================================================================
section("3. command dispatch: news")

class FakeResp:
    def __init__(self, code, payload):
        self.status_code = code
        self._payload = payload
    def json(self):
        return self._payload


main._fetch_articles = lambda url, params: (
    [{"title": "H1"}, {"title": "H2"}] if params.get("country") == "us" else []
)
check("news falls back to a served country",
      act(main.read_news) == ["H1", "H2"])

main._fetch_articles = lambda url, params: []
check("empty news gives feedback",
      act(main.read_news) == ["No news headlines available right now"])

main._fetch_articles = lambda url, params: None
check("request failure speaks failure",
      act(main.read_news) == ["Failed to fetch news"])

main._fetch_articles = lambda url, params: (
    [{"title": "H1"}] if "top-headlines" in url else []
)
check("news prefers top-headlines", act(main.read_news) == ["H1"])

main._fetch_articles = lambda url, params: [{"title": "H"}]
for cmd in ["news", "top news", "latest headlines", "news please", "news?"]:
    check(f"news phrase '{cmd}' works", act(main.processCommand, cmd) == ["H"])

for q in ["what is in the news about india", "explain news broadcasting"]:
    check(f"question not hijacked: '{q[:30]}'",
          act(main.processCommand, q) == ["ANSWER"])

# =========================================================================
section("4. chat control commands")

main.gemini.reset_called = False
_real_reset = main.gemini.reset
main.gemini.reset = lambda: setattr(main.gemini, "reset_called", True)

for cmd in ["clear chat", "reset chat", "new chat", "forget everything",
            "clear chat?", "CLEAR CHAT"]:
    main.gemini.reset_called = False
    s = act(main.processCommand, cmd)
    check(f"'{cmd}' clears history",
          main.gemini.reset_called and s == ["Chat history cleared"])
main.gemini.reset = _real_reset

# =========================================================================
section("5. Gemini wrapper (stubbed)")

class FakeChat:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
    def send_message(self, msg):
        self.calls.append(msg)
        item = self.script.pop(0) if self.script else "ok"
        if isinstance(item, Exception):
            raise item
        return types.SimpleNamespace(text=item)

g = main.GeminiChat.__new__(main.GeminiChat)
g.backend = "stub"
g._chat = FakeChat(["hello"])
g._client = None
g._model = None
check("send returns text", g.send("hi") == "hello")

g._chat = FakeChat(["   "])
res = g.send("hi", retries=0)
check("blank reply handled without exception",
      isinstance(res, str) and "could not reach" in res.lower())

g._chat = FakeChat([RuntimeError("boom")])
res = g.send("hi", retries=0)
check("exception becomes a message not a crash", isinstance(res, str))

g._chat = FakeChat([RuntimeError("a"), RuntimeError("b"), "recovered"])
res = g.send("hi", retries=2)
check("recovers after transient failures", res == "recovered")

# =========================================================================
section("6. speech cleanup")

captured = []
main.engine = types.SimpleNamespace(say=captured.append, runAndWait=lambda: None)

md = "**Bold** and *it* and `# Head` and [l](http://x) and `c` and $x$ and - b"
main.speak(md, force=True)
out = captured[0]
check("markdown stripped", not any(ch in out for ch in "*#`|") and "Bold" in out)

captured.clear()
main.speak("Data \u2014 a result \u2013 more \u2026 done \u201cfour\u201d \u2192 end",
           force=True)
out = captured[0]
check("em/en dash -> comma", "\u2014" not in out and "\u2013" not in out)
check("ellipsis expanded", "..." in out)
check("curly quotes normalised", "\u201c" not in out and "\u201d" not in out)
check("arrow -> 'to'", " to " in out)

captured.clear()
main.speak("```py\nprint(1)\n```")
check("code block not read literally", "print(1)" not in captured[0].lower()
      or "code block skipped" in captured[0].lower())

captured.clear()
main.speak("***")
check("empty after clean is safe", captured == [])

captured.clear()
main.speak(None)
check("None is safe", captured == [])

# speech engine failure must not crash
boom = {"n": 0}
def failing_say(t):
    boom["n"] += 1
    if boom["n"] == 1:
        raise RuntimeError("COM failure")
main.engine = types.SimpleNamespace(say=failing_say, runAndWait=lambda: None)
init_count = {"n": 0}
def fake_init(*a, **k):
    init_count["n"] += 1
    return main.engine
_real_init = sys.modules["pyttsx3"].init
sys.modules["pyttsx3"].init = fake_init
try:
    main.speak("hello there")
    check("recovers from speech engine failure",
          boom["n"] == 2 and init_count["n"] >= 1)
except Exception as e:
    check("recovers from speech engine failure", False, type(e).__name__)
sys.modules["pyttsx3"].init = _real_init
main.engine = fake_engine

# =========================================================================
section("7. speech shortening")

long_txt = ("This is a sentence about travel. " * 40).strip()
short = main.shorten_for_speech(long_txt)
check("long text shortened", len(short) < len(long_txt))
check("shortening hints about screen", "on screen" in short)
check("short text untouched", main.shorten_for_speech("Hi.") == "Hi.")

# =========================================================================
section("8. wake word detection")

for good in ["merlin", "Merlin", "hey merlin", "MERLIN play something",
             # Google's recogniser frequently mishears "Merlin" as these,
             # so they must still wake the assistant.
             "berlin", "Berlin what is two plus two", "marlin",
             "hey marlin open google"]:
    check(f"wake word in '{good}'", main.contains_wake_word(good))
for bad in ["merlinizing", "terminal", "submarine", "germ", "berliners",
            "merlins", ""]:
    check(f"no false wake in '{bad}'", not main.contains_wake_word(bad))
check("wake check tolerates None", not main.contains_wake_word(None))
check("wake check tolerates non-str",
      not main.contains_wake_word(12345))

# =========================================================================
section("9. input validation / defensive behaviour")

for bad_input in [None, 123, [], "", "   ", b"bytes"]:
    try:
        main.processCommand(bad_input)
        check(f"processCommand tolerates {type(bad_input).__name__}",
              True)
    except Exception as e:
        check(f"processCommand tolerates {type(bad_input).__name__}",
              False, f"{type(e).__name__}: {e}")

try:
    main.close_microphone(None)
    check("close_microphone(None) safe", True)
except Exception as e:
    check("close_microphone(None) safe", False, type(e).__name__)

class BadSource:
    def __exit__(self, *a):
        raise RuntimeError("teardown blew up")
try:
    main.close_microphone(BadSource())
    check("close_microphone swallows teardown errors", True)
except Exception as e:
    check("close_microphone swallows teardown errors", False, type(e).__name__)

class NoneStreamMic:
    def __init__(self, device_index=None):
        self.stream = None
        self.audio = types.SimpleNamespace(terminate=lambda: None)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return None

_real_mic = main.sr.Microphone
main.sr.Microphone = NoneStreamMic
try:
    main.open_microphone(11)
    check("open_microphone surfaces hidden library failure", False)
except main.MicUnavailableError:
    check("open_microphone surfaces hidden library failure", True)
except Exception as e:
    check("open_microphone surfaces hidden library failure", False, type(e).__name__)
main.sr.Microphone = _real_mic

# =========================================================================
section("10. main loop failure handling")

class Boom(Exception):
    pass

check("is_mic_fatal detects audio device failure",
      main.is_mic_fatal(OSError("No Default Input Device Available")))
check("is_mic_fatal ignores unrelated errors",
      not main.is_mic_fatal(ValueError("something else entirely")))

# run() must return non-zero instead of hanging when no mic exists
_real_find = main.find_working_microphone
main.find_working_microphone = lambda: (None, None)
rc = main.run()
check("run() exits non-zero when no mic", rc == 1, f"rc={rc}")
main.find_working_microphone = _real_find  # un-stub before probing it below

# A loopback endpoint must be flagged, since it opens fine but hears the
# wrong audio, which would silently break recognition.
for loopback in ["Stereo Mix (Realtek(R) Audio)", "Microsoft Sound Mapper - Input",
                 "Input ()", "CABLE Output (loopback)"]:
    check(f"'{loopback}' not treated as a mic",
          not main.is_real_microphone(loopback))
for real in ["Microphone (Realtek HD Audio Mic input)",
             "Headset Microphone (Airdopes-111)", "Webcam Mic"]:
    check(f"'{real}' treated as a mic", main.is_real_microphone(real))

# find_working_microphone must skip devices that fail and return one that
# works, rather than returning the best-named but unusable one.
_real_open = main.open_microphone
_real_close = main.close_microphone


class OkSource:
    stream = object()

    def __exit__(self, *a):
        return None


opened_order = []


def selective_open(index):
    opened_order.append(index)
    if index == 16:
        raise main.MicUnavailableError("OSError [Errno -9999] Unanticipated host error")
    return OkSource()


_real_candidates = main.candidate_devices
_real_measure = main.measure_device

main.candidate_devices = lambda: [(16, "Microphone (Realtek HD Audio Mic input)"),
                                 (1, "Stereo Mix (Realtek(R) Audio)")]
main.open_microphone = selective_open
main.close_microphone = lambda s: None
main.measure_device = lambda source: 4000.0
idx, name = main.find_working_microphone()
check("probe skips a dead device", idx == 1, f"got index {idx}")
check("probe tried the mic first", opened_order[:1] == [16], f"order {opened_order}")

# A device that opens but captures silence must lose to one that hears.
opened_order.clear()
main.candidate_devices = lambda: [(1, "Headset (Airdopes-111)"),
                                 (7, "Headset (Airdopes-111)")]
levels = {1: 3.0, 7: 198.0}
main.measure_device = lambda source: levels[opened_order[-1]]
idx, name = main.find_working_microphone()
check("silent device loses to a live one", idx == 7, f"got index {idx}")
check("both duplicates were measured", opened_order == [1, 7], f"{opened_order}")

# RMS, not peak: a device whose only sound is one click must not win.
opened_order.clear()
main.candidate_devices = lambda: [(1, "Clicky Dead Mic"), (7, "Real Mic")]
levels = {1: 4.0, 7: 190.0}
main.measure_device = lambda source: levels[opened_order[-1]]
check("sustained energy beats a lone peak", main.find_working_microphone()[0] == 7)

# Nothing hears anything: still return a device rather than refusing to run.
main.candidate_devices = lambda: [(1, "Headset (Airdopes-111)")]
main.measure_device = lambda source: 3.0
idx, name = main.find_working_microphone()
check("falls back to a device when all are quiet",
      idx == 1 and name == "Headset (Airdopes-111)")

# A device that returns no data at all is unusable, not merely quiet.
main.candidate_devices = lambda: [(3, "Ghost Mic")]
main.measure_device = lambda source: None
idx, name = main.find_working_microphone()
check("device with no audio is rejected", idx is None and name is None)

# peak_amplitude must read signed 16-bit PCM correctly.
check("peak_amplitude finds loudest sample",
      main.peak_amplitude(struct.pack("<4h", 100, -3000, 500, 2000)) == 3000)
check("peak_amplitude of silence is 0",
      main.peak_amplitude(struct.pack("<4h", 0, 0, 0, 0)) == 0)
check("peak_amplitude of empty input is 0", main.peak_amplitude(b"") == 0)
check("peak_amplitude ignores a trailing odd byte",
      main.peak_amplitude(struct.pack("<2h", -900, 100) + b"\x01") == 900)

# rms_amplitude must match hand-computed values.
check("rms_amplitude of constant full-scale is 32767",
      abs(main.rms_amplitude(struct.pack("<2h", 32767, 32767)) - 32767) < 1)
check("rms_amplitude of silence is 0.0",
      main.rms_amplitude(struct.pack("<4h", 0, 0, 0, 0)) == 0.0)
check("rms_amplitude ignores a trailing odd byte",
      abs(main.rms_amplitude(struct.pack("<2h", 1000, -1000) + b"\x01")
          - 1000) < 1)
check("rms_amplitude of empty input is 0.0", main.rms_amplitude(b"") == 0.0)
check("rms_amplitude is below peak for a lone click",
      main.rms_amplitude(struct.pack("<2h", 30000, 0))
      < main.peak_amplitude(struct.pack("<2h", 30000, 0)))

# If every candidate fails, it must report failure rather than raise.
main.candidate_devices = _real_candidates


def always_fail(index):
    raise main.MicUnavailableError("nope")


main.open_microphone = always_fail
idx, name = main.find_working_microphone()
check("probe returns (None, None) when all devices fail", idx is None and name is None)

main.candidate_devices = _real_candidates
main.open_microphone = _real_open
main.close_microphone = _real_close
main.measure_device = _real_measure

# A Bluetooth headset is a real microphone even though its name never says
# "mic". It must outrank a Stereo Mix loopback, otherwise the assistant
# silently transcribes the user's music instead of their speech.
class FakePA:
    DEVICES = [
        (1, "Headset (Airdopes-111)", 1),
        (2, "Stereo Mix (Realtek(R) Audio)", 2),
        (3, "Microphone (Realtek HD Audio Mic input)", 2),
        (4, "Microsoft Sound Mapper - Input", 2),
    ]

    def get_default_input_device_info(self):
        raise OSError("no default input device")

    # sr.Microphone.get_pyaudio() returns a module-like object whose
    # PyAudio() builds the handle, so the stub needs to mimic that shape.
    def PyAudio(self):
        return self

    def get_device_count(self):
        return len(self.DEVICES)

    def get_device_info_by_index(self, i):
        name, ch = self.DEVICES[i][1], self.DEVICES[i][2]
        return {"name": name, "maxInputChannels": ch}

    def terminate(self):
        pass


_real_get_pa = main.sr.Microphone.get_pyaudio
main.sr.Microphone.get_pyaudio = staticmethod(lambda: FakePA())

env_idx = os.environ.pop("MIC_DEVICE_INDEX", None)
order = main.candidate_devices()
names = [n for _i, n in order]

check("loopback is ranked last",
      all(main.is_real_microphone(n) for n in names[:-2]),
      f"order={names}")
check("named mic outranks headset",
      names.index("Microphone (Realtek HD Audio Mic input)")
      < names.index("Headset (Airdopes-111)"))
check("headset outranks stereo mix",
      names.index("Headset (Airdopes-111)") < names.index("Stereo Mix (Realtek(R) Audio)"))

if env_idx is not None:
    os.environ["MIC_DEVICE_INDEX"] = env_idx
main.sr.Microphone.get_pyaudio = _real_get_pa

# =========================================================================
print()
passed = sum(1 for _, ok, _ in _results if ok)
failed = [(l, d) for l, ok, d in _results if not ok]
print(f"{passed}/{len(_results)} checks passed")
if failed:
    print("\nFAILURES:")
    for label, detail in failed:
        print(f"  - {label}" + (f"  ({detail})" if detail else ""))
    sys.exit(1)
print("ALL CHECKS PASSED")