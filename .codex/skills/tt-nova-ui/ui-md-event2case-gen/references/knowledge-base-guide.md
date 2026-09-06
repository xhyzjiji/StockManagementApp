# live_tracking_knowledge_base 使用指引

埋点领域权威知识（事件字典 / ETD 一手设计 / 事故红线 / 入口命名 / 用例规范）集中在
[`live_tracking_knowledge_base`](https://code.byted.org/livearch/live_tracking_knowledge_base)。
本 skill 的事件名、参数、枚举值**只能取自这里或用户给的 ETD**，严禁臆造（知识库铁律 1/2）。

## 拉取到本地缓存

```bash
KB=/tmp/live_tracking_knowledge_base
if [ -d "$KB/.git" ]; then git -C "$KB" pull --ff-only; \
else git clone --depth 1 https://code.byted.org/livearch/live_tracking_knowledge_base.git "$KB"; fi
```

拉取后先读仓库根 `INDEX.md`（意图路由）与 `CLAUDE.md`（行为铁律）。

## 路由（生成埋点用例时至少读这些）

| 需要什么 | 文档路径（仓库根为基准，写全路径） |
|---|---|
| 本需求改了哪些埋点（**需求级一手设计**：事件/触发/枚举） | `knowledge-business/event-dictionary/etd-designs/INDEX.md`；增量事件 `etd-designs/new-events.md`；机读 `mappings/_generated/etd.json`。**只允许用与用户 ETD 同 token/同标题的条目交叉校验，禁止用「相近」ETD 替换。** |
| 事件/参数/枚举/必传/强保证/上报时机（**权威字典**） | `knowledge-business/event-dictionary/core/<module_en>.md`；入口 `core/INDEX.md` |
| **UI 导航路径（写 `**Path**` / 开播进房步骤必读）** | `knowledge-business/business-ui_routes/`（例：`user_product/基础业务- UI_Routes.md`：主页→开播、主播中心、设置页、提词器）。Path 必须从 App 主页起，对齐这里的「UI路径」。 |
| 事故红线（**每次生成强制前置读，适用即必检**） | `knowledge-guidelines/testing-phase/case-design/incident-redlines.md`（[main 在线版](https://code.byted.org/livearch/live_tracking_knowledge_base/blob/main/knowledge-guidelines/testing-phase/case-design/incident-redlines.md)）。生成前读登记表；命中则读详情；产物附覆盖表；`tools/check_redline_coverage.py` 门禁。 |
| **埋点隐性规则（每个埋点文档都要套，强制前置读）** | `knowledge-quality/test-automation/埋点隐性规则 - Sheet1.csv`。ETD 不写但默认成立的通用规则：点击只报一次、page 曝光不多报（组件曝光可多报）、结果类按成功/失败态（失败 ≤1 次）、id 类参数互不相等、反向用例设计。用法见 [`tracking-assertion-contract.md`](./tracking-assertion-contract.md) 3.4。 |
| **业务线简介（链接知识库 / 定 `biz_line` 前先读）** | `knowledge-quality/test-automation/TT直播横向业务简介 - Sheet1.csv`（列：`业务英文 | 业务名称 | 简介 | 关键词`）。`业务英文` = `biz_line` 合法取值全集；用需求关键词匹配 `关键词`/`简介` 来推荐 `biz_line`（**仍须用户确认**）并决定去哪个业务目录找 ETD / UI routes。 |
| 用例结构规范（4 层链式 + 必检项 + 交付卡点） | `knowledge-guidelines/testing-phase/case-design/case-design-config.md` |
| 机读用例约定（sidecar cases.yaml / evidence / kb_gap） | `knowledge-quality/test-cases/CASE-SCHEMA.md` |
| `enter_from_merge` / `enter_method` / `action_type` 取值 | `knowledge-business/event-dictionary/entry-source-naming.md` |
| 某参数被哪些事件用 / 参数反查影响面 | `knowledge-business/mappings/core-event-param-graph.md` |
| 某场景要验哪些埋点 / 触发路径 | `knowledge-business/mappings/core-scene-event-mapping.md` |

## 模块英文名（core/<module_en>）关键词映射（节选，全量见 core/INDEX.md）

| 关键词 | module_en |
|---|---|
| 开播 / 主播上播 / 实时主播中心 | `live_user_creator` |
| 看播流量 / 进房 / 流量 | `live_user_traffic` |
| 互动 / 点赞 / 评论 | `live_user_interact` |
| 工具 / 分享 / 截图 | `live_user_tool` |
| 送礼 / 礼物 | `live_revenue_gift_process`（及 `live_revenue_gift_*`） |
| 连麦 / cohost | `live_revenue_cohost` |
| PK / 对战 | `live_revenue_match` |
| SMB / 机构 / 公会 | `live_user_smb` |

## 用例回写（自动化 md 存 git，不走 TOS）

本 skill 产出的自动化 md 用例**存进本仓库**（`live_tracking_knowledge_base`），作为 xmind 用例备注引用的 git 源；这也对上知识库的用例沉淀闭环（CASE-SCHEMA / case-design-config 卡点 5）：

**业务线目录（硬约束）**：路径必须是 `knowledge-business/ui-test/{biz_line}/…`。`biz_line` 只能是用户指定的  
`SMB` / `activity_platform` / `game` / `multi_guest` / `revenue` / `user_product` / `wallet`。  
未指定 → **反问用户选一项**（见 SKILL「业务线反问模板」），禁止默认、禁止写到 `ui-test/` 根下。

**分支（硬约束）**：统一使用分支名 **`tt_nova`** 提交并提 MR（`<ref>` 优先写 `tt_nova`）。

1. 写用例：`<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`；推荐并排 sidecar 同目录 `{ui_path}_cases.cases.yaml`（schema 见 `knowledge-quality/test-cases/CASE-SCHEMA.md`）。
2. 红线门禁：`cd <KB> && python tools/check_redline_coverage.py knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`（非 0 退出即不合格）。
3. **本需求范围门禁（R12–R16）**：先有 `etd_scope.json`，再写用例；终稿前  
   `python skills/tt-nova-ui/ui-md-event2case-gen/scripts/check_etd_scope.py --scope …/etd_scope.json --cases …/{ui_path}_source_cases.md`（非 0 不合格）。详见 [`etd-scope-matrix.md`](./etd-scope-matrix.md)。
4. 重建映射图：`cd <KB> && python tools/build_mapping.py`（回填 `mappings/scene-event-mapping.md` / `event-param-graph.md` / `_generated/graph.json`）。
5. checkout/创建分支 `tt_nova` → commit → push → 提 MR 到 `live_tracking_knowledge_base`。`source_url` 的 `<ref>` 用 `tt_nova`（合入后可回填 commit sha）。

## 盲区回填（gap 答案沉淀到 KB）

用户对 R9 反问的**可复用**回答，应随用例回写一并沉淀到 KB（同 `tt_nova` 分支/同 MR），下次生成直接命中不再反问。**只追加到本轮参考过的现有文件，禁止新建任何 KB 文件/目录/条目**：

- `ui_route` → **追加到本轮读过的那份** `knowledge-business/business-ui_routes/<area>/…md`（对齐既有「UI路径 / UI信息」写法）
- `etd_enum` / `etd_param` / `etd_semantic` → **追加到本轮读过的现有** `event-dictionary/etd-designs/<条目>` 或 `core/<module_en>.md` 同名事件（补口径），机读由 `build_mapping.py` 回填
- **不回填**：`release_kit`（包/ppe/flight）、`byteio`、`gt_*`（一次性 / out-of-scope）
- 找不到可追加的现有文件 → 标 `skipped` 并提示用户手动补，**不要自建文件**

约束：人确认后写、带 provenance（来源链接 + `user_supplied:<gap_id>` + 日期）、幂等 patch、不改写其它需求 ETD/既有枚举（除非用户明示补通用字典）。完整规则见 [`kb-gap-interactive.md`](./kb-gap-interactive.md)「回填知识库」。

> 也可直接复用知识库自带的端到端编排 `skills/tracking-case-generator/SKILL.md`（生成→门禁→重建映射→导出 BITS→提 MR）。

## 铁律（务必遵守）

1. 严禁编造 event_name / 参数枚举值 / UI 控件路径 / ppe·flight id；查不到 → **R9**：`kb_gaps.json` + 补齐卡，blocking 未齐不写终稿。
2. 优先级：本需求事件清单以**用户提供的埋点设计文档**为准；知识库同名 `etd-designs/` 仅交叉校验；`core/` 补必传/强保证；**禁止用标题相近的其它 ETD 顶替**（防串事件/串参数方案）。
3. 所有断言注明来源（evidence，见 tracking-assertion-contract.md 第五节）。
4. 生成用例必须逐条核对事故红线并附覆盖表；**拿不到 `incident-redlines.md` 或 `埋点隐性规则 - Sheet1.csv` 禁止裸生成**。埋点隐性规则逐条判定适用性，适用即落用例。
5. `**Path**` 必须从 App 主页起；段来源 = `business-ui_routes/` 命中或用户补齐的 `user_supplied:G-xxx`；禁止模块标签路径，禁止 routes 未命中时猜完整链。

## 无法访问时的降级

网络/权限导致仓库拉取失败时：仅用用户提供的 ETD 正文作为事件/参数来源；坐实不了的事件、枚举一律标 `TODO-KNOWLEDGE`，**不要臆造**，并在交付说明里提示用户补充知识库访问权限。
