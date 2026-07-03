"""Offline smoke test for the conversion pipeline (no LG hardware needed).

Run from the project root:

    python tests/smoke_test.py

Steps:
  1. locate ffmpeg + check the v360 filter,
  2. generate a tiny synthetic clip,
  3. run metadata-only injection and assert spherical metadata is present,
  4. if v360 is available, run a short dual-fisheye -> equirectangular
     reprojection and assert the output is a valid MP4 that carries 360 metadata.

Exits non-zero on the first failed check.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import converter, ffmpeg_runner, metadata  # noqa: E402


def _make_clip(ffmpeg, path, size="1280x640", seconds=1):
    cmd = [
        ffmpeg, "-y", "-hide_banner",
        "-f", "lavfi",
        "-i", "testsrc=size=%s:rate=15:duration=%d" % (size, seconds),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ffmpeg = ffmpeg_runner.find_ffmpeg()
    print("ffmpeg:", ffmpeg or "NOT FOUND")
    if not ffmpeg:
        print("FAIL: ffmpeg is required for the smoke test.")
        return 1

    v360 = ffmpeg_runner.has_v360(ffmpeg)
    print("v360 filter:", "available" if v360 else "unavailable")

    workdir = tempfile.mkdtemp(prefix="lg360_smoke_")
    src = os.path.join(workdir, "src.mp4")
    _make_clip(ffmpeg, src)
    print("generated test clip:", src)

    # 1) metadata-only injection
    meta_out = os.path.join(workdir, "meta_360.mp4")
    converter.convert(
        src,
        converter.ConversionOptions(mode=converter.MODE_METADATA, output_path=meta_out),
        progress_cb=lambda f, m: None,
        log=lambda m: None,
    )
    assert os.path.exists(meta_out), "metadata-only output was not created"
    assert metadata.has_spherical_metadata(meta_out), "no spherical metadata detected after inject"
    print("PASS: metadata-only injection ->", meta_out)

    # 2) reprojection (only if the v360 filter is present)
    if v360:
        rep_out = os.path.join(workdir, "reproj_360.mp4")
        converter.convert(
            src,
            converter.ConversionOptions(
                mode=converter.MODE_REPROJECT, crf=28, preset="ultrafast",
                output_path=rep_out,
            ),
            progress_cb=lambda f, m: None,
            log=lambda m: None,
        )
        assert os.path.exists(rep_out), "reprojected output was not created"
        info = ffmpeg_runner.probe(rep_out, ffmpeg)
        assert info["duration"], "reprojected output has no readable duration"
        assert metadata.has_spherical_metadata(rep_out), "reprojected output missing 360 metadata"
        print("PASS: reprojection -> %s (%sx%s)" % (rep_out, info["width"], info["height"]))
    else:
        print("SKIP: reprojection test (v360 unavailable in this ffmpeg build)")

    print("\nALL CHECKS PASSED")
    print("Artifacts left in:", workdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
