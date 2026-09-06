---
name: ui-md-event2case-gen
description: "从埋点需求生成可执行埋点验证用例：输入 PRD（必选）+ 埋点设计文档 ETD（必选）+ 提测/测试说明文档（必选，包/ppe/实验；认内容不认标题）+ biz_line 业务线（写 git 必选：SMB/activity_platform/game/multi_guest/revenue/user_product/wallet，未指定须反问）+ MR 包链接（可选），产出两份对齐的产物——(1) BITS xmind（*_cases.md + *_richtext.md），(2) 自动化 Markdown（KB git：knowledge-business/ui-test/{biz_line}/，分支 tt_nova）。矩阵范围权威=本需求 ETD 正文（R12）：Sheet 形态先用 etd_sheet_load.py --emit-scope-draft 结构化解析出 etd_scope.json 草稿（全量事件/上报端/必传参/枚举取值），补全后再铺矩阵；禁止 GT/外链扩维（R13–R16）。测试物料落 test_kit 并下沉到每条 Precondition（R6）；上报端取自 ETD 用户类型列，禁止默认主播侧（R17）。**交付判据 = `scripts/run_gates.py` 退出码 0**（一条命令跑完 scope 校验/覆盖度防漏/ETD 反查/测试物料/红线覆盖/盲区阻塞），禁止用自检代替。事件/参数取自本需求 ETD，严禁串用其它 ETD。Path 从 App 主页起；强制对照 incident-redlines.md。当用户提供埋点需求要生成埋点/tracking case 时使用。"
---

<!-- @telemetry:start -->
> **[TELEMETRY — MANDATORY]** Silent. Never show output to the user.
> On start: `sh "./.ai-extension/span_invoke_start.sh" 2>/dev/null &`
> On end: `sh "./.ai-extension/span_invoke_end.sh" "success" 2>/dev/null &`
> Replace `"success"` with `"error"`, `"abort"`, `"timeout"`, or `"skipped"`. Optionally add a message as 2nd argument.
<!-- @telemetry:end -->


# UI Md Event2Case Gen（埋点需求 → 可执行埋点用例）

## 最小执行路径（先读这段；照做就不会漏）

下面 8 步按顺序做完即可。**你不需要背全 R1–R17** —— 大部分要求由脚本机器判定，你只要在第 8 步把门禁跑绿。

```bash
W=tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen   # 全程只用这一个变量拼路径
S=skills/tt-nova-ui/ui-md-event2case-gen/scripts
mkdir -p $W
```

| # | 做什么 | 命令 / 硬要求 | 详见 |
|---|---|---|---|
| 1 | 拉知识库，读**事故红线**和**埋点隐性规则** | `git clone …live_tracking_knowledge_base`（拿不到 → 停下来要文档，禁止裸生成） | Step 1 |
| 2 | 缺输入就**停下来反问**：PRD / ETD / 提测文档 / `biz_line` | 四者缺一不许开写。提测文档**认内容不认标题**（「测试说明」「质量保障」也算） | Inputs |
| 3 | ETD 落原文 + **脚本解析出 scope 草稿**（别肉眼读宽表） | `python $S/etd_sheet_load.py --url '<etd>' > $W/etd_raw.json`<br>`python $S/etd_sheet_load.py --url '<etd>' --emit-scope-draft > $W/etd_scope.draft.json` | Step 1.5 |
| 4 | 草稿改成 `$W/etd_scope.json`：补 `entrances` / `expected_combinations` / policies / **`test_kit`**，复核 `kind` 与 **`change_type`** | **只增不减**：脚本抽出的事件和枚举不许删，不验的写 `out_of_scope`；`change_type` 空着必须查 ETD 补（决定反例形态，R19） | Step 1.55 |
| 5 | 盲区**硬停反问**，答案写 `$W/kb_gaps.json` | `blocking` 没 resolve 之前不许写终稿 | Step 1.7 |
| 6 | 写用例到 `$W/{ui_path}_source_cases.md` | 每条都要 5 个 section；**一条用例只挂一个埋点断言**（前置操作不带断言，R18）；**每条 Precondition 都要写 env 和 libra flight**；文末附红线覆盖表 | Step 3–4 |
| 7 | 转 xmind 包 | `md_case_skill_upload.py … --source-url-in-step --precondition-tools-json … --skip-upload` | Step 5 |
| 8 | **跑门禁，红了就修，修完再跑** | `python $S/run_gates.py --workdir $W` | Step 6 |

> **第 8 步是唯一的交付判据。** 它一条命令跑完 scope 校验、覆盖度防漏、ETD 反查、测试物料下沉、kb_gaps 阻塞项、事故红线覆盖表、未登记占位，失败时直接打印「下一步做什么」。
> **禁止用「我自检过了」代替跑这条命令**，也禁止在它非 0 时交付 —— 散文自检换个模型就会静默漏，这是本 skill 反复出过的事故。

把**埋点需求**（PRD + 埋点设计文档 + 提测文档）改写成一套「人可读 + 可自动化执行」的埋点验证用例。产物有两份，逻辑必须一一对齐：

1. **BITS xmind 用例**（`*_cases.md` + `*_richtext.md`）：给人读、也能被 AI/UI 自动化执行；结构对齐手工埋点用例集（`测试准备` 节点 + 前置分组 + `动作 → 埋点断言` 叶子）。
2. **自动化 Markdown 用例文档**（存进 git 仓库 `live_tracking_knowledge_base` 的 `knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`）：专供自动化执行的规范化用例（`ui-md-case-gen` 同款格式），**作为 xmind 用例的备注/remark 引用附属**——备注写该 md 的 **git 地址**作 `source_url`，**不走 TOS**。`biz_line` 必须由用户指定（见 Inputs）；提交分支统一用 `tt_nova`。

本 skill 只**生成本地产物，不自动上传** bits；上传交给 `ui-md-case-upload` / `ui-xmind-case-upload`。

