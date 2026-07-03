# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: build a self-contained Windows app.

Build from the project root:

    python -m pip install pyinstaller
    pyinstaller --clean --workpath .pyi-build --distpath dist build/app.spec

Result: dist/LG360Spherical/LG360Spherical.exe
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Resolve the project root from the spec's own location, so the build works
# regardless of the current working directory (PyInstaller resolves relative
# script paths against the spec directory, not the cwd).
try:
    project_root = os.path.dirname(os.path.abspath(SPECPATH))
except NameError:
    project_root = os.path.abspath(os.getcwd())

# Bundle the ffmpeg binary from imageio-ffmpeg so the app is self-contained.
binaries = []
try:
    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if ffmpeg_exe and os.path.exists(ffmpeg_exe):
        binaries.append((ffmpeg_exe, os.path.join("imageio_ffmpeg", "binaries")))
except Exception:
    pass

# Ship the vendored spatialmedia package as data (imported via sys.path tweak).
datas = [
    (
        os.path.join(project_root, "vendor", "spatialmedia"),
        os.path.join("vendor", "spatialmedia"),
    ),
]

# tkinterdnd2 ships the platform tkdnd shared libraries as package data.
hiddenimports = [
    "app",
    "app.gui",
    "app.converter",
    "app.ffmpeg_runner",
    "app.metadata",
    "app.selftest",
]
try:
    datas += collect_data_files("tkinterdnd2")
    hiddenimports += collect_submodules("tkinterdnd2")
except Exception:
    pass

# The vendored spatialmedia package is shipped as *data*, so PyInstaller does
# not scan it for imports. Explicitly bundle the stdlib modules it needs
# (xml.etree in particular is not pulled in otherwise).
hiddenimports += [
    "xml",
    "xml.etree",
    "xml.etree.ElementTree",
    "struct",
    "io",
    "traceback",
    "collections",
]

block_cipher = None

a = Analysis(
    [os.path.join(project_root, "run_app.py")],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LG360Spherical",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed GUI app (no console window)
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="LG360Spherical",
)
