from PIL import Image, ImageDraw

# 尺寸 16:9
W, H = 1024, 576

# 创建纯黑背景（RGBA 方便透明）
img = Image.new('RGBA', (W, H), (0, 0, 0, 255))
draw = ImageDraw.Draw(img)

# 保存
img.save("black_faint_grid_bg.png")
print("已生成：black_faint_grid_bg.png")
