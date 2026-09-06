# 埋点断言契约（Tracking Assertion Contract）

本文件定义埋点用例里"断言什么、怎么写、来源是谁"。综合三处事实源：

- 参考手工用例集：`实时主播中心入口UI样式优化-埋点case`（BITS 15225705，提词器 `livesdk_anchor_manager_cues_msg_*`）
- 埋点断言逻辑 wiki（`bytedance.larkoffice.com/wiki/J1RIwBCxDif1jqkXDwTcxko0nDe`，为 Sheet）
- 知识库 `live_tracking_knowledge_base`：`case-design-config.md`（必检项）、`CASE-SCHEMA.md`（机读约定）、`incident-redlines.md`（事故红线）、`knowledge-quality/test-automation/埋点隐性规则 - Sheet1.csv`（**埋点隐性规则**，见 3.4）

## 零、断言只验埋点，不验功能（硬规则，最高优先）

本 skill 产出的**埋点用例**，断言点（`**Assert**` 与 Steps 内 `- Assert:`）**只关注埋点上报**，**不检查功能是否正确**：

- **只允许 `data` category**（埋点上报 / 参数）作为断言与**通过判据**。埋点用例的通过=失败只由「事件是否上报、参数是否符合本需求 ETD」决定。
- **禁止把功能性观察写成断言**：如「面板成功弹出」「页面跳转成功」「toast 出现」「AI 建联成功」「布局正确」「静音生效」等 **UI/功能验收**，不得作为 `Assert` / 预期结果 / 通过判据。
- 功能操作只作为**到达埋点触发点的步骤描述**放在 `Steps` 里（人话控件名即可），**不挂 `state`/`visual`/`text` 断言**去校验功能对错。确需描述"面板已出现"作为触发前置时，写进步骤正文（"…等待面板完全弹出后…"），不要写成 `- Assert: state | 面板展现`。
- 涉及功能回归的事故红线（如 RL-007「埋点不破坏功能」、RL-009 下游功能影响）：在本 skill 里**只承接其埋点侧**（该报/不该报、参数取值），功能是否受损**不在本 skill 断言范围**，如需覆盖请在覆盖表理由里注明「功能回归另行功能用例保障」。

> 一句话：这里是**埋点验证用例**，不是功能验收用例。断言里出现任何非 `data` 的功能校验 = 不合格。

## 一、四类埋点断言（穷举，每类都要能表达）

| 类别 | 语义 | 写法（自动化 md，`data` category） | 手工用例集原文示例 |
|---|---|---|---|
| 事件上报 | 事件应上报 | `` data | 上报 `event_name` 埋点 `` | 上报 `livesdk_anchor_manager_cues_msg_show` 埋点 |
| 事件不上报（反向） | 事件**不应**上报 | `` data | 不上报 `event_name` 埋点 `` | 不上报 `livesdk_anchor_manager_cues_msg_change_position` 埋点（变化未成功） |
| 参数=值 | 参数取具体值/枚举 | `` data | 参数 `key` = `value` `` | 参数 `is_button` = `1`；`action_type` = `click_cta`；`position_before` = `up` |
| 参数有值 / 参数不上报 | 必传参数非空 / 某参数被移除 | `` data | `key` 有值 `` / `` data | 不上报 `key` `` | `suggestion_template_id`、`show_text`、`msg_type`、`msg_id`、`anchor_id`、`room_id` 均上报有值；`playbook_id`、`play_id` 不上报了 |

> **BITS 落盘硬约束**：上述自然语言 Assert 转 xmind 时**必须**包成 `data_assertion` 工具节点（`assert_type=AppLog`，`data_filter_name=<event>`，`assertion=<参数正文>`）。转换器（`md_case_skill_upload`）自动完成；不要手写纯文本预期节点。
> 例：`上报 \`livesdk_ai_guide_entrance_show\` 埋点；\`anchor_id\` 有值；\`enter_from\` 有值；\`room_id\` 有值。`
> → `data_filter_name=livesdk_ai_guide_entrance_show` / `assert_type=AppLog` / `assertion=\`anchor_id\` 有值；\`enter_from\` 有值；\`room_id\` 有值`。

