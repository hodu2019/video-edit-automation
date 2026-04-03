"""
src/ffmpeg_utils.py
===================
Shared FFmpeg helpers:
  - FFMPEG_BIN  : path to bundled ffmpeg executable
  - short_path  : Windows 8.3 short path (handles Unicode filenames)
  - get_video_info   : probe width, height, duration, fps, has_audio
  - get_audio_duration : probe audio file duration
"""

import ctypes
import os
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

# ── FFmpeg binary (bundled via imageio-ffmpeg, no system install needed) ───────
FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

# ── Windows Unicode path fix ───────────────────────────────────────────────────

def short_path(path: str) -> str:
    """
    Return the Windows 8.3 short path for *path*.
    ffmpeg/subprocess on Windows can fail on Unicode filenames;
    short paths are always ASCII-safe.
    Falls back to the original path on non-Windows or if the API call fails.
    """
    if sys.platform != "win32":
        return path
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
    return buf.value if n > 0 else str(path)


# ── Media probing ──────────────────────────────────────────────────────────────

def get_video_info(video_path: str) -> dict:
    """
    Probe a video file and return a dict with keys:
        width, height, duration (s), fps, has_audio
    Uses ffmpeg -i (parses stderr). Falls back to moviepy if parsing fails.
    """
    info: dict = {"width": 0, "height": 0, "duration": 0.0,
                  "fps": 30.0, "has_audio": False}
    try:
        r = subprocess.run(
            [FFMPEG_BIN, "-i", short_path(os.path.abspath(video_path))],
            capture_output=True,
        )
        txt = r.stderr.decode("utf-8", "replace")

        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", txt)
        if m:
            info["duration"] = (int(m.group(1)) * 3600
                                + int(m.group(2)) * 60
                                + float(m.group(3)))

        m = re.search(r"Stream.*Video.*?(\d{2,5})x(\d{2,5})", txt)
        if m:
            info["width"]  = int(m.group(1))
            info["height"] = int(m.group(2))

        m = re.search(r"(\d+(?:\.\d+)?)\s*fps", txt)
        if m:
            info["fps"] = float(m.group(1))

        info["has_audio"] = bool(re.search(r"Stream.*Audio", txt))

    except Exception as exc:
        print(f"  [WARN] get_video_info: {exc}")

    # Fallback: moviepy
    if info["duration"] == 0 or info["width"] == 0:
        try:
            from moviepy import VideoFileClip
            clip = VideoFileClip(video_path)
            info["width"], info["height"] = clip.size
            info["duration"]  = clip.duration
            info["fps"]       = clip.fps
            info["has_audio"] = clip.audio is not None
            clip.close()
        except Exception as exc2:
            print(f"  [WARN] moviepy fallback: {exc2}")

    return info


def get_audio_duration(audio_path: str) -> float:
    """Return duration of an audio file in seconds. Returns 0.0 on failure."""
    try:
        r = subprocess.run(
            [FFMPEG_BIN, "-i", short_path(os.path.abspath(audio_path))],
            capture_output=True,
        )
        txt = r.stderr.decode("utf-8", "replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", txt)
        if m:
            return (int(m.group(1)) * 3600
                    + int(m.group(2)) * 60
                    + float(m.group(3)))
    except Exception:
        pass
    return 0.0
