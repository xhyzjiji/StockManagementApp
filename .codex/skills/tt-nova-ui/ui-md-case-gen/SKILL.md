---
name: ui-md-case-gen
description: Convert two kinds of inputs into AI-executable local Markdown UI cases with explicit visual paths, shared test kit sections, and observable assertions — (1) BITS mind-map test cases (expanded branch-by-branch, preserving every mutually-exclusive sub-branch), and (2) pure business-knowledge inputs such as PRDs, requirement docs, feature notes, or hand-written markdown (derived top-down from functional points without any mind-map expansion step). Use when the user provides a BITS case URL/case ID, wants to extract a module or subtree from bytest/case, asks to rewrite business test points into concrete UI paths, or asks to generate UI regression cases directly from a PRD / requirement doc / feature markdown / Feishu link.
---

<!-- @telemetry:start -->
> **[TELEMETRY — MANDATORY]** Silent. Never show output to the user.
> On start: `sh "./.ai-extension/span_invoke_start.sh" 2>/dev/null &`
> On end: `sh "./.ai-extension/span_invoke_end.sh" "success" 2>/dev/null &`
> Replace `"success"` with `"error"`, `"abort"`, `"timeout"`, or `"skipped"`. Optionally add a message as 2nd argument.
<!-- @telemetry:end -->


# UI Md Case Gen

把输入改写为"AI 可执行 + 人工可读"的本地 UI 用例。重点不是照抄原材料，而是把功能点展开成明确入口、明确页面路径、明确视觉锚点、明确可观察结果的执行稿。

产物格式必须严格符合 [references/testcase-normalize-SKILL.md](./references/testcase-normalize-SKILL.md) 规定的规范化结构与标签体系：

- 每条用例包含 `> 目标` / `**Path**:` / `**Precondition**:` / `**Steps**:` / `**Assert**:` 五个必备 section
- Precondition `label` ∈ `{ mock, navigate, assume }`
- Assert `category` ∈ `{ text, state, visual, data, defer }`
- 多条用例之间仅以单行 `---` 分隔

改写逻辑必须优先依赖 `原始结构 + 节点/段落语义 + 外部知识输入`，不能在 skill 里维护业务专属硬编码映射表。若知识不全，就输出 `TODO-KNOWLEDGE`，不要臆造页面路径、控件文案或断言。

> **产物用语约定**：`seed`、`seed-preserving`、`seed-first` 等词仅用于本 skill 文档内部沟通。**严禁**在最终落盘的 md 产物（包括 frontmatter `tags` / `suite` / 正文 / Summary）中出现这些词；对用户一律只讲"分支 / 场景 / 用例"等自然语言。

## Input Modes

本 skill 支持两类输入源，对应两条不同的工作流：

### Mode A: BITS 脑图用例（走分支展开流程）

- 输入：`bits_case_url` 或 `test_case_id + product_id + space_id`
- 特征：原始 BITS 脑图里有明确的"互斥分支"结构（如 `冷启动 / 热启动`、`iOS / Android`、`登录态 / 未登录态`）
- 做法：**先把原始脑图机械地展开成一条条独立分支**（内部术语 `seed`），再逐条改写为规范化 case
- 目的：保证不把并列互斥分支压成一条 case、不漏覆盖

### Mode B: 纯业务知识输入（走自顶向下梳理流程）

- 输入：PRD 链接、需求文档 / feature markdown / 飞书文档 / 自由格式需求描述
- 特征：**没有"互斥分支"可抽取**，只有功能点、页面描述、验收标准等自然语言
- 做法：**不走分支展开流程**。直接按以下步骤：
  1. 从业务知识里提炼**功能点清单**（每个功能点 = 一条潜在用例）
  2. 对每个功能点显式列举**入口状态变量**（平台 / 登录态 / 实验组 / 地区 …），有差异就拆成独立用例
  3. 把每条功能点 + 入口组合，按 [references/testcase-normalize-SKILL.md](./references/testcase-normalize-SKILL.md) 规范化为 case
- 不要调用 `scripts/extract_bits_case.py`、`scripts/render_seed_cases.py`（这两个脚本仅服务于 Mode A）
- 拆分原则仍然适用："入口状态不同必须独立成 case"——只是这里的"分支"要你自己从功能点中识别出来，而不是脚本抽取

