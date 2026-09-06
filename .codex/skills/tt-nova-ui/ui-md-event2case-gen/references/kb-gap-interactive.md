# 知识盲区交互卡（TODO-KNOWLEDGE Gate）

本 skill **不追求一次生成完美**，但**标准必须守住**：缺权威知识时**禁止臆造**，必须停住让用户补齐后再继续写用例。

## 原则

1. **发现盲区 ≠ 写进最终 Path/Assert 冒充已知**。旧做法「产物里标 `TODO-KNOWLEDGE` 却继续编完整路径」= 不合格。
2. **阻塞型盲区 → 硬停**：未收到用户补齐前，不得进入「写自动化 md / 转 xmind / 上传」。
3. **可移植核心**：落盘 `kb_gaps.json` + 对话停住反问（用户按 `G-xxx | answer` 回复或直接改 JSON）。**这是所有 agent 都必须能走的路径。**
4. **宿主增强可选**：Cursor 的 `AskQuestion` / Canvas 只是更好的 UI，**不是硬依赖**；没有这些工具时不得报错中止，应降级到第 3 条。

## 跨 agent / 跨 IDE 说明

| 能力 | 是否 Cursor 独有 | 其它 agent（Claude Code / Codex / 通用 Agent Skills 等） |
|---|---|---|
| `kb_gaps.json` 落盘 + blocking 硬停 | 否（文件约定） | **必须遵守**，这是 R9 的真实标准 |
| 对话短反问 / 用户改 JSON | 否 | **默认通道** |
| `AskQuestion` 选择框 | **是**（Cursor 宿主工具） | 没有 → 用编号选项散文或请用户自由回复，**不要调用不存在的工具** |
| Cursor Canvas 补齐卡 | **是** | 跳过；不要创建 `.canvas.tsx` |
| 读 KB / 写用例 md / 上传脚本 | 否 | 同 skill；依赖本机 git/python/网络与权限 |

结论：在其它 agent 执行 **不会因为缺 AskQuestion/Canvas 而逻辑失败**；只会少一层选择框 UI。若某 agent 把「必须 AskQuestion」理解成硬调用，会踩坑——故下文写明 **探测到工具再用不强求**。

## 盲区分类

| severity | 含义 | 未补齐时 |
|---|---|---|
| `blocking` | 写不出合规 Path / 断言会臆造 | **硬停**，反问等用户 |
| `soft` | 可先生成但须显式登记；或用户书面同意跳过 | 可续跑，Notes/`kb_gap` 保留，交付时列出 |

常见 `kind`（`backfill` 列 = 用户答案是否值得回填知识库，见下节）：

| kind | 何时 blocking | backfill? | 回填目标（**只追加到本轮参考过的现有文件，禁止新建文件**） |
|---|---|---|---|
| `ui_route` | `business-ui_routes` 无对应导航（如多人上麦、麦位面板、底部连麦入口） | ✅ 可复用 | 追加到本轮已读的那份 `knowledge-business/business-ui_routes/<area>/…md`（gap 的 `context.matched_routes_file`），在其**既有**「UI路径」章节下补小节 |
| `etd_param` / `etd_enum` | 本需求 ETD 未给清参数/枚举，却要写 Assert | ✅ 可复用（限本需求 ETD 澄清，非串其它 ETD） | 追加到本轮已读的现有 `etd-designs/` 条目 或 `event-dictionary/core/<module_en>.md` 的**同名事件**行；机读 `mappings/_generated` 由 build 脚本回填 |
| `etd_enum_conflict` | ETD 描述 / PRD / GT 提到某枚举会触发埋点，但 ETD 参数取值表缺该枚举；影响断言时 **blocking** | ✅ 可复用（用户确认后补本需求口径） | 追加到本轮已读的现有 `etd-designs/` 条目 或 `core/<module_en>.md` 同名事件（补枚举口径） |
| `prd_trigger_scope` | PRD 给出触发条件/正反向展示条件，但 ETD 只给事件参数；不影响 event/param 时 **non-blocking**，但必须进入 `scenario_axes` | ⚠️ 可复用（若是通用触发路径/条件口径） | 可追加到本轮已读 UI routes 或 ETD 口径说明；一次性实验条件不回填 |
| `etd_outbound_link` | ETD 正文贴链另一埋点文档，且矩阵可能依赖其事件/入口 → **先问是否并入本需求**；未确认前禁止展开（R12） | ⚠️ 仅当用户明示并入本需求后按 `etd_enum` 处理 | 同上 |
| `etd_report_side` | ETD 的「用户类型 / 上报端」列为空或写不清，定不了该事件由主播侧还是用户侧上报（R17）→ **blocking**，**禁止默认主播侧** | ✅ 可复用 | 追加到本轮已读的现有 `etd-designs/` 条目 或 `core/<module_en>.md` 同名事件（补上报端） |
| `etd_semantic` | 语义参（ucnt/cnt 等）在 ETD 无口径说明，无法写可构造期望（R15） | ✅ 可复用（口径描述） | 追加到本轮已读的现有 `etd-designs/` 条目 或 `event-dictionary/core/<module_en>.md` 同名事件（补口径） |
| `gt_extra_dimension` | GT 多出入口/表情类型而本需求 ETD 正文没有 → **soft**（写入 `etd_scope.out_of_scope`，默认不进矩阵） | ❌ | 不回填（out-of-scope） |
| `release_kit` | 提测缺包 / ppe / flight | ❌ 一次性 | 不回填（随版本失效，只留 `kb_gaps.json`/Test Kit） |
| `gt_etd_conflict` | GT 与 ETD 词表冲突且影响断言（如 GT 有 `action_type=disappear`、ETD 枚举缺失）；**blocking，必须问用户确认并写 `conflicts[]`** | ❌（除非用户明确说补本需求 ETD，此时转 `etd_enum_conflict`） | 不回填（决策记 Notes） |
| `byteio` | 缺 ByteIO → **soft**（可只保留自然语言断言） | ❌ 一次性 | 不回填 |
| `redline_doc` | 拿不到 `incident-redlines.md` → **blocking**（禁止裸生成） | ❌ | 不回填（是取文档问题） |

