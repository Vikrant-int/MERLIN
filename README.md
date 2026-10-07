# MERLIN

MERLIN is a Windows voice assistant. It listens for a wake word, transcribes what
you say, and then either runs a local command or sends the question to Google
Gemini and speaks the answer back.

Everything runs locally except the network calls: speech is transcribed with the
Google Web Speech API, answers come from Gemini, and headlines come from NewsAPI.

## Features

* **Wake word** — say `merlin` (also recognised: `marlin`, `berlin`) and wait for
  the confirmation prompt before giving a command.
* **Open websites** — `open google`, `launch youtube`, `visit github`,
  `open facebook`, `open instagram`, `open leetcode`.
* **Play music** — `play <song>`, matched against the entries in
  `musicLibrary.py`.
* **Read the news** — `news`, `top headlines`, `read the news`. Uses NewsAPI's
  `top-headlines` endpoint and falls back to `everything` when the free plan
  does not serve the configured country.
* **Ask anything** — any other sentence is passed to Gemini and read aloud.
* **Conversation control** — `clear chat` / `reset chat` starts a fresh Gemini
  conversation; `exit`, `quit`, `goodbye`, `shutdown merlin` stops the assistant.
* **Offline text-to-speech** — via `pyttsx3` (SAPI on Windows).
* **Microphone safeguards** — MERLIN probes candidate inputs, rejects endpoints
  that return digital silence or discontinuous noise, and refuses to start if no
  working microphone is found.

## Desktop app

`app.py` opens a native PySide6/Qt window around the same `main.py` backend —
nothing in the backend was rewritten to suit it.

* **Six pages** — Dashboard (greeting, assistant state orb, quick actions,
  recent activity), Chat, Voice, News, Music, Settings.
* **Frameless dark-premium window** with a custom title bar, a left sidebar with
  an active indicator, and edge-drag resizing. Minimum size 1000×650, light and
  dark themes, and reduced-motion is respected.
* **System tray** — Open MERLIN / Voice command / Settings / Quit; closing the
  window hides it to the tray instead of quitting (Settings → *Minimize to
  tray*).
* **Optional hotkey** — `Ctrl+Alt+M`, off by default, enabled in Settings.
* **Never blocks the window** — Gemini calls, news fetches, speech recognition,
  TTS and music playback all run on worker threads; the UI stays responsive and
  reports what it is doing.
* **Honest failure states** — a missing key, an unplugged microphone, a dead
  network or an API error each become a friendly message. No stack traces, no
  invented answers, no API key ever rendered on screen.

`main.py` keeps working exactly as before for console use.

## Requirements