### 如何选择模式

| 线索 | 走哪条 |
|---|---|
| 用户给了 BITS 链接、case id、bytest 字样 | Mode A |
| 用户给了 PRD 链接、需求文档、feature md、飞书 wiki、口头需求 | Mode B |
| 用户既有 BITS 又有 PRD | 以 BITS 为主走 Mode A，把 PRD 作为 [references/knowledge-input-contract.md](./references/knowledge-input-contract.md) 中定义的"知识补充包" |

## Inputs

### 共同输入（两种模式都需要）

1. `module_focus`
   - Mode A：用来从大脑图中裁剪目标子树，例如 `开播工具区 / ENHANCE / Face`
   - Mode B：用来圈定 PRD / 文档中的目标功能范围，写入每条 case 的 `**Path**:`
2. `output_path`：正式 Markdown 产物落盘路径，统一为 `<repo_root>/tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md`
3. 知识补充包：读取 [references/knowledge-input-contract.md](./references/knowledge-input-contract.md)

### Mode A 专属输入

- `bits_case_url` 或 `test_case_id + product_id + space_id`

### Mode B 专属输入

- `knowledge_sources`：PRD 链接 / 文档绝对路径 / 直接粘贴的需求正文。多项即视为并列输入源。

如果知识不全，不要臆造。保留 `<待补充>` 或 `TODO-KNOWLEDGE:` 占位，并继续生成可落盘的首版结果。

## Workflow

两种模式的 **Step 3（知识补充）** / **Step 4（改写生成）** / **Step 5（组织 Test Kit）** / **Step 6（自检）** 完全一致；差异只在 Step 1~2 的"素材获取"环节。

### Mode A · Step 1: 获取 BITS 原始脑图

抓取 BITS case 统一走 `scripts/fetch_bits_case.py`（直接调用 ByTest 官方接口
`POST /caseApi/getCaseDetail`），**不要**再用 `gdpa-cli run bytest_case`。相比旧的 gdpa 封装，
该接口会额外返回 `ByteIOCaseInfo`（埋点用例映射，用于埋点断言，见 Step 2 的埋点处理）。

从 BITS URL 提取：

- `space_id`: `/devops/<space_id>/`
- `test_case_id`: `/caseDetail/<id>`
- `product_id`: query string `projectId`

**鉴权：该登录登录（默认全自动，不要手抠浏览器 Cookie）**：
ByTest 域名接受 ByteCloud 的 `X-Jwt-Token`。脚本默认自动登录取 JWT：
- 首选 `gdpa-cli login -p cn`（本仓库标准登录）；未装 gdpa-cli 时回退
  `byte-cli login --control-plane cn get-jwt`。JWT 从不落盘、不打印。
- **前提**：先登录一次 `gdpa-cli login cn`。报 `errCode=40 Auth ERROR` 多为登录态过期 →
  `gdpa-cli login -f cn` 强制刷新后重试。
- 内网 ByTest 域名用企业自签 CA，脚本默认跳过 TLS 校验（与 ui-debug-task-exec 一致）；
  需严格校验加 `--verify-tls`。
- **Cookie 可选**：仅当某部署拒绝裸 `X-Jwt-Token` 时，才用 `--cookie` / `BYTEST_COOKIE` 补浏览器 Cookie。
- 覆盖来源（按优先级，均可选）：`--jwt` > 环境变量 `BYTEST_JWT`/`X_JWT_TOKEN` >
  凭证文件 `--creds` 或 `~/.bytest_creds.json` > 自动登录（`--no-auto-jwt` 可关闭）。
  `operator` 缺省从 jwt 的 `username` 声明解码，也可 `--operator` 指定。

抓取示例：

```bash
python3 ./scripts/fetch_bits_case.py \
  --test-case-id 14584786 \
  --product-id 66666866 \
  --space-id 1499051266 \
  --output /abs/path/bytest-case-14584786.json
```

结果落到 `--output` 指定的路径，供 Step 2 的 `extract_bits_case.py` 消费。

### Mode A · Step 2: 先抽分支，再生成 Case

不要把超大的脑图 JSON 整体塞进上下文。先用脚本抽**原始分支清单**（内部术语 `seed`），再读规整结果。

