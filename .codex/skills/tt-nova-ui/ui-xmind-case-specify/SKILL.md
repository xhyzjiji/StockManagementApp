---
name: "ui-xmind-case-specify"
description: "支持两种场景生成 Feature 测试规格文档（spec）：测新模式（基于 PRD 文档）和回归模式（基于手工用例 xlsx/md 或 BITS 用例链接 / case id）。"
---

# UI Xmind Case Specify

## Description

你是一个测试架构文档生成器（QA Documentation Generator），同时具备：
- 测试语义解析能力（识别 action / assertion / state）
- 测试建模能力（抽象测试点、合并同类用例）
- 多模态理解能力（结合截图理解 UI，并将关键信息转为可验证文本）

支持两种工作模式：
- **测新模式（New Feature）**：基于 PRD / 产品文档 / 技术文档，从需求出发生成完整的测试规格文档
- **回归模式（Regression）**：基于已有手工用例（xlsx / md / BITS 脑图用例），将散乱用例结构化为标准 spec

## When to Use

| 场景 | 触发条件 | 输入 |
|------|---------|------|
| **测新** | 用户提供 PRD 链接 / 产品文档，无手工用例 | PRD 链接（必选）+ 技术文档（可选） |
| **回归** | 用户提供 xlsx / md 手工用例文件，或提供 BITS 链接 / case id | 用例文件或 BITS case（必选）+ PRD（可选补充） |

**自动判断规则**：
- 用户提供了 `.xlsx` 或 `.md` 用例文件 → **回归模式**
- 用户提供了 BITS 链接、`caseDetail/<id>`、`test_case_id`、`bytest` 相关描述 → **回归模式**
- 用户仅提供 PRD / 飞书链接，无用例文件 → **测新模式**
- 同时提供用例文件 / BITS case + PRD → **回归模式**（PRD 作为补充信息增强 spec 质量）

## Usage

### 统一路径约定

- **正式 spec 产物**：`<repo_root>/tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_spec.md`
- **临时 JSON / Prompt / 校验脚本**：`<repo_root>/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/...`

本 skill 下凡是回归模式规整 JSON、Feature 级有效用例 JSON、分批 Prompt、覆盖率校验输入、临时验证脚本，都统一放到 `tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/`，不要再写到裸 `/tmp/` 或仓库根目录 `output/`。

### 输入

#### 测新模式（New Feature）

- **PRD / 产品文档**（必选）：飞书 / Confluence 链接，或本地文件路径
- 技术文档（可选）：链接或文件路径
- 相关接口/埋点/状态说明（可选）
- 用户名（可选）：用于读取飞书文档权限（如 huangyiran.dd）

测新模式下，Seeds 由 PRD 需求细节推导生成（非手工用例转换），需要从需求描述中识别：
- 功能边界和角色（主播/观众/管理员）
- 业务规则和状态流转
- UI 交互路径和入口
- 预期结果和可观测信号
- 异常与边界场景

**测新模式的生成顺序**：与回归模式一致（自底向上），但 Ch7 Seeds 来源不同：
- 回归模式：Seeds = 手工用例的 1:1 结构化转换
- 测新模式：Seeds = 从 PRD 功能描述中推导的最小可测试单元，每个 seed 对应一条独立的、可由 AutoGLM 执行的测试路径

#### 回归模式（Regression）

- **原始回归输入**（必选，三选一）：
  - **xlsx 文件路径**：用例可能含截图或图片链接
  - **md 文件路径**：层级式 markdown 格式（见下方「md 手工用例格式」）
  - **BITS 用例**：`bits_case_url` 或 `test_case_id + product_id + space_id`
- 产品文档（可选）：链接（飞书/Confluence 等）
- 技术文档（可选）：链接（飞书/Confluence 等）
- 相关接口/埋点/状态说明（可选）：接口名、PSM、埋点名、状态字段/状态机描述等
- 用户名（可选）：用于读取飞书文档权限（如 yixin.11）
- 优先级过滤（可选）：按用例表格中的「优先级」列筛选用例范围
  - **"只要P0"** / **"P0"**：仅保留优先级为 P0 的用例
  - **"P1+"**：保留 P0 和 P1 的用例
  - **"P2+"**：保留 P0、P1 和 P2 的用例
  - **未指定**：默认不过滤，处理全部用例
- PRD / 产品文档（可选）：补充模块定位、业务规则、边界
- 技术文档（可选）
- 用户名（可选）
- 优先级过滤（可选）：按用例表格中的「优先级」列筛选用例范围
  - **"只要P0"** / **"P0"**：仅保留优先级为 P0 的用例
  - **"P1+"**：保留 P0 和 P1 的用例
  - **"P2+"**：保留 P0、P1 和 P2 的用例
  - **未指定**：默认不过滤，处理全部用例

#### BITS 回归用例输入

当用户提供的是 BITS / bytest 用例链接时，**不要要求用户先人工导出为 md/xlsx**。直接在 skill 内完成抓取和规整，再进入回归模式主流程。

支持两种输入形态：

- `bits_case_url`
- `test_case_id + product_id + space_id`

若用户给的是完整 BITS 链接，从 URL 中提取：

- `space_id`：`/devops/<space_id>/`
- `test_case_id`：`/caseDetail/<id>`
- `product_id`：优先取 query 中的 `projectId`；若缺失，再看 `devops_space_old_id`

BITS 回归输入的处理原则：

1. 先抓原始脑图 JSON，再做机械展开；不要把超大的原始 JSON 直接塞给 LLM。
2. 展开结果只作为 **回归模式的原始事实输入**，后续仍按本 skill 的 spec 生成规则产出 Ch1~Ch7。
3. BITS 中的互斥分支（如登录态/未登录态、冷启动/热启动、平台/地区差异）必须在 Ch7 Seeds 中保留为独立行。
4. 若用户同时给了 PRD / 飞书文档，则把 PRD 作为 BITS 回归模式的知识补充包，用于补全 Feature 边界、角色、实验条件和术语解释。
5. **强制步骤**：只要回归模式输入来自 BITS，必须先运行 `scripts/prepare_bits_regression_input.py` 产出标准中间 JSON；禁止跳过该步骤直接让 LLM读取原始 BITS JSON 或整条路径文本。

#### md 手工用例格式

当用户提供 `.md` 文件作为手工用例输入时，文件应采用以下层级结构：

```markdown
# 模块名称

## 功能模块 A

### 用例标题 1
#### 前置条件
- 条件描述 1
- 条件描述 2

#### 操作步骤
1. 步骤 1
2. 步骤 2
3. 步骤 3

#### 预期结果
- 结果 1
- 结果 2

---

### 用例标题 2
#### 前置条件
- ...

#### 操作步骤
1. ...

#### 预期结果
- ...

## 功能模块 B

### 用例标题 3
...
```

**层级映射**：
| Markdown 层级 | 含义 | 示例 |
|---|---|---|
| `#` | 模块 / 需求名称 | `# 粉丝团社群等级形象化` |
| `##` | 功能模块 / 用例分组 | `## 社群等级体系与积分` |
| `###` | 单条用例标题 | `### 社群lv1升级到lv2解锁手部槽位` |
| `####` | 用例字段 | `#### 前置条件` / `#### 操作步骤` / `#### 预期结果` |

**字段识别规则**（按 `####` 标题语义匹配，不强制字段名完全一致）：
- 前置条件：`前置条件` / `前置` / `Preconditions` / `前提`
- 操作步骤：`操作步骤` / `步骤` / `Steps` / `测试步骤`
- 预期结果：`预期结果` / `预期` / `Expected` / `期望结果`
- 备注/说明：`备注` / `说明` / `Notes`（可选字段）

**容错处理**：
- 如果 `###` 下没有 `####` 子标题，则将 `###` 下全部内容视为用例描述，按语义拆解为步骤与预期
- 如果 `####` 标题无法匹配上述字段，视为补充说明归入备注
- 列表项（`-` / `1.`）和纯文本段落均可作为字段内容

### 输出

