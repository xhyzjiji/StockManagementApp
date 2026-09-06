# 本需求 ETD 范围矩阵（R12–R16 操作手册）

> **范围权威**：用户提供的**本需求 ETD 正文**（Sheet 经 R10 去删除线后）。  
> GT / PRD / 产品存量能力 / ETD 正文外链 → **不得自动扩维**。

本文件把 Feedback 表里的 R12–R16 落成可执行卡点。生成用例前必须产出 `etd_scope.json`；写终稿前必须跑 `scripts/check_etd_scope.py`。

## 一、权威阶梯（冲突时从上到下）

| 优先级 | 来源 | 用途 |
|--------|------|------|
| 1 | **本需求 ETD 正文**（去删除线） | 事件 / 入口 / 断言枚举轴 / 参数口径 / click·show 去重策略 |
| 2 | core 权威字典（同名事件交叉校验） | 补强保证、公参；**不得引入正文没有的事件/入口** |
| 3 | 事故红线 | 增量边界；**不得借红线塞进 ETD 未声明入口**（串味叶须有不同期望值） |
| 4 | PRD | 只补触发条件 / 正反向场景；不新增 event/param |
| — | **GT（旧手工用例集）** | **不参与推理**。终稿后才用于对账反思（见五之二），差异只用来反问，不直接进矩阵 |
| 5 | ETD 正文外链 / 附件 | 默认忽略；用户明示「外链并入本需求」才展开 |

## 二、写终稿前必须落盘：`etd_scope.json`

路径：

```text
tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_scope.json
```

最小 schema（字段名固定）：

```json
{
  "etd_url": "https://...",
  "authority": "user_etd_body",
  "events": [
    {
      "event_name": "livesdk_multi_stage_reaction_select",
      "entrances": ["self_spot_panel"],
      "roles": ["anchor", "guest", "moderator"],
      "roles_evidence": "ETD「用户类型」列 = 主播侧/嘉宾侧（R17，禁止默认主播）",
      "change_type": "new_event",
      "change_evidence": "ETD「变更类型」列 = 新增埋点",
      "params": [
        {"key": "action_type", "kind": "enum", "values": ["show", "click"]},
        {"key": "user_type", "kind": "enum", "values": ["anchor", "guest", "moderator"]},
        {"key": "stage_reaction_id", "kind": "opaque"},
        {"key": "stage_reaction_list", "kind": "opaque"}
      ],
      "show_policy": "dedup",
      "click_policy": "per_click"
    },
    {
      "event_name": "livesdk_multi_stage_reaction_show",
      "entrances": ["self_spot_panel"],
      "roles": ["anchor", "guest", "moderator"],
      "params": [
        {
          "key": "stage_reaction_show_ucnt",
          "kind": "semantic",
          "meaning": "能看到该麦位表情的用户数，不含主播",
          "example_expect": "主播1+上麦嘉宾1、无观众 => 1"
        }
      ],
      "show_policy": "per_emit",
      "click_policy": "n/a"
    }
  ],
  "out_of_scope": [
    {"dim": "entrance", "value": "bottom_linkmic", "reason": "本需求 ETD 正文未声明该入口为本次断言触发"}
  ],
  "scenario_axes": [
    {
      "key": "creator_verbal_habit",
      "values": ["no_matching_habit", "has_matching_habit"],
      "source": "prd",
      "affects": ["livesdk_anchor_manager_cues_msg_show"],
      "note": "PRD 触发条件可用于正反向场景，但不得新增 event/param"
    }
  ],
  "conflicts": [
    {
      "kind": "etd_enum_conflict",
      "severity": "blocking",
      "status": "resolved",
      "event_name": "livesdk_anchor_manager_cues_msg_click",
      "param": "action_type",
      "value": "disappear",
      "reason": "PRD/GT/ETD 描述提到自动退场会上报，但 ETD 枚举表缺 disappear；已由用户确认并入"
    }
  ],
  "test_kit": {
    "source_doc": "https://.../提测文档 或 测试说明文档",
    "packages": {"ios": "<bits code 链接>", "android": "<bits code 链接>"},
    "env": "ppe_unified_im",
    "libra_flights": ["72057031", "72058703"],
    "server_config": ["有 CTA button 样式 / 无 CTA button 样式（区分 is_button=0/1）"],
    "accounts": [],
    "missing": [
      {"field": "accounts", "reason": "文档未给命中实验的开播账号，待 RD 补", "gap_id": "G-REL-001"}
    ]
  },
  "outbound_links_ignored": []
}
```