一条用例的预期结果 = 「事件上报/不上报」+ 若干「参数=值 / 参数有值 / 参数不上报」，可用分号连接为一条 `data` 断言，或拆成多条 `data` 断言（同一断言步骤下）。

## 二、必检项（每条用例至少覆盖对应项，来自 case-design-config.md）

1. **事件上报存在性**：`event_name` 出现在 ByteIO 日志中（对应"上报X埋点"）。
2. **触发时机准确性**：上报时机与 ETD/字典一致（展现时 vs 点击时 vs 消失时）。
3. **必传参数完整性**：本需求 ETD/字典标"必传/强保证"的参数全部有值（"参数有值"）。**漏检必传参 = 不合格**（典型反例：`cues_msg_show` 漏 `is_button`）。
4. **参数枚举值合法性**：enum 参数取值落在本需求 ETD/字典枚举范围内（"参数=值"）。**删除线/标明作废的取值不在合法范围内**（见 R10 / `etd_sheet_load.py`）。
5. **场景区分参数**：`enter_from_merge` / `enter_method` / `action_type` 等取值正确（查 `entry-source-naming.md` + 本需求 ETD）。
6. **事故红线全覆盖（最高优先）**：见第四节。
7. **断言参数 ⊆ 本需求 ETD（防多写）**：Assert 出现的每个参数必须在该事件的本需求 ETD 参数表里；**多写 ETD 未声明参数 = 不合格**。
8. **埋点隐性规则全判定**：对 `埋点隐性规则 - Sheet1.csv` 每条规则逐条判定适用性，适用即落用例（上报次数 / id 互不相等 / 反向用例）。见 3.4。
9. **事件清单 = 本需求 ETD 全集（防串用/漏事件）**：产物里的 `event_name` 集合必须等于用户提供的本需求埋点设计文档声明的事件集合。禁止从「相近」知识库 ETD 偷事件进来（典型反例：串入 `cues_switch_*` / `realtime_live_center_module`）；禁止漏掉本需求 ETD 已声明事件（典型反例：漏 `cues_msg_change_position`）。

### 2.1 Sheet ETD 删除线（R10）

飞书 Sheet 上用 **删除线**（`font_line=line-through`）标掉的枚举/说明 = **已作废**，不得进锁定表、不得生成用例。

- 读取：`ui-md-event2case-gen/scripts/etd_sheet_load.py`（`+cells-get --include value,style`）。
- 整格删除线 → 该格文本丢弃；富文本混排 → 只丢划掉的 segment。
- **禁止**仅用 `+csv-get` / 纯文本锁枚举（看不见删除线）。
- 仅变色无删除线 ≠ 作废。

## 三、拆行/拆用例规则（矩阵优先；范围权威 = 本需求 ETD 正文）

> **总原则**：Assert 词表与矩阵维度都跟**本需求 ETD 正文**；**GT（旧手工用例集）不参与推理**，只在终稿后对账反思；事故红线做增量。禁止只抽样交差，也禁止把 ETD 未声明的入口/表情类型铺满。  
> **操作手册 + 门禁**：[`etd-scope-matrix.md`](./etd-scope-matrix.md) + `scripts/check_etd_scope.py`（写终稿前必跑）。

### 3.0 一条用例一个断言时机（R18，先过这一条）

**一条用例 = 一次操作 + 一次校验。** 每条用例只允许**一个断言时机**。

**时机 = (事件, `action_type` 取值)**：同一个 `livesdk_xxx_panel` 的 `action_type=show` 和 `=mic` 是**两次不同的上报**，属于两个时机。所以下面三种都算合并，都会被 G11 拦：

