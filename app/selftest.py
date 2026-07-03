"""Headless self-test for verifying the app (from source or a frozen build).

Runs the real pipeline with whatever ffmpeg the app resolves, so it also
validates a packaged executable. Returns 0 on success, non-zero on failure.

The result is written to a text file (``LG360_SELFTEST_REPORT`` env var or the
``report_path`` argument) because a windowed/frozen build has no attached
stdout to read.
"""

import os
import subprocess
import sys
import tempfile

from app import converter, ffmpeg_runner, metadata


def _make_clip(ffmpeg, path, size="1280x640", seconds=1):
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-f", "lavfi",
        "-i", "testsrc=size=%s:rate=15:duration=%d" % (size, seconds),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run(report_path=None):
    """Exercise the pipeline end-to-end. Returns 0 on success, 1 on failure."""
    lines = []

    def emit(msg):
        lines.append(str(msg))

    ok = True
    emit("frozen build: %s" % bool(getattr(sys, "frozen", False)))
    ffmpeg = ffmpeg_runner.find_ffmpeg()
    emit("ffmpeg: %s" % (ffmpeg or "NOT FOUND"))

    try:
        if not ffmpeg:
            raise RuntimeError("ffmpeg was not found in this build")
        v360 = ffmpeg_runner.has_v360(ffmpeg)
        emit("v360 filter: %s" % ("available" if v360 else "unavailable"))

        workdir = tempfile.mkdtemp(prefix="lg360_selftest_")
        src = os.path.join(workdir, "src.mp4")
        _make_clip(ffmpeg, src)
        emit("generated synthetic test clip")

        # 1) metadata-only injection
        meta_out = os.path.join(workdir, "meta_360.mp4")
        converter.convert(
            src,
            converter.ConversionOptions(mode=converter.MODE_METADATA, output_path=meta_out),
            progress_cb=lambda f, m: None, log=lambda m: None,
        )
        if os.path.exists(meta_out) and metadata.has_spherical_metadata(meta_out):
            emit("PASS: metadata-only injection")
        else:
            ok = False
            emit("FAIL: metadata-only injection")

        # 2) reprojection (only when v360 is available)
        if v360:
            rep_out = os.path.join(workdir, "reproj_360.mp4")
            converter.convert(
                src,
                converter.ConversionOptions(
                    mode=converter.MODE_REPROJECT, crf=28, preset="ultrafast",
                    output_path=rep_out,
                ),
                progress_cb=lambda f, m: None, log=lambda m: None,
            )
            info = ffmpeg_runner.probe(rep_out, ffmpeg)
            if (
                os.path.exists(rep_out)
                and info.get("duration")
                and metadata.has_spherical_metadata(rep_out)
            ):
                emit("PASS: reprojection (%sx%s)" % (info["width"], info["height"]))
            else:
                ok = False
                emit("FAIL: reprojection")
        else:
            emit("SKIP: reprojection (v360 unavailable)")
    except Exception as exc:  # noqa: BLE001 - report any failure
        ok = False
        emit("ERROR: %s" % exc)

    emit("RESULT: %s" % ("OK" if ok else "FAIL"))
    report = "\n".join(lines)

    report_path = report_path or os.environ.get("LG360_SELFTEST_REPORT")
    if report_path:
        try:
            with open(report_path, "w", encoding="utf-8") as handle:
                handle.write(report + "\n")
        except OSError:
            pass

    try:
        if sys.stdout is not None:
            print(report)
    except Exception:  # noqa: BLE001
        pass

    return 0 if ok else 1