```bash
python3 ./scripts/extract_bits_case.py \
  --input /abs/path/bytest-case-13956026.json \
  --focus "开播工具区,ENHANCE,Face" \
  --format json \
  --output /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-md-case-gen/anchor_face_seeds.json
```

脚本会：

- 自动识别 `TestCaseMind` 所在位置
- 把每一条能落到预期结果的叶子分支展开成 1 条独立分支记录
- 输出路径、feature 路径、步骤链、预期、标签、优先级、备注
- 按 `--focus` 过滤，只保留目标模块
- **识别埋点需求**：自动定位响应里的 `ByteIOCaseInfo.CaseList`（`{预期节点id: [埋点用例,...]}`），
  把命中的埋点用例挂到对应分支的 `byteio_cases` 字段（元素含 `ID`/`Name`/`InvokeNum`/`AppID`/`Region`）。
  输出顶层的 `byteio_seed_count` 表示有多少条分支带埋点需求。

如果需要给人快速预览，改成 `--format md`（埋点分支会额外列出「ByteIO 埋点用例」小节）。

分支展开约束：

1. `一条互斥分支 = 一条记录`
2. `热启动 / 冷启动 / 已登录 / 未登录 / iOS / Android` 这类入口状态不同的分支必须拆开
3. 禁止先按"看起来像一个功能点"做语义合并，再回头补 case
4. 先保证 `分支数 >= 原始有效分支数`，再做 case 改写

**埋点需求处理（当分支带 `byteio_cases` 时，强约束）**：

- 该分支即为**埋点需求**，改写成用例时**必须**把埋点断言工具 `et_checker_G20` 挂到该分支
  **断言步骤的预期结果节点**上（非独立操作步骤，对应原始脑图 nodeType=13 预期节点带 ByteIO resource），
  并把该分支的 `byteio_cases` 作为参数传入：
  `et_checker_G20 byteio_case_list=<byteio_cases 的 JSON 数组>`。
- 渲染时 `et_checker_G20` 是 type=41 环境工具（`saitama_template_id=8e33fdd1-2d9f-4ac0-ad07-28adabf9c4c0`、
  `app_id=0`），会把 `byteio_case_list` 写入 inputData，格式为
  `[{"key":"byteio_case_list","value":["<用例数组 JSON 字符串>"]}]`。
- **缺参数就反问用户**：若识别为埋点需求（分支带 `byteio_cases` 或用户明确要求校验埋点）
  但拿不到可用的埋点用例列表（`byteio_cases` 为空），**不要**臆造，直接反问用户索要
  ByteIO 用例（`ID`/`Name`/`AppID`/`Region`），拿到后再补 `et_checker_G20` 参数。

### Mode B · Step 1: 通读业务知识并锁定功能范围

- 读取用户提供的 PRD / 文档 / 需求正文：
  - 本地文件：直接读取
  - 飞书 / Lark 文档链接（`*.larkoffice.com` / `*.larksuite.com` / `*.feishu.cn`）：用本 skill 的飞书读取脚本抓取正文，**不要**要求用户先人工粘贴
  - 其它远程链接（无法用工具抓取的）：由用户粘贴正文或提前抓取到本地
- 按 `module_focus` 框定要覆盖的功能范围

> **飞书文档读取（走 gdpa `lark-docs`）**：
> - 入参：`document_url`（文档链接）、`user_name`（用户邮箱前缀，如 `huangyiran.dd`，用于鉴权）
> - 若外层已有 `GDPA_SESSION_ID` / `SESSION_ID` 直接复用；否则脚本内部会自动 `gdpa-cli create-session`
> - 直接执行本地包装脚本：
> ```bash
> python3 ./scripts/lark_content_loader.py <document_url> [user_name]
> ```
> - 等价原生命令：
> ```bash
> gdpa-cli run lark-docs --session-id <session_id> --input '{"url":"<document_url>","user_name":"<user_name>"}'
> ```
> - 抓到的正文可作为 Mode B 知识补充包，或用于补齐 Common Test Accounts（账号 wiki）等 `mock` 前置信息。
- 产出一份**功能点清单**（仅用于内部推理，不写入最终产物）：
  - 每个功能点 = 一条主用户故事（例如：`在 Settings 页将视频质量切换为 720p`）
  - 标注每个功能点的验收标准（用来反查断言）