| 形态 | 长什么样 |
|---|---|
| 断言分散在多个步骤 | 第 2 步验 show、第 3 步验 click |
| 一条用例跨多个事件 | 同一步同时验 `..._interact_panel`（`action_type=manage`）和 `..._connection_panel_show` |
| 同事件多个 `action_type` | **同一个操作步骤下**挂 `action_type=show` 和 `action_type=click` 两条断言 |

到达触发点之前的操作（开播、进房、等曝光、开面板）都是**不挂埋点断言**的导航步骤。

理由：合成一条后，执行器（人或 AI）分不清哪条断言属于哪一次操作，只能在流程跑完后回捞日志 —— 早报、漏报、上一步串下来的报，全都验不出来，用例没法直接拿去执行。曝光事件的覆盖由**它自己那条曝光用例**保证，不靠寄生在点击用例里。

```markdown
<!-- ❌ 合并 A：断言分散在两个步骤 -->
**Steps**:
1. 开播进直播间，等提词器展现。
    - Assert: data | 上报 `..._cues_msg_show` 埋点；`is_button` = `1`。
2. 点击 CTA 按钮。
    - Assert: data | 上报 `..._cues_msg_click` 埋点；`action_type` = `click_cta`。

<!-- ❌ 合并 B：同一个步骤下挂多个埋点（最常见，也最难执行） -->
**Steps**:
3. 设备A（主播）：点击自己麦位 → 点 manage → 等管理面板弹出。
    - Assert: data | `..._interact_panel`；`action_type` = `manage`。
    - Assert: data | `..._connection_panel_show`；`link_page_entrance` = `interact_panel`。

<!-- ✅ 拆条；非目标事件的那一步只导航、不断言 -->
（用例一）
**Steps**:
1. 开播进直播间，等提词器展现。
    - Assert: data | 上报 `..._cues_msg_show` 埋点；`is_button` = `1`。
（用例二）
**Steps**:
1. 开播进直播间，等提词器展现（本条不校验展现埋点）。
2. 点击 CTA 按钮。
    - Assert: data | 上报 `..._cues_msg_click` 埋点；`action_type` = `click_cta`。
```

**唯一例外**：基线 + 增量本来就是同一个判据，拆开就没法验 —— show 去重、频控窗口内不再报、生命周期二次展现、连点按次计数、同一刻多事件齐报。这类用例必须在 `**Notes**` 里显式声明，否则门禁拦：

```markdown
**Notes**:
- 多时机例外: 去重判据 = 首次展现报 1 条（基线）+ 拖动后仍只有 1 条（增量）
```

反向断言（`不上报 …`）不算独立时机，可以和正向断言同处一条用例。

### 3.0 反例形态：新增埋点 vs 已有埋点新增参数（必判，写错=反例不成立）

**先看 `etd_scope.events[].change_type`，再写反例。**

| `change_type` | 反例语义 | 反例断言写法 |
|---|---|---|
| `new_event`（本需求新增埋点） | 对照组 / 条件不满足时**整个事件不该上报** | `` data \| 不上报 `livesdk_new_event` 埋点 `` |
| `param_added`（**已有**埋点在新场景**新增参数**） | **上报时机不变**，事件照常上报，只是**不带新增参数** | `` data \| 上报 `livesdk_room_enter` 埋点；不上报 `guide_type` `` |

