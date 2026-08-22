# TTADK Mobile 命令参考

## SDD 工作流命令

### /adk:sdd:spec

从飞书/Lark 文档、本地 Markdown/Text 文件或一句话需求生成初始技术 Spec。输出是后续流程的核心输入，需研发理解需求并仔细补充。

**对应 MCP 工具**：`prd-to-spec`；带额外仓库时还会使用 `spec-group`

**用法**：`/adk:sdd:spec [--add-repo <repo>] <飞书文档 URL | 本地 Markdown/Text 文件 | 一句话需求>`

**示例**：
- `/adk:sdd:spec https://bytedance.larkoffice.com/docx/xxxxxxxxxxxx`
- `/adk:sdd:spec docs/prd.md`
- `/adk:sdd:spec "Add creator profile card"`
- `/adk:sdd:spec "Add shared profile" --add-repo ../ios-app`

**前置条件**：必须提供输入内容。支持三类输入：飞书/Lark 文档 URL、本地 Markdown/Text 文件、一句话/短自然语言需求。

**行为**：
1. 验证参数中包含输入；缺失则提示用户补充。
2. 推断 `inputType`：飞书/Lark URL → `lark_url`；本地 Markdown/Text 文件 → `local_file`；一句话/短自然语言 → `plain_text`。
3. 最多接受一个 `--add-repo`，以 `additionalRepoPath: string` 传给 `mcp__adk-mobile__prd-to-spec`；出现多个时停止，并提示后续逐次使用 `/adk:sdd:repo --add`。
4. 先按返回步骤生成当前仓库的 `spec.md` 并确定 `specName`；飞书/Lark 输入会保留现有 comments、media、whiteboards/images 和 linked Lark docs 读取行为。
5. 若 `additionalRepoPath` 非空，在生成本地 `spec.md` 后只询问一次，提供四个组合选项：Fast-Flow/立即打开（推荐）、Fast-Flow/稍后、完整 SDD/立即打开、完整 SDD/稍后。
6. 将回答映射为 `workflowMode` 和 `launchNow`，再调用一次 `spec-group(action="add")`；MCP 负责所选启动动作，后续不得再次询问 Open now/Later。

**注意**：Spec.md 是后续流程核心，`/adk:sdd:spec` 的作用是辅助生成粗版草稿，仍需研发理解需求并仔细补充。

---

### /adk:sdd:new

启动 Mobile SDD 工作流，从目标描述或 Spec 文档开始，依次经过 Requirements → Design → Tasks → Implementation 四个阶段。每个阶段需 Review & Approve 后自动进入下一阶段。

**对应 MCP 工具**：`sdd-guide`；带额外仓库时还会使用 `spec-group`

**用法**：`/adk:sdd:new [--add-repo <repo>] <功能描述 | 本地文件路径 | 飞书 URL>`

**示例**：
- `/adk:sdd:new Create user authentication system`
- `/adk:sdd:new Add dark mode support`
- `/adk:sdd:new @spec_file.md Implement feature per Spec`
- `/adk:sdd:new Create shared profile --add-repo ../ios-app`

**推荐输入**：使用 AI Technical Spec 模版对需求进行系统化描述（参见 Spec 输入模版章节）。前期描述越清楚，需求设计生成质量越高。

**多仓行为**：本命令最多接受一个 `--add-repo`，并以 `additionalRepoPath: string` 传入。本命令固定使用完整 SDD；本地 Spec 生成后按 Guide 指示调用一次 `spec-group(action="add", repoPath=<单个仓库>, ..., workflowMode="sdd", launchNow=<所选时机>)`。更多成员通过 `/adk:sdd:repo --add` 逐个加入。

---

### /adk:sdd:continue

恢复已有的 SDD 工作流会话，从断点继续推进。

**对应 MCP 工具**：`sdd-guide` / `sdd-ff-guide` + `spec-list` + `spec-status`；Lark URL 分支还会使用 `lark-doc-fetch`

**用法**：`/adk:sdd:continue <local-spec | Lark/Feishu doc URL>`

