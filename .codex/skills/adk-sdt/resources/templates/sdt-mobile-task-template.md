<!--
【语言适配规则 — 必须在生成 task.md 时执行】
preferred_language=en 时，将所有自然语言翻译为英文；preferred_language=zh 时保持中文。
占位符、命令、平台常量、YAML/JSON 键名和文件路径不得翻译或改写。
-->

# 🧪 Mobile 测试任务执行计划: {{FEATURE_NAME}}

## 📋 Input

| 参数 | 值 | 说明 |
| :--- | :--- | :--- |
| platform | {{PLATFORM}} | `ios` \| `android` |
| spec | {{SPEC_FILE}} | 平台验证工作流的 `--spec` 输入。默认就是 `{{FEATURE_DIR}}/test/case.md`。**`execution_mode = remote-agent` 时要看这一端怎么把用例送进容器**：靠工作区同步送的那一端（iOS）两条都要满足 —— ①**不被被测仓 gitignore**（`.ttadk/` 在有些仓里是被忽略的，被忽略的文件同步不过去）；②**写成相对仓库根的路径**（这个值会被原样透传给容器里那条命令，而容器的仓库根是另一个绝对路径）。违反的表现是「跑完了但一条用例都没执行」而不是报错。Android 由它的 `materialize` 节点单独把这个文件送过去，不受这两条限制。运输规则见 implement T002 的前置（键名 `spec`，两端都是 `--spec`） |
| execution_mode | {{EXECUTION_MODE}} | `local` \| `remote-agent`；本地/远端整体执行的唯一开关。ff 按 profiles 的 `DEFAULT_EXECUTION_MODE` 填，用户显式指定时以用户为准。**不要把各平台的默认值抄进这一行**——抄本与 profiles 分家时没有症状 |
| build_mode | local | `local` \| `airbuild`（仅 iOS 生效） |
| run_mode | full | `full`（build+lint+E2E）\| `verify`（**只跑 E2E**：跳过 build+lint，install 复用工作区已有产物——SDD 大循环衔接的默认值，前置依赖是小循环刚完成且产物最新） |
| task | {{TASK}} | **Android 专属**：构建命令（如 `./gradlew app:assembleMusicallyI18nDebug`）。**这是构建命令，不是本计划的 T00x 任务。** 由 ff 定：候选唯一就直接用，多个要在 clarify 阶段让用户选定 —— **不猜 flavor**，猜错不报错，只会编出一个不是你要的包，然后去查一堆莫名其妙的测试失败。iOS 无此键（它的构建目标是隐含的），交过去会被那一侧忽略 |
| bundle_id | {{BUNDLE_ID}} | 被测应用的包名 / Bundle ID。**必须与 `task` 编出来的那个包一致** —— 两者要同源推导（先定 `task`，再从它的 flavor 反查 applicationId），各推各的会在装包时对账失败。**Android 给了就与产物里读出的包名对账，对不上整跑停下；不给就按产物里读出的那个装**（`install` 节点）；iOS 是 `Info.plist` 的 override，通常不给 |
| artifact_path | | 可选；BYO 预编译产物（`.app`/`.ipa`/`.apk`）。非空时 run_mode 必须为 `verify` |
| with_unit_test |  | `true` 时给验证工作流追加 `--with-unit-test`（单测 stage：按变更集推导 pod 范围，委托宿主单测 skill 执行；需 run_mode 含 build） |
| concurrency | 3 | 并行 worker/设备数 |
| max_fix_rounds | 3 | 用例失败后自动改代码重验的轮数上限。**不要用 `0` 表示「只报告不修复」** —— 两端都不把它读成关闭（Android 翻成外循环链长上限，自动修复由它自己的开关决定）；要关自动修复，查那一端 SKILL.md 的开关，这张表今天没有对应的键 |
| remote_agent_provider | {{AGENT_PROVIDER}} | **仅 `execution_mode = remote-agent` 用**。那一侧 agent 的运行环境（端点 / 身份 / 模型 / 手上的能力）由谁提供。ff 按 profiles 的 `DEFAULT_AGENT_PROVIDER` 填。取值域归验证工作流，本文件不解释——它只负责把这个值原样交过去 |
| remote_model | {{MODEL}} | **仅 `execution_mode = remote-agent` 用**。那次会话用哪个模型：具体 id，或一个系列名（如 `gpt`）—— 系列名原样交过去，**认不认由那一端的 SKILL.md 定**（认的端会按 `remote_agent_provider` 那个身份实际可用的列表解析成具体 id 并记进报告），本文件不替它解析。ff 只有在 profiles 的 `DEFAULT_MODEL` 是系列名时才会填系列名。空 = 由 `remote_agent_provider` 决定谁来挑；**走原生接入时空值意味着由被测仓自己的 agent 配置文件说了算**，那份文件跟本次验证无关 |

