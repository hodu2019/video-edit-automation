"""
src/batch_processor.py
======================
Batch video processor – no TTS, no subtitles.

Pipeline per video:
  1. Scale source video to `video_scale` % (keep aspect ratio)
  2. Overlay on background image (centred)
  3. Mix background music (looped) + original video audio
  4. Render static text overlay (same text for all videos)
  5. Encode and export

Entry point: run_batch(cfg)
Config file: config/videos_config.json
"""

import json
import os
import subprocess
import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional

from PIL import Image

from .ffmpeg_utils import FFMPEG_BIN, short_path, get_video_info
from .image_utils import make_text_overlay

# ── Supported video extensions ─────────────────────────────────────────────────
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


# ── Config ─────────────────────────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """Load and validate JSON config. Raises SystemExit on critical errors."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg


# ── Core processor ─────────────────────────────────────────────────────────────

def process_video(source_path: str, output_path: str, cfg: dict) -> None:
    """
    Process a single video file according to *cfg*.
    Raises RuntimeError if ffmpeg fails.
    """
    print(f"\n  Source : {Path(source_path).name}")
    print(f"  Output : {Path(output_path).name}")

    bg_path    = os.path.abspath(cfg["background_path"])
    audio_path = os.path.abspath(cfg["audio_path"])

    # Text: inline string takes priority over text_path file
    text_str: str = (cfg["text"].strip() if "text" in cfg
                     else Path(cfg["text_path"]).read_text(encoding="utf-8").strip())

    # ── Canvas from background image
    bg_pil = Image.open(bg_path).convert("RGB")
    cw, ch = bg_pil.size
    print(f"  Canvas : {cw}x{ch}")

    # ── Source video metadata
    info  = get_video_info(source_path)
    dur   = info["duration"]
    scale = cfg.get("video_scale", 0.95)
    print(f"  Video  : {info['width']}x{info['height']}, {dur:.1f}s, "
          f"audio={'yes' if info['has_audio'] else 'no'}")

    orig_vol = cfg.get("original_audio_volume", 1.0)
    bg_vol   = cfg.get("bg_music_volume", 0.25)
    fps      = cfg.get("output_fps", 30)

    use_bg_audio = bg_vol > 0 and os.path.exists(audio_path)

    # ── Temp text overlay PNG
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False,
                                     dir=tempfile.gettempdir()) as tmp:
        text_tmp = tmp.name
    try:
        make_text_overlay(text_str, cw, ch, cfg, text_tmp)

        # ── ffmpeg input slots
        # 0 : background image  (-loop 1)
        # 1 : source video
        # 2 : bg music          (-stream_loop -1)  [optional]
        # last : text PNG       (-loop 1)
        sp_bg    = short_path(bg_path)
        sp_src   = short_path(os.path.abspath(source_path))
        sp_audio = short_path(audio_path)
        sp_text  = short_path(text_tmp)
        sp_out   = short_path(os.path.abspath(output_path))

        cmd = [FFMPEG_BIN, "-y",
               "-loop", "1", "-framerate", str(fps), "-i", sp_bg,
               "-i", sp_src]

        audio_idx: Optional[int] = None
        if use_bg_audio:
            cmd += ["-stream_loop", "-1", "-i", sp_audio]
            audio_idx = 2

        text_idx = (audio_idx + 1) if audio_idx is not None else 2
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", sp_text]

        # ── Video filter
        fc = (f"[1:v]scale=iw*{scale}:ih*{scale},setsar=1[sv];"
              f"[0:v]scale={cw}:{ch},setsar=1[bg];"
              f"[bg][sv]overlay=(W-w)/2:(H-h)/2[comp];"
              f"[comp][{text_idx}:v]overlay=0:0:format=auto[vout]")

        # ── Audio filter
        audio_map: list[str] = []
        if info["has_audio"] and use_bg_audio:
            fc += (f";[1:a]volume={orig_vol}[a1]"
                   f";[{audio_idx}:a]volume={bg_vol},atrim=0:{dur}[a2]"
                   f";[a1][a2]amix=inputs=2:duration=first:normalize=0[aout]")
            audio_map = ["-map", "[aout]"]
        elif info["has_audio"]:
            fc += f";[1:a]volume={orig_vol}[aout]"
            audio_map = ["-map", "[aout]"]
        elif use_bg_audio:
            fc += (f";[{audio_idx}:a]volume={bg_vol},atrim=0:{dur}[aout]")
            audio_map = ["-map", "[aout]"]

        cmd += ["-filter_complex", fc,
                "-map", "[vout]",
                *audio_map,
                "-t", str(dur),
                "-c:v", cfg.get("output_codec", "libx264"),
                "-preset", cfg.get("output_preset", "fast"),
                "-crf", str(cfg.get("output_crf", 23))]
        if audio_map:
            cmd += ["-c:a", cfg.get("output_audio_codec", "aac"), "-ar", "44100"]
        cmd.append(sp_out)

        print("  Encoding…")
        proc = subprocess.run(cmd, capture_output=True)

        if proc.returncode != 0:
            stderr_lines = [l for l in
                            proc.stderr.decode("utf-8", "replace").splitlines()
                            if l.strip()]
            print("  [ERR] ffmpeg failed:")
            for l in stderr_lines[-30:]:
                print("   ", l)
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")

    finally:
        try:
            os.unlink(text_tmp)
        except OSError:
            pass

    print("  [OK] Done!")


# ── Batch runner ───────────────────────────────────────────────────────────────

def run_batch(cfg: dict) -> None:
    """Process all videos in cfg['source_dir'] and write to cfg['output_dir']."""
    source_dir = Path(cfg["source_dir"])
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(f for f in source_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in _VIDEO_EXTS)

    if not videos:
        print(f"[!] No videos found in: {source_dir}")
        return

    print(f"\n{'='*60}")
    print(f"  Batch Video Processor")
    print(f"{'='*60}")
    print(f"  Found  : {len(videos)} video(s)")
    print(f"  Output : {output_dir.resolve()}")
    print(f"  Text   : {repr(cfg.get('text', '(from file)'))}")
    print(f"{'='*60}")

    ok: int = 0
    failed: list[str] = []
    t0 = time.time()

    for i, vp in enumerate(videos, 1):
        out_path = str(output_dir / (vp.stem + "_output.mp4"))
        print(f"\n[{i}/{len(videos)}]", end="")
        t1 = time.time()
        try:
            process_video(str(vp), out_path, cfg)
            print(f"  Time: {time.time()-t1:.1f}s")
            ok += 1
        except Exception:
            traceback.print_exc()
            failed.append(vp.name)

    print(f"\n{'='*60}")
    print(f"  Done : {ok}/{len(videos)} succeeded")
    if failed:
        print("  Failed:")
        for f in failed:
            print(f"    - {f}")
    print(f"  Total: {time.time()-t0:.1f}s")
    print(f"{'='*60}\n")