**示例**：
- `/adk:sdd:continue user-auth`（精确匹配）
- `/adk:sdd:continue 001`（前缀匹配 `001-user-auth`）
- `/adk:sdd:continue 1`（同上）
- `/adk:sdd:continue https://bytedance.larkoffice.com/docx/XXXXXXXX`（反查本地 FF Spec 并同步文档评论）

**行为**：
1. Spec 名只在当前仓库的已有 Spec 中匹配（精确 / 前缀 / 关键词）；不会创建多仓关系。
2. Lark/Feishu URL 会通过当前仓库的 `lark-approval.json` 或 `events.jsonl` 反查本地 FF Spec；不会解析到其他仓库。
3. URL 分支拉取飞书正文与未解决评论。Implementation 前可同步正文；Implementation 中保留本地任务 checkbox，只把评论修订合入本地 `plan.md`，再同步回飞书并解决已处理评论。
4. 调用 `spec-status` 与对应 Guide 恢复；所有带 `phase` 的 `sdd-guide` / `sdd-ff-guide` 调用都传入 `specName`。
5. 阶段 Guide 若发现其他成员有更新，会提供 Apply / Later / View；Apply 只写当前仓库的 `spec.md`，成员 `specDir` 只读。

**常用场景**：模型降智或服务中断后，`/clear` + `/adk:sdd:continue <spec-name>` 可安全恢复。

---

### /adk:sdd:clarify

通过逆序扫描制品、交互式问答（最多 5 个问题）和级联更新，解决 Spec 制品中的歧义和不一致。

**用法**：`/adk:sdd:clarify [spec-name] [可选：聚焦问题]`

**示例**：
- `/adk:sdd:clarify`（自动检测当前 Spec）
- `/adk:sdd:clarify user-auth`
- `/adk:sdd:clarify 001-payment-flow the retry logic seems unclear`

**使用场景**：在需求开发过程中，发现需求或技术设计需要修改时，通过 clarify 保证修改在不同阶段的一致性。小改动用 clarify，大改动用 revert。

**行为**：
1. 解析目标 Spec（参数 / 上下文推断 / 询问用户）。
2. 调用 `spec-status` 确定当前阶段，构建制品链。
3. 按逆序（最新阶段优先）扫描制品，检测歧义、不一致、覆盖缺失、过时引用。
4. 生成最多 5 个按影响排序的澄清问题，逐一交互。
5. 每次回答后立即级联更新所有受影响制品。
6. 只修改当前仓库中的本地制品，不传播或写入其他成员；后续阶段 Guide 会自动感知成员 `spec.md` 的变化。

---

### /adk:sdd:repo

为已有本地 Spec 添加或移除一个仓库成员。允许同平台仓库和 3 个及以上成员。

**对应 MCP 工具**：`spec-group`

**用法**：
- `/adk:sdd:repo --add <repo>`
- `/adk:sdd:repo --remove <repo>`

**行为**：
1. `--add` 与 `--remove` 互斥，每次只接受一个仓库路径；remove 不能移除当前仓库。
2. 只在多个本地 Spec 候选无法唯一确定时询问用户。
3. add 时若本地 Spec 尚未确定 mode，使用同一个四合一问题同时收集 mode 和打开时机；若 mode 已确定，则在调用 MCP 前只询问一次 Open now/Later。将结果作为 `launchNow` 传给唯一一次 `spec-group(action="add")`，调用后不再询问。
4. 启动 Prompt 与已选模式一致：FF 用 `/adk:sdd:ff <local-spec>`，完整 SDD 用 `/adk:sdd:new <local-spec>`。Open now 由 MCP 打开 Agent、返回完整 Prompt 和复制结果；调用方不得再执行 Bash，只转述返回内容，用户在 Agent 就绪后手动粘贴运行。
5. remove 调用 `spec-group(action="remove")`，只汇报移除/幂等清理结果，不打开 Session。
6. 同一 Spec 可逐次 add 不同仓库形成 3+ 成员组；重复 add 同一仓库是幂等的重新打开路径。不保留旧命令别名。

---

### /adk:sdd:ff

