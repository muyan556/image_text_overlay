# -*- coding: utf-8 -*-
"""
Flask Web Server for the Video Generation Tool.
Run with: python app.py
Then open http://localhost:5000 in your browser.
"""
import base64
import json
import os
import queue
import threading
import uuid
from dataclasses import asdict
from typing import Optional, Dict

from flask import Flask, Response, jsonify, render_template, request, send_file

from config import AppConfig, load_config, save_config, config_to_dict
from preview_generator import generate_preview
from video_pipeline import VideoPipeline

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

# ── In-memory job store ──────────────────────────────────────────────────────
_jobs: Dict[str, dict] = {}  # job_id -> {queue, thread, status, output}
_jobs_lock = threading.Lock()


def _get_or_create_job(job_id: str) -> dict:
    with _jobs_lock:
        if job_id not in _jobs:
            _jobs[job_id] = {
                "q": queue.Queue(),
                "status": "pending",
                "output": None,
            }
        return _jobs[job_id]


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    cfg = load_config()
    return jsonify(config_to_dict(cfg))


@app.route("/api/config", methods=["POST"])
def set_config():
    data = request.get_json(force=True)
    cfg = load_config()
    d = asdict(cfg)

    def deep_merge(base, overlay):
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                deep_merge(base[k], v)
            else:
                base[k] = v

    deep_merge(d, data)
    # Reconstruct from merged dict
    from config import (TextLayerConfig, TTSConfig, BehaviorConfig)
    new_cfg = AppConfig()
    new_cfg.ffmpeg_path = d.get("ffmpeg_path", new_cfg.ffmpeg_path)
    new_cfg.background_image = d.get("background_image", new_cfg.background_image)
    new_cfg.output_dir = d.get("output_dir", new_cfg.output_dir)
    new_cfg.tts_output_dir = d.get("tts_output_dir", new_cfg.tts_output_dir)
    new_cfg.images_dir = d.get("images_dir", new_cfg.images_dir)
    new_cfg.watermark_text = d.get("watermark_text", new_cfg.watermark_text)
    new_cfg.watermark_pos_x = d.get("watermark_pos_x", new_cfg.watermark_pos_x)
    new_cfg.watermark_pos_y = d.get("watermark_pos_y", new_cfg.watermark_pos_y)
    new_cfg.watermark_font_size = d.get("watermark_font_size", new_cfg.watermark_font_size)
    new_cfg.watermark_color = d.get("watermark_color", new_cfg.watermark_color)

    for attr, cls in [("tts", TTSConfig), ("behavior", BehaviorConfig),
                      ("text1", TextLayerConfig), ("text2", TextLayerConfig),
                      ("text3", TextLayerConfig), ("text4", TextLayerConfig)]:
        src = d.get(attr, {})
        obj = cls()
        for k in cls.__dataclass_fields__:
            if k in src:
                setattr(obj, k, src[k])
        setattr(new_cfg, attr, obj)

    save_config(new_cfg)
    return jsonify({"ok": True})


