"""LG 360 CAM -> Spherical 360 video converter.

A small desktop app that turns footage from an LG 360 CAM into a spherical
(equirectangular) 360 video that VLC, YouTube, Facebook and VR headsets
recognize as 360.

Pipeline:
    1. (optional) reproject dual-fisheye -> equirectangular via ffmpeg's v360 filter
    2. inject Google Spatial Media spherical metadata so players switch to 360 mode
"""

__version__ = "1.0.0"
