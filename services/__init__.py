"""Adapter layer between MERLIN's existing backend and the desktop UI.

`main.py` is the source of truth and is never modified here. Everything in
this package only *calls* the backend and translates the result into
Qt-friendly signals, so the console assistant keeps working untouched.
"""
