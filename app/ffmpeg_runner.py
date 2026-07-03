"""Locate, verify and drive ffmpeg for the reprojection stage.

Design notes:
* ffmpeg is resolved from the bundled ``imageio-ffmpeg`` package first, then
  from ``PATH``. This means the user does not need to install ffmpeg manually.
* Progress is read from ``-progress pipe:1`` (machine-readable, newline
  terminated) rather than scraping the ``\\r``-updated stats line, which is
  awkward to parse reliably.
* On Windows we pass ``CREATE_NO_WINDOW`` so no console flashes when the app is
  run via ``pythonw`` / a packaged ``.exe``.
"""

import os
import re
import shutil
import subprocess
import sys
import threading

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_OUT_TIME_RE = re.compile(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_STREAM_RE = re.compile(r"Stream #[^\n]*Video:[^\n]*")
_AUDIO_STREAM_RE = re.compile(r"Stream #[^\n]*Audio:\s*([A-Za-z0-9_]+)")
_DIM_RE = re.compile(r"(\d{2,5})x(\d{2,5})")


class FfmpegError(RuntimeError):
    """Raised when ffmpeg is missing or a run fails."""


def _bundled_ffmpeg():
    """Return an ffmpeg bundled inside a frozen (PyInstaller) build, if any."""
    if not (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")):
        return None
    bundled_dir = os.path.join(sys._MEIPASS, "imageio_ffmpeg", "binaries")
    if not os.path.isdir(bundled_dir):
        return None
    for name in sorted(os.listdir(bundled_dir)):
        if name.lower().startswith("ffmpeg"):
            candidate = os.path.join(bundled_dir, name)
            if os.path.isfile(candidate):
                return candidate
    return None


def find_ffmpeg():
    """Return the path to an ffmpeg executable, or ``None`` if unavailable."""
    bundled = _bundled_ffmpeg()
    if bundled:
        return bundled
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:  # noqa: BLE001 - fall back to PATH
        pass
    return shutil.which("ffmpeg")


def has_v360(ffmpeg=None):
    """Return ``True`` if the resolved ffmpeg exposes the ``v360`` filter."""
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        return False
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW,
            universal_newlines=True,
            errors="replace",
        )
    except Exception:  # noqa: BLE001
        return False
    return bool(re.search(r"\bv360\b", result.stdout or ""))


def _parse_duration(text):
    match = _DURATION_RE.search(text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def probe(input_path, ffmpeg=None):
    """Return basic stream info parsed from ffmpeg's stderr.

    Keys: ``duration`` (seconds or None), ``width``, ``height``,
    ``has_audio`` (bool), ``audio_codec`` (lowercase str or None).
    """
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise FfmpegError("ffmpeg was not found.")

    # ``-i`` with no output exits non-zero but prints stream info to stderr.
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", input_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=_CREATE_NO_WINDOW,
        universal_newlines=True,
        errors="replace",
    )
    text = result.stderr or ""

    info = {
        "duration": _parse_duration(text),
        "width": None,
        "height": None,
        "has_audio": False,
        "audio_codec": None,
    }

    video_match = _VIDEO_STREAM_RE.search(text)
    if video_match:
        dim = _DIM_RE.search(video_match.group(0))
        if dim:
            info["width"] = int(dim.group(1))
            info["height"] = int(dim.group(2))

    audio_match = _AUDIO_STREAM_RE.search(text)
    if audio_match:
        info["has_audio"] = True
        info["audio_codec"] = audio_match.group(1).lower()

    return info


def build_video_filter(fov):
    """ffmpeg ``-vf`` string that maps side-by-side dual-fisheye to equirect."""
    return "v360=input=dfisheye:output=equirect:ih_fov=%s:iv_fov=%s" % (fov, fov)


def _audio_args(info):
    if not info.get("has_audio"):
        return ["-an"]
    # LG 360 CAM records AAC, which we can stream-copy losslessly.
    if info.get("audio_codec") == "aac":
        return ["-c:a", "copy"]
    return ["-c:a", "aac", "-b:a", "192k"]


def _run_with_progress(cmd, duration, progress_cb, log):
    """Run ffmpeg, streaming progress from stdout and logging stderr."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_CREATE_NO_WINDOW,
        universal_newlines=True,
        errors="replace",
        bufsize=1,
    )

    stderr_lines = []

    def _drain_stderr():
        for line in proc.stderr:
            line = line.rstrip("\n")
            if line:
                stderr_lines.append(line)
                if log:
                    log(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        for raw in proc.stdout:
            line = raw.strip()
            match = _OUT_TIME_RE.search(line)
            if match and duration and progress_cb:
                hours, minutes, seconds = match.groups()
                elapsed = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                fraction = max(0.0, min(elapsed / duration, 0.999))
                progress_cb(fraction, "Reprojecting to equirectangular...")
            elif line.startswith("progress=") and progress_cb and not duration:
                progress_cb(None, "Reprojecting to equirectangular...")
    finally:
        proc.wait()
        stderr_thread.join(timeout=1.0)

    return proc.returncode, "\n".join(stderr_lines[-15:])


def reproject(
    input_path,
    output_path,
    fov=189.0,
    vcodec="libx264",
    crf=18,
    preset="medium",
    progress_cb=None,
    log=None,
    info=None,
    ffmpeg=None,
):
    """Reproject side-by-side dual-fisheye video to equirectangular.

    Returns ``output_path`` on success; raises :class:`FfmpegError` otherwise.
    """
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise FfmpegError(
            "ffmpeg is required for reprojection but was not found. Install the "
            "imageio-ffmpeg package or add ffmpeg to your PATH."
        )
    if info is None:
        info = probe(input_path, ffmpeg)
    duration = info.get("duration")

    def run(audio_args):
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-i",
            input_path,
            "-vf",
            build_video_filter(fov),
            "-c:v",
            vcodec,
            "-crf",
            str(crf),
            "-preset",
            preset,
            *audio_args,
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            output_path,
        ]
        if log:
            log("Running: " + " ".join(cmd))
        return _run_with_progress(cmd, duration, progress_cb, log)

    audio_args = _audio_args(info)
    return_code, stderr_tail = run(audio_args)

    # If stream-copying the audio failed, fall back to a safe AAC re-encode.
    if return_code != 0 and audio_args[:2] == ["-c:a", "copy"]:
        if log:
            log("Audio stream-copy failed; retrying with AAC re-encode...")
        return_code, stderr_tail = run(["-c:a", "aac", "-b:a", "192k"])

    if return_code != 0:
        raise FfmpegError(
            "ffmpeg reprojection failed (exit code %d):\n%s" % (return_code, stderr_tail)
        )

    if progress_cb:
        progress_cb(1.0, "Reprojection complete")
    return output_path
