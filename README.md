# LG 360 CAM → Spherical 360 Video Converter

A small Windows desktop app (drag-and-drop) that turns footage from an
**LG 360 CAM** into a spherical **360 video** that VLC, YouTube, Facebook and VR
headsets recognize and let you look around in.

## Why this is needed

Raw MP4s copied off the LG 360 CAM's SD card are usually **dual-fisheye** (two
circular images side by side). Players only render **equirectangular** video as
360, and even an equirectangular file plays as a flat 2:1 video unless it
contains **Google Spatial Media** metadata that switches the player into 360
mode. So conversion is up to two steps:

1. **Reproject** dual-fisheye → equirectangular (via ffmpeg's `v360` filter).
2. **Inject** spherical metadata (the `uuid` / `sv3d` boxes).

This app does both, and lets you pick per video.

## Requirements

These apply only when **running from source** or rebuilding — the packaged app
in `dist/LG360Spherical/` bundles everything and needs nothing installed.

- **Python 3.9+** (developed/tested on 3.14) with Tkinter (included in the
  official python.org Windows installer).
- **ffmpeg** — installed automatically via the `imageio-ffmpeg` pip package, so
  you don't have to set anything up. If you already have a full ffmpeg on your
  `PATH`, that's used as a fallback.

## Get the app

There are two ways to run it.

### Option A — Packaged Windows app (no Python needed)

A self-contained build is placed in `dist/LG360Spherical/` (if that folder isn't
there, build it with the steps in **Build the standalone .exe** below).
Double-click:

```
dist\LG360Spherical\LG360Spherical.exe
```

Keep the `_internal/` folder beside the exe (it holds the bundled ffmpeg and
Python runtime). To move or share the app, copy or zip the **entire**
`dist/LG360Spherical/` folder — the exe will not run on its own.

### Option B — From source (Python 3.9+)

```powershell
cd lg360-to-spherical
python -m pip install -r requirements.txt   # first time only
python -m app
```

`python run_app.py` works too.

## Usage

1. **Drag** an LG 360 CAM `.mp4` onto the drop zone (or click it / use
   **Browse…**).
2. **Choose a mode:**
   - **Reproject dual-fisheye → equirectangular, then add 360 metadata** — for
     raw SD-card footage (two side-by-side fisheye circles). *This is the usual
     choice.*
   - **Add 360 metadata only** — if your file is *already* stitched to
     equirectangular (e.g. exported by LG's app) and just isn't recognized as
     360.
3. *(optional)* Open **Advanced options** to change:
   - **Input FOV** (default `189°` — matches the usable LG lens coverage and
     reduces the seam; try `180`–`200` if the horizon looks stretched or
     doubled),
   - **Video codec** (H.264 or HEVC),
   - **Quality (CRF)** — lower is better quality/larger file (default `18`),
   - **Output folder**.
4. Click **Convert**. Progress and a log show status. The result is written next
   to the input (or your chosen folder) as `NAME_360.mp4` with audio preserved;
   use **Open output folder** to jump to it.

### Verifying the result

Open `NAME_360.mp4` in **VLC 3+** — you should be able to click-and-drag to look
around. Uploading to YouTube will also show the 360 navigation controls after
processing.

## How it works

```
app/
  gui.py            drag-and-drop UI, background worker, progress
  converter.py      pipeline: (reproject) -> inject metadata
  ffmpeg_runner.py  locate/verify ffmpeg, probe, run v360 reprojection
  metadata.py       wraps the vendored spatialmedia injector/parser
  selftest.py       headless end-to-end self-test (used to verify builds)
run_app.py          launcher (also the PyInstaller entry point)
vendor/
  spatialmedia/     Google's Apache-2.0 spherical-metadata tool (see NOTICE)
tests/
  smoke_test.py     offline pipeline test
build/
  app.spec          PyInstaller build recipe
```

The reprojection command is roughly:

```
ffmpeg -i IN.mp4 -vf "v360=input=dfisheye:output=equirect:ih_fov=189:iv_fov=189" \
       -c:v libx264 -crf 18 -preset medium -c:a copy -movflags +faststart TMP.mp4
```

followed by injecting equirectangular spherical metadata (V1 `uuid` box for
broad compatibility, plus the V2 `sv3d` box for modern/headset players).

## Command-line options

Both the packaged exe and `run_app.py` accept:

- `--selftest` — run a headless end-to-end check (no GUI) and exit `0` on
  success or non-zero on failure. Set `LG360_SELFTEST_REPORT` to a file path to
  capture the report (useful for the windowed exe, which has no console):

  ```powershell
  $env:LG360_SELFTEST_REPORT = "$PWD\selftest.txt"
  .\dist\LG360Spherical\LG360Spherical.exe --selftest
  Get-Content $env:LG360_SELFTEST_REPORT
  ```
- `--version` — print the app version and exit.

## Test from source (no camera needed)

```powershell
python tests/smoke_test.py
```

This generates a tiny synthetic clip, runs metadata-only injection (asserting
the metadata is detected afterward), and — if the `v360` filter is available —
runs a short dual-fisheye → equirectangular reprojection.

## Build the standalone .exe

To produce (or rebuild) the self-contained app:

```powershell
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm --workpath .pyi-build --distpath dist build/app.spec
```

The result (with ffmpeg bundled) is written to `dist/LG360Spherical/`, with
support files in its `_internal/` subfolder. `dist/` is git-ignored, so the
build itself is not committed.

## Notes & limitations

- Dual-fisheye vs. equirectangular **cannot be reliably auto-detected** (both
  are ~2:1), which is why you pick the mode.
- `189°` FOV is approximate for the LG hardware; adjust it if the stitch seam is
  visible.
- Reprojection re-encodes the video (quality/size depend on CRF); metadata-only
  mode is near-instant and lossless.

## License / attribution

This project bundles Google's `spatialmedia` package (Apache License 2.0) under
`vendor/spatialmedia/` — see `vendor/NOTICE` and
`vendor/spatialmedia/LICENSE`.