- `param_added` 场景**禁止**把反例写成 `不上报 <event>`：老埋点在旧场景本来就要上报，这条断言必然挂，等于没验到「新参数只在新场景带」。历史事故：营收用例集 [15917403](https://bits.bytedance.net/devops/1499051266/quality/case/caseDetail/15917403) 整批反例都是这种错法。
- 每个 `params[].added: true` 的参数都要有自己的「不带该参数」反例；也可再补「旧参数取值不变」正例。
- 真的存在「整事件不上报」的反例（新入口本身是新增的）→ scope 该事件写 `no_emit_negative: "<理由>"`，门禁才放行。
- 门禁：`check_etd_scope.py` 覆盖度检查报 `反例形态错`（缺参数级反例 / 用了事件级不上报）。

门禁：`check_etd_scope.py` G11，按上表三类分别报错；它不看步骤编号（用无编号步骤绕不过去），也认 `banner_action_type` / `event_action_type` 这类变体。

### 3.1 事件优先矩阵（人读验收主结构）

对每个本需求 ETD 事件，只展开**锁定表内**可区分维度后再落叶子（缺 **ETD 已声明** 的维 = 不合格；多出 ETD 没有的维 = 也不合格）：

| 维度 | 典型取值（**仅本需求 ETD 正文**） | 要求 |
|------|----------------------------------|------|
| 角色 | 主播 / 嘉宾 / 管理员（映射 `user_type` / `is_multi_guest_moderator`） | ETD 角色轴可区分则拆行 |
| 入口 | ETD 触发说明里的入口（如自己麦位→manage） | **仅 ETD 写明的入口拆行**；GT/产品旁路入口默认不进（R12） |
| 控件/枚举 | ETD **断言枚举轴**（如 `action_type=mic\|camera|…`） | 有离散取值表才拆；opaque id/「有值」**不拆**（R13） |
| 动作极性 | `show` / `click` | 面板/列表类默认成对（若 ETD 两者都有） |
| 重复操作 | show 去重 / click 按次 | **分极性**（R14）：show 按 ETD/红线去重；click 默认点几次报几次 |

内部先产出「矩阵覆盖表」（可落 tmp），再写用例：

```text
event | role | entrance∈ETD | control_or_enum∈断言轴|— | polarity | case_id | etd_assert_keys
```

### 3.2 断言词表 = 本需求 ETD（与步骤人话分离）

- **步骤/标题**可用好人话：`打开 TikTok 应用` → `点击自己的麦位区域` → `定位并点击麦克风按钮`。
- **Assert / 预期结果**必须用 ETD 字段：如 `` `action_type` = `mic` ``，禁止把 GT 里未出现在本需求 ETD 的名字写进断言。
- 用户给了 GT 时：**生成过程中不读它**。终稿后对账若发现 GT 有而 ETD 正文没有的入口/枚举（例如 GT 有 `action_type=disappear`、ETD 描述暗示自动退场但枚举表缺失）→ 记 `gt_etd_conflict` / `etd_enum_conflict` 并 blocking 反问用户；确认 out-of-scope 后才丢弃，确认并入后写入 `etd_scope.conflicts[].status=resolved` 与对应枚举/组合，**回到生成阶段重跑**，而不是把 GT 内容直接抄进终稿。
- PRD 可补充触发条件、场景正反向（例如“条件1满足 + 条件2不满足时入口不展示”），这些条件写入 `scenario_axes` 并生成正/反向用例；但 PRD 不得新增本需求 ETD 没声明的 event/param。
- **语义参（R15）**：`*_ucnt` / `*_cnt` / list 长度等写清口径 + 可构造期望，禁止只写「有值」。
- **入口绑定（R16）**：断言 `link_page_entrance`/`from_page`/`way_of_switch`/`action_page`=`V` 时，Path 必须是 ETD 定义会产生 `V` 的入口。

### 3.3 其它拆行规则

- **入口状态分组**：不同前置（实验组/对照组等，且 ETD 会区分）→ 不同用例组。
- **UI 差异 → 矩阵**：仅当差异落在本需求 ETD 断言轴时拆行（R4∩R12）。
- **有效组合 → 矩阵**：多个 enum 参数相关时，必须按 `etd_scope.expected_combinations` 生成并校验；禁止只让每个枚举值分别出现。
- **正/反向成对**：有「成功上报」就要有反例，但**反例形态取决于 `etd_scope.events[].change_type`**（见下）。
- **冷启动独立**：每条从零复现，把「先等面板/表情展现」写进本条步骤。
- **零缩写**：禁止「条件1/场景N/按 Path」；导航链与条件全文内联。
- **红线增量**：矩阵写完后再套 RL；红线用例补矩阵未覆盖的边界，不替代矩阵，也不得借红线名义塞进 ETD 未声明入口（串味对照叶须有 ETD 期望值差异）。

### 3.4 埋点隐性规则（每个埋点文档都要套，强制前置读）

权威源：KB `knowledge-quality/test-automation/埋点隐性规则 - Sheet1.csv`
（[在线](https://code.byted.org/livearch/live_tracking_knowledge_base/blob/main/knowledge-quality/test-automation/%E5%9F%8B%E7%82%B9%E9%9A%90%E6%80%A7%E8%A7%84%E5%88%99%20-%20Sheet1.csv)，列：`场景 | 校验维度 | 规则描述`）。

这些是 **ETD 通常不会写、但默认成立**的通用埋点规则。**任何埋点需求**在锁定表（3.1 矩阵）之上都要逐条判定适用性，适用却没覆盖 = 不合格。当前登记（随 CSV 更新，以仓库 `main` 为准）：

| 场景 | 隐性规则 | 落到用例 |
|---|---|---|
| 点击场景（入口/模块/按钮） | 通常 `action_type` = `click`；**点击一次只上报一次，不存在多报** | click 叶子按次断言；补「连点/重复点」次数用例 |
| 曝光场景（页面/模块/按钮） | 通常 `action_type` = `show`；page 曝光**一个场景只报一次、不应多报**；模块/按钮/tab 曝光**同一时间可能有多个上报**（多报不判错） | page 级 show 补去重用例；组件级 show **不要**写成「只报一次」 |
| 返回结果（充值/送礼等） | 依赖状态返回：成功态**报一次**；失败态**上报 ≤ 1 次** | 成功/失败成对拆用例，失败态断言写「≤1 次」而非「不上报」 |
| id 类值不相等 | `room_id` != `anchor_id` != `channel_id` != `pk_id` … | 断言这些 id「有值」时，同步断言互不相等 |
| 曝光/结果类反向用例 | 位置切换未成功 → 不报位置变化埋点；拖动模块 → 不重复报 show；**按埋点描述以此类推** | 每个 show/结果类事件都要想一遍「什么情况不该报」，落反向用例 |

**边界（与 R12/第七必检项不冲突）**：隐性规则只在**已锁定的事件/参数**上追加「上报次数 / 取值关系 / 反向条件」维度，**不得**借此引入本需求 ETD 未声明的事件或参数；也不得覆盖 ETD 显式写明的相反口径（ETD 明说某事件可重复上报时以 ETD 为准，并在 Notes 记 `隐性规则被 ETD 覆盖`）。

产物 Notes 里对命中的隐性规则标来源：`- 来源：埋点隐性规则 / <场景>`。

## 四、事故红线覆盖（硬性卡点，不满足不予通过）

权威文档（线上事故提炼，**每次生成强制前置读**）：
[`incident-redlines.md`](https://code.byted.org/livearch/live_tracking_knowledge_base/blob/main/knowledge-guidelines/testing-phase/case-design/incident-redlines.md)
（本地：`knowledge-guidelines/testing-phase/case-design/incident-redlines.md`）。

文档原话：**任何 agent / 人在生成埋点测试用例前，必须逐条核对本清单是否适用；适用却未覆盖，视为用例不合格。**

执行顺序（不可颠倒）：

1. **生成前**：读完整「红线登记表」；对本需求事件/参数/交互做适用判定。
2. **命中则读详情**：打开该 RL 的「红线详情」节，按「必检模式 / 边界场景」设计用例（不要只抄 ID）。
3. **写入矩阵**：命中边界进入「场景 × 事件」候选用例，再落盘。
4. **产物必须附覆盖表**，对登记表中**每一条**红线逐条表态：

```markdown
### 本次命中的事故红线（来自 incident-redlines.md）

| 红线ID | 名称 | 覆盖情况 |
|--------|------|----------|
| RL-00X | ... | ✅ 已覆盖，见用例 X.x / ⚪ 不适用（写明原因）/ ❌ 未覆盖（须补） |
```

- `❌ 未覆盖` 不允许提交；`⚪ 不适用` 必须写理由；`✅` 必须指向具体用例。
- **红线覆盖也只从埋点侧承接（第零节）**：命中 RL-007/RL-009 等含功能回归的红线时，本 skill 只覆盖其埋点侧（该报/不该报、参数），功能是否受损写「另行功能用例保障」，不在埋点断言里校验功能。
- 信息不足以断言（如曝光阈值未定义）→ 预期标"待 RD 确认"，覆盖情况仍记 ✅ + 在测试建议列确认待办；不得因信息缺失判为不适用。
- 落盘后跑：`python tools/check_redline_coverage.py knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`（非 0 = 不合格）。

当前登记（随文档更新，以仓库 main 为准）：RL-001 曝光真实性、RL-002 重复/误报、RL-003 list/参数关系、RL-004 双端、RL-005 异步时序、RL-006 来源串味、RL-007 不破坏功能、RL-008 AB/二跳、RL-009 变更血缘、RL-010 生命周期、RL-011 环境矩阵、RL-012 公参。

## 五、来源绑定与知识盲区（evidence / kb_gap）

对齐 CASE-SCHEMA「严禁无来源结论」：每条关键断言（事件存在性 / 参数枚举）钉到权威源。

- `evidence`：`etd:<wiki_token>#<event>` / `etd:<wiki_token>#<event>.<param>` / `core:<module_en>#<event>.<param>`
- `kb_gap`：`G-NNN: <没能坐实的点，如 anchor_id 必传性 ETD 未列，待 RD 确认>`

在自动化 md 里，来源写进 `**Notes**:`（如 `- 来源：ETD <token> / event / param` 或 `- 来源：user_supplied:G-UI-001`）。

**交互闸门（R9）**：阻塞型盲区（缺 UI routes 段、缺关键枚举、缺提测包/ppe、缺红线文档）不得只写 `TODO-KNOWLEDGE` 然后继续编造终稿。必须写入 `kb_gaps.json` 并打开补齐卡，等用户 `answer` 后再生成。流程与 schema 见 [`kb-gap-interactive.md`](./kb-gap-interactive.md)。Soft 类（如缺 ByteIO）可续跑并登记。

## 六、et_checker_G20 自动埋点校验（"both" 断言的自动化层）

自然语言埋点断言（第一节）是默认表达，人可读、AI 执行器可解读。当拿得到 **ByteIO 用例** 时，再叠加确定性自动校验：

- 走 `ui-xmind-case-specify` → `ui-xmind-case-gen` 路径：spec 第 7 章 seed 第 5 列写 `byteio_case_list`（元素含 `ID`/`Name`/`InvokeNum`/`AppID`/`Region`），`ui-xmind-case-gen` 的 `seed-assemble` 会把 `et_checker_G20 byteio_case_list=[...]` 确定性注入到断言步骤的**预期结果节点**（不是独立操作步骤），render 阶段转成 `${richText:埋点校验}` 占位符。
- **参数来源唯一**：`byteio_case_list` 直取自 ByteIO 用例，LLM 从不复述 ID。

### 缺 ByteIO 用例时的反问模板（不要臆造）

```
**et_checker_G20 缺少必填参数：byteio_case_list**

该用例被识别为埋点需求，但未取到 ByteIO 埋点用例列表。请提供埋点用例（可多条）：
- **ID** - ByteIO 用例 ID
- **Name** - 用例名称
- **AppID** - 应用 ID（默认 1233）
- **Region** - 区域（如 sg）

示例：et_checker_G20 byteio_case_list=[{"ID":"...","Name":"...","InvokeNum":1,"AppID":1233,"Region":"sg"}]
```

拿不到就只保留自然语言埋点断言，并在 Notes 里记 `TODO-KNOWLEDGE: 缺 ByteIO 用例，未叠加 et_checker_G20`。