> **键名就是 flag 名**：交接时把键名的下划线换成横线（`remote_model` → `--remote-model`），
> 两端都直接命中，谁都不需要维护一张翻译表。**这一条是「不要替它拼命令行」能成立的前提** ——
> 键名与 flag 名一旦分家，一端会硬停、另一端会静默吞掉，而后者没有症状。
> `remote_*` 两键只在 `execution_mode = remote-agent` 下有意义；iOS 那一端没有
> `remote_agent_provider` 这个能力，交过去会被它静默忽略（它有 `remote_model`）。

> 参数一经填写即为本计划的执行事实；重跑时不重新询问，除非用户显式修改。

## 🧩 Resolved Skills

| 能力标识 | 已解析的技能（实际调用） |
| :--- | :--- |
| `VERIFY_WORKFLOW` | `{{VERIFY_WORKFLOW_SKILL}}` |
| `REPORT_GENERATE` | `{{REPORT_GENERATE_SKILL}}`（空 = 按模板内联生成） |

> 后续任务必须通过能力标识查表调用技能，不得猜测技能名。**平台分叉只发生在 T001 的解析结果里**：
> 两端都解析为 `harness-workflow`（或其插件命名空间别名 `infra-ios:` / `infra-android:`）——**同名，但是两套
> 独立实现**，差异全部收在各自的 `SKILL.md` 里，由它自己把本文件的 Input 翻成本端参数。profiles 里
> `VERIFY_WORKFLOW` 为空的平台，T001 按其失败处理停下。
> 本文件其余任务一律平台无关，禁止新增平台特判：Input 里那几个 `DEFAULT_*` 打头的默认值是 ff 查 profiles 填的，
> 不是分叉——没有任何下游逻辑读 `platform` 来决定行为。哪些键有默认值以 profiles 为准，别在这里另抄一份。

## 📌 执行标记说明

| 标记 | 含义 |
| :--- | :--- |
| `[ ]` | 未执行 |
| `[x]` | 已完成 |

## 🚀 Phase 1: Resolve

### T001: 解析平台验证工作流（唯一平台分叉点）

| 项目 | 内容 |
| :--- | :--- |
| 状态 | `[ ]` |
| 执行方式 | 读 `SDT_ASSET_ROOT/templates/sdt-skill-profiles.json`，取 `profiles[PROFILE][platform].VERIFY_WORKFLOW`。先按裸名经 host skill 机制解析；失败则依次尝试 `VERIFY_WORKFLOW_ALIASES`。解析成功后把实际技能名回填到上方 Resolved Skills 表（case.md 不含执行配置，不回填）。 |
| 成功条件 | 技能可被 host 调用（作为 tool），或其 `SKILL.md` 可被读取并可按其协议执行。 |
| 失败处理 | `VERIFY_WORKFLOW` 为空或全部解析失败 → **STOP**，输出：「当前平台（{{PLATFORM}}）尚未配置验证工作流。iOS 请安装 harness-workflow skill；Android 接入指引见 adk-sdt/README.md § Android 扩展指引（实现平台 workflow skill + 在 sdt-skill-profiles.json 填入技能名即可，无需改动任何 SDT 逻辑）。」不得猜测替代技能，不得回退到零散原子能力拼装。 |

> ✅ **Checkpoint：T001 标记为 [x] 后，方可进入 Phase 2**

## 🧪 Phase 2: Verify

### T002: 执行平台验证工作流（build + lint + E2E，小循环内部闭环）

