import array
import math
import os
import re
import sys
import time

import speech_recognition as sr
import webbrowser
import pyttsx3
import musicLibrary
import requests

# Secrets are read from the environment only. They are deliberately never
# written in source: a hardcoded fallback leaked the key into this file once
# and made the project impossible to share or commit safely.
#   setx GEMINI_API_KEY "<your key>"
#   setx NEWS_API_KEY "<your key>"
API_KEY = os.getenv("GEMINI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# NewsAPI's free plan only serves top-headlines for a subset of countries.
# For example country=in returns an empty list, so we fall back to a country
# the free plan does serve, and finally to the search endpoint.
NEWS_COUNTRY = os.getenv("NEWS_COUNTRY", "in")
NEWS_FALLBACK_COUNTRIES = ("us", "gb")
NEWS_QUERY = os.getenv("NEWS_QUERY", "india OR travel")

# A spoken answer should be short enough to finish before the user loses
# patience. The full answer is still printed to the console.
MAX_SPOKEN_CHARS = 600
MAX_SPOKEN_SENTENCES = 5

# Choosing a microphone. Windows can expose several input endpoints that open
# without error but capture digital silence, and it lists them all under one
# name, so MERLIN measures a real sample from each candidate and keeps the
# one carrying the most energy. RMS is used rather than peak amplitude: a
# single click produces a huge peak on a device that is otherwise deaf,
# whereas speech produces sustained energy. A silent endpoint reads near 1-5;
# a working microphone reads in the hundreds.
MIC_MIN_RMS = float(os.getenv("MIC_MIN_RMS", "20"))
# How many devices to probe before giving up, so start-up stays quick when
# many phantom Bluetooth endpoints are present.
MIC_PROBE_LIMIT = int(os.getenv("MIC_PROBE_LIMIT", "6"))
# Seconds of audio to sample from each candidate device.
MIC_PROBE_SECONDS = float(os.getenv("MIC_PROBE_SECONDS", "2"))
# Consecutive failed listens after which we suspect the device is deaf and
# re-run device selection instead of waiting forever on a silent microphone.
MIC_RESELECT_AFTER = int(os.getenv("MIC_RESELECT_AFTER", "5"))
# A working microphone never emits literal zero samples: the ADC noise floor
# fills every slot, so genuine speech measures under 1% exact-zero samples.
# An endpoint whose driver is receiving no data hands back digital silence
# instead, and a broken one can hand back a fixed repeating buffer whose
# pattern drives the level meter to full scale while carrying no voice at
# all. Measured on this machine: the dead endpoint MERLIN used to select
# produced 91-100% zero samples per second. Anything at or above this
# fraction is not microphone audio, so it is rejected here rather than
# offered to the recogniser, which can only answer "could not understand
# it" and send the user chasing the wrong problem.
MIC_MAX_ZERO_FRACTION = float(os.getenv("MIC_MAX_ZERO_FRACTION", "0.4"))
# The zero fraction alone does not catch everything: a broken endpoint can
# hand back a varying buffer whose exact-zero share sits just under the
# limit above (measured as low as 38%), in which case it is selected and
# every utterance still comes back as "could not understand it". The second
# test uses how the signal moves rather than how loud it is. Every real
# acoustic signal is band-limited by the transducer, so one sample predicts
# the next closely: lag-1 autocorrelation measured +0.954 to +0.975 across
# six speech samples. The artefact measured -0.321 to +0.106, because it is
# a sparse spike train standing in for audio, not a band-limited signal.
# Threshold sits midway between those populations.
MIC_MIN_CONTINUITY = float(os.getenv("MIC_MIN_CONTINUITY", "0.5"))
# The continuity test only runs when a capture already carries a noticeable
# share of exact zeros. Genuine microphone audio essentially never does --
# the converter's noise floor fills every sample -- so this gate keeps the
# test away from quiet-but-working microphones, whose noise floor could
# otherwise be wide enough to look discontinuous.
MIC_CONTINUITY_ZERO_GATE = 0.10


class GeminiChat:
    """Thin wrapper around Gemini that hides SDK differences and retries.

    Prefers the current `google-genai` SDK and falls back to the legacy
    `google-generativeai` package, which is end-of-life.
    """

    def __init__(self):
        self.backend = None
        self._client = None
        self._model = None
        self._chat = None
        self._config_error = None
        self._init()

    def _init(self):
        if not API_KEY:
            # Building a client with no key raises, and because the module
            # constructs this object at import time that would take down the
            # whole program (and the test suite) before it could do anything
            # useful. Record the problem and report it on first use instead.
            self.backend = "unconfigured"
            self._config_error = (
                "GEMINI_API_KEY is not set. Create one at "
                "https://aistudio.google.com/apikey and run: "
                "setx GEMINI_API_KEY \"<your key>\" "
                "(then open a new terminal)"
            )
            return

        try:
            from google import genai

            self._client = genai.Client(api_key=API_KEY)
            self.backend = "google-genai"
        except ImportError:
            # The legacy package is a fallback, not a guarantee: it is
            # end-of-life and is not listed in requirements.txt, so a clean
            # install does not have it. If it is unavailable too, record the
            # problem instead of raising, because GeminiChat is built while
            # main.py is being imported - an exception here would stop the
            # whole assistant from starting over a missing optional package.
            try:
                import google.generativeai as legacy

                legacy.configure(api_key=API_KEY)
                self._model = legacy.GenerativeModel(MODEL_NAME)
                self.backend = "google-generativeai (legacy)"
            except Exception as legacy_error:
                self.backend = "unconfigured"
                self._config_error = (
                    "No usable Gemini SDK is installed, so questions cannot "
                    "be answered. Install one with: "
                    "myprojectenv\\Scripts\\pip install google-genai "
                    f"({type(legacy_error).__name__}: {legacy_error})"
                )
                return
        self.reset()

    def reset(self):
        """Start a fresh conversation, discarding history."""
        if getattr(self, "_config_error", None):
            return
        try:
            if self.backend == "google-genai":
                self._chat = self._client.chats.create(model=MODEL_NAME)
            else:
                self._chat = self._model.start_chat(history=[])
        except Exception as e:
            raise RuntimeError(f"Could not start Gemini chat: {e}") from e

    def send(self, message, retries=2):
        """Send a message, retrying transient failures.

        Returns the reply text. On unrecoverable failure returns a short
        message instead of raising, so the assistant never dies from a
        network blip mid-conversation.
        """
        if getattr(self, "_config_error", None):
            return self._config_error

        last_error = None
        for attempt in range(retries + 1):
            try:
                if self.backend == "google-genai":
                    response = self._chat.send_message(message)
                    text = getattr(response, "text", None)
                else:
                    response = self._chat.send_message(message)
                    text = getattr(response, "text", None)

                if text and text.strip():
                    return text.strip()

                # A response with no text usually means the prompt was blocked.
                last_error = "empty reply (the response may have been blocked)"
            except Exception as e:
                last_error = str(e)

            if attempt < retries:
                wait = 1.5 * (attempt + 1)
                print(f"Gemini call failed ({last_error}); retrying in {wait}s")
                time.sleep(wait)

        return f"Sorry, I could not reach Gemini right now. {last_error}"


gemini = GeminiChat()

recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.pause_threshold = 1
engine = pyttsx3.init()


def speak(text, force=False):
    """Speak text, stripping markup the voice engine would read literally.

    Gemini answers are markdown-heavy and pyttsx3 has no concept of '*' or
    '#', so without this it would say "asterisk asterisk plants, comma algae".
    """
    if text is None:
        return
    if not isinstance(text, str):
        text = str(text)

    cleaned = re.sub(r"```.*?```", " code block skipped. ", text, flags=re.S)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)              # inline code
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)          # bold
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)              # italic
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.M)    # headings
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.M)   # bullets
    cleaned = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", cleaned)       # links
    cleaned = re.sub(r"\$([^$]*)\$", r"\1", cleaned)            # inline math
    cleaned = re.sub(r"[*_#>|`]", "", cleaned)                  # leftovers
    cleaned = to_speech_friendly_punctuation(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return

    if not force:
        cleaned = shorten_for_speech(cleaned)

    if not cleaned:
        return

    global engine
    for attempt in (1, 2):
        try:
            engine.say(cleaned)
            engine.runAndWait()
            return
        except Exception as e:
            # SAPI5 raises COM errors fairly often, e.g. when the engine is
            # busy or was disconnected. Rebuilding it usually recovers.
            print(f"Speech engine error: {e}")
            if attempt == 2:
                print("Could not speak the response.")
                return
            try:
                engine = pyttsx3.init()
            except Exception as init_error:
                print(f"Could not restart the speech engine: {init_error}")
                return


def to_speech_friendly_punctuation(text):
    """Turn typographic punctuation into something worth listening to.

    Headlines and Gemini replies are full of em dashes and curly quotes. A
    TTS engine either skips them awkwardly or pronounces them as words, so we
    swap them for punctuation that sounds natural.
    """
    replacements = {
        "\u2014": ", ",   # em dash
        "\u2013": ", ",   # en dash
        "\u2212": " minus ",  # minus sign
        "\u2018": "'", "\u2019": "'",   # single curly quotes
        "\u201c": '"', "\u201d": '"',   # double curly quotes
        "\u2026": "...",   # ellipsis
        "\u00a0": " ",           # non-breaking space
        "\u2022": ", ",          # bullet
        "\u2192": " to ",        # right arrow
        "\u00d7": " times ",     # multiplication sign
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Collapse any doubled punctuation the replacements created.
    text = re.sub(r"\s*,\s*,+\s*", ", ", text)
    return text


def shorten_for_speech(text):
    """Trim a long answer down to something reasonable to listen to."""
    if len(text) <= MAX_SPOKEN_CHARS:
        return text

    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = []
    total = 0
    for sentence in sentences:
        if len(kept) >= MAX_SPOKEN_SENTENCES:
            break
        if total + len(sentence) > MAX_SPOKEN_CHARS and kept:
            break
        kept.append(sentence)
        total += len(sentence)

    result = " ".join(kept).strip()
    if result and result != text:
        result += " ... The rest is on screen."
    return result


class MicUnavailableError(Exception):
    """Raised when the audio input device cannot be opened at all."""


def open_microphone(device_index):
    """Open a microphone, surfacing failures that SpeechRecognition hides.

    Microphone.__enter__ swallows the exception raised by audio.open() and
    leaves self.stream as None, so the real error only resurfaces later as a
    confusing "'NoneType' object has no attribute 'close'".
    """
    source = sr.Microphone(device_index=device_index)
    try:
        source.__enter__()
    except Exception as e:
        raise MicUnavailableError(
            f"Could not open microphone at index {device_index}: {e}"
        ) from e

    if getattr(source, "stream", None) is None:
        try:
            source.audio.terminate()
        except Exception:
            pass
        raise MicUnavailableError(
            f"Could not open microphone at index {device_index}. "
            "Another application (an audio enhancer such as FxSound, a "
            "meeting app, or a browser) is likely holding the device."
        )
    return source


def is_real_microphone(name):
    """False for loopback/virtual endpoints that capture the wrong audio.

    A "Stereo Mix" records whatever the speakers are playing, and
    "Microsoft Sound Mapper" is a virtual placeholder. Both open without
    error, so without this check the assistant silently transcribes the
    user's music instead of their speech.
    """
    if not name:
        return False
    low = name.lower()
    return not any(
        b in low for b in ("stereo mix", "loopback", "virtual",
                          "input ()", "sound mapper")
    )


def candidate_devices():
    """Ordered list of (index, name) worth trying, best candidate first.

    Device indices are not stable: they shift whenever a driver or an audio
    application loads or unloads. So we rank by name, then verify by
    actually opening each one rather than trusting the enumeration order.
    """
    override = os.getenv("MIC_DEVICE_INDEX")
    if override is not None:
        try:
            idx = int(override)
            pa = sr.Microphone.get_pyaudio().PyAudio()
            try:
                name = pa.get_device_info_by_index(idx)["name"]
            except Exception:
                name = "unknown"
            finally:
                pa.terminate()
            print(f"Using microphone from MIC_DEVICE_INDEX={idx}")
            return [(idx, name)]
        except ValueError:
            print(f"Invalid MIC_DEVICE_INDEX={override!r}, ignoring.")

    pa = sr.Microphone.get_pyaudio().PyAudio()
    try:
        ordered = []

        try:
            d = pa.get_default_input_device_info()
            ordered.append((d["index"], d["name"]))
        except Exception:
            pass  # no default set

        candidates = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                candidates.append((i, info["name"]))

        def rank(item):
            _i, name = item
            low = name.lower()
            # Loopback and virtual endpoints capture system audio rather than
            # a person's voice, so they go last. Note that a Bluetooth
            # headset is a genuine microphone even though its name never says
            # "mic", so we test for loopback before looking at the name.
            if not is_real_microphone(name):
                return 3
            if "microphone" in low or "mic" in low:
                return 0     # a dedicated mic is usually the best input
            if "headset" in low:
                return 1     # headset mic: real, but closer to the mouth
            return 2         # some other real capture device

        candidates.sort(key=rank)

        for item in candidates:
            if item not in ordered:
                ordered.append(item)
        return ordered
    finally:
        pa.terminate()


def peak_amplitude(data):
    """Largest absolute sample in raw 16-bit PCM bytes.

    SpeechRecognition hands back signed little-endian 16-bit samples, which
    is what every supported backend expects, so this is a safe read.
    """
    usable = len(data) - (len(data) % 2)
    if usable <= 0:
        return 0
    samples = array.array("h")
    samples.frombytes(data[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    peak = 0
    for value in samples:
        magnitude = -value if value < 0 else value
        if magnitude > peak:
            peak = magnitude
    return peak


def rms_amplitude(data):
    """Root-mean-square amplitude of raw 16-bit PCM bytes.

    RMS is used in preference to peak amplitude when comparing microphones.
    A single door slam or click gives a huge peak on a device that is
    otherwise dead, whereas RMS tracks sustained energy, which is what
    speech actually produces. On a silent endpoint RMS sits near 1-5; a mic
    that is genuinely picking you up reads in the hundreds.
    """
    usable = len(data) - (len(data) % 2)
    if usable <= 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(data[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    total = 0
    for value in samples:
        total += value * value
    return math.sqrt(total / len(samples))


def zero_sample_fraction(data):
    """Fraction of raw 16-bit PCM samples that are exactly zero.

    Genuine microphone audio is never exactly zero because the converter's
    noise floor is always present, whereas an input with no data source
    behind it returns flat digital silence. This distinguishes the two
    without needing to know what the room sounds like.

    Empty input counts as all-zero: no data is not usable audio.
    """
    usable = len(data) - (len(data) % 2)
    if usable <= 0:
        return 1.0
    samples = array.array("h")
    samples.frombytes(data[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    zeros = 0
    for value in samples:
        if value == 0:
            zeros += 1
    return zeros / len(samples)


def lag1_autocorrelation(data):
    """Lag-1 autocorrelation of raw 16-bit PCM, or 0.0 when undefined.

    This measures continuity rather than level. Speech sampled at tens of
    kilohertz changes only slightly from one sample to the next, so the
    series is strongly autocorrelated; measured on real speech this returns
    0.95 to 0.98. An endpoint handing back a spike train, sparse noise, or
    any other stand-in for audio scores near zero or below, because its
    consecutive samples carry no relationship to each other.

    Because it is normalised, it is unaffected by how loud the input is, so
    it separates a roaring broken endpoint from quiet speech without any
    amplitude threshold. A constant input has no variance and is reported
    as 0.0, which is not continuity.
    """
    usable = len(data) - (len(data) % 2)
    if usable < 4:
        return 0.0
    samples = array.array("h")
    samples.frombytes(data[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    n = len(samples)
    mean_a = math.fsum(samples) / n
    mean_b = math.fsum(samples[1:]) / (n - 1)
    cross = 0.0
    var_a = 0.0
    var_b = 0.0
    for i in range(n - 1):
        a = samples[i] - mean_a
        b = samples[i + 1] - mean_b
        cross += a * b
        var_a += a * a
        var_b += b * b
    if var_a <= 0.0 or var_b <= 0.0:
        return 0.0
    return cross / math.sqrt(var_a * var_b)


def measure_device(source, seconds=MIC_PROBE_SECONDS):
    """Record a short sample and return its RMS level, or None if unusable.

    Returns None if the device produced no data at all, and also if the data
    is not live microphone audio. Opening without error does not mean a
    device can hear anything: Windows hands out endpoints that capture
    digital silence, and a broken endpoint can return a fixed repeating
    buffer whose pattern registers as sustained energy. Both pass a naive
    amplitude probe, so MERLIN would announce "Microphone ready" and then
    every utterance would come back as "could not understand it".

    Two back-to-back captures are taken to separate the cases:

    * identical consecutive captures mean a static buffer, not a stream;
    * a high fraction of exactly-zero samples means digital silence;
    * a capture that is partly digital silence yet shows no continuity is
      a varying artefact rather than audio, which is the case a level or a
      zero fraction on its own will miss.

    A real microphone fails none of these tests, so it is measured as
    before.
    """
    half = max(seconds / 2.0, 0.25)
    try:
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        first = recognizer.record(source, duration=half).get_raw_data()
        second = recognizer.record(source, duration=half).get_raw_data()
    except Exception:
        return None

    if not first or not second:
        return None
    if first == second:
        # The endpoint returned the same bytes twice: a fixed buffer.
        return None

    combined = first + second
    zeros = zero_sample_fraction(combined)
    if zeros >= MIC_MAX_ZERO_FRACTION:
        return None
    if zeros >= MIC_CONTINUITY_ZERO_GATE and \
            lag1_autocorrelation(combined) < MIC_MIN_CONTINUITY:
        return None
    return rms_amplitude(combined)


def find_working_microphone():
    """Pick an input device that opens *and* actually hears something.

    Two separate failures are handled here:

    1. the device cannot be opened at all (disabled, or held by another app);
    2. the device opens but captures silence, which looks identical to a
       working microphone until you try to speak to it.

    Windows happily lists several endpoints under one name, with only one of
    them wired to real hardware, so we measure each candidate and keep the
    one carrying the most energy.
    """
    tried = []
    best = None  # (rms, index, name)
    limit = MIC_PROBE_LIMIT

    for index, name in candidate_devices():
        if limit and len(tried) >= limit:
            break
        try:
            source = open_microphone(index)
        except MicUnavailableError as e:
            tried.append((index, name, str(e)))
            continue

        level = measure_device(source)
        close_microphone(source)

        if level is None:
            tried.append((index, name,
                          "no live audio (digital silence or a fixed buffer)"))
            continue
        if best is None or level > best[0]:
            best = (level, index, name)

    if best is None:
        print("No input device is carrying live microphone audio.")
        for index, name, err in tried:
            print(f"  tried index {index} ({name}): {err}")
        if any("stereo mix" in name.lower() for _i, name, _e in tried):
            print("  note: Stereo Mix captures system audio, not your voice.")
        print("  A Bluetooth headset only exposes its microphone while the")
        print("  Hands-Free profile is active; if its capture endpoints fail")
        print("  with Errno -9999 the stereo (A2DP) link is up instead, and")
        print("  the headset mic cannot be reached at all. Connect a USB")
        print("  microphone, or fix the headset, then re-run.")
        return None, None

    level, index, name = best
    if level >= MIC_MIN_RMS:
        print(f"Microphone ready: index {index} ({name}) [level {level:.1f}]")
    else:
        # Not fatal: the user may simply not have spoken during the probe.
        print(f"Microphone: index {index} ({name}) [level {level:.1f}, "
              f"want {MIC_MIN_RMS}]")
        print("Speak during start-up so MERLIN can verify the mic. If the")
        print("level stays low, raise it: mmsys.cpl -> Recording -> "
              "Properties -> Levels.")
    return index, name


def close_microphone(source):
    """Release a microphone, ignoring teardown errors."""
    if source is None:
        return
    try:
        source.__exit__(None, None, None)
    except Exception:
        pass


def is_mic_fatal(exc):
    """True if this exception means we should stop rather than retry."""
    msg = str(exc).lower()
    fatal_markers = (
        "no default input device",
        "no input device",
        "input device",
        "microphone",
        "audio error",
        "insufficient data",
    )
    return isinstance(exc, (sr.RequestError, OSError, AttributeError)) and any(
        m in msg for m in fatal_markers
    )


# The wake word, plus the ways Google's recogniser commonly mishears it.
# "Merlin" is not a common English word, so it is regularly transcribed as
# "Berlin" or "Marlin". Without accepting those, MERLIN simply never wakes.
WAKE_WORDS = frozenset({"merlin", "marlin", "berlin"})


def contains_wake_word(text):
    """True if a wake word appears as a whole word, not a substring.

    Matching is done token by token so that unrelated words containing these
    letters ("germ", "terminal", "submarine") do not trigger the assistant.
    """
    if not text or not isinstance(text, str):
        return False
    tokens = re.findall(r"[a-z]+", text.lower())
    return any(token in WAKE_WORDS for token in tokens)


WEBSITES = {
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "facebook": "https://facebook.com",
    "instagram": "https://instagram.com",
    "leetcode": "https://leetcode.com",
    "github": "https://github.com",
}

# Only treat a phrase as a news request when it is actually asking for
# headlines. A bare substring test would hijack ordinary questions like
# "what is in the news about india" away from the assistant.
NEWS_REQUESTS = {
    "news", "the news", "top news", "latest news", "news headlines",
    "headlines", "the headlines", "top headlines", "latest headlines",
    "give me the news", "tell me the news", "read the news",
    "what is the news", "give me news", "play the news", "news please",
}

CLEAR_REQUESTS = {
    "clear chat", "reset chat", "clear history", "forget everything",
    "new chat", "restart chat",
}

EXIT_REQUESTS = {"shutdown merlin", "stop merlin", "exit", "quit", "goodbye"}


def open_site(words):
    for name, url in WEBSITES.items():
        if name in words:
            webbrowser.open(url)
            speak(f"Opening {name}")
            return
    speak("Which site should I open?")


def play_song(words):
    song = " ".join(words[1:]).strip()
    if not song:
        speak("Which song to play?")
        return
    normalised = song.replace(" ", "")
    for key, url in musicLibrary.music.items():
        if key.lower().replace(" ", "") == normalised:
            webbrowser.open(url)
            speak(f"Playing {key}")
            return
    speak("Song not found")


def _fetch_articles(url, params):
    """Return a list of articles, or None if the request failed."""
    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json().get("articles") or []
    except ValueError:
        return None


def fetch_news_articles():
    """Get headlines, working around NewsAPI plan restrictions.

    NewsAPI's free plan does not serve top-headlines for every country; for
    example country=in returns an empty list while country=us returns data.
    We therefore try the configured country first and fall back to a country
    that the free plan is known to serve.

    Returns a list of articles, or None if every request failed (offline,
    bad key, DNS). Distinguishing "request failed" from "no stories" matters:
    the first is an error worth reporting, the second is not.
    """
    preferred = NEWS_COUNTRY
    any_request_succeeded = False

    for country in _country_order(preferred):
        articles = _fetch_articles(
            "https://newsapi.org/v2/top-headlines",
            {"country": country, "apiKey": NEWS_API_KEY},
        )
        if articles is None:
            continue
        any_request_succeeded = True
        if articles:
            if country != preferred:
                print(f"No headlines for '{preferred}' on this NewsAPI plan; "
                      f"showing '{country}' instead.")
            return articles[:5]

    # Last resort: the search endpoint is available on the free plan even
    # when top-headlines is restricted for the chosen country.
    articles = _fetch_articles(
        "https://newsapi.org/v2/everything",
        {"q": NEWS_QUERY, "pageSize": 5, "sortBy": "publishedAt",
         "language": "en", "apiKey": NEWS_API_KEY},
    )
    if articles is None:
        return None if not any_request_succeeded else []
    return articles[:5]


def _country_order(preferred):
    """Preferred country first, then the fallbacks the free plan supports."""
    order = [preferred]
    for fallback in NEWS_FALLBACK_COUNTRIES:
        if fallback not in order:
            order.append(fallback)
    return order


def read_news():
    articles = fetch_news_articles()
    if articles is None:
        speak("Failed to fetch news")
        return

    spoken_any = False
    for article in articles:
        if isinstance(article, dict):
            title = article.get("title")
            if title:
                speak(title)
                spoken_any = True

    if not spoken_any:
        speak("No news headlines available right now")


def answer_question(text):
    reply = gemini.send(text)
    print(reply)
    speak(reply)


def processCommand(c):
    if not isinstance(c, str):
        return
    text = c.strip()
    if not text:
        return

    low = text.lower().rstrip("?.!")
    words = low.split()

    def starts_with(*verbs):
        return bool(words) and words[0] in verbs

    if starts_with("open", "launch", "browse", "visit", "go"):
        open_site(words)
    elif starts_with("play"):
        play_song(words)
    elif low in NEWS_REQUESTS or (words and words[0] == "news"):
        read_news()
    elif low in CLEAR_REQUESTS:
        gemini.reset()
        speak("Chat history cleared")
    elif low in EXIT_REQUESTS:
        speak("Shutting down")
        sys.exit()
    else:
        answer_question(text)


def run():
    """Main listening loop."""
    print(f"Gemini backend: {gemini.backend}")
    if gemini._config_error:
        print("\nWARNING: GEMINI_API_KEY is not set, so questions asked to")
        print("Gemini will not be answered. Opening a website or reading")
        print("the news still works. Set the key and start again:\n")
        print("    setx GEMINI_API_KEY \"<your key>\"\n")
        print("  then open a NEW terminal.")
    if not NEWS_API_KEY:
        print("NOTE: NEWS_API_KEY is not set, so 'news' will not work.")

    device_index, device_name = find_working_microphone()
    if device_index is None:
        print("MERLIN cannot start without working audio input.")
        print("Check that a microphone is connected and enabled in Windows")
        print("Sound settings, and is not in use by another app. Set")
        print("MIC_DEVICE_INDEX to choose a specific input device.")
        return 1

    if device_name and not is_real_microphone(device_name):
        print(f"Warning: '{device_name}' is not a microphone. It captures")
        print("system audio, so MERLIN will hear what you play, not you.")

    speak("Initializing MERLIN")

    print("\n" + "-" * 58)
    print("  MERLIN is listening. Say:  'merlin'")
    print("  Then wait for 'Yes master' and give a command, e.g.")
    print("  'open google'  /  'news'  /  'what is photosynthesis'")
    print("  Press Ctrl+C to quit.")
    print("-" * 58 + "\n")

    mic_failures = 0
    other_failures = 0
    silent_attempts = 0

    while True:
        source = None
        try:
            source = open_microphone(device_index)
            try:
                print("Adjusting for noise...")
                recognizer.adjust_for_ambient_noise(source, duration=2)

                print("Listening for the wake word...")
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=5)
                word = recognizer.recognize_google(audio)
                print("Heard:", word)
                mic_failures = 0
                other_failures = 0
                silent_attempts = 0
            finally:
                close_microphone(source)
                source = None

            if not contains_wake_word(word):
                continue

            speak("Yes master")

            source = open_microphone(device_index)
            try:
                print("Listening for a command...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=8)
                command = recognizer.recognize_google(audio)
                print("Command:", command)
                processCommand(command)
            finally:
                close_microphone(source)
                source = None

        except KeyboardInterrupt:
            print("\nExiting.")
            return 0

        except sr.WaitTimeoutError:
            # Normal: nobody spoke within the window. Just listen again.
            # If this keeps happening the chosen device may be deaf, so we
            # count consecutive misses and let the loop re-select a device.
            silent_attempts += 1
            if silent_attempts >= MIC_RESELECT_AFTER:
                silent_attempts = 0
                new_index, _ = find_working_microphone()
                if new_index is not None and new_index != device_index:
                    print(f"Switching to input {new_index}.")
                    device_index = new_index
            continue

        except sr.UnknownValueError:
            # Normal: heard something unintelligible. Just listen again.
            print("Didn't catch that, waiting...")
            silent_attempts += 1
            if silent_attempts >= MIC_RESELECT_AFTER:
                silent_attempts = 0
                new_index, _ = find_working_microphone()
                if new_index is not None and new_index != device_index:
                    print(f"Switching to input {new_index}.")
                    device_index = new_index
            continue

        except sr.RequestError as e:
            # Speech-to-text service failed (offline, rate limited, etc).
            print(f"Speech recognition service error: {e}")
            time.sleep(2)
            continue

        except MicUnavailableError as e:
            # The chosen device stopped working. This happens legitimately:
            # another app grabs the mic, or Windows re-enumerates devices and
            # shifts the indices. Re-probe instead of hammering a dead index.
            mic_failures += 1
            if mic_failures >= 3:
                print(f"\nMicrophone unavailable 3x ({e})")
                print("Looking for another input device...")
                new_index, new_name = find_working_microphone()
                if new_index is None:
                    print("MERLIN cannot find any working audio input.")
                    print("Close any app using the microphone (FxSound, Zoom,")
                    print("Teams, browsers) or enable it in Windows Sound")
                    print("settings. Set MIC_DEVICE_INDEX to force a device.")
                    return 1
                if new_index != device_index:
                    print(f"Switched to input {new_index} ({new_name}).")
                    device_index = new_index
                    device_name = new_name
                    mic_failures = 0
                    continue
                print("The same device is the only option; waiting.")
            time.sleep(2)
            continue

        except Exception as e:
            # Anything unexpected. Retry a bounded number of times so a
            # persistent problem cannot spin forever at full CPU.
            if is_mic_fatal(e):
                mic_failures += 1
                if mic_failures >= 3:
                    print(f"\nMicrophone problem 3x: {e}")
                    new_index, new_name = find_working_microphone()
                    if new_index is None:
                        print("No working audio input found. Close apps using "
                              "the mic, or set MIC_DEVICE_INDEX.")
                        return 1
                    if new_index != device_index:
                        print(f"Switched to input {new_index} ({new_name}).")
                        device_index = new_index
                        device_name = new_name
                        mic_failures = 0
                        continue
                print(f"Microphone problem ({mic_failures}/3): {e}")
                time.sleep(2)
                continue

            print(f"Error: {e}")
            other_failures += 1
            if other_failures >= 10:
                print("\nToo many consecutive unexpected errors, stopping.")
                print(f"Last error: {e}")
                return 1
            time.sleep(1)
        finally:
            close_microphone(source)


if __name__ == "__main__":
    sys.exit(run())