Fast-Flow（FF）：单 `plan.md`、单次审批，适合小功能、Bugfix、小范围重构（改动文件数 ≤ `ffMaxFiles`，默认 10）。超出范围请用 `/adk:sdd:new`。

**对应 MCP 工具**：`sdd-ff-guide`；带额外仓库时还会使用 `spec-group`

**用法**：`/adk:sdd:ff [--add-repo <repo>] <功能描述 | Bug 报告 | 本地文档路径 | 飞书 URL>`

**示例**：
- `/adk:sdd:ff Fix double-trigger on like button`
- `/adk:sdd:ff Add story tab entry per Figma URL`
- `/adk:sdd:ff @bug_report.md Reproduce and fix the upload crash`
- `/adk:sdd:ff Add shared profile --add-repo ../ios-app`

**行为**：
1. 解析目标描述与引用文件。
2. 最多接受一个 `--add-repo`，以 `additionalRepoPath: string` 调用 `mcp__*__sdd-ff-guide`；多个 flag 必须停止并提示改用 `/adk:sdd:repo --add`。
3. 带额外仓库时按 Guide 指示调用 `spec-group(action="add", repoPath=<单个仓库>, ..., workflowMode="ff", launchNow=<所选时机>)`。
4. Plan / Implementation 的每次 phase Guide 调用都同时传入当前 `specName`。
5. 按 MCP 返回的 Fast-Flow 步骤推进。

**注意**：MCP 包需包含 `sdd-ff-guide` 工具。

---

### /adk:sdd:revert

将 Spec 回退到指定阶段的起始状态，删除该阶段及之后的制品，并安全回滚已记录的实现期生成代码。

**对应 MCP 工具**：`spec-status` + `sdd-code-revert` + `log` + `approvals`

**用法**：`/adk:sdd:revert [spec-name] <target-phase>`

**可用的 target-phase**：`requirement`、`design`、`task`、`implementation`

**示例**：
- `/adk:sdd:revert design`（回退到 design 阶段起点）
- `/adk:sdd:revert 001-user-auth requirement`（回退到 requirement 阶段起点）
- `/adk:sdd:revert implementation`（重置所有任务进度并回滚已记录的实现生成代码）

**受影响范围**：

| 回退到 | 保留 | 删除/重置 |
|--------|------|-----------|
| `requirement` | spec.md, events.jsonl | requirements.md, design.md, explore.md, tasks.md, 实现进度, 已记录的实现生成代码, d2c-output/ |
| `design` | requirements.md, spec.md, events.jsonl | design.md, explore.md, tasks.md, 实现进度, 已记录的实现生成代码, d2c-output/ |
| `task` | requirements.md, design.md, explore.md, spec.md, events.jsonl | tasks.md, 实现进度, 已记录的实现生成代码 |
| `implementation` | 所有文档 | 重置 tasks.md 中的任务 checkbox, 已记录的实现生成代码 |

**永不删除**：`spec.md`（上游真相来源）、`events.jsonl`（审计日志）、`implementation-manifest.json`（工具回滚后保留并标记 `revertedAt`/`lastRevert`，直至下次进入 implementation 重建 checkpoint；持久审计记录在 `events.jsonl` 的 `codeRevertPlan`）。

**生成代码回滚**：基于 `implementation-manifest.json`（`log` 工具在实现阶段维护），执行前先 `sdd-code-revert` dry-run 列出 restore/delete/noop 计划；有冲突或失败即中止，不删任何制品。

---

### /adk:sdd:save

将 Spec 从 MCP 工作流目录保存到代码仓库，便于纳入 git 版本管理，随 MR 一起合入并沉淀。

**对应 MCP 工具**：`spec-save`

**用法**：`/adk:sdd:save [spec-name] [target-dir]`

**示例**：
- `/adk:sdd:save`（保存当前/唯一 Spec）
- `/adk:sdd:save story-archive`（保存指定 Spec）
- `/adk:sdd:save story-archive src/feature-name/specs`（保存到指定目录）

