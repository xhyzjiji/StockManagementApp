# Mobile SDT（Spec Driven Test）× Verify Loop

> 技术方案：《TTADK Mobile SDT & Verify Loop 技术方案》
> https://bytedance.larkoffice.com/wiki/LTkQwTfY8ivuUqkmpOcczT9angg

与 SDD 平行的测试工作流：`adk-sdt-ff`（spec → 用例）→ `adk-sdt-implement`（执行 + 报告）。
`adk-sdt-clarify` 是**可选**的按需环节——对生成的 `case.md` 不满意时用它澄清修订并采集批准；新生成的用例
可直接执行。批准一旦存在即具约束力（sha 绑定，改了已批准的用例会被拦），详见下方「阶段门禁」。参考服务端
实现（`plugins/ttadk/core/skills/adk-sdt*`）迁移，按移动端裁剪。

## 架构

```
SDD (spec.md / plan.md)
        │
        ▼
adk-sdt-ff ─────────► test/case.md   ← 人工 review 与平台验证工作流 --spec 的同一份输入
        │             test/task.md   ← 平台无关执行计划
        │
        ├──（可选，对用例不满意时）adk-sdt-clarify
        │     多轮澄清，修 case → 复核干净后写 clarify_approved 事件（绑定 case.md sha）
        │
        ▼  ◄── 阶段门禁：无 case.md 即 STOP；批准存在但 sha 不匹配（批准后又改了 case.md）即 STOP
adk-sdt-implement           （从未 clarify → 放行，CLARIFY: not_run；check-prerequisites --require-clarify）
        │
        ├─ T001 解析 VERIFY_WORKFLOW（profiles 查表 + host skill 发现）★唯一平台分叉点
        │        ├─ ios     → harness-workflow（别名 infra-ios:harness-workflow）
        │        └─ android → harness-workflow（别名 infra-android:harness-workflow）
        │           ↑ 同名，两套独立实现；差异由各自 SKILL.md 消化，T002 只交配置
        ├─ T002 驱动 workflow 至终态：build + lint + E2E
        │        └─ 小循环内部闭环：build fix / lint fix / 用例 wave fix（--fix，不外抛确认）
        └─ T003 读 workflow 报告工件 → test/report.md
```

与 SDD verify loop 的关系（iOS）：

> 术语：这里的 **Verify Loop 指 ttadk 四阶段循环**（技术方案图里那个），不是 harness-workflow 内部的 pipeline
> DAG——harness 只是其中两个 stage 的**执行器**。

| Verify Loop 阶段 | 由谁喂 | 执行器 | 启动依赖 |
|---|---|---|---|
| Agent Code Review | `sdd:implement` | ai-sde playbook（不变） | 代码写完（`code_complete`） |
| Build & Lint Test | `sdd:implement` | **harness-workflow `--run-mode build`** | Code Review 完成 |
| Unit Test | `sdd:implement` | harness `unit_test` stage / ai-sde playbook | Build & Lint 完成 |
| **E2E Test** | **`sdt:implement`** | **harness-workflow `--run-mode verify`**（只跑 E2E，复用产物） | **双向汇合**（见下） |

**E2E 的启动是两条 lane 的汇合，谁先到谁等**：

- **lane A（SDT 侧）**：`sdt:ff` 产出 `test/case.md`——没有它 E2E 没有输入（`sdt:clarify` 可选，不在 lane 上）；
- **lane B（verify loop 侧）**：本轮的 Code Review + Build & Lint + Unit Test 全部完成——E2E 要跑在它们刚
  验证过的那份代码上。

所以 SDT 侧快了就在汇合点等 lane B，verify loop 快了就等用例文件；两个条件都满足前不得调用
`sdt:implement`（早调用要么在执行器里干等，要么装上旧包验错版本）。

顺序保持 ttadk 原有逻辑：**小循环** Code Review → Build & Lint → Unit Test（SDD 流程内，gate `spec_completed`），
之后才是 **大循环** SDT → E2E（SDD 核心流程之外）。harness-workflow 只是替代直接使用原子能力的 build + lint + e2e，
是原能力的超集：外部只需指定本地/远端（`execution_mode`，iOS 构建另有 `build_mode: local|airbuild`）。本期 MVP
默认全 local。

### SDD → SDT 自动衔接（ai-sde `e2eTest` 开关）

