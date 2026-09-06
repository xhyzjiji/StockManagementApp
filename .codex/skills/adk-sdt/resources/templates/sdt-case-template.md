<!--
【语言适配规则 — 必须在生成 case.md 时执行】
当 `preferred_language` 为 `en` 时，必须将本模板中所有中文标题、说明文字翻译为英文后再写入 case.md。
占位符（{{...}}）、字段关键字（Priority/Platform/Pkg/Path/Precondition/Steps/Assert）、标签关键字（mock/assume/page/route）、
Assert category 关键字（text/state/visual/tracker/network）、段落标题「用例表（执行索引）」及其表头
（用例ID/优先级/角色/前置条件/执行步骤/预期结果）保持英文/原文不变——它们是解析契约。仅翻译自然语言描述，不改变模板结构。
当 `preferred_language` 为 `zh` 时，保持中文原文不变。

【本模板用途】
1. `adk-sdt-ff` 调用 `TEXT_CASE_GENERATE`（默认 ui-md-case-gen，缺失时自生成兜底）生成 `test/case.md` 时的格式契约。
2. `adk-sdt-clarify` 校验用例字段是否完整、规范的依据。
3. `adk-sdt-implement` 将本文件**原样**作为平台验证工作流（双端同名 `harness-workflow`，两套独立实现）的 `--spec` 输入：
   五段式用例区块供 Agent authoring 阶段理解语义；文末「用例表（执行索引）」供框架的确定性表格解析
   （verify-loop `cases:parse` 按表头 `用例ID/执行步骤/预期结果` 提取）。两者必须由 ff/clarify 保持同步。

【产物边界 — 生成的 case.md 只含用例本身】
生成的 case.md 只包含下方「产物骨架」：标题 + 两行引言 + `## TC-XXX` 区块 + 「用例表（执行索引）」。
- 本注释块（含下方的编写原则、字段说明）是给**生成者与澄清者**的规范，**不写入产物**。
- **执行参数不写入 case.md**（无 Harness Config 段）：run_mode / execution_mode / build_mode / concurrency /
  max_fix_rounds 等只存在于 `test/task.md` 的 Input 表——那是唯一事实源，`adk-sdt-implement` T002 只读那里；
  写两处必然漂移。历史产物里遗留的 `## Harness Config` 段直接忽略（以 task.md 为准），澄清改到该文件时顺手删除。

【编写原则（生成与澄清都必须遵守）】
1. **Goal 写验证意图**：用例标题（引用块 `>`）说清楚"验证什么"，而不是"做什么操作"。
2. **mock 要具体**：写明 AB 实验名和值（如 `mock | ab experiment_name=1`），不要写"开启某实验"；地区、登录态、网络等同理。
3. **page chain 写法**：`起点 → 中间页 → 目标页`，并为每个需要导航的 waypoint 配 `route | <页面>: <到达方式>` 提示。
4. **一个 Step 一个操作**：不要在一个步骤里塞多个动作；多动作拆成多个 Step。**"等待/观察/确认"是断言不是动作**，
   写成该步骤下的 `Assert:` 行，不得单独成 Step。
5. **Assert 选对 category**：能用 `text`/`state` 就不用 `visual`；能用 `tracker`/`network` 客观验证的不要用 `text` 猜。
6. **`visual` 不得作为唯一验收断言（硬规则）**：执行侧的 `assert.visual` 目前接的是 MockJudge —— **恒返回
   PASS**。一条用例若只有 `visual` 断言，会产出与真通过完全无法区分的假绿。实测教训：某次 29 条断言全是
   `visual`（颜色只能看图），若照译就是 12/12 全绿且毫无意义。颜色/外观类判据的正确写法是**把判据并入
   `intent` 的定位描述**（如"未点赞态且图标为明显绿色"），让它成为执行步骤能否成立的前提，而不是一条恒真断言；
   `visual` 只能作为附加证据项存在。
   动作只描述操作本身，不得在动作里隐含"确认结果"语义（结果交给 Assert）。

【字段说明】
- **Priority**: `P0` | `P1` | `P2` | `P3`（核心正向场景优先 P0）。
- **Platform**: `Android` | `iOS`（决定 `adk-sdt-implement` 解析哪个平台的 `VERIFY_WORKFLOW`）。
- **Pkg**: 被测 App 包名 / Bundle ID。**它必须是这一跑实际会装到设备上的那个包**——
  验证工作流按它清场、装包、拉起应用，写错的表现不是报错，而是清了一个不存在的应用、
  或在错误的 app 上跑完一整轮用例。
  **判据：与这个仓当前构建出来的那个包一致，不是仓库里第一个搜到的标识符。**
  多 flavor 的工程里，构建脚本顶部的默认标识符往往不是本次构建的那个（同一个文件里
  常有若干条按 flavor 覆盖的）。**怎么拿到它取决于平台**：
  Android 从构建命令的 flavor 反查那个 flavor 自己的 `applicationId`（所以先定 `task`）；
  iOS 是 Bundle ID。拿不准就问用户，不要从构建脚本里挑一个看着像的。