| Requirement | Notes |
|---|---|
| **Windows** | MERLIN uses Windows audio endpoints and SAPI speech output. Not supported on Linux/macOS. |
| **Python 3.12** | The version this project is developed and tested on (`Python 3.12.1`). |
| **A working microphone** | MERLIN will not start without live audio input. See [Verify your microphone](#verify-your-microphone). |
| **Internet connection** | Required for speech transcription, Gemini answers and news. |
| **`GEMINI_API_KEY`** | Required to answer questions. Without it MERLIN still runs and still opens sites and reads news. |
| **`NEWS_API_KEY`** | Required for the `news` command only. |

Speech transcription uses Google's Web Speech API and does **not** need a key.

## Installation

Open **PowerShell** and run:

```powershell
git clone <repository-url>
cd mega_Project_1

python -m venv myprojectenv
myprojectenv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Add your API keys

MERLIN reads **Windows environment variables**. It does not load a `.env` file
automatically — `.env.example` documents the variable names for reference only.

Create a key at <https://aistudio.google.com/apikey> (Gemini) and
<https://newsapi.org> (news), then set them:

```powershell
setx GEMINI_API_KEY "<your key>"
setx NEWS_API_KEY "<your key>"
```

`setx` writes to your user profile, so **open a new terminal** afterwards —
already-running shells will not see the new values.

To keep a local copy for reference:

```powershell
Copy-Item .env.example .env
notepad .env
```

`.env` is ignored by git and will never be committed.

## Running

### Desktop app

```powershell
myprojectenv\Scripts\python.exe app.py
```

The window opens immediately and shows **Starting…** while the backend loads
(the first `import main` takes a few seconds) — the window keeps painting the
whole time. The sidebar status turns **Online** when the backend is ready.

Preferences live in `%LOCALAPPDATA%\MERLIN\settings.json`, outside the
repository. `.env` is **not** read by MERLIN; the keys must be real Windows
environment variables (see above).

### Console

```powershell
myprojectenv\Scripts\python.exe main.py
```

Say `merlin`, wait for `Yes master`, then give a command:

```
open google
news
what is photosynthesis
clear chat
quit
```

To pin a specific input device instead of letting MERLIN choose:

```powershell
$env:MIC_DEVICE_INDEX = "7"
myprojectenv\Scripts\python.exe main.py
```

Use `setx MIC_DEVICE_INDEX "7"` if you want it to persist across terminals.

## Verify your microphone

Run this **before** MERLIN. It shows a live level meter for every input device
and tells you which one actually carries microphone audio:

```powershell
myprojectenv\Scripts\python.exe mic_check.py
```

Speak when prompted (`merlin what is two plus two`). It prints the best device
index and saves `mic_check.wav` so you can play it back and confirm it contains
your voice.

This step matters: Windows often exposes *Stereo Mix* and Bluetooth *Hands-Free*
endpoints that are not real microphones. MERLIN discards those rather than
sending silence to the recogniser.

## Tests

```powershell
myprojectenv\Scripts\python.exe test_merlin.py
```

Runs the full backend regression suite (110 checks) without a microphone and
without network access — audio output and the network-backed layers are stubbed.

```powershell
myprojectenv\Scripts\python.exe tests_ui.py
```

Runs the desktop UI suite (60 checks) headless (`QT_QPA_PLATFORM=offscreen`), so
it works on CI and on a machine with no display. It builds the real window and
the real services and covers: startup while the backend imports, all six pages
and navigation, secret leakage, a missing Gemini key, a missing News key and a
failed news request, an absent microphone, GUI responsiveness during a blocking
backend call, the optional global hotkey, minimize/maximize/resize, the tray
menu, close-to-tray vs close-to-quit, and shutdown. It also saves a PNG of
every page in both themes and reads each one back to check it is not blank.

Exits `0` only when every check passes.

A live Gemini connectivity check is also available:

```powershell
myprojectenv\Scripts\python.exe test_gemini.py
```

This one does call the Gemini API, so `GEMINI_API_KEY` must be set.

## Packaging

Once the development version is verified, build the Windows executable:

```powershell
myprojectenv\Scripts\pip install "pyinstaller>=6.10,<7"
myprojectenv\Scripts\pyinstaller.exe --noconfirm MERLIN.spec
```

This produces `dist\MERLIN.exe` — a single windowed (no console) executable.
It needs no Python installation on the target machine and reads
`GEMINI_API_KEY` / `NEWS_API_KEY` from the Windows environment at run time, so
no key is ever baked into the binary; without them it still starts and says
what is missing.

`build/` and `dist/` are git-ignored — never commit a generated executable.
`MERLIN.spec` itself is tracked.

## Diagnostics

| Script | Purpose |
|---|---|
| `mic_check.py` | Interactive microphone finder with a live level meter. |
| `mic_test.py` | One-shot speech recognition test — records once and prints the recognised text. |
| `b.py` | Block-level audio probe for inspecting a specific device. |
| `voice_gemini.py` | Standalone voice + Gemini round trip. |
| `test_gemini.py` | Standalone Gemini connectivity check. |

## Project structure

```
mega_Project_1/
├── app.py               Entry point for the desktop app
├── main.py             Assistant: wake word, command dispatch, mic selection
├── musicLibrary.py     Song name → URL map used by the "play" command
├── mic_check.py        Microphone finder (also provides the shared is_live check)
├── mic_test.py         One-shot recognition test
├── b.py                Audio block probe
├── voice_gemini.py     Standalone voice + Gemini script
├── test_merlin.py      Backend regression suite (110 checks, offline)
├── tests_ui.py         Desktop UI suite (60 checks, headless)
├── test_gemini.py      Live Gemini connectivity check
├── MERLIN.spec         PyInstaller recipe for dist\MERLIN.exe
├── services/           Thin adapters between main.py and the UI
│   ├── core.py             Speech thread, task pool, backend ownership
│   ├── assistant_service.py  Gemini chat + honest credential status
│   ├── news_service.py     Headlines off the GUI thread
│   ├── music_service.py    Playlist / play / pause without invented state
│   ├── voice_service.py    Mic ownership, device list, one-shot dictation
│   ├── system_audio.py     Real Windows endpoint volume (pycaw)
│   ├── settings_store.py   %LOCALAPPDATA%\MERLIN\settings.json
│   └── audio_lock.py       Serialises PortAudio access across threads
├── ui/                  PySide6 shell (signals only; no blocking calls)
│   ├── app.py / window.py   Bootstrap, frameless window, tray, navigation
│   ├── state.py             Backend signal → one honest UI state
│   ├── theme.py             Two palettes + the whole stylesheet
│   ├── hotkey.py            Optional Ctrl+Alt+M via RegisterHotKey
│   ├── components/          Icons, orb, title bar, sidebar, banners, images
│   └── views/               Dashboard, Chat, Voice, News, Music, Settings
├── requirements.txt    Pinned direct dependencies
├── .env.example        Environment variable names (no real values)
└── .gitignore          Keeps secrets, venvs and generated files out of git
```

`main.py` and the other backend files are **not** modified by the UI; every
integration goes through `services/`.

## Configuration reference

All optional — MERLIN runs with sensible defaults if they are unset.

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | *(none)* | Gemini API key. Required for questions. |
| `NEWS_API_KEY` | *(none)* | NewsAPI key. Required for `news`. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use. |
| `NEWS_COUNTRY` | `in` | Preferred NewsAPI country. |
| `NEWS_QUERY` | `india OR travel` | Search query for the `everything` fallback. |
| `MIC_DEVICE_INDEX` | *(auto)* | Force a specific input device index. |
| `MIC_MIN_RMS` | `20` | Minimum level for a device to be considered usable. |
| `MIC_PROBE_LIMIT` | `6` | How many devices to probe. |
| `MIC_PROBE_SECONDS` | `2` | Seconds to probe each device. |
| `MIC_RESELECT_AFTER` | `5` | Re-select the microphone after this many failures. |
| `MIC_MAX_ZERO_FRACTION` | `0.4` | Reject captures above this share of exact-zero samples. |
| `MIC_MIN_CONTINUITY` | `0.5` | Minimum lag-1 autocorrelation for a silent capture. |

## Troubleshooting

**`pip install PyAudio` fails to build.**
PyAudio ships prebuilt Windows wheels for **CPython 3.12 on 64-bit Intel**
(`cp312-cp312-win_amd64`), which is the supported combination here. On a Python
version without a wheel, pip must compile it and you will need the
[Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
Stick to 3.12 64-bit to avoid this.

**`MERLIN cannot start without working audio input`.**
Run `mic_check.py` first. Check that a microphone is connected, enabled, set as
the Windows default input, and not exclusively held by another application.
Bluetooth headset microphones are only exposed while the Hands-Free profile is
active — see `mmsys.cpl` → *Recording*.

**`GEMINI_API_KEY is not set`.**
Set it with `setx` and open a **new** terminal. MERLIN warns but keeps running.

**`news` does nothing.**
`NEWS_API_KEY` is unset, or the free NewsAPI plan is not serving the configured
country. MERLIN already falls back to another country and then to the search
endpoint.

**Speech transcribes as nonsense.**
Confirm your microphone with `mic_check.py` and play back the saved
`mic_check.wav`. If that recording does not contain your voice, the problem is
the Windows input device, not MERLIN.

**The desktop window never appears.**
Run `myprojectenv\Scripts\python.exe app.py` from a terminal and read the
output. A missing Qt platform plugin (`qwindows`) means the PySide6 install is
incomplete — reinstall it with
`myprojectenv\Scripts\pip install --force-reinstall PySide6`.

**The sidebar stays on "Starting…".**
The backend import failed. The window itself will show the reason rather than a
stack trace; running `myprojectenv\Scripts\python.exe main.py` prints the same
error directly.

**Closing the window does not quit MERLIN.**
That is *Minimize to tray*. Use **Quit** from the tray menu (right-click the
icon), or turn the option off in Settings.

**The `Ctrl+Alt+M` hotkey does nothing.**
Windows reserves some combinations, and the hotkey is off by default. Turn it on
in Settings; if it still does not fire, another application already owns that
combination. The Settings page always states whether the hotkey registered.

**The Music page's level slider is missing.**
Endpoint volume could not be read (pycaw/Core Audio unavailable). Playback keys
still work; only the slider is hidden, rather than showing a fake number.

## Notes

* `.env` and the `myprojectenv/` virtual environment are intentionally
  git-ignored, as are `*.wav`, `*.log` and `__pycache__/`.
* No API keys are stored anywhere in this repository. Values are read from the
  environment at runtime with `os.getenv`.
