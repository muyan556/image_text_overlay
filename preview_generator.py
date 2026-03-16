# -*- coding: utf-8 -*-
"""
Fast in-memory preview generator.
Returns a JPEG bytes object for a single card based on current config.
Respects show_text3_from_repeat so the preview shows what each repeat will look like.
"""
import io
import os
from typing import List
from PIL import Image, ImageDraw, ImageFont, ImageColor


def _load_font(script_dir: str, font_file: str, fallback_name: str,
               font_size: int):
    candidates = []
    if font_file:
        p = os.path.join(script_dir, "ttf", font_file)
        if os.path.exists(p):
            candidates.append(p)
    candidates.append(os.path.join(script_dir, "ttf", fallback_name))
    candidates.append(r"C:\Windows\Fonts\msyh.ttc")
    candidates.append("/System/Library/Fonts/PingFang.ttc")
    candidates.append("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    for c in candidates:
        if c and os.path.exists(c):
            try:
                return ImageFont.truetype(c, font_size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_wrapped(draw, text: str, font, start_x: int, start_y: int,
                  align_x: int, img_width: int, color: str,
                  line_spacing: int = 15):
    if not text:
        return
    right_limit = img_width - 120
    try:
        bbox = draw.textbbox((0, 0), "测试A", font=font)
        char_h = bbox[3] - bbox[1]
    except Exception:
        char_h = font.size if hasattr(font, "size") else 20
    cur_x, cur_y = start_x, start_y
    line = ""
    for ch in text:
        try:
            ch_w = draw.textlength(ch, font=font)
            line_w = draw.textlength(line, font=font)
        except Exception:
            ch_w, line_w = 10, len(line) * 10
        if cur_x + line_w + ch_w > right_limit:
            draw.text((cur_x, cur_y), line, font=font, fill=color)
            line = ch
            cur_y += char_h + line_spacing
            cur_x = align_x
        else:
            line += ch
    if line:
        draw.text((cur_x, cur_y), line, font=font, fill=color)


def generate_preview(cfg, sample_texts: List[str],
                     max_width: int = 960,
                     preview_repeat: int = 1) -> bytes:
    """
    Render a single preview JPEG.

    cfg: AppConfig
    sample_texts: [t1, t2, t3, t4] – the row content to preview
    max_width: resize output to max_width px wide (keeps aspect ratio)
    preview_repeat: which repeat number to simulate (affects text3 visibility)
    Returns JPEG bytes.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # ── Load background ─────────────────────────────────────────────────
    bg_path = cfg.background_image
    if not os.path.exists(bg_path):
        bg = Image.new("RGBA", (1920, 1080), (30, 30, 40, 255))
    else:
        bg = Image.open(bg_path).convert("RGBA")

    img = bg.copy()

    # ── Unpack texts ────────────────────────────────────────────────────
    t1    = sample_texts[0] if len(sample_texts) > 0 else ""
    t2    = sample_texts[1] if len(sample_texts) > 1 else ""
    t3_raw = sample_texts[2] if len(sample_texts) > 2 else ""
    t4    = sample_texts[3] if len(sample_texts) > 3 else ""

    # Chinese reveal gating
    show_t3_from = int(getattr(cfg.behavior, "show_text3_from_repeat", 1))
    if show_t3_from == 0:
        t3 = ""          # never show
    elif preview_repeat < show_t3_from:
        t3 = ""          # not yet revealed on this repeat
    else:
        t3 = t3_raw      # show it

    # ── Load fonts ──────────────────────────────────────────────────────
    font1 = _load_font(script_dir, cfg.text1.font_file, "MiSans-Heavy.ttf",      cfg.text1.font_size)
    font2 = _load_font(script_dir, cfg.text2.font_file, "MiSans-ExtraLight.ttf", cfg.text2.font_size)
    font3 = _load_font(script_dir, cfg.text3.font_file, "MiSans-Light.ttf",      cfg.text3.font_size)
    font4 = _load_font(script_dir, cfg.text4.font_file, "MiSans-Normal.ttf",     cfg.text4.font_size)

    # ── Draw watermark on a separate alpha layer first ──────────────────
    wm_font = _load_font(script_dir, "", "MiSans-Normal.ttf", cfg.watermark_font_size)
    wm_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    wm_draw  = ImageDraw.Draw(wm_layer)
    try:
        wm_rgb = ImageColor.getrgb(cfg.watermark_color)
    except ValueError:
        wm_rgb = (255, 255, 255)
    wm_bbox = wm_draw.textbbox((0, 0), cfg.watermark_text, font=wm_font)
    ww = wm_bbox[2] - wm_bbox[0]
    wh = wm_bbox[3] - wm_bbox[1]
    wx = cfg.watermark_pos_x - ww
    wy = cfg.watermark_pos_y - wh
    wm_draw.text((wx, wy), cfg.watermark_text, fill=wm_rgb + (115,), font=wm_font)
    img = Image.alpha_composite(img, wm_layer)

    # ── Draw all text layers AFTER alpha_composite so draw is valid ─────
    draw = ImageDraw.Draw(img)

    # Text 1 (大标题)
    if t1:
        draw.text((cfg.text1.pos_x, cfg.text1.pos_y), t1,
                  fill=cfg.text1.color, font=font1)

    # Text 3 (注释 / Chinese translation) — shown/hidden by reveal logic
    if t3:
        draw.text((cfg.text3.pos_x, cfg.text3.pos_y), t3,
                  fill=cfg.text3.color, font=font3)

    # Text 4 [词性标签] + Text 2 (释义) on same line
    cursor_x = cfg.text2.pos_x
    cursor_y = cfg.text2.pos_y
    if t4:
        t4_display = f"[{t4}]"
        draw.text((cursor_x, cursor_y), t4_display,
                  fill=cfg.text4.color, font=font4)
        try:
            cursor_x += draw.textlength(t4_display, font=font4) + 20
        except Exception:
            cursor_x += len(t4_display) * cfg.text4.font_size // 2 + 20
    if t2:
        _draw_wrapped(draw, t2, font2, cursor_x, cursor_y,
                      cfg.text2.pos_x, img.width, cfg.text2.color)

    # ── Layer position indicator dots ───────────────────────────────────
    dot_r = max(6, min(12, img.width // 160))
    for (px, py, col) in [
        (cfg.text1.pos_x, cfg.text1.pos_y, "#FF4444"),
        (cfg.text2.pos_x, cfg.text2.pos_y, "#44FF88"),
        (cfg.text3.pos_x, cfg.text3.pos_y, "#4488FF"),
        (cfg.text4.pos_x, cfg.text4.pos_y, "#FFB344"),
    ]:
        draw.ellipse((px - dot_r, py - dot_r, px + dot_r, py + dot_r), fill=col)

    # ── Resize for web delivery ─────────────────────────────────────────
    if img.width > max_width:
        ratio  = max_width / img.width
        new_h  = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)

    img_rgb = img.convert("RGB")
    buf = io.BytesIO()
    img_rgb.save(buf, format="JPEG", quality=88)
    return buf.getvalue()
