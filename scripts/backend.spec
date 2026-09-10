# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Super Station Studio FastAPI backend.

Important: PyInstaller resolves relative paths from the .spec file's
location, not necessarily from the shell's current working directory.
Use absolute paths derived from this file so the spec works when invoked
from the repository root or from scripts/.
"""
from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_submodules

# PyInstaller executes .spec files with exec(), and in some versions
# __file__ is intentionally not defined. The build wrapper therefore
# supplies PROJECT_ROOT; fall back to the current working directory so the
# spec also works when launched manually from the repository root.
ROOT = Path(os.environ.get("SSS_PROJECT_ROOT", Path.cwd())).resolve()
BACKEND = ROOT / "backend"

hiddenimports = []
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("src")

# PyAV and sounddevice contain runtime-loaded extension components. Their
# normal package hooks handle the platform-specific binaries, while the
# explicit hidden imports above cover the application's package tree.
a = Analysis(
    [str(BACKEND / "run_backend.py")],
    pathex=[str(ROOT), str(BACKEND)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SuperStationBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
