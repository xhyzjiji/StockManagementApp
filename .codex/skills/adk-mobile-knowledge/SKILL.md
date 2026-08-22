---
name: adk-mobile-knowledge
description: TTADK Mobile knowledge base. Covers mobile SDD workflow, commands, MCP tools, knowledge base skills, dashboard, D2C integration, and troubleshooting for iOS/Android client development.
user-invocable: false
---

# TTADK Mobile 知识库

## TTADK Mobile 是什么

TTADK Mobile（原名 AI SDE）是 TikTok Mobile 端的 Spec Driven Agentic System，将 PRD → TRD → Planning → Execution 流程标准化，并内置知识库为 LLM 补充领域上下文。在这套研发工作流中，研发的角色从工程师向架构师转变。

核心特性：
- **标准工作流**：Requirements → Design → Tasks → Implementation，自动化流转，无需记住命令（新手友好）
- **实时 Dashboard**：Web 端实时工作流进度追踪、审批和 Review
- **审批流程**：内置 Human in the Loop 审批，分阶段保证交付质量
- **内置模版**：客户端场景专属模板保证需求、设计、任务文档质量
- **通用知识库**：支持 AB、埋点、网络等基础组件知识；业务领域知识、架构设计约束
- **业务拓展**：插件化设计，业务在模板、Skills、知识库有充分扩展空间

## 与 TTADK (Server/Web) 的差异

| 特征 | TTADK (Server/Web) | TTADK Mobile |
|------|------------------------|--------------|
| 工作流引擎 | Node.js 脚本 + 本地文件 | adk-mobile MCP 服务 |
| SDD 阶段 | specify → plan → tasks → implement | requirements → design → tasks → implementation |
| 制品管理 | `specs/` 目录下本地文件 | MCP 工作流目录（`.ttadk/.adk-mobile/specs/`） |
| 持久化 | 直接在 specs/ 下编辑 | 通过 `/adk:sdd:save` 保存到代码仓库 |
| 项目结构 | 单仓库为主 | Monorepo + 子模块（Modules/） |
| 知识库 | Constitution + Skills | Module-level CLAUDE.md + docs/ |
| 审批方式 | 无内置审批 | Dashboard / CLI 两种审批模式 |
| D2C 集成 | 无 | Figma → Code（Android remote / iOS local） |
| 定制能力 | 插件 commands/skills | user-templates / user-hooks / user-knowledge |

## 当前命令体系

### SDD 工作流命令

| 命令 | 使用场景 | 说明 |
|------|---------|------|
| `/adk:sdd:spec <input>` | PRD / 技术方案 / 本地需求转 Spec | 输入飞书/Lark 文档、本地 Markdown/Text 文件或一句话需求，根据模版生成 Spec 草稿，作为工作流的输入。Spec 是后续流程核心，需研发仔细补充 |
| `/adk:sdd:new <description>` | Spec 转代码 | 启动 SDD 工作流（Requirements → Design → Tasks → Implementation） |
| `/adk:sdd:continue <local-spec \| Lark URL>` | 异常恢复 / 飞书反馈同步 | 恢复当前仓库已经开始的工作流；Lark URL 可反查本地 FF Spec 并同步评论 |
| `/adk:sdd:clarify` | 增量修补 | 发现需求或技术设计需要修改时，保证修改在不同阶段的一致性 |
| `/adk:sdd:ff <description>` | 小需求快速流 | 单 plan.md、单次审批、改动 ≤ `ffMaxFiles` 文件（默认 10）；更大需求用 `/adk:sdd:new` |
| `/adk:sdd:repo --add <repo>` / `--remove <repo>` | 多仓协同 | 为当前需求添加或移除一个开发仓库；add 可打开预填 Prompt 的 Agent Session |
| `/adk:sdd:revert <phase>` | 中间回退 | 回退到指定阶段重新开始（同时回滚已记录的实现生成代码），如在 implement 阶段发现需要修改设计 |
| `/adk:sdd:save [spec name]` | 保存 Spec | 将 Spec 中间产物保存至业务模块路径下，纳入 git 版本管理 |
| `/adk:sdd:list [exact-spec]` | 查看进度 | 默认展示服务端返回的逐成员状态与 Spec 同步状态；传入精确本地 Spec 时显示详情 |