**SDT ≠ E2E**：SDT 是与 SDD 平行的测试工作流（ff → implement，clarify 可选），输入是 SDD 产出的 spec 目录
（`spec.md` / `plan.md` / `explore.md`），产出 `test/case.md`；E2E Test 是 verify loop 的一个 stage，由
`adk-sdt-implement` 驱动，产出 `test/report.md`。

Verify loop 分两层（技术方案原文）：

| 层 | 内容 | 位置 | 失败处理 |
|---|---|---|---|
| **小循环** | AI Code Review、Build & Lint、Unit Test | 集成在 SDD 流程内 | subagent 内自动修复即时收敛；**它才是 `spec_completed` 的门禁** |
| **大循环** | E2E Test、回归测试 | **SDD 核心流程之外** | 人主导：经 `/adk:sdd:clarify` 反哺 spec，或 `/adk:sdd:ff` 起轻量 bugfix 流程 |

SDT 三个 skill 可独立手动使用。当 ai-sde 的 `config.toml` 开 `e2eTest = true` 时，SDD 会在 `spec_completed`
**之后**自动衔接 SDT 大循环（FF 流与标准流 guide 各新增一节，并进入 CORE 流程图与阶段索引）：

- `adk-sdt-ff`（`case.md` 缺失时）→ `adk-sdt-implement`（驱动 E2E → `test/report.md`）；
  `adk-sdt-clarify` 可选——对用例不满意时澄清修订并采集批准（lark-cli 可用时把 case.md 上传成
  **飞书文档**供用户查看确认，否则终端确认；批准一旦记录即 sha 绑定）；
- **不 gate `spec_completed`**：大循环在 SDD 核心流程之外，小循环 clean 即可完成 spec；
- **并行 + 硬依赖**：ff 只依赖已完成的文档，implementation 阶段一开始就**强制**后台派发（SDD 2.5 /
  FF 2.5 节），主 agent 立即回到任务循环——用例生成与编码、小循环重叠进行；
  E2E 消费的是 **case.md（ff 产物）**，所以 implement 处是**阻塞式 join**：备料没跑完就等，绝不跳过；
  clarify 是可选环节，不在 join 里等批准——但若用户已批准过且 case.md 又被改（stale），
  `adk-sdt-implement` 的 `--require-clarify` 前置检查会独立拦截，要求重新 clarify；implement 还需
  可构建产物，因此始终等小循环 clean；
- FAIL 归因路由：`case_defect` → `adk-sdt-clarify` 修用例（批准 sha 失效自动要求重批）后 rerun；
  `code_defect` → 呈报证据由用户选择 `/adk:sdd:clarify` 反哺 spec 或 `/adk:sdd:ff` 起 bugfix（修复重新
  走一遍小循环，不在 E2E 步骤里直接手改产品代码）；`env_blocker` → 上报用户；
- 状态衔接（**两端的状态模型不同，按各自 SKILL.md 处置，不要按另一端推**）：
  - **iOS**：状态在仓内 `.harness/`。Compile & Lint 留下的 build 态 pipeline 会被 implement 的
    stale-pipeline guard 先 `--archive` 再初始化 full 管线。
  - **Android**：状态在仓外（`~/.android-harness-workflow/`），一轮一目录，**没有 `.harness/context.json`，
    也没有 `--archive` 这个动词，也没有任何东西会拦你**——上一轮什么状态都不阻止起新一轮，没有强起的
    flag，既没有拒绝信息可循，也没有残留状态要清。**读到上一轮的唯一方式是没声明这是新的一轮**，而那个
    失败是静默的：你会拿到一份格式完好、内容属于别轮的报告。显式起新一轮，记下它返回的 run 标识，
    之后每条命令都核对。

## 版本依赖

| 能力 | 依赖 | 不满足时 |
|---|---|---|
| `adk-sdt-implement` iOS 分叉 | 宿主装有 `harness-workflow`（infra-ios） | T001 STOP + 接入指引 |
| `adk-sdt-implement` Android 分叉 | 宿主装有 `harness-workflow`（infra-android），且该 skill 目录已 `npm ci`（它的 CLI 在 `dist/` 里，执行方 `mobile-ai-test` 也随依赖树装） | T001 解析得到但跑不起来 → 停在 T002，原样带回它自己的诊断 |
| `UNIT_TEST=true`（verify loop 第三环） | 那一端的验证工作流认 `--with-unit-test`（今天只有 iOS 的新版；Android 认得但只记账不执行） | T002 探测不到 → 显式告知本轮不跑单测（iOS 旧版会静默吞掉该参数） |

## 环境准备（可选增强）