## 回填知识库（gap 答案沉淀，避免下次重复反问）

用户对反问的回答里，**可复用的权威知识**（UI 导航路径、本需求 ETD 的枚举/参数口径）应回填 `live_tracking_knowledge_base`，让下一次生成直接命中、不再反问；**一次性/版本相关**答案（提测包、ppe、flight、byteio id）**不回填**。

规则（硬约束）：

1. **只回填 `backfill=✅` 的 kind**（见上表）；`release_kit` / `byteio` / `gt_*` / `redline_doc` 一律不回填。
2. **只追加、不新建文件**：回填一律**追加到本轮生成时已参考、且已存在的那份 KB 文件**（`ui_route` = `context.matched_routes_file`；`etd_*` = 本轮读过的现有 `etd-designs/` 条目或 `core/<module_en>.md`）。**禁止新建任何 KB 文件 / 新目录 / 新 etd-designs 条目**。若找不到可追加的现有文件 → `backfill.status=skipped`，在交付说明里提示用户手动补，**不要**自建文件顶替。
3. **不破坏范围权威（R12）**：`etd_enum`/`etd_param`/`etd_semantic` 只回填**本需求 ETD 的澄清**（用户确认的本需求取值/口径）；**禁止**把它写进别的需求 ETD、也**禁止**据此改写 `core/` 里其它需求的既有枚举（除非用户明示补的是通用字典缺口）。
4. **人确认后再写**：KB 是全员共享权威。回填前把「拟追加到哪个现有文件 + 拟追加内容」列给用户，**用户确认**（或答案本身已足够明确即视为同意）后再写盘。禁止把没核实的猜测当权威沉淀。
5. **带 provenance**：每条回填追加一行来源标注，便于追溯与后续校正，例如：
   `> 来源：<PRD/ETD 链接或 token> · user_supplied:<gap_id> · <date> · by ui-md-event2case-gen`
6. **幂等**：目标文件已有同名小节/同一取值 → **patch 更新**，不重复追加；`business-ui_routes` 追加时对齐既有「UI路径 / UI信息」写法。
7. **分支统一 `tt_nova`**：回填与用例回写走同一分支/同一 MR；写盘后同样跑 `cd <KB> && python tools/build_mapping.py` 重建映射，再提交/提 MR。
8. **回填 ≠ 解阻塞前置**：blocking 仍以 `kb_gaps.json` 的非空 `answer` 为准放行；回填是 resolve **之后**的沉淀动作，失败（如无写权限）不阻塞本轮交付，但要在交付说明里提示「答案未沉淀，请手动补 KB」。

`ui_route` 回填样例（**追加到已存在的** `business-ui_routes/<area>/…md`，接在其既有 AI 向导等章节之后）：

```markdown
### N、<功能名>入口

**UI路径**：在直播间内，<用户补的完整导航链，控件名用人话>

**UI信息**：
- 【<控件>】：<外观/位置描述（若用户给了）>

> 来源：<ETD/PRD 链接> · user_supplied:G-UI-002 · 2026-07-21 · by ui-md-event2case-gen
```

## 落盘契约

路径（每次生成必写，可复查）：

```text
tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/kb_gaps.json
```

最小 schema：

