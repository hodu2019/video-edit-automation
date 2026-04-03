"""
src/voice_processor.py
======================
Voice video processor – TTS + running subtitle + text overlay.

Pipeline per video:
  1. Scale source video to `video_scale` % (keep aspect ratio)
  2. Overlay on background image (centred)
  3. Generate TTS audio from `audio_script` via Microsoft Edge Neural TTS
  4. Duration check: warn if TTS > video, trim if necessary
  5. Build running subtitle (ASS) synced to TTS word timing
  6. Mix audio: original video + TTS voice + optional background music
  7. Render static text overlay (CTA)
  8. Encode and export

Entry point: run_batch(config_path)
Config file: config/voice_config.json
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional

import edge_tts
from PIL import Image

from .ffmpeg_utils import FFMPEG_BIN, short_path, get_video_info, get_audio_duration
from .image_utils import load_font, make_text_overlay


# ── TTS ────────────────────────────────────────────────────────────────────────

async def generate_tts(text: str, voice: str, rate: str, volume: str,
                       output_path: str) -> list[dict]:
    """
    Stream TTS from edge-tts and write MP3 to *output_path*.

    edge-tts 7.x emits SentenceBoundary events (not word-level).
    We approximate per-word timing by distributing each sentence's
    duration proportionally to each word's character count.

    Returns a list of word dicts:
        [{"word": str, "start": float, "duration": float}, ...]
    """
    communicate  = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
    sent_bounds: list[dict] = []
    audio_data   = bytearray()

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "SentenceBoundary":
            sent_bounds.append({
                "text":     chunk["text"],
                "start":    chunk["offset"]   / 10_000_000,  # 100ns → s
                "duration": chunk["duration"] / 10_000_000,
            })

    with open(output_path, "wb") as f:
        f.write(audio_data)

    # Decompose sentences → words with proportional timing
    word_boundaries: list[dict] = []
    for sb in sent_bounds:
        words       = sb["text"].split()
        total_chars = max(sum(len(w) for w in words), 1)
        cursor      = sb["start"]
        for word in words:
            word_dur = sb["duration"] * (len(word) / total_chars)
            word_boundaries.append({"word": word, "start": cursor,
                                    "duration": word_dur})
            cursor += word_dur

    return word_boundaries


# ── Subtitle helpers ───────────────────────────────────────────────────────────

def _seconds_to_ass(s: float) -> str:
    """Convert seconds to ASS timestamp format H:MM:SS.cc."""
    h   = int(s // 3600)
    m   = int((s % 3600) // 60)
    sec = s % 60
    cs  = int((sec % 1) * 100)
    return f"{h}:{m:02d}:{int(sec):02d}.{cs:02d}"


def build_subtitle_lines(word_boundaries: list[dict], words_per_line: int,
                          max_duration: float) -> list[dict]:
    """
    Group word boundaries into subtitle display lines.
    Breaks at sentence-ending punctuation or every *words_per_line* words.

    Returns list of dicts: [{"start": float, "end": float, "text": str}, ...]
    """
    lines: list[dict]   = []
    current: list[dict] = []
    end_puncts          = {".", "?", "!", "…", "..."}

    def flush() -> None:
        if not current:
            return
        start = current[0]["start"]
        end   = current[-1]["start"] + current[-1]["duration"] + 0.05
        text  = " ".join(w["word"] for w in current)
        lines.append({"start": start,
                      "end":   min(end, max_duration),
                      "text":  text})
        current.clear()

    for wb in word_boundaries:
        if wb["start"] >= max_duration:
            break
        current.append(wb)
        if (len(current) >= words_per_line
                or any(wb["word"].rstrip("\"'").endswith(p) for p in end_puncts)):
            flush()

    flush()

    # Remove overlaps
    for i in range(len(lines) - 1):
        if lines[i]["end"] > lines[i + 1]["start"]:
            lines[i]["end"] = lines[i + 1]["start"] - 0.01

    return lines


def make_ass_file(subtitle_lines: list[dict], canvas_w: int, canvas_h: int,
                  cfg: dict, out_path: str, video_duration: float) -> None:
    """Write an ASS subtitle file for *subtitle_lines*."""
    font_size = cfg.get("subtitle_font_size", 46)
    pos_y     = cfg.get("subtitle_position_y", 0.72)
    margin_v  = int((1.0 - pos_y) * canvas_h)
    stroke_w  = cfg.get("subtitle_stroke_width", 2)

    # Resolve font name for ASS style header
    font_path = cfg.get("subtitle_font_path")
    font_name = Path(font_path).stem if (font_path and os.path.exists(font_path)) else "Arial"

    def _rgb_to_ass(rgb: list | tuple) -> str:
        r, g, b = rgb
        return f"&H00{b:02X}{g:02X}{r:02X}"

    primary = _rgb_to_ass(cfg.get("subtitle_color",       [255, 255, 255]))
    outline = _rgb_to_ass(cfg.get("subtitle_stroke_color", [0,   0,   0]))

    header = (
        f"[Script Info]\n"
        f"ScriptType: v4.00+\n"
        f"PlayResX: {canvas_w}\n"
        f"PlayResY: {canvas_h}\n"
        f"ScaledBorderAndShadow: yes\n\n"
        f"[V4+ Styles]\n"
        f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        f"OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        f"ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        f"Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{primary},&H000000FF,"
        f"{outline},&H80000000,-1,0,0,0,100,100,0,0,1,{stroke_w},0,"
        f"2,20,20,{margin_v},1\n\n"
        f"[Events]\n"
        f"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = "".join(
        f"Dialogue: 0,{_seconds_to_ass(ln['start'])},{_seconds_to_ass(min(ln['end'], video_duration))},"
        f"Default,,0,0,0,,{ln['text'].replace('{', '{{').replace('}', '}}')}\n"
        for ln in subtitle_lines
        if ln["start"] < video_duration
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + events)


def _build_drawtext_filter(sub_lines: list[dict], canvas_h: int,
                            cfg: dict) -> str:
    """
    Fallback subtitle renderer using ffmpeg drawtext filter chain.
    Used when libass / subtitles filter is unavailable.
    """
    fs     = cfg.get("subtitle_font_size", 46)
    y_px   = int(cfg.get("subtitle_position_y", 0.72) * canvas_h)
    stroke = cfg.get("subtitle_stroke_width", 2)

    parts = []
    for ln in sub_lines:
        safe = (ln["text"]
                .replace("'", "\\'")
                .replace(":", "\\:")
                .replace(",", "\\,"))
        enable = f"between(t\\,{ln['start']:.3f}\\,{ln['end']:.3f})"
        parts.append(
            f"drawtext=text='{safe}':fontsize={fs}:fontcolor=white"
            f":borderw={stroke}:bordercolor=black"
            f":x=(w-text_w)/2:y={y_px}:enable='{enable}'"
        )

    return ("[comp]" + ",".join(parts)) if parts else "[comp]null"


# ── Core processor ─────────────────────────────────────────────────────────────

async def process_one(entry: dict, settings: dict) -> bool:
    """
    Process a single video entry.
    Returns True on success, False on failure.
    """
    s = settings

    video_file = entry["video"]
    script     = entry["audio_script"].strip()
    text_str   = entry.get("text", "")
    voice      = entry.get("voice",        s.get("voice",        "en-US-AndrewNeural"))
    rate       = entry.get("voice_rate",   s.get("voice_rate",   "+0%"))
    vol_str    = entry.get("voice_volume", s.get("voice_volume", "+0%"))

    source_dir = Path(s["source_dir"])
    output_dir = Path(s["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    source_path = str(source_dir / video_file)
    output_path = str(output_dir / (Path(video_file).stem + "_output.mp4"))

    if not os.path.exists(source_path):
        print(f"  [ERR] File not found: {source_path}")
        return False

    print(f"\n  Video  : {video_file}")
    print(f"  Voice  : {voice} | rate={rate}")

    # ── Background canvas
    bg_pil = Image.open(os.path.abspath(s["background_path"])).convert("RGB")
    cw, ch = bg_pil.size

    # ── Source video metadata
    info    = get_video_info(source_path)
    vid_dur = info["duration"]
    scale   = s.get("video_scale", 0.95)
    fps     = s.get("output_fps", 30)
    print(f"  Canvas : {cw}x{ch}")
    print(f"  Video  : {info['width']}x{info['height']}, {vid_dur:.2f}s")

    # ── All temp files live in one temp dir (auto-cleaned on exit)
    with tempfile.TemporaryDirectory() as tmpdir:
        tts_path  = os.path.join(tmpdir, "voice.mp3")
        sub_path  = os.path.join(tmpdir, "subs.ass")
        text_path = os.path.join(tmpdir, "text_overlay.png")

        # ── TTS generation
        print(f"  TTS    : generating ({len(script.split())} words)…")
        word_bounds = await generate_tts(script, voice, rate, vol_str, tts_path)
        tts_dur     = get_audio_duration(tts_path)
        print(f"  TTS    : {tts_dur:.2f}s | video: {vid_dur:.2f}s")

        # ── Duration check
        if tts_dur > vid_dur:
            excess = tts_dur - vid_dur
            print(f"\n  [WARN] TTS audio ({tts_dur:.2f}s) exceeds video ({vid_dur:.2f}s) "
                  f"by {excess:.2f}s — will be trimmed.")
            print(f"         Fix: shorten audio_script or increase voice_rate.\n")
            effective_dur = vid_dur
        else:
            effective_dur = tts_dur
            gap = vid_dur - tts_dur
            if gap > 3.0:
                print(f"  [INFO] Audio ({tts_dur:.2f}s) is {gap:.1f}s shorter than video. "
                      f"Remaining portion will have no voice.")

        # ── Subtitles
        words_per_line = s.get("subtitle_words_per_line", 6)
        sub_lines      = build_subtitle_lines(word_bounds, words_per_line, effective_dur)
        make_ass_file(sub_lines, cw, ch, s, sub_path, vid_dur)
        print(f"  Subs   : {len(sub_lines)} line(s)")

        # ── Static text overlay
        make_text_overlay(text_str, cw, ch, s, text_path)

        # ── Audio settings
        mute_orig  = s.get("mute_original_audio", False)
        orig_vol   = 0.0 if mute_orig else s.get("original_audio_volume", 0.25)
        voice_vol  = s.get("voice_audio_volume", 1.0)

        bg_music_enabled = s.get("bg_music_enabled", False)
        bg_music_path    = s.get("bg_music_path", "audio/audio_template.wav")
        bg_music_vol     = s.get("bg_music_volume", 0.15)
        use_bg_music     = (bg_music_enabled
                            and os.path.exists(os.path.abspath(bg_music_path)))

        print(f"  Audio  : orig={'muted' if mute_orig else orig_vol} | "
              f"tts={voice_vol} | bgm={'off' if not use_bg_music else bg_music_vol}")

        # ── Short paths for ffmpeg
        sp_bg   = short_path(os.path.abspath(s["background_path"]))
        sp_src  = short_path(os.path.abspath(source_path))
        sp_tts  = short_path(tts_path)
        sp_text = short_path(text_path)
        sp_sub  = sub_path.replace("\\", "/").replace(":", "\\:")
        sp_out  = short_path(os.path.abspath(output_path))
        sp_bgm  = short_path(os.path.abspath(bg_music_path)) if use_bg_music else None

        # ── Build ffmpeg inputs
        # Slot 0 : background image  (-loop 1)
        # Slot 1 : source video
        # Slot 2 : TTS audio
        # Slot 3 : BG music          (-stream_loop -1)  [optional]
        # Slot last : text PNG       (-loop 1)
        cmd = [FFMPEG_BIN, "-y",
               "-loop", "1", "-framerate", str(fps), "-i", sp_bg,
               "-i", sp_src,
               "-i", sp_tts]

        bgm_idx: Optional[int] = None
        if use_bg_music:
            cmd  += ["-stream_loop", "-1", "-i", sp_bgm]
            bgm_idx  = 3
            text_idx = 4
        else:
            text_idx = 3

        cmd += ["-loop", "1", "-framerate", str(fps), "-i", sp_text]

        # ── Video filter
        vf = (f"[1:v]scale=iw*{scale}:ih*{scale},setsar=1[sv];"
              f"[0:v]scale={cw}:{ch},setsar=1[bg];"
              f"[bg][sv]overlay=(W-w)/2:(H-h)/2[comp];"
              f"[comp]subtitles='{sp_sub}'[comp_sub];"
              f"[comp_sub][{text_idx}:v]overlay=0:0:format=auto[vout]")

        # ── Audio filter (dynamic mix of up to 3 sources)
        af_parts:   list[str] = []
        mix_labels: list[str] = []

        if info["has_audio"] and not mute_orig:
            af_parts.append(f"[1:a]volume={orig_vol},atrim=0:{vid_dur}[a_orig]")
            mix_labels.append("[a_orig]")

        af_parts.append(f"[2:a]volume={voice_vol},atrim=0:{vid_dur}[a_tts]")
        mix_labels.append("[a_tts]")

        if use_bg_music:
            af_parts.append(f"[{bgm_idx}:a]volume={bg_music_vol},"
                            f"atrim=0:{vid_dur}[a_bgm]")
            mix_labels.append("[a_bgm]")

        n = len(mix_labels)
        if n == 1:
            single = mix_labels[0].strip("[]")
            af_parts.append(f"[{single}]anull[aout]")
        else:
            af_parts.append(f"{''.join(mix_labels)}amix=inputs={n}:"
                            f"duration=first:normalize=0[aout]")

        af = ";".join(af_parts)
        fc = vf + ";" + af

        cmd += ["-filter_complex", fc,
                "-map", "[vout]",
                "-map", "[aout]",
                "-t", str(vid_dur),
                "-c:v", s.get("output_codec", "libx264"),
                "-preset", s.get("output_preset", "fast"),
                "-crf", str(s.get("output_crf", 23)),
                "-c:a", s.get("output_audio_codec", "aac"),
                "-ar", "44100",
                sp_out]

        print("  Encoding…")
        proc = subprocess.run(cmd, capture_output=True)

        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", "replace")
            # Fallback: libass not available → use drawtext
            if "subtitles" in stderr.lower() or "libass" in stderr.lower():
                print("  [WARN] subtitles filter unavailable → drawtext fallback")
                vf_fb = _build_drawtext_filter(sub_lines, ch, s)
                vf2   = (f"[1:v]scale=iw*{scale}:ih*{scale},setsar=1[sv];"
                         f"[0:v]scale={cw}:{ch},setsar=1[bg];"
                         f"[bg][sv]overlay=(W-w)/2:(H-h)/2[comp];"
                         f"{vf_fb}[comp_sub];"
                         f"[comp_sub][{text_idx}:v]overlay=0:0:format=auto[vout]")
                fc2 = vf2 + ";" + af
                cmd[cmd.index("-filter_complex") + 1] = fc2
                proc = subprocess.run(cmd, capture_output=True)

            if proc.returncode != 0:
                err_lines = [l for l in
                             proc.stderr.decode("utf-8", "replace").splitlines()
                             if l.strip()]
                print("  [ERR] ffmpeg failed:")
                for l in err_lines[-20:]:
                    print("   ", l)
                return False

    print(f"  [OK] → {output_path}")
    return True


# ── Batch runner ───────────────────────────────────────────────────────────────

async def run_batch(config_path: str) -> None:
    """Load voice_config.json and process all listed videos."""
    path = Path(config_path)
    if not path.exists():
        print(f"[ERR] Config not found: {config_path}")
        return

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    settings: dict   = raw.get("settings", {})
    videos:   list   = raw.get("videos",   [])

    if not videos:
        print("[!] No videos listed in config.")
        return

    print(f"\n{'='*60}")
    print(f"  Voice Video Processor")
    print(f"{'='*60}")
    print(f"  Config : {config_path}")
    print(f"  Videos : {len(videos)}")
    print(f"  Output : {settings.get('output_dir', 'output_voice')}")
    print(f"{'='*60}")

    ok:     int       = 0
    failed: list[str] = []
    t0 = time.time()

    for i, entry in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}]", end="")
        t1 = time.time()
        try:
            success = await process_one(entry, settings)
            elapsed = time.time() - t1
            if success:
                print(f"  ✓ {elapsed:.1f}s")
                ok += 1
            else:
                failed.append(entry["video"])
        except Exception:
            traceback.print_exc()
            failed.append(entry["video"])

    print(f"\n{'='*60}")
    print(f"  Done : {ok}/{len(videos)} succeeded")
    if failed:
        print("  Failed:")
        for f in failed:
            print(f"    - {f}")
    print(f"  Total: {time.time()-t0:.1f}s")
    print(f"{'='*60}\n")