**行为**：
1. 解析参数确定 `specName` 和 `targetDir`。
2. 调用 `spec-save`；会自动推断目标路径，也可手动指定。
3. 处理需要确认的场景：路径确认、已存在覆盖、任务未完成。

**保存的文件**：`spec.md`、`requirements.md`、`design.md`、`tasks.md`、`explore.md`。

---

### /adk:sdd:list

默认展示服务端返回的每个多仓需求及其逐仓状态；传入精确本地 Spec 时显示详情。单仓需求仍按原有摘要展示。

**对应 MCP 工具**：`spec-list`

**用法**：`/adk:sdd:list [exact-spec]`

**示例**：
- `/adk:sdd:list`：显示每成员的仓库、平台、本地 Spec、`specDir`、可达性、mode、phase、进度和 Spec 同步状态
- `/adk:sdd:list 004-profile-ios`：显示精确 Spec 详情；`behind` 成员还会显示增删计数与摘要 diff

---

## 基础公共命令

### /adk:help

回答 Mobile SDD 工作流、命令用法、KB Skills、当前状态等问题。

**用法**：`/adk:help [你的问题]`

**示例**：
- `/adk:help 下一步该做什么`
- `/adk:help /adk:sdd:new 怎么用`
- `/adk:help 怎么为模块生成文档`

---

### /adk:readiness

评估移动端仓库或特定模块的 AI Coding 就绪度，生成多维度成熟度报告。

**用法**：`/adk:readiness [模块路径 | --all-modules | 其他选项]`

**示例**：
- `/adk:readiness`（仓库级扫描）
- `/adk:readiness Modules/Search`（模块级扫描）
- `/adk:readiness --all-modules`（批量扫描所有模块）

**评估维度**：

仓库级（5 个维度）：Context Engineering、Build & Dependencies、Style & Validation、Security & Governance、SDD Readiness

模块级（3 个维度）：Module Documentation、Module Testing、Module Code Organization

**综合评分**（模块扫描时）：40% 仓库基础设施 + 60% 模块评分。成熟度等级 L1 → L4。

---

### /adk:commit

提交当前工作区改动，自动生成规范化 commit message 并 push。支持多仓库/子模块。

**用法**：`/adk:commit`

**单仓库流程**：`git add -A` → 生成 conventional commit → `git commit` + `git push`。

**多仓库/子模块流程**：先逐个 commit 有变更的子模块，最后 commit 主仓库。

---

## 知识库 Skills

### kb-init-docs

为模块目录首次生成结构化文档（CLAUDE.md + docs/）。

**用法**：
- `kb-init-docs <module-path>`（直接为指定路径生成文档）
- `kb-init-docs --analysis <path>`（分析路径下的子目录，推荐 doc roots；适合大仓库）
- `kb-init-docs <path> --lang en|zh`（指定语言）

**生成的文件**：CLAUDE.md、AGENTS.md（符号链接）、docs/interface.md、docs/workflow.md、docs/domain.md、docs/rule.md

**注意**：如果不满意 LLM 生成的文件质量，可以自行修改文档内容。

---

### kb-update-docs

根据最新代码增量更新已有模块文档，仅修改过时内容。

**用法**：
- `kb-update-docs --mr <mr_number> --repo <repo>`（首选：读 MR diff，自动按改动分组解析受影响文档）
- `kb-update-docs <path> [<path> ...]`（手动指定改动文件 / 目录；自动向上解析其归属文档根）
- `kb-update-docs --ci ...`（CI / 非交互模式，输出机器可读摘要；可与上面任一输入组合）

**更新规则**：仅更新已存在的文档，`<nay-ai>...</nay-ai>` 包裹的内容不可修改。改动会自动按「大模块」分组，更新有改动的叶子文档、评估上层 umbrella 文档；无对应文档的改动会单列（kb-init 候选），不更新。

---

### kb-docs-validator

校验知识文档质量，检测跨文件冲突和不一致，对齐代码与文档。

**用法**：`kb-docs-validator <doc-root1> [doc-root2 ...]`

---

### kb-evals-creator

为 kb-docs-benchmark 创建和维护 `evals.json` 评测文件。