@app.route("/api/preview", methods=["POST"])
def preview():
    """Generate a preview JPEG from current settings + first-row sample texts."""
    data = request.get_json(force=True)
    cfg = load_config()

    # Apply any inline overrides from UI
    _apply_inline_config(cfg, data.get("config", {}))

    sample = data.get("sample_texts", ["", "", "", ""])
    while len(sample) < 4:
        sample.append("")

    # Which repeat to simulate (1-based), so preview can show/hide Chinese
    preview_repeat = int(data.get("preview_repeat", 1))

    try:
        png_bytes = generate_preview(cfg, sample, preview_repeat=preview_repeat)
        b64 = base64.b64encode(png_bytes).decode()
        return jsonify({"ok": True, "image": b64, "mime": "image/jpeg"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/list-fonts", methods=["GET"])
def list_fonts():
    ttf_dir = os.path.join(BASE_DIR, "ttf")
    fonts = []
    if os.path.isdir(ttf_dir):
        fonts = [f for f in os.listdir(ttf_dir) if f.lower().endswith((".ttf", ".ttc", ".otf"))]
    return jsonify({"fonts": sorted(fonts)})


@app.route("/api/generate", methods=["POST"])
def generate():
    """Start a background pipeline job. Returns job_id."""
    data = request.get_json(force=True)
    cfg = load_config()
    _apply_inline_config(cfg, data.get("config", {}))

    text_lists = data.get("text_lists", [[], [], [], []])
    while len(text_lists) < 4:
        text_lists.append([])

    output_path = os.path.join(cfg.output_dir, cfg.behavior.output_filename)

    job_id = str(uuid.uuid4())
    job = _get_or_create_job(job_id)

    def emit(event, payload):
        job["q"].put(json.dumps({"event": event, "data": payload}))
        if event == "done":
            job["status"] = "done"
            job["output"] = payload.get("output")
        elif event == "log" and payload.get("level") == "error":
            pass  # keep running

    def run_pipeline():
        try:
            pipeline = VideoPipeline(cfg, emit=emit)
            pipeline.run(text_lists=text_lists, output_path=output_path)
        except Exception as exc:
            emit("log", {"level": "error", "msg": f"Pipeline crashed: {exc}"})
            emit("done", {"output": None, "error": str(exc)})
        finally:
            job["q"].put(None)  # sentinel

    t = threading.Thread(target=run_pipeline, daemon=True)
    t.start()
    job["thread"] = t

    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/resume", methods=["POST"])
def resume():
    """
    Resume from a previous failed/interrupted run.
    Skips TTS (reuses tts_output/*.mp3) and image generation (reuses images/*.png).
    Jumps straight to video assembly stage.
    """
    data = request.get_json(force=True)
    cfg = load_config()
    _apply_inline_config(cfg, data.get("config", {}))

    text_lists = data.get("text_lists", [[], [], [], []])
    while len(text_lists) < 4:
        text_lists.append([])

    output_path = os.path.join(cfg.output_dir, cfg.behavior.output_filename)

    job_id = str(uuid.uuid4())
    job = _get_or_create_job(job_id)

    def emit(event, payload):
        job["q"].put(json.dumps({"event": event, "data": payload}))
        if event == "done":
            job["status"] = "done"
            job["output"] = payload.get("output")

    def run_resume():
        try:
            pipeline = VideoPipeline(cfg, emit=emit)
            pipeline.run(
                text_lists=text_lists,
                output_path=output_path,
                skip_tts=True,       # reuse existing mp3 files
                skip_images=True,    # reuse existing png files
            )
        except Exception as exc:
            emit("log", {"level": "error", "msg": f"Resume crashed: {exc}"})
            emit("done", {"output": None, "error": str(exc)})
        finally:
            job["q"].put(None)

    t = threading.Thread(target=run_resume, daemon=True)
    t.start()
    job["thread"] = t

    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/progress/<job_id>", methods=["GET"])
def progress(job_id: str):
    """SSE stream of progress events for a given job."""
    job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "unknown job"}), 404

    def stream():
        q = job["q"]
        while True:
            try:
                msg = q.get(timeout=30)
            except queue.Empty:
                yield "data: {\"event\":\"ping\"}\n\n"
                continue
            if msg is None:
                yield "data: {\"event\":\"end\"}\n\n"
                break
            yield f"data: {msg}\n\n"

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/api/upload-background", methods=["POST"])
def upload_background():
    """Upload a new background image."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    f = request.files["file"]
    dest = os.path.join(BASE_DIR, "background.png")
    f.save(dest)
    return jsonify({"ok": True, "path": dest})


# ── Helpers ──────────────────────────────────────────────────────────────────
def _apply_inline_config(cfg: AppConfig, overrides: dict):
    """Apply a flat/nested overrides dict onto a loaded config object."""
    if not overrides:
        return
    from config import TextLayerConfig, TTSConfig, BehaviorConfig

    simple_fields = [
        "ffmpeg_path", "background_image", "output_dir", "tts_output_dir",
        "images_dir", "watermark_text", "watermark_pos_x", "watermark_pos_y",
        "watermark_font_size", "watermark_color",
    ]
    for f in simple_fields:
        if f in overrides:
            setattr(cfg, f, overrides[f])

    def _merge_sub(obj, src_dict):
        for k in obj.__class__.__dataclass_fields__:
            if k in src_dict:
                setattr(obj, k, src_dict[k])

    for attr in ["tts", "behavior", "text1", "text2", "text3", "text4"]:
        if attr in overrides and isinstance(overrides[attr], dict):
            _merge_sub(getattr(cfg, attr), overrides[attr])


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  TTS Video Generation Tool — Web UI")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