### `test_kit`（R6，P0 —— 测试物料没上 bits 的唯一事实源）

`packages` / `env` / `libra_flights` / `accounts` 四个字段，**要么有值，要么在 `missing[]` 里带 `reason` + `gap_id`**，否则门禁失败。不接受静默留空。

来源文档**认内容不认标题**：`【提测文档】…`、`…测试说明`、`…质量保障`、`…QA 方案` 都要解析。

下游三个消费点，缺一处测试物料就到不了 bits：

| 消费点 | 怎么用 |
|---|---|
| 文件头 `## 测试物料(Test Kit)` | 给人看 |
| **每条用例 `**Precondition**`** | `- mock \| env={env}` + `- mock \| 账号已加实验 libra flight/{id}`；给人看 + 门禁扫（**不会**自动变成工具节点） |
| Step 5 `--precondition-tools-json` | 按选型灌工具：`环境名称`(env) / `libra实验`(flight+group_id；**仅当有 Libra 链接**且缺 group 时分别问实验组/对照组并按 case 分配，见 [`../../references/libra-group-assignment.md`](../../references/libra-group-assignment.md)) / 可选 `ttmock_preset`(region 或 ab_settings JSON 对象) |

### `roles` / `roles_evidence`（R17）

`roles` 取自 ETD 的「用户类型」「上报端」列：主播侧→`anchor`，用户侧/观众侧/看播侧→`viewer`，嘉宾→`guest`。**默认写 `anchor` 是历史故障**（用户侧事件被整批生成成主播侧，设备和校验端全错）。该列为空 → `kb_gap(kind=etd_report_side, severity=blocking)` 反问。

`etd_sheet_load.py --emit-scope-draft` 会直接解析出这一列；`check_etd_scope.py --etd-text` 会反查 scope 与 ETD 是否一致。

### `change_type`（反例形态，必填）

反例写成什么样**完全由它决定**，写错就是「反例不成立」——营收 15917403 那批用例就是全部写成「不上报该埋点」。

| `change_type` | 何时 | 正例 | **反例（唯一正确形态）** |
|---|---|---|---|
| `new_event` | 本需求**新增**埋点 | 命中新场景 → 上报 | 对照组/条件不满足 → **不上报该事件** |
| `param_added` | **已有**埋点，在新场景**新增参数** | 新场景 → 上报且新参有值 | 旧场景 → **仍上报**，但**不带新增参数**（上报时机不变，不许写「不上报该事件」） |

- `param_added` 必须用 `params[].added: true` 标出本需求新增的参数；反例逐个参数覆盖。
- 反例写法（转换器会包成 `data_assertion`）：`` 上报 `livesdk_room_enter` 埋点；不上报 `guide_type` ``。
- `param_added` 事件确实还存在「整事件不上报」的场景（例如新场景本身是新入口）→ 在该事件写 `no_emit_negative: "<理由>"`，否则门禁拦。
- 起草：`etd_sheet_load.py --emit-scope-draft` 读 ETD「变更类型 / 是否新增」列；列缺失或写法认不出时留 `""`，门禁报错逼确认，**不默认 `new_event`**。

### `params[].kind` 判定

| kind | 何时 | 矩阵行为 | Assert |
|------|------|----------|--------|
| `enum` | ETD 给出离散取值表，且要按值验 | **按值拆行** | `key = value` |
| `opaque` | 仅「有值」/无取值表 / id 不验类型 | **不拆行**（按角色抽样） | `key` 有值（可注「不强制类型」） |
| `semantic` | ucnt/cnt/长度/比例等 | **不拆行** | **口径 + 可构造期望**（禁止只写有值） |

### `click_policy` / `show_policy`

| 值 | 含义 |
|----|------|
| `per_click` | 点几次报几次（默认 click） |
| `dedup` | 重复操作不重复上报（常见 show；click 仅 ETD 明文时） |
| `per_emit` | 每次发出各报一次（reaction_show 发出方） |
| `n/a` | 该极性不适用 |