### 基础公共命令

| 命令 | 说明 |
|------|------|
| `/adk:help` | TTADK Mobile 帮助手册，回答工作流、命令用法、当前状态等问题 |
| `/adk:readiness` | 评估移动端仓库或模块的 AI Coding 就绪度，支持 Monorepo 模块级评估 |
| `/adk:commit` | 提交当前工作区改动，自动生成规范化 commit message 并 push，支持子模块 |

### 知识库 Skills

| Skill | 使用场景 | 说明 |
|-------|---------|------|
| `kb-init-docs` | 首次生成知识 | 模型基于代码理解，为任意路径生成知识库。`--analysis` 可自动分目录生成 |
| `kb-update-docs` | 增量更新知识 | LLM 基于最新代码，谨慎地更新知识库文档 |
| `kb-docs-validator` | 校验质量 | 检测冲突、不一致，对齐代码与文档 |
| `kb-docs-benchmark` | 基准测试 | 通过 Q&A 对比衡量文档对回答质量的影响 |
| `kb-evals-creator` | 创建评测 | 创建和维护 evals.json 评测文件 |

## MCP 工具

TTADK Mobile 通过 adk-mobile MCP 服务驱动工作流：

| MCP 工具 | 说明 | 使用方 |
|----------|------|--------|
| `sdd-guide` | 启动或恢复 SDD 工作流 | `/adk:sdd:new`, `/adk:sdd:continue` |
| `sdd-ff-guide` | 启动 Fast-Flow 小需求工作流 | `/adk:sdd:ff` |
| `prd-to-spec` | 从飞书/Lark 文档、本地文件或文本需求生成技术 Spec | `/adk:sdd:spec` |
| `spec-list` | 列出多仓需求的逐仓状态；可通过 `specName` 查询精确详情 | `/adk:sdd:list`, `/adk:help` |
| `spec-status` | 查询 Spec 当前阶段和进度 | `/adk:sdd:continue`, `/adk:help` |
| `spec-save` | 将 Spec 保存到代码仓库 | `/adk:sdd:save` |
| `log` | 记录工作流事件 | `/adk:sdd:revert` |
| `sdd-code-revert` | 按 implementation manifest 回滚已记录的实现生成代码（支持 dry-run） | `/adk:sdd:revert` |
| `approvals` | 管理制品审批状态 | `/adk:sdd:revert`, 审批流程 |
| `spec-group` | 为已有本地 Spec 添加或移除仓库成员 | `/adk:sdd:repo`，以及带 `--add-repo` 的创建入口 |

MCP 工具调用模式：`mcp__adk-mobile__<tool-name>`

## 推荐工作流

### 标准模式（推荐）

```text
readiness → sdd:new <goal> → [sdd:clarify] → sdd:save → commit
```

核心路径：Requirements → Design → Tasks → Implementation，每个阶段需 Review & Approve 后自动进入下一阶段。

### PRD 驱动模式

```text
readiness → sdd:spec <input> → sdd:new <spec> → [sdd:clarify] → sdd:save → commit
```

先从 PRD、技术方案、本地需求文件或一句话需求生成 Spec 草稿，研发补充完善后进入工作流。

### Fast-Flow 模式（小需求 / Bugfix）

```text
readiness → sdd:ff <goal> → [sdd:clarify] → sdd:save → commit
```

适用：小功能、Bugfix、小范围重构（单 plan.md、单次审批、改动文件数 ≤ `ffMaxFiles`，默认 10）。超出范围请用标准模式 `/adk:sdd:new`。