输出为一个 Markdown 格式的 Feature 测试规格文档（spec）。必须严格遵守以下文档结构，不允许遗漏章节；不允许逐条复述原始用例；所有断言必须可验证；所有 UI 描述必须具体可定位。

```markdown
# Feature 测试规格文档（Spec）

## 1. 模块概述（Module Overview）
- 模块定位
- 模块边界

## 2. 功能点总览（Feature Index）
- F-01 功能点A
- F-02 功能点B

## 3. 功能点详情（Feature Details）

### 3.F-01 {{功能名称}}

#### 3.F-01.1 功能描述（What）
- 2~3 句话概括功能能力，不展开子场景细节

#### 3.F-01.2 使用前置条件（Preconditions）

**环境与权限前置（Environment & Access Prerequisites）**
- 本功能点所有场景共用的外部条件，须沿功能依赖链继承（登录、权限、版本、分组、地区等）

**功能依赖前置（Cross-Feature Dependencies）**
- 本功能点所有场景共用的功能依赖，须标注编号（→ F-XX）
- 每条依赖必须附带「前置实现配方」：用纯业务语言描述从零达到该前置状态的最小可执行步骤序列，供下游自动化框架将其映射为具体工具调用或 GUI 操作
- **禁止在配方中出现工具名、函数名、API 名**（如 `ai_room_start`、`enter_room`），只用业务动作（如"主播开播""观众进入直播间"）
- 格式：`- 依赖描述（→ F-XX）` 换行后跟 `  - 前置实现：步骤1 → 步骤2 → ...`

#### 3.F-01.3 测试场景（Test Scenarios）

<!-- 每个场景是一个自包含的测试单元，对应 xlsx 模块路径中的一棵子树 -->

##### S-a {{场景名称}}
- **场景前置条件**：在 Feature 级前置条件基础上，本场景额外需要的状态或操作结果
- **用户路径**：使用标准化 action 表达的操作步骤与系统响应
- **业务规则**：本场景相关的输入限制 / 逻辑规则 / 状态流转
- **验证要点**：具体的、可验证的断言列表（禁止"正常/正确"等模糊表述）
- **可观测信号**：UI 元素 / 接口 / 状态变化（截图信息须转为文字）
- **来源用例**：case_id 列表

##### S-b {{场景名称}}
- **场景前置条件**：...
- **用户路径**：...
- **业务规则**：...
- **验证要点**：...
- **可观测信号**：...
- **来源用例**：...

#### 3.F-01.4 异常与边界场景（Edge & Exception Cases）
- 跨场景的边界条件：空数据 / 超限 / 非法操作 / 中断恢复 / 并发与竞态

#### 3.F-01.5 不建议测试 / 已知限制（Out of Scope）

## 4. 功能点之间的关系（Feature Relationships）

## 5. 风险等级与测试优先级建议

## 6. 变更敏感点（Change Sensitivity）

## 7. 原始用例分组（Raw Case Seeds）
<!-- 此节供 ui-xmind-case-gen Pass 2 作为覆盖率锚点，每行对应一条独立可执行的 AutoGLM 用例 -->
<!-- 必须用表格形式，明确声明每条 seed 的入口状态，防止 ui-xmind-case-gen 错误合并互斥路径 -->

### F-01 {{功能名称}}

| Seed ID | 入口状态（前置） | 核心操作 | 预期结果 |
|---------|----------------|---------|---------|
| F01-S01 | {{对象/系统处于 XX 状态，如"竞猜进行中，观众未作答"}} | {{执行的动作，如"点击Yes"}} | {{可观测结果，如"显示已作答提示"}} |
| F01-S02 | {{同上或不同状态}} | {{另一个动作}} | {{对应结果}} |

### F-02 {{功能名称}}

| Seed ID | 入口状态（前置） | 核心操作 | 预期结果 |
|---------|----------------|---------|---------|
| F02-S01 | {{...}} | {{...}} | {{...}} |

## 输入数据
<!-- 回归模式：附原始 case 文件（xlsx 或 md）-->
<!-- 测新模式：附 PRD 链接及关键需求摘要 -->
{{回归模式：原始的 case 文件路径；测新模式：PRD 链接 + 需求摘要}}
```

### 执行提示

#### 可用工具

> **知识来源判定（生成 spec 前必做）**：
> - 若用户**已提供知识链接 / 文档**（PRD / 飞书 / Confluence 链接、本地用例或文档），按既有方式读取（飞书走 `scripts/lark_content_loader.py`，本地直接读）。
> - 若用户**没有提供任何知识链接 / 文档**（如回归模式只给了用例文件却无 PRD 补充，或缺少可读的需求文档），则**优先调用 Tika 知识库**检索与本模块 / Feature 相关的业务知识（功能边界、角色、术语、业务规则、状态流转），用于补全 spec；**不要**因缺链接就臆造或写"正常/正确"。
> - 若 Tika 未配置或返回为空：在对应位置标注 `⚠️ ... 请人工补充`，不要编造。

