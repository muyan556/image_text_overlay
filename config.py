# -*- coding: utf-8 -*-
"""
Central configuration for the Video Generation Tool.
Load/save to web_config.json in the project directory.
"""
import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "web_config.json")


@dataclass
class TextLayerConfig:
    """Settings for one text layer on the image."""
    pos_x: int = 100
    pos_y: int = 200
    font_size: int = 80
    color: str = "#FFFFFF"
    font_file: str = ""  # filename inside ttf/ dir, empty = auto


@dataclass
class TTSConfig:
    """TTS backend settings."""
    backend: str = "edge_tts"            # "http_api" or "edge_tts"
    api_url: str = "https://api.tjit.net/api/ai/audio/speech"
    api_key: str = "Io4tCBJeWEYBf1DjwITwgGe3pM"
    voice: str = "zh-CN-XiaoxiaoNeural"
    # Source text list used for TTS (index 0-based in text lists, default = text1)
    tts_source_list: int = 0             # 0=text1, 1=text2, 2=text3, 3=text4


@dataclass
class BehaviorConfig:
    """Video behavior settings."""
    repeat_count: int = 1        # How many times to read each item
    silent_multiplier: float = 2.5  # Pause duration after reading = audio_duration * this
    tts_request_delay: float = 0.5  # Seconds between TTS API calls
    output_filename: str = "output_video.mp4"
    temp_dir: str = "temp_segments"
    # Chinese reveal: text3 is only shown starting from this repeat number.
    # 1 = always visible, 2 = hidden on 1st read / shown from 2nd, 0 = never show text3.
    show_text3_from_repeat: int = 1


@dataclass
class AppConfig:
    """Root configuration object."""
    ffmpeg_path: str = r"C:\Users\muyan\scoop\shims\ffmpeg.exe"
    background_image: str = os.path.join(BASE_DIR, "background.png")
    output_dir: str = os.path.join(BASE_DIR, "output")
    tts_output_dir: str = os.path.join(BASE_DIR, "tts_output")
    images_dir: str = os.path.join(BASE_DIR, "images")
    watermark_text: str = "@YourChannel"
    watermark_pos_x: int = 1820
    watermark_pos_y: int = 1000
    watermark_font_size: int = 30
    watermark_color: str = "#FFFFFF"

    tts: TTSConfig = field(default_factory=TTSConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)

    text1: TextLayerConfig = field(default_factory=lambda: TextLayerConfig(
        pos_x=100, pos_y=200, font_size=100, color="#FFFFFF", font_file="MiSans-Heavy.ttf"))
    text2: TextLayerConfig = field(default_factory=lambda: TextLayerConfig(
        pos_x=100, pos_y=430, font_size=65, color="#FFFFFF", font_file="MiSans-ExtraLight.ttf"))
    text3: TextLayerConfig = field(default_factory=lambda: TextLayerConfig(
        pos_x=100, pos_y=600, font_size=45, color="#FFFFFF", font_file="MiSans-Light.ttf"))
    text4: TextLayerConfig = field(default_factory=lambda: TextLayerConfig(
        pos_x=100, pos_y=430, font_size=65, color="#E0E0E0", font_file="MiSans-Normal.ttf"))


def _deep_update(base: dict, update: dict) -> dict:
    """Recursively merge update dict into base dict."""
    for k, v in update.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> AppConfig:
    """Load config from JSON file, falling back to defaults."""
    cfg = AppConfig()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge saved data onto defaults
            base = asdict(cfg)
            merged = _deep_update(base, data)
            # Reconstruct nested dataclasses
            cfg.ffmpeg_path = merged.get("ffmpeg_path", cfg.ffmpeg_path)
            cfg.background_image = merged.get("background_image", cfg.background_image)
            cfg.output_dir = merged.get("output_dir", cfg.output_dir)
            cfg.tts_output_dir = merged.get("tts_output_dir", cfg.tts_output_dir)
            cfg.images_dir = merged.get("images_dir", cfg.images_dir)
            cfg.watermark_text = merged.get("watermark_text", cfg.watermark_text)
            cfg.watermark_pos_x = merged.get("watermark_pos_x", cfg.watermark_pos_x)
            cfg.watermark_pos_y = merged.get("watermark_pos_y", cfg.watermark_pos_y)
            cfg.watermark_font_size = merged.get("watermark_font_size", cfg.watermark_font_size)
            cfg.watermark_color = merged.get("watermark_color", cfg.watermark_color)

            def _layer(d, default):
                return TextLayerConfig(**{k: d.get(k, getattr(default, k))
                                         for k in TextLayerConfig.__dataclass_fields__})
            def _tts(d):
                return TTSConfig(**{k: d.get(k, getattr(TTSConfig(), k))
                                    for k in TTSConfig.__dataclass_fields__})
            def _behavior(d):
                return BehaviorConfig(**{k: d.get(k, getattr(BehaviorConfig(), k))
                                         for k in BehaviorConfig.__dataclass_fields__})

            if "tts" in merged:
                cfg.tts = _tts(merged["tts"])
            if "behavior" in merged:
                cfg.behavior = _behavior(merged["behavior"])
            if "text1" in merged:
                cfg.text1 = _layer(merged["text1"], cfg.text1)
            if "text2" in merged:
                cfg.text2 = _layer(merged["text2"], cfg.text2)
            if "text3" in merged:
                cfg.text3 = _layer(merged["text3"], cfg.text3)
            if "text4" in merged:
                cfg.text4 = _layer(merged["text4"], cfg.text4)
        except Exception as e:
            print(f"[Config] Failed to load config: {e}, using defaults.")
    return cfg


def save_config(cfg: AppConfig) -> None:
    """Save config to JSON file."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2, ensure_ascii=False)


def config_to_dict(cfg: AppConfig) -> dict:
    return asdict(cfg)