### 多仓需求模式

```text
spec/new/ff [--add-repo <repo>] → 为单个额外仓库准备本地 Spec
→ 更多成员逐次使用 sdd:repo --add <repo> 幂等加入
→ 各仓库独立推进 → clarify 只更新当前仓库制品
→ 阶段 Guide 感知其他成员的 spec.md 更新并询问 Apply / Later / View
→ list 查看逐成员状态与 Spec 同步状态
```

任何已完成 TTADK Mobile 初始化的仓库都可加入；允许同平台仓库和 3 个及以上成员，3+ 成员通过同一 Spec 的多次单仓 `sdd:repo --add` 形成。每个仓库的状态机、审批和业务代码保持隔离，只有 `spec.md` 可同步到当前仓库；其他成员的 `specDir` 只读。

所有仓库统一使用已选择的工作流入口首次启动：Fast-Flow 使用 `/adk:sdd:ff <local-spec>`，完整 SDD 使用 `/adk:sdd:new <local-spec>`。命令复用已准备的本地 Spec；`/adk:sdd:continue` 只用于后续恢复。

也可在任意阶段运行 `/adk:sdd:repo --add <repo>`，或用 `/adk:sdd:repo --remove <repo>` 移除一个非当前成员。命令自动解析当前 Spec，并把用户选择的 `launchNow` 交给 MCP；MCP 负责打开新 Session、返回完整 Prompt 和复制结果，Agent 只转述结果。用户在 Session 就绪后手动粘贴运行，remove 不启动 Session。

### 知识库建设流程

```text
readiness → kb-init-docs --analysis <path> → kb-docs-validator → kb-evals-creator → kb-docs-benchmark
```

## 命令速查表

| 场景 | 推荐命令 |
|------|---------|
| 不知道下一步该做什么 | `/adk:help` |
| 判断仓库/模块 AI 开发就绪度 | `/adk:readiness` |
| 从 PRD / 技术方案 / 本地需求生成 Spec 草稿 | `/adk:sdd:spec <input>` |
| 从 Spec 开始新功能 | `/adk:sdd:new <目标描述>` |
| 小需求 / Bugfix（≤10 文件） | `/adk:sdd:ff <目标描述>` |
| 恢复之前的工作流 / 同步飞书评论 | `/adk:sdd:continue <local-spec \| Lark URL>` |
| 查看逐成员状态或精确 Spec 详情 | `/adk:sdd:list [exact-spec]` |
| 发现需求/设计需要修改 | `/adk:sdd:clarify` |
| 把已初始化 Mobile 仓库加入当前需求 | `/adk:sdd:repo --add <repo>` |
| 从当前需求移除一个非当前仓库 | `/adk:sdd:repo --remove <repo>` |
| 回退到之前的阶段 | `/adk:sdd:revert <phase>` |
| 保存 Spec 到代码仓库 | `/adk:sdd:save [spec-name]` |
| 代码准备提交 | `/adk:commit` |
| 为模块首次生成文档 | `kb-init-docs <module-path>` |
| 分析哪些模块需要文档 | `kb-init-docs --analysis <path>` |
| 更新已有模块文档 | `kb-update-docs <module-path>` |
| 模型降智/服务挂了 | `/clear` + `/adk:sdd:continue <spec-name>` |

## 核心概念

