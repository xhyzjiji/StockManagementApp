---
name: integration-testing
description: Automate post-coding integration testing workflow including pre-checks, test case design, code submission, BOE/PPE deployment via BITS, RPC/HTTP test execution, log verification (trace + error), metrics tracking verification, and report generation. Use when the user wants to run integration tests for changed code or specific interfaces, or mentions "integration testing" / "集成测试" / "接口测试".
---

# 集成测试流程

> **核心原则**：整个流程由 `.gdpa/{session-id}/status.json` 驱动。每次执行前先读取状态文件，确认当前阶段；每步操作后更新状态文件。
> **Session-ID 约束（workflow 专用）**：`gdpa-cli run` 全局不再强制要求 `--session-id`，但本 workflow 必须在整条链路里显式复用同一个 `--session-id <session_id>`。CLI 不会自动把 Session-ID 注入到 Skill 输入；如果漏传或中途更换，`.gdpa/{session-id}/status.json`、阶段产物和恢复链路都会断开。

---

## 强制执行约束（必须遵守）

**以下规则优先级最高，违反任何一条都视为执行失败：**

1. **命令失败时如实报告，不可伪造成功** — 如果 `gdpa-cli` 命令执行失败，**必须如实向用户报告错误**并排查修复，不可跳过或伪造结果。
2. **调用 `gdpa-cli` 前必须先阅读对应 Skill** — 了解完整的参数格式、输入输出 Schema 和使用示例，确保命令参数正确。不要凭记忆或猜测拼写命令。
3. **环境参数一致性** — `env`、`vregion`、`vdc` 等参数必须从 `status.json` 的 `context` 中读取，全流程保持一致。
4. **必须创建 session 目录并维护 status.json** — **必须**在 `.gdpa/{session-id}/` 下创建目录、初始化 `status.json`，并在每一步操作后写入产出文件和更新状态。不可跳过状态文件的创建和维护。
5. **测试数据基于真实分析构造** — 测试用例和数据必须基于接口 Schema、代码分析、参考文档等真实信息构造，禁止随意编造无依据的测试数据。
6. **回退操作须用户确认** — 任何阶段回退都需要向用户展示问题摘要并提供选项，由用户决策。

---

## 一、启动与恢复

**每次新对话的第一个操作，必须严格按以下顺序执行。不可跳步、不可调换顺序。**

### Step 0：创建 session（第一个动作，无条件执行）

> **这是整个流程的第一个动作，必须在做任何其他事情之前执行。**
> **不要先去查看 .gdpa/ 目录、不要先 ls、不要先检查是否有旧 session。**

**执行**：`gdpa-cli create-session`

- 记住返回的 `session_id`（例如 `sess_20260416_143052_abcd1234`）
- 后续所有 `gdpa-cli run` 命令都通过 `--session-id <session_id>` 传递

**唯一例外**：本次对话中已经执行过 `create-session` 并获得了 `session_id`，则直接使用，不重复创建。

### Step 1：初始化 session 目录和 status.json

拿到 `session_id` 后，**立即**执行：

```bash
mkdir -p .gdpa/{session-id}
```

然后在 `.gdpa/{session-id}/status.json` **写入**初始化内容（使用 [status-schema.md](status-schema.md) 中的初始化模板）。

> 完整的 status.json 结构与初始化模板见 [status-schema.md](status-schema.md)
>
> **关键**：后续每个阶段的产出文件也必须实际写入 `.gdpa/{session-id}/` 对应子目录，不可省略。

### Step 2：恢复已有流程（仅限用户主动提供 session_id 时）

> **此步骤仅在用户明确说"恢复 session XXX"或提供了一个已有的 session_id 时才执行。**
> 如果用户没有提供旧 session_id，则跳过此步骤，直接从 Phase 0 开始。

读取用户指定的 `.gdpa/{用户提供的session-id}/status.json`，按 `current_phase` 定位到对应阶段：

| phase status | 行为 |
|-------------|------|
| `pending` | 开始该阶段 |
| `in_progress` | 从上次中断处继续（结合 `history` 判断进度） |
| `completed` | 跳到下一个阶段 |
| `skipped` | 跳到下一个阶段 |
| `failed` | 分析 `summary` 中的失败原因，尝试修复或询问用户 |

---

## 二、阶段定义与状态流转

### 流转总览

```
pre_check → test_design → code_submit → deploy → test_execution → log_verify → tracking_verify → report
                                           ↑           │                │               │
                                           └───────────┘                │               │
                                           (回退: 修复代码后重新部署)      │               │
                                                        ↑               │               │
                                                        └───────────────┘               │
                                                        (回退: 重新执行测试)              │
                                                                        ↑               │
                                                                        └───────────────┘
                                                                        (回退: 重新验证日志)
```

各阶段 `status` 值：`pending` → `in_progress` → `completed` / `skipped` / `failed`

**流转规则**：

| 从 | 到 | 条件 | 类型 |
|----|----|------|------|
| pre_check | test_design | 用户确认信息 + 测试范围 | 确认门 |
| test_design | code_submit | 测试用例确认 | 确认门 |
| code_submit | deploy | 代码推送成功 | 线性（自动推进） |
| deploy | test_execution | BITS 流水线成功 | 线性（自动推进） |
| test_execution | log_verify | 测试用例全部执行完 | 线性（自动推进） |
| log_verify | tracking_verify | 日志验证完成 | 线性 |
| tracking_verify | report | 埋点验证完成/跳过 | 线性 |
| test_execution | deploy | 发现代码问题 + 用户选择回退 | 用户决策回退 |
| log_verify | test_execution | 发现问题 + 用户选择回退 | 用户决策回退 |
| tracking_verify | log_verify | 发现问题 + 用户选择回退 | 用户决策回退 |

**回退统一机制**：任何验证阶段发现问题时，暂停并展示问题摘要，提供选项：
- **A: 回退** — 回退到指定阶段重新执行
- **B: 继续** — 标记问题并继续到下一阶段
- **C: 直接出报告** — 跳到 report 阶段，产出包含问题记录的报告

---

### Phase 0: pre_check（预检查）

> **目标**：收集服务信息、分析代码变更、检测受影响的接口、确认测试范围和环境。
>
> 使用 `repo2psm`、`repotalk`、`bam-api` Skill。**调用前必读对应 Skill。**

**入口条件**：收到用户的集成测试请求

**操作步骤**：

0. **初始化（获取用户名与确定执行范围）**：

   为后续的运行数据回传（report 阶段）准备基础信息。

   1) **获取用户名**：通过 git config 获取 `username`
      ```bash
      GIT_EMAIL=$(git config user.email 2>/dev/null)
      if [ -n "$GIT_EMAIL" ] && [[ "$GIT_EMAIL" == *"@"* ]]; then
        GIT_USERNAME=$(echo "$GIT_EMAIL" | cut -d'@' -f1)
      else
        GIT_USERNAME=$(git config user.name 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
        if [ -z "$GIT_USERNAME" ]; then
          GIT_USERNAME="unknown-user"
        fi
      fi
      ```
      将 `GIT_USERNAME` 写入 `context.username`。

   2) **确定测试范围（scope）**：根据用户输入识别生成模式
      - **全量**：用户明确要求"全量"/"整个服务"/"所有接口"测试 → `scope="all"`
      - **增量（默认）**：针对变更代码的集成测试（含未指定场景） → `scope="incremental"`
      - 将结果写入 `context.scope`。

