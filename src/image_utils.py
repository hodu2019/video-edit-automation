"""
src/image_utils.py
==================
PIL-based image rendering helpers:
  - load_font      : load TrueType font with graceful fallback
  - wrap_text      : word-wrap text to fit a pixel width
  - make_text_overlay : render a transparent RGBA PNG overlay with text
"""

import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


# ── Font loading ───────────────────────────────────────────────────────────────

def load_font(font_path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
    """
    Load a TrueType font.
    Priority: font_path → Arial → Segoe UI → PIL default (bitmap).
    """
    if font_path and os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    for name in ["arial.ttf",
                 "C:/Windows/Fonts/arial.ttf",
                 "C:/Windows/Fonts/segoeui.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


# ── Text wrapping ──────────────────────────────────────────────────────────────

def wrap_text(text: str, font, draw: ImageDraw.ImageDraw,
              max_width: int) -> list[str]:
    """
    Word-wrap *text* so each line fits within *max_width* pixels.
    Preserves paragraph breaks (blank lines).
    """
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            lines.append("")
            continue
        words, current = paragraph.split(), ""
        for word in words:
            candidate = (current + " " + word).strip()
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [text]


# ── Text overlay PNG ───────────────────────────────────────────────────────────

def make_text_overlay(text: str, canvas_w: int, canvas_h: int,
                      cfg: dict, out_path: str) -> None:
    """
    Render *text* onto a transparent RGBA canvas and save to *out_path* (PNG).

    Relevant cfg keys (with defaults):
        text_font_path    : None  (Arial)
        text_font_size    : 48
        text_position_x   : "center"  | "left" | "right" | int (px from left)
        text_position_y   : 0.88      (fraction of canvas height, centre of block)
        text_color        : (255, 255, 255)
        text_stroke_color : (0, 0, 0)
        text_stroke_width : 2
        text_padding_x    : 40
    """
    img  = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = cfg.get("text_font_size", 48)
    font      = load_font(cfg.get("text_font_path"), font_size)
    padding   = cfg.get("text_padding_x", 40)
    lines     = wrap_text(text, font, draw, canvas_w - padding * 2)

    line_h  = font_size + int(font_size * 0.30)
    total_h = line_h * len(lines)
    pos_y   = cfg.get("text_position_y", 0.88)
    y = max(0, int(pos_y * canvas_h) - total_h // 2)
    y = min(y, canvas_h - total_h)

    # Normalise colors – accept both list and tuple
    color    = tuple(cfg.get("text_color",        (255, 255, 255)))[:3] + (255,)
    stroke_c = tuple(cfg.get("text_stroke_color", (0,   0,   0  )))[:3] + (255,)
    stroke_w = cfg.get("text_stroke_width", 2)
    pos_x    = cfg.get("text_position_x", "center")

    for line in lines:
        if line:
            bbox   = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]

            if pos_x == "center":
                x = (canvas_w - line_w) // 2
            elif pos_x == "left":
                x = padding
            elif pos_x == "right":
                x = canvas_w - line_w - padding
            else:
                x = int(pos_x)

            draw.text((x, y), line, font=font, fill=color,
                      stroke_width=stroke_w, stroke_fill=stroke_c)
        y += line_h

    img.save(out_path, "PNG")
