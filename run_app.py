#!/usr/bin/env python
"""Launch the GUI (default) or run a headless self-test (``--selftest``).

This is also the entry script used by the PyInstaller build in
``build/app.spec``.
"""

import os
import sys

# Ensure the project root is importable whether run as a script or when frozen.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _run_gui():
    from app.gui import main

    main()


def _run_selftest():
    from app import selftest

    return selftest.run()


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] in ("--selftest", "--self-test"):
        raise SystemExit(_run_selftest())
    if argv and argv[0] in ("--version", "-V"):
        from app import __version__

        if sys.stdout is not None:
            print(__version__)
        raise SystemExit(0)
    _run_gui()