1. **自动检测 PSM**（使用 `repo2psm` 策略）：
   - 按优先级在仓库根目录中查找 PSM 定义：
     1. `script/bootstrap.sh` → `PSM` 变量
     2. `script/settings.py` → `PRODUCT.SUBSYSTEM.MODULE`
     3. `build.sh` → `RUN_NAME` 变量
     4. `atum.yaml` → `PSM` 字段
   - 找到后填入确认单；未找到则留空让用户填写

2. **检查本地分支**：
   - 当前分支 **不是** `master`/`main`：默认使用当前分支
   - 当前分支 **是** `master`/`main`：基于需求建议新分支名，在确认单中让用户确认

4. **分析代码变更**：
   - 执行 `git diff --name-only HEAD~1..HEAD`（或对比 master/main）获取变更文件列表
   - 使用 `repotalk` 语义搜索分析变更涉及的接口和业务逻辑
   - 使用 `bam-api` 获取受影响接口的完整定义（方法名、请求/响应 Schema）
   - **记录文件数量**：过滤出源代码文件后（排除测试文件、配置文件等），将文件数量写入 `context.file_num`；全量模式下，将目标范围内的全部源代码文件数作为 `file_num`

5. **搜索并收集参考文档**（文档驱动测试的基础，必须认真执行）：

   **自动搜索**（按优先级逐一扫描）：
   - `specs/` 目录下的 `spec.md`、`plan.md`、`tasks.md`
   - 项目根目录的 `README.md`、`DESIGN.md`、`CHANGELOG.md`
   - `.cursor/` 目录下的设计文档
   - `docs/` 目录下的 PRD、技术设计文档
   - 与受影响接口同名或相关的文档（如接口名为 `PrivacyQuery`，搜索含 `privacy` 的 md 文件）
   - IDL 文件中的注释和接口描述（已在 Step 4 获取的 Schema 中）

   **向用户主动索取**（搜索完成后，无论是否找到文档，都必须展示搜索结果并询问用户）：
   - 展示已找到的文档列表
   - **明确询问**用户是否有以下补充材料：
     - PRD 链接（飞书/Confluence/其他）
     - 技术设计文档
     - 接口使用说明或上下游对接文档
     - 历史 bug 记录或已知问题
     - 口述的业务规则、边界条件、特殊场景
   - 将所有文档路径和用户补充内容记录到 `context.test_context_docs`

   > **重要**：文档是测试用例设计的第一输入源。如果项目中完全没有文档且用户也未提供任何补充，需要在确认单中明确标注「⚠️ 无参考文档，测试设计将完全依赖代码分析，可能遗漏业务层面的验收标准」。

6. **展示确认单**：

```markdown
## 集成测试确认单

| 配置项 | 当前值 | 来源 | 说明 |
|--------|--------|------|------|
| **PSM** | `tiktok.xxx.xxx` | 🤖 仓库自动检测 | ⚠️ 请确认 |
| **开发分支** | `feat/xxx` | 🤖 当前分支 | master 时将自动创建测试分支 |
| **部署环境** | BOE / PPE | ⏳ 待选择 | 请选择 BOE 或 PPE |
| **PPE 环境名** | `ppe_<标识>` | 🤖 自动生成 | 可自定义，用于 Env Platform 部署 |
| **区域 (Region)** | `i18n` | 🤖 推断 | i18n / cn |
| **测试 VRegion** | Singapore-Central | 🤖 推导 | ⚠️ 请确认 |
| **测试 VDC** | sg1 | 🤖 推导 | ⚠️ 请确认 |
| **检测到的变更接口** | `GetXxx`, `UpdateYyy` | 🤖 代码分析 | 将作为测试目标 |
| **参考文档** | spec.md, plan.md | 🤖 项目搜索 | 用于测试设计 |

> 回复 "确认" 继续；回复具体修改项进行调整。
> 如有额外参考文档（PRD 链接、口述需求等），请一并提供。
```

7. **修正参数**：根据用户反馈更新，直到用户确认

**退出条件**：用户明确确认所有参数

**产出文件**：`pre-check/task_config.json`（PSM、分支、环境、接口列表、参考文档路径）

> 完成检查：`task_config.json` 存在且 `psm` 非空 → 标记 completed

---

### Phase 1: test_design（测试用例设计）

> **目标**：采用「文档驱动优先、代码分析补充」的策略，设计覆盖业务场景和代码分支的完整测试用例。
>
> 使用 `repotalk`、`bam-api` Skill。**调用前必读对应 Skill。** 参考 `integration-testing-knowledge` 获取测试构造指导。如有飞书文档链接，使用 `lark_docs` Skill 获取内容。

**入口条件**：`pre_check` 已完成

**核心原则**：

> **文档驱动优先**：先从文档中提取业务场景和验收标准，形成「业务视角」的用例骨架；再通过代码递归分析补充「实现视角」的分支覆盖和边界条件。两个视角交叉比对，确保既不遗漏业务需求，也不遗漏代码路径。

**操作步骤**：

#### Step 0: 开始生成测试计时

在开始测试用例设计之前，记录生成起始时间（用于 report 阶段的运行数据回传）：

```bash
GEN_CASE_START_TIME=$(date +%s.%N)
```

将起始时间（ISO8601 格式）写入 `context.gen_case_start_time`。

#### Step 1: 文档分析（第一输入源）

> **文档是测试设计的首要输入，必须在代码分析之前完成。** 即使文档不完整，也能提供代码分析无法替代的业务意图和验收标准。

1. **逐一阅读 `context.test_context_docs` 中的所有文档**，从每份文档中提取：

   | 提取维度 | 说明 | 示例 |
   |---------|------|------|
   | **业务场景** | 接口的典型使用场景、用户故事 | "用户在 TEA 平台发起 adhoc 查询时校验预算" |
   | **验收标准** | 功能正确的判定条件 | "白名单用户不受预算限制" |
   | **业务规则** | 条件判断的业务含义 | "非 CN 用户不计入预算消耗" |
   | **边界条件** | 文档中明确提到的限制和极端情况 | "同一 SQL 查询上限 50 次/周" |
   | **错误场景** | 文档中描述的异常处理 | "平台不支持时返回 5114 错误码" |
   | **数据格式** | 字段的编码/格式要求 | "privacy_extra 使用 URL query encoding" |

2. **文档类型优先级和提取重点**：

   | 文档类型 | 提取重点 | 对测试设计的价值 |
   |---------|---------|----------------|
   | `spec.md` | 功能规格、接口契约、状态机 | 定义「什么是正确的」— 正向用例的权威来源 |
   | `plan.md` | 实现方案、技术决策、依赖 | 定义关键路径和技术风险点 |
   | PRD | 业务场景、用户故事、验收标准 | 定义「用户怎么用」— 端到端场景的来源 |
   | 技术设计文档 | 架构、时序、错误处理策略 | 定义异常处理的预期行为 |
   | CHANGELOG / 历史 bug | 变更历史、已知问题 | 定义回归测试重点 |
   | 用户口述 | 隐性知识、特殊场景 | 补充文档未覆盖的边界条件 |