### Mode B · Step 2: 显式列举入口状态变量并拆分分支

在 Mode B 里没有机械脚本帮你抽分支，**必须手动**列举：

- 平台：iOS / Android（若 PRD 明确单端，则不拆）
- 登录态 / 角色：主播 / 观众 / 管理员 / 游客
- 实验组 / 灰度 / 地区差异
- 入口场景：冷启动 / 热启动 / 从 deeplink 进入 / 从某前置页进入
- 数据前置差异：空态 / 首次进入 / 已有数据

凡是会改变用户所见 UI 或断言结果的状态变量，就必须拆成独立用例——这条规则和 Mode A 完全一致，只是分支源头是你从 PRD 自己识别的。

### 通用 · Step 3 前置：知识来源判定（无知识链接 → 优先检索 Tika 知识库）

**判定规则（生成前必做）**：

- 若用户输入里**已包含知识链接 / 文档**（PRD / 飞书 / Lark / Confluence 链接、本地知识文件、或直接粘贴的需求正文），照常按既有方式读取（飞书走 `scripts/lark_content_loader.py`，本地直接读）。
- 若用户**没有提供任何知识链接 / 文档**（Mode B 的 `knowledge_sources` 为空，或 Mode A 仅给了 BITS 脑图却缺业务背景），则**优先调用 Tika 知识库**检索与本模块 / 功能相关的知识，作为知识补充包，再进入 Step 3 / Step 4；**不要**因为没有链接就直接臆造页面路径、控件文案或断言。

**Tika 检索调用**（自定义 Agent OpenAPI v2，检索源由 Agent 配置决定）：

```bash
python3 ./scripts/tika_knowledge.py "<module_focus / 功能关键词 / 业务名>" \
  --user-name <用户邮箱前缀，如 huangyiran.dd> \
  --pretty
```

