# receiver.spec — PyInstaller spec for Intrakom Receiver (headless daemon)
# Build: pyinstaller receiver.spec
# Produces a single self-contained binary (onefile on all platforms).

block_cipher = None

import os as _os
import subprocess as _subprocess
import sys as _sys


def _portaudio_dylib():
    """Find Homebrew's portaudio dylib on macOS (works on Intel and Apple Silicon)."""
    try:
        prefix = _subprocess.check_output(
            ["brew", "--prefix", "portaudio"], text=True, stderr=_subprocess.DEVNULL
        ).strip()
    except Exception:
        prefix = "/opt/homebrew"
    path = _os.path.join(prefix, "lib", "libportaudio.2.dylib")
    return path if _os.path.exists(path) else None


_binaries = []
if _sys.platform == "darwin":
    dylib = _portaudio_dylib()
    if dylib:
        _binaries = [(dylib, ".")]

a = Analysis(
    ["intrakom/receiver.py"],
    pathex=[],
    binaries=_binaries,
    datas=[],
    hiddenimports=["win32event", "win32api", "winerror"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PIL", "pystray", "numpy", "requests"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Single onefile binary on all platforms — headless daemon, no .app bundle needed
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="intrakom-receiver",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,   # headless daemon — no window, but stdout/stderr go to log
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
