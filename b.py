"""Raw PyAudio check: which input devices can we actually hear from?

Windows lists the same microphone several times under one name, and most of
those duplicates capture digital silence while opening without error. Picking
by name alone therefore picks a deaf device, so this measures each candidate
and reports the real levels.

    myprojectenv\\Scripts\\python.exe b.py
"""
import math
import struct

import pyaudio

# Reuse the same liveness rules as mic_check.py so every diagnostic in this
# project rejects a dead endpoint the same way. mic_check is safe to import:
# its own work sits behind `if __name__ == "__main__"`.
from mic_check import is_live

# Fallback only. Capture uses each device's own defaultSampleRate (see
# measure), because Bluetooth Hands-Free endpoints commonly run at 16000
# or 8000 rather than 44100.
RATE = 44100
CHUNK = 1024
SECONDS = 2

# Loopback / virtual endpoints capture system audio, not a person speaking.
LOOPBACK = ("stereo mix", "loopback", "virtual", "input ()",
            "sound mapper", "hands-free")

p = pyaudio.PyAudio()

candidates = []
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info.get("maxInputChannels", 0) > 0:
        candidates.append((i, info["name"]))

if not candidates:
    print("No input device found. Plug one in and try again.")
    p.terminate()
    raise SystemExit(1)


def rank(item):
    name = item[1].lower()
    if any(b in name for b in LOOPBACK):
        return 2
    if "microphone" in name or "mic" in name or "headset" in name:
        return 0
    return 1


def measure(index):
    """Return RMS level of a short sample, or None if it cannot be opened."""
    # Open at this device's own rate. Windows exposes the same microphone
    # at several rates, and a Bluetooth Hands-Free endpoint is typically
    # 16000 or 8000 rather than 44100. Forcing 44100 fails outright, which
    # would report a usable microphone as unavailable.
    try:
        rate = int(p.get_device_info_by_index(index).get(
            "defaultSampleRate", RATE))
    except Exception:
        rate = RATE

    try:
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=rate,
                        input=True, input_device_index=index,
                        frames_per_buffer=CHUNK)
    except Exception as e:
        return None, str(e)

    blocks = []
    try:
        for _ in range(int(rate / CHUNK * SECONDS)):
            block = stream.read(CHUNK)
            if block:
                blocks.append(block)
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass

    if not blocks:
        return None, "returned no audio data"

    raw = b"".join(blocks)

    # Opening without error does not mean an endpoint can hear. Some hand
    # back flat digital silence, and one on this machine hands back a
    # stand-in buffer whose level registers in the thousands while carrying
    # no voice at all. Printing that level would tell the user to select a
    # microphone that cannot hear them, so it is rejected here instead.
    live, detail = is_live(raw)
    if not live:
        return None, detail

    samples = struct.unpack(f"{len(raw) // 2}h", raw)
    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    return rms, ""


candidates.sort(key=rank)

print("Speak now -- measuring each input device for %ds.\n" % SECONDS)
best = None      # loudest real microphone
best_loopback = None  # loudest loopback, reported but never chosen

for index, name in candidates:
    level, err = measure(index)
    if level is None:
        print("  %-44s unavailable: %s" % (name[:44], err[:30]))
        continue
    bar = "#" * min(40, int(level / 5))
    print("  %-44s level=%8.1f |%s" % (name[:44], level, bar))
    if rank((index, name)) == 2:
        # Loopback records system audio, so it can be loud while hearing
        # nothing of the user. Never let it win.
        if best_loopback is None or level > best_loopback[0]:
            best_loopback = (level, index, name)
        continue
    if best is None or level > best[0]:
        best = (level, index, name)

if best is None:
    print("\nNo real microphone could be opened.")
    if best_loopback:
        print("The only thing that opened was %s (device %d), which records"
              % (best_loopback[2], best_loopback[1]))
        print("system audio rather than your voice, so it will not help.")
    print("Connect your headset or microphone and try again.")
    print("Another application using the mic may also be blocking it --")
    print("close FxSound / Zoom / Teams / browsers and retry.")
    p.terminate()
    raise SystemExit(1)

level, index, name = best
print("\nLoudest microphone: device %d (%s) level=%.1f" % (index, name, level))

if level < 20:
    print("\nThat is effectively silence, so nothing will be recognised.")
    print("Raise the microphone volume: mmsys.cpl -> Recording tab ->")
    print("Properties -> Levels -> Microphone Volume 100, Mute unchecked.")
else:
    print("Microphone working. Start MERLIN with:")
    print("    $env:MIC_DEVICE_INDEX=%d" % index)

p.terminate()