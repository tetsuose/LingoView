# 项目进度记录

| 日期 | 阶段 | 进度摘要 | 风险/问题 | 下一步 |
| ---- | ---- | -------- | -------- | ------ |
| 2025-02-14 | 启动 | 建立项目开发计划，确定技术栈与里程碑；创建文档结构 | 无 | 完成 Electron + mpv 原型验证，准备词典数据方案 |
| 2025-02-15 | M0 项目初始化 | 创建 Electron + mpv 框架结构，编写基础配置与示例 UI | 依赖版本尚未验证，mpv/yt-dlp 安装依赖用户环境 | 验证 electron-vite 配置并实现 mpv 播放原型 |
| 2025-02-16 | M0 项目初始化 | 完成 mpv 控制器设计文档与主进程控制骨架，搭建单元测试桩并接入渲染层 API | mpv 未实际运行，测试依赖模拟 socket，需后续接入真实播放器验证 | 接入真实 mpv 进程并扩展媒体状态管理 |
| 2025-02-17 | M0 项目初始化 | 完成渲染层 Zustand 媒体状态管理与示例控制面板，接入 Electron IPC 事件并支持轨道同步/切换 | 尚未接入真实 mpv 流程，UI 控制需依赖后端实现 | 联调 mpv 播放原型，扩展状态管理至字幕与播放列表 |
| 2025-09-30 | M2 字幕 & UI 联调 | Whisper/DeepSeek 字幕管线可用，新增 YouTube 输入、控制区与 mpv 窗口对齐；优化英文/日文句子拆分与标点保留 | Whisper 非 verbose_json 回退导致时间轴错位、mpv IPC 启动时序与字幕缓存策略需注意；词典尚缺中英/中日数据 | 引入离线中英/中日词库并对接 lookup；完善字幕生成容错与缓存管理 |
| 2025-10-01 | M2 字幕 & 词典 | 扩展词典语言模式、引入 SQLite 查词服务与前端展示升级；scripts/dictionaries/build.ts 切换至 Kaikki Wiktionary + JMdict + CC-CEDICT 自动拉取与转换 | Kaikki 词条覆盖仍有限（部分动词缺中文译文），需持续评估；词典打包与分发体积显著增大 | 补充查词单元测试与端到端验证，规划打包时的词典同步策略及差分更新 |
| 2025-10-14 | M3 翻译 & ASR 优化 | 重命名为 LingoView；参考 [umlx5h/LLPlayer](https://github.com/umlx5h/LLPlayer) 抽象翻译 prompt 与上下文策略；新增基于 ffmpeg 流式切片 + 静音检测 + 重叠的 Whisper 音频管线 | Whisper 本地切片尚未做并发，静音阈值需继续调优；DeepSeek Chat 翻译依赖外部 API 稳定性 | 引入 channel 并发消费、增加配置持久化 UI，准备离线模型切换入口 |
| 2025-10-16 | M3 翻译 & ASR 优化 | 替换自适应能量 VAD + 可选降噪，重写 Whisper 切片管线；新增测试超时守卫与 VAD/切片单元测试 | mpv 集成测试仍依赖本地环境，better-sqlite3 需重新编译，长视频样本要补充回归 | 收集真实长视频调参、整理 DEBUG_WHISPER_CHUNKS 导出、推进原生 UI 方案草稿 |
| 2025-10-17 | M3 翻译 & ASR 优化 | Python 后端接入 Whisper-1/Grok API（WebRTC VAD 切片、分词）；CLI 支持 SRT/JSON 导出；新增 Streamlit Web UI | API 并发/错误容错待完善，翻译逐句请求性能待评估；Docker 镜像尚未提交 | 继续优化并发与缓存、补充自动化测试、规划 Docker/部署脚本 |
| 2025-10-21 | 架构重构 | 完成 Electron -> FastAPI + React/Vite 架构切换；实现 `/api/transcribe` 上传、历史记录与 SRT/JSON 导出；前端集成 video.js 播放与双语字幕列表 | Whisper-1 首句时间轴仍需校正；本地 `faster-whisper` 切换策略未对接 UI；API/前端缺乏自动化测试 | 引入对齐修正与本地 ASR 选项、补充前后端测试、规划 Docker 一键启动与配置模板 |
| 2025-10-25 | ASR/翻译优化 | 切换 `faster-whisper large-v2` + VAD 分片 (`120s/0 overlap`)，启用 MeCab NEologd 校正与重复裁剪；翻译改用 OpenAI `gpt-4.1-mini` 并新增 token 用量统计；新增 Whisper 阈值配置与 `.env` 核心参数 | 长句仍受模型识别限制，需评估更大模型或热词提示；翻译落在外部 API，需监控速率限制 | 收集长视频回归样本，观察新阈值对英文/多语言场景效果；规划 UI 配置入口与自动化测试 |
| 2025-10-26 | ASR/翻译优化 | Demucs 人声分离接入缓存；重写 VAD 分段策略：静音 >1s 硬切、0.5–1s 静音按中点拆分，保持 0.6s padding 并对齐时间戳，只在人声段入 Whisper；建立 `python/.venv` 并安装 `.[dev]` | DummyTranslator 缺少会话钩子导致 pytest 失败；长音频拆分仍需更多实际样本验证 | 为翻译客户端补齐 begin/end session 接口或做兼容，再收集真实音频验证新分段准确性 |
| 2025-10-27 | UI/翻译接口 | 顶部表单并排布局、视频/字幕移至左列、右侧新增词语释义面板；字幕高亮滚动位置下移；DummyTranslator 增加 begin/end usage 钩子并通过 `python/.venv/bin/python -m pytest` | 词语释义面板仍为占位，需接入选词翻译；翻译服务本地化方案待选型 | 监听字幕选区并调用本地/云端翻译填充词典；规划 NLLB/T-Translate 等自建翻译服务 |
