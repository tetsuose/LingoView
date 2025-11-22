# LingoView

![CI](https://github.com/tetsuose/LingoView/actions/workflows/ci.yml/badge.svg)
![CodeQL](https://github.com/tetsuose/LingoView/actions/workflows/codeql.yml/badge.svg)

LingoView 是一款面向语言学习的字幕生成与翻译工具，使用 Python (FastAPI) 后端 + React/Vite 前端架构。

**核心特性**：
- **本地字幕生成**：基于 `faster-whisper` 和 WebRTC VAD 的高效语音识别。
- **AI 语境词典**：点击字幕单词，即时获取基于当前语境的 AI 释义、发音和例句（支持本地缓存）。
- **现代 UI 设计**：Apple 风格的毛玻璃界面，提供沉浸式的双栏（视频/字幕）学习体验。
- **多模型支持**：支持 OpenAI、DeepSeek、Grok 等多种 LLM 用于翻译和查词。

## 目录结构

```
docs/          # 开发计划、进度记录与系统文档
python/        # FastAPI 服务与字幕管线
resources/     # 离线词典及缓存目录
scripts/       # 词典构建等辅助脚本
web/           # React/Vite 前端工程
```

## 快速开始

1. 安装 [pnpm](https://pnpm.io/installation) 与 Python 3.10+。
2. 首次运行可执行 `scripts/bootstrap.sh` 自动安装前后端依赖并生成本地 `.env`/`web/.env` 示例。
3. 可执行 `./start.sh`，同时启动 FastAPI 服务（默认端口 8000）与 Vite 前端（默认端口 5173）。
4. 手动启动：
   - 后端：`cd python && ./run_api.sh`
   - 前端：`cd web && pnpm install && pnpm dev`
5. 后端测试：`cd python && pytest`
6. 前端测试与构建：`cd web && pnpm test -- --run && pnpm build`

> 如需改用 OpenAI Whisper API，可设置 `.env` 中的 `WHISPER_BACKEND=openai` 并提供 `OPENAI_API_KEY`；默认使用本地 faster-whisper。

## 开发计划

详细路线图与里程碑请参考 `docs/development-plan.md`，进度更新请见 `docs/progress-log.md`。

## 贡献

欢迎通过 Issue 和 PR 参与贡献！请先阅读 `CONTRIBUTING.md` 与 `CODE_OF_CONDUCT.md`。

## 安全

如发现安全问题，请勿公开提交 Issue，参见 `SECURITY.md`。

## 许可证

本项目默认使用 GPL-3.0-or-later 许可证（见 `LICENSE`）。如需改用更宽松许可（MIT/Apache-2.0），请在 Issue 中讨论。

## 参考与改进

- 翻译模块在 `python/lingoview_service/translate.py` 实现上下文增强，仅支持 OpenAI 翻译（默认 `gpt-4.1-mini`，可通过 `.env` 的 `OPENAI_TRANSLATE_MODEL` 调整）。
- 音频识别采用 WebRTC VAD + `faster-whisper` 分片推理（`python/lingoview_service/vad.py` 与 `transcribe.py`）。
- `scripts/dictionaries/build.ts` 提供 Kaikki + JMdict + CC-CEDICT 的离线词典构建流程。
- 支持通过 `WHISPER_BACKEND` 切换本地推理（`local`）或 OpenAI Whisper API（`openai`）；后者需设置 `OPENAI_API_KEY`，可选 `OPENAI_WHISPER_MODEL` 与 `OPENAI_API_BASE`。
- 默认启用 Demucs 人声分离（`ENABLE_VOCAL_SEPARATION=true`）。请在虚拟环境中 `pip install demucs`，首次使用时执行 `demucs --two-stems=vocals -n htdemucs <音频文件>` 或直接运行字幕生成流程，以便自动下载模型；如需关闭，可设置 `ENABLE_VOCAL_SEPARATION=false`。
