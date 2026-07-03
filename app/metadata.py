"""Thin wrapper around the vendored Google ``spatialmedia`` package.

Exposes two helpers used by the rest of the app:

* :func:`inject_spherical` - write a new file that contains equirectangular
  spherical metadata (V1 ``uuid`` box, plus the V2 ``sv3d`` box by default) so
  players render the video as 360.
* :func:`has_spherical_metadata` - report whether a file already carries
  recognizable spherical metadata (used by tests / post-run validation).
"""

import os
import sys

# Make the vendored ``spatialmedia`` package importable. It uses absolute
# imports (``from spatialmedia import mpeg``), so the *parent* of the package
# directory (``vendor/``) must be on sys.path. When frozen by PyInstaller the
# data lives under sys._MEIPASS instead of next to this source file.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENDOR_DIR = os.path.join(_BASE_DIR, "vendor")
if _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

from spatialmedia import metadata_utils  # noqa: E402  (import after sys.path tweak)


def _collect_console(log=None):
    """Build a console callback compatible with the vendored code.

    The vendored parser sometimes calls the console with more than one
    positional argument, so this accepts ``*args``. Everything is also
    captured into a list so we can surface the tail on failure.
    """
    messages = []

    def console(*args):
        msg = " ".join(str(a) for a in args)
        messages.append(msg)
        if log:
            log(msg)

    return console, messages


def inject_spherical(input_path, output_path, log=None, inject_v2=True):
    """Inject equirectangular spherical metadata into ``input_path``.

    Writes a brand new file at ``output_path`` (the two paths must differ).
    Returns ``output_path`` on success and raises ``RuntimeError`` on failure.
    """
    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)
    if input_path == output_path:
        raise ValueError("Input and output paths must differ for metadata injection.")

    console, messages = _collect_console(log)

    metadata = metadata_utils.Metadata()
    # V1: the widely-recognized uuid/XML box (YouTube, Facebook, VLC).
    metadata.video = metadata_utils.generate_spherical_xml(projection="equirectangular")
    # V2: the sv3d box preferred by many modern / headset players.
    if inject_v2:
        metadata.projection = "equirectangular"

    try:
        metadata_utils.inject_metadata(input_path, output_path, metadata, console)
    except Exception as exc:  # noqa: BLE001 - convert to a friendly error
        tail = "\n".join(messages[-5:])
        raise RuntimeError(
            "Spherical metadata injection failed: %s\n%s" % (exc, tail)
        ) from exc

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        tail = "\n".join(messages[-5:])
        raise RuntimeError(
            "Spherical metadata injection did not produce a valid output file.\n" + tail
        )
    return output_path


def has_spherical_metadata(path, log=None):
    """Return ``True`` if ``path`` already has spherical (V1) metadata."""
    console, _ = _collect_console(log)
    try:
        parsed = metadata_utils.parse_metadata(os.path.abspath(path), console)
    except Exception:  # noqa: BLE001
        return False
    if not parsed or not getattr(parsed, "video", None):
        return False
    for track_meta in parsed.video.values():
        if track_meta and str(track_meta.get("Spherical", "")).lower() == "true":
            return True
    return False
