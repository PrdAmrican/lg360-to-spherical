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

These apply only when **running from source** or rebuilding — the packaged
release download bundles everything and needs nothing installed.

- **Python 3.9+** (developed/tested on 3.14) with Tkinter (included in the
  official python.org Windows installer).
- **ffmpeg** — installed automatically via the `imageio-ffmpeg` pip package, so
  you don't have to set anything up. If you already have a full ffmpeg on your
  `PATH`, that's used as a fallback.

## Get the app

There are two ways to run it.

### Option A — Download the release (no Python needed)

1. Open the [**Releases**](https://github.com/PrdAmrican/lg360-to-spherical/releases/latest)
   page and download `LG360Spherical-vX.Y.Z-win64.zip` (v1.0.0 or later).
2. Extract the zip anywhere.
3. Run `LG360Spherical\LG360Spherical.exe`.

Keep the `_internal/` folder next to the exe (it holds the bundled ffmpeg and
Python runtime) — don't move the exe out on its own. Everything is bundled, so
no Python or ffmpeg install is required.

> **Windows SmartScreen** may warn about an unrecognized app (the exe is
> unsigned). Click **More info → Run anyway**, or right-click the zip →
> **Properties → Unblock** before extracting.

If you build the app yourself instead (see **Build the standalone .exe**), the
same folder is produced in `dist/LG360Spherical/`.

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

## Examples

**Example 1 — Raw SD-card clip (dual-fisheye → 360).** You copied `LGE_0007.mp4`
off the camera and it shows two side-by-side circles in VLC.
1. Drag `LGE_0007.mp4` onto the app.
2. Leave the mode on **Reproject dual-fisheye → equirectangular…**.
3. Click **Convert** → you get `LGE_0007_360.mp4`, which pans around in VLC and
   plays as 360 on YouTube.

**Example 2 — Already-stitched clip that won't play as 360.** Your file is
already a 2:1 equirectangular video but players treat it as flat.
1. Drag the file in and choose **Add 360 metadata only**.
2. Click **Convert** → the `_360.mp4` copy is created almost instantly (no
   re-encode, no quality loss) with the spherical metadata added.

**Example 3 — Smaller output / faster encode.** Open **Advanced options**, raise
**CRF** to `23`–`28` (smaller file) and/or pick **HEVC (libx265)**, then Convert
as usual.

**Example 4 — Verify without the GUI (command line):**

```powershell
# packaged release (run from the extracted folder)
$env:LG360_SELFTEST_REPORT = "$PWD\selftest.txt"
.\LG360Spherical\LG360Spherical.exe --selftest ; Get-Content $env:LG360_SELFTEST_REPORT

# from source
python run_app.py --selftest
python run_app.py --version
```

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

## Troubleshooting

**The video still plays flat (not 360).** Make sure you're opening the converted
`_360.mp4`, not the original. Use **VLC 3.0+** (older versions have no 360
support); on YouTube, allow a few minutes after upload for 360 processing.

**The 360 view is warped, or two fisheye circles are wrapped onto the sphere.**
You used **Add 360 metadata only** on raw dual-fisheye footage. Re-run with
**Reproject dual-fisheye → equirectangular** instead.

**Visible seam, or the horizon looks doubled/stretched.** Adjust **Input FOV**
in Advanced options — try `180`–`200` (default `189`). Lower reduces overlap;
higher fills more of the sphere.

**The "Reproject…" mode is disabled / "v360 unavailable".** The detected ffmpeg
lacks the `v360` filter. Use the **release download** (ffmpeg bundled), or
install a full ffmpeg on your `PATH`. From source, `python -m pip install -r
requirements.txt` provides ffmpeg via `imageio-ffmpeg`.

**Windows SmartScreen / "Windows protected your PC".** The exe isn't
code-signed. Click **More info → Run anyway**, or **Unblock** the zip in its
file **Properties** before extracting.

**The app won't start / closes immediately.** Keep the exe and its `_internal/`
folder together — the exe copied out on its own will not run. Re-extract the
full zip if unsure.

**Audio is missing or not surround.** Audio is stream-copied when it's AAC (the
LG default) and otherwise re-encoded to AAC; a source with no audio produces no
audio.

**The output file is very large.** Reprojection re-encodes video — raise **CRF**
(e.g. `23`–`28`) and/or choose **HEVC** in Advanced options to shrink it.

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
