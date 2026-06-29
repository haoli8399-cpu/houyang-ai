# HANDOFF — 后仰喜剧 AI 电话客服系统

> **生成日期**：2026-06-29 23:37
> **项目负责人**：豪哥
> **当前 Agent**：Hermes Agent（2026-06-29 接手，替换原 CodeBuddy）
> **用途**：给新接手的 Agent 完整了解项目

---

## 一、项目总览

### 1.1 项目定位

为「成都后仰喜剧」搭建 AI 电话客服系统。用户拨打客服电话 → AI 自动接听 → 四川普通话风格对话 → 处理咨询/转人工。

### 1.2 目录结构

```
~/projects/houyang-ai/
├── pipecat-ai/                       ← 主项目目录
│   ├── ai_pipeline.py               ← AI 引擎核心（ASR+LLM+TTS 对话管道）
│   ├── pipecat_start.sh             ← 启停脚本（start/stop/restart/status）
│   ├── puresl.py                     ← 纯 Python ESL 库（FreeSWITCH 通信）
│   ├── scripts/
│   │   └── com.houyang.cosyvoice.plist  ← launchd 守护配置
│   ├── project-center/              ← 项目中心文件（所有 Agent 读取拉齐用）
│   ├── records/                      ← 通话记录（当前空，待实现）
│   └── .gitignore                   ← Git 忽略规则
│
├── cosyvoice/                        ← CosyVoice 音色引擎（5.4G）
│   └── podcast-engine/
│       └── server.py                ← TTS HTTP 服务（端口 9880）
│
└── pipecat-venv/                     ← Python 虚拟环境
```

### 1.3 GitHub

```
仓库: https://github.com/haoli8399-cpu/houyang-ai
分支: main
```

---

## 二、技术架构

### 2.1 系统架构

```
[用户电话/软电话] ─── SIP 5060 ───→  FreeSWITCH
                                           │
                                     ESL 8022 (127.0.0.1)
                                           │  CHANNEL_CREATE 事件
                                           ▼
                                  ai_pipeline.py (AI 引擎)
                                           │
                             ┌─────────────┼─────────────┐
                             ▼             ▼             ▼
                        faster-whisper  DeepSeek API  CosyVoice TTS
                        (ASR, 本地)      (LLM, 云端)    (本地 9880)
```

### 2.2 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 电话接入 | FreeSWITCH 1.11.1 | SIP 5060 + ESL 8022 |
| AI 引擎 | Python 3.11 | 单 socket 事件监听 |
| ASR | faster-whisper (base) | 本地运行，CPU int8，已预热 |
| LLM | DeepSeek API (deepseek-chat) | 云端，API Key 在 .env |
| TTS | CosyVoice2-0.5B | 本地 MPS 加速，端口 9880，豪哥音色 |
| 虚拟环境 | ~/pipecat-venv | Python venv（QClaw 代理封装的 Python） |

### 2.3 分机配置

| 分机 | 用途 | 密码 |
|------|------|------|
| 5000 | AI Agent | — |
| 1001 | 用户注册 | 1234 |
| 9999 | 转人工（占位，无坐席） | — |

---

## 三、当前状态（2026-06-29）

### 3.1 ✅ 已完成

| # | 任务 | 完成日期 | 说明 |
|---|------|---------|------|
| 1 | 全链路跑通 | 06-23 | ASR+LLM+TTS 成功通话 |
| 2 | ASR 日志增强 + 启动预热 | 06-23 | 区分 ImportError vs 模型加载失败 |
| 3 | TTS 音色切换 demo→豪哥 | 06-23 | 零样本克隆 |
| 4 | TTS 播放时序优化 | 06-23 | 估算系数 /6 → /3.5 + 1.0 |
| 5 | VAD 录音 | 06-23 | 1s 轮询替代固定 5s，最长 8s |
| 6 | CosyVoice launchd 守护 | 06-23 | plist（crash 自动重启 + 开机自启） |
| 7 | 启动脚本 CosyVoice 自启 | 06-23 | start 命令自动检查+拉起 |
| 8 | **修复重启全链路** | 06-29 | ASR torch 分离 + TTS curl 绕代理 |
| 9 | **API Key 安全（硬编码→环境变量）** | 06-29 | fallback Key 已移除 |
| 10 | **通话记录存储（SQLite）+ 录音持久化** | 06-29 | db.py + 每轮记录 + 录音存档 |
| 11 | **Phase 2 运营后台** | 06-29 | FastAPI + 配置/知识库/音色/通话记录管理 |

