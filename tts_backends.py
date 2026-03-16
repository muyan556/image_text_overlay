# -*- coding: utf-8 -*-
"""
Pluggable TTS Backends.
Supports:
  - HttpAPITTSBackend  (default, uses tjit.net-style REST GET API)
  - EdgeTTSBackend     (edge-tts)
"""
import os
import re
import time
import requests
from abc import ABC, abstractmethod
from typing import Optional, List
from urllib.parse import urlencode, unquote


class BaseTTSBackend(ABC):
    """Abstract TTS backend."""

    @abstractmethod
    def generate(self, text: str, output_path: str) -> bool:
        """Synthesize text and save to output_path. Returns True on success."""
        ...

    def batch_generate(self, texts: list[str], output_dir: str,
                       prefix: str = "", delay: float = 0.5,
                       progress_cb=None) -> dict:
        """
        Batch-generate audio files.
        output_dir: directory to save files
        prefix: filename prefix before the index number
        delay: seconds between requests
        progress_cb: callable(index, total, text, success)
        Returns {'success': [...], 'failed': [...]}
        """
        os.makedirs(output_dir, exist_ok=True)
        results = {"success": [], "failed": []}
        total = len(texts)

        for i, text in enumerate(texts, 1):
            if not text.strip():
                results["success"].append({"index": i, "text": text, "path": None})
                continue
            path = os.path.join(output_dir, f"{prefix}{i}.mp3")
            ok = self.generate(text, path)
            if ok:
                results["success"].append({"index": i, "text": text, "path": path})
            else:
                results["failed"].append({"index": i, "text": text})
            if progress_cb:
                progress_cb(i, total, text, ok)
            if i < total:
                time.sleep(delay)

        return results


# ---------------------------------------------------------------------------
# HTTP API Backend  (tjit.net style)
# ---------------------------------------------------------------------------
class HttpAPITTSBackend(BaseTTSBackend):
    """TTS via HTTP GET API that returns audio stream or HTML redirect."""

    def __init__(self, api_url: str, api_key: str, voice: str,
                 speed: float = 1.0, model: str = "tts-1-hd"):
        self.api_url = api_url
        self.api_key = api_key
        self.voice = voice
        self.speed = speed
        self.model = model
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "*/*",
        })

    def _build_url(self, text: str) -> str:
        params = {
            "key": self.api_key,
            "text": text,
            "voice": self.voice,
            "format": "mp3",
            "speed": str(self.speed),
            "model": self.model,
            "type": "speech",
        }
        return f"{self.api_url}?{urlencode(params)}"

    def _download(self, url: str, output_path: str, depth: int = 0) -> bool:
        if depth > 3:
            return False
        try:
            resp = self.session.get(url, timeout=90, stream=True)
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "").lower()

            if "audio" in ct or "mpeg" in ct or "octet-stream" in ct:
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if chunk:
                            f.write(chunk)
                return os.path.getsize(output_path) > 100

            elif "text/html" in ct:
                m = re.search(r'src="([^"]+)"', resp.text)
                if m:
                    real_url = unquote(m.group(1))
                    return self._download(real_url, output_path, depth + 1)
                return False

            elif "application/json" in ct:
                print(f"  [TTS] API JSON error: {resp.json()}")
                return False
            else:
                print(f"  [TTS] Unknown content-type: {ct}")
                return False
        except Exception as e:
            print(f"  [TTS] Download error: {e}")
            return False

    def generate(self, text: str, output_path: str) -> bool:
        url = self._build_url(text)
        return self._download(url, output_path)





# ---------------------------------------------------------------------------
# Edge TTS Backend
# ---------------------------------------------------------------------------
class EdgeTTSBackend(BaseTTSBackend):
    """TTS via edge-tts (free Azure voices)."""

    def __init__(self, voice: str):
        self.voice = voice

    def generate(self, text: str, output_path: str) -> bool:
        import subprocess
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            cmd = ["edge-tts", "--voice", self.voice, "--text", text, "--write-media", output_path]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=False)
            if r.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return True
            else:
                print(f"  [Edge TTS] Failed: {r.stderr}")
                return False
        except Exception as e:
            print(f"  [Edge TTS] Error: {e}")
            return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_tts_backend(cfg) -> BaseTTSBackend:
    """Create and return the TTS backend specified in config."""
    if cfg.tts.backend == "edge_tts":
        return EdgeTTSBackend(voice=cfg.tts.voice)
    else:  # "http_api"
        if "tjit.net" in cfg.tts.api_url:
            print("  [TTS] tjit.net API is known to be offline. Falling back to edge-tts.")
            return EdgeTTSBackend(voice=cfg.tts.voice)
        return HttpAPITTSBackend(
            api_url=cfg.tts.api_url,
            api_key=cfg.tts.api_key,
            voice=cfg.tts.voice,
        )