**Tika 知识库检索（无知识链接时优先）**：
- 按 [Tika 自定义 Agent OpenAPI v2](https://bytedance.larkoffice.com/wiki/VEX4wwxF4iDV24ktekacclT3ndf) 实现（建会话 → 发起对话检索 → 解析 SSE）；检索源由 Agent 配置决定。
- 用法：
```bash
python3 scripts/tika_knowledge.py "<module_focus / Feature 关键词 / 业务名>" \
  --user-name <用户邮箱前缀，如 huangyiran.dd> \
  --pretty
```
- 凭证走环境变量 `TIKA_JWT_TOKEN` / `TIKA_SPACE_ID` / `TIKA_AGENT_ID`（兼容旧 `TIKA_TENANT_ID` 作 space_id；可选 `TIKA_ENV`：办公网 `office` / 生产网 `prod`）或 `--config <json>`；缺失时脚本返回明确报错。
- 返回 JSON 的 `answer`（综合回答）+ `references[]`（召回片段，含 `title` / `url` / `content`）作为 spec 知识补充，引用 `url` 写入对应章节以便追溯。

**飞书文档读取（统一走 gdpa `lark-docs`）**：
- 准备入参：
  - document_url：文档链接
  - user_name：用户邮箱前缀，如 liqingquan.indigo
- 若外层已有 `GDPA_SESSION_ID` / `SESSION_ID`，直接复用；否则先执行 `gdpa-cli create-session` 创建会话。
- 可直接执行本地包装脚本，底层已切到 `gdpa-cli run lark-docs`：
```bash
python3 scripts/lark_content_loader.py <document_url> [user_name]
```
- 等价的原生命令如下：
```bash
gdpa-cli run lark-docs --session-id <session_id> --input '{
  "url": "<document_url>",
  "user_name": "<user_name>"
}'
```

**BITS 用例抓取与规整**：
- 复用兄弟 skill `ui-md-case-gen` 的现成抽分支脚本，但统一通过本 skill 的 `scripts/prepare_bits_regression_input.py` 输出标准中间 JSON。
- 先抓 case，再规整为回归模式输入；不要让 Agent 在对话里手工做字段映射。

抓取 BITS case（统一走 `ui-md-case-gen/scripts/fetch_bits_case.py`，直接调用 ByTest 官方接口
`POST /caseApi/getCaseDetail`，**不要**再用 `gdpa-cli run bytest_case`）。相比旧封装，该接口会额外
返回 `ByteIOCaseInfo`（埋点用例映射），后续规整脚本会据此标记埋点需求：

```bash
python3 ../ui-md-case-gen/scripts/fetch_bits_case.py \
  --test-case-id 13956026 \
  --product-id 66666866 \
  --space-id 1499051266 \
  --output /abs/path/bytest-case-13956026.json
```

**鉴权：该登录登录（默认全自动，不要手抠浏览器 Cookie）**：
ByTest 域名接受 ByteCloud 的 `X-Jwt-Token`。脚本默认自动登录取 JWT，无需手动传凭证：
- 首选 `gdpa-cli login -p cn` 打印 cn 区 JWT（本仓库标准登录）；未装 gdpa-cli 时回退
  `byte-cli login --control-plane cn get-jwt`。JWT 从不落盘、不打印。
- **前提**：先登录一次 `gdpa-cli login cn`（或 `gdpa-cli login`）。若拉取报
  `errCode=40 Auth ERROR`，多为登录态过期 → `gdpa-cli login -f cn` 强制刷新后重试。
- 内网 ByTest 域名使用企业自签 CA，脚本默认跳过 TLS 校验（与 ui-debug-task-exec 一致）；
  需严格校验加 `--verify-tls`。
- **Cookie 可选**：仅当某部署拒绝裸 `X-Jwt-Token` 时，才用 `--cookie` / `BYTEST_COOKIE` 补一个浏览器 Cookie。
- 覆盖来源（按优先级，均可选）：`--jwt` > 环境变量 `BYTEST_JWT`/`X_JWT_TOKEN` >
  凭证文件 `--creds` 或 `~/.bytest_creds.json` > 自动登录（`--no-auto-jwt` 可关闭）。
- `operator` 缺省从 jwt 的 `username` 声明解码，也可 `--operator` 显式指定。

将返回的 JSON 直接规整为回归模式中间文件：

```bash
python3 scripts/prepare_bits_regression_input.py \
  --input /abs/path/bytest-case-13956026.json \
  --input-kind bytest \
  --tmp-dir /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify \
  --output /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/bits_regression_input.json
```

若用户已指定模块范围，可追加 `--focus`：

```bash
python3 scripts/prepare_bits_regression_input.py \
  --input /abs/path/bytest-case-13956026.json \
  --input-kind bytest \
  --focus "开播工具区,ENHANCE,Face" \
  --tmp-dir /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify \
  --output /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/bits_regression_input.json
```

若用户已经给了 `extract_bits_case.py` 的产物，也可直接输入：

```bash
python3 scripts/prepare_bits_regression_input.py \
  --input /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/focused_bits_seeds.json \
  --input-kind extracted \
  --tmp-dir /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify \
  --output /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/bits_regression_input.json
```

`tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/bits_regression_input.json` 中的 `cases[]` 已是回归模式可直接消费的结构化输入，每条至少包含：
- `module`
- `title`
- `precond` / `precond_list`
- `steps` / `step_list`
- `expected` / `expected_list`
- `feature_path_text`
- `seed_path_text`
- `byteio_cases` / `is_byteio_case`（埋点需求：`is_byteio_case=true` 时，该用例关联了 ByteIO 埋点用例，
  改写时必须绑定 `et_checker_G20` 埋点断言，见下方「埋点需求处理」）

输出示例：

```json
{
  "source_type": "bits",
  "seed_count": 175,
  "case_count": 175,
  "cases": [
    {
      "id": "bits_0001",
      "module": "设备注册 / 卸载重装 / 覆盖安装，启动app",
      "title": "请求update_sender接口",
      "precond": "设备注册；卸载重装 / 覆盖安装，启动app",
      "precond_list": ["设备注册", "卸载重装 / 覆盖安装，启动app"],
      "steps": "请求update_sender接口",
      "step_list": ["请求update_sender接口"],
      "expected": "上报push的通道、设备型号、设备版本、sdk版本等信息",
      "expected_list": ["上报push的通道、设备型号、设备版本、sdk版本等信息"],
      "feature_path_text": "设备注册 / 卸载重装 / 覆盖安装，启动app",
      "seed_path_text": "设备注册 / 卸载重装 / 覆盖安装，启动app / 请求update_sender接口",
      "byteio_cases": [],
      "is_byteio_case": false
    }
  ]
}
```

#### 埋点需求处理（当 `is_byteio_case=true` 时，强约束）

- 顶层 `byteio_case_count` 给出带埋点需求的用例数；单条用例通过 `is_byteio_case` / `byteio_cases` 标记。
- 该用例改写为 spec seed 时，**必须**保留其埋点属性（spec 第 7 章 seed 表的第 5 列 `byteio_case_list`）。
  生成阶段（`ui-xmind-case-gen`）会**确定性地**把埋点断言工具 `et_checker_G20` 挂到该用例**断言步骤的
  预期结果节点**上（非独立操作步骤），参数 `byteio_case_list` 直接取该用例的 `byteio_cases`
  （元素含 `ID`/`Name`/`InvokeNum`/`AppID`/`Region`）。埋点工具为 type=41 环境工具
  （`saitama_template_id=8e33fdd1-2d9f-4ac0-ad07-28adabf9c4c0`，`app_id=0`），无需 LLM 复述用例 ID。
- **缺参数就反问用户**：若识别为埋点需求但 `byteio_cases` 为空（或用户口头要求校验埋点却无用例映射），
  **不要**臆造用例 ID，直接反问用户索要 ByteIO 用例（`ID`/`Name`/`AppID`/`Region`），拿到后再补参数。

#### 生成顺序（自底向上，必须遵守）

> **核心原则**：Seeds 是事实，Ch3 是对事实的归纳，Ch1/2/4/5/6 是摘要。必须先有事实，再写归纳，不可逆序。
> 逆序（先写 Ch3 再生成 seeds）会导致 LLM 锚定于抽象场景数量，对 seeds 进行有损压缩。

**阶段零（仅测新模式）：PRD 需求分析**

> 仅当进入**测新模式**（无手工用例，仅有 PRD）时执行此阶段。回归模式跳过。

1. 读取 PRD 全文（通过飞书文档读取工具或直接读取本地文件）
2. 提取并结构化以下信息：
   - **功能清单**：PRD 中描述的所有功能点，按模块分组 → 映射为 Feature（F-01, F-02, ...）
   - **角色清单**：涉及哪些角色（主播/观众/管理员/系统）
   - **业务规则**：输入限制、状态流转、权限控制、开关/实验依赖
   - **UI 交互描述**：页面入口、操作路径、页面跳转
   - **边界与异常**：PRD 中提到的特殊情况、限制、兼容性要求
3. 将上述信息整理为「PRD 需求摘要」，作为后续阶段的输入

**阶段零-B（仅 BITS 回归模式）：抓取与规整 BITS 原始事实**

> 仅当回归模式的输入是 **BITS 链接 / case id** 时执行。xlsx/md 回归模式跳过。
> **硬约束**：阶段零-B 是 BITS 回归模式的必经步骤，不允许跳过，不允许和阶段一并行。

1. 解析 `bits_case_url`，提取 `test_case_id` / `product_id` / `space_id`
2. 使用 `../ui-md-case-gen/scripts/fetch_bits_case.py`（ByTest 官方接口 `POST /caseApi/getCaseDetail`）拉取原始 case JSON；**不要**再用 `gdpa-cli run bytest_case`。该接口会返回 `ByteIOCaseInfo`（埋点用例映射）。脚本默认自动登录取 JWT（`gdpa-cli login -p cn`），**前提是已 `gdpa-cli login cn` 登录过**；报 `errCode=40 Auth ERROR` 时先 `gdpa-cli login -f cn` 刷新登录再重试（详见上文「鉴权：该登录登录」）
3. 用 `scripts/prepare_bits_regression_input.py` 将原始 JSON 规整为回归模式中间文件（会自动标记 `is_byteio_case` / `byteio_cases`）
4. 若用户指定模块范围，用 `--focus` 先裁剪目标子树，再进入 spec 生成
5. 将中间文件中的 `cases[]` 视为回归模式的“原始用例行”；`is_byteio_case=true` 的行按上方「埋点需求处理」保留埋点属性
6. 从这份映射结果继续执行本 skill 的阶段一、二、三；**不要要求用户再手工转 md/xlsx**

**阶段一：生成第 7 章 Seeds（事实层）**

**回归模式**：
- 输入分流：
  - **xlsx/md 回归输入**：原始手工用例，按 Feature 分组并预过滤有效行
  - **BITS 回归输入**：`tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/bits_regression_input.json` 中的 `cases[]`，按 Feature 分组并预过滤有效行
- 目标：格式规范化。Seeds = 对原始用例的 1:1 结构化转换，不做有损合并
- 约束：seeds 行数必须 ≥ 有效用例数（遵守「八、九」两节规则）
- BITS 额外约束：只读取 `bits_regression_input.json` 的结构化字段，不直接读取原始 BITS JSON 或整条路径文本
- 大规模场景（> 50 条）：使用 `seed-gen-prompts` 批量生成（见「九」）

**测新模式**：
- 输入：阶段零产出的「PRD 需求摘要」
- 目标：从需求描述推导出最小可测试单元。每个 seed 对应一条独立的、可由 AutoGLM 从冷启动执行的测试路径
- 推导逻辑（按 Feature 逐个处理）：
  1. **识别操作路径**：从 PRD 的 UI 交互描述中提取所有用户可执行的操作
  2. **识别状态变量**：从业务规则中提取影响行为的状态维度（如角色、权限等级、开关状态等）
  3. **叉积展开**：对操作路径 × 状态变量做组合，生成 seed 候选集
  4. **补充边界场景**：从 PRD 的限制/异常描述中补充边界 seed（空数据、超限、非法操作等）
  5. **精确化断言**：将 PRD 中的功能描述转为可观测的 UI / 系统反馈
- 约束：
  - 每条 seed 的「入口状态」必须精确到状态值，不可笼统
  - 每条 seed 的「预期结果」必须是可直接观测的 UI / 系统反馈，禁止"正常/正确"
  - 拆行规则（枚举值/多断言/多角色/叉积穷举）与回归模式完全相同（遵守「八」节规则）

**阶段二：生成第 3 章 Feature Details（洞察层）**

- 输入：已完成的 Ch7 Seeds + 原始输入（回归模式为用例文件，测新模式为 PRD 需求摘要）
- 目标：从 seeds 聚类归纳场景、从入口状态提炼前置条件、从预期结果汇总可观测信号
- 约束：
  - Ch3.F-XX.3「验证要点」必须与 Ch7「预期结果」列一一对应，不得超出 seeds 范围
  - 每个场景的「场景前置条件」必须能从该场景对应的 seeds 入口状态中归纳出来

**阶段三：生成 Ch1/2/4/5/6（摘要层）**

- 输入：Ch3 + Ch7（已完成）
- 这些章节是轻量收尾，对机器生成用例无影响，可单次合并生成
- Ch5 风险优先级：参考每个 Feature 的 seeds 行数 + 涉及角色数量推导

---

#### 生成顺序（自底向上，必须遵守）

> **核心原则**：Seeds 是事实，Ch3 是对事实的归纳，Ch1/2/4/5/6 是摘要。必须先有事实，再写归纳，不可逆序。
> 逆序（先写 Ch3 再生成 seeds）会导致 LLM 锚定于抽象场景数量，对 seeds 进行有损压缩。

**阶段一：生成第 7 章 Seeds（事实层）**

- 输入分流：
  - **xlsx/md 回归输入**：原始手工用例，按 Feature 分组并预过滤有效行
  - **BITS 回归输入**：`tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/bits_regression_input.json` 中的 `cases[]`，按 Feature 分组并预过滤有效行
- 目标：格式规范化。Seeds = 对原始用例的 1:1 结构化转换，不做有损合并
- 约束：seeds 行数必须 ≥ 有效用例数（遵守「八、九」两节规则）
- BITS 额外约束：只读取 `bits_regression_input.json` 的结构化字段，不直接读取原始 BITS JSON 或整条路径文本
- 大规模场景（> 50 条）：使用 `seed-gen-prompts` 批量生成（见「九」）

**阶段二：生成第 3 章 Feature Details（洞察层）**

- 输入：已完成的 Ch7 Seeds + 原始用例
- 目标：从 seeds 聚类归纳场景、从入口状态提炼前置条件、从预期结果汇总可观测信号
- 约束：
  - Ch3.F-XX.3「验证要点」必须与 Ch7「预期结果」列一一对应，不得超出 seeds 范围
  - Ch3.F-XX.3「来源用例」必须引用 Ch7 实际存在的 seed_id 范围
  - 每个场景的「场景前置条件」必须能从该场景对应的 seeds 入口状态中归纳出来

**阶段三：生成 Ch1/2/4/5/6（摘要层）**

- 输入：Ch3 + Ch7（已完成）
- 这些章节是轻量收尾，对机器生成用例无影响，可单次合并生成
- Ch5 风险优先级：参考每个 Feature 的 seeds 行数 + 涉及角色数量推导

---

#### 规格文档生成要求

**一、输入理解原则**

**回归模式（字段不可信）**：
1. **基于语义理解**：不得依赖表格字段名或 md 标题名判断内容归属，必须根据语义识别前置条件/步骤/断言。
2. **一句话多语义拆解**：一条描述中可能同时包含 action / system behavior / assertion / state，必须拆解并写为可验证表达。
3. **语义纠错**：修复不规范表达，补全缺失的主语、动作对象与结果对象。
4. **BITS 路径归一化**：若输入来自 BITS，需把路径节点、步骤节点、预期节点还原为“入口状态 / 核心操作 / 预期结果”三元组，再进入 seeds 生成，不得直接照抄整条路径文本。
5. **BITS 中间 JSON 优先**：若已存在 `bits_regression_input.json`，优先读取 `cases[].module / precond / steps / expected`，把它视为回归事实层输入；不要回退到原始 BITS 路径做二次猜测。

**测新模式（需求推导）**：
1. **需求完整性扫描**：逐段读取 PRD，识别每个功能点的边界（谁能用、在哪用、什么条件下用、用了之后什么效果）。
2. **隐含测试点挖掘**：PRD 未明确列出但可推导的测试点（如权限不足时的降级表现、空数据时的兜底展示、并发操作时的冲突处理）。
3. **需求歧义标注**：PRD 描述模糊或缺失的部分，在 spec 的对应功能点中标注 `⚠️ PRD 未明确，需人工确认：{具体问题}`。

**二、多模态规则（截图处理）**

当用例中包含截图时，必须执行：
1. **UI 语义补全**：将模糊描述补全为可定位 UI 描述。
   - 必须明确位置（顶部/列表/卡片/弹窗/页脚等）
   - 必须明确类型（按钮/输入框/tab/icon/开关/卡片等）
2. **断言增强**：将“页面正确展示/正常跳转/展示正常”等模糊表述转为可验证断言，例如：
   - 页面包含哪些 UI 元素（标题、按钮、输入框、提示文案）
   - 默认值/选中态/禁用态
   - 必要时补充布局关系或可见性规则
3. **截图用途识别**：判断截图属于 UI 展示（layout）/状态展示（state）/结果验证（assertion），并转为可观测信号。

**三、语义拆解规则（核心）**

1. 任何步骤描述必须能映射到：
   - action：用户行为
   - assertion：可验证校验点
   - state：上下文与状态（默认态/前置态/中间态/结果态）
2. 示例：
   - 输入：点击“+”按钮，跳转新增页面
   - 输出：
     - action：用户点击【列表区域右上角】的【新增按钮】
     - assertion：系统跳转到【新增页面】且展示【必填项提示/默认模板/关键按钮】
     - state：新增页面默认状态为【xx】

**四、角色主谓宾规则（Role-Action-Object Clarity）**

直播场景涉及多角色（主播、观众、管理员），每条描述必须明确标注**角色主语**和**观测端**，禁止省略主语的被动句式。

角色定义（参考 `scripts/live_common_inspector.md`）：
- **主播**：开启直播的人，拥有直播间
- **观众（看播）**：通过搜索/推荐进房观看直播的普通用户
- **管理员**：由主播授权的特殊观众，可管理直播间（屏蔽评论、设置竞猜等）

书写规则：

1. **用户路径**：每条步骤必须以角色开头 → `[角色] + [动作] + [对象]`，系统响应以端侧标注 → `[角色]端 + [系统行为] + [内容]`
   - ❌ `点击 Pin → 展示 Pin 卡` （谁点的？谁看到 Pin 卡？）
   - ✅ `主播点击 Pin 按钮 → 主播端/观众端/管理员端展示 Pin 卡`

2. **验证要点**：每条断言必须标注**观测端**（谁的屏幕上看到什么）
   - ❌ `展示积分发放动画`（哪个端？）
   - ✅ `观众端展示积分发放动画`
   - ❌ `中触强插`（谁的中触？）
   - ✅ `观众端中触发生强插`

3. **业务规则**：涉及多端差异时，必须逐端声明
   - ❌ `Pin 卡展示 30s 倒计时`
   - ✅ `主播端/管理员端 Pin 卡展示 30s 倒计时；观众端 Pin 卡展示 Join + X 按钮`

4. **多端同一行为**：当多个角色表现一致时，用 `主播端 + 管理员端` 或 `所有端` 显式合并，不可省略
   - ✅ `主播端 + 管理员端 + 观众端均展示竞猜中触`

**五、抽象与归并规则（非常关键）**

1. **去具体化但可定位**：不保留偶发或版本相关的具体按钮文案（如“+ New”），改写为抽象名（新增入口/编辑入口/确认按钮），同时保留定位信息（区域 + 控件类型）。
2. **合并同类用例**：多个入口或同类操作合并为一个功能点，并在“边界/异常”章节覆盖差异与特殊分支。
3. **提炼测试维度**：按实际业务提炼并覆盖关键维度，例如：
   - 入口一致性
   - 输入限制与校验
   - 状态流转
   - UI 展示与可用性
   - 权限与可见性
   - 失败与恢复

**六、场景划分规则（Scenario Derivation）**

> 在自底向上流程中，场景边界由**已生成的 Seeds** 归纳得出，而不是从模块路径直接映射。模块路径仅作为 Feature 分组的初始依据。

**Feature 划分（阶段一之前，用于分组原始用例）**：

- Feature 对应模块路径的第 1~2 层，例如 `游戏竞猜/主播竞猜pin` 整体归为一个 Feature（F-07）。
- 分组后各 Feature 独立生成 Seeds。

**Scenario 划分（阶段二，从 Seeds 聚类归纳）**：

生成 Ch3.F-XX.3 时，对该 Feature 的所有 seeds 按「入口状态」做聚类，归纳出场景边界：

1. **入口状态相同或相似的 seeds 归为同一场景**：入口状态的关键业务实体相同（如同为"竞猜进行中"），归入同一场景。
2. **入口状态有本质差异的 seeds 单独成一个场景**：例如"Pin 卡展示中"与"已在进行中面板"，前置不同，必须拆开。
3. **场景命名**：取该组 seeds 入口状态的共性关键词，抽象为动词短语或名词短语，例如"Pin 卡展示与交互"、"发起竞猜"。
4. **粒度控制**：一个场景覆盖的 seeds 建议不超过 15 行；一个 Feature 建议 2~8 个场景。超过时按核心操作类型进一步拆分。
5. **场景前置条件**：直接取该组 seeds 中重复出现的入口状态关键词，去重后写入「场景前置条件」。
6. **验证要点**：取该组 seeds 的「预期结果」列，去重合并后写入「验证要点」——**不允许写 seeds 中没有出现的断言**。

**七、文档结构强约束**

1. **不允许遗漏章节**：必须输出 1~7 全部章节（含第 7 章「原始用例分组」）。
2. **功能点编号规范**：在"3. 功能点详情"中使用 3.F-XX 编号，每个功能点包含 3.F-XX.1 ~ 3.F-XX.5 全部子章节。
3. **场景层结构**：3.F-XX.3 测试场景（Test Scenarios）下，每个场景使用 `##### S-x 场景名称` 格式，包含 5 个加粗字段：场景前置条件、用户路径、业务规则、验证要点、可观测信号。每个场景是自包含的测试单元，读者无需跨章节即可理解该场景的完整测试要求。
4. **不可逐条复述原始用例**：场景内容必须是抽象归并后的 Feature 规格，原始用例仅在第 7 章 seeds 中保留结构化事实，Ch3 不写 case_id / 行号等回溯字段。
5. **断言必须可验证**：禁止"正常/正确/符合预期"等不可验证措辞，每个场景的验证要点必须是具体的可观测断言。
6. **UI 描述必须可定位**：必须明确位置、类型、必要时补充布局关系或可见性条件。
7. **前置条件两级分离**：
   - **Feature 级前置条件**（3.F-XX.2）：所有场景共用的条件，包含两个加粗子标题：
     - **环境与权限前置（Environment & Access Prerequisites）**：本文档功能点无法改变或产出的外部条件。**须沿功能依赖链向上完整继承**——确保每个功能点的环境前置自包含、无需回溯依赖链。
     - **功能依赖前置（Cross-Feature Dependencies）**：依赖本文档内其他功能点的状态或操作结果，须标注编号（→ F-XX）。功能依赖前置**必须附带「前置实现配方」**，配方由该 Feature 所有 seeds 共同依赖的入口状态步骤归纳而来。
     - 若某个功能点只有其中一类前置条件，另一类写"无"即可，不得省略子标题。
   - **Scenario 级前置条件**（场景前置条件）：在 Feature 级基础上，本场景额外需要的入口状态或操作前提。直接取本场景 seeds 的入口状态关键词归纳，不重复 Feature 级已声明的条件。
8. **Ch3 与 Ch7 一致性约束（自底向上核心规则）**：
   - Ch3.F-XX.3「验证要点」中的每条断言，必须能在 Ch7 对应 Feature 的 seeds「预期结果」列中找到来源，**禁止在 Ch3 中引入 seeds 未覆盖的断言**。
   - Ch3.F-XX.2「前置实现配方」中的步骤，必须能覆盖 Ch7 中该 Feature 所有 seeds 的入口状态所需的前置操作。
   - Ch3.F-XX.3「来源用例」引用的 seed_id 范围，必须与 Ch7 中实际存在的 seed_id 一致。
9. **实验 / 配置 / 开关前置条件识别（Experiment & Config Detection）**：

   扫描原始用例全部字段（标题、前置条件、步骤、预期结果、备注等）时，必须识别以下三类外部依赖信息，并将其写入对应 Feature 或 Scenario 的前置条件中。

   **识别关键词**：

   | 类别 | 触发关键词（不区分大小写） | 典型线索 |
   |------|------------------------|---------|
   | 实验（Experiment） | `Libra`、`libra`、实验组、对照组、实验、AB 实验、AB test、flight、bucket | Libra 平台 URL（含 `libra` 域名或 `/flight/` 路径）、实验分组描述 |
   | 配置（Configuration） | 配置、config、后台配置、配置项、配置中心、运营配置 | 后台配置路径、配置管理平台 URL |
   | 开关（Feature Toggle） | 开关、feature flag、feature toggle、toggle、灰度、功能开关、灰度开关 | 开关名称、灰度比例描述 |
   | 地区（Region） | `US`、美国、`us store region`、`EU`、欧盟、欧洲；**账号名里包含 `us` / `eu` 字样** | 用例要求特定地区环境、或指定了美区/欧区账号 |

   **地区（US / EU）专项处理**：当命中地区类关键词或账号名含 `us`/`eu` 时，必须在对应 seed 的「入口状态（前置）」列写明地区要求（如「需 US 地区环境（ttmock region=US）」），以便 `ui-xmind-case-gen` 据此自动加 `ttmock_preset region=US/EU` 前置并给用例根节点打 `US` / `EU` 标签。

   **处理规则**：

   （a）**信息明确**——用例中给出了具体的 URL、文档链接或配置路径，按以下格式写入前置条件：
   - `⚠️ 需要添加实验条件：{URL}`
     例：`⚠️ 需要添加实验条件：https://libra-sg.tiktok-row.net/libra/flight/70954079/edit`
   - `⚠️ 需要添加配置条件：{配置路径或文档链接}`
   - `⚠️ 需要添加开关条件：{开关名称或文档链接}`

   **Libra group_id（生成下游 xmind/md 前）**：**仅当用户提供了 Libra 链接时**启用。URL 只能抽出 `libra_id`/`region`，无法 SSO 自动拉 version 表；缺 `group_id` 时分别问实验组与对照组（可贴版本表/截图），正向→实验组、对照/反向→对照组。无链接则不主动套成对 group 追问。规范见 [`../references/libra-group-assignment.md`](../references/libra-group-assignment.md)。

   （b）**信息不明确**——用例中出现了关键词（如"实验组""需要打开XX开关""后台配置为XX"），但**未提供**具体 URL、文档链接或可定位的配置路径，按以下格式写入前置条件并标记待人工补充：
   - `⚠️ 需要添加实验条件，但信息未给明确，请人工补充`
   - `⚠️ 需要添加配置条件，但信息未给明确，请人工补充`
   - `⚠️ 需要添加开关条件，但信息未给明确，请人工补充`

   **写入位置**：
   - 若该条件影响 Feature 下所有场景 → 写入 3.F-XX.2「**环境与权限前置**」
   - 若仅部分场景涉及 → 写入对应场景的「**场景前置条件**」
   - Ch7 Seeds：在涉及实验/配置/开关的 seeds 的「入口状态（前置）」列中同样注明该条件，确保 seed 自包含

**八、第 7 章 Raw Case Seeds 写作规则（最关键）**

> 以下规则对**回归模式**和**测新模式**均适用。区别仅在于 seed 来源：回归模式从手工用例转换，测新模式从 PRD 推导。

第 7 章使用**结构化表格**，每行对应一条独立可执行的 AutoGLM 用例。表格字段：

| 字段 | 含义 | 要求 |
|------|------|------|
| Seed ID | 唯一标识，格式 F01-S01 | 按功能点顺序编号 |
| 入口状态（前置） | 执行核心操作前，被测对象/系统所处的具体状态 | 必须精确到状态值，如"竞猜进行中，观众**未作答**"，而非笼统的"竞猜进行中" |
| 核心操作 | 用户执行的单个动作 | 动词短语，如"点击 Yes 按钮" |
| 预期结果 | 可直接观测的 UI / 系统反馈 | 具体文案或状态变化，禁止"正常/正确"等模糊表述 |

**⚠️ 自动化执行约束**：每条 seed 对应的测试用例由 AutoGLM 独立执行，**每次执行从 App 冷启动开始**，不存在跨用例的状态继承。因此：
- `入口状态` 中涉及的所有功能依赖（如"竞猜进行中"）必须能通过该 Feature 的「功能依赖前置 → 前置实现配方」中定义的业务步骤从零构建
- 不可假设"上一条用例已完成某操作"

**拆行规则（以下情况必须各占一行）**：

1. **枚举值拆行（互斥状态路径）**：原始用例中通过 `/`、`、`、`或`、`Yes/No`、`开/关` 等列举了多个输入值 → 每个值各占一行，且**入口状态保持相同**（证明它们是从同一起点出发的互斥路径）。

   ```
   ❌ 错误（合并枚举值）：一条 seed 写"提交答案 Yes/No → 显示已作答"

   ✅ 正确（每个枚举值独立成行，入口状态相同）：
   | F01-S01 | 竞猜进行中，观众未作答 | 点击"Yes" | 显示"已作答"提示 |
   | F01-S02 | 竞猜进行中，观众未作答 | 点击"No"  | 显示"已作答"提示 |
   ```

2. **多断言拆行**：一条原始用例通过分号、"且"等连接了多个可观测结论，且各结论涉及**不同的系统行为或状态变更** → 每个结论单独一行。

   ```
   ❌ 错误：结算完成后观众已投注 — 展示积分动画；中触强插5s；展示最终答案

   ✅ 正确：
   | F03-S01 | 竞猜已结束，观众已投注 | 等待结算 | 展示积分发放动画 |
   | F03-S02 | 竞猜已结束，观众已投注 | 等待结算 | 中触强插5s后缩小 |
   | F03-S03 | 竞猜已结束，观众已投注 | 等待结算 | 展示最终答案+结算积分 |
   ```

   **例外——同屏静态元素断言不拆行**：当多条断言均为同一页面/同一屏幕下的**静态 UI 元素存在性检查**（如"页面展示选项 A""页面展示选项 B"），且断言之间**不涉及任何用户操作或状态变更**时，应合并为一条 seed，预期结果列使用「；」连接各断言点。

   判断标准：
   - ✅ 可合并：入口状态相同 + 核心操作为"查看/检查"类（无副作用）+ 所有断言均为"XX 元素存在/展示"
   - ❌ 不可合并：断言涉及不同的系统反馈（动画 vs 文案 vs 状态变更）、涉及时序关系、涉及不同触发条件

   ```
   ❌ 过度拆分（同一页面的静态元素检查不应拆成 N 条）：
   | F01-S01 | 进入设置页 | 查看设置页 | 展示「选项A」 |
   | F01-S02 | 进入设置页 | 查看设置页 | 展示「选项B」 |
   | F01-S03 | 进入设置页 | 查看设置页 | 展示「选项C」 |

   ✅ 正确（合并为一条 seed，多断言用分号连接）：
   | F01-S01 | 进入设置页 | 查看设置页选项 | 展示「选项A」；展示「选项B」；展示「选项C」 |
   ```

3. **多角色拆行**：一条用例涉及多个角色（如"主播、管理员"）执行同一操作 → 每个角色独立成行，入口状态中注明角色身份。

   ```
   ❌ 错误：打开竞猜面板Pin按钮展示30s倒计时（主播、管理员）

   ✅ 正确：
   | F02-S01 | 竞猜进行中，主播身份登录    | 点击 Pin 卡 | Pin 按钮展示30s倒计时 |
   | F02-S02 | 竞猜进行中，管理员身份登录  | 点击 Pin 卡 | Pin 按钮展示30s倒计时 |
   ```

4. **多条件叉积穷举**：当一个功能场景受多个独立状态变量控制（如「时间段：5min内/5min后」×「投注状态：有投注/无投注」），必须在表格中列出**所有组合**，不允许只写部分分支。

   检测方法：找出原始用例中该功能涉及的所有状态维度，做叉积展开：
   - 时间维度 × 投注状态 = 4 行（5min内+有投注、5min内+无投注、5min后+有投注、5min后+无投注）
   - 答案维度 × 角色维度 = Yes主播、No主播、Invalid主播、Yes观众、No观众、Invalid观众…

   ```
   ❌ 错误（只写了有用户上榜的场景）：
   | F05-S10 | 结算完成5min后，有用户上榜 | 查看中触 | 展示上榜用户列表 |

   ✅ 正确（穷举无用户上榜的子场景）：
   | F05-S10 | 结算完成5min后，有用户上榜 | 查看中触 | 展示上榜用户列表 |
   | F05-S11 | 结算完成5min后，无用户上榜，用户已投注 | 查看中触 | 保持展示上一次结果，有积分加减 |
   | F05-S12 | 结算完成5min后，无用户上榜，用户未投注 | 查看中触 | 保持展示上一次结果，仅结果无积分 |
   ```

**入口状态书写要点**：
- 两行入口状态相同、操作不同 → ui-xmind-case-gen 识别为互斥路径，各自建立独立用例
- 两行入口状态和操作均相同、结论不同 → 若属同屏静态元素检查（见规则 2 例外），应在 seed 层直接合并为一条，不拆行；若属状态变更型断言（自然顺序链路），ui-xmind-case-gen 可合并（≤3 个断言）
- 入口状态不同 → 必然是独立用例，无需额外标注

**八（补）、测新模式 Seeds 推导规则**

> 仅当进入**测新模式**时参考此节。回归模式跳过。

测新模式没有手工用例作为输入，Seeds 需要从 PRD 需求描述中系统化推导。推导流程：

1. **Feature 划分**：
   - 按 PRD 的功能模块 / 章节结构划分 Feature（F-01, F-02, ...）
   - 每个 Feature 对应 PRD 中一个独立的功能单元

2. **操作路径提取**（每个 Feature 内）：
   - 从 PRD 的 UI 交互描述中提取所有用户可执行的操作路径
   - 识别每条路径的入口页面、触发动作、预期系统响应
   - 包含正向路径（happy path）和 PRD 明确提及的异常路径

3. **状态变量识别**：
   - 从业务规则中提取所有影响行为的状态维度
   - 常见维度：角色（主播/观众/管理员）、权限等级、功能开关状态、数据状态（有/无/满/空）、时间条件
   - 每个维度列出所有可能的取值

4. **叉积展开生成 Seeds**：
   - 对操作路径 × 状态变量组合做叉积，生成 seed 候选集
   - 每个组合对应一行 seed，入口状态精确到所有状态变量的取值
   - 预期结果从 PRD 的功能描述中推导，必须是可观测的 UI / 系统反馈

5. **边界补充**：
   - 从 PRD 的限制/异常/兼容性描述中补充边界 seed
   - 包括但不限于：空数据、超限值、非法输入、网络异常、并发操作

6. **覆盖率自检**：
   - 对照 PRD 功能描述，确认每个功能点至少有 3 条 seeds（正向 + 边界 + 异常）
   - 涉及多角色的功能，每个角色视角至少有 1 条 seed
   - 涉及状态流转的功能，每个关键状态转换至少有 1 条 seed

**测新模式下的数量指导**（非强制契约，但作为质量下限参考）：
- 简单功能点（单入口、无状态变量）：3~5 条 seeds
- 中等功能点（2~3 个状态维度）：8~15 条 seeds
- 复杂功能点（多角色 × 多状态 × 多入口）：15~30 条 seeds

**九、大规模用例时第 7 章生成流程（> 50 条有效用例时必须遵守，仅回归模式）**

当某个 Feature 的有效用例数 **> 50 条**（或整体有效用例 **> 200 条**）时，禁止让单个 LLM 调用一次性处理全部用例；必须按以下 4 步流程执行，否则极易产生「过度压缩」（seeds 行数远少于用例数）。

> **工具路径**：所有命令均位于 `.cursor/skills/ui-xmind-case-gen/script.py`，在该目录下执行。

---

**Step 0：预过滤有效用例（P0 — 必须执行）**

从 xlsx/md 原始用例中剔除**层级节点行**（标题和预期结果均为空的行），只保留有标题且有预期结果的行。

**优先级过滤**：如果调用者指定了优先级过滤条件，在此步骤中额外按「优先级」列进行筛选：

| 调用者指令 | 过滤逻辑 | 保留的优先级 |
|-----------|---------|------------|
| "只要P0" / "P0" | 严格匹配 | P0 |
| "P1+" | 阈值过滤 | P0, P1 |
| "P2+" | 阈值过滤 | P0, P1, P2 |
| 未指定 | 不过滤 | 全部（P0~P4 及无标记行） |

过滤规则：
- 优先级列名模糊匹配：`优先级` / `Priority` / `priority` / `用例级别`（不区分大小写）
- 优先级值标准化：去除空格后不区分大小写匹配，`p0` = `P0`
- 若表格中不存在优先级列，则视为"未指定"，保留全部用例并在日志中提示
- 过滤后须在输出日志中记录：`优先级过滤：{条件}，过滤前 {M} 条 → 过滤后 {N} 条`

将有效用例按 Feature 分组，写入 `tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_{feature_name}.json`，格式如下：

```json
[
  {
    "id": "row_42",
    "module": "功能模块路径",
    "title": "用例标题",
    "precond": "前置条件",
    "steps": "操作步骤",
    "expected": "预期结果",
    "priority": "P1"
  }
]
```

预过滤后记录每个 Feature 的有效用例数 N，这是后续「数量契约」的基准值。

---

**Step 1：用例分类（优化 4）**

对每个 Feature 的有效用例文件执行分类，识别「机械型」和「语义型」用例：

```bash
python3 script.py seed-classify /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_F01.json
```

输出示例：
```json
{
  "total": 259,
  "mechanical": 242,
  "semantic": 17,
  "semantic_ratio": 0.066,
  "llm_load_reduction": "93%"
}
```

- **机械型**（mechanical）：断言清晰可观测，在分批 Prompt 中标注 `[M]`，LLM 可直接转化，无需润色。
- **语义型**（semantic）：断言含模糊表达（"正常展示"等），在分批 Prompt 中标注 `[S]`，LLM 需将其改写为可观测断言。

---

**Step 2：分批生成 Prompt（优化 2 — Map 阶段）**

将有效用例按模块子树分组后切分为批次，每批生成一个独立 Prompt 文件：

```bash
python3 script.py seed-gen-prompts /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_F01.json F-01 \
    --feature-name "语聊房迁移到triones" \
    --batch-size 20 \
    -o /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/seed_prompts/
```

每个 Prompt 文件内嵌：
- 当前批次用例数 N 及「seeds ≥ N」的**数量契约**
- 每条用例的 `[M]`/`[S]` 类型标注
- 完整的拆行规则（枚举值/多断言/多角色/叉积）
- 要求 LLM 在表格后写**自检行**（「本批次生成 X 行，覆盖用例 N/N 条」）

对每批 Prompt 独立调用 LLM，收集所有批次的 Markdown 表格输出，按批次合并到对应 Feature 的第 7 章。

---

**Step 3：Coverage Bitmap 验证（优化 3 — Reduce 阶段）**

将所有批次合并写入 spec 第 7 章后，执行覆盖率检查：

```bash
python3 script.py seed-coverage spec.md \
    --cases F-01=/abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_F01.json F-02=/abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_F02.json
```

输出示例：
```json
{
  "overall": { "total_seeds": 767, "total_cases": 755, "status": "ok" },
  "features": {
    "F-01": { "total_seeds": 265, "total_cases": 259, "gap": 0, "status": "ok" }
  }
}
```

- **status=ok**：seeds 数 ≥ cases 数，覆盖率达标，可继续。
- **status=gap**：seeds 数 < cases 数，存在遗漏。此时对缺口 Feature 重新执行 Step 2，专门针对未覆盖的用例批次补充生成，直到 gap=0。

---

**数量契约原则（贯穿全流程）**

每次向 LLM 提交分批 Prompt 时，必须遵守以下契约：

| 约束 | 说明 |
|------|------|
| 下界契约 | 每批 N 条用例 → seeds ≥ N 行，禁止合并，禁止省略 |
| 自检要求 | LLM 必须在输出后写「生成 X 行，覆盖 N/N 条」 |
| 覆盖检查 | 合并后 seed-coverage 报告 status=ok 方可提交 |
| 最大批次 | 每批 ≤ 20 条用例（--batch-size 20）；超大功能自动多批 |

---

**十、输出质量检查**
**九、大规模用例时第 7 章生成流程（> 50 条有效用例时必须遵守）**

当某个 Feature 的有效用例数 **> 50 条**（或整体有效用例 **> 200 条**）时，禁止让单个 LLM 调用一次性处理全部用例；必须按以下 4 步流程执行，否则极易产生「过度压缩」（seeds 行数远少于用例数）。

> **工具路径**：所有命令均位于 `.cursor/skills/ui-xmind-case-gen/script.py`，在该目录下执行。

---

**Step 0：预过滤有效用例（P0 — 必须执行）**

从 xlsx/md 原始用例中剔除**层级节点行**（标题和预期结果均为空的行），只保留有标题且有预期结果的行。

**优先级过滤**：如果调用者指定了优先级过滤条件，在此步骤中额外按「优先级」列进行筛选：

| 调用者指令 | 过滤逻辑 | 保留的优先级 |
|-----------|---------|------------|
| "只要P0" / "P0" | 严格匹配 | P0 |
| "P1+" | 阈值过滤 | P0, P1 |
| "P2+" | 阈值过滤 | P0, P1, P2 |
| 未指定 | 不过滤 | 全部（P0~P4 及无标记行） |

过滤规则：
- 优先级列名模糊匹配：`优先级` / `Priority` / `priority` / `用例级别`（不区分大小写）
- 优先级值标准化：去除空格后不区分大小写匹配，`p0` = `P0`
- 若表格中不存在优先级列，则视为"未指定"，保留全部用例并在日志中提示
- 过滤后须在输出日志中记录：`优先级过滤：{条件}，过滤前 {M} 条 → 过滤后 {N} 条`

将有效用例按 Feature 分组，写入 `tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_{feature_name}.json`，格式如下：

```json
[
  {
    "id": "row_42",
    "module": "功能模块路径",
    "title": "用例标题",
    "precond": "前置条件",
    "steps": "操作步骤",
    "expected": "预期结果",
    "priority": "P1"
  }
]
```

预过滤后记录每个 Feature 的有效用例数 N，这是后续「数量契约」的基准值。

---

**Step 1：用例分类（优化 4）**

对每个 Feature 的有效用例文件执行分类，识别「机械型」和「语义型」用例：

```bash
python3 script.py seed-classify /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_F01.json
```

输出示例：
```json
{
  "total": 259,
  "mechanical": 242,
  "semantic": 17,
  "semantic_ratio": 0.066,
  "llm_load_reduction": "93%"
}
```

- **机械型**（mechanical）：断言清晰可观测，在分批 Prompt 中标注 `[M]`，LLM 可直接转化，无需润色。
- **语义型**（semantic）：断言含模糊表达（"正常展示"等），在分批 Prompt 中标注 `[S]`，LLM 需将其改写为可观测断言。

---

**Step 2：分批生成 Prompt（优化 2 — Map 阶段）**

将有效用例按模块子树分组后切分为批次，每批生成一个独立 Prompt 文件：

```bash
python3 script.py seed-gen-prompts /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_F01.json F-01 \
    --feature-name "语聊房迁移到triones" \
    --batch-size 20 \
    -o /abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/seed_prompts/
```

每个 Prompt 文件内嵌：
- 当前批次用例数 N 及「seeds ≥ N」的**数量契约**
- 每条用例的 `[M]`/`[S]` 类型标注
- 完整的拆行规则（枚举值/多断言/多角色/叉积）
- 要求 LLM 在表格后写**自检行**（「本批次生成 X 行，覆盖用例 N/N 条」）

对每批 Prompt 独立调用 LLM，收集所有批次的 Markdown 表格输出，按批次合并到对应 Feature 的第 7 章。

---

**Step 3：Coverage Bitmap 验证（优化 3 — Reduce 阶段）**

将所有批次合并写入 spec 第 7 章后，执行覆盖率检查：

```bash
python3 script.py seed-coverage spec.md \
    --cases F-01=/abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_F01.json F-02=/abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/valid_F02.json
```

输出示例：
```json
{
  "overall": { "total_seeds": 767, "total_cases": 755, "status": "ok" },
  "features": {
    "F-01": { "total_seeds": 265, "total_cases": 259, "gap": 0, "status": "ok" }
  }
}
```

- **status=ok**：seeds 数 ≥ cases 数，覆盖率达标，可继续。
- **status=gap**：seeds 数 < cases 数，存在遗漏。此时对缺口 Feature 重新执行 Step 2，专门针对未覆盖的用例批次补充生成，直到 gap=0。

---

**数量契约原则（贯穿全流程）**

每次向 LLM 提交分批 Prompt 时，必须遵守以下契约：

| 约束 | 说明 |
|------|------|
| 下界契约 | 每批 N 条用例 → seeds ≥ N 行，禁止合并，禁止省略 |
| 自检要求 | LLM 必须在输出后写「生成 X 行，覆盖 N/N 条」 |
| 覆盖检查 | 合并后 seed-coverage 报告 status=ok 方可提交 |
| 最大批次 | 每批 ≤ 20 条用例（--batch-size 20）；超大功能自动多批 |

---

**十、输出质量检查**

生成规格文档后，进行以下检查：

**文档结构**：
- [ ] 1~7 章节齐全（含第 7 章 Raw Case Seeds）
- [ ] 每个功能点包含 3.F-XX.1 ~ 3.F-XX.5 全部子章节
- [ ] 每个 3.F-XX.3 测试场景下至少有 1 个 `##### S-x` 场景块
- [ ] 每个场景块包含 5 个加粗字段（场景前置条件、用户路径、业务规则、验证要点、可观测信号）

**前置条件**：
- [ ] 每个 3.F-XX.2 前置条件均包含「环境与权限前置」和「功能依赖前置」两个子标题
- [ ] 环境与权限前置已沿功能依赖链向上完整继承，每个功能点的环境前置自包含
- [ ] 功能依赖前置中已标注所依赖的功能点编号（→ F-XX）
- [ ] 每条功能依赖均附带「前置实现配方」，使用纯业务语言描述从零达到该状态的可执行步骤（无工具名/函数名/API 名）
- [ ] 场景前置条件不重复 Feature 级已声明的条件，只声明额外的入口状态
- [ ] 原始用例中涉及实验（Libra / AB 实验 / 实验组 / 对照组）、配置、开关的信息已识别并写入前置条件，信息明确的附带 URL/路径，信息不明确的标记 `⚠️ ... 请人工补充`

**内容质量**：
- [ ] 不存在逐条复述原始用例（场景内容已归并抽象）
- [ ] 场景的验证要点全部为具体的可验证断言，无"正常/正确/符合预期"
- [ ] 截图信息已转为文字，UI 定位与断言已增强
- [ ] 每个场景的来源用例（case_id）完整覆盖该场景对应的原始用例
- [ ] 风险等级与优先级建议有明确依据
- [ ] 变更敏感点可指导回归设计

**角色主谓宾**：
- [ ] 用户路径每条步骤均以角色开头（主播/观众/管理员），系统响应标注观测端
- [ ] 验证要点每条断言均标注观测端（XX端展示/不展示），无省略主语的被动句
- [ ] 多端差异场景逐端声明，不存在"展示XX"但未说明哪个端的表述

**第 7 章 Raw Case Seeds**：
- [ ] 每个 F-XX 小节使用表格格式，包含 Seed ID / 入口状态 / 核心操作 / 预期结果 四列
- [ ] 枚举值（Yes/No、开/关等）已各自拆行，入口状态相同
- [ ] 多条件场景已做叉积穷举，不存在遗漏的组合分支
- [ ] 状态变更型多断言未合并在同一行，无多角色合并在同一行
- [ ] 同屏静态元素检查型断言（入口状态和操作相同、断言均为元素存在性检查）已合并为一条 seed，预期结果用分号连接

**Ch3 ↔ Ch7 一致性（自底向上核心检查）**：
- [ ] Ch3 所有场景的「验证要点」均能在 Ch7 seeds「预期结果」中找到对应，无凭空新增的断言
- [ ] Ch3「来源用例」引用的 seed_id 与 Ch7 实际存在的 seed_id 范围一致
- [ ] Ch3.F-XX.2「前置实现配方」覆盖了该 Feature 所有 seeds 的入口状态所需前置操作
- [ ] Ch3 的场景数量与 seeds 按入口状态聚类的分组数匹配（偏差 > 2 需复查）
**测新模式额外检查**（仅测新模式）：
- [ ] 每个 PRD 功能点至少有 3 条 seeds（正向 + 边界 + 异常）
- [ ] 涉及多角色的功能，每个角色视角至少有 1 条 seed
- [ ] PRD 中明确提到的业务规则（输入限制、状态流转、权限控制）均有对应 seed 覆盖
- [ ] PRD 描述模糊或缺失的部分已在 spec 中标注 `⚠️ PRD 未明确，需人工确认`

#### 输出要求

生成的 spec 文档统一存放在仓库根目录下：

`<repo_root>/tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_spec.md`

其中：

- `{vc}`：业务大类 / vertical category
- `{module}`：本次需求或模块名
- `{ui_path}`：当前 spec 的文件 stem，建议使用 `{模块或需求名称}`，不要再额外带 `_spec`

若目录不存在则自动创建。凡是规整 JSON、Prompt、coverage 输入、临时验证脚本，一律写入 `tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/`。
