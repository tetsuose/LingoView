# LingoView Python Service

此目录存放 LingoView 后端服务的 Python 版本：

- 使用本地 `faster-whisper` 推理 + WebRTC VAD 切片完成字幕识别。
- 集成 Grok-4-mini-fast 翻译、分词与字幕导出（SRT/JSON）。
- 提供 CLI (`lingoview-cli`)、FastAPI HTTP 服务与后续 Streamlit/Web UI 的公共接口。
- 与前端（React/Vite）共享字幕生成管线，也支持 Docker、批处理和脚本化场景。

## 快速开始

```bash
cd python
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
lingoview-cli --help

# 运行 Streamlit Web UI（自动记录日志到 ~/Library/Application Support/LingoView/streamlit.log）
./run_webui.sh

# 启动 FastAPI 服务（供 React 前端调用）
./run_api.sh

# 自动化测试
pytest
```

> 注：默认使用本地 `faster-whisper` 模型，可通过环境变量切换模型大小、设备和精度。

## 配置

- `lingoview_service.config.ServiceSettings` 会读取 `.env`（推荐放在仓库根目录或 `python/` 目录）及系统环境变量。
- 建议的 `.env` 内容示例：
  ```bash
  # DeepSeek（优先使用）
  DEEPSEEK_API_KEY=sk-...
  DEEPSEEK_MODEL=deepseek-chat
  DEEPSEEK_ENDPOINT=https://api.deepseek.com/chat/completions

  # 如需使用 Grok 作为备选
  GROK_API_KEY=xai-...
  GROK_MODEL=grok-4-mini-fast
  GROK_ENDPOINT=https://api.x.ai/v1/chat/completions
  WHISPER_MODEL=base
  WHISPER_DEVICE=auto    # cpu / cuda / auto
  WHISPER_COMPUTE_TYPE=int8   # int8 / float16 / float32 等
  WHISPER_BEAM_SIZE=5
  LINGOVIEW_STORAGE_DIR=~/Library/Application\ Support/LingoView/cache
  ```
- `LINGOVIEW_STORAGE_DIR` 默认指向 `~/.cache/lingoview`，可改为更易检查/清理的位置。

后续会补充 `.env.sample`、Dockerfile；Streamlit UI 可通过 `./run_webui.sh` 启动。

## CLI 用法示例

```bash
lingoview-cli transcribe ./sample.mp4 --translate ja --json-output output/subtitles.json --srt-output output/subtitles.srt --srt-source translation
```

## Web UI 特性

- 输入本地媒体路径，一键生成并浏览原文/译文字幕
- 表格查看分词结果，直接下载 SRT / JSON 文件
- 默认使用本地 `faster-whisper`，翻译优先调用 DeepSeek Chat（可在 `.env` 配置备选 Grok）