**输出位置**：`<doc-root>/docs/evals/evals.json`

---

### kb-docs-benchmark

通过 Q&A 对比测试（有/无文档）衡量文档对回答质量的影响。

**对比维度**：通过率、响应时间、Token 用量、问题来源分析。

---

## Spec 输入模版

推荐使用以下模版结构化描述需求，作为 `/adk:sdd:new` 的输入：

```markdown
# AI Technical Spec: [任务名称]

## 1. Basic Info (基本信息)
- Platform: [Android | iOS]
- App: [TikTok | TikTok-Lite | TikTok-TV]
- Goal: [一句话描述需求与目标]

## 2. Editable Scope & File Manifest (改动范围 & 文件清单)
- Modification Boundary: 只能修改 <path> 内文件
- Target Files:
  - [NEW] /path/to/NewFile.kt: [新建说明]
  - [MOD] /path/to/ExistingFile.kt: [修改说明]
  - [REF] /path/to/ReferenceFile.kt: [参考说明]

## 3. UI/UX Structure (界面交互结构描述) (Optional)
- Figma 设计稿链接（不同 UI 区块贴独立 Figma node 链接）
- TUX 组件约束
- 相对位置（Anchor）

## 4. Data Models & API (数据模型与接口) (Optional)
- Models (Pseudo-code / JSON)
- API Interactions（含 Loading/Error 处理）

## 5. Business Logic (业务逻辑流程)
使用 "When → Then" 格式描述交互

## 6. Event Tracking (埋点设计) (Optional)
- 新增埋点表格
- 已有埋点参数变更

## 7. AB Testing Setup (AB 测试配置) (Optional)
- 实验组配置表格

## 8. Constraints (约束与规范)
- Navigation、Images、Theme 等约束
```

---

## 工作流个性化配置

`.ttadk/.adk-mobile/config.toml` 支持以下配置项：

```toml
port = 49972                    # Dashboard 端口
lang = "zh"                     # 输出语言 "en" | "zh"
approvalMode = "dashboard"      # 审批模式 "dashboard" | "cli"
codeReview = false              # 是否分阶段 Review 代码
useRemoteD2C4Android = false    # Android 是否开启 Remote D2C
```

- **approvalMode**：`dashboard` 模式在 Web 网页上进行 Review 和审批；`cli` 模式在命令行中弹出 Review 提示。
- **codeReview**：开启后，每个 task 完成时 SDE 会暂停等待人工 Review 代码。
- **业务定制目录**：默认使用 `.ttadk/.adk-mobile/` 下的 `user-templates/`（模版）、`user-hooks/`（阶段钩子）、`user-knowledge/`（业务知识）；高级场景可通过 adk-mobile MCP 启动参数调整，不是 `config.toml` 字段。

---

## MCP 配置

adk-mobile MCP 通过 `.mcp.json` 配置：

```json
{
  "mcpServers": {
    "adk-mobile": {
      "command": "npx",
      "args": [
        "-y", "--registry=https://bnpm.byted.org",
        "@byted-tiktok/adk-mobile-mcp@latest",
        "--workflow-dir", ".ttadk/.adk-mobile"
      ],
      "env": { "platform": "Android" }
    }
  }
}
```

- `platform`：`Android` 或 `iOS`。
- `--workflow-dir`：工作流目录（`.ttadk/.adk-mobile`）。
- Lemon8 项目可额外传 `--user-custom-dir`。

## Preset 配置

| Preset | 包含插件 |
|--------|---------|
| `ttadk/android` | `ttadk/mobile-core` + `ttadk/android` |
| `ttadk/ios` | `ttadk/mobile-core` + `ttadk/ios` |
| `lemon8/android` | `ttadk/mobile-core` + `lemon8/android` |
| `lemon8/ios` | `ttadk/mobile-core` + `lemon8/ios` |

平台插件（`ttadk/android`、`ttadk/ios`）包含各平台特有的 Skills（如 Android 的 smartrouter、tux、ab-test、network、applog 等；iOS 的 Serena、Xcode Build、TTKC Swift 等），已集成到各自仓库中。