3. **产出**：提取结果汇总为**业务场景清单**（写入 test_plan.md 的「文档分析」部分）：

   ```markdown
   ### 文档分析结果

   #### 来源文档
   - specs/xxx/spec.md — 功能规格
   - 用户口述 — "白名单用户跳过预算检查"

   #### 提取的业务场景
   | # | 场景 | 来源 | 预期行为 |
   |---|------|------|---------|
   | S1 | TEA 平台 adhoc 查询 | spec.md §3.1 | 校验预算，预算不足返回 5109 |
   | S2 | 白名单用户查询 | 用户口述 | 跳过所有预算检查，直接放行 |
   | S3 | 非 CN 用户查询 | spec.md §3.4 | 不计入预算，直接放行 |
   ```

4. **无文档时的处理**：
   - 如果 `context.test_context_docs` 为空且用户未提供任何补充 → **在测试方案中明确标注**：
     - 「⚠️ 无参考文档输入，以下用例完全基于代码分析设计，可能遗漏业务层面的验收标准和使用场景」
   - 仍然继续进入 Step 2 代码分析，但建议用户在确认阶段补充业务背景

#### Step 2: 递归调用链分析（代码视角补充）

> **在文档分析的基础上**，通过代码递归分析发现文档未覆盖的实现细节、隐含分支和边界行为。不可局限于最外层方法，必须逐层递归到叶子节点。

**分析方法**：

1. **绘制完整调用树**：从 Handler 入口开始，对每个调用的函数递归展开，形成树状结构
2. **标注每个节点**：
   - 函数签名和所在文件
   - 所有可能的返回值（成功值、错误码、nil）
   - 外部依赖（RPC、MySQL、Redis、TCC、HTTP 等）
   - 条件分支（if/switch 的每个分支走向）
   - 错误是否向上传播（有些层会吞掉错误只记 metrics）
3. **识别关键分支点**：
   - 白名单/黑名单短路
   - 过滤器（filter）跳过后续逻辑
   - 参数校验失败提前返回
   - 平台/场景/类型的 switch 分支
   - 大小写敏感、类型断言等隐含行为
4. **识别"存在但不可达"的路径**：如常量已定义但 switch 未覆盖、枚举值存在但转换函数不接受等

**产出**：一份完整的调用链文档（写入 test_plan.md），格式示例：

```
HandlerFunc
├── SubFuncA
│   ├── ExternalRPC (3 retries) → nil on failure
│   └── MySQLQuery → error swallowed, metrics only
├── FilterX → true: skip downstream; false: continue
├── ValidateY → error: ErrorCodeXxx (code)
└── BusinessLogicZ
    ├── RedisCheck → threshold N → ErrorCodeYyy
    ├── TrafficFilter → non-target: skip
    └── CoreJudgment → MySQL → match/exempt/exceed
```

#### Step 3: 交叉比对与差异分析

> **将文档分析（业务视角）和代码分析（实现视角）进行交叉比对**，识别两者的差异和互补点。

1. **文档有提到但代码中未发现的场景** → 可能是文档过期或代码待实现 → 标记为「⚠️ 待确认」用例
2. **代码中存在但文档未提到的分支** → 可能是实现细节或防御性编码 → 标记为「代码发现」用例
3. **文档描述与代码实现不一致** → 可能是 bug 或文档过期 → 标记为「⚠️ 文档-代码不一致」，在测试方案中高亮提醒用户

**产出**：差异分析表（写入 test_plan.md）：

```markdown
### 文档-代码交叉比对

| # | 项目 | 文档描述 | 代码实现 | 差异 | 处理 |
|---|------|---------|---------|------|------|
| 1 | 平台校验 | 支持 tea/shuttle/holmes | switch 还覆盖 arena/clickhouse/hive | 代码更多 | 补充用例 |
| 2 | explain 过滤 | 未提及 | HasPrefix 大小写敏感 | 仅代码 | 标记为代码发现 |
| 3 | dataset 场景 | spec 中列为合法场景 | StrToDPQueryScene 不接受 | 不一致 | ⚠️ 高亮 |
```

#### Step 4: 分类设计测试用例

基于文档分析和代码分析的双重输入，按以下 **六个分类** 系统性设计用例：

**A. 业务场景用例（Business Scenario）**— 来自文档的端到端场景

- 直接对应文档中提取的业务场景（Step 1 的场景清单）
- 每个业务场景至少一个 P0 用例
- 用例的预期结果以**文档中的验收标准**为准
- `source` 字段标注来源文档和章节

**B. 正向用例（Positive）**— 覆盖合法输入维度组合

- 为代码分析发现的每个合法输入维度组合设计用例
- 与业务场景用例互补（覆盖文档未明确但代码支持的合法路径）
- 标注验证的完整调用链路径

**C. 白名单/特殊路径（Special Path）**— 覆盖短路和特殊逻辑

- 白名单用户、特殊条件触发的标记设置
- 参数组合触发的特殊分支

**D. 分支覆盖（Branch Coverage）**— 覆盖代码中的条件分支

- 过滤器的正反两面（如大小写敏感需分别测试）
- switch/if 的每个分支
- "存在但不可达"的路径
- 边界值和默认值路径

**E. 异常用例 — 参数校验（Negative - Param）**

- 缺少必填字段（逐个缺少）
- 格式错误（编码错误、类型错误）
- 空值和 nil 路径

**F. 异常用例 — 业务错误（Negative - Business）**

- 不支持的枚举值
- 下游依赖返回错误
- 业务限制触发（来自文档的错误场景）

#### Step 5: 用例质量要求

每个测试用例必须包含以下字段：

| 字段 | 说明 | 必填 |
|------|------|------|
| `id` | 用例唯一标识（如 TC001） | 是 |
| `name` | 用例名称 | 是 |
| `priority` | P0（核心路径）/ P1（重要分支）/ P2（边界/极端） | 是 |
| `category` | business_scenario / positive / special_path / branch_coverage / negative_param / negative_business | 是 |
| `source` | 用例来源：`文档:spec.md §3.1` / `代码分析:budget.go L123` / `用户口述` / `交叉比对` | 是 |
| `request` | 完整的请求体 | 是 |
| `expected` | 预期响应（状态码、关键字段值） | 是 |
| `call_chain_verification` | 该用例验证的调用链路径描述 | 是 |
| `notes` | 设计理由，解释为什么选择这个输入组合 | 是 |
| `is_write` | 是否为写操作（写操作执行前须用户确认） | 是 |
| `dependencies` | 该用例依赖的外部环境/数据前置条件（无依赖时为空数组） | 是 |

#### Step 6: 构造测试数据与外部依赖处理

> **核心原则**：集成测试不同于单元测试，外部依赖（RPC、Redis、MySQL、TCC 等）是真实调用而非 Mock。必须在用例设计阶段识别所有外部依赖，并制定数据准备方案。

