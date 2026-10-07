"""Windows system volume, with every call guarded.

Real Core Audio endpoints via pycaw -- no simulated or faked levels. If the
package is missing or the machine has no render device, every function
returns ``None``/``False`` and the caller hides the control instead of
pretending it works.

The endpoint object is created on, and only ever used from, the GUI thread,
which is where Qt slider signals arrive.
"""
from __future__ import annotations

_endpoint = None
_unavailable_reason = ""


def _resolve():
    global _endpoint, _unavailable_reason
    if _endpoint is not None:
        return _endpoint
    if _unavailable_reason:
        return None
    try:
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        device = AudioUtilities.GetSpeakers()
        _endpoint = device.EndpointVolume
    except Exception as exc:
        _unavailable_reason = f"{type(exc).__name__}: {exc}"
        _endpoint = None
    return _endpoint


def available() -> bool:
    return _resolve() is not None


def reason() -> str:
    """Short, non-technical explanation when volume control is missing."""
    if available():
        return ""
    return "System volume isn't available on this device."


def get_volume() -> float | None:
    endpoint = _resolve()
    if endpoint is None:
        return None
    try:
        return float(endpoint.GetMasterVolumeLevelScalar())
    except Exception:
        _invalidate()
        return None


def set_volume(value: float) -> bool:
    endpoint = _resolve()
    if endpoint is None:
        return False
    try:
        endpoint.SetMasterVolumeLevelScalar(max(0.0, min(1.0, float(value))),
                                            None)
        return True
    except TypeError:
        try:
            endpoint.SetMasterVolumeLevelScalar(max(0.0, min(1.0, float(value))))
            return True
        except Exception:
            _invalidate()
            return False
    except Exception:
        _invalidate()
        return False


def get_mute() -> bool | None:
    endpoint = _resolve()
    if endpoint is None:
        return None
    try:
        return bool(endpoint.GetMute())
    except Exception:
        _invalidate()
        return None


def set_mute(value: bool) -> bool:
    endpoint = _resolve()
    if endpoint is None:
        return False
    try:
        try:
            endpoint.SetMute(1 if value else 0, None)
        except TypeError:
            endpoint.SetMute(1 if value else 0)
        return True
    except Exception:
        _invalidate()
        return False


def _invalidate() -> None:
    global _endpoint, _unavailable_reason
    _endpoint = None
    _unavailable_reason = "The audio endpoint went away."


def toggle_playback() -> bool:
    """Send the Windows "media play/pause" key.

    MERLIN opens tracks in the browser and has no visibility into that
    player's state, so rather than faking a pause indicator this hands the
    toggle to the OS, which routes it to whatever is actually playing.
    """
    try:
        import ctypes  # noqa: PLC0415

        VK_MEDIA_PLAY_PAUSE = 0xB3
        KEYEVENTF_KEYUP = 0x0002
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False
