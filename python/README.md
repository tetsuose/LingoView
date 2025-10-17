# LingoView Python Service

此目录存放 LingoView 后端服务的 Python 版本：

- 使用本地 `faster-whisper` 推理 + WebRTC VAD 切片完成字幕识别。
- 提供基于 OpenAI 的翻译、分词与字幕导出（SRT/JSON）。
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

- `lingoview_service.config.ServiceSettings` 会读取 `.env`（推荐放在仓库根目录或 `python/` 目录）及系统环境变量；可参考根目录的 `.env.example`。
- 仅支持 OpenAI 翻译：
  ```bash
  OPENAI_API_KEY=sk-...
  OPENAI_TRANSLATE_MODEL=gpt-4.1-mini
  # Whisper 相关（本地推理/参数）
  WHISPER_MODEL=base
  WHISPER_DEVICE=auto           # cpu / cuda / auto
  WHISPER_COMPUTE_TYPE=float32  # int8 / float16 / float32 等
  WHISPER_BEAM_SIZE=5
  LINGOVIEW_STORAGE_DIR=~/Library/Application\ Support/LingoView/cache
  ```
- `LINGOVIEW_STORAGE_DIR` 默认指向 `~/.cache/lingoview`，可改为更易检查/清理的位置。

注：历史上的 Grok/DeepSeek 翻译接口已不再维护，不在 README 范围内提供说明。

## CLI 用法示例

```bash
lingoview-cli transcribe ./sample.mp4 --translate ja --json-output output/subtitles.json --srt-output output/subtitles.srt --srt-source translation
```

## Web UI 特性

- 输入本地媒体路径，一键生成并浏览原文/译文字幕
- 表格查看分词结果，直接下载 SRT / JSON 文件
- 默认使用本地 `faster-whisper`，翻译采用 OpenAI（可通过 `OPENAI_TRANSLATE_MODEL` 调整模型）
