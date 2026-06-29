# COLLABORATION — AI 电话客服系统

> 多 Agent 协作指南
> 最后更新：2026-06-29

---

## 一、Agent 角色

| Agent | 职责 | 触发场景 |
|-------|------|---------|
| **Hermes Agent（主 Agent / Orchestrator）** | 需求分析、方案设计、任务分发、结果验证、项目中心文件维护、git push | **始终**，全权负责人 |
| **Implementation Agent（子 Agent）** | 代码修改（ai_pipeline.py / puresl.py / 脚本）+ 运维操作（服务启停 / Docker / 监控） | 需要改代码或执行运维操作时 |
| **Review Agent（子 Agent）** | 代码审查、一致性检查、安全审计 | **仅 ai_pipeline.py 核心逻辑变更时**启用，常规改动由主 Agent 自行审查 |

## 二、任务分发规范

### 方式一：TASK.md（子 Agent 独立窗口）
主 Agent 将任务写入项目根目录 `TASK.md`，豪哥在各窗口发「读根目录 TASK.md」即可执行。

**TASK.md 生命周期：**
- 任务完成后，主 Agent **立即清空** TASK.md 或归档到 `TASK_ARCHIVE/`
- 禁止将已完成的旧任务留在 TASK.md 中

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
Phase 3：执行
    ├── 单线任务 → Hermes 自己执行
    ├── 并行可拆 → 分发 Implementation Agent（文件集不重叠）
    ├── 核心逻辑变更 → + Review Agent 审查
    └── 错误处理 → 验证失败则打回重做
    ↓
Hermes 汇总验证（语法检查 + 一致性扫描 + 修复遗漏）
    ↓
Hermes 更新项目中心文件 → git push
    ↓
Hermes 汇报结果 + 清空/归档 TASK.md
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

### 5.3 子 Agent 输出验证协议

主 Agent 在合并子 Agent 结果前，必须执行基础验证：

| 检查项 | 方法 | 不通过处理 |
|--------|------|-----------|
| 语法检查 | `python3 -c "compile(...)"` 或 lint | 打回，附错误信息 |
| 文件完整性 | 目标文件是否存在、关键函数是否保留 | 打回，附差异说明 |
| 一致性扫描 | 检查是否引用了不存在的函数/变量 | 打回 |
| 与中心文件对齐 | 修改是否对应已确认的方案 | 打回 |

### 5.4 文件锁规则

- **同一文件同一轮只派给一个子 Agent**，禁止并行修改同一文件
- 多子 Agent 并行时，各自的文件集必须不重叠
- 主 Agent 和子 Agent 的文件集也不能重叠（主 Agent 只改 project-center/，子 Agent 不改）

### 5.5 谁延迟谁负责

如果因更新不及时导致子 Agent 信息不一致、产生冲突或重复劳动，**责任在主 Agent**。

### 5.6 项目中心文件路径

```
~/projects/houyang-ai/pipecat-ai/project-center/
```