### `expected_combinations`（多枚举轴有效组合）

当一个事件有多个 enum 参数，且取值之间有业务相关性时，必须写 `expected_combinations`。否则门禁只能知道每个单值出现过，无法发现组合错位。

```json
{
  "event_name": "livesdk_anchor_manager_cues_msg_change_position",
  "params": [
    {"key": "position_before", "kind": "enum", "values": ["up", "down"]},
    {"key": "position_after", "kind": "enum", "values": ["up", "down"]},
    {"key": "is_button", "kind": "enum", "values": ["0", "1"]}
  ],
  "expected_combinations": [
    {"position_before": "up", "position_after": "down", "is_button": "1"},
    {"position_before": "down", "position_after": "up", "is_button": "1"},
    {"position_before": "up", "position_after": "down", "is_button": "0"}
  ]
}
```

生成器必须按组合生成；`check_etd_scope.py --cases` 必须按组合反查。禁止只生成 `position_before=down`、`position_after=up`、`is_button=0` 这种单值都出现但组合不对的用例。

### `conflicts`（PRD/GT/ETD 冲突闸门）

PRD/GT/ETD 描述与 ETD 参数表冲突时，不允许静默 out-of-scope。必须写入 `conflicts[]`：

- `severity=blocking`：影响断言或矩阵，例如 GT 有 `action_type=disappear`、PRD/ETD 描述说“自动退场上报”，但枚举表没列。未 resolve 前禁止终稿。
- `status` 允许：`resolved` / `accepted` / `waived` / `ignored` / `out_of_scope`。
- `out_of_scope` 只表示已由用户/规则确认不并入，不是默认处理。

## 三、矩阵展开公式（防笛卡尔积爆炸）

对每个 `event`：

```text
叶子 ⊆ roles × entrances × (enum 轴取值积或 expected_combinations) × {show, click 若 ETD 有} × PRD scenario_axes（只影响触发条件，不新增 event/param）
```

- **禁止**把 `opaque` / `semantic` 参数的「业务表现型」（如具体 emoji 名）乘进叶子。
- **禁止**把 `out_of_scope` 或 GT 多出的 entrance 乘进叶子。
- **禁止**把 `conflicts` 里的 blocking 项静默丢弃；必须 resolve 后再生成。
- 关键 show/click：按 `show_policy` / `click_policy` 加重复操作叶（R14），不要一刀切。

## 四、入口绑定（R16）速查

若 Assert 含下列键，Path/Steps **必须**使用 ETD 定义会产生该取值的入口：

| 参数 | 例 | Path 必须 |
|------|-----|-----------|
| `link_page_entrance` | `interact_panel` | 自己麦位 → manage（非底部连麦旁路） |
| `from_page` | `interact_panel` | 从互动面板点出的控件 |
| `way_of_switch` | `interact_panel` | 同上 |
| `action_page` | `interact_panel` | 同上 |

旁路入口仅当 ETD 列为另一触发，或串味对照（期望值 ≠ 上表）时单独成条。

## 五、历史事故 → 反模式（生成时对照）

来自 MG Stage Reactions 评审反馈，违反任一条 = 本轮不合格：

