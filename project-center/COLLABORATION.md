# COLLABORATION — AI 电话客服系统

> 多 Agent 协作指南
> 最后更新：2026-06-29

---

## 一、Agent 角色

| Agent | 职责 | 触发场景 |
|-------|------|---------|
| **Hermes Agent（主 Agent）** | 需求分析、方案设计、代码实现、文档维护、子 Agent 协调调度 | 默认，全权负责人 |
| **Sub-Agent（子 Agent）** | 执行主 Agent 分发的独立子任务 | 主 Agent 拆分并行任务时 |
| **Reviewer Agent** | 代码审查、一致性检查、质量把关 | 关键变更的审查环节 |

## 二、任务分发规范

### 方式一：TASK.md（子 Agent 独立窗口）
主 Agent 将任务写入项目根目录 `TASK.md`，豪哥在各窗口发「读根目录 TASK.md」即可执行。
格式：

```markdown
# TASK — [任务名称]

## 目标
[一句话描述]

## 上下文
[相关文件路径、当前状态、关键代码位置]

## 要求
1. [具体要求]
2. [具体要求]

## 约束
- 只读分析，不要修改文件
- 如需读项目中心文件，参考 project-center/ 目录
```

### 方式二：delegate_task（Hermes 内部分发）
主 Agent 通过 `delegate_task(tasks=[...])` 直接分发并行子任务。
每个子任务 context 必须自包含（项目根目录、文件路径、映射表、禁止事项）。

## 三、协作流程

```
豪哥提需求
    ↓
Hermes Agent 分析（Phase 1：全量读项目中心文件 + 代码分析）
    ↓
Hermes Agent 方案（Phase 2：输出结构化执行计划）
    ↓
豪哥确认
    ↓
Hermes Agent 执行（Phase 3）或 分发子 Agent
    ├── Sub-Agent A（并行子任务）
    ├── Sub-Agent B（并行子任务）
    └── Hermes 汇总验证 + 修复遗漏
    ↓
Hermes Agent 更新项目中心文件 → git push
    ↓
Hermes Agent 汇报结果
```

## 四、文件所有权

| 文件/目录 | 主要维护者 | 修改需审批 |
|-----------|-----------|-----------|
| `ai_pipeline.py` | Hermes Agent | ✅ 豪哥 |
| `puresl.py` | Hermes Agent | ✅ 豪哥 |
| `project-center/*` | Hermes Agent（主 Agent） | ✅ 豪哥（只读给子 Agent） |
| `pipecat_start.sh` | Hermes Agent | ✅ 豪哥 |

## 五、信息拉齐机制（铁律）

### 5.1 执行前必读

所有 Agent 执行任何任务前，必须读取项目中心文件：

| Agent | 读什么 | 怎么读 |
|-------|--------|--------|
| **主 Agent**（Hermes） | `project-center/` 下**全部文件** | 全量读取，逐文件过 |
| **子 Agent** | 由主 Agent 在 context 中提供必要信息 | 不需自己读，但 context 必须包含关键上下文 |

### 5.2 执行后必更

主 Agent 在每轮任务结束后，必须**立即执行**（不积压、不拖延）：

```
1. 更新所有受影响的中心文件（联动写入）
2. git add → git commit → git push
3. 汇报时附带更新摘要
```

### 5.3 谁延迟谁负责

如果因更新不及时导致子 Agent 信息不一致、产生冲突或重复劳动，**责任在主 Agent**。

### 5.4 项目中心文件路径

```
~/projects/houyang-ai/pipecat-ai/project-center/
```
