# 后仰喜剧 AI 电话客服 — Trae 接手文档

> 生成日期：2026-07-03
> 项目位置：`~/projects/houyang-ai/pipecat-ai/`
> GitHub 仓库：`https://github.com/haoli8399-cpu/houyang-ai`
> 部署机器：macOS（本地开发机，非云端）

---

## 一、项目全景

### 1.1 系统架构

```
用户电话 (SIP/400)
     │
     ▼
┌─────────────────────┐
│   FreeSWITCH        │  ← SIP 注册 & 通话路由
│   SIP 5060          │     AI Agent 分机 5000
│   ESL 8022          │     用户分机 1001（测试）
└────────┬────────────┘
         │ 拨分机 5000 → dialplan answer→park
         │ ESL 事件通知
         ▼
┌─────────────────────┐
│   ai_pipeline.py    │  ← 核心 AI 引擎（Pipecat）
│   监听 ESL 事件     │     单 socket 阻塞收 CHANNEL_CREATE
│   收到来电开线程    │     每通电话一个 CallHandler 线程
└────────┬────────────┘
    ┌────┼────┬────┐
    ▼    ▼    ▼    ▼
   ASR  LLM  TTS  DB
  (本地) (云端) (本地) (SQLite)
```

### 1.2 调用链路

```
用户语音 → FreeSWITCH → ESL → ai_pipeline.py
  → ASR (faster-whisper 本地 base 模型)
  → LLM (DeepSeek API — deepseek-chat)
  → TTS (CosyVoice 本地 9880 端口)
  → 播放 WAV → FreeSWITCH → 用户听到回复
```

---

## 二、关键路径一览

### 2.1 项目代码

| 组件 | 绝对路径 |
|------|---------|
| **项目根目录** | `~/projects/houyang-ai/pipecat-ai/` |
| 主程序 | `~/projects/houyang-ai/pipecat-ai/ai_pipeline.py` |
| 启停脚本 | `~/projects/houyang-ai/pipecat-ai/pipecat_start.sh` |
| 运营后台 | `~/projects/houyang-ai/pipecat-ai/admin/app.py` |
| 前端模板 | `~/projects/houyang-ai/pipecat-ai/admin/templates/index.html` |
| 数据库层 | `~/projects/houyang-ai/pipecat-ai/db.py` |
| ESL 封装 | `~/projects/houyang-ai/pipecat-ai/puresl.py` |

### 2.2 配置文件

| 文件 | 路径 | 内容 |
|------|------|------|
| 系统提示词 | `config/prompt.md` | LLM system prompt（小仰人设） |
| 欢迎词 | `config/welcome.txt` | 接通后首句话 |
| 结束语 | `config/farewell.txt` | 挂断前最后一句话 |
| 音色配置 | `config/voice.txt` | 当前="嘉宾1" |
| 预生成欢迎语 | `config/welcome.wav` | 1087KB，启动时生成 |
| 预生成结束语 | `config/farewell.wav` | 711KB，启动时生成 |
| 知识库目录 | `config/knowledge/` | 演出信息、剧场信息等 |
| 环境变量 | `.env` | DeepSeek API Key（已 gitignore） |

### 2.3 数据与日志

| 类型 | 路径 | 说明 |
|------|------|------|
| 通话记录 DB | `records/calls.db` | SQLite，含 calls + turns 表 |
| 录音文件 | `records/{uuid}/` | 每通话一个子目录 |
| Pipeline 日志 | `pipecat.log` | 运行时日志 |
| FS 日志 | `~/freeswitch/log/freeswitch.log` | FreeSWITCH 日志 |
| CosyVoice 日志 | `/tmp/cosyvoice.log` | TTS 引擎日志 |

### 2.4 服务路径

| 服务 | 路径 / 配置 | 备注 |
|------|------------|------|
| **FreeSWITCH** | `~/freeswitch/conf/` | 自定义配置（非 Homebrew） |
| FreeSWITCH 配置 | `~/freeswitch/conf/vars.xml` | local_ip_v4=192.168.0.249 |
| FS 拨号方案 | `~/freeswitch/conf/dialplan/default/15_pipecat_agent.xml` | 5000分机：answer→park |
| FS 原拨号方案 | `~/freeswitch/conf/dialplan/default.xml` | demo_ivr 已注释 |
| **CosyVoice** | `~/projects/houyang-ai/cosyvoice/` | TTS 引擎 |
| CosyVoice 服务 | `~/projects/houyang-ai/cosyvoice/podcast-engine/server.py` | 端口 9880 |

### 2.5 旧版遗留（勿用）

| 路径 | 说明 |
|------|------|
| `~/pipecat-ai/` | CodeBuddy 旧版（6月23日），ai_pipeline.py 不完整，无 admin/config 目录 |
| `~/Desktop/cosyvoice-podcast-system/` | CosyVoice 旧位置，当前用 `~/projects/houyang-ai/cosyvoice/` |

---

## 三、如何运行

### 3.1 启动顺序

```bash
# 1. Python 虚拟环境
VENV="$HOME/pipecat-venv"
source $VENV/bin/activate

# 2. FreeSWITCH
freeswitch -nc -ncwait -conf ~/freeswitch/conf -db ~/freeswitch/db -log ~/freeswitch/log -htdocs ~/freeswitch/htdocs

# 3. CosyVoice TTS（conda 环境）
~/miniconda3/envs/cosyvoice/bin/python \
  ~/projects/houyang-ai/cosyvoice/podcast-engine/server.py > /tmp/cosyvoice.log 2>&1 &

# 4. AI Pipeline（自动加载 .env）
cd ~/projects/houyang-ai/pipecat-ai && ./pipecat_start.sh start

# 5. 运营后台（新终端）
cd ~/projects/houyang-ai/pipecat-ai
~/pipecat-venv/bin/uvicorn admin.app:app --host 127.0.0.1 --port 3001 --reload
```