SDT 三命令零硬依赖，开箱即用。用例生成默认委托 `ui-md-case-gen`——它所在的 `tt-nova-ui` 包（连同
`tt-nova-common`）已 **vendored 进 mobile-core**（`skills/tt-nova-ui@1.0.156`、`skills/tt-nova-common@1.0.126`），
随插件一起分发，**无需任何安装、不依赖网络**。vendored 副本移除了上游的「每日自更新」前置步骤（版本确定、
离线可用；自更新中断会留空壳目录导致探测假阳性——实测踩过），升级方式见各自 SKILL.md 的「版本说明」。
探测契约不变：`TEXT_CASE_GENERATE_PROBE` 必须是**非空文件**；`TEXT_CASE_GENERATE_INSTALL` 置空 = 禁用懒装，
探针失败说明插件安装不完整（`ttadk plugin update ttadk/mobile-core`），ff 会自撰兜底、不报错。

想临时覆盖为官方最新版（可选；下次 `ttadk plugin update` 还原为内置版本）：

```bash
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-ui --agent claude-code --yes
```

环境体检走 `adk-doctor`（Stage A 已含 tt-nova-ui 可选项检查：缺失 = ⚠️ 提示，不影响就绪结论——运行时 ff 会自己装）。

## 目录契约

```
FEATURE_DIR/                  # .adk-mobile/specs/<NNN-name>/（或 .ttadk/specs/、specs/）
├── spec.md / plan.md         # SDD 产物（输入）
└── test/
    ├── case.md               # ff 产物；只含用例本身（TC 区块 + 用例表执行索引）——执行参数在 task.md
    ├── task.md               # ff 产物；平台无关执行计划（T001/T002/T003）
    ├── report.md             # implement 产物；按 sdt-report-template 填写
    └── events.jsonl          # 阶段事件流（ff_generated → [clarify_approved 可选] →
                              #   implement_completed → report_reviewed），每条绑定当时 case.md 的
                              #   sha256；clarify_approved 一旦存在即是 implement 的 stale 门禁依据
.test-harness-workflow/       # 仅 remote-agent 形态：spec 的运输副本（`.ttadk/` 被某些仓 gitignore，
                              #   同步不进容器；这里放一份逐字副本供 --spec 指向，判据仍是 test/case.md）
<验证工作流的产物目录>         # 位置由该工作流决定，别写死：iOS 是仓内 .harness/（Validation.md/html、截图、
                              #   worker 结果）；Android 在仓外的状态目录里（summary.json 是判据），
                              #   它会把绝对路径打出来
```

## 阶段门禁（可选 clarify，批准一旦存在即具约束力）

clarify **不是必经环节**：ff 生成的用例可直接执行，clarify 是对 `case.md` 不满意时的按需澄清修订通道。
门禁机制由 `resources/scripts/sdt-events.js` + `check-prerequisites.js --require-clarify` 本地执行：

- `adk-sdt-clarify` 复核干净（无未决产品决策）后**采集用户批准**再写 `clarify_approved` 事件（绑定 `case.md`
  sha256）。批准通道双轨（SDD-FF 式轻量飞书审批，比 dashboard 网页卡更轻）：lark-cli 可用时把 `case.md` 上传成
  **飞书文档**（`bytedcli lark docs create`，同 feature 重澄清 overwrite 同一篇，url 持久化在
  `test/lark-case-doc.json`）供用户查看后确认，文档内评论/改动拉回本地作为修订反馈——`case.md` 始终是唯一
  存储，文档只是 review 面；不可用时回落终端对话确认。事件里 `channel` 字段记录采集通道（lark 附 docUrl）。
  （dashboard `approvals` `category='sdt'` 基建保留兼容，不再是默认通道）；
- `adk-sdt-implement` pre-check 跑 `--require-clarify`：无 `case.md`（no_case）STOP 指去 ff；从未 clarify
  （missing）**放行**并在开跑摘要里提示 clarify 可用；批准后 `case.md` 被改（stale，sha 不匹配）STOP 要求
  重新 clarify——**改了已批准产物即废批准**，批准是契约不是仪式；
- 事件只能由 clarify 流程写入；agent 不得代录、不得绕过（防呆非防恶意——本地无服务端，这是能做到的上限）；
- **报告同样要人确认**：`adk-sdt-implement` 产出 `test/report.md` 后，走**与 case 批准同一条飞书通道**
  （report.md 上传成飞书文档 + 对话内确认，url 持久化在 `test/lark-report-doc.json`），approved 才记
  `report_reviewed` 并宣告验证完成；needs_revision / rejected 按 FAIL 归因路由处理，不得在未确认时收工。
  无 lark-cli 时同样回落终端确认；
