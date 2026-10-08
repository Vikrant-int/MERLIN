# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the MERLIN desktop app.

Build (from the project root, inside the virtual environment):

    myprojectenv\\Scripts\\pyinstaller.exe --noconfirm MERLIN.spec

Produces ``dist\\MERLIN.exe`` -- a single windowed executable. ``build/`` and
``dist/`` are git-ignored; the spec file itself is tracked.

Deliberate choices
------------------
* ``console=False`` -- this is a desktop application, not a terminal one. Every
  failure path in the UI already degrades to a friendly message, so a hidden
  console loses nothing.
* ``datas=[]`` -- there are no bundled assets to speak of: every icon, the
  assistant orb and the title-bar glyphs are drawn with QPainter at runtime,
  and the stylesheet lives in ``ui/theme.py``.
* ``main`` and friends are listed as hidden imports. They are only reached by
  ``import`` statements buried inside functions (``services.core.get_main()``,
  ``_list_devices_blocking()``), so an explicit list keeps the bundle honest
  instead of depending on what the bytecode scanner happens to see.
* No key is baked in. ``GEMINI_API_KEY`` / ``NEWS_API_KEY`` are read from the
  Windows environment at run time; without them the app starts and says so.
"""

from PyInstaller.utils.hooks import collect_submodules

# Third-party packages that import lazily or through dynamic drivers.
hiddenimports = [
    # The backend and its data file.
    "main",
    "musicLibrary",
    "mic_check",
    # Speech stack.
    "speech_recognition",
    "pyttsx3",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    # AI provider abstraction (imported by services.assistant_service).
    "services",
    "services.ai_provider",
    # Gemini.
    "google.genai",
    "requests",
    # Real endpoint volume for the Music page.
    "pycaw",
    "pycaw.pycaw",
    "comtypes",
]
hiddenimports += collect_submodules("pyttsx3")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Never reached on Windows, and each one drags in a large chunk of
        # the standard library.
        "tkinter",
        "unittest",
        "pydoc",
        "doctest",
        "test",
        "tests",
        # Not installed, and only referenced by a legacy fallback in main.py.
        "google.generativeai",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MERLIN",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
