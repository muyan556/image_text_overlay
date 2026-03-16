# -*- coding: utf-8 -*-
"""
Video Generation Pipeline
Combines: TTS → Image generation → Video assembly with silence padding.

Key features:
- show_text3_from_repeat: hide Chinese translation on early repeats, reveal later
- Real silent audio (not -an) to prevent sync drift
- Windows-safe concat list paths (forward slashes)
"""
import os
import shutil
import subprocess
import time
from typing import Callable, List, Optional

from image_text_overlay import ImageTextOverlay
from tts_backends import get_tts_backend
from config import AppConfig


def _get_ffprobe(ffmpeg_path: str) -> str:
    """Derive ffprobe path from ffmpeg path."""
    probe = ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
    if os.path.exists(probe):
        return probe
    return "ffprobe"


def _safe_path(p: str) -> str:
    """Return forward-slash path safe for FFmpeg concat demuxer."""
    return p.replace("\\", "/")


def get_audio_duration(audio_path: str, ffmpeg_path: str) -> float:
    """Get audio file duration in seconds using ffprobe."""
    ffprobe = _get_ffprobe(ffmpeg_path)
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    try:
        r = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=15)
        return float(r.stdout.strip())
    except Exception:
        return 5.0


def generate_silent_audio(duration: float, output_path: str, ffmpeg_path: str) -> bool:
    """
    Generate a real silent MP3 of the given duration via lavfi anullsrc.
    Using real audio (not -an) prevents audio/video sync drift in the final concat.
    """
    if duration <= 0.05:
        return False   # Skip negligible pauses rather than letting FFmpeg error

    cmd = [
        ffmpeg_path,
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=44100",
        "-t", f"{duration:.3f}",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        "-y",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [Pipeline] Silent audio gen failed: {e.stderr[-300:]}")
        return False


def create_video_segment(image_path: str, audio_path: str,
                          output_path: str, ffmpeg_path: str) -> bool:
    """Combine one image + one audio file into a video segment."""
    cmd = [
        ffmpeg_path,
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-y",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [Pipeline] Segment failed {os.path.basename(output_path)}: {e.stderr[-200:]}")
        return False
    except Exception as e:
        print(f"  [Pipeline] Segment error {os.path.basename(output_path)}: {e}")
        return False


def concatenate_segments(segment_pairs: List[tuple], temp_dir: str,
                          intermediate_path: str, ffmpeg_path: str) -> bool:
    """
    Concatenate (voiced, silent) segment pairs into one intermediate video.
    BUG FIX: use forward slashes in concat list for Windows FFmpeg compatibility.
    """
    concat_list = os.path.join(temp_dir, "concat_list.txt")
    entries = []
    for voiced, silent in segment_pairs:
        if voiced and os.path.exists(voiced):
            entries.append(f"file '{_safe_path(os.path.abspath(voiced))}'")
        if silent and os.path.exists(silent):
            entries.append(f"file '{_safe_path(os.path.abspath(silent))}'")

    if not entries:
        print("  [Pipeline] Concat: no valid segments to concatenate.")
        return False

    with open(concat_list, "w", encoding="utf-8") as f:
        f.write("\n".join(entries) + "\n")

    cmd = [
        ffmpeg_path,
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        "-y",
        intermediate_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [Pipeline] Concat failed: {e.stderr[-400:]}")
        return False


def fix_sync_video(input_path: str, output_path: str, ffmpeg_path: str, emit: Callable[[str, dict], None] = None) -> bool:
    """Remux the video and ensure quick start playback time without re-encoding."""
    cmd = [
        ffmpeg_path, "-y",
        "-i", input_path,
        "-c", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    try:
        if emit:
            emit("log", {"level": "info", "msg": "  Applying video optimization (faststart)…"})
            
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if r.returncode == 0:
            if emit:
                emit("progress", {"stage": "video", "pct": 100, "detail": "优化完成"})
            return True
        else:
            if emit:
                emit("log", {"level": "error", "msg": f"  [Pipeline] Optimization failed: {r.stderr[-400:]}"})
            return False
    except Exception as e:
        if emit:
            emit("log", {"level": "error", "msg": f"  [Pipeline] Optimization error: {e}"})
        return False


def _generate_images_for_reveal(cfg: AppConfig,
                                 text1: List[str], text2: List[str],
                                 text3: List[str], text4: List[str],
                                 images_dir: str,
                                 prefix: str = "") -> None:
    """
    Helper: generate a batch of images into images_dir with optional prefix.
    prefix="" → {i}.png (with text3),  prefix="no3_" → {i}.png (without text3)
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    def font_path(layer_cfg):
        if layer_cfg.font_file:
            p = os.path.join(script_dir, "ttf", layer_cfg.font_file)
            return p if os.path.exists(p) else None
        return None

    overlay = ImageTextOverlay(cfg.background_image, images_dir)

    # Temporarily rename output files via a custom output_dir with subdirectory
    # ImageTextOverlay saves as {i}.png — use a temp subdir then rename
    if prefix:
        sub_dir = os.path.join(images_dir, "_tmp_no3")
        os.makedirs(sub_dir, exist_ok=True)
        ov2 = ImageTextOverlay(cfg.background_image, sub_dir)
        ov2.batch_generate(
            text_list1=text1, text_list2=text2,
            text_list3=[""] * len(text1),   # ← empty = no Chinese shown
            text_list4=text4,
            watermark_text=cfg.watermark_text,
            text1_pos=(cfg.text1.pos_x, cfg.text1.pos_y),
            text2_pos=(cfg.text2.pos_x, cfg.text2.pos_y),
            text3_pos=(cfg.text3.pos_x, cfg.text3.pos_y),
            watermark_bottom_right_pos=(cfg.watermark_pos_x, cfg.watermark_pos_y),
            font_path1=font_path(cfg.text1), font_path2=font_path(cfg.text2),
            font_path3=font_path(cfg.text3), font_path4=font_path(cfg.text4),
            font_path_watermark=None,
            font_size1=cfg.text1.font_size, font_size2=cfg.text2.font_size,
            font_size3=cfg.text3.font_size, font_size4=cfg.text4.font_size,
            font_size_watermark=cfg.watermark_font_size,
            text_color1=cfg.text1.color, text_color2=cfg.text2.color,
            text_color3=cfg.text3.color, text_color4=cfg.text4.color,
            watermark_color=cfg.watermark_color,
        )
        # Rename {i}.png → no3_{i}.png in images_dir
        for fname in os.listdir(sub_dir):
            if fname.endswith(".png"):
                os.replace(
                    os.path.join(sub_dir, fname),
                    os.path.join(images_dir, prefix + fname)
                )
        shutil.rmtree(sub_dir, ignore_errors=True)
    else:
        overlay.batch_generate(
            text_list1=text1, text_list2=text2,
            text_list3=text3,
            text_list4=text4,
            watermark_text=cfg.watermark_text,
            text1_pos=(cfg.text1.pos_x, cfg.text1.pos_y),
            text2_pos=(cfg.text2.pos_x, cfg.text2.pos_y),
            text3_pos=(cfg.text3.pos_x, cfg.text3.pos_y),
            watermark_bottom_right_pos=(cfg.watermark_pos_x, cfg.watermark_pos_y),
            font_path1=font_path(cfg.text1), font_path2=font_path(cfg.text2),
            font_path3=font_path(cfg.text3), font_path4=font_path(cfg.text4),
            font_path_watermark=None,
            font_size1=cfg.text1.font_size, font_size2=cfg.text2.font_size,
            font_size3=cfg.text3.font_size, font_size4=cfg.text4.font_size,
            font_size_watermark=cfg.watermark_font_size,
            text_color1=cfg.text1.color, text_color2=cfg.text2.color,
            text_color3=cfg.text3.color, text_color4=cfg.text4.color,
            watermark_color=cfg.watermark_color,
        )


class VideoPipeline:
    """
    Full pipeline: TTS → Images → Video segments → Final video.
    emit(event, data) is called at each step for SSE streaming.
    """

    def __init__(self, cfg: AppConfig, emit: Callable[[str, dict], None] = None):
        self.cfg = cfg
        self._emit = emit or (lambda event, data: print(f"[{event}] {data}"))

    def _log(self, msg: str, level: str = "info"):
        self._emit("log", {"level": level, "msg": msg})

    def _progress(self, stage: str, pct: float, detail: str = ""):
        self._emit("progress", {"stage": stage, "pct": pct, "detail": detail})

    def run(self,
            text_lists: List[List[str]],
            output_path: str = None,
            skip_tts: bool = False,
            skip_images: bool = False) -> bool:
        """
        Run the full pipeline.
        text_lists: [text1_lines, text2_lines, text3_lines, text4_lines]
        output_path: overrides config's output filename
        skip_tts: reuse existing mp3 files (for resume after error)
        skip_images: reuse existing png files (for resume after error)
        """
        cfg = self.cfg
        final_output = output_path or os.path.join(
            cfg.output_dir, cfg.behavior.output_filename
        )

        # Unpack and validate text lists
        text1 = text_lists[0] if len(text_lists) > 0 else []
        text2 = text_lists[1] if len(text_lists) > 1 else []
        text3 = text_lists[2] if len(text_lists) > 2 else []
        text4 = text_lists[3] if len(text_lists) > 3 else []

        max_items = max(len(text1), len(text2), len(text3), len(text4), 1)

        def pad(lst, n):
            return lst + [""] * (n - len(lst))

        text1 = pad(text1, max_items)
        text2 = pad(text2, max_items)
        text3 = pad(text3, max_items)
        text4 = pad(text4, max_items)

        # Which text list drives TTS
        tts_src_idx = cfg.tts.tts_source_list
        tts_texts = [text1, text2, text3, text4][min(tts_src_idx, 3)]

        # Behavior params
        repeat           = max(1, cfg.behavior.repeat_count)
        silent_mult      = max(0.0, cfg.behavior.silent_multiplier)
        show_t3_from_rep = cfg.behavior.show_text3_from_repeat   # 1-based; 0=never

        # Setup directories
        os.makedirs(cfg.tts_output_dir, exist_ok=True)
        os.makedirs(cfg.images_dir,     exist_ok=True)
        os.makedirs(cfg.output_dir,     exist_ok=True)

        temp_dir     = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    cfg.behavior.temp_dir)
        intermediate = os.path.join(temp_dir, "_intermediate.mp4")

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)

        try:
            # ── STAGE 1: TTS ─────────────────────────────────────────
            audio_paths: List[Optional[str]] = []
            if skip_tts:
                self._log("=== Stage 1/3: TTS — SKIPPED (reusing existing files) ===")
                self._progress("tts", 100, "Reusing TTS audio")
                for i in range(1, max_items + 1):
                    p = os.path.join(cfg.tts_output_dir, f"{i}.mp3")
                    if os.path.exists(p) and os.path.getsize(p) > 100:
                        audio_paths.append(p)
                        self._log(f"  [{i}/{max_items}] ✓ found: {i}.mp3")
                    else:
                        audio_paths.append(None)
                        self._log(f"  [{i}/{max_items}] ✗ missing — skip", "warning")
            else:
                self._log("=== Stage 1/3: TTS Audio Generation ===")
                self._progress("tts", 0, f"Generating {max_items} audio files…")
                backend = get_tts_backend(cfg)
                for i, text in enumerate(tts_texts, 1):
                    if not text.strip():
                        audio_paths.append(None)
                        self._log(f"  [{i}/{max_items}] empty — skip TTS", "warning")
                    else:
                        out = os.path.join(cfg.tts_output_dir, f"{i}.mp3")
                        if os.path.exists(out) and os.path.getsize(out) > 100:
                            self._log(f"  [{i}/{max_items}] ✓ reuse: {os.path.basename(out)}")
                        else:
                            ok = backend.generate(text, out)
                            level = "info" if ok else "error"
                            sym = "✓" if ok else "✗ FAILED"
                            self._log(f"  [{i}/{max_items}] {sym}: {text[:40]}", level)
                        audio_paths.append(out if os.path.exists(out) else None)
                    self._progress("tts", i / max_items * 100, f"TTS {i}/{max_items}")
                    if i < max_items and cfg.behavior.tts_request_delay > 0:
                        time.sleep(cfg.behavior.tts_request_delay)

            # ── STAGE 2: Image Generation ───────────────────────────────────
            needs_no3 = (show_t3_from_rep > 1 or show_t3_from_rep == 0) and repeat > 0
            if skip_images:
                self._log("=== Stage 2/3: Images — SKIPPED (reusing existing files) ===")
                self._progress("images", 100, "Reusing images")
            else:
                self._log("=== Stage 2/3: Image Generation ===")
                self._progress("images", 0, "Generating images…")
                _generate_images_for_reveal(cfg, text1, text2, text3, text4,
                                            cfg.images_dir, prefix="")
                self._log(f"  ✓ {max_items} images (with Chinese) saved")
                if needs_no3:
                    _generate_images_for_reveal(cfg, text1, text2, text3, text4,
                                                cfg.images_dir, prefix="no3_")
                    self._log(f"  ✓ {max_items} images (without Chinese) saved")
                self._progress("images", 100, "Generated images")

            # ── STAGE 3: Video Assembly ───────────────────────────────────────
            self._log("=== Stage 3/3: Video Assembly ===")
            self._progress("video", 0, "Assembling video segments…")

            segment_pairs: List[tuple] = []
            total_ops    = max_items * repeat * 2   # voiced + silent per rep
            ops_done     = 0

            for i in range(1, max_items + 1):
                # Base images for with/without Chinese
                img_with = os.path.join(cfg.images_dir, f"{i}.png")
                img_no3  = os.path.join(cfg.images_dir, f"no3_{i}.png")
                audio_path = audio_paths[i - 1]

                if not os.path.exists(img_with):
                    self._log(f"  ✗ Missing image {i}.png — skip item {i}", "error")
                    ops_done += repeat * 2
                    continue
                if audio_path is None or not os.path.exists(audio_path):
                    self._log(f"  ✗ Missing audio {i}.mp3 — skip item {i}", "error")
                    ops_done += repeat * 2
                    continue

                audio_dur  = get_audio_duration(audio_path, cfg.ffmpeg_path)
                silent_dur = audio_dur * silent_mult

                for rep in range(1, repeat + 1):
                    # Choose image version for this repetition
                    show_chinese = (show_t3_from_rep > 0 and rep >= show_t3_from_rep)
                    if show_chinese or not needs_no3:
                        img_path = img_with
                    else:
                        img_path = img_no3 if os.path.exists(img_no3) else img_with

                    # — Voiced segment —
                    voiced_out = os.path.join(temp_dir, f"{i}_r{rep}_voiced.mp4")
                    ok = create_video_segment(img_path, audio_path, voiced_out,
                                              cfg.ffmpeg_path)
                    ops_done += 1
                    self._progress("video", ops_done / total_ops * 100,
                                   f"Item {i} rep {rep}/{repeat} voiced {'✓' if ok else '✗'}")

                    if not ok:
                        ops_done += 1  # skip silent count
                        continue

                    # — Silent segment (real blank audio) —
                    silent_vid_path = None
                    if silent_dur > 0.05:
                        silent_audio = os.path.join(temp_dir, f"{i}_r{rep}_silent.mp3")
                        s_ok = generate_silent_audio(silent_dur, silent_audio, cfg.ffmpeg_path)
                        if s_ok:
                            silent_out = os.path.join(temp_dir, f"{i}_r{rep}_silent.mp4")
                            s2_ok = create_video_segment(img_path, silent_audio, silent_out,
                                                         cfg.ffmpeg_path)
                            if s2_ok:
                                silent_vid_path = silent_out
                    ops_done += 1
                    self._progress("video", ops_done / total_ops * 100,
                                   f"Item {i} rep {rep}/{repeat} silent {'✓' if silent_vid_path else '—'}")

                    segment_pairs.append((voiced_out if ok else None, silent_vid_path))

            if not segment_pairs:
                self._log("✗ No segments generated — aborting.", "error")
                return False

            self._log(f"  ✓ {len(segment_pairs)} segment pairs ready. Concatenating…")
            if not concatenate_segments(segment_pairs, temp_dir, intermediate,
                                        cfg.ffmpeg_path):
                self._log("✗ Concatenation failed.", "error")
                return False

            if not fix_sync_video(intermediate, final_output, cfg.ffmpeg_path, emit=self._emit):
                self._log("✗ Sync fix failed.", "error")
                return False

            self._progress("video", 100, "Done!")
            self._log(f"✅ Final video: {final_output}")
            self._emit("done", {"output": final_output})
            return True

        finally:
            # Clean up temp dir (includes intermediate file)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
