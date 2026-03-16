#!/usr/bin/env python3
"""
TTS 批量生成工具 (Edge TTS 版)
支持生成 MP3 格式音频

用法:
  python tts_generator.py "文本内容"
  python tts_generator.py --file (读取脚本目录下的 text1.txt)
"""

import os
import sys
import subprocess
from os.path import abspath, dirname, join
from typing import List


class TTSGenerator:
    """Edge TTS 音频生成器"""
    
    def __init__(self):
        """初始化音频配置"""
        self.voice = "en-US-AvaMultilingualNeural"

    def generate_to_file(self, text: str, output_path: str) -> bool:
        """调用 Edge TTS 生成音频文件"""
        try:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            print(f"  正在合成: {text[:30]}...")
            cmd = [
                "edge-tts",
                "--voice", self.voice,
                "--text", text,
                "--write-media", output_path
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=False)

            if r.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                file_size = os.path.getsize(output_path)
                print(f"  ✓ 成功保存到: {output_path} ({file_size} 字节)")
                return True
            else:
                print(f"  ✗ 合成失败: {r.stderr}")
                return False
                
        except Exception as e:
            print(f"  ✗ 发生异常: {str(e)}")
            return False
            
        return False
    
    def batch_generate(self, texts: List[str], output_dir: str = "tts_output", prefix: str = ""):
        """批量生成音频文件"""
        os.makedirs(output_dir, exist_ok=True)
        
        results = {'success': [], 'failed': []}
        total = len(texts)
        
        print(f"\n开始批量生成 {total} 个音频文件 (Format: MP3)...")
        print("=" * 60)
        
        for i, text in enumerate(texts, 1):
            if not text.strip():
                continue
                
            output_path = os.path.join(output_dir, f"{prefix}{i}.mp3")
            print(f"\n[{i}/{total}]")
            
            if self.generate_to_file(text, output_path):
                results['success'].append((i, text, output_path))
            else:
                results['failed'].append((i, text))
        
        print("\n" + "=" * 60)
        print(f"批量生成完成！")
        print(f"✓ 成功: {len(results['success'])} 个")
        print(f"✗ 失败: {len(results['failed'])} 个")
        
        if results['failed']:
            print("\n失败的项目:")
            for i, text in results['failed']:
                print(f"  [{i}] {text[:50]}...")


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("TTS 音频生成工具 (Edge TTS 版)")
        print("=" * 60)
        print("\n用法:")
        print('  单个文本: python tts_generator.py "文本内容"')
        print('  批量文本: python tts_generator.py "文本1" "文本2" ...')
        print('  文件导入: python tts_generator.py --file (读取脚本目录下的 text1.txt)')
        print("\n示例:")
        print('  python tts_generator.py "Hello, this is Ava."')
        print('  python tts_generator.py --file')
        print("=" * 60)
        sys.exit(1)
    
    use_file = False
    texts = []
    
    for arg in sys.argv[1:]:
        if arg == '--file':
            use_file = True
        elif arg.startswith('--'):
            pass 
        else:
            texts.append(arg)
            
    if use_file:
        script_dir = dirname(abspath(__file__))
        file_path = join(script_dir, 'text1.txt')
        print(f"尝试从 {file_path} 加载文本...")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_lines = [line.strip() for line in f.readlines() if line.strip()]
                
                if file_lines:
                    print(f"成功加载 {len(file_lines)} 行文本。")
                    texts.extend(file_lines)
                else:
                    print("警告: 文件为空或没有有效文本行。")
            except Exception as e:
                print(f"读取文件失败: {e}")
                sys.exit(1)
        else:
            print(f"错误: 未找到 text1.txt 文件 (应位于 {script_dir})")
            sys.exit(1)
    
    if not texts:
        print("错误: 请提供至少一个文本参数，或使用 --file 加载文件")
        sys.exit(1)
    
    generator = TTSGenerator()
    
    if len(texts) == 1 and not use_file:
        generator.generate_to_file(texts[0], "output.mp3")
    else:
        generator.batch_generate(texts, output_dir="tts_output")

if __name__ == "__main__":
    main()