- 小循环不受影响：implement/harness 的 wave fix 只改代码与 `task.md`/`report.md`，不碰 `case.md`，批准不失效。

## Android 接入

设计目标始终是：**接入一个新平台不改任何 SDT 逻辑**。SDT 只认 `VERIFY_WORKFLOW` 这一个逻辑能力，
平台分叉只发生在 T001 解析出的那个技能名上。

**Android 已接入**：`infra-android` 插件自带一个同样叫 `harness-workflow` 的技能——**与 iOS 那个同名，
但是两套独立实现**。宿主同时装了两个插件时，
裸名解析可能命中另一端，所以 profiles 里给了带命名空间的别名兜底。

### 两端怎么对齐的（决定了 T002 该怎么写）

不是让两端的 CLI 长成一样——**消费方是 Agent，翻译发生在它读 `SKILL.md` 那一刻**。所以对齐做在
SKILL 语义层：

- **T002 交出去的是一段「执行配置」**（task.md 的 Input 键值），不是拼好的命令行；
- **键名就是 flag 名**：下划线换横线（`remote_model` → `--remote-model`）后两端都直接命中，
  谁都不需要维护翻译表 —— 这是「不替它拼命令行」能成立的前提，键名与 flag 名一旦分家，
  一端硬停、另一端静默吞掉；
- 上游因此不需要知道那边是 `--run-mode` 还是 `--preset`、是 `--verify <stage>` 还是 `submit --nonce`。

**别指望「不支持的键」会有回声。** 一端把忽略项记进结论（可审计），另一端什么都不留 ——
交完之后**核对它复述的配置**（读它的状态/结论文件），不要等一条不会来的报错。

**照一端的 flag 拼给另一端会出事**：Android 的参数解析对不认识的 flag **当场硬停**，iOS 的则会静默吞掉
（`*) shift`）——后者更危险，那一跑照常跑完，只是你要的那件事从没发生过。

### 接入另一个平台时要做的

1. 实现该平台的验证工作流 skill，其 `SKILL.md` 必须能吃 task.md Input 那套键并驱动自己到终态；
2. 在宿主工程安装它（或加进该平台的 preset）；
3. `sdt-skill-profiles.json` 填 `profiles.mobile.<平台>.VERIFY_WORKFLOW`（可加 `VERIFY_WORKFLOW_ALIASES`、
   `DEFAULT_EXECUTION_MODE`）。

契约要求：接受一份 `--spec <case.md>`（本模板格式）；自含它承诺的那几段执行；失败修复内部闭环、不向
调用方外抛中间确认（**代码落地除外**——远端形态下容器改的代码回传本机时必须由人裁决）；产出报告工件，
其中至少一份是**机器可读、有 schema** 的结论。

## 用例生成能力（TEXT_CASE_GENERATE）

默认委托 **`ui-md-case-gen`**（TTAT `tt-nova-ui` 包；`adk-sdt-ff` 把 `sdt-case-template.md` 作为输出格式契约传给它），
未安装时 ff 自生成兜底、不阻塞。宿主安装命令：

```bash
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-ui --agent claude-code --yes
```

选型说明：ui-md-case-gen 产物即"AI 可执行 UI 用例"（明确入口/页面路径/可观察断言），格式与本模板同源
（testcase-normalize 规范），依赖轻（PRD→case 模式零外部服务）。prd2case/prd2case-pipeline（QA 测试分析资产、
Bits 用例管理）不再随插件分发；QA 级分析/Bits 协同场景由用户显式走 QA 链路。

## MVP 范围（本期）

- ✅ 双端通用 ff / clarify / implement；iOS 经 harness-workflow 本地跑通 build + lint + E2E + wave fix + 报告
  （TikTok_wt_9 实测通过）。
- ✅ `TEXT_CASE_GENERATE=ui-md-case-gen`（可选委托 + 自生成兜底）。
- ✅ Android VERIFY_WORKFLOW = `infra-android:harness-workflow`（独立实现，不是 iOS harness 里的 android adapter）。
- ⏸ feedback-loop / learning skills（移动端后续按需引入）。
- ⚠️ 已知工具链缺口（已反馈）：verify-loop `assert.visual` 当前为 MockJudge 占位（恒 PASS）——真 judge 接入前，
  `visual` 断言不得作为用例唯一验收断言，报告阶段需人工复核截图证据。
