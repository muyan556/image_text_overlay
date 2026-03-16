# Video Synth Engine

极简架构的音画同步视频合成系统，自带实时网页控制台。
通过精确的 FFmpeg 底层滤镜 (`apad`、`aresample`) 实现毫秒级完美的 A/V 轨道无缝拼接，彻底解决合成视频第二遍发音延迟的问题。

## 环境要求

1. **Python 3.8+**
2. **FFmpeg**: 必须已安装，并已配置到系统全局环境变量 `PATH` 中。

## 安装依赖

打开终端，在项目根目录下运行：

```bash
pip install flask pillow edge-tts