### 3.2 📋 待开发

| 优先级 | # | 任务 | 说明 |
|--------|---|------|------|
| 🟡 | 1 | 转人工坐席对接 | 分机 9999 → 真实手机/坐席 |
| 🟢 | 2 | System Prompt 热更新（不重启） | 实时生效 |
| 🟢 | 3 | 日志轮转 | 防止日志无限增长 |

---

## 四、启动与操作

### 4.1 启动全链路

```bash
cd ~/projects/houyang-ai/pipecat-ai && ./pipecat_start.sh start
```

### 4.2 检查状态

```bash
./pipecat_start.sh status
# 或
./pipecat_start.sh check
```

### 4.3 查看日志

```bash
tail -f ~/projects/houyang-ai/pipecat-ai/pipecat.log
```

### 4.4 拨打测试

注册软电话 → 分机 1001（密码 1234） → 拨打 5000 → AI 接听

---

## 五、关键警告（务必阅读）

| # | 警告 |
|---|------|
| 1 | **不要** `brew services start freeswitch` — 会启动默认配置 |
| 2 | **不要**同时运行两个 FreeSWITCH 实例 |
| 3 | 重启 CosyVoice **必须**重启 ai_pipeline（TTS 连接会断） |
| 4 | DeepSeek API Key **不要**提交到公开仓库 |
| 5 | ESL 端口是 **8022** 而非默认 8021 |
| 6 | Python HTTP 被 QClaw 代理拦截 → TTS 使用 curl 子进程绕行 |
| 7 | **项目中心文件只读给子 Agent**，只有主 Agent（Hermes）可修改 |

---

## 六、项目中心文件

| 文件 | 路径 | 内容 | 维护者 |
|------|------|------|--------|
| HANDOFF.md | `project-center/HANDOFF.md` | 项目交接/状态（本文） | Hermes |
| PRD.md | `project-center/PRD.md` | 产品需求文档 | Hermes |
| AGENT_RULES.md | `project-center/AGENT_RULES.md` | Agent 工作规则 | Hermes |
| CONTRACT.md | `project-center/CONTRACT.md` | 协作契约 | Hermes |
| DECISION_LOG.md | `project-center/DECISION_LOG.md` | 全部决策记录 | Hermes |
| CHANGELOG.md | `project-center/CHANGELOG.md` | 变更日志 | Hermes |
| ROADMAP.md | `project-center/ROADMAP.md` | 产品路线图 | Hermes |
| FROZEN.md | `project-center/FROZEN.md` | 不可变契约 | Hermes |
| CONSISTENCY_CHECKER.md | `project-center/CONSISTENCY_CHECKER.md` | 一致性检查规则 | Hermes |
| COLLABORATION.md | `project-center/COLLABORATION.md` | 多 Agent 协作指南 | Hermes |
| MANIFEST.md | `project-center/MANIFEST.md` | 项目全景概述 | Hermes |
| BUDGET.md | `project-center/BUDGET.md` | 预算/资源 | Hermes |
| codebase_progress.md | `project-center/codebase_progress.md` | 任务看板 | Hermes |

---

## 七、工作规范（给新 Agent）

### 7.1 三阶段流程

任何任务必须：**Phase 1 只读分析 → Phase 2 方案提议（豪哥确认）→ Phase 3 执行**

### 7.2 信息拉齐

每轮执行前，主 Agent 必须全量读取项目中心文件（project-center/ 下所有文件）。
子 Agent 由主 Agent 在 context 中提供必要上下文。

### 7.3 事务完整性

确认 → 写入所有联动文件 → git add → git commit → git push

### 7.4 称呼

- 对话中称 **「豪哥」**
- 对外文件用 **「产品负责人」**
