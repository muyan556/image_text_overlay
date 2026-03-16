# 图片文本叠加批量生成工具

## 功能介绍

这是一个Python脚本工具，可以将文本列表批量叠加到背景图片上，支持固定位置配置，自动生成编号图片（1.png, 2.png, 3.png...）。

**主要特性：**
- 支持批量处理多组文本
- 可自定义文本位置、字体大小、颜色
- 支持中文字体
- 自动按数字顺序命名输出文件
- 灵活的配置参数

## 使用方法

### 基本用法

```bash
python3 image_text_overlay.py <背景图片> <文本1文件> <文本2文件>
```

### 完整示例

```bash
python3 image_text_overlay.py background.png text1.txt text2.txt \
  --text1-pos 150,150 \
  --text2-pos 150,250 \
  --font-path /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc \
  --font-size1 48 \
  --font-size2 32 \
  --color1 "#2C3E50" \
  --color2 "#34495E" \
  --output-dir output
```

## 参数说明

### 必需参数

| 参数 | 说明 |
|------|------|
| `background` | 背景图片路径（支持PNG、JPG等格式） |
| `text1_file` | 文本1列表文件路径（每行一个文本） |
| `text2_file` | 文本2列表文件路径（每行一个文本） |

### 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--text1-pos` | `100,100` | 文本1位置，格式：x,y（像素坐标） |
| `--text2-pos` | `100,200` | 文本2位置，格式：x,y（像素坐标） |
| `--font-path` | 系统默认 | 字体文件路径（.ttf或.ttc文件） |
| `--font-size1` | `40` | 文本1字体大小 |
| `--font-size2` | `40` | 文本2字体大小 |
| `--color1` | `black` | 文本1颜色（支持颜色名或十六进制） |
| `--color2` | `black` | 文本2颜色（支持颜色名或十六进制） |
| `--output-dir` | `output` | 输出目录路径 |

## 文件准备

### 1. 准备背景图片

任何PNG、JPG等格式的图片都可以作为背景图片。

### 2. 准备文本列表文件

创建两个文本文件，每行一个文本内容。例如：

**text1.txt**（标题列表）：
```
标题一
标题二
标题三
标题四
标题五
```

**text2.txt**（描述列表）：
```
这是第一段描述文字
这是第二段描述文字
这是第三段描述文字
这是第四段描述文字
这是第五段描述文字
```

脚本会自动将两个列表配对，生成对应数量的图片。

## 字体配置

### Linux系统常用中文字体路径

```bash
# Noto CJK字体（推荐）
/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc

# 文泉驿字体
/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc

# 思源黑体
/usr/share/fonts/opentype/source-han-sans/SourceHanSansCN-Regular.otf
```

### 安装中文字体（如果系统没有）

```bash
# Ubuntu/Debian
sudo apt-get install fonts-noto-cjk

# 或安装文泉驿字体
sudo apt-get install fonts-wqy-zenhei
```

## 输出结果

脚本会在指定的输出目录中生成按数字顺序命名的PNG图片：

```
output/
├── 1.png
├── 2.png
├── 3.png
├── 4.png
└── 5.png
```

## 高级用法示例

### 1. 使用不同颜色和字体大小

```bash
python3 image_text_overlay.py bg.png titles.txt descriptions.txt \
  --text1-pos 200,100 \
  --text2-pos 200,180 \
  --font-size1 60 \
  --font-size2 36 \
  --color1 "#FF5733" \
  --color2 "#3498DB"
```

### 2. 生成到自定义目录

```bash
python3 image_text_overlay.py bg.png titles.txt descriptions.txt \
  --output-dir /path/to/custom/output
```

### 3. 只使用一个文本位置

如果只需要一个文本，可以让另一个文本文件为空行，或者将两个位置设置为相同。

## 作为Python模块使用

脚本也可以作为Python模块导入使用：

```python
from image_text_overlay import ImageTextOverlay

# 创建处理器
processor = ImageTextOverlay('background.png', 'output')

# 批量生成
processor.batch_generate(
    text_list1=['标题1', '标题2', '标题3'],
    text_list2=['描述1', '描述2', '描述3'],
    text1_pos=(150, 150),
    text2_pos=(150, 250),
    font_size1=48,
    font_size2=32,
    text_color1='#2C3E50',
    text_color2='#34495E'
)
```

## 常见问题

### Q: 中文显示为方块或乱码？
A: 需要安装中文字体并使用`--font-path`参数指定字体文件路径。

### Q: 如何确定文本位置坐标？
A: 可以使用图片编辑软件（如GIMP、Photoshop）打开背景图片，鼠标悬停即可看到坐标。左上角为(0,0)。

### Q: 两个文本列表长度不一致怎么办？
A: 脚本会自动以较长的列表为准，较短的列表会用空字符串补齐。

### Q: 支持哪些图片格式？
A: 支持PIL/Pillow库支持的所有格式，包括PNG、JPG、JPEG、BMP、GIF等。

### Q: 如何在MCP/工作流中使用？
A: 可以通过命令行调用此脚本，或者将其封装为MCP工具。脚本返回标准输出，便于集成到自动化工作流中。

## 依赖要求

- Python 3.6+
- Pillow (PIL) 库

安装依赖：
```bash
pip3 install Pillow
```

## 许可证

本工具为开源脚本，可自由使用和修改。