| 项目 | 内容 |
| :--- | :--- |
| 状态 | `[ ]` |
| 前置条件 | T001 完成；`spec` 指向的文件存在且用例表非空 |
| 调用技能 | `VERIFY_WORKFLOW` |
| 执行方式 | **把上方 Input 表当作一段「执行配置」交给该技能，由它按自己的 `SKILL.md` 翻译成本端参数并驱动至终态。不要替它拼命令行。** 交接内容就是**上方那张 Input 表里每一个非空的行**——照表交，不要另列一份键清单：**少交一个键，那一跑它就没生效，而报告照常出**。加一句「按你 SKILL.md 的执行协议自驱到终态，产出报告工件」。**两端的 CLI 形状不同**：iOS 是 `--run-mode` / `--build-mode` / `--concurrency` 配 `next → --verify <stage> → --final`；Android 是 `--preset` / `--site` 配 `start → next → submit --stage --nonce --json → final`（**起跑动词是 `start`，漏了它就成了续跑上一轮**），而且**不认识的参数会当场硬停**。照一端的写法拼给另一端，轻则报错重则静默跑偏。翻译规则写在各端 SKILL.md 里（Android 见其「上游 workflow 派下来的一段执行配置」一节）；**它不支持的键必须由它出声说明，不得静默忽略**。**`remote_agent_provider` / `remote_model` 非空时一个都不能漏**：它们只在 `execution_mode = remote-agent` 下生效，而漏掉 `remote_agent_provider` 的后果是那一侧回落到平台自带网关——它会在长会话中途换模型，换过去那个的 function-calling 未必接受当前 agent 的 tool schema，之后每次工具调用都被打回，**而报告读起来完全正常**。 |
| 闭环约束 | build 失败修复、lint 修复由 workflow 内部完成。**本任务不得把中间失败上抛给用户确认，不得走 `/adk:sdd:clarify`**；仅当 workflow 终态为 blocked、或修复预算耗尽仍有 FAIL 时，记录结果并进入 T003 汇报。**用例 FAIL 之后会不会自动改代码重验，取决于那一端**——有的端在本轮内修，有的端只在显式重开一轮时才重验。`max_fix_rounds` 交过去，实际怎么用以它 SKILL.md / 它打印的 note 为准；**不要假定失败一定会被修绿**，预算耗尽仍不绿是正常终态。 |
| 交互点 | 一般情况下 workflow 内部不外抛确认。**例外：`execution_mode = remote-agent` 时，代码改动落地需要人裁决**——远端容器为修 build / lint 改的代码以 patch 回传，由用户决定 apply / push / reject（iOS 在 settle 环节，Android 是 `land` 节点）。这不是「中间失败上抛」，是代码落地，必须呈给用户：把 diff 给他看，按他的裁决交回 workflow，不得代为决定。 |
| 成功条件 | workflow 到达终态，并交代**它的结论落在哪一份工件里**（那一份才是判据）。**几份、叫什么、在哪，由它自己说** —— 但**别假定终态命令会打印它们**：有的端只在自己那个 report stage 的输出里给路径、产物落在仓内 `.harness/`，有的端打印仓外状态目录并用产物索引统一寻址。去那一端自己的输出里找，**找不到不等于它没产**。判据那份与人读报告并存时以判据为准：人读那份可能是有损投影。记录：终态、总/通过/失败/跳过用例数、修复轮数、产物目录绝对路径。 |
| 失败处理 | workflow 无法启动（环境/依赖）→ 停在 T002，记录精确 `next_action`；终态含 FAIL → 正常进入 T003，在报告中归因。 |

**执行结果记录：**

| 维度 | 结果 |
| :--- | :--- |
| 执行身份 | **必填**：这一轮的执行身份，形式由验证工作流的 SKILL.md 定（Android=起跑返回的 `run.id`；iOS=本机跑取 `.harness/context.json` 的 `created_at`；**远端派发时本机没有 `.harness/`**，取那次派发返回的任务 id）。下次进来时 Step 2.5 优先凭它判断这条记录属不属于本轮 |
| 终态 | **照那一端打印的终态词原样填**（各端词表不同，别归一化成两档 —— 「用例失败」与「环境阻塞」在两端都是不同的词，压平会把缺陷读成 infra 问题） |
| 总用例数 | |
| 通过数 | |
| 失败数 | |
| 跳过数 | |
| 修复轮数 | |
| 产物目录 | |

> ✅ **Checkpoint：T002 标记为 [x] 后，方可进入 Phase 3**
>
> ⚠️ **收尾时把执行身份填上**：Step 2.5 优先凭它区分「本轮跑过」与「某轮跑过」。在一轮一目录、
> 旧轮原地还在的那一端它是唯一依据；漏填的表现不是报错，而是下一次调用把上一轮的结论当成自己的。

## 📊 Phase 3: Report

### T003: 生成测试报告并归档

| 项目 | 内容 |
| :--- | :--- |
| 状态 | `[ ]` |
| 前置条件 | T002 已完成（含带 FAIL 的完成） |
| 调用技能 | `REPORT_GENERATE`（为空则内联） |
| 执行方式 | 读取 T002 产物目录中的报告工件，按 `SDT_ASSET_ROOT/templates/sdt-report-template.md` 填写并写入 `{{FEATURE_DIR}}/test/report.md`。保留 TC-ID；**每条用例的原始终态原样写进报告，不要压成三态**——验证工作流给几档就写几档（Android 给 10 档，`indeterminate` / `blocked_*` / `aborted_*` 与 `failed` 不是一回事，压平会把环境阻塞和未决读成产品缺陷）。每个非绿用例给出根因归类、证据路径（截图/UI 树/worker 日志）与修复建议；**自动修复记录照那一跑实际发生的填**：一轮都没修就写 `0`，别凭平台名推。 |
| 成功条件 | `test/report.md` 生成，无 `{{...}}` 占位符残留。 |

## 🔗 Pipeline 依赖关系

```text
Phase 1: Resolve (T001)
         ↓
Phase 2: Verify  (T002)   ← 平台验证工作流内部自含 build → lint → E2E → 修复小循环
         ↓
Phase 3: Report  (T003)
```

<!--
【硬规则】
1. 所有 {{...}} 占位符必须替换；`VERIFY_WORKFLOW_SKILL` 由 ff 阶段按 profiles 预填、implement T001 复核回填。
2. 重跑（rerun after fix）时保留 case.md 与本文件 Input，重置 T002/T003 为 `[ ]`；已有可复用产物时可将 run_mode 改为 verify 快路径。
3. 任务完成必须立即将状态 `[ ]` → `[x]` 回写本文件，不得批量补记。
4. 本模板 iOS / Android 通用；平台差异只允许存在于 T001 解析出的技能名及其内部实现。
-->