- **Spec**：SDD 制品集合，包含 `requirements.md`、`design.md`、`tasks.md`、`explore.md`、`spec.md`。
- **Workflow Directory**：`.ttadk/.adk-mobile/`，MCP 工作流的工作目录，Spec 制品存储在 `specs/{spec-name}/` 下。
- **Dashboard**：Web 端审批和进度追踪界面，支持 Review、评论、请求修订。
- **config.toml**：`.ttadk/.adk-mobile/config.toml`，个性化配置（语言、审批模式、代码 Review、D2C 等）。
- **Module**：Monorepo 中的独立功能模块（如 `Modules/Search/`），是知识库文档的基本单元。
- **Doc Root**：包含 `CLAUDE.md` + `docs/` 的模块目录，是知识库 Skills 操作的目标。
- **D2C**：Design-to-Code，从 Figma 设计稿生成代码。Android 支持 Remote D2C，iOS 为 Local D2C。
- **多仓需求**：同一需求需要在一个或多个仓库中开发；各仓保留独立 Spec 名称、状态机、审批和业务代码，`spec.md` 同步状态由阶段 Guide 和 `/adk:sdd:list` 实时计算。
- **User Customization**：业务定制目录（相对于 `.ttadk/.adk-mobile/`）：`user-templates/`（模版定制）、`user-hooks/`（阶段钩子）、`user-knowledge/`（业务知识）。

## Spec 输入模版

推荐使用 AI Technical Spec 模版作为 `/adk:sdd:new` 的输入，包含以下部分：

1. **Basic Info**：平台、App、目标
2. **Editable Scope & File Manifest**：改动范围和文件清单（`[NEW]`/`[MOD]`/`[REF]` 标记）
3. **UI/UX Structure**（可选）：Figma 链接、TUX 组件约束、布局位置
4. **Data Models & API**（可选）：数据模型、接口交互
5. **Business Logic**：When → Then 格式的交互逻辑
6. **Event Tracking**（可选）：埋点设计
7. **AB Testing Setup**（可选）：实验组配置
8. **Constraints**：约束与规范

前期 Spec 描述越清楚，需求设计生成的质量越高，交互时间就省下来了。

## 模块文档结构

```text
<Module>/
├── CLAUDE.md               # 模块概览、关键类、文档引用
├── AGENTS.md               # → CLAUDE.md 的符号链接
└── docs/
    ├── interface.md         # 外部接口和公共 API
    ├── workflow.md          # 业务流程（可含 UML 图）
    ├── domain.md            # 业务术语和领域知识
    ├── rule.md              # 代码规范、设计模式、约定
    └── evals/
        └── evals.json       # Q&A 评测用例
```

各文件的召回时机：

| 文件 | 内容 | 召回时机 |
|------|------|---------|
| CLAUDE.md | 模块简介、主要实现类、子文件索引 | LLM 访问所在文件夹 |
| domain.md | 业务术语、术语与代码映射、业务策略 | PRD/TRD 生成 |
| interface.md | 对外暴露的接口 | 代码生成（多模块改动时提供横向视角） |
| workflow.md | 业务流程 | TRD 生成、代码生成（理解上下游节点和影响范围） |
| rule.md | 代码风格、设计范式、示例 | TRD 生成、代码生成（保证质量和一致性） |

## 支持的 AI 工具

| 工具 | 支持状态 | 备注 |
|------|---------|------|
| Claude Code | 已支持（主力） | 完整 SDD 工作流支持 |
| Cursor IDE | 已支持 | 可选 SOTA 模型、可视化 Review、Token 响应更快 |
| Cursor CLI | 已支持 | 可在终端中运行完整 SDD 工作流 |
| Codex CLI | 已支持 | 通过 Codex Skills 使用工作流命令 |
| Trae | 未支持 | — |

## 详细参考文件

| 文件 | 内容 | 何时阅读 |
|------|------|---------|
| [sdd-workflow.md](./sdd-workflow.md) | Mobile SDD 流程、阶段说明、审批模式、D2C 集成、业务定制 | 用户询问 SDD 概念、工作流阶段或开发最佳实践 |
| [commands-reference.md](./commands-reference.md) | SDD 命令、基础命令、KB Skills 详解与示例 | 用户询问具体命令用法、MCP 工具或 KB Skills |
| [troubleshooting.md](./troubleshooting.md) | 常见问题、报错处理、MCP 连接、中断恢复 | 用户遇到问题、报错或询问"为什么""怎么解决" |
