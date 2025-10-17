# LingoView — Development Plan (Python Backend + Web Frontend)

## 1. 项目概览
- **目标**：构建一套面向语言学习的视频字幕生成与翻译工具，采用 Python (FastAPI) 后端 + React/Vite 前端架构，通过视频上传、自动字幕、翻译、词法分析等能力，帮助用户快速理解外语内容。
- **形态**：本地部署的前后端分离应用。后端负责音频处理、ASR、翻译、导出；前端提供上传、播放器 (video.js)、双语字幕、历史记录与下载入口。
- **部署方式**：开发阶段通过 `python/run_api.sh` 启动 FastAPI 服务，`pnpm --filter web dev` 启动前端。后续提供 Docker/二进制捆绑方案。

## 2. 目标与非目标
- **必须实现**
  - 支持本地音视频上传，触发 Whisper 自动字幕生成。
  - 提供字幕句子级时间轴、双语并排显示、点击回放等交互。
  - 集成 Grok（或兼容 OpenAI API）进行字幕翻译，可切换目标语言。
  - 支持词法/分词结果保留以便后续扩展词典、学习功能。
  - 生成 SRT/JSON 导出，并在前端同步展示下载链接。
  - 维护历史任务缓存，可重新加载既有结果。
- **非目标（暂不覆盖）**
  - 桌面原生客户端（Electron/WPF 等）。
  - 多用户协同、云同步、在线公共部署。
  - 自动字幕纠错/润色的高级交互（保留 API 能力可后续扩展）。

## 3. 目标平台与性能指标
- **平台**：macOS 与 Linux 开发环境，以 Python 3.10+ 与 Node.js 20+ 为基础。后续扩展 Windows 开发兼容。
- **性能指标**：
  - 10 分钟以内视频的字幕生成响应时间 < 4 倍音频时长（本地 `faster-whisper base`）。
  - 如切换至云端 Whisper-1，可将 15 分钟视频控制在 < 3 倍音频时长。
  - 前端上传/播放体验流畅，视频播放时 CPU 占用 < 35%（1080p，本地磁盘）。
  - 历史记录查询 < 200ms，下载链接即时可用。

## 4. 功能范围
- **媒体处理**
  - 利用 FFmpeg 统一转码至 16kHz 单声道 WAV 做 Whisper 输入。
  - 支持音频/视频格式（MP4, MKV, MP3 等）。
  - 通过临时文件完成 Demucs（可选）人声分离与静音分析，处理结束后仅保留导出与缓存元数据。
  - 可选执行 Demucs 人声分离，缓存提取后的 vocal-only 音频以提升静音判定与 ASR 质量。
- **字幕生成**
  - 默认使用 `faster-whisper large-v2` 本地推理（`compute_type=float32`，可按需切换量化），配合 WebRTC VAD 分片（`chunk_seconds=120`、`chunk_overlap≈1s` 安全重叠）。
  - 基于 VAD/能量混合策略识别语音段落：静音 >1.0s 作为硬切、0.5–1.0s 静音按中点分段，对齐原始时间轴并维持 0.6s 语音 padding，仅对检测到人声的区间执行 Whisper。
  - `condition_on_previous_text=true`，同时启用 `no_speech/log_prob/compression_ratio` 阈值裁剪低置信段，保持句子连贯。
  - MeCab（`mecab-ipadic-neologd`）做轻量文本归一化，新增重叠句归一化去重，避免“次回！”类重复。
  - 预留云端 Whisper-1 / 其他 ASR 服务的可选配置。
  - 句子级时间轴、分词信息写入 JSON。
- **翻译**
  - 默认调用 OpenAI Responses API（`gpt-4.1-mini`），必要时 fallback Grok / DeepSeek，并记录 token 消耗统计。
  - 逐句翻译+标点修正，保留上下文提示（前后句原文）以维持术语一致。
  - 翻译失败时回退原文，保证界面展示完整。
  - 翻译客户端与测试桩统一实现 `begin_usage_session` / `end_usage_session`，方便计费统计与测试隔离。
- **前端交互**
  - Vite + React + video.js 播放器，标题栏内并排呈现文件选择、目标语言、生成按钮。
  - 上传/翻译语言选择/历史下拉，视频与字幕区位于页面左列，右列保留词语释义面板。
  - 双语字幕列表、点击回到对应时间点、自适应滚动，高亮段落定位在可视区域下方避免遮挡播放器。
  - 导出文件列表（SRT/JSON）置于字幕列表下方，不挤占滚动空间。
- **历史与导出**
  - 后端统一存储在 `~/.cache/lingoview`（含 `exports`、`demucs`、`chunks` 等子目录），记录 metadata + 导出结果。
  - `/api/history` 提供最近 N 条任务，返回导出文件与元数据供前端加载。