**6.1 构造请求体**：

- 根据接口 Schema 和业务逻辑构造每个用例的请求体
- 注意字段的编码格式（如 URL encoding vs JSON，从 ParseXxx 函数的实现确认）
- 写接口的测试数据需标注 `⚠️ 写操作`

**6.2 外部依赖识别与处理**：

从 Step 2 的递归调用链分析中，提取每个用例涉及的外部依赖，按以下规则处理：

| 依赖类型 | AI 可自行构造 | 需用户手动操作 |
|---------|:---:|:---:|
| **TCC 配置** | ✅ 可通过 `tcc-query` 查询现有值确认；可通过 `tcc-deploy` 写入测试配置 | 如涉及生产 TCC namespace 的修改，需用户确认 |
| **Redis 数据** | ✅ 可通过 `redis` Skill 查询现有值 | ❌ 写入测试数据需用户操作（或提供 redis-cli 命令） |
| **MySQL/DB 数据** | ✅ 可通过 `rds` Skill 查询现有数据确认 | ❌ 插入/修改测试数据需用户操作（提供 SQL 语句） |
| **RPC 下游服务** | ❌ 无法控制下游返回 | 提供可用的测试入参（如已知存在的用户名）；或建议使用白名单/Mock 绕过 |
| **测试账号** | ✅ 可通过 `integration-testing-knowledge` 的 `get_occupied_user.py` 获取 | 如脚本不可用则需用户提供 |

**6.3 依赖处理流程**：

对每个用例的 `dependencies` 逐一处理：

1. **AI 可自行处理的依赖**：
   - 查询确认当前环境的 TCC 配置值（如白名单列表），确保测试入参与实际配置匹配
   - 查询 Redis/DB 中是否存在测试需要的数据
   - 调用相关 Skill 自动完成数据准备
   - 将实际查询结果更新到用例的 `request` 中

2. **需用户手动操作的依赖**：
   - 汇总所有需要用户操作的依赖项，在测试方案确认时一并展示
   - 提供**可直接执行的操作指令**（SQL 语句、Redis 命令、平台操作步骤等）
   - 在展示模板中新增「前置依赖准备」部分：

   ```markdown
   ### 前置依赖准备

   以下依赖项需要在测试执行前准备就绪：

   #### AI 已自动完成
   | # | 依赖 | 操作 | 状态 |
   |---|------|------|------|
   | 1 | TCC budget_white_list | 查询确认包含 tea_query | ✅ 已确认 |

   #### 需用户手动操作
   | # | 依赖 | 关联用例 | 操作指令 | 说明 |
   |---|------|---------|---------|------|
   | 1 | MySQL budget 表测试数据 | TC_xxx | `INSERT INTO budget (...) VALUES (...)` | 需要在 PPE 环境的 DB 中插入测试预算记录 |
   | 2 | Redis 同查询计数 | TC_xxx | `SET sq_tea_dept1_grp1_sqlhash 49` | 设置计数为 49 以测试临界值 |

   > 请完成上述操作后回复 "已完成"。
   ```

3. **无法满足的依赖**：
   - 如某些依赖在 PPE 环境中无法构造（如下游 RPC 服务未部署在 PPE），标记该用例为 `blocked`
   - 提供替代方案（如使用白名单用户绕过该依赖路径）

**6.4 依赖绕过策略**：

当外部依赖难以构造时，优先使用以下策略绕过：

| 策略 | 适用场景 | 示例 |
|------|---------|------|
| **白名单用户** | 下游 RPC 不可用时，白名单用户跳过 RPC 调用 | 使用 `tea_query` 跳过 GetEmployeeBaseInfo 的 RPC |
| **过滤路径** | 某些输入组合可跳过特定依赖 | 使用 `query_scene=dataset` 跳过 startBudgetCalc |
| **空值路径** | 空 privacy_extra 不触发任何下游调用 | 空 privacy_extra 走默认 "other" 路径 |
| **拆分用例** | 将一个复杂用例拆为多个，各自只触发部分依赖 | 拆分为"白名单路径"和"非白名单路径"两个用例 |

#### Step 7: 识别需要验证的 Metrics 指标

- 遍历调用链中所有 Metrics 打点调用（如 `metrics.EmitCounter`、`UploadFuncCallMetrics` 等）
- 记录指标名称、预期标签（tags）、预期变化（如计数+N、延迟有值）
- 特别关注错误路径的 metrics（如解析失败、下游调用失败的 metrics）
- 写入 `context.metrics_to_verify`

#### Step 8: 展示测试方案供用户确认

```markdown
## 测试方案

### 测试环境
- **Env Type**: {context.env_type}
- **VRegion**: {context.test_vregion}
- **VDC**: {context.test_vdc}

### 文档分析结果
{Step 1 的业务场景清单}

### 完整调用链分析
{Step 2 的调用树}

### 文档-代码交叉比对
{Step 3 的差异分析表}

### 测试用例 ({total} 个)

#### A. 业务场景用例 ({count} 个) — 来源：文档

| # | 用例名称 | 来源 | 优先级 | 预期行为 |
|---|---------|------|--------|---------|
| 1 | ... | spec.md §3.1 | P0 | ... |

#### B. 正向用例 ({count} 个) — 来源：代码分析
...
#### C. 白名单/特殊路径 ({count} 个)
...
#### D. 分支覆盖 ({count} 个) — 来源：代码分析
...
#### E. 异常 — 参数校验 ({count} 个)
...
#### F. 异常 — 业务错误 ({count} 个)
...

### 待验证 Metrics ({count} 个)

| # | 指标名 | Tags | 预期变化 |
|---|--------|------|---------|
| 1 | func_call | func=xxx, code=0 | +N |

### 测试数据来源
- 文档来源：{列出使用的文档及提取的场景数}
- 代码分析：{列出分析的文件数和调用链层数}
- 交叉比对发现：{不一致项数 + 仅代码发现项数}

> 回复 "确认" 开始提交代码；回复修改意见调整用例。
> ⚠️ 标记为写操作的用例，执行时将再次征求确认。
```

#### Step 9: 结束生成测试计时

用户确认测试方案后，记录生成结束时间并计算总耗时（用于 report 阶段的运行数据回传）：

```bash
GEN_CASE_END_TIME=$(date +%s.%N)
GEN_CASE_COST=$(echo "$GEN_CASE_END_TIME - $GEN_CASE_START_TIME" | bc -l)
```

- 将结束时间（ISO8601 格式）写入 `context.gen_case_end_time`
- 将总耗时（秒，浮点数）写入 `context.gen_case_cost`

**退出条件**：用户确认测试方案

**产出文件**：
- `test-design/test_plan.md`（测试方案全文，含文档分析 + 调用链 + 交叉比对）
- `test-design/test_cases.json`（结构化的测试用例列表 + 测试数据 + 来源标注）

> 完成检查：两个文件都存在且 `test_cases` 非空 → 标记 completed

---

### Phase 2: code_submit（代码提交推送）

> **目标**：确保测试代码在远程分支上可用，为 PPE/BOE 部署做准备。