```json
{
  "feature": "mg-stage-reactions",
  "status": "awaiting_user",
  "created_at": "2026-07-16T10:00:00+08:00",
  "gaps": [
    {
      "id": "G-UI-001",
      "kind": "ui_route",
      "severity": "blocking",
      "title": "嘉宾进入多人房并上麦",
      "needed_for": ["Path", "Steps 导航前缀"],
      "asked": "请给出从 TikTok 主页起的可执行导航链（控件名用人话）",
      "context": {
        "matched_routes_file": "user_product/基础业务- UI_Routes.md",
        "matched_sections": ["开播相关路径"],
        "missing": ["连麦", "上麦", "麦位", "底部连麦入口"]
      },
      "hint_partial": "主播开播前缀可对齐：【+】→【直播】→ Go Live（已有 routes）",
      "answer": null,
      "backfill": {
        "reusable": true,
        "target": "knowledge-business/business-ui_routes/multi_guest/社交业务- UI_Routes.md",
        "status": "pending"
      }
    }
  ]
}
```

用户补齐后：`answer` 填字符串（Path 链 / 枚举表 / env 等），`status` → `resolved`（全部 blocking 都有非空 `answer`）或 `partial`。

`backfill` 字段（可选，标记该答案是否沉淀 KB，见「回填知识库」节）：`reusable`（true=可复用值得回填；一次性答案填 false 或省略）、`target`（拟写入的 KB 相对路径）、`status`（`pending`→未写、`written`→已回填、`skipped`→用户不回填/不可复用）。

## Agent 动作（硬卡点 Step 1.7）

在写用例矩阵定稿之前：

1. 扫 `business-ui_routes`（目录名 → 文件名 → 文件内章节关键词）。
2. 对矩阵里每条需要的导航段做「命中 / 未命中」；未命中 → 追加 `gaps[]`。
3. 若存在任一 `severity=blocking` 且 `answer` 为空：
   - 写/更新 `kb_gaps.json`（`status=awaiting_user`）
   - 按「交互通道」问用户（**无 Cursor 工具 → 短反问**，禁止强调不存在的工具）
   - **停止生成用例**（事件锁定表 / 红线表 / 矩阵草稿可留）
4. 用户提交后：答案写回 `kb_gaps.json`，Path/步骤 evidence=`user_supplied:<gap_id>`，再继续 Step 3+。
5. **回填 KB（gap resolve 后）**：对 `backfill.reusable=true` 的 gap，按「回填知识库」节把答案沉淀到对应 KB 文件（`tt_nova` 分支，人确认后写，带 provenance），写完 `backfill.status=written`；不可复用/用户不回填 → `skipped`。
6. **禁止**：用 PRD/GT「猜」完整 Path 写进终稿却不标 gap、不反问。

## 交互通道（优先级）

通道按**宿主实际能力**选 **一种**（不要叠开；**不要调用不存在的工具**）：

| 优先级 | 通道 | 适用 |
|---|---|---|
| **1** | **对话短反问 / 改 `kb_gaps.json`** | **全 agent 默认基线**；自由 Path 文本 |
| **2** | **`AskQuestion`**（仅 Cursor 且工具已暴露） | 有固定候选时选模板 +「其它（我自己打）」 |
| **3** | **Cursor Canvas**（仅 Cursor 且用户要） | 同屏填多条长 Path；默认不开 |

### 通用短反问（所有 agent）

```
【R9 硬停】缺 UI 导航知识，已写入 kb_gaps.json。请补齐后再继续：

G-UI-001（嘉宾进房上麦）: <完整导航链，或直接改 JSON 的 gaps[].answer>
G-UI-002 ...
```

用户也可改完 JSON 后说「已填，继续」。

### `AskQuestion`（仅 Cursor）

仅当会话**确实有**该工具时用；没有则跳过。每条消息最多一个问题；Path 先给候选 +「其它」，选其它后再收自由文本。

### Canvas（仅 Cursor，可选）

仅用户明确要卡片时用。落点 `~/.cursor/projects/<workspace>/canvases/{ui_path}-kb-gaps.canvas.tsx`。非 Cursor 禁止创建 canvas。

## 自检

- [ ] 最终用例 Path 每一段要么来自 `business-ui_routes`，要么来自已 resolve 的 `user_supplied:G-xxx`
- [ ] 无「知识盲区写了缺 routes 却 Path 已完整编造且从未反问」的矛盾
- [ ] blocking 未齐时不应交付宣称完成的 `*_cases.md` 终稿
- [ ] 非 Cursor 环境未强调 AskQuestion/Canvas
- [ ] `backfill.reusable=true` 的 gap 已回填 KB（`status=written`）或已征得用户同意跳过（`skipped`）；`release_kit`/`byteio`/`gt_*` 未被误回填
- [ ] 回填内容落到**本需求自己的** etd-designs / 对应 area 的 routes，带 provenance；未改写其它需求 ETD/既有枚举（除非用户明示补通用字典）
