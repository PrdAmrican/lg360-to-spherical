"""High-level conversion pipeline used by the GUI (and by tests / CLI).

Two modes:
* ``reproject`` - dual-fisheye MP4 -> equirectangular (ffmpeg) -> inject metadata
* ``metadata``  - inject spherical metadata into an already-equirectangular file

``progress_cb(fraction, message)`` is called with ``fraction`` in ``[0, 1]`` or
``None`` (indeterminate). ``log(message)`` receives human-readable log lines.
"""

import os
import tempfile

from app import ffmpeg_runner, metadata

VIDEO_EXTS = {".mp4", ".mov"}

MODE_REPROJECT = "reproject"
MODE_METADATA = "metadata"

# The reprojection encode dominates wall-clock time, so it gets most of the bar.
_REPROJECT_SHARE = 0.92


class ConversionOptions:
    """User-selectable options for a single conversion."""

    def __init__(
        self,
        mode=MODE_REPROJECT,
        fov=189.0,
        vcodec="libx264",
        crf=18,
        preset="medium",
        output_dir=None,
        output_path=None,
        inject_v2=True,
    ):
        self.mode = mode
        self.fov = fov
        self.vcodec = vcodec
        self.crf = crf
        self.preset = preset
        self.output_dir = output_dir
        self.output_path = output_path
        self.inject_v2 = inject_v2


def default_output_path(input_path, output_dir=None):
    """``<dir>/<name>_360.mp4`` next to the input (or in ``output_dir``)."""
    input_path = os.path.abspath(input_path)
    directory = output_dir or os.path.dirname(input_path)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(directory, stem + "_360.mp4")


def convert(input_path, options, progress_cb=None, log=None):
    """Run the conversion described by ``options`` and return the output path."""
    input_path = os.path.abspath(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError("Input file does not exist: %s" % input_path)
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in VIDEO_EXTS:
        raise ValueError("Unsupported input type '%s' (expected .mp4 or .mov)." % ext)

    output_path = options.output_path or default_output_path(input_path, options.output_dir)
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if output_path == input_path:
        raise ValueError("Output path must differ from the input path.")

    def report(fraction, message):
        if progress_cb:
            progress_cb(fraction, message)

    def _log(message):
        if log:
            log(message)

    if options.mode == MODE_METADATA:
        report(None, "Injecting 360 metadata...")
        metadata.inject_spherical(input_path, output_path, log=_log, inject_v2=options.inject_v2)
        report(1.0, "Done")
        return output_path

    if options.mode != MODE_REPROJECT:
        raise ValueError("Unknown conversion mode: %r" % options.mode)

    ffmpeg = ffmpeg_runner.find_ffmpeg()
    if not ffmpeg:
        raise ffmpeg_runner.FfmpegError(
            "ffmpeg is required for reprojection but was not found. Install the "
            "imageio-ffmpeg package or add ffmpeg to your PATH."
        )
    info = ffmpeg_runner.probe(input_path, ffmpeg)

    # Reproject into a temp file alongside the output, then inject metadata into
    # the final file (the injector requires distinct input/output paths).
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix="lg360_equirect_", suffix=".mp4", dir=os.path.dirname(output_path)
    )
    os.close(tmp_fd)
    try:
        def reproject_progress(fraction, message):
            if fraction is None:
                report(None, message)
            else:
                report(fraction * _REPROJECT_SHARE, "Reprojecting to equirectangular...")

        ffmpeg_runner.reproject(
            input_path,
            tmp_path,
            fov=options.fov,
            vcodec=options.vcodec,
            crf=options.crf,
            preset=options.preset,
            progress_cb=reproject_progress,
            log=_log,
            info=info,
            ffmpeg=ffmpeg,
        )

        report(_REPROJECT_SHARE, "Injecting 360 metadata...")
        metadata.inject_spherical(tmp_path, output_path, log=_log, inject_v2=options.inject_v2)
        report(1.0, "Done")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

    return output_path