**入口条件**：`test_design` 已完成

**操作步骤**（必须在终端实际执行）：

1. **判断当前场景**：

   **场景 A：有代码变更需要提交**（`git status` 显示有修改的业务代码）
   - `git add .`（或根据用户指示选择性 add）
   - `git commit`（基于变更内容自动生成提交信息）
   - `git push -u origin <branch>`（分支名从 `context.branch` 读取）

   **场景 B：无代码变更，仅测试已有接口**（常见于测试 master 上的存量功能）
   - **master/main 分支不能直接部署到 PPE**，必须创建测试分支
   - 如果当前在 master/main → 创建测试分支：`git checkout -b test/<接口名>-integration`
   - 推送测试分支：`git push -u origin test/<接口名>-integration`
   - 更新 `context.branch` 为新分支名

2. **记录提交信息**：commit hash（如有）、分支名、推送状态

**自动推进规则**：Push 成功后，**无需询问用户，直接进入 `deploy` 阶段**。

**退出条件**：远程分支上有可部署的代码

**产出文件**：`code-submit/submit_info.json`（分支、commit hash、push 状态、变更文件列表、场景类型 A/B）

> 完成检查：`submit_info.json` 存在且 `push_success=true` → 标记 completed

---

### Phase 3: deploy（环境部署）

> **目标**：通过 Env Platform 创建或复用 PPE/BOE 环境，部署服务并等待就绪。
>
> 使用 `env` Skill。**调用前必读该 Skill。**

**入口条件**：`code_submit` 已完成

**操作步骤**：

1. **确认部署目标**（从 `context` 读取）：
   - `env_type`：`ppe` 或 `boe`（pre_check 阶段用户已选择）
   - `test_vregion`：VRegion（如 `Singapore-Central`）
   - `branch`：部署分支

2. **检查是否有可复用的环境**：
   - 构造环境名：`ppe_<简短标识>`（如 `ppe_privacy_query_test`）或使用用户指定的名称
   - 调用 `env` 的 `detail` 查询该环境是否已存在：
     - **环境已存在** → 使用 `dsl_deploy`（DSLUpdate）升级服务版本
     - **环境不存在** → 使用 `dsl_create`（DSLCreate）创建新环境并部署服务

3. **执行部署**：

   **新建环境（`dsl_create`）**：
   ```bash
   gdpa-cli run env --input '{
     "action": "dsl_create",
     "name": "<env_name>",
     "psm": "<context.psm>",
     "branch": "<context.branch>",
     "vregion": "<context.test_vregion>"
   }'
   ```

   **升级已有环境（`dsl_deploy`）**：
   ```bash
   gdpa-cli run env --input '{
     "action": "dsl_deploy",
     "name": "<env_name>",
     "psm": "<context.psm>",
     "branch": "<context.branch>",
     "vregion": "<context.test_vregion>"
   }'
   ```

4. **轮询部署状态**：
   - 从部署响应中获取 `deployment_id`
   - 调用 `dsl_status` 查询状态（传入 `deployment_id` 和 `name`）
   - 每 30 秒轮询一次，每次向用户简报当前步骤状态
   - 关注 tickets 中各步骤：`SCM compile` → `Create tce service` → `Create tce cluster` → `Check consul register status`
   - `status: success` → 部署成功
   - `status: failure` → 展示失败步骤和原因，提供选项：
     - 调用 `dsl_retry` 重试
     - 修复代码后回退到 code_submit

5. **记录部署信息**：将环境名写入 `context.test_env`

**自动推进规则**：部署成功后，**无需询问用户，直接进入 `test_execution` 阶段**。

**退出条件**：PPE/BOE 环境就绪 + 服务 status 为 running

**产出文件**：`deploy/deploy_info.json`（deployment_id、env_name、部署状态、VRegion、部署方式）

> 完成检查：`deploy_info.json` 存在且 `pipeline_success=true` → 标记 completed
>
> 部署失败时：记录失败详情（含失败步骤和原因），展示给用户选择重试、修复后重新部署或终止流程
>
> **环境清理提醒**：测试完成后（report 阶段），提醒用户及时清理 PPE 环境（`env` 的 `delete_env`），避免资源浪费。PPE 环境有自动回收机制，但主动清理是好习惯

---

### Phase 4: test_execution（测试执行）

> **目标**：按 test_design 阶段设计的测试用例，**全量**发起 RPC/HTTP 测试请求，记录结果。
>
> 使用 `bam-query` Skill。**调用前必读该 Skill。**

**入口条件**：`deploy` 已完成

**操作步骤**（必须在终端实际执行，禁止用本地单测或 Grep 替代）：

#### Step 0: ACL 鉴权预检查（在执行任何测试请求之前）

> BAM 平台使用固定的调用方 PSM `explorer.api.executor` 发起请求，无法更改。如果被测服务开启了 ACL 严格授权且未授权该 PSM，所有 BAM 请求都会被拒绝（通常表现为 `1601` 错误码或连接被拒）。**必须在执行测试前完成此检查。**

**检查流程**（使用 `neptune-acl` Skill，调用前必读该 Skill）：

1. **检查服务鉴定是否开启**：
   ```bash
   gdpa-cli run neptune-acl --session-id <sid> --input '{"action":"check_authen","callee":"<context.psm>","vregion":"<context.test_vregion>"}'
   ```
   - `authen_enabled: false` → **无 ACL 问题**，跳过后续检查，直接进入 Step 1
   - `authen_enabled: true` → 继续检查

2. **检查严格授权是否开启**：
   ```bash
   gdpa-cli run neptune-acl --session-id <sid> --input '{"action":"check_acl_enabled","callee":"<context.psm>","vregion":"<context.test_vregion>"}'
   ```
   - `acl_enabled: false` → **无 ACL 问题**，直接进入 Step 1
   - `acl_enabled: true` → 继续检查

3. **检查 BAM 调用方是否已授权**：
   ```bash
   gdpa-cli run neptune-acl --session-id <sid> --input '{"action":"check_acl_authorized","callee":"<context.psm>","caller":"explorer.api.executor","vregion":"<context.test_vregion>"}'
   ```
   - `authorized: true` → **BAM 已授权**，直接进入 Step 1
   - `authorized: false` → **BAM 未授权**，需要处理

4. **BAM 未授权时的处理**：

   向用户展示问题并提供操作方案：

   ```markdown
   ## ⚠️ ACL 鉴权问题

   被测服务 `{context.psm}` 开启了严格授权（ACL），BAM 的调用方 PSM `explorer.api.executor` **未被授权**。
   如果不处理，所有 BAM 测试请求将被拒绝。

   ### 解决方案（请手动操作）

   1. 打开 Neptune 平台：https://neptune.bytedance.net/
   2. 搜索服务 `{context.psm}`
   3. 进入「服务治理」→「准入控制 / ACL」
   4. 添加授权规则：
      - **调用方 PSM**: `explorer.api.executor`
      - **调用方集群**: `*`（或 `default`）
      - **方法**: `*`（全部方法）
      - **动作**: `允许`
   5. 保存并等待规则生效（通常 1-2 分钟）

   > 完成后回复 "已授权" 继续执行测试。
   > 如果不想修改 ACL，回复 "跳过" 将尝试继续执行（可能部分或全部请求失败）。
   ```

   - 用户回复「已授权」→ 重新执行 Step 0.3 验证授权状态，通过后进入 Step 1
   - 用户回复「跳过」→ 在 test_result.json 中标注 `acl_warning: true`，继续执行（预期部分请求可能失败）

