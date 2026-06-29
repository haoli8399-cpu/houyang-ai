# CHANGELOG — AI 电话客服系统

> 记录所有业务级变化，按时间倒序

---

## 2026-06-23

### Phase 1 工程稳固（第一批）

#### 新增
- 初始化项目中心文件结构（PRD、HANDOFF、DECISION_LOG、CHANGELOG、STATE 等）
- **S1**: CosyVoice launchd 守护进程 — `scripts/com.houyang.cosyvoice.plist`（crash 自动重启 + 开机自启）
- **S3**: `pipecat_start.sh` 集成 CosyVoice 自启 — start 命令自动检查 9880 端口并拉起

#### 优化
- **S2**: VAD 录音替代定长 5s — 1s 轮询检测语音，有声音提前 ASR，最长 8s

#### 修复
- **P0-1**: ASR `_load()` 增加异常详情日志，区分包缺失 vs 模型加载失败
- **P0-1**: `listen_mode()` 启动时预热 ASR 模型，避免通话中首次加载延迟
- **P0-2**: TTS 音色从 `demo` 切换为 `豪哥`（自定义克隆音色）
- **P1**: TTS 播放时序估算优化：`len(text)/6` → `len(text)/3.5 + 1.0`（匹配中文语速）

#### 状态
- 全链路已跑通，Phase 1 第一批 3 项工程加固已执行（launchd + VAD + 脚本自启）
- 待豪哥重启验证 + 注册 launchd plist

## 2026-06-29

### 修复重启 — 全链路恢复运行

#### 修复
- **ASR**: 拆分 `import torch` 防止 torch 未安装时误判 faster-whisper 不可用
- **TTS**: `is_ready()` 改用 socket 端口检测；`synthesize()` 改用 curl 子进程，避开 QClaw 代理限制

#### 状态
- ✅ FreeSWITCH: 运行中
- ✅ ASR: faster-whisper (base) 预热完成
- ✅ TTS: CosyVoice 豪哥音色就绪
- ✅ LLM: DeepSeek API 已配置
- 📞 待豪哥注册软电话拨 5000 拨测

## 2026-06-29（第二轮）

### 🔴 Phase 2 功能开发 — 通话记录存储 + 录音持久化

#### 新增
- **`db.py`**: SQLite 数据库模块，双表结构（`calls` + `turns`），WAL 模式支持并发
- 通话开始自动写入 `calls` 表（主叫/被叫/时间）
- 每轮对话自动写入 `turns` 表（ASR 文字 + LLM 回复 + 动作 + 音频路径）
- 通话结束时自动更新时长和状态
- 录音从 `/tmp` 持久化到 `records/{call_id}/turn_{N}_user.wav`
- TTS 音频持久化到 `records/{call_id}/turn_{N}_assistant.wav`

#### 查看方式
```bash
sqlite3 records/calls.db "SELECT turn_number, user_text, assistant_text FROM turns WHERE call_id='...' ORDER BY turn_number;"
```

## 2026-06-30（凌晨）

### 🎉 Phase 2 运营后台（Round 1+2 一次性完成）

#### 新增
- **`admin/app.py`**: FastAPI 后台服务（端口 3001）
- **`admin/templates/index.html`**: 运营后台前端（SPA，4 个标签页）
- **`config/` 目录**: prompt.md / welcome.txt / farewell.txt / voice.txt / knowledge/
- **运营后台功能**:
  - 📝 配置页：编辑 AI 提示词、欢迎语、结束语
  - 📚 知识库页：增/删/改/查知识条目（Markdown）
  - 🎤 音色页：查看可用音色、切换音色、试听 TTS
  - 📞 通话记录页：查看历史通话、对话详情、播放录音
  - 🟢 后台首页显示各服务运行状态

#### 改造
- **`ai_pipeline.py`**: 提示词/欢迎语/结束语/音色均从 `config/` 文件读取，不再硬编码
- 编辑 `config/prompt.md` → 重启生效（后续可做热更新）

#### 启动方式
```bash
cd ~/projects/houyang-ai/pipecat-ai
# 终端1: AI Pipeline（已在运行）
# 终端2: 运营后台
~/pipecat-venv/bin/uvicorn admin.app:app --host 127.0.0.1 --port 3001 --reload

# 浏览器打开：http://localhost:3001
```
