# LingoView — 项目摘要

## 1. 当前形态
- **后端**：Python 3.10+，FastAPI 提供 `/api/transcribe`、`/api/subtitles/{hash}` 与 `/exports/*` 静态下载。
  - ASR：默认使用本地 `faster-whisper large-v2`（`compute_type=float32`，可换用量化模型），结合 WebRTC VAD 切片；`chunk_seconds=120`、重叠约 1s、`condition_on_previous_text=true`，并启用 `no_speech/log_prob/compression_ratio` 阈值过滤低置信段。
  - 静音策略：可选 Demucs 人声提取后再执行 VAD，静默 >1s 直接切割、0.5–1s 静默按中点拆段，保持 0.6s padding 以对齐原时间轴，仅在人声区间调用 Whisper。
  - 翻译：OpenAI Responses API（默认 `gpt-4.1-mini`）优先，必要时切换 Grok/DeepSeek；翻译客户端在 `begin_usage_session` / `end_usage_session` 钩子内统计 token 消耗。
  - 分词：Sudachi（NEologd）+ pykakasi 生成读音/罗马字，可选 Fugashi；日语场景自动触发 MeCab 纠错去重。
  - 缓存：以源文件 SHA-256 + 目标语言定位 `~/.cache/lingoview/exports` 中的 metadata；命中直接返回并附带导出链接。Demucs 与 VAD 中间结果分别缓存在 `demucs/`、`chunks/`。
  - 导出：SRT / JSON（含词级信息）及元数据写入 `.metadata.json`，供 `/api/history` 与前端下载调用。
- **前端**：React + Vite + video.js。
  - 顶部标题栏内横向放置文件选择、翻译语言和“生成字幕”按钮；上传后获取任务 ID 并监听 API 响应，视频仍通过本地 `URL.createObjectURL` 播放。
  - 自动计算文件 hash，已有结果通过 `/api/subtitles/{hash}` 直接载入；支持手动刷新强制重新转写。
  - 主体区域采用左右两列布局：左侧包含播放器与字幕列表，高亮段落滚动定位于列表下部并在下方列出导出文件；右侧词语释义面板预留给选词翻译。
  - 字幕区域展示原文/翻译/词法，按词高亮，支持切换目标语言；处理进度通过 API 消息同步。
- **脚本与环境**：
  - `python/run_api.sh` 启动 FastAPI；`web/pnpm dev` 启动前端。
  - `start.sh` 协调前后端子进程，退出时发送 `SIGINT` 防止 `pnpm dev` 报错。

## 2. 关键目录
- `python/`：后台服务；运行 `./run_api.sh`。
  - `lingoview_service/pipeline.py`：字幕管线、整句合并逻辑。
  - `lingoview_service/audio_processing.py`：Demucs 人声分离缓存。
  - `lingoview_service/transcribe.py`：Whisper 推理，英文启用 `vad_filter`。
  - `lingoview_service/vad.py`：静音判定 + 分段逻辑。
  - `lingoview_service/tokenizer.py`：Sudachi + pykakasi 分词与罗马字。
  - `lingoview_service/exports.py`：缓存 metadata、Hash 命中逻辑。
  - `tests/`：pytest 覆盖 CLI、导出、管线。
- `web/`：前端；`pnpm dev` 启动。
  - `src/App.tsx`：上传/缓存匹配、字幕渲染。
  - `src/App.css`：字幕样式调整。
- `docs/`：项目文档（开发计划、进度、摘要）。

## 3. 现有功能
- 本地视频上传 → 自动字幕生成 → 翻译 → 分词展示。
- 相同视频二次上传直接命中缓存（按 hash + 目标语言）。
- Whisper 分段整合 Demucs 人声 + VAD 静音策略（>1s 硬切、0.5–1s 中点拆分），并在归一化后去除重复短句。
- 导出 SRT/JSON（原文与翻译）供下载。
- 前端支持词级高亮、切换翻译语言、自动滚动定位。
- 翻译客户端及测试桩统一实现 `begin_usage_session` / `end_usage_session` 钩子，方便统计 token 与兼容管线调用。

## 4. 测试与构建
- 后端：`python -m venv python/.venv && source python/.venv/bin/activate && pip install -e .[dev]`；测试命令 `python/.venv/bin/python -m pytest`（需确保翻译客户端具备会话钩子以通过管线测试）。
- 前端：`cd web && pnpm install && pnpm build`。

## 5. 待办/展望
- 可考虑：新增缓存清理策略、后端任务进度反馈、前端错误提示优化。
- 英语字幕合并仍依赖终止符判断，可后续加入词距阈值（停顿时间）进一步修剪。
- 深入支持其他语言（如中文分词、韩语罗马音）可复用 TokenDetail 结构。