**产出**：ACL 检查结果记录到 `history`（`action: "acl_precheck"`，`detail: "authen={on/off}, acl={on/off}, bam_authorized={true/false}"`）

#### Step 1: 加载用例并建立执行清单

从 `test-design/test_cases.json` 加载**全部**用例列表，建立执行追踪清单：

```markdown
## 执行清单 (共 N 个用例)

| ID | 名称 | 状态 |
|----|------|------|
| TC001 | xxx | ⏳ 待执行 |
| TC002 | xxx | ⏳ 待执行 |
| ... | ... | ... |
```

> **关键约束**：每个用例 ID 必须出现在清单中，不可遗漏。用例总数必须与 `test_cases.json` 中的 `test_cases` 数组长度一致。

#### Step 1.5: 前置依赖检查与准备

> 在执行任何用例之前，必须检查并完成所有外部依赖的准备工作。

1. **扫描所有用例的 `dependencies` 字段**，汇总去重得到完整的依赖项列表
2. **AI 自行处理的依赖**：
   - 查询 TCC 配置确认值是否符合预期（如 `tcc-query` 查询白名单列表）
   - 查询 Redis/DB 确认测试数据是否存在（如 `redis`、`rds` Skill）
   - 如发现实际值与用例假设不一致，更新用例的 `request` 或 `expected`
   - 每项处理完成后记录到 `history`
3. **需用户手动操作的依赖**：
   - 向用户展示待操作清单（含可直接执行的命令/SQL/操作步骤）
   - **等待用户回复「已完成」后才继续执行**
   - 如用户回复「跳过 {依赖项}」，将关联的用例标记为 `blocked`（不执行，在结果中标注原因）
4. **无法满足的依赖**：
   - 标记关联用例为 `blocked`，从执行清单中移除（不计入完整性校验的 `total`）

#### Step 2: 记录测试起始时间

写入 `context.test_start_time`（ISO8601）。

#### Step 3: 批量执行全部用例

**执行策略**：

1. **按优先级分批执行**：先 P0 → 再 P1 → 最后 P2
2. **每批并行发起**：同一优先级内的用例可以并行发起（多个 `bam-query` 命令同时执行）
3. **VRegion** 和 **Env** 参数**必须从 `context.test_vregion` 和 `context.test_env` 读取**
4. 使用标准 VRegion 值（如 `Singapore-Central`），不要传别名
5. 读接口直接测试；**写接口必须先征求用户确认**
6. 如有多个 VRegion/VDC，需分别测试每个组合

**每个用例执行后立即记录结果**：
- 请求体、响应体、响应码
- 是否与预期匹配（pass/fail/error）
- 失败或异常原因
- 更新执行清单状态（⏳ → ✅/❌/⚠️）

#### Step 4: 完整性校验（强制步骤，不可跳过）

全部批次执行完成后，**必须进行完整性校验**：

1. 统计已执行用例数，对比 `test_cases.json` 中的总数
2. 如果 `已执行数 < 总用例数` → **必须识别并补执行遗漏的用例**，不可直接进入下一阶段
3. 展示完整性校验结果：

```markdown
## 完整性校验
- 设计用例总数: {total}
- 已执行用例数: {executed}
- 遗漏用例: {missing_ids or "无"}
- ✅ 全部执行完毕 / ❌ 存在遗漏，需补执行
```

> **硬约束**：`已执行数 == 总用例数` 才可进入 Step 5。否则必须先补齐遗漏用例。

#### Step 5: 记录测试结束时间

- 写入 `context.test_end_time`（ISO8601）。
- 根据 `context.test_start_time` 和 `context.test_end_time` 计算测试执行总耗时（秒，浮点数），写入 `context.exec_cost`（用于 report 阶段的运行数据回传）。

#### Step 6: 展示执行摘要

```markdown
## 测试执行结果 ({executed}/{total} 用例已执行)

### A. 业务场景用例

| # | 用例 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| TC001 | ... | pns_code=0 | pns_code=0 | ✅ Pass |

### B. 正向用例
...（按 test_design 的六分类逐一展示）

### 汇总
- ✅ 通过: {pass}/{total}
- ❌ 失败: {fail}/{total}
- ⚠️ 异常: {error}/{total}
```

#### Step 7: 失败处理

如有用例失败或异常，展示回退选项：
- **A: 回退到 deploy** — 修复代码后重新提交部署
- **B: 继续** — 标记失败用例，继续日志检查
- **C: 直接出报告** — 跳到 report 阶段

**自动推进规则**：全部用例执行完成后（无论是否全部通过），如用户选择继续，**自动进入 `log_verify` 阶段**。

**退出条件**：**全部用例**执行完成（完整性校验通过）+ 用户确认下一步操作

**产出文件**：`testing/test_result.json`（每个用例的请求/响应/结果 + 汇总统计 + 完整性校验结果）

> 完成检查：`test_result.json` 存在且 `executed_cases` 长度 == `test_cases.json` 中的用例总数 → 标记 completed
>
> 回退时：`current_phase` 回退到 `deploy`，`test_execution` 标记 `failed`

---

### Phase 5: log_verify（日志检查）

> **目标**：通过 Argos 查询业务日志和错误日志，确认测试请求被正确处理、无非预期异常。
>
> 使用 `argos-query` Skill。**调用前必读该 Skill。**

**入口条件**：`test_execution` 已完成

**操作步骤**：

#### Step 1: 等待日志就绪

- Argos 日志可能有 **1-5 分钟延迟**
- 进入本阶段后，**先等待 60 秒**再开始查询
- PPE 日志合并到在线存储，VRegion 使用**在线 VRegion**（如 `Singapore-Central`），不要用 PPE VRegion

#### Step 2: 业务日志查询

验证测试请求是否被服务正确接收和处理：

1. **搜索业务关键字**：使用目标接口的 handler 方法名或业务日志关键字
   ```bash
   gdpa-cli run argos-query --session-id <sid> --input '{
     "action": "search",
     "psm": "<context.psm>",
     "keyword": "<接口方法名或业务关键字>",
     "start_time": "<context.test_start_time 前推 1 分钟>",
     "end_time": "<context.test_end_time 后推 5 分钟>",
     "vregion": "<context.test_vregion>"
   }'
   ```
2. **分析结果**：
   - 有日志 → 确认测试请求到达了服务端，检查日志内容是否与预期一致
   - 无日志 → 可能是日志延迟或 PPE 未配置 StreamLog，记录为 `inconclusive`

#### Step 3: 错误日志查询

检查测试期间是否产生了非预期的错误：

