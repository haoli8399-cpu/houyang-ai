# DECISION_LOG — AI 电话客服系统

> 记录所有产品/技术决策，ID 格式：D-YYYYMMDD-XXX

---

| 决策 ID | 日期 | 决策内容 | 提议人 | 状态 | 影响范围 |
|---------|------|---------|--------|------|---------|
| D-20260623-001 | 2026-06-23 | P0-1: ASR `_load()` 增加异常详情日志（区分 ImportError vs 模型加载失败），`listen_mode()` 启动时预热 ASR 模型 | CodeBuddy | ✅ 已执行 | `ai_pipeline.py` |
| D-20260623-002 | 2026-06-23 | P0-2: TTS 音色从 `demo`（预置女声）切换到 `豪哥`（零样本克隆音色），提升品牌辨识度 | CodeBuddy | ✅ 已执行 | `ai_pipeline.py` 第 54 行 |
| D-20260623-003 | 2026-06-23 | P1: TTS 播放时序估算系数从 `len(text)/6` 调整为 `len(text)/3.5 + 1.0`，匹配中文正常语速 3.5 字/秒 | CodeBuddy | ✅ 已执行 | `ai_pipeline.py` `_speak()` |
| D-20260623-004 | 2026-06-23 | 初始化项目中心文件结构（PRD/HANDOFF/DECISION_LOG/CHANGELOG/STATE 等），建立规范化项目管理 | CodeBuddy | ✅ 已执行 | `project-center/`, `STATE/` |
| D-20260623-005 | 2026-06-23 | S1: CosyVoice launchd 守护进程 — 新建 plist（KeepAlive+RunAtLoad），crash 自动重启 | Builder-1 | ✅ 已执行 | `scripts/com.houyang.cosyvoice.plist` |
| D-20260623-006 | 2026-06-23 | S2: VAD 录音替代定长 5s — 1s 轮询检测文件大小，有语音提前停止，最长 8s | Builder-1 | ✅ 已执行 | `ai_pipeline.py` |
| D-20260623-007 | 2026-06-23 | S3: 启动脚本集成 CosyVoice 自启 — start 命令自动检查+启动 9880，等待 30s | Builder-1 | ✅ 已执行 | `pipecat_start.sh` |
| D-20260629-001 | 2026-06-29 | ASR 修复：拆分 `import torch` 防止 torch 未安装时误判 faster-whisper 不可用 | Hermes Agent | ✅ 已执行 | `ai_pipeline.py` `_load()` |
| D-20260629-002 | 2026-06-29 | TTS 修复：`is_ready()` 改用 socket 端口检测 + `synthesize()` 改用 curl 子进程，避开 QClaw 代理对 Python HTTP 的限制 | Hermes Agent | ✅ 已执行 | `ai_pipeline.py` `TTSClient` |
| D-20260629-003 | 2026-06-29 | 移除硬编码的 DeepSeek API Key，改为环境变量读取，密钥仅存于 .env | Hermes Agent | ✅ 已执行 | `ai_pipeline.py` config |
| D-20260629-004 | 2026-06-29 | 清理 CodeBuddy 遗留文件 + 初始化 git + 推送到 GitHub（haoli8399-cpu/houyang-ai） | Hermes Agent | ✅ 已执行 | 全部项目 |
| D-20260629-005 | 2026-06-29 | 多 Agent 架构优化：精简角色、新增子 Agent 验证协议、文件锁规则、TASK.md 生命周期 | Hermes Agent | ✅ 已执行 | COLLABORATION.md, AGENT_RULES.md, FROZEN.md |
| D-20260629-006 | 2026-06-29 | 通话记录存储（SQLite）+ 录音持久化：新建 db.py，改造 CallHandler 记录每轮对话和录音 | Hermes Agent | ✅ 已执行 | db.py, ai_pipeline.py |