### 3.2 服务检查

```bash
cd ~/projects/houyang-ai/pipecat-ai && ./pipecat_start.sh status
```

### 3.3 关键端口

| 端口 | 服务 | 当前状态 |
|------|------|---------|
| 5060 | FreeSWITCH SIP | ✅ |
| 8022 | ESL (Event Socket) | ✅ 密码 ClueCon |
| 9880 | CosyVoice TTS | ✅ |
| 3001 | 运营后台 | ✅ 访问 http://localhost:3001 |

### 3.4 ⚠️ 重要警告

- **不要运行 `brew services start freeswitch`** — 会启动 Homebrew 默认配置而非自定义配置
- **不要同时运行两个 FreeSWITCH 实例** — 端口冲突
- **重启 CosyVoice 后必须重启 ai_pipeline** — TTS 健康检查在启动时做
- **ESL 端口是 8022 而非 8021** — 解决 macOS IPv6 限制的改动
- **DeepSeek API Key 在 `.env` 中** — 已 gitignore，不要提交到公开仓库

---

## 四、当前状态

### 4.1 已完成（✅ 全链路跑通）

- [x] FreeSWITCH + SIP 注册 + 拨打 5000 分机
- [x] ASR (faster-whisper) 本地语音识别
- [x] LLM (DeepSeek API) 对话生成（约 2s）
- [x] TTS (CosyVoice) 语音合成（CPU 模式约 20-40s 实时合成）
- [x] 欢迎语/结束语预生成（启动时合成 wav，避免通话中等待 40-70s）
- [x] 通话记录存储 (SQLite)
- [x] 运营后台（配置/知识库/音色管理/通话记录）
- [x] 音色试听功能修复
- [x] ASR 键盘输入阻塞修复（移除 input() 兜底，改为静默跳过）

### 4.2 已知问题

| # | 问题 | 优先级 |
|---|------|--------|
| 1 | TTS 播放用 `time.sleep` 估算时长，不精确 | 🟡 |
| 2 | CosyVoice 无守护进程，挂了无人拉起 | 🟡 |
| 3 | faster-whisper 加载时机在通话中，首轮延迟暴增 | 🟡 |
| 4 | 无转人工坐席（分机 9999 只是占位符） | 🟡 |

### 4.3 下一步（Loop 工程计划）

参考 `~/projects/houyang-ai/pipecat-ai/project-center/ROADMAP.md` 和外部方案文档
（原文件路径：`~/.qclaw/workspace-ua58rsb93veqtxl7/ai-phone-customer-service-loop-engineering-plan.md`）

Phase 0（基础设施）：
- ✅ 0.1 ASR fix（已完成）
- □ 0.2 创建 loops/ 目录结构
- □ 0.3 system prompt 抽到外部文件
- □ 0.4 orchestrator.py 调度器骨架

---

## 五、测试方法

### 5.1 拨打测试

```bash
# 通过 Telephone 软电话注册分机 1001（密码 1234）
# 服务器 Domain: 192.168.0.249
# 拨打 5000 → 听到预生成欢迎语 → 说话 → AI 回复
```

### 5.2 模拟测试

```bash
cd ~/projects/houyang-ai/pipecat-ai
# 目前 test 模式走模拟对话
python3 ai_pipeline.py --test
```

### 5.3 Loopback 测试（FS 内部）

```bash
# 连接到 FreeSWITCH 控制台
fs_cli -P 8022
# 在控制台中拨打 loopback
originate loopback/5000 &park()
```

---

## 六、重要文件说明

### 6.1 ai_pipeline.py 结构

```
main()
├── --check → check_services()
├── --listen → listen_mode()         # 主监听循环
│   ├── 预热 ASR
│   ├── 预生成 welcome/farewell wav
│   └── while True: recv_event()
│       └── CHANNEL_CREATE → _run_handler()
│           └── CallHandler.run()
│               ├── answer + 播放 welcome
│               └── _loop() 对话循环
│                   ├── _capture_speech() 录音+ASR
│                   ├── LLM.chat()
│                   └── _speak() TTS合成+播放
└── --test → test_mode()
```

### 6.2 运营后台 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 管理后台首页 |
| `/api/config/prompt` | GET/PUT | System prompt |
| `/api/config/welcome` | GET/PUT | 欢迎词 |
| `/api/config/farewell` | GET/PUT | 结束语 |
| `/api/config/voice` | GET/PUT | 音色配置 |
| `/api/knowledge` | GET | 知识库列表 |
| `/api/knowledge/{name}` | GET | 知识库内容 |
| `/api/knowledge/{name}` | PUT | 更新知识库 |
| `/api/knowledge` | POST | 新建知识库 |
| `/api/calls` | GET | 通话记录 |
| `/api/voices` | GET | CosyVoice 音色列表 |
| `/api/test-tts` | POST | 试听指定音色 |

### 6.3 可用音色

`["我的声音","豪哥","嘉宾1","主持人2","主持人1","旁白","嘉宾2","嘉宾3"]`
当前使用：**嘉宾1**

---

## 七、Git

```bash
# 仓库
git remote -v
# → origin  https://github.com/haoli8399-cpu/houyang-ai.git (fetch)
# → origin  https://github.com/haoli8399-cpu/houyang-ai.git (push)

# 最后提交
# a86a4e0 docs: 端到端拨测通过，更新项目中心文件
```

---

*本文档生成于 2026-07-03，供 Trae 接手本项目使用。*