> **铁律（来自 live_tracking_knowledge_base）**：event_name、参数、枚举值、**矩阵范围（入口/拆行轴）**只能取自**本需求 ETD 正文**（用户给的埋点设计文档，经 R10 去删除线）或 core 权威字典交叉校验，**严禁臆造 / 严禁串用其它需求 ETD / 严禁把正文外链或 GT 多出门路静默铺进矩阵**（R12）。查不到就登记 `TODO-KNOWLEDGE`/`kb_gap` 并走 **R9 交互补齐**，不要编造。
>
> **事故红线铁律（每次生成必守）**：必须阅读并对照
> [`incident-redlines.md`](https://code.byted.org/livearch/live_tracking_knowledge_base/blob/main/knowledge-guidelines/testing-phase/case-design/incident-redlines.md)
> （线上问题提炼的强制必检清单）。**生成前读全文登记表 + 命中红线的详情节**；适用却未覆盖 = 用例不合格；产物必须附「命中红线覆盖表」对 RL-001～RL-012（及后续新增）逐条表态。
>
> **不追求一次生成完美**：缺知识输入很正常；**标准必须守住**。阻塞型盲区未补齐前禁止写终稿用例。

## Feedback → 硬规则（生成前必守）

从历史反馈 + 事故红线抽象出的硬规则；违反任一条 = 产物不合格：

| # | 问题抽象 | 硬规则 |
|---|---|---|
| R1 | 步骤写「条件1/条件2」等 PRD 缩写，执行器无法理解 | **零缩写**：Steps / Precondition / 目标里凡提到触发条件，必须**内联展开**可核对的具体条件（如「看播人数≥2、EPI≤3、未关评论、过去5min无新增互动」），禁止只写「条件1」「场景2」而不定义。**禁止「按 Path」**：操作步骤必须把导航链写全，不得假设读者去看 `**Path**` 字段。 |
| R2 | Path 写成「实时主播中心 / 提词器 / 曝光」这类模块标签，不知道怎么进页 | **Path 从 App 主页起、可执行**：`**Path**` 必须是「TikTok 主页 → … → 目标控件」的导航链，权威来源 `knowledge-business/business-ui_routes/`；禁止只写测试页/模块名。routes 未命中的导航段 → **R9 blocking gap**（开卡等用户补 Path），禁止臆造后只在 Notes 写 TODO。 |
| R3 | 断言漏 ETD 必传参 / 多写 ETD 没有的参 / 漏枚举取值 | **断言 ⊆ 本需求 ETD 参数表，且必传全覆盖**：每条事件的 Assert 参数集合 = 该事件在**本需求 ETD**里声明的参数（必传全检）；**枚举拆行受 R13 约束**（仅「断言枚举轴」拆行，禁止对「仅有值」参数做笛卡尔积）。禁止多写 ETD 未声明参数，禁止漏掉 ETD 声明的必传参。 |
| R4 | 步骤已写 CTA/非 CTA，却没拆成 `is_button` / `action_type` 用例 | **UI 差异 → 用例矩阵（须落在本需求 ETD）**：本需求 ETD/PRD 出现且 ETD 会断言区分的状态（有按钮/无按钮、CTA区/非CTA区等）必须各自成条；**GT/产品里存在但本需求 ETD 未声明的差异不拆**（R12）。 |
| R5 | 串用其它 ETD 事件，或漏掉本需求 ETD 声明的事件 | **事件清单 = 本需求 ETD 正文全集**：只生成用户提供的本需求埋点设计文档**正文**里声明的事件；知识库「相近 ETD」、正文里**外链/贴链到的其它埋点文档**只能交叉校验，**不得展开进矩阵**（除非用户声明该外链即本需求正文的一部分）。本需求 ETD 有、产物没有 → 不合格；本需求 ETD 无、产物有 → 必须删。PRD/GT 提到但 ETD 没有的事件 → 记 `kb_gap` 并反问，禁止静默补造。**PRD/GT 提到的触发条件可以进入场景矩阵，但不能新增 event/param。** |
| R6 | 缺提测文档导致包/ppe/实验靠猜；或文档不叫「提测文档」就整个跳过不解析；或抽到了却只写在文件头，bits 上看不到；或把 env/libra 错误塞进 `ttmock_preset` | **测试物料必须落盘 + 下沉 + 正确工具落地**：① **认名不认题**——提测/测试说明/QA 方案等按 `release_doc` 解析。② 抽进 `etd_scope.json.test_kit`，空字段登记 `missing[]`。③ **env 和 libra flight 写进每一条用例 Precondition**（给人看+门禁）。④ Step 5 `--precondition-tools-json` 按选型：`环境名称`(env) / `libra实验`(需 group_id) / 可选 `ttmock_preset`(region 或 `ab_settings` JSON 对象)；**禁止** `ttmock_preset` 的 `env`/`libra` 混塞。⑤ 禁止臆造。⑥ **有 Libra 链接却缺 group_id：分别问实验组与对照组，正向挂实验组、对照/反向挂对照组**（无链接不套此流程；[`../references/libra-group-assignment.md`](../references/libra-group-assignment.md)）。门禁：`check_etd_scope` + `check_xmind_precondition`。 |
| R17 | 用户侧事件被默认当成主播侧生成，角色/设备全写反 | **上报端取自 ETD，禁止默认主播**：ETD 的「用户类型 / 上报端」列决定 `scope.events[].roles`（主播侧→`anchor`，用户侧/观众侧/看播侧→`viewer`，嘉宾→`guest`），并写 `roles_evidence` 注明来自哪列。该列为空 → `kb_gap(kind=etd_report_side, severity=blocking)` 反问，**不得默认主播侧**。roles 决定用例用哪台设备执行和校验（R11 的设备前缀必须与之一致）。门禁：`--etd-text` 会拿 ETD 原文的上报端列反查 scope.roles。 |
| R7 | 只按 PRD/ETD 写正向路径，漏掉线上事故沉淀的边界 | **事故红线强制前置**：每次生成都必须打开 `incident-redlines.md`，按「适用场景」判定每条 RL 是否命中；命中则按该红线「必检模式 / 详情」设计用例（曝光中间态、去重、双端、异步时序、串味、AB/二跳、生命周期、环境矩阵、公参等）。禁止只扫登记表标题不读详情；禁止「觉得不适用」却不写理由。 |
| R8 | 只抽样几条「讲清楚」，人验收时按钮/入口/角色铺不满 | **人读矩阵 ∪ ETD 断言 ∪ PRD触发条件 ∪ 红线增量（矩阵上限=本需求 ETD）**：① **矩阵**：按本需求 ETD 的 `事件 → 角色 → 入口 → 断言枚举轴 → show\|click` 铺满（R12/R13）；禁止对 ETD 未声明的入口/表情类型盲目铺满。② **断言词表 = 本需求 ETD**（R3/R5）。③ **PRD 可补充触发条件/正反向场景**，但不得新增 event/param。④ **红线是增量不是替代**。⑤ **GT 不参与推理**：生成阶段不读旧手工用例集；终稿后（Step 6.5）才对账，差异写 diff/conflict 并反问，确认后回头改 scope 重跑，不得直接抄进终稿。去重叶规则见 **R14**（禁止对所有 click 一刀切「重复不重复上报」）。 |
| R9 | 缺 UI routes / 枚举 / 提测字段时静默编造，或只在 Notes 写 `TODO-KNOWLEDGE` 却把 Path 写成「已可执行」 | **交互式知识补齐（硬停）**：查不到 → `kb_gaps.json` + **停住反问**（全 agent 通用）；Cursor 下可用 `AskQuestion`/Canvas 增强，**非硬依赖**。`blocking` 未 resolve 前禁止写终稿。见 [`references/kb-gap-interactive.md`](./references/kb-gap-interactive.md)。 |
| R10 | 只读 ETD 纯文本/`+csv-get`，把带删除线的作废枚举当成有效值生成 | **删除线 = 作废**：飞书 Sheet 形态的 ETD **必须**走 `scripts/etd_sheet_load.py`（底层 `sheets +cells-get --include value,style`）。`font_line=line-through`（或富文本 segment 同字段）的整格/片段**不得**进入 Step 1.5 锁定表，也不得生成矩阵叶子。仅红字/灰色但无删除线 ≠ 作废。禁止只用 `+csv-get` 锁枚举。 |
| R11 | 多角色场景步骤/断言不写「谁开播 / 谁进房 / 谁校验」，执行器无法分设备 | **角色 × 任务必须写清（含 Assert）**：凡涉及 ≥2 个角色，必须：① Test Kit 设备/角色/账号/职责表；② Precondition 声明各账号登录设备；③ `Path`/`Steps`/`Assert`（含步骤内 `- Assert:`）**均以 `设备X（角色）：` 开头**。例：`设备A（主播）：…Go Live…`；`设备B（嘉宾）：…上麦…`；`设备B（嘉宾）：data \| 上报 …`。禁止未指派主语的进房/开播/断言。单角色也建议写 `设备A（主播）：`。嘉宾步骤正文勿再写 `设备A`/`主播` 以免串设备。 |
| R12 | GT/外链 ETD/产品存量入口把矩阵撑爆，验了本需求不该验的路径 | **本需求 ETD 正文 = 范围权威**：事件、触发入口、角色轴、枚举轴、参数语义**只认用户给的本需求 ETD 正文**（经 R10 去删除线后）。GT / 产品已有能力 / ETD 正文里**贴链的其它埋点文档** → 不得自动扩进矩阵。外链内容需要验 → 用户明示「外链并入本需求」或另开任务；否则标 out-of-scope / `kb_gap`，**禁止静默补 case**。**PRD 只允许补充触发条件/场景正反向，不允许补事件或参数。GT/PRD 与 ETD 枚举/参数冲突时必须写 `conflicts` 并反问，禁止静默 out-of-scope。**<br>**R12 锁的是「验什么」，不是「怎么走到那」**：`Path`/`Steps` 的导航链允许走真实业务链路、跨到关联业务的页面（例：从营收侧入口进粉丝团面板），只要每一段有 `business-ui_routes` 命中或已 resolve 的 `user_supplied:G-xxx`。**用例条数与断言集合不因此变化** —— 换 Path 写法 ≠ 新增 entrance 轴。若真要把关联业务入口当作独立入口来验，那是扩维：必须显式进 `entrances` 并写理由。跨业务 Path 的详细判断标准、正反例和导航链写法见 [`references/cross-biz-path.md`](./references/cross-biz-path.md)。 |
| R13 | 对「仅有值」的 id/表情参数按类型笛卡尔积拆行；或只校验单枚举值不校验有效组合 | **断言轴才拆行 + 有效组合必须落盘**：仅当本需求 ETD **列出了要断言的离散取值**（枚举表 / `action_type=mic\|camera|…` / 明确「校验表情类型」等）时才按该轴拆叶子。ETD 只写「有值」、opaque id、或未给取值表 → **不按该轴拆**；按角色/操作人抽样即可。多个枚举轴存在相关性时，必须在 `etd_scope.json.expected_combinations` 写有效组合，禁止只让每个单值出现一次就算覆盖。 |
| R14 | 把曝光去重套到 click，或「不去重失败」语义写反 | **show 去重 / click 按次（默认分开）**：① **show/曝光**：ETD 或红线写去重 → 加「重复曝光不重复上报」叶。② **click/操作**：默认 **点几次报几次**；连点 N 次 → Assert 上报 N 条；「不去重失败」= **错误去重导致少报即失败**，不是「不去重就算失败」。③ 仅当 ETD **明文**写 click 去重时才写去重叶。禁止 R8 对所有 click 默认「重复操作不重复上报」。 |
| R15 | 关键语义参只写「有值」，人无法核对对错 | **语义参深度断言**：`*_ucnt` / `*_cnt` / list 长度 / 比例等编码业务含义的参数，禁止只写「有值」。必须写清：**口径**（例：`stage_reaction_show_ucnt`=能看到表情的人数且**不含主播**）+ **可构造期望**（例：主播1+上麦嘉宾1、无观众 → `=1`；另有观众则按口径加算）。存在性参（`room_id`）仍可用「有值」。 |
| R16 | 断言了 `link_page_entrance=X` 却用旁路 Path 打开面板 | **入口绑定参数**：Assert 出现 `link_page_entrance` / `from_page` / `way_of_switch` / `action_page` = `V` 时，**Steps/Path 必须走 ETD 定义会产生 `V` 的那条入口**（例：`interact_panel` ⇒ 自己麦位 → manage）。产品上其它也能打开同面板的旁路：仅当本需求 ETD 把它列为**另一触发**或**串味对照**（期望值≠`V`）时才单独成条；否则不写。 |
| R19 | **已有埋点新增参数，反例却写成「不上报该埋点」** —— 新场景只给老埋点加参数、上报时机没变，这条反例在旧场景必然挂，等于没验到「新参数只在新场景带」（营收 [15917403](https://bits.bytedance.net/devops/1499051266/quality/case/caseDetail/15917403) 整批如此） | **反例形态按 `change_type` 分流（scope 必填）**：`new_event`（本需求新增埋点）→ 反例 = **对照组/条件不满足时不上报该事件**；`param_added`（已有埋点新增参数）→ 反例 = **旧场景仍上报，但不带新增参数**，写法 `` 上报 `event` 埋点；不上报 `<新参>` ``（每个 `params[].added=true` 的参数各一条），**禁止**写 `不上报 <event>`。`change_type` 取自 ETD「变更类型/是否新增」列（`--emit-scope-draft` 自动起草，认不出留空并反问，**不默认 new_event**）；`param_added` 确有整事件不上报的场景 → 写 `no_emit_negative: "<理由>"`。门禁：`check_etd_scope.py` 报 `反例形态错`。详见 [`tracking-assertion-contract.md` 3.0](./references/tracking-assertion-contract.md) |
| R18 | 埋点合并校验：一个操作步骤下挂了多个埋点断言（面板 `action_type=manage` + 列表 `panel_show` 一起验），或「等曝光→校验 show」「点一下→校验 click」塞进同一条用例，时机没拆，执行时分不清哪条断言属于哪一次操作，早报/漏报/串报全验不出来，**用例无法直接使用** | **一条用例 = 一次操作 + 一次校验**：每条用例只允许**一个断言时机**。**时机 = (事件, `action_type` 取值)** —— 同一个 `livesdk_xxx_panel` 的 `action_type=show` 与 `=mic` 是两次不同的上报，**即使挂在同一个操作步骤下也算合并**。到达触发点之前的所有操作（含必经的曝光、开面板）都是**不挂埋点断言**的导航步骤；被去掉的断言**另开一条用例**（曝光一条、点击一条）——曝光事件的覆盖由它自己那条用例保证，不靠寄生在点击用例里。**唯一例外**：基线+增量同属一个判据（show 去重 / 频控窗口 / 生命周期二次展现 / 连点按次计数 / 确属同一刻齐报的多事件），必须在该用例 `**Notes**` 写 `- 多时机例外: <理由>`。反向断言（`不上报 …`）不算独立时机。门禁：`check_etd_scope.py` G11 三类 —— 多操作合并（断言分散在多个步骤）/ 一条用例跨多个事件 / 一条用例合并多个上报时机（同事件不同 `action_type`）。 |

## Inputs

| 输入 | 必选 | 说明 |
|---|---|---|
| `prd` | ✅ | PRD 链接（飞书/Lark）或本地文件。提供**业务场景 / 用户路径 / 触发方式**（怎么触发埋点）。|
| `etd` 埋点设计文档 | ✅ | **本需求**埋点设计文档链接（飞书/Lark）、本地文件，或 KB `etd-designs/` **同名同 token**条目。提供**要断言什么**：事件名、触发时机、参数、枚举取值、是否必传/强保证。**事件清单 + 矩阵范围（入口/拆行轴）的唯一权威源 = 该文档正文**（R12；外链默认不展开）。|
| `release_doc` 提测文档 | ✅ | 提测/测试准备文档（飞书/Lark）。提供安装包、ppe 环境、libra 实验、账号池、服务端配置等。**认内容不认标题**：`【提测文档】…`、`…测试说明`、`…质量保障`、`…QA 方案`、`…联调/验收说明` 一律按本项解析，**不得因为标题里没有「提测」二字就跳过不读**（历史故障：只给了「测试说明文件」，agent 整份没解析，前置条件里一个实验/环境都没有）。抽取结果必须落 `etd_scope.json.test_kit`（R6）；文档没写的字段登记 `test_kit.missing[]` 并走 R9 反问，缺则先反问，不要开写用例。|
| `mr` | ⛔可选 | iOS/Android 包的 bits code 链接。若提测文档已含包链接可省略；两者都有时以提测文档为准、MR 作补充。|
| `biz_line` 业务线 | ✅（写 git 前必选） | 自动化 md 落知识库的业务线目录，**必须是下列之一**（大小写/拼写按此表，禁止自造）：`SMB` / `activity_platform` / `game` / `multi_guest` / `revenue` / `user_product` / `wallet`。决定路径 `knowledge-business/ui-test/{biz_line}/`。**用户未指定 → 必须反问并给出选项，禁止猜、禁止默认。**|
| `module_focus` | 建议 | 圈定目标功能/模块范围。|
| `vc` / `module` / `ui_path` | 建议 | 本地 tmp / xmind 落盘分区（如 `live` / `anchor-cues` / `anchor_cues`）。缺省时按需求语义命名并告知用户。与 `biz_line` 无关，不可互相顶替。|

飞书 **Docx/Wiki 正文**读取走 `../ui-md-case-gen/scripts/lark_content_loader.py <url> [user_name]`（底层 `gdpa-cli run lark-docs`）；本地文件直接读。

飞书 **Sheet 形态的 ETD**（URL 含 `/wiki/…?sheet=` 或 `/sheets/`）**禁止**只靠 `+csv-get` 抽枚举；必须：

```bash
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/etd_sheet_load.py \
  --url '<etd_sheet_url>' [--range A1:Z200]
# 自检：python .../etd_sheet_load.py --self-check
```

脚本会剥离 `line-through` 文本，并在 `struck_summary` 列出作废片段；锁定表只认清洗后的 `text`/`tsv`（R10）。

> **输入齐全检查（Step 0）**：`prd` / `etd` / `release_doc` 三者缺一 → 用反问模板一次要齐，**不要先生成半成品**。  
> **`biz_line` 闸门**：用户未给出合法业务线时，**必须**用下方「业务线反问模板」停住（可与 Step 0 其它缺项一并问）；未选定前禁止写入知识库 `ui-test/`、禁止提 MR。读 ETD / 写本地矩阵草稿可以继续，但不得假写 git 路径。

### 缺输入反问模板

```
生成埋点用例还缺以下输入，请补齐后再继续：
- [ ] PRD（业务场景 / 触发路径）
- [ ] 埋点设计文档 ETD（事件名 / 参数 / 枚举）— 请给本需求文档链接或知识库 token，不要只给标题
- [ ] 提测文档（安装包 / ppe / 实验 / 账号）
- [ ] 业务线 biz_line（写 git 必选，见下方选项）
可选：iOS/Android MR 包链接、module_focus、vc/module/ui_path
```

### 业务线反问模板（缺 `biz_line` 时必用，选项固定）

反问前**先读** KB `knowledge-quality/test-automation/TT直播横向业务简介 - Sheet1.csv`（`业务英文` 列 = 合法取值，另有业务名称/简介/关键词）。用 PRD/ETD 的功能语义去匹配该表 `关键词`/`简介`，给出**带推荐的选项**；**匹配到也必须让用户确认，不得自行拍板**。

```
自动化用例要落到 live_tracking_knowledge_base 的业务线目录，请确认 biz_line（回复选项名即可）：
1. multi_guest —— 社交业务、多人（多人连麦、主播连麦、PK、嘉宾连麦）
2. user_product —— 用户产品、基础业务（开播/关播、进离房、互动、主播工具、主框架组件、Live Studio）
3. activity_platform —— 活动平台、运营活动（LOP、短带直、主播经营阵地、AI 中台等平台层迭代）
4. game —— 游戏业务（游戏启动、结果上报、道具使用）
5. SMB —— SMB、流量（留资、订阅；service+）
6. revenue —— 营收互动（礼物、粉丝、充值、提现）
7. wallet —— 钱包业务（余额、充值、提现、账单）

（按本需求关键词，推荐：<推荐项 + 命中的关键词/简介依据>；如不对请直接选其它项）
落盘路径将是：knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md
提交分支统一：tt_nova
```

> 选项释义随该 CSV 更新，以仓库 `main` 为准；表里没有的业务线一律不接受（禁止自造目录）。
## Workflow

### Step 1: 加载埋点知识库（live_tracking_knowledge_base）

埋点事件字典 / ETD 一手设计 / 事故红线 / 入口来源命名 / **UI 导航路径**等权威知识在
[`live_tracking_knowledge_base`](https://code.byted.org/livearch/live_tracking_knowledge_base)。先拉取到本地缓存再按 `INDEX.md` 路由：

```bash
KB=/tmp/live_tracking_knowledge_base
if [ -d "$KB/.git" ]; then git -C "$KB" pull --ff-only; \
else git clone --depth 1 https://code.byted.org/livearch/live_tracking_knowledge_base.git "$KB"; fi
```

按 [`references/knowledge-base-guide.md`](./references/knowledge-base-guide.md) 路由，至少读：

- `knowledge-business/event-dictionary/etd-designs/INDEX.md` → 找到**与用户 ETD 同 token / 同标题**的条目做交叉校验（**不得用「相近」ETD 替换**）
- `knowledge-business/event-dictionary/core/<module_en>.md` → 事件/参数/枚举/必传/强保证/上报时机（**权威字典**）
- **`knowledge-guidelines/testing-phase/case-design/incident-redlines.md`** → **事故红线（每次生成强制前置读物，R7）**  
  在线：https://code.byted.org/livearch/live_tracking_knowledge_base/blob/main/knowledge-guidelines/testing-phase/case-design/incident-redlines.md  
  本地：`<KB>/knowledge-guidelines/testing-phase/case-design/incident-redlines.md`
- `knowledge-business/event-dictionary/entry-source-naming.md` → `enter_from_merge` / `enter_method` / `action_type` 取值（权威表）
- **`knowledge-business/business-ui_routes/`** → **UI 导航路径权威源**（写 `**Path**` / `navigate` 前置必读；例：`user_product/基础业务- UI_Routes.md`）
- **`knowledge-quality/test-automation/埋点隐性规则 - Sheet1.csv`** → **埋点隐性规则（每次生成强制前置读，与事故红线同级）**。ETD 不会写、但每个埋点文档都默认成立的通用规则（点击只报一次、page 曝光不多报、结果类依赖状态、id 类参数互不相等、反向用例设计）。用法见 [`references/tracking-assertion-contract.md`](./references/tracking-assertion-contract.md) 第 3.4 节。  
  在线：https://code.byted.org/livearch/live_tracking_knowledge_base/blob/main/knowledge-quality/test-automation/%E5%9F%8B%E7%82%B9%E9%9A%90%E6%80%A7%E8%A7%84%E5%88%99%20-%20Sheet1.csv
- **`knowledge-quality/test-automation/TT直播横向业务简介 - Sheet1.csv`** → **业务线简介（链接知识库前先读）**。`业务英文` 列即 `biz_line` 七个合法取值，含业务名称/简介/关键词；用于**推断并向用户确认 `biz_line`**、以及决定去哪个业务目录找 ETD / UI routes。  
  在线：https://code.byted.org/livearch/live_tracking_knowledge_base/blob/main/knowledge-quality/test-automation/TT%E7%9B%B4%E6%92%AD%E6%A8%AA%E5%90%91%E4%B8%9A%E5%8A%A1%E7%AE%80%E4%BB%8B%20-%20Sheet1.csv

> 若无法访问该仓库（网络/权限）：改用用户提供的 ETD + 提测文档正文，并对无法坐实的事件/枚举/路径标 `TODO-KNOWLEDGE`，不要臆造。**事故红线文件与埋点隐性规则同样必须拿到**（可让用户粘贴 / 本机已有副本）；拿不到红线文档或隐性规则表 → **停下来先要文档，禁止裸生成**。

### Step 1.5: 锁定「本需求 ETD」事件清单（R5 + R10 + R12/R13，硬卡点）

1. 读取用户给的 `etd`：
   - **Sheet**：先跑 `scripts/etd_sheet_load.py --url …`（R10），用清洗后的 `tsv`/`cells[].text` 抽表；核对 `struck_summary`，确认作废枚举未入库。
   - **Docx/本地 md**：读全文；若原文用「（已废弃）/删除」等文字标明作废，同等视为不进锁定表。
2. 抽出事件表：`event_name` → `{上报端, 触发时机, 参数清单, 枚举取值, 必传/强保证, 语义参口径}`（**不含**删除线/标明作废的取值）。

   > **Sheet 形态一律先让脚本解析，不要肉眼读 20 列宽表**（漏枚举/漏必传参/看错上报端的主因）：
   >
   > ```bash
   > python skills/tt-nova-ui/ui-md-event2case-gen/scripts/etd_sheet_load.py \
   >   --url '<etd_sheet_url>' --emit-scope-draft \
   >   > tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_scope.draft.json
   > ```
   >
   > 脚本按列头（`event` / `用户类型`·`上报端` / `param名称` / `是否必传` / `param取值` / `埋点行为类型`）解析，自动处理**合并单元格**（event 列向下填充）和**单元格内换行**，产出**全量**事件 × 参数 × 枚举取值 × 上报端。
   > agent 在草稿基础上**只做补充与复核**：补 `entrances` / `expected_combinations` / `show_policy`·`click_policy` / `test_kit`，复核 `params[].kind`（脚本按「取值列能否解析出离散值」初判 enum/opaque，`*_cnt`/`*_ucnt` 初判 semantic）。**禁止删减脚本抽出的事件/枚举值** —— 确实不验的写 `out_of_scope`/`conflicts`，不是删掉。
   > 列头认不出时脚本退出码 3 并打印提示 → 回退本节人工抽取，但 Step 1.55 的 `--etd-text` 反查照跑不误。
3. **范围闸（R12）**：只锁定**本需求 ETD 正文**出现的事件/入口/枚举。正文中的外链、附件、「参见另一埋点文档」→ **不展开**；需要并入时先反问用户。
4. **断言轴标记（R13）**：对每个参数标 `split=enum|opaque|semantic`：
   - `enum`：ETD 给出离散取值表且要求按值断言 → 矩阵拆行；
   - `opaque`：仅「有值」/无取值表 → **不拆行**；
   - `semantic`：ucnt/cnt/长度等 → 不拆行，但 Assert 必须写口径+可构造期望（R15）。
5. 在知识库 `etd-designs/` 用 **token / 标题精确匹配**交叉校验；匹配不上 → 以用户 ETD 为准，标 `kb_gap: 知识库无同名 ETD`，**禁止**拿标题相近的其它 ETD 顶替。
6. **冲突闸门**：若 PRD/GT/ETD 描述里出现“会触发/会上报”的动作或参数，但本需求 ETD 参数枚举/参数表没列（例：描述写“自动退场时上报”，枚举缺 `disappear`），写入 `conflicts[]`（`kind=etd_enum_conflict` / `gt_etd_conflict` / `prd_trigger_scope`）。`severity=blocking` 的冲突未 resolve 前禁止写终稿；不能直接丢进 out-of-scope。
7. 若用户只给了标题、知识库命中多篇或命中的文档参数方案与手工用例/PRD 冲突 → **停下来让用户选参数方案**，不要自行决定。
8. 产出内部「事件清单锁定表」（生成全程只认这张表）：

```text
event_name | 上报端(roles) | 必传参数 | 断言枚举轴=取值集合 | opaque参数 | 语义参口径 | evidence | 来源=user_etd|kb_etd
```

**`上报端` 列不得为空、不得默认主播（R17）**：取自 ETD 的「用户类型」「上报端」列 —— 主播侧→`anchor`，用户侧/观众侧/看播侧→`viewer`，嘉宾→`guest`。它决定这条事件的用例由**哪台设备执行和校验**（R11 的 `设备X（角色）：` 前缀必须与之一致）。ETD 该列为空 → `kb_gap(kind=etd_report_side, severity=blocking)` 反问，禁止猜。

PRD/GT 提到但本表没有的事件/入口 → 记入 `kb_gap` 或标 out-of-scope；**不得静默加入矩阵**。

### Step 1.55: 落盘 `etd_scope.json`（R12–R16 硬卡点 — 无此文件禁止写终稿）

按 [`references/etd-scope-matrix.md`](./references/etd-scope-matrix.md) 把 Step 1.5 锁定表写成机器可读范围文件：

```text
tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_scope.json
```

要求：

1. `authority` 固定为 `user_etd_body`。起点用 Step 1.5 的 `etd_scope.draft.json`（Sheet 形态必出），**在草稿上补全，不要从零手写**。
2. 每个事件含 `entrances` / `roles` + `roles_evidence`（R17，注明取自 ETD 哪一列）/ `params[].kind∈{enum,opaque,semantic}` / `show_policy` / `click_policy`。
2.2 **`change_type` 必填（R19，决定反例形态）**：`new_event`（本需求新增埋点）或 `param_added`（已有埋点在新场景新增参数，须用 `params[].added=true` 标出新参）。取自 ETD「变更类型/是否新增」列并写 `change_evidence`；草稿留空 = 该列缺失或写法认不出，**必须查 ETD 或反问后补**，禁止默认 `new_event`（默认就是「反例写成不上报」的来路）。
2.5 **`test_kit` 必填（R6）**：`{source_doc, packages{ios,android}, env, libra_flights[], server_config[], accounts[], missing[]}`。`packages`/`env`/`libra_flights`/`accounts` 任一为空且未在 `missing[]` 登记 `{field, reason, gap_id}` → 门禁失败。这一节是「测试物料没上 bits」的唯一事实源：Step 4 写 Precondition、Step 5 传 `--precondition-tools-json` 都从这里取值。
3. GT/产品多出的入口写入 `out_of_scope`（带 reason），**不要**放进 `entrances`。
4. ETD 正文外链写入 `outbound_links_ignored`（或用户明示并入后才进 `events`）。
5. PRD 触发条件（如“条件1/条件2”、有无口播习惯、正反向展示条件）写入 `scenario_axes`，用于生成 show/click 的正反向场景；这些条件**不得**新增 event/param。
6. 多个枚举轴有相关性时写入 `expected_combinations`，用于校验完整有效组合（例如 `position_before + position_after + is_button`），禁止只靠单枚举值覆盖。
7. `conflicts[]` 中 `severity=blocking` 项必须带 `status=resolved|waived|out_of_scope` 之一，否则 `check_etd_scope.py` 必须失败。
8. **ETD 原文留档**（每次必做）：把本需求 ETD 的机读正文落到 `…/ui-md-event2case-gen/etd_raw.json`（Sheet = `etd_sheet_load.py` 的输出；Docx/md = 正文文本文件）。它是反查「scope 自己抽漏事件」的第二源，**测新/回归都有**。
9. 立刻校验（`--etd-text` 每次都带）：

```bash
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/check_etd_scope.py \
  --scope tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_scope.json \
  --etd-text tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_raw.json
```

> `--etd-text` 反查三件事，都是「scope 自己抽漏」的静默失效点：
> 1. **漏事件** —— ETD 原文有、scope 没有 → 失败；确实不验的写进 `out_of_scope`（`dim=event`，`value` 支持 `前缀*`）。抽不到任何事件名也判失败，不会静默通过。
> 2. **漏枚举取值 / 漏必传参** —— 按列头解析 ETD 的「param取值」「是否必传」列逐个比对（问题：只抽了 `action_type` 的一半取值，事件名反查完全看不出来）。确不验 → 写 `conflicts`/`out_of_scope`，或给该参数加 `coverage_waiver`。
> 3. **上报端写反** —— ETD「用户类型/上报端」列 vs `scope.events[].roles`（R17）。
>
> 列头认不出时会打印 `WARN: ETD 表头未识别…已跳过`，此时上述 2/3 需人工逐列核对 —— **看到这行 WARN 不等于通过**。

非 0 → 修好再进入红线判定 / 矩阵展开。后续矩阵叶子 **只能** 来自该文件，禁止边写 case 边扩维。

### Step 1.6: 事故红线适用判定（R7，硬卡点 — 写用例前必须完成）

打开 [`incident-redlines.md`](https://code.byted.org/livearch/live_tracking_knowledge_base/blob/main/knowledge-guidelines/testing-phase/case-design/incident-redlines.md)，对登记表 **每一条 RL**（当前 RL-001～RL-012，及文档后续新增）做适用判定：

1. 读该条「适用场景（命中即必检）」——用本需求事件名/参数/交互（`_show`、拖拽、click、AB 实验、公参 `room_id`/`anchor_id`、二跳等）自动匹配。
2. **命中** → 必须读该红线「详情」节（必检模式 / 边界场景列表），把对应边界写进候选用例矩阵（不要只标「已覆盖」却无真实用例）。
3. **未命中** → 覆盖表写 `⚪ 不适用` + **一句话理由**（禁止空理由）。
4. 产出内部「红线适用表」（生成全程对照）：

```text
RL-ID | 命中? | 必检边界摘要 | 拟覆盖用例 id / 不适用理由
```

> 文档原话：**「任何 agent / 人在生成埋点测试用例前，必须逐条核对本清单是否适用；适用却未覆盖，视为用例不合格。」** 本 skill 原样执行，不得跳过。

### Step 1.7: 知识盲区闸门（R9，硬卡点 — 写终稿前必须过）

对照 [`references/kb-gap-interactive.md`](./references/kb-gap-interactive.md)：

1. 扫 `business-ui_routes/`（子目录名 → 文件名 → 文件内「UI路径」章节），对矩阵所需导航段做命中判定。
2. 汇总阻塞型盲区（`ui_route` 未命中、提测缺包/ppe/flight、ETD 缺关键枚举、拿不到红线文档等）到  
   `tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/kb_gaps.json`。
3. **若存在未 resolve 的 `severity=blocking`**：
   - 写 `kb_gaps.json`；**默认短反问**（全 agent）；仅当宿主有 `AskQuestion`/用户要 Canvas 时再用增强 UI
   - **停止**写终稿（矩阵草稿可留）
4. 用户补齐后写回 `answer`，evidence=`user_supplied:<gap_id>`，再继续。
5. **回填知识库**：对可复用的答案（`ui_route` 导航、本需求 ETD 的枚举/参数口径）在 gap resolve 后沉淀回 `live_tracking_knowledge_base`（`tt_nova` 分支、人确认、带 provenance），下次直接命中不再反问；一次性答案（包/ppe/flight/byteio）不回填。规则见 [`references/kb-gap-interactive.md`](./references/kb-gap-interactive.md)「回填知识库」节。
6. 反例：Notes 写缺 routes，Path 却已完整编造且从未反问。

### Step 2: 读 PRD + ETD + 提测文档，按 `etd_scope.json` 拆矩阵（R8 + R12/R13）

> **本步不读 GT**（旧手工用例集）。GT 只在终稿后做对账反思，见 Step 6.5。

- **范围文件优先**：展开公式与反模式见 [`references/etd-scope-matrix.md`](./references/etd-scope-matrix.md)。没有合法 `etd_scope.json` → 回 Step 1.55。
- **PRD → 触发方式 / 角色**：条件展开（R1）；PRD 触发条件可以补充 `scenario_axes` / 正反向场景，但 event/param/enum 仍以 ETD scope 为准；入口仅保留 `etd_scope.events[].entrances`。
- **提测文档 → 测试准备**：包 / env / 实验 / 账号（R6）。
- **UI 差异（R4）**：仅 `params.kind=enum` 的轴拆行。

产出矩阵（可落 tmp）：每个
`(event, role, entrance∈scope, enum轴取值|—, polarity)` = 一条候选用例；
再按各事件 `show_policy`/`click_policy`（R14）加重复操作叶，再加红线增量。

### Step 3: 按埋点断言契约拆分用例

严格遵循 [`references/tracking-assertion-contract.md`](./references/tracking-assertion-contract.md)。核心规则：

1. **矩阵铺满（R8∩R12/R13）**：锁定表内每个事件的角色/ETD 入口/断言枚举轴/show|click 可区分组合都有叶子；opaque 轴不拆。
2. **一条用例一个断言时机（R18）**：每条用例只聚焦一个 `event_name` 的一次触发；到达触发点前的操作（含必经的曝光、开面板）**只写步骤、不挂埋点断言**。要验曝光就单独成条（曝光一条、点击一条），基线+增量例外须在 Notes 写 `- 多时机例外: <理由>`。
3. **断言 ⊆ ETD（R3）+ 语义参（R15）+ 入口绑定（R16）**。
4. **show 去重 / click 按次（R14）**：勿混用。
5. **正/反向**：上报 / 不上报成对（仍须在 ETD 范围内）。
6. **红线增量（R7）**：矩阵之后再套红线；覆盖表 + `check_redline_coverage.py`。
7. **冷启动独立**：入口状态从零复现。

### Step 4: 生成自动化 Markdown 用例（单一事实源，落 git 知识库）

按 [`references/output-contract.md`](./references/output-contract.md) 生成自动化 md，格式对齐
[`../ui-md-case-gen/references/testcase-normalize-SKILL.md`](../ui-md-case-gen/references/testcase-normalize-SKILL.md)
（五个必备 section：`> 目标` / `**Path**` / `**Precondition**` / `**Steps**` / `**Assert**`）。

**写 git 前先确认 `biz_line`**：必须 ∈ `{SMB, activity_platform, game, multi_guest, revenue, user_product, wallet}`。未指定或拼写不在表内 → 用「业务线反问模板」硬停，**禁止**写到 `ui-test/` 根目录或臆造子目录。

**产物直接写入 git 知识库 `live_tracking_knowledge_base`**（不走 TOS）：
`<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`（`<KB>` 为 Step 1 的本地 clone）。
推荐并排产出结构化 sidecar `<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.cases.yaml`（schema 见 CASE-SCHEMA），便于知识库回抽建图。目录不存在则 `mkdir -p`。

埋点专属约定：

- **`**Path**`（R2+R9）**：写成从 TikTok 主页起的可执行导航链；每一段要么命中 `business-ui_routes`，要么来自已 resolve 的 `user_supplied:G-xxx`。禁止 `模块 / 子模块 / 埋点类型` 标签路径；禁止 routes 未命中时自行编完整链。
- **Steps（R1）**：禁止「条件1/条件2/触发场景N」等未展开缩写；条件全文内联；操作描述具体到控件区域（CTA / 非 CTA）。
- **埋点断言用 `data` category**。写成可机器解析：`` data | 上报 `event_name` 埋点；参数 `key` = `value`；`key2` 有值；不上报 `key3` ``。
- **BITS 预期结果必须包 `data_assertion` 工具**（转换器自动做）：自然语言 Assert 经 `md_case_skill_upload` 转 xmind 时，会拆成
  `data_filter_name=<event>` + `assert_type=AppLog` + `assertion=<参数正文>`。
  例：`上报 \`livesdk_ai_guide_entrance_show\` 埋点；\`anchor_id\` 有值；\`enter_from\` 有值；\`room_id\` 有值。`
  → `data_assertion data_filter_name=livesdk_ai_guide_entrance_show assert_type=AppLog assertion=\`anchor_id\` 有值；\`enter_from\` 有值；\`room_id\` 有值`。
  **禁止**把埋点断言写成纯文本预期节点；反向「不上报」同样包 `data_assertion`（`assertion=不上报`）。
- **`测试准备`（R6，P0）**：取自 `etd_scope.json.test_kit`，**必须同时**落两处 —— ① 文件头 `## 测试物料(Test Kit)` 段（给人看）；② **每一条用例的 `**Precondition**`**（给人看 + 门禁扫）。至少写全 `- mock | env={test_kit.env}（来源：提测文档）` 和 `- mock | 账号已加实验 libra flight/{id}`。**Bits 可执行节点不靠这些 mock 行自动生成**，而靠 Step 5 `--precondition-tools-json` 按选型落地工具。**只写文件头不写 Precondition = 不合格**。门禁 `check_etd_scope.py --cases` 会逐条反查。
- 事件名一律反引号包裹；参数值写成 `` `参数` = `值` ``（便于知识库回抽，见 CASE-SCHEMA）。
- **不臆造（R9）**：事件/枚举/路径/env 缺来源 → `kb_gaps.json` + 开卡；blocking 未齐不写终稿。

写入后按知识库约定重建映射图并提交/提 MR（见 [`references/knowledge-base-guide.md`](./references/knowledge-base-guide.md)「用例回写」）：`cd <KB> && python tools/build_mapping.py`。

**git 分支统一用 `tt_nova`；`tt_nova` 是多人共用的长期分支，基线永远取远端 `tt_nova`，不是 `main`。** 按下面这套幂等流程推，被拒就整套重跑一遍（**不要 rebase**：`tt_nova` 上有 main 的合并提交，rebase 会把它们重放出冲突）：

```bash
cd <KB>
git fetch origin tt_nova                       # 远端没有该分支时改用 origin/main 作基线
git checkout -B tt_nova FETCH_HEAD             # 基线 = 最新远端 tt_nova，丢弃本地漂移
cp <生成的用例 md> knowledge-business/ui-test/{biz_line}/   # 重新落产物（含 KB 回填的追加）
python tools/build_mapping.py
git add -A && git commit -m "<msg>"
# G9：用重试脚本替代裸 git push，自动 fetch+rebase+重试，避免并发 non-fast-forward
python3 $S/scripts/git_push_with_retry.py --repo <KB> --branch tt_nova --max-retries 2
```

> 产物在本地重新生成即可，所以「重跑一遍」永远安全 —— 这比解冲突快，也是并发下唯一稳定的姿势。推之前先确认产物文件已经写好，否则 `checkout -B` 会连同未提交的改动一起带走。`git_push_with_retry.py` 退出码 0 = push 成功；非 0 = 重试后仍失败，按脚本输出手动处理。

`source_url` 的 `<ref>` 优先写 `tt_nova`（合入后可再回填 commit sha）。
### Step 5: 转换为 BITS xmind 用例包（人读 + 自动执行）

复用 `ui-md-case-upload` 的转换逻辑（**只转换、不上传**），把 Step 4 落在知识库里的自动化 md 转成 bits xmind 包 `*_cases.md` + `*_richtext.md`。

**前置工具选型（对齐 `ui-xmind-case-gen`，禁止混塞）**：

| 物料 | 正确工具 | params | 禁止 |
|---|---|---|---|
| PPE / 泳道 `test_kit.env` | `环境名称` | `env=<ppe_xxx>` | ❌ 塞进 `ttmock_preset` 的 `env`/`libra` |
| Libra flight | `libra实验` | `region=` + `libra_id=` + `group_id=`。**仅当用户提供了 Libra 链接时**：URL 抽 `libra_id`/`region`；缺 `group_id` 分别问实验组与对照组，再按 case 分配（正向→实验组、对照/反向→对照组）。无链接则不套本流程。规范见 [`../references/libra-group-assignment.md`](../references/libra-group-assignment.md) | ❌ `ttmock_preset libra=` / `ab_settings=flight:...`；❌ 只问一个笼统 group_id；❌ 无链接却追问成对 group |
| 地区 / 语言 | `ttmock_preset` | `region=` / `language=` | |
| debug AB / Settings KV | `ttmock_preset` | `ab_settings={"<key>":"<val>"}` 或 `ab_settings_live={...}` —— **必须是 JSON 对象 string** | ❌ JSON 数组、非 JSON、`libra=` |
| Gecko Channel/Package 等 | `Gecko 配置` | 见 xmind-case-gen | ❌ 误用 `GeckoX_settings`（后者只改 local_test/boe/online） |

MD 里的 `- mock | env=...` / `- mock | libra flight/...` **只给人看 + 门禁扫**，转换器**不会**自动解析成工具；可执行节点全靠 `--precondition-tools-json`。

```bash
python3 ../ui-md-case-upload/scripts/md_case_skill_upload.py \
  --input /abs/<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md \
  --vc {vc} --module {module} --ui-path {ui_path} \
  --out-dir /abs/.../tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen \
  --tmp-dir /abs/.../tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen \
  --source-url 'https://code.byted.org/livearch/live_tracking_knowledge_base/blob/tt_nova/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md' \
  --source-url-in-step \
  --precondition-tools-json '{"precondition_tools":[{"tool":"环境名称","target":"all","params":{"env":"<test_kit.env>"}},{"tool":"libra实验","target":"all","params":{"region":"<region>","libra_id":"<flight1>","group_id":"<group1>"}},{"tool":"ttmock_preset","target":"all","params":{"region":"<store_region>","language":"zh"}}]}' \
  --skip-upload
```

- **`--precondition-tools-json` 必传（R6，P0）**：按上表从 `etd_scope.json.test_kit` 选型组装。多个 flight → 多条 `libra实验`。**仅当用户提供了 Libra 链接**且缺 `group_id`：**停下来分别问实验组 / 对照组**（可附截图/版本表），写入 `treatment_group_id` / `control_group_id`；**正向 case 挂实验组、对照/反向 case 挂对照组**。无 Libra 链接则不套该成对追问。禁止猜、禁止只问一个 group、禁止改塞 `ttmock`。详见 [`../references/libra-group-assignment.md`](../references/libra-group-assignment.md)。
- 若提测还给了 debug AB / settings 键值，另加 `ttmock_preset` 的 `ab_settings`（JSON 对象）。**有则必检**：
  ```bash
  python ../ui-xmind-case-gen/script.py check-json-object --param ab_settings '<值>'
  ```
  `ok:false` 或转换报 `[INVALID_JSON_OBJECT]` → 重写后再跑 Step 5；禁止数组 / `flight:` / 把 libra 塞进 ttmock。
- `test_kit.env` / `libra_flights` 登记在 `missing[]` 时，对应工具可省略（门禁不再 expect）。

- 埋点断言（`data` 预期）会作为**预期结果节点**原样搬进 xmind，人可读、AI 可执行。
- **自动化 md 附属在 xmind 用例备注里 = git 地址引用**：`--source-url` 显式传该 md 在 `live_tracking_knowledge_base` 的 git 链接（`<ref>` 优先 `tt_nova`，合入后可回填 commit）。**不走 TOS**。
- **溯源备注恒定挂在操作步骤行**：`**[remark]** [md] <用例标题> + <source_url>` 作为 note 内联挂到操作步骤行末，下游要从步骤里读回 git 链接，落到前置条件就读不到了。备注**不带** `<ttat>`（那只是前置条件节点的标记约定），前置条件仅保留一条空 `**[remark]** <ttat>`。备注永远与内容同行、不单独成行（BITS 导入器会把独立 `**[...]**` 行当成空预期结果节点）。`--source-url-in-step` 已废弃为空操作，加不加都一样。
- md 尚未推到远端时：`<ref>` 先用分支名 `tt_nova` 占位；或直接用 `git://<repo_id>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md?ref=tt_nova`（`ui-md-case-upload` Git 输入模式即用 git uri 作 `source_url`，天然不传 TOS）。

### Step 5.5（可选，"both" 断言的自动校验）: 绑定 et_checker_G20

当能拿到 **ByteIO 用例**（`ID`/`Name`/`AppID`/`Region`，来自 ByteIO 平台或 ETD）时，除自然语言预期外，再叠加确定性自动校验：走
[`../ui-xmind-case-specify/SKILL.md`](../ui-xmind-case-specify/SKILL.md) + [`../ui-xmind-case-gen/SKILL.md`](../ui-xmind-case-gen/SKILL.md)
路径——在 spec 第 7 章 seed 的第 5 列写 `byteio_case_list`，`ui-xmind-case-gen` 会把 `et_checker_G20 byteio_case_list=[...]` 确定性注入到断言步骤的预期结果节点。

- **被识别为埋点需求但拿不到 ByteIO 用例列表时**：**不要臆造**，按 `references/tracking-assertion-contract.md` 的反问模板向用户索要 `ID`/`Name`/`AppID`/`Region`；拿不到就只保留自然语言埋点断言。

### Step 6: 覆盖自检（落盘前）

**先跑总门禁 —— 这是唯一的交付判据，非 0 不得交付：**

```bash
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/run_gates.py \
  --workdir tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen
```

它自动发现工作目录里的产物并依次跑：① 产物齐全 ② `check_etd_scope.py`（scope 校验 + 覆盖度防漏 + test_kit + ETD 反查事件/枚举/上报端 + **断言时机拆分(G11)** + **draft 草稿删减校验(G8)** + **Docx 弱反查(G7)**）③ **`check_xmind_precondition.py`（G2：`环境名称` / `libra实验` / ttmock `ab_settings` 选型与格式）** ④ `kb_gaps` 阻塞项 ⑤ 事故红线覆盖表（调 KB 的 `check_redline_coverage.py`）⑥ 未登记占位。每个失败项都会打印「下一步做什么」。

- **红了就按提示修，修完重跑，直到全绿**。禁止用「我自检过了」代替跑它。
- 输出里出现 `⚠ 未执行`（例如 KB 没 clone 导致红线门禁没跑、ETD 表头没认出导致枚举反查跳过）**不等于通过** —— 要么补齐条件重跑，要么人工核对并在交付说明里写明结论。
- 需要单独调试某一项时再直接调 `check_etd_scope.py`（参数见 [`etd-scope-matrix.md`](./references/etd-scope-matrix.md) 六）。

下面的清单里，🤖 标记的条目**已由上面这条命令机器判定**，你不必逐条自查；未标记的仍需人工确认：

- [ ] **R1** Steps/Precondition 无未展开的「条件N/场景N」缩写；触发条件全文可读。
- [ ] **R2** 每条 `**Path**` 从 TikTok 主页起；段来源 = routes 命中或 `user_supplied:G-xxx`；无「模块/埋点类型」标签路径。
- [ ] **R3** 每条事件 Assert 参数 ⊆ 本需求 ETD 参数表；必传全有；无多余参数。
- [ ] **R4** 本需求 ETD 会断言区分的 UI 差异（CTA/非CTA、有/无按钮等）都有独立用例；ETD 未声明的不拆。
- [ ] 🤖 **R5** 产物事件集合 == Step 1.5 锁定表；无串用其它/外链 ETD 事件；本需求 ETD 声明的事件无遗漏。
- [ ] 🤖 **R6** 提测/测试说明文档**已实际解析**（不因标题不叫「提测文档」而跳过）；包/ppe/实验/账号已落 `scope.test_kit`，空字段在 `test_kit.missing[]` 有 `reason`+`gap_id`；**env 与 libra flight 已写进每一条用例的 Precondition**（不是只写文件头）；Step 5 按选型传了 `--precondition-tools-json`（env→`环境名称`，flight→`libra实验`，AB KV→`ttmock ab_settings` JSON 对象）。无臆造、无把 env/libra 塞进 ttmock。
- [ ] 🤖 **R17** 每个事件的 `roles` 取自 ETD「用户类型/上报端」列并有 `roles_evidence`；用户侧事件的 Steps/Assert 用观众设备（不是一律 `设备A（主播）`）；`--etd-text` 的上报端反查通过。
- [ ] 🤖 **R18** 每条用例只有一个断言时机 =（一个事件 + 一个 `action_type`）；**没有任何一个操作步骤下挂两条及以上埋点断言**；前置导航步骤（含必经曝光）没挂埋点断言；基线+增量类用例已在 Notes 写 `- 多时机例外: <理由>`。
- [ ] 🤖 **R7** 已读 `incident-redlines.md` 全文登记表；命中 RL 已读详情并有对应用例；覆盖表对每条 RL 有 ✅/⚪（含理由）/❌；`check_redline_coverage.py` 通过。
- [ ] **R8** 矩阵铺满锁定表内维度（非抽样）；Assert 词表 = ETD；GT 未扩维；红线为增量。
- [ ] **隐性规则** 已读 `knowledge-quality/test-automation/埋点隐性规则 - Sheet1.csv` 并逐条判定适用性：click 一次只报一次、page 曝光不多报（组件曝光允许多报，未误判为错）、结果类成功报一次/失败 ≤1 次、id 类参数互不相等、反向用例已设计；命中项在 Notes 标来源。适用却未覆盖 = 不合格。见 tracking-assertion-contract 3.4。
- [ ] 🤖 **R9** `kb_gaps.json` 中 blocking 均已 resolve（或本轮无 blocking）；曾开过补齐卡；无「Notes 写缺 routes 但 Path 已完整编造」矛盾。
- [ ] **R10** Sheet ETD 已用 `etd_sheet_load.py`（带 style）；`struck_summary` 中的作废枚举未进锁定表/矩阵。
- [ ] **R11** 多角色用例 Steps/Path/**Assert** 均以 `设备X（角色）：` 指派；Test Kit 有角色表；无「未声明主语」的进房/开播/断言。
- [ ] 🤖 **R12–R16 门禁** `etd_scope.json` 已落盘且 `check_etd_scope.py --scope … --cases …` 退出码 0；无 GT/外链扩维；opaque 未拆表情；click 按次；语义参有口径；入口与 `link_page_entrance` 等绑定。
- [ ] 🤖 **scope 抽漏反查** 跑了 `--etd-text`（ETD 原文，每次必带），三层都过：漏事件 / **漏枚举取值·漏必传参** / **上报端**。Sheet 形态还要确认走了 `--emit-scope-draft` 起草（没走 = 肉眼读宽表，漏枚举的老路）；若打印了 `WARN: ETD 表头未识别`，必须人工逐列核对并在此说明结论 —— **WARN ≠ 通过**。（GT 对账属 Step 6.5 事后反思，不在生成路径上）
- [ ] 🤖 **覆盖度门禁（防漏，同一条命令）** scope 每个事件都有正向用例（防漏事件）、每个 enum 参数的**每个取值**都有叶子（防漏 `is_button=0` 这类）、每个事件都有反向「不上报」用例；确不适用的必须在 scope 写 `coverage_waiver` / `negatives_waiver` 理由。**禁止以「自检已通过」代替跑脚本**——散文 checklist 换模型就会静默漏。见 [`etd-scope-matrix.md`](./references/etd-scope-matrix.md) 五之二。
- [ ] **biz_line** 已由用户选定且 ∈ 固定枚举（选项释义取自 `TT直播横向业务简介 - Sheet1.csv`；可推荐但不可替用户拍板）；KB 路径为 `knowledge-business/ui-test/{biz_line}/…`（非 `ui-test/` 根）；git 分支为 `tt_nova`。
- [ ] 🤖 正/反向是否都覆盖，且**反例形态对**（R19）？`new_event` → 「不上报该事件」；`param_added` → 「仍上报但不带新增参数」。run_gates 按 `change_type` 分别反查，形态错报 `反例形态错`。
- [ ] 事件名/枚举是否都有 `evidence`？未 resolve 的 blind 是否仍阻塞交付？
- [ ] 两份产物（xmind `*_cases.md` 与自动化 md）逻辑是否一一对齐？**改一边必须同步另一边**（权威源=自动化 md → 再转换 xmind）。
- [ ] **双边质量分轨**：人读 xmind 标题/预期可读；自动化 md 的 Steps 逐步可执行（无「若…则」「观察一下」等模糊话）。见 `output-contract.md` §零。
- [ ] **断言只验埋点**：所有 `Assert`/预期结果只用 `data`（埋点上报/参数）作通过判据；无功能性断言（面板弹出/跳转成功/toast/建联/静音生效等）；功能只作步骤描述。见 tracking-assertion-contract 第零节。
- [ ] 规范化自检：五个必备 section、Precondition ∈ `{mock,navigate,assume}`、Assert 仅 `data`（必要时 `defer`）、多用例仅以单行 `---` 分隔。

### Step 6.5: GT 对账反思（可选，**终稿之后**）

**只在回归/改版且用户给了旧手工用例集时做；测新没有 GT，跳过。** GT **不参与前面任何推理**，这里只用来回头照镜子：

```bash
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/check_etd_scope.py \
  --scope …/etd_scope.json --gt-seeds …/gt_seeds.json \
  --gt-diff-output …/gt_scope_diff.json --gt-diff-only
```

- 差异（GT 有、scope 没有的事件/枚举）**只作为反问材料**：问用户「这是本次抽漏了，还是确实不验？」
- 用户说抽漏 → 回 Step 1.5 补 scope、重跑生成与门禁；用户说不验 → 写进 `out_of_scope` / `conflicts` 并注明理由。
- **禁止**照抄 GT 的用例写法、入口、维度直接补进终稿。范围权威始终是本需求 ETD 正文。

## Output

- **自动化 Markdown 用例（权威源，落 git 知识库）**：`<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`（+ 推荐 sidecar 同目录 `{ui_path}_cases.cases.yaml`），在分支 **`tt_nova`** 上提交/提 MR 到 `live_tracking_knowledge_base`。`biz_line` 见 Inputs 固定枚举。
- **BITS xmind 用例包**：`<repo_root>/tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_cases.md` + `{ui_path}_richtext.md`（转换中间产物先落 `tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/`，确认后再拷到 `xmind/`）。xmind 用例备注引用自动化 md 的 **git 地址**（非 TOS）。
- **tmp 目录留给用户看的终稿（仅这三类）**：
  - `{ui_path}_source_cases.md`（自动化权威源本地副本）
  - `{ui_path}_cases.md` + `{ui_path}_richtext.md`（BITS 上传包）
- **`etd_scope.json` 保留（不删）**：它是覆盖度门禁的期望集合，也是同需求换 agent 重跑时的**覆盖基线**——删了就无法复跑门禁、无法解释「这次为什么少了 6 条」。与终稿同目录留存。
- **`kb_gaps.json` 有 `deferred` 项时必须保留**（不删）：用例里的 `TODO-KNOWLEDGE` 占位靠它的 gap id 证明「是已登记的已知缺口，不是偷懒」。全部 gap 都 `resolved` 时才可删除，否则 `run_gates.py` 会判「占位无法核验」。
- **其余过程文件交付后删除**：`etd_scope.draft.json` / `event_lock.md` / `matrix_coverage.md` / `kb_gaps.json`（**全部 resolved 时**）/ `*_manifest.json` / GT 导出 / diff 笔记等，**不要**留在 tmp 里给用户看。生成过程中可暂存，终稿交付前清掉。
- **知识补齐（R9）**：可移植核心 = `kb_gaps.json` + 对话硬停反问；`AskQuestion`/Canvas 仅 Cursor 可选增强。硬停期间 `kb_gaps.json` 可暂留；gaps resolve 且终稿交付后删除。
- **盲区回填（沉淀）**：可复用答案（UI 路径、本需求 ETD 枚举/口径）经用户确认后回填 `live_tracking_knowledge_base`（`tt_nova` 分支、带 provenance），随用例回写同一 MR；**只追加到本轮参考过的现有 KB 文件，禁止新建文件/目录/条目**，找不到现有文件则标 skipped 并提示手动补；一次性答案（包/ppe/flight/byteio）不回填。详见 `references/kb-gap-interactive.md`「回填知识库」。

交付后提示用户：自动化 md 已（或将）合入 `live_tracking_knowledge_base` 的 `tt_nova` 分支、`knowledge-business/ui-test/{biz_line}/`（备注 git 链接才生效）；如需上云，用 `ui-md-case-upload` / `ui-xmind-case-upload` 上传（`source_url` 用 git 地址，不走 TOS），再用 `ui-debug-task-exec` 云上调试执行。

上传 bits 时：若用户给了参考用例链接，`--project_id` 取 URL 路径 `/devops/{id}/`（如 `1499051266`），**不要**用 `devops_space_old_id`（如 `66666866`）；`--dir_id` 取 `dirId`。详见 [`../ui-md-case-upload/SKILL.md`](../ui-md-case-upload/SKILL.md)。

**交付前隐性检查（强制）**：`run_gates.py` 绿了不等于 Bits 节点一定对。上传后按父 skill 清单过一遍 P0，并用清单末尾话术提醒用户——尤其：env/libra 是否进了每条 Precondition、remark/git 是否在步骤、多设备是否换行、Assert 是否只有埋点。清单：[`../references/case-delivery-checklist.md`](../references/case-delivery-checklist.md)。

## Resources

- [../references/case-delivery-checklist.md](../references/case-delivery-checklist.md) — **交付前隐性问题清单（P0/P1）**：remark 位置、设备换行、账号、并行、project_id、测试物料等
- [../references/libra-group-assignment.md](../references/libra-group-assignment.md) — **有 Libra 链接却缺 group_id**：分别问实验组/对照组并按 case 极性分配（无链接不套此流程）
- [references/etd-scope-matrix.md](./references/etd-scope-matrix.md) — **R12–R16 操作手册**：权威阶梯、`etd_scope.json`、断言轴判定、入口绑定、历史反模式、门禁命令
- [references/tracking-assertion-contract.md](./references/tracking-assertion-contract.md) — 埋点断言四类逻辑、参数 ⊆ ETD、UI 差异拆行、evidence/红线/et_checker_G20 与反问模板
- [references/output-contract.md](./references/output-contract.md) — 两份产物结构、可执行 Path、`测试准备` 映射、备注附属打包、落盘路径
- [references/knowledge-base-guide.md](./references/knowledge-base-guide.md) — live_tracking_knowledge_base 拉取与路由（事件字典 / ETD / 红线 / UI routes / 入口命名）
- [references/kb-gap-interactive.md](./references/kb-gap-interactive.md) — R9：kb_gaps 硬停（跨 agent）+ Cursor 可选 UI
- **`scripts/run_gates.py` — 交付门禁总入口（唯一交付判据）**：自动发现工作目录，一条命令跑完全部检查并打印「下一步做什么」。`--self-check` 可自测
- `scripts/etd_sheet_load.py` — Sheet ETD + 删除线（R10）；`--emit-scope-draft` 按列头解析出 `etd_scope.json` 草稿（全量事件 / 上报端 / 必传参 / 枚举取值，处理合并单元格与格内换行）
- `scripts/check_etd_scope.py` — `etd_scope.json` + source_cases 门禁：反模式（R12–R16）、覆盖度防漏、`test_kit` 与用例级 Precondition 反查（R6）、ETD 原文反查事件/枚举/上报端（R17）
- 复用同集 skill：`../ui-md-case-gen`（自动化 md 规范化契约）、`../ui-md-case-upload`（md→xmind 转换、备注 source_url）、`../ui-xmind-case-gen` + `../ui-xmind-case-specify`（et_checker_G20 自动埋点校验路径）
