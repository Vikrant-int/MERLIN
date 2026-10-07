"""MERLIN microphone check -- finds out whether your mic actually works.

Run this, then SPEAK when the countdown starts. It shows a live level meter
for every input device so you can see exactly which one hears you.

    myprojectenv\\Scripts\\python.exe mic_check.py

Once it reports the best device, start MERLIN with it:

    $env:MIC_DEVICE_INDEX=<number>
    myprojectenv\\Scripts\\python.exe main.py
"""
import math
import struct
import sys
import time
import wave

import pyaudio

# Fallback only. Capture uses each device's own defaultSampleRate (see
# device_rate), because Bluetooth Hands-Free endpoints commonly run at
# 16000 or 8000 rather than 44100.
RATE = 44100
CHUNK = 1024
SECONDS_PER_DEVICE = 4

# Endpoints that are not microphones, or that Windows leaves as a stub.
SKIP = ("stereo mix", "sound mapper", "input ()", "loopback",
        "hands-free", "primary sound capture", "realtek hd audio stereo input")

# Speech should comfortably exceed this. Room noise is usually below 300.
SPEECH_LEVEL = 800

# A real microphone never emits exactly-zero samples: the converter's noise
# floor fills every slot, so live speech measures under 1% zero samples. An
# endpoint with no signal behind it returns flat digital silence, and one of
# them on this machine measured 91-100% zero samples while still showing a
# peak in the thousands -- which is what made a dead endpoint look like
# "SPEECH DETECTED". Anything at or above this fraction is skipped.
MAX_ZERO_FRACTION = 0.4

# Second, independent test. The zero fraction alone does not catch a broken
# endpoint that hands back a *varying* buffer whose zero share sits just
# under the limit above -- one such capture measured 38% and was selected,
# after which every utterance came back as "could not understand it". Every
# real acoustic signal is band-limited by the transducer, so one sample
# predicts the next closely: lag-1 autocorrelation measured +0.954 to +0.975
# across six speech samples, while the artefact measured -0.321 to +0.106.
MIN_CONTINUITY = 0.5
# The continuity test only runs once a capture already shows real digital
# silence. Genuine microphone audio essentially never does -- the converter's
# noise floor fills every sample -- so this gate keeps the test away from
# quiet-but-working microphones whose noise floor might not be band-limited.
CONTINUITY_ZERO_GATE = 0.10


def zero_fraction(raw):
    """Fraction of raw 16-bit PCM samples that are exactly zero."""
    count = len(raw) // 2
    if count <= 0:
        return 1.0
    samples = struct.unpack(f"{count}h", raw[:count * 2])
    return sum(1 for x in samples if x == 0) / count


def lag1_autocorrelation(raw):
    """Lag-1 autocorrelation of raw 16-bit PCM, or 0.0 when undefined.

    Measures continuity rather than level, so it is unaffected by how loud
    the input is. Speech and any other band-limited acoustic signal scores
    near 1.0; a spike train or sparse noise standing in for audio scores
    near zero or below, because its consecutive samples are unrelated.
    """
    count = len(raw) // 2
    if count < 4:
        return 0.0
    samples = struct.unpack(f"{count}h", raw[:count * 2])
    n = len(samples)
    mean_a = math.fsum(samples) / n
    mean_b = math.fsum(samples[1:]) / (n - 1)
    cross = var_a = var_b = 0.0
    for i in range(n - 1):
        a = samples[i] - mean_a
        b = samples[i + 1] - mean_b
        cross += a * b
        var_a += a * a
        var_b += b * b
    if var_a <= 0.0 or var_b <= 0.0:
        return 0.0
    return cross / math.sqrt(var_a * var_b)


def is_live(raw):
    """Whether a capture carries genuine microphone audio.

    Returns (live, detail). `detail` explains the failure when live is
    False, so callers can report *why* an endpoint was skipped instead of
    showing a level meter that means nothing. Shared with b.py so every
    diagnostic in this project rejects dead endpoints the same way.
    """
    frac = zero_fraction(raw)
    if frac >= MAX_ZERO_FRACTION:
        return False, f"{frac * 100:.0f}% of samples are exactly zero"
    if frac >= CONTINUITY_ZERO_GATE:
        rho = lag1_autocorrelation(raw)
        if rho < MIN_CONTINUITY:
            return False, (f"{frac * 100:.0f}% zero and discontinuous "
                           f"(continuity {rho:+.2f}, want "
                           f"{MIN_CONTINUITY:.2f})")
    return True, ""


def bar(peak, width=44):
    filled = min(width, int(peak / 700))
    colour = "#" * filled
    if peak >= SPEECH_LEVEL:
        mark = " <-- SPEECH DETECTED"
    elif peak >= 200:
        mark = " (low, but something)"
    else:
        mark = " (near silence)"
    return f"[{colour:<{width}}] peak={peak:>6}{mark}"


def input_devices():
    p = pyaudio.PyAudio()
    out = []
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d.get("maxInputChannels", 0) > 0:
            name = d["name"]
            if any(b in name.lower() for b in SKIP):
                continue
            out.append((i, name))
    p.terminate()
    return out


