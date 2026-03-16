#!/usr/bin/env python3
"""
图片文本叠加批量生成工具 (增强版 v4)
更新日志：
1. [修复] 文本顺序：先显示 Text4，后显示 Text2。
2. [新增] Text4 自动包裹方括号 []。
3. [修复] 增大右侧边距，解决文字超出图片边缘 2.5 字符的问题。
"""

from PIL import Image, ImageDraw, ImageFont, ImageColor
import os
import argparse
from typing import List, Tuple

class ImageTextOverlay:
    def __init__(self, background_path: str, output_dir: str = "output"):
        try:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            self.script_dir = os.getcwd()

        self.background_path = background_path
        self.output_dir = output_dir
        
        os.makedirs(output_dir, exist_ok=True)
        self.background = Image.open(background_path).convert("RGBA")
        
    def _load_font(self, font_path: str, default_name: str, font_size: int):
        candidates = []
        if font_path and os.path.exists(font_path):
            candidates.append(font_path)
        default_path = os.path.join(self.script_dir, "ttf", default_name)
        candidates.append(default_path)
        candidates.append("C:\\Windows\\Fonts\\msyh.ttc") 
        candidates.append("/System/Library/Fonts/PingFang.ttc") 
        candidates.append("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc") 
        
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                try:
                    return ImageFont.truetype(candidate, font_size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def draw_text_with_wrap(self, draw, text, font, start_pos, align_x_pos, fill, line_spacing=15):
        """
        自动换行绘制文本 (修复版)
        """
        if not text:
            return

        x, y = start_pos
        current_x = x
        img_width = self.background.width
        
        # --- 关键修改：增大右侧安全边距 ---
        # 之前是 50，现在改为 120，确保不会溢出
        right_margin_limit = img_width - 120 
        
        # 获取字高
        bbox = draw.textbbox((0, 0), "测试", font=font)
        char_height = bbox[3] - bbox[1]

        current_line = ""
        
        for char in text:
            # 计算：当前已累积的行长 + 下一个字符的长度
            # 注意：这里计算的是渲染后的绝对宽度
            char_width = draw.textlength(char, font=font)
            line_width = draw.textlength(current_line, font=font)
            
            # 预测加入该字符后的总 X 坐标
            expected_right_edge = current_x + line_width + char_width
            
            # --- 换行判断逻辑 ---
            if expected_right_edge > right_margin_limit:
                # 1. 先把手里存的这一行画上去
                draw.text((current_x, y), current_line, font=font, fill=fill)
                
                # 2. 坐标重置
                current_line = char # 新的一行从当前这个导致溢出的字开始
                y += char_height + line_spacing # Y轴下移
                current_x = align_x_pos # X轴回到对齐点 (通常是 Text2 的起始左边)
            else:
                current_line += char
        
        # 绘制最后剩下的内容
        if current_line:
            draw.text((current_x, y), current_line, font=font, fill=fill)

    def add_text_to_image(
        self,
        text1: str,
        text2: str,
        text3: str,
        text4: str, 
        watermark_text: str,
        current_index: int,
        text1_pos: Tuple[int, int],
        text2_pos: Tuple[int, int],
        text3_pos: Tuple[int, int],
        watermark_bottom_right_pos: Tuple[int, int],
        font_path1: str = None, 
        font_path2: str = None,
        font_path3: str = None,
        font_path4: str = None,
        font_path_watermark: str = None,
        font_size1: int = 100,
        font_size2: int = 65,
        font_size3: int = 45,
        font_size4: int = 65,
        font_size_watermark: int = 30,
        text_color1: str = "white",
        text_color2: str = "white",
        text_color3: str = "white",
        text_color4: str = "white",
        watermark_color: str = "white"
    ) -> Image.Image:
        
        img = self.background.copy()
        draw = ImageDraw.Draw(img)
        
        # --- 字体加载 ---
        font1 = self._load_font(font_path1, "MiSans-Heavy.ttf", font_size1)
        font2 = self._load_font(font_path2, "MiSans-ExtraLight.ttf", font_size2)
        font3 = self._load_font(font_path3, "MiSans-Light.ttf", font_size3)
        font4 = self._load_font(font_path4, "MiSans-Normal.ttf", font_size4) 
        font_watermark = self._load_font(font_path_watermark, "MiSans-Normal.ttf", font_size_watermark)
        
        # --- 1. 绘制 Text1, Text3 (固定位置) ---
        draw.text(text1_pos, text1, fill=text_color1, font=font1)
        draw.text(text3_pos, text3, fill=text_color3, font=font3)
        
        # --- 2. 绘制组合逻辑: [Text4] + Text2 ---
        
        # 定义起始坐标 (使用原来 Text2 的位置作为这一行的起点)
        cursor_x, cursor_y = text2_pos
        
        # Step A: 绘制 Text4 (如果有)
        if text4:
            # 自动添加方括号
            text4_display = f"[{text4}]"
            
            # 绘制 Text4
            draw.text((cursor_x, cursor_y), text4_display, fill=text_color4, font=font4)
            
            # 计算 Text4 占用的宽度
            text4_width = draw.textlength(text4_display, font=font4)
            
            # 更新游标位置：Text4宽度 + 间距 (20px)
            cursor_x += text4_width + 20
            
        # Step B: 绘制 Text2 (紧跟在 Text4 后面，或者没有 Text4 就直接开始)
        if text2:
            self.draw_text_with_wrap(
                draw=draw,
                text=text2,
                font=font2,
                start_pos=(cursor_x, cursor_y), # 从 Text4 后面开始画
                align_x_pos=text2_pos[0],       # 换行后，对齐到该行的最左侧 (即 text2_pos 的 X)
                fill=text_color2,
                line_spacing=15
            )

        # --- 3. 水印与序号逻辑 ---
        index_text = f"{current_index}"
        bbox_wm = draw.textbbox((0, 0), watermark_text, font=font_watermark)
        wm_width, wm_height = bbox_wm[2] - bbox_wm[0], bbox_wm[3] - bbox_wm[1]
        
        watermark_x = watermark_bottom_right_pos[0] - wm_width
        watermark_y = watermark_bottom_right_pos[1] - wm_height
        
        bbox_index = draw.textbbox((0, 0), index_text, font=font_watermark)
        index_width, index_height = bbox_index[2] - bbox_index[0], bbox_index[3] - bbox_index[1]

        index_x = watermark_x + wm_width - index_width
        index_y = watermark_y - index_height - 10
        
        watermark_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw_wm = ImageDraw.Draw(watermark_layer)
        wm_rgb = ImageColor.getrgb(watermark_color)
        wm_rgba_transparent = wm_rgb + (115,) 
        
        draw_wm.text((watermark_x, watermark_y), watermark_text, fill=wm_rgba_transparent, font=font_watermark)
        img = Image.alpha_composite(img, watermark_layer)
        
        draw = ImageDraw.Draw(img)
        index_rgba_opaque = wm_rgb + (255,) 
        draw.text((index_x, index_y), index_text, fill=index_rgba_opaque, font=font_watermark)
        
        return img

    def batch_generate(
        self,
        text_list1: List[str],
        text_list2: List[str],
        text_list3: List[str],
        text_list4: List[str],
        watermark_text: str,
        text1_pos: Tuple[int, int],
        text2_pos: Tuple[int, int],
        text3_pos: Tuple[int, int],
        watermark_bottom_right_pos: Tuple[int, int],
        **kwargs
    ) -> List[str]:
        output_paths = []
        max_len = max(len(text_list1), len(text_list2), len(text_list3), len(text_list4))
        
        text_list1 += [""] * (max_len - len(text_list1))
        text_list2 += [""] * (max_len - len(text_list2))
        text_list3 += [""] * (max_len - len(text_list3))
        text_list4 += [""] * (max_len - len(text_list4))
        
        for i, (t1, t2, t3, t4) in enumerate(zip(text_list1, text_list2, text_list3, text_list4), start=1):
            img = self.add_text_to_image(
                text1=t1, text2=t2, text3=t3, text4=t4,
                watermark_text=watermark_text, current_index=i,
                text1_pos=text1_pos, text2_pos=text2_pos, text3_pos=text3_pos,
                watermark_bottom_right_pos=watermark_bottom_right_pos,
                **kwargs
            )
            output_path = os.path.join(self.output_dir, f"{i}.png")
            img.save(output_path)
            output_paths.append(output_path)
        return output_paths

def load_text_from_file(file_path: str) -> List[str]:
    if not file_path or not os.path.exists(file_path): return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('background')
    parser.add_argument('text1_file')
    parser.add_argument('text2_file')
    parser.add_argument('text3_file')
    parser.add_argument('text4_file', nargs='?', default=None)
    
    # 坐标与参数
    parser.add_argument('--text1-pos', type=str, default='100,200')
    parser.add_argument('--text2-pos', type=str, default='100,400')
    parser.add_argument('--text3-pos', type=str, default='100,600')
    parser.add_argument('--watermark-pos', type=str, default='1820,1000')
    parser.add_argument('--watermark-text', type=str, default='@您的B站账号')
    
    # 字体路径
    parser.add_argument('--font-path1', type=str, default=None)
    parser.add_argument('--font-path2', type=str, default=None)
    parser.add_argument('--font-path3', type=str, default=None)
    parser.add_argument('--font-path4', type=str, default=None)
    parser.add_argument('--font-path-watermark', type=str, default=None)
    
    # 字体大小
    parser.add_argument('--font-size1', type=int, default=100)
    parser.add_argument('--font-size2', type=int, default=80)
    parser.add_argument('--font-size3', type=int, default=60)
    parser.add_argument('--font-size4', type=int, default=65)
    parser.add_argument('--font-size-watermark', type=int, default=30)
    
    # 颜色
    parser.add_argument('--color1', type=str, default='white')
    parser.add_argument('--color2', type=str, default='white')
    parser.add_argument('--color3', type=str, default='white')
    parser.add_argument('--color4', type=str, default='#E0E0E0') 
    parser.add_argument('--watermark-color', type=str, default='white')
    
    parser.add_argument('--output-dir', type=str, default='images')
    
    args = parser.parse_args()
    
    processor = ImageTextOverlay(args.background, args.output_dir)
    processor.batch_generate(
        text_list1=load_text_from_file(args.text1_file),
        text_list2=load_text_from_file(args.text2_file),
        text_list3=load_text_from_file(args.text3_file),
        text_list4=load_text_from_file(args.text4_file) if args.text4_file else [],
        watermark_text=args.watermark_text,
        text1_pos=tuple(map(int, args.text1_pos.split(','))),
        text2_pos=tuple(map(int, args.text2_pos.split(','))),
        text3_pos=tuple(map(int, args.text3_pos.split(','))),
        watermark_bottom_right_pos=tuple(map(int, args.watermark_pos.split(','))),
        font_path1=args.font_path1, font_path2=args.font_path2,
        font_path3=args.font_path3, font_path4=args.font_path4,
        font_path_watermark=args.font_path_watermark,
        font_size1=args.font_size1, font_size2=args.font_size2,
        font_size3=args.font_size3, font_size4=args.font_size4,
        font_size_watermark=args.font_size_watermark,
        text_color1=args.color1, text_color2=args.color2,
        text_color3=args.color3, text_color4=args.color4,
        watermark_color=args.watermark_color
    )
    print(f"✓ 处理完成，已修复溢出问题。")

if __name__ == "__main__":
    main()