## 5. 技术栈
- **后端**：Python 3.10+, FastAPI, httpx, pydantic-settings, Typer（CLI）、uvicorn。
- **ASR/VAD**：`faster-whisper` large-v2、FFmpeg、webrtcvad，自研 chunk 管线（可扩展云端 Whisper-1）。
- **分词/校正**：Sudachi + `mecab-ipadic-neologd`、pykakasi、可选 Fugashi，MeCab 后处理去噪。
- **翻译**：DeepSeek Chat API（可配置 Grok 等其它 LLM）。
- **前端**：React 19, Vite, TypeScript, axios, video.js, clsx。
- **构建工具**：pnpm 9+（前端）、venv + pip（后端）。
- **开发辅助**：eslint, typescript-eslint, Ruff, pytest/pytest-asyncio。

## 6. 系统架构
```
┌────────────────────────┐      ┌────────────────────────┐
│        React/Vite       │      │      FastAPI Backend    │
│ - 上传表单              │  ┌─▶ │ - /api/transcribe       │
│ - video.js 播放器       │  │   │ - /api/history          │
│ - 字幕/翻译展示         │  │   │ - 静态文件: /exports       │
│ - 导出下载              │  │   │                        │
└──────────┬─────────────┘  │   └──────────┬─────────────┘
           │Axios           │              │
           │REST            │              │调用
           ▼                │              ▼
      JSON/媒体             │      ┌─────────────────────┐
                             │      │ SubtitlePipeline    │
                             │      │ - FFmpeg 转码       │
                             │      │ - Whisper 分片/ASR  │
                             │      │ - 句子切分 + 分词   │
                             │      │ - Grok 翻译         │
                             │      │ - 导出 SRT/JSON     │
                             │      └─────────────────────┘
```
- **存储**：`~/.cache/lingoview` 下的 `exports/`（字幕导出）、`demucs/`（人声缓存）、`chunks/`（VAD 中间结果）。上传原文件使用临时目录，任务结束即清理。
- **日志/调试**：FastAPI 控制台日志，前端浏览器 DevTools。

## 7. 外部依赖与配置
- 环境变量：`OPENAI_API_KEY`、`GROK_API_KEY` 等在 `.env` 管理。
- 需要本地安装 FFmpeg；若启用 `faster-whisper`，需下载模型权重。
- CORS：默认允许 `localhost:5173` 等开发源，生产时需收敛。

## 8. 构建与运行
1. **后端**
   - `cd python`
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -e .[dev]`
   - `OPENAI_API_KEY=... GROK_API_KEY=... ./run_api.sh`
2. **前端**
   - `cd web`
   - `pnpm install`
   - `pnpm dev`
3. 访问 `http://localhost:5173`，上传视频触发流程。

## 9. 测试策略
- **后端**：
  - pytest 单元测试覆盖 VAD、chunking、翻译 fallback、导出。
  - 集成测试：向 `/api/transcribe` 发送样例文件校验响应结构与缓存命中逻辑。
  - 将关键模块接入 Ruff + mypy（后续）。
- **前端**：
  - Vitest/React Testing Library 覆盖上传表单、历史列表等逻辑。
  - Playwright（后续）验证端到端交互。
- **性能/回归**：
  - 提供脚本测量本地模型与云端模型耗时。
  - 保留实际长视频样本，定期比对输出时间轴。

## 10. 里程碑规划
| 阶段 | 周期 | 交付物 |
| --- | --- | --- |
| M0 架构切换 | 第 1-2 周 | FastAPI + React 雏形，完成上传→字幕→下载闭环 |
| M1 字幕强化 | 第 3-5 周 | Whisper 分片、句子切分、翻译落地，历史记录与导出完善 |
| M2 学习体验 | 第 6-8 周 | video.js 交互增强、词法/分词展示、词典计划 |
| M3 部署准备 | 第 9-10 周 | Docker 化、配置模板、监控/日志、性能优化 |

## 11. 风险与对策
- **API 依赖不稳定**：增加 `faster-whisper` 本地模式，翻译支持多供应商。
- **大型文件处理耗时**：异步队列 / 后端任务化，增加进度反馈。
- **前端播放器兼容性**：引入 video.js，测试主流浏览器，保留 `<video>` 作为 fallback。
- **隐私与存储**：提供自动清理脚本/设置，支持自定义存储路径。
- **第三方接口封装一致性**：翻译客户端需提供 `begin_usage_session/end_usage_session` 钩子；为避免管线报错，需要统一抽象与兜底实现。

## 12. 文档与协作
- 代码规范：Python Ruff + Black（后续引入），前端 ESLint + Prettier。
- 文档目录：
  - `docs/development-plan.md`（本文件）
  - `docs/progress-log.md`（阶段进展）
  - `python/README.md`（后端运行指南）
  - `web/README.md`（前端运行指南）
- 每次迭代更新进度/风险，确保环境变量示例同步。

## 13. 下一步行动
1. 整理后端配置，增加本地 `faster-whisper` 切换与缓存策略。
2. 将 video.js 正式接入播放器组件，支持倍速/字幕轨道切换。
3. 为 `/api/transcribe` 增加任务状态（队列）接口，改善大文件体验。
4. 实现“选中字幕 → 右侧词语释义面板即时翻译”交互，优先集成本地/自托管翻译服务。
5. 扩展导出格式（ASS、带分词 JSON），并在前端展示词法结果。
6. 补充端到端测试与 CI（pytest + `pnpm build && pnpm test`）。
