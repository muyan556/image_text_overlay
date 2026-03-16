import os
import json
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
        self.output_dir = os.path.dirname(self.cfg['project']['output_filename'])
        
        for d in [self.temp_dir, self.output_dir]:
            os.makedirs(d, exist_ok=True)

    def _hex_to_rgba(self, hex_color, opacity):
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (r, g, b, int(255 * opacity))

    def _get_font(self, font_name, size):
        font_dir = self.cfg['paths'].get('font_dir', 'ttf')
        candidates = [
            os.path.join(font_dir, font_name), font_name,                         
            "C:\\Windows\\Fonts\\msyh.ttc", "/System/Library/Fonts/PingFang.ttc" 
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                try: return ImageFont.truetype(candidate, size)
                except: continue
        return ImageFont.load_default()

    def generate_image(self, t1, t2, t3, t4, index, show_t3=True, preview_path=None):
        bg_path = self.cfg['project']['background_image']
        if not os.path.exists(bg_path):
            img = Image.new("RGBA", (1920, 1080), (200, 200, 200, 255))
        else:
            img = Image.open(bg_path).convert("RGBA")
            
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        layout = self.cfg['layout']
        texts = {
            'text1': (t1, layout.get('text1')),
            'text2': (t2, layout.get('text2')),
            'text3': (t3 if show_t3 else "", layout.get('text3')),
            'text4': (f"[{t4}]" if t4 else "", layout.get('text4'))
        }

        for key, config in texts.items():
            text, style = config
            if not text or not style: continue
            font = self._get_font(style['font'], style['size'])
            color = self._hex_to_rgba(style['color'], style['opacity'])
            draw.text((style['x'], style['y']), text, fill=color, font=font)

        wm = layout.get('watermark', {})
        if wm and wm.get('text'):
            wm_font = self._get_font(wm.get('font', 'msyh.ttc'), wm.get('size', 30))
            wm_color = self._hex_to_rgba(wm.get('color', '#000000'), wm.get('opacity', 0.5))
            draw.text((wm.get('x', 1800), wm.get('y', 1000)), wm.get('text'), fill=wm_color, font=wm_font)

        seq = layout.get('sequence', {})
        if seq and str(index).isdigit():
            seq_font = self._get_font(seq.get('font', 'msyh.ttc'), seq.get('size', 40))
            seq_color = self._hex_to_rgba(seq.get('color', '#000000'), seq.get('opacity', 0.8))
            draw.text((seq.get('x', 50), seq.get('y', 50)), str(index), fill=seq_color, font=seq_font)

        final_img = Image.alpha_composite(img, overlay).convert("RGB")
        out_path = preview_path or os.path.join(self.temp_dir, f"img_{index}_{'with3' if show_t3 else 'no3'}.png")
        final_img.save(out_path)
        return out_path

    def generate_tts(self, text, index):
        out_path = os.path.join(self.temp_dir, f"audio_{index}.mp3")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100: return out_path
        subprocess.run(["edge-tts", "--voice", self.cfg['tts']['voice'], "--text", text, "--write-media", out_path], capture_output=True)
        return out_path

    def get_audio_duration(self, audio_path):
        ffprobe = self.ffmpeg.replace('ffmpeg', 'ffprobe')
        cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        try: return float(subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip())
        except: return 3.0

    def create_video_segment(self, img_path, audio_path, out_path, target_dur):
        if os.path.exists(out_path): return True 
        
        # 强制输出为标准 MPEG-TS 流，完美适配 M3U8
        cmd = [
            self.ffmpeg, "-y", "-loop", "1", "-framerate", "25",
            "-i", img_path, "-i", audio_path,
            "-filter_complex", "[1:a]aresample=44100,aformat=channel_layouts=stereo,apad[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-r", "25", 
            "-pix_fmt", "yuv420p", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{target_dur:.3f}", 
            "-f", "mpegts", 
            out_path
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0: self.emit("error", f"FFmpeg Error: {res.stderr.decode('utf-8')[-200:]}")
        return res.returncode == 0

    def build_video(self):
        self.load_config()
        self.emit("log", "Starting HLS Streaming Pipeline...")
        
        t1, t2 = self.cfg['texts']['text1'], self.cfg['texts']['text2']
        t3, t4 = self.cfg['texts']['text3'], self.cfg['texts']['text4']
        max_items = max(len(t1), len(t2), len(t3), len(t4))
        
        def pad(lst): return lst + [""] * (max_items - len(lst))
        t1, t2, t3, t4 = pad(t1), pad(t2), pad(t3), pad(t4)

        repeat = self.cfg['behavior']['repeat_count']
        show_t3_from = self.cfg['behavior']['show_text3_from_rep']
        dur_mult = self.cfg['behavior']['duration_multiplier']

        segments = []
        max_duration = 0

        for i in range(max_items):
            idx = i + 1
            self.emit("progress", {"pct": int((idx/max_items)*85), "msg": f"正在生成视频流切片 ({idx}/{max_items})..."})
            
            img_no3 = self.generate_image(t1[i], t2[i], t3[i], t4[i], idx, show_t3=False)
            img_with3 = self.generate_image(t1[i], t2[i], t3[i], t4[i], idx, show_t3=True)
            
            tts_text = locals().get(self.cfg['tts']['source_list'], t1)[i] 
            audio_path = self.generate_tts(tts_text, idx)
            target_dur = self.get_audio_duration(audio_path) * dur_mult
            if target_dur > max_duration: max_duration = target_dur

            for rep in range(1, repeat + 1):
                # 直接将生成的 .ts 文件保存到 static/output 目录下
                ts_filename = f"item{idx}_rep{rep}.ts"
                seg_out = os.path.join(self.output_dir, ts_filename)
                
                current_img = img_with3 if rep >= show_t3_from else img_no3
                self.create_video_segment(current_img, audio_path, seg_out, target_dur)
                segments.append((ts_filename, target_dur))

        self.emit("progress", {"pct": 95, "msg": "正在生成 M3U8 播放列表 (0耗时)..."})
        
        # 抛弃缓慢的合并过程，直接写入 M3U8 文本配置
        m3u8_path = self.cfg['project']['output_filename']
        with open(m3u8_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            f.write("#EXT-X-VERSION:3\n")
            f.write(f"#EXT-X-TARGETDURATION:{int(max_duration) + 1}\n")
            f.write("#EXT-X-MEDIA-SEQUENCE:0\n")
            f.write("#EXT-X-PLAYLIST-TYPE:VOD\n")
            
            for ts_filename, dur in segments:
                f.write("#EXT-X-DISCONTINUITY\n") # 关键！解决时间戳断层
                f.write(f"#EXTINF:{dur:.3f},\n")
                f.write(f"{ts_filename}\n")
                
            f.write("#EXT-X-ENDLIST\n")

        self.emit("progress", {"pct": 100, "msg": "构建完成！"})
        self.emit("done", m3u8_path)