| # | 反模式 | 对应规则 | 正解 |
|---|--------|----------|------|
| A1 | 因 GT/外链补了「底部连麦入口」整组 case | R12 | ETD 正文未声明 → out_of_scope，不写 |
| A2 | 每个 emoji 一条 click/show | R13 | `stage_reaction_id` 为 opaque → 按角色各 1 条 |
| A3 | 标题写「不去重失败」，Assert 却按曝光去重 | R14 | click：N 次点击 → N 条上报 |
| A4 | `stage_reaction_show_ucnt` 只写「有值」 | R15 | 写口径（不含主播）+ 可构造期望 |
| A5 | 管理面板相关 case 用底部入口打开，却断言 `link_page_entrance=interact_panel` | R16 | Path 改为自己麦位 → manage |
| A6 | 展开 ETD 正文贴链的另一份埋点文档事件 | R5/R12 | 外链默认忽略；要验先问用户 |
| A7 | ETD 声明了 `change_position` 事件，产物里一条都没有 | R5 | scope 列全事件 + 覆盖度门禁（五之二） |
| A8 | `is_button` 有 0/1 两值，只写了 `=1` 的用例 | R13/R8 | enum 轴每值必须落叶子，门禁按 `(event, key, value)` 反查 |
| A9 | 只有正向上报，没有「拖动未生效不上报 / 拖动中不重复 show」 | 隐性规则 3.4 | 每事件至少 1 条反向用例，或写 `negatives_waiver` |
| A10 | GT 有 `disappear`，ETD 描述也暗示自动退场，但枚举表缺失时直接 out-of-scope | R12/冲突闸门 | 写 `conflicts[kind=etd_enum_conflict,severity=blocking]`，反问确认是否并入 |
| A11 | `position_before`/`position_after`/`is_button` 单值都出现，但有效组合错位 | R13/expected_combinations | scope 写有效组合，门禁逐组合反查 |
| A12 | PRD 的“触发条件1/条件2”完全没进用例 | R8/scenario_axes | PRD 触发条件进入 scenario_axes，生成正/反向 show 场景 |
| A14 | **已有埋点新增参数**，反例却写成「不上报该埋点」（营收 15917403 整批如此）——新场景只影响参数，不改上报时机，这种反例根本不成立 | `change_type` | scope 写 `change_type=param_added` + `params[].added`，反例改成「旧场景仍上报，但 `不上报 <新参>`」；门禁 `反例形态错` |
| A13 | 埋点合并校验：第 2 步验 show、第 3 步验 click，或**同一个操作步骤下挂多个埋点断言**（`action_type=manage` + `panel_show`），时机没拆，用例无法直接执行 | R18/G11 | 一条用例一个时机 =（一个事件 + 一个 `action_type`）：拆成曝光一条、点击一条，非目标事件的步骤只导航不断言。基线+增量（去重/频控/生命周期）在 Notes 写 `- 多时机例外: <理由>` |

## 五之二、覆盖度门禁（防漏，与"防多写"同等硬）

> **来由**：同一需求换 agent（TRAE/gpt5.5 vs Cursor）重跑，少了 `click is_button=0`、整个 `change_position` 事件、以及拖动未生效/拖动中不重复 show 等反向用例。这些"该生成什么"的要求原本**只写在散文 checklist 里**，靠模型自觉；换个指令遵循弱一点的模型就静默漏掉。
>
> **规则**：**可枚举的覆盖要求一律落成 `etd_scope.json` 里的机器可判期望集合，不能只当 checklist 条目。** `check_etd_scope.py --cases` 会用 scope 反查产物，缺一即非 0 退出。

脚本从 scope 计算期望集合、从产物解析实际集合，做三个方向的 diff：

| 检查 | 判据 | 报错前缀 |
|---|---|---|
| 事件全集（R5） | scope 每个 `event_name` 至少有 1 条**正向上报**用例 | `R5 漏事件` |
| 枚举叶子（R13/R8） | 每个 `kind=enum` 参数的**每个 value**，都要在断言该事件的用例里出现过 `` `key` = `value` `` | `R13 漏枚举叶子` |
| 有效组合（R13/R8） | scope 每个 `expected_combinations[]` 对象必须在同一条正向用例中整体出现 | `组合矩阵 漏组合` |
| 反向用例（隐性规则） | `change_type=new_event`：至少 1 条 `不上报 <event>` 用例 | `隐性规则 漏反向用例` |
| **反例形态（`change_type`）** | `change_type=param_added`：每个 `added` 参数都要有「仍上报 + `不上报 <param>`」用例；且**不得**出现 `不上报 <event>`（除非写 `no_emit_negative`） | `反例形态错` |
| **测试物料下沉（R6）** | `test_kit.env` 与至少一个 `test_kit.libra_flights[]` 必须出现在**每一条**用例的 `**Precondition**` 里 | `测试物料未落到用例` |

**豁免必须显式写进 scope**（不写理由就等于不合格）：

- 某 enum 取值确实不适用 → 该参数加 `"coverage_waiver": "<理由>"`
- 某事件确无反向场景 → 该事件加 `"negatives_waiver": "<理由>"`
- `param_added` 事件确有「整事件不上报」的反例 → 该事件加 `"no_emit_negative": "<理由>"`

