"""One lock around PortAudio access.

``sr.Microphone.get_pyaudio().PyAudio()`` runs PortAudio's global
initialiser, and PortAudio is **not** safe to initialise concurrently: two
threads constructing ``PyAudio`` at the same time take the process down with
an access violation inside ``PyAudio.__init__``. This is not theoretical --
it was observed while starting the desktop app, because several pages each
ask for the device list as soon as the backend reports ready.

``main.py`` is deliberately untouched. The UI serialises its calls into the
existing backend instead, so enumeration, probing and capture never overlap.

Use an ``RLock``: a capture routine may re-enter device helpers while it
already holds the lock, and a normal lock would deadlock on that.
"""
from __future__ import annotations

import threading

DEVICE_LOCK = threading.RLock()