def device_rate(index):
    """The sample rate this device actually runs at.

    Windows exposes the same microphone at several rates: a stereo
    endpoint is usually 44100, while a Bluetooth Hands-Free endpoint is
    typically 16000 or 8000. Opening one at a rate it does not support
    fails outright, so forcing 44100 everywhere reported usable
    microphones as unavailable -- the opposite of what a diagnostic
    should do. Falls back to RATE if the device cannot be queried.
    """
    p = pyaudio.PyAudio()
    try:
        return int(p.get_device_info_by_index(index).get(
            "defaultSampleRate", RATE))
    except Exception:
        return RATE
    finally:
        p.terminate()


def record_device(index, seconds):
    """Record from a device, returning raw 16-bit mono bytes or None."""
    rate = device_rate(index)
    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=rate,
                        input=True, input_device_index=index,
                        frames_per_buffer=CHUNK)
    except Exception:
        p.terminate()
        return None

    blocks = []
    per_read = CHUNK / rate
    next_meter = time.time()
    try:
        for _ in range(int(seconds / per_read)):
            block = stream.read(CHUNK)
            if block:
                blocks.append(block)
            now = time.time()
            if now >= next_meter:
                recent = b"".join(blocks[-4:])
                if recent:
                    s = struct.unpack(f"{len(recent) // 2}h", recent)
                    print("      " + bar(max(abs(x) for x in s)))
                next_meter = now + 0.5
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
        p.terminate()
    return b"".join(blocks) if blocks else None


def peak_of(raw):
    s = struct.unpack(f"{len(raw) // 2}h", raw)
    return max(abs(x) for x in s)


def main():
    devices = input_devices()
    print("=" * 66)
    print("  MERLIN MICROPHONE CHECK")
    print("=" * 66)
    print(f"{len(devices)} candidate microphone device(s) found.\n")

    if not devices:
        print("No microphone found at all.")
        print("Check: Settings -> System -> Sound -> Input")
        return 1

    print("SPEAK LOUDLY NOW -- say:  'merlin what is two plus two'\n")

    results = []
    dead = []
    for n, (index, name) in enumerate(devices, 1):
        print(f"[{n}/{len(devices)}] device {index} @ {device_rate(index)} "
              f"Hz: {name[:48]}")
        raw = record_device(index, SECONDS_PER_DEVICE)
        if raw is None:
            print("      could not open this device\n")
            continue
        live, detail = is_live(raw)
        if not live:
            dead.append((index, name, detail))
            print(f"      DEAD -- {detail}.")
            print("      This endpoint carries no microphone signal, so its\n"
                  "      level meter means nothing. Skipping it.\n")
            continue
        peak = peak_of(raw)
        print("      " + bar(peak) + "\n")
        results.append((peak, index, name, raw))

    if not results:
        print("No device produced live microphone audio.")
        if dead:
            print("\nThese endpoints did not carry live microphone audio "
                  "and were skipped:")
            for index, name, detail in dead:
                print(f"  device {index} ({name[:44]}): {detail}")
            print("\nA Bluetooth headset exposes its microphone only while")
            print("the Hands-Free profile is active. If its capture")
            print("endpoints fail with Errno -9999, the stereo (A2DP) link")
            print("is up instead and the headset mic is unreachable. Plug")
            print("in a USB microphone or fix the headset, then re-run.")
        return 1

    results.sort(key=lambda r: r[0], reverse=True)
    peak, index, name, raw = results[0]

    print("=" * 66)
    print(f"  BEST DEVICE: index {index}  ({name[:40]})")
    rms = math.sqrt(sum((x / 32768) ** 2 for x in
                        struct.unpack(f"{len(raw) // 2}h", raw))
                    / (len(raw) // 2))
    print(f"  peak amplitude : {peak}")
    print(f"  rms            : {rms * 32768:.1f}  "
          f"({20 * math.log10(rms) if rms else -99:.1f} dBFS)")
    print("=" * 66)

    with wave.open("mic_check.wav", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(raw)
    print("\nSaved mic_check.wav -- play it to confirm it contains your "
          "voice.")

    if peak >= SPEECH_LEVEL:
        print(f"\nThe microphone WORKS. Start MERLIN with:")
        print(f"    $env:MIC_DEVICE_INDEX={index}")
        print(f"    myprojectenv\\Scripts\\python.exe main.py")
        return 0

    print(f"""
The microphone is effectively SILENT (peak {peak}, need {SPEECH_LEVEL}).

MERLIN's code is working -- it opened the device and read samples from it.
The problem is the input level. Fix it in Windows:

  1. Win + R -> mmsys.cpl -> Enter
  2. Go to the "Recording" tab
  3. Select your microphone, click "Properties"
  4. "Levels" tab: drag Microphone Volume to 100, UNCHECK "Mute"
  5. "Advanced" tab: uncheck "Allow applications to take exclusive control"
  6. Back on Recording tab: tick "Allow applications to take control"
  7. Re-run:  myprojectenv\\Scripts\\python.exe mic_check.py

Also check, with the microphone selected as the Windows default:
  Settings -> System -> Sound -> Input -> choose your mic -> volume 100

If your headset only appears as "Hands-Free", that profile has no usable
mic at all -- connect it in high-quality/stereo mode, or use another mic.
""")
    return 2


if __name__ == "__main__":
    sys.exit(main())