- **Path**: 自然语言的主路径描述，仅作导航向导，不是执行的唯一依据。
- **Precondition**: 每行一个，前缀标签决定语义：
  - `mock | <可配置的 App/环境状态>`：AB 实验、地区、灰度、登录态、网络、设备设置等（执行期由框架注入并随启动生效）。
  - `assume | <声明式假设>`：例如"使用一个已注册账号"等从候选资源中选取的前提（无法注入、只能声明）。
  - `page | 起点 → ... → 目标页`：页面门禁链路；其下可挂 `route | <waypoint>: <到达方式>`。
- **Steps**: 有序步骤，一步一操作，每步下挂 1+ 条 `Assert: <category> | <期望>`。
- **Assert**（用例级收尾断言）：整条用例结束后必须成立的断言。
- **Assert category**：
  - `text`：UI 树文本子串匹配（确定性，框架判定）。期望串尽量短而稳定。
  - `state`：页面/元素状态查询（确定性，框架判定，如 enabled/selected/存在性）。
  - `visual`：截图视觉判断（AI 判定，需自报置信度），仅在 text/state 无法覆盖时使用。
  - `tracker`：埋点事件断言，写明事件名（如 `enter_personal_detail`）与关键参数。
  - `network`：接口断言，写明 method + urlPattern（如 `POST /aweme/v1/commit/item/digg/ 返回 2xx`）。

【产物骨架 — 以下才是写入 case.md 的内容】
-->

# 测试用例: {{FEATURE_NAME}}

> 本文件由 `adk-sdt-ff` 基于 spec 目录（`spec.md` / `plan.md` 等）生成，面向客户端（Android / iOS）E2E。
> 每个用例是一个独立场景；用例之间相互隔离，不得跨用例携带状态假设。执行参数见 `test/task.md`。

## TC-001: {{用例标题简述}}

> {{用例验证意图，例：进入他人页后，极小包场景的基础交互下应正常工作。}}

- **Priority**: P1
- **Platform**: iOS
- **Pkg**: {{BUNDLE_ID}}

**Path**:
{{主路径描述，例：他人页主路径：首页点击用户头像进入他人页}}

**Precondition**:
- mock | ab {{AB_KEY}}={{AB_VALUE}}
- page | 首页 → {{目标页}}
    - route | {{目标页}}: {{到达方式}}

**Steps**:
1. {{单个操作}}
    - Assert: text | {{期望}}
2. {{单个操作}}
    - Assert: state | {{期望}}
    - Assert: tracker | 触发 {{event_name}} 埋点

**Assert**:
- text | 当前前台应用仍为 App 本身，交互无异常跳转或闪退

---

## 用例表（执行索引）

<!--
本表由上方用例区块**派生**，供执行框架确定性解析（verify-loop `cases:parse` 按表头定位
`用例ID` / `执行步骤` / `预期结果` 三列，`优先级` / `角色` / `前置条件` 为增强列）。
硬规则：
1. 每个 `## TC-XXX` 区块对应本表一行，两处内容必须一致——任何对区块的修改（ff 生成、clarify 澄清）
   必须同步更新本表；不一致视为 case.md 无效。
2. 前置条件列 = 该用例 Precondition 各行压缩（`mock: ...`、`page: ...`、`route: ...`、`assume: ...`，`<br>` 分隔）。
3. 执行步骤列 = Steps 编号项（`1.` `2.` … `<br>` 分隔，只含操作本身）。
4. 预期结果列 = 各步骤 Assert + 用例级 Assert，按步骤号对应，每条带 category 前缀（`1. text: ...`）。
5. 角色列：单角色写 `user`；双端/双角色拆成两行顺序用例并注明依赖。
-->

| 用例ID | 优先级 | 角色 | 前置条件 | 执行步骤 | 预期结果 |
|--------|--------|------|----------|----------|----------|
| TC-001 | P1 | user | mock: ab {{AB_KEY}}={{AB_VALUE}}<br>page: 首页 → {{目标页}}<br>route: {{到达方式}} | 1. {{单个操作}}<br>2. {{单个操作}} | 1. text: {{期望}}<br>2. state: {{期望}}；tracker: 触发 {{event_name}} 埋点<br>整体 text: 前台仍为 App 本身，无异常跳转或闪退 |

<!--
【硬规则】
1. 追加用例时复制 `## TC-XXX` 区块并递增编号，同时在「用例表（执行索引）」追加对应行。
2. 每条用例必须包含：标题引用块、Priority、Platform、Pkg、Path、Precondition、Steps、Assert。
3. 一份 case.md 只属于 test/task.md 里 `platform` 那一端（ff 只推断一个平台）；要双端都验就各出一份 feature。
4. 交付前删除本文件所有 {{...}} 占位符与模板注释；用例表至少 1 行，且与区块严格一致。
5. 本文件不写任何 skill 调用细节与执行参数；执行编排在 test/task.md（唯一事实源）。
-->