产物解析约定（写用例时必须满足，否则门禁读不到）：用例间单行 `---` 分隔、每条以 `> 标题` 开头且含 `**Steps**`、断言里事件名与参数值一律反引号包裹、反向断言用「不上报」字样。

### 谁来查「scope 自己抽漏了」

覆盖度门禁只能查「scope 有、用例没有」。**scope 本身漏了事件,它一无所知**——所以要有独立第二源反查:

| 第二源 | 参数 | 何时有 | 判据 |
|---|---|---|---|
| **ETD 原文**(主路径,测新/回归都有) | `--etd-text` | **每次都有**。Sheet 走 `etd_sheet_load.py` 输出的 JSON(取去删除线后的 `tsv`);Docx/md 直接给正文文件 | 见下面三层 |
| GT 手工用例集(**终稿后反思用**,不进推理) | `--gt-seeds` | **只有回归/改版才有**(之前有人写过 BITS 用例)。测新没有,跳过 | GT 里的事件/枚举若不在 scope 里 → 反问用户,确认后回头改 scope 重跑 |

`--etd-text` 反查三层，对应三种不同的静默失效：

| 层 | 查什么 | 挡住的失效 |
|---|---|---|
| 事件名（正则 `livesdk_*`） | ETD 原文出现的事件必须都在 `scope.events` | 整个事件被漏掉 |
| **枚举取值 / 必传参**（按列头解析「param取值」「是否必传」列） | ETD 列出的每个离散取值、每个必传参都要在 scope 对应事件里 | **事件抽对了但枚举只抽一半** —— 事件名反查完全看不出来，是漏 case 的主要形态 |
| **上报端**（「用户类型」「上报端」列） | ETD 的角色必须包含在 `scope.events[].roles` | 用户侧事件被默认成主播侧 |

后两层依赖列头识别。认不出时打印 `WARN: ETD 表头未识别…已跳过` 并**只保留第一层** —— 看到这行 WARN 必须人工逐列核对，**WARN ≠ 通过**。

豁免路径：确实不验的事件写进 `out_of_scope`(`dim=event`,`value` 支持 `前缀*` 通配)；不验的枚举取值写 `conflicts`/`out_of_scope`(`event_name`+`param`+`value`)或给该参数加 `coverage_waiver`；不验的必传参写 `out_of_scope`(`dim=param`,`event_name`,`value=<参数名>`)。
**抽不到任何事件名时直接失败**,不会因为文件给错而静默通过。

## 六、门禁命令

**日常只需要这一条**（交付判据，自动发现路径、跑完全部检查、失败时打印下一步）：

```bash
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/run_gates.py \
  --workdir tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen
```

下面是它内部调用的分步命令，**只在单项调试时**直接用：

```bash
# 0) Sheet 形态 ETD：先解析出 scope 草稿，别肉眼读宽表（全量事件/上报端/必传参/枚举取值）
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/etd_sheet_load.py \
  --url '<etd_sheet_url>' --emit-scope-draft \
  > tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_scope.draft.json
# 退出码 3 = 列头认不出 → 回退人工抽取，但下面的 --etd-text 照跑

# 1) 校验 scope 文件（含 test_kit 完整性）
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/check_etd_scope.py \
  --scope tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_scope.json

# 2) 对照 scope 扫描 source_cases（终稿前）+ ETD 原文反查 scope 有没有抽漏（每次必带）
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/check_etd_scope.py \
  --scope tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_scope.json \
  --cases tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/{ui_path}_source_cases.md \
  --etd-text tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/etd_raw.json

# 3) 仅回归/改版且拿得到旧手工用例集时，再叠加 GT 反查（测新没有 GT，跳过）
#   --gt-seeds <extract_bits_case.py 的 seeds JSON> [--gt-diff-output …] [--gt-diff-only]

# 自检
python skills/tt-nova-ui/ui-md-event2case-gen/scripts/check_etd_scope.py --self-check
```

非 0 退出 → 不得交付终稿。

## 七、与 R8 / R9 的关系

- **R8「铺满」** = 铺满 `etd_scope.json` 内的维，不是铺满 GT。
- **R9**：ETD 正文含外链且用户可能想并入、或语义参口径在 ETD 写不清 → `kb_gaps.json`（`kind=etd_outbound_link` / `etd_semantic`），硬停反问，禁止猜。