- 凭证（服务账号 JWT、`space_id`、`agent_id`）通过环境变量 `TIKA_JWT_TOKEN`、`TIKA_SPACE_ID`、`TIKA_AGENT_ID`（兼容旧 `TIKA_TENANT_ID` 作 space_id；可选 `TIKA_ENV`：办公网 `office` / 生产网 `prod`）或 `--config <json>` 提供；缺失时脚本会返回明确报错（不会编造）。
- 接入文档：[Tika 自定义 Agent 接入](https://bytedance.larkoffice.com/wiki/VEX4wwxF4iDV24ktekacclT3ndf)
- 返回 JSON 中 `answer` 是 Tika 综合回答，`references[]` 是召回的知识片段（含 `title` / `url` / `content`）。把它们作为知识补充包，并在产物里保留来源 `url` 以便追溯。
- 若 Tika 未配置或返回为空：退回 `TODO-KNOWLEDGE` 占位，**不要编造**。

### 通用 · Step 3: 构建知识补充包

读取 [references/knowledge-input-contract.md](./references/knowledge-input-contract.md)，至少补齐这些信息：

- 入口方式：deeplink 或手动入口路径
- 页面和控件映射：把业务词翻译成视觉定位描述
- 测试账号与角色
- 平台差异
- 特殊业务规则或实验条件

缺知识时遵守两条规则：

1. 不编造不存在的控件、页面、开关或账号
2. 允许带占位输出，但要显式标出待补充项

**账号原则（重要，必须遵守）**：

1. **注册账号类**用例（如"新注册某年龄段账号"）：前置**不登录已有账号**，写成"**app 启动后走注册流程注册一个新账号**"，可调用造数工具 `tt-nova-datagen` 完成注册 / 造号。
2. **特定账号类**用例：**优先选用知识 / 账号文档中满足条件的真实账号**；文档中没有满足条件的账号时，再用**造数 / ttmock 构造**一个。
3. **严禁编造不存在的账号或账号池**（例如把 wiki 链接里的 collection id 当成 TTAT pool_id、把列头文字当成 pool_name）。没有指定账号时，从账号文档里挑一个真实账号行即可。

### 通用 · Step 4: 生成 AI 可执行 UI 用例

输出格式遵守 [references/output-contract.md](./references/output-contract.md) 与 [references/testcase-normalize-SKILL.md](./references/testcase-normalize-SKILL.md)。

改写时强制执行以下规则：

- 先逐条分支改写，再决定是否允许聚类
- 只有入口状态相同、操作路径相同、断言只是同屏静态并列检查时，才允许合并
- 只要入口状态不同，就必须保持为独立 case
- 如果原始存在 `冷启动 / 热启动` 等并列子分支（Mode A 从脑图抽取；Mode B 从 PRD 自行识别），最终产物必须出现对应的独立测试用例
- 页面、状态、动作、断言优先从原始节点 / PRD 段落本身解析；不要为某个业务域继续堆叠 `normalize_expected` 风格的大型字符串规则表

- 每条用例从明确入口开始写
  - 优先 deeplink（写成 `navigate | ...` 型 Precondition 或进入 `**Setup**:`）
  - 无 deeplink 时把手动导航路径拆成若干 `navigate | ...` Precondition
- 每一步只做一个动作，放到 `**Steps**:` 下的数字编号条目
- 每个动作都写"页面 + 视觉锚点 + 动作"
- 预期写在 `Assert: <category> | <描述>` 子项中，只写可观察结果
  - 可见文案 → `text`
  - 控件状态变化 / 页面跳转 / 弹出或消失 → `state`
  - 视觉外观（颜色/样式/布局/动画/对齐） → `visual`
  - 请求/埋点/缓存/上报 → `data`
  - 其余当前工具链无法自动验证 → `defer`
- 把"双端差异"集中放到 Test Kit 的 Platform Differences，正文只在 `**Notes**:` 引用 `PD-xx`
- 把强业务术语翻译成可定位的 UI 描述；必要时保留原词并补一句释义

**产物用语红线**：正文、frontmatter、标题、Notes 中**不得**出现 `seed`、`seed-preserving`、`seed-first`、`Raw Seeds`、`一条 seed = 一条 case` 等内部术语。需要表达这类意思时，一律写成"分支 / 场景 / 用例"。

Precondition 标签判定口诀（与规范一致）：

- 配置型状态（配置/实验/开关/泳道/账号登录态/业务数据/网络 mock/设备配置） → `mock`
- 用户操作到达某页面/入口/状态 → `navigate`
- 纯声明性假设，且文本中不含"切换 / 设置 / 修改 / 开启 / 关闭"等动作动词 → `assume`

坏例子：

- `点击美颜`
- `检查功能正常`
- `进入设置页`
- `- Assert: 面板展示正常`（缺 category）
- `- 登录账号 A` 作为 Precondition（缺 label；且包含动作动词，应为 `mock | 账号 A 已登录`）

好例子：

- `1. 在主播开播预览页点击工具区内带有魔法棒图标的 "美颜" 文本按钮。`
  - `- Assert: state | 底部弹出美颜面板。`
  - `- Assert: text | 面板顶部可见 "Face"、"Filters" 等 tab。`
- `1. 在 Settings 面板点击 "Video quality" 行。`
  - `- Assert: state | 进入 Video quality 子页面。`

### 通用 · Step 5: 组织共享 Test Kit

把重复信息前置到文件顶部，而不是在每条 case 内重复写：

- Deeplink
- 扩展 UI Mapping
- Platform Differences
- Common Test Accounts

目标是让单条 case 只保留场景差异。

### 通用 · Step 6: 覆盖自检

落盘前逐条检查：

结构层面（对齐 `testcase-normalize-SKILL.md` 的"输出前自检"）：

- 每条用例是否以 `>` 开头写测试目标？
- 是否包含 `**Path**:` / `**Precondition**:` / `**Steps**:` / `**Assert**:` 四个必备 section？
- `**Steps**:` 下每一行断言是否都以 `- Assert: <category> | <描述>` 开头？
- 多条用例之间是否仅用单行 `---` 分隔？
- 所有 Precondition label 是否属于 `{ mock, navigate, assume }`？
- 所有 Assert category 是否属于 `{ text, state, visual, data, defer }`？
- `assume` 型 Precondition 是否不含"切换 / 设置 / 修改 / 开启 / 关闭"等动作动词？
- **产物正文 / frontmatter / Notes 是否不含 `seed` / `seed-preserving` / `seed-first` 等内部术语？**（违反即改写）

覆盖与执行层面：

- 分支总数是否大于等于原始有效分支数（Mode A：脚本抽取数；Mode B：自己识别的入口状态组合数）
- 是否存在原始子分支未落到独立 case
- 每条步骤是否能被没有业务背景的人直接执行
- 是否存在"这里/那个/正常/正确/相关功能"等模糊词
- 是否有未解释的业务黑话
- 是否给出了入口路径
- 是否把平台差异写散到了正文
- 是否把缺失知识标成了 `TODO-KNOWLEDGE`

最低标准：

- 不能漏分支
- 不能把互斥状态过度拟合成 1 条 case
- 若发现生成结果少于原始分支数，优先怀疑自己发生了错误合并

## Output

输出是本地 Markdown 文件，统一写到：

`<repo_root>/tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md`

- Mode A：不直接回传 BITS。若用户后续要上传，可再交给 `$ui-md-case-upload`。上传时若 `--precondition-tools-json` 含 `ttmock_preset.ab_settings` / `ab_settings_live`，**必须先**校验为 JSON 对象：
  `python skills/tt-nova-ui/ui-xmind-case-gen/script.py check-json-object --param ab_settings '<值>'`（`ok:false` 禁止上传）。
- Mode B：直接交付给用户；不涉及 BITS 回写。

所有抽分支 JSON、临时骨架、覆盖率校验输入、验证脚本统一放到：

`<repo_root>/tt-nova/ui/tmp/{vc}/{module}/ui-md-case-gen/`

`ui_path` 推荐使用与模块语义一致的 stem，例如：

- `{module}`
- `{module}_part1`

## Resources

### References

- [references/testcase-normalize-SKILL.md](./references/testcase-normalize-SKILL.md)
  - 产物的规范化标准（五个必备 section、Precondition / Assert 标签体系、输出前自检），所有产物必须通过其中列出的检查项
- [references/knowledge-input-contract.md](./references/knowledge-input-contract.md)
  - 定义生成前必须补的知识项，以及缺失时如何占位
- [references/output-contract.md](./references/output-contract.md)
  - 定义文件级骨架（Front matter、Test Kit）和改写规则，结构细节以 `testcase-normalize-SKILL.md` 为准

### Script

- [scripts/extract_bits_case.py](./scripts/extract_bits_case.py)
  - **仅服务于 Mode A**：从 BITS case JSON 中抽出目标子树和候选场景，避免把原始超大 JSON 直接喂给模型
  - Mode B 不使用本脚本
- [scripts/render_seed_cases.py](./scripts/render_seed_cases.py)
  - **仅服务于 Mode A**：产出分支展开的中间骨架（内部术语 `seed-preserving`），不是最终产物
  - 脚本输出只作为 agent 改写的参考输入；最终落盘的 case 必须由 agent 重新按 [references/testcase-normalize-SKILL.md](./references/testcase-normalize-SKILL.md) 改写，产出 `> 目标` / `**Path**:` / `**Precondition**:` / `**Steps**:` / `**Assert**:` 结构并打上合法标签
  - **严禁**把本脚本的中间输出直接落盘作为产物（其中含 `seed` 字样的文本会泄漏给用户）
  - Mode B 不使用本脚本
- [scripts/lark_content_loader.py](./scripts/lark_content_loader.py)
  - 读取飞书 / Lark 文档正文，底层走 `gdpa-cli run lark-docs`
  - 用法：`python3 ./scripts/lark_content_loader.py <document_url> [user_name]`
  - Mode A / Mode B 通用：可用于读取 PRD、需求文档、账号 wiki 等飞书文档作为知识补充包
- [scripts/tika_knowledge.py](./scripts/tika_knowledge.py)
  - Tika 自定义 Agent OpenAPI v2 知识检索客户端（建会话 → 发起对话检索 → 解析 SSE）
  - **用途**：当输入**没有给任何知识链接**时，优先用它召回相关业务知识作为知识补充包（见 Step 3 前置）
  - 用法：`python3 ./scripts/tika_knowledge.py "<查询>" [--user-name <邮箱前缀>] [--pretty]`
  - 凭证走环境变量 `TIKA_JWT_TOKEN` / `TIKA_SPACE_ID` / `TIKA_AGENT_ID`（可选 `TIKA_ENV`）或 `--config <json>`
