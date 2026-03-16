import os
import json
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

class VideoEngine:
    def __init__(self, config_path="config.json", emit=None):
        self.config_path = config_path
        self.emit = emit or (lambda t, d: print(f"[{t}] {d}"))
        self.load_config()

    def load_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.cfg = json.load(f)
        
        self.temp_dir = self.cfg['paths'].get('temp_dir', 'temp')
        self.ffmpeg = self.cfg['paths'].get('ffmpeg_path', 'ffmpeg')
        for d in [self.temp_dir, os.path.dirname(self.cfg['project']['output_filename'])]:
            os.makedirs(d, exist_ok=True)

    def _hex_to_rgba(self, hex_color, opacity):
        """支持十六进制颜色 + 透明度转换为 RGBA"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (r, g, b, int(255 * opacity))

    def _get_font(self, font_name, size):
        font_dir = self.cfg['paths'].get('font_dir', 'ttf')
        candidates = [
            os.path.join(font_dir, font_name), 
            font_name,                         
            "C:\\Windows\\Fonts\\msyh.ttc",    
            "/System/Library/Fonts/PingFang.ttc" 
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                try: return ImageFont.truetype(candidate, size)
                except Exception: continue
        return ImageFont.load_default()

    def generate_image(self, t1, t2, t3, t4, index, show_t3=True, preview_path=None):
        """生成带透明度、自定义字体的单张静态画面"""
        bg_path = self.cfg['project']['background_image']
        if not os.path.exists(bg_path):
            img = Image.new("RGBA", (1920, 1080), (200, 200, 200, 255))
        else:
            img = Image.open(bg_path).convert("RGBA")
            
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        layout = self.cfg['layout']
        texts = {
            'text1': (t1, layout['text1']),
            'text2': (t2, layout['text2']),
            'text3': (t3 if show_t3 else "", layout['text3']),
            'text4': (f"[{t4}]" if t4 else "", layout['text4'])
        }

        for key, (text, style) in texts.items():
            if not text: continue
            font = self._get_font(style['font'], style['size'])
            color = self._hex_to_rgba(style['color'], style['opacity'])
            draw.text((style['x'], style['y']), text, fill=color, font=font)

        wm = layout['watermark']
        if wm.get('text'):
            wm_font = self._get_font(wm.get('font', 'msyh.ttc'), wm['size'])
            wm_color = self._hex_to_rgba(wm['color'], wm['opacity'])
            draw.text((wm['x'], wm['y']), wm['text'], fill=wm_color, font=wm_font)

        final_img = Image.alpha_composite(img, overlay).convert("RGB")
        out_path = preview_path or os.path.join(self.temp_dir, f"img_{index}_{'with3' if show_t3 else 'no3'}.png")
        final_img.save(out_path)
        return out_path

    def generate_tts(self, text, index):
        """调用 Edge TTS"""
        out_path = os.path.join(self.temp_dir, f"audio_{index}.mp3")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            return out_path
        
        voice = self.cfg['tts']['voice']
        cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", out_path]
        subprocess.run(cmd, capture_output=True)
        return out_path

    def get_audio_duration(self, audio_path):
        ffprobe = self.ffmpeg.replace('ffmpeg', 'ffprobe')
        cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", 
               "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return float(res.stdout.strip())
        except: return 3.0

    def create_video_segment(self, img_path, audio_path, out_path, target_dur):
        """完美无延迟片段合成方案：图片+音频，音频结束后自动apap静音补齐到target_dur"""
        if os.path.exists(out_path): return True 
        
        cmd = [
            self.ffmpeg, "-y", "-loop", "1", "-framerate", "25",
            "-i", img_path, "-i", audio_path,
            "-filter_complex", "[1:a]aresample=44100,aformat=channel_layouts=stereo,apad[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-r", "25", "-video_track_timescale", "90000",
            "-pix_fmt", "yuv420p", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{target_dur:.3f}", out_path
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0:
            self.emit("error", f"FFmpeg Error: {res.stderr.decode('utf-8')[-200:]}")
        return res.returncode == 0

    def build_video(self):
        """执行完整工作流"""
        self.load_config()
        self.emit("log", "Starting video build pipeline...")
        
        t1, t2 = self.cfg['texts']['text1'], self.cfg['texts']['text2']
        t3, t4 = self.cfg['texts']['text3'], self.cfg['texts']['text4']
        max_items = max(len(t1), len(t2), len(t3), len(t4))
        
        def pad(lst): return lst + [""] * (max_items - len(lst))
        t1, t2, t3, t4 = pad(t1), pad(t2), pad(t3), pad(t4)

        repeat = self.cfg['behavior']['repeat_count']
        show_t3_from = self.cfg['behavior']['show_text3_from_rep']
        dur_mult = self.cfg['behavior']['duration_multiplier']
        seg_template = self.cfg['behavior']['segment_name_template']

        segments = []
        for i in range(max_items):
            idx = i + 1
            self.emit("progress", {"pct": int((idx/max_items)*50), "msg": f"Generating assets for item {idx}..."})
            
            img_no3 = self.generate_image(t1[i], t2[i], t3[i], t4[i], idx, show_t3=False)
            img_with3 = self.generate_image(t1[i], t2[i], t3[i], t4[i], idx, show_t3=True)
            
            # 判断以哪个文本作为发音源
            src_list_name = self.cfg['tts']['source_list']
            tts_text = locals().get(src_list_name, t1)[i] 
            audio_path = self.generate_tts(tts_text, idx)
            
            target_dur = self.get_audio_duration(audio_path) * dur_mult

            for rep in range(1, repeat + 1):
                seg_name = seg_template.format(index=idx, rep=rep)
                seg_out = os.path.join(self.temp_dir, seg_name)
                
                show_chinese = rep >= show_t3_from
                current_img = img_with3 if show_chinese else img_no3
                
                self.create_video_segment(current_img, audio_path, seg_out, target_dur)
                segments.append(seg_out)

        self.emit("progress", {"pct": 80, "msg": "Concatenating standard segments..."})
        list_path = os.path.join(self.temp_dir, "list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for s in segments: f.write(f"file '{os.path.abspath(s).replace('\\', '/')}'\n")

        final_out = self.cfg['project']['output_filename']
        subprocess.run([
            self.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path, 
            "-c", "copy", "-movflags", "+faststart", final_out
        ])
        
        self.emit("progress", {"pct": 100, "msg": "Done!"})
        self.emit("done", final_out)