1. **搜索 ERROR 关键字**：
   ```bash
   gdpa-cli run argos-query --session-id <sid> --input '{
     "action": "search",
     "psm": "<context.psm>",
     "keyword": "error",
     "start_time": "<context.test_start_time 前推 1 分钟>",
     "end_time": "<context.test_end_time 后推 5 分钟>",
     "vregion": "<context.test_vregion>"
   }'
   ```

2. **搜索 PANIC 关键字**：同上，keyword 替换为 `panic`

3. **查询错误聚合统计**（如 Argos 支持）：
   ```bash
   gdpa-cli run argos-query --session-id <sid> --input '{
     "action": "error_overview",
     "psm": "<context.psm>",
     "start_time": "...",
     "end_time": "...",
     "vregion": "<context.test_vregion>"
   }'
   ```

#### Step 4: 日志分析与分类

对查询到的日志逐条分析，分为三类：

| 分类 | 说明 | 处理 |
|------|------|------|
| **预期内错误** | 异常用例（TC015-TC019）触发的错误日志，属于正常行为 | 标记为 expected，不计为问题 |
| **非预期错误** | 正向用例触发的 ERROR/PANIC，不应出现 | 标记为 unexpected，记录为问题 |
| **业务日志** | INFO 级别的正常业务日志 | 验证请求参数是否正确传递 |

#### Step 5: 重试机制

如果 Step 2 和 Step 3 均返回 0 条日志：

1. **第一次重试**：等待 60 秒后重新查询
2. **第二次重试**：扩大时间范围（前推 5 分钟、后推 10 分钟）重新查询
3. **仍无结果**：标记为 `inconclusive`，在结果中注明可能原因（PPE 未配置 StreamLog / 日志索引延迟），建议用户通过 TCE Pod 日志补充验证

#### Step 6: 结果判断与展示

```markdown
## 日志检查结果

### 业务日志
- 查询关键字: {keyword}
- 查询时间范围: {start} ~ {end}
- 匹配日志数: {count}
- 请求到达确认: ✅ 已确认 / ⚠️ 无法确认

### 错误日志
- ERROR 日志数: {count}（预期内: {expected_count}，非预期: {unexpected_count}）
- PANIC 日志数: {count}
- 非预期错误明细:
  | # | 时间 | 级别 | 内容摘要 | 关联用例 |
  |---|------|------|---------|---------|
  | 1 | ... | ERROR | ... | TC001? |

### 结论: ✅ 通过 / ⚠️ 不确定 / ❌ 发现问题
```

#### Step 7: 问题处理

如发现非预期错误，展示回退选项（同统一回退机制）。

**退出条件**：日志分析完成 + 用户确认结果

**产出文件**：
- `logs/verify_result.json`（验证结论、业务日志统计、错误日志分类统计）
- `logs/logs_summary.md`（日志分析摘要，人类可读）
- `logs/logs_raw.log`（原始日志，大量日志时写入）

> 完成检查：`verify_result.json` + `logs_summary.md` 都存在 → 标记 completed
>
> 回退时：`current_phase` 回退到 `test_execution`，`log_verify` 标记 `failed`

---

### Phase 6: tracking_verify（埋点检查）

> **目标**：通过 Metrics 查询验证关键业务指标是否正确上报。
>
> 使用 `metrics` Skill。**调用前必读该 Skill。**

**入口条件**：`log_verify` 已完成

**跳过判断**：`context.metrics_to_verify` 为空 或 用户明确不需要埋点检查 → 标记为 `skipped`，直接进入 `report`

**操作步骤**：

1. **读取待验证指标**：从 `context.metrics_to_verify` 获取指标列表
2. **查询 Metrics 数据**：
   - 使用 `metrics` Skill 按 PSM + 指标名 + 时间范围（测试期间 ± 5 分钟缓冲）查询
   - 根据 `context.env_type` 确定 VRegion：
     - PPE 环境使用对应 PPE VRegion（如 `Singapore-PPE`）
     - BOE 环境使用 BOE VRegion
   - 对每个指标检查是否有预期的数据上报

3. **验证结果判断**：
   - 对比查询结果与预期（如 Counter 应有增量、Timer 应有值）
   - 标记每个指标的验证状态（pass/fail/inconclusive）

4. **展示验证结果**：

```markdown
## 埋点检查结果

| # | 指标名 | 类型 | 预期 | 实际 | 状态 |
|---|--------|------|------|------|------|
| 1 | xxx_qps | Counter | +N | +3 | ✅ Pass |
| 2 | xxx_latency | Timer | 有值 | avg=15ms | ✅ Pass |
| 3 | yyy_error | Counter | +0 | +0 | ✅ Pass |

### 结论: ✅ 全部通过 / ⚠️ 部分异常
```

5. **问题处理**：如发现问题，展示回退选项（同统一回退机制）

**退出条件**：所有指标验证完成 + 用户确认

**产出文件**：`tracking/verify_result.json`（每个指标的查询结果和验证状态）

> 完成检查：`verify_result.json` 存在 → 标记 completed
>
> 回退时：`current_phase` 回退到 `log_verify`，`tracking_verify` 标记 `failed`

---

### Phase 7: report（报告产出）

> **目标**：汇总所有阶段结果，生成结构化的集成测试报告。

**入口条件**：`tracking_verify` 完成或跳过（或用户从任意阶段选择直接出报告）

**操作步骤**：

1. **汇总各阶段数据**：读取所有已完成阶段的产出文件

2. **运行数据回传**（默认执行，无需用户同意）：

   将集成测试的执行数据通过指定接口回传，字段列表与单测运行数据回传保持一致。

   - 从 `context` 与各阶段产出文件中取值：
     - `username` ← `context.username`
     - `scope` ← `context.scope`（`"all"` 或 `"incremental"`）
     - `file_num` ← `context.file_num`
     - `case_num` ← `testing/test_result.json` 中 `executed_cases` 的总数（等价于 `summary.total`）
     - `case_success_rate` ← `testing/test_result.json` 中 `summary.pass / summary.total`（0-1 之间的小数）
     - `code_cover_rate` ← 集成测试通常不直接测量代码覆盖率，默认填 `0`；如有覆盖率工具输出，则填实际值（0-1 之间的小数）
     - `gen_case_cost` ← `context.gen_case_cost`（测试用例设计阶段总耗时，单位：秒）
     - `exec_cost` ← `context.exec_cost`（测试执行阶段总耗时，单位：秒）

   执行以下 curl 请求：

   ```bash
   curl --location 'http://pns-ca-synapse-api-cn.byted.org/synapse_agent/v1/pns_quality_first/integration_testing_event' \
   --header 'Content-Type: application/json' \
   --data '{
       "version": "v1",
       "username": "XXX",
       "repo_name": "XXX",
       "psm": "XXX",
       "scope": "XXX",
       "change_code_lines": XXX,
       "file_num": XXX,
       "case_num": XXX,
       "case_success_rate": XXX,
       "code_cover_rate": XXX,
       "gen_case_cost": XXX,
       "exec_cost": XXX
   }'
   ```

   - **说明**：
     - **执行要求**：本步骤必须在任务结束前执行，严禁遗漏！
     - `version`：固定填 `"v1"`
     - `username`：通过 git config 获取的用户名（来源：`context.username`）
     - `repo_name`：仓库名，选填
     - `psm`：PSM信息，选填（来源：`context.psm`）
     - `scope`：测试范围，取值为 `"all"`（全量）或 `"incremental"`（增量）
     - `change_code_lines`：变更代码行数，选填；存量扫描（scope="all"）填 0，其他情况填实际变更代码行数
     - `file_num`：测试涉及的源代码文件数量
     - `case_num`：执行的测试用例总数
     - `case_success_rate`：测试成功率（0-1 之间的小数）
     - `code_cover_rate`：代码覆盖率（0-1 之间的小数，集成测试无覆盖率数据时填 0）
     - `gen_case_cost`：生成测试用例花费的总时间（秒）
     - `exec_cost`：执行所有测试用例花费的总时间（秒）
     - 回传成功或失败均不影响集成测试报告的生成，失败时将错误信息记入 `history`

3. **生成报告**：使用以下模板生成 `summary/report.md`

```markdown
# 集成测试报告

## 概述
- **PSM**: {context.psm}
- **分支**: {context.branch}
- **Commit**: {context.commit_hash}
- **测试环境**: {context.env_type} ({context.test_env})
- **VRegion**: {context.test_vregion}
- **测试时间**: {context.test_start_time} ~ {context.test_end_time}
- **BITS 任务**: {context.bits_link}

## 测试范围
- **变更接口**: {从 pre-check/task_config.json 读取}
- **测试用例数**: {total} (P0: {p0_count}, P1: {p1_count}, P2: {p2_count})
- **参考文档**: {context.test_context_docs}

## 测试用例结果

| # | 用例 | 接口 | VRegion | 状态 | 响应码 | 备注 |
|---|------|------|---------|------|--------|------|
| ... | ... | ... | ... | ... | ... | ... |

**汇总**: ✅ 通过 {pass}/{total} | ❌ 失败 {fail}/{total}

## 日志检查
### Trace Log
{从 logs/logs_summary.md 读取 trace 部分}

### Error Log
{从 logs/logs_summary.md 读取 error 部分}

## 埋点检查
{从 tracking/verify_result.json 读取，如 skipped 则标注"未执行"}

| # | 指标 | 状态 | 备注 |
|---|------|------|------|
| ... | ... | ... | ... |

## 问题记录
{汇总所有阶段发现的问题，包括回退历史}

## 结论
{整体结论：全部通过 / 存在问题需关注}
```

4. **展示报告摘要**：向用户展示关键结果

**退出条件**：报告生成完成 + 运行数据回传已执行

**产出文件**：`summary/report.md`

> 完成检查：`report.md` 存在 且 运行数据回传已执行（`history` 中存在对应条目）→ 标记 completed

---

## 三、状态文件规范

> 完整 status.json 结构见 [status-schema.md](status-schema.md)

### 3.1 状态更新规则

**必须在以下时机更新 status.json**：

| 时机 | 更新内容 |
|------|---------|
| 进入新阶段 | `current_phase`、该阶段 `status` → `in_progress`、`started_at` |
| 完成当前阶段 | 该阶段 `status` → `completed`、`completed_at`、`summary`；`current_phase` → 下一阶段 |
| 跳过阶段 | 该阶段 `status` → `skipped`、`summary` 注明跳过原因 |
| 阶段失败 | 该阶段 `status` → `failed`、`summary` 注明失败原因 |
| 回退阶段 | `current_phase` 回退、目标阶段 `status` → `in_progress` |
| 关键操作完成 | 追加 `history` 条目 |
| context 信息变更 | 更新 `context` 对应字段 |

### 3.2 各阶段产出文件

| 阶段 | 产出文件 | 完成检查条件 |
|------|---------|-------------|
| `pre_check` | `pre-check/task_config.json` | 文件存在且 psm 非空 |
| `test_design` | `test-design/test_plan.md` + `test-design/test_cases.json` | 两个文件都存在且 test_cases 非空 |
| `code_submit` | `code-submit/submit_info.json` | 文件存在且 push_success=true |
| `deploy` | `deploy/deploy_info.json` | 文件存在且 pipeline_success=true |
| `test_execution` | `testing/test_result.json` | 文件存在且 executed_cases 非空 |
| `log_verify` | `logs/verify_result.json` + `logs/logs_summary.md` | 两个文件都存在 |
| `tracking_verify` | `tracking/verify_result.json` | 文件存在（skipped 时无需产出） |
| `report` | `summary/report.md` | 文件存在 |

完整目录结构：

```
.gdpa/{session-id}/
├── status.json                    # 流程状态（核心，每步更新）
├── pre-check/
│   └── task_config.json           # pre_check 产出
├── test-design/
│   ├── test_plan.md               # test_design 产出（测试方案）
│   └── test_cases.json            # test_design 产出（结构化用例）
├── code-submit/
│   └── submit_info.json           # code_submit 产出
├── deploy/
│   └── deploy_info.json           # deploy 产出
├── testing/
│   └── test_result.json           # test_execution 产出
├── logs/
│   ├── verify_result.json         # log_verify 产出
│   ├── logs_summary.md            # log_verify 产出
│   └── logs_raw.log               # log_verify 产出（大量日志时）
├── tracking/
│   └── verify_result.json         # tracking_verify 产出（skipped 时不存在）
└── summary/
    └── report.md                  # report 产出
```

### 3.3 使用规则

1. **每步四拍节奏**：读 status → 执行操作 → 写产出文件 → 更新 status（缺一不可）
2. **产出文件是硬约束**：标记 `completed` 前必须先写入对应产出文件
3. **history 记录 wrote_file**：每次写入产出文件后，在 `history` 中追加 `{"action": "wrote_file", "detail": "文件路径"}`
4. **大输出走文件**：大体量输出（如 argos 日志）写入文件，对话 context 仅传摘要 + 文件路径
5. **Session 隔离**：每次测试流程使用独立 `session-id`，互不干扰
6. **Git 忽略**：`.gdpa/` 目录应加入 `.gitignore`
7. **Context 优先读 status**：PSM、分支、env、vregion、vdc 等信息统一从 `context` 读取，不重复询问用户
8. **Skipped 阶段无需产出**：被标记为 `skipped` 的阶段不需要写产出文件
9. **产出必须基于真实数据**：产出文件数据必须来自 `gdpa-cli` 命令的真实返回或实际执行结果，禁止编造
10. **使用标准 VRegion**：调用 `bam-query`、`argos-query`、`metrics` 等 Skill 时，vregion 参数必须使用标准值（`Singapore-Central`、`US-East`、`China-North`、`China-BOE`、`US-BOE`），不要传别名
11. **参考文档优先搜索**：test_design 阶段的参考文档优先在项目中自动搜索（spec.md、plan.md、docs/ 等），不足时再向用户索取

---

## 四、附加资源

- 完整 status.json 结构与初始化模板 → [status-schema.md](status-schema.md)
- 各阶段产出文件与状态更新 JSON 示例 → [phase-examples.md](phase-examples.md)
- 可用 Skill 速查与选择指南 → [skills-reference.md](skills-reference.md)
