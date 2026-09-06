---
name: testcase-normalize
description: 把一份自然语言写就的测试用例 Markdown 文件，原子化地规范化为标准结构化用例格式（Precondition 标签 {mock,navigate,assume}，Assert 标签 {text,state,visual,data,defer}）。用户提供一个 md 文件（含 1 条或多条用例），本 skill 只负责产出规范化结果文本，不做执行、不调 CLI、不改原始文件。当用户请求"把 xx 测试用例 md 规范化 / 转标准格式 / normalize testcase / 生成 normalized testcase"时调用。
---

# testcase-normalize

## 定位

本 skill 是 **用例规范化**原子能力，独立提供，不依赖任何上游 skill。

- 输入：**一份自然语言 Markdown 文件**（可能包含 1 条或多条测试用例，格式任意）
- 输出：**符合标准格式的规范化 Markdown 文本**（多用例以 `---` 分隔）
- 副作用：**无**（除非调用方明确给出目标路径；默认只返回文本内容）

## 触发条件

以下任意一种意图都应调用本 skill：

- "帮我把这个测试用例 md 转成标准格式"
- "normalize this testcase file"
- "生成 normalized testcase"
- "把自然语言 case 规范化后给我"

**不应调用**的场景：

- 用户要求执行测试用例（本 skill 只做规范化，不执行）
- 用户要求解析 JSON / schema 校验（走 CLI `validate` 命令）
- 用户只要求阅读用例内容或做摘要

## 绝对规则

### 1. 源文件保护

- **禁止**修改、重写、删除输入源文件
- 源文件是唯一数据源（single source of truth）
- 规范化输出必须忠实于源语义，不得新增源文件中不存在的测试步骤
- 不得省略源文件中已有的任何用例或步骤
- 源文件中隐含但未显式写出的前置条件 / 全局断言，可根据上下文合理补充
- 断言文案中引号括起的精确文案（如 `"网络诊断"`）必须**原样保留**，不得改写措辞

### 2. 用例边界判定

源文件里"用例 1 / 用例 2 / 编号列表 / 分段描述"**不一定是多条独立用例**。先判定关系再决定合并或拆分：

#### 合并为一条用例的多个 Steps（有依赖）

判定信号：
- 后一条的操作对象是前一条操作的结果（例："点击按钮弹出对话框" → "点击对话框中的确认"）
- 后一条隐含"已在某页面 / 已显示某元素"作为前提
- 条目之间描述的是同一个用户操作流程的连续阶段

示例：源文件写了 "用例1: 打开设置页…"、"用例2: 点击按钮弹出对话框…"、"用例3: 点击确认关闭对话框…" → 这是**一条用例的 3 个 Step**，不是 3 条独立用例。

#### 输出为多条独立用例（无依赖）

判定信号：
- 各条目测试的是不同功能路径或不同场景
- 各条目可以独立执行，不依赖其他条目的结果状态
- 源文件用明确的分隔（标题 / 分组 / 独立编号体系）区分不同测试场景

### 3. 禁止跳过规范化

**无论源文件看起来多像标准格式，都必须逐行检查并输出。禁止直接复制源文件内容作为规范化结果。**

"看起来是标准格式"不等于"是标准格式"。源文件中可能存在细微的格式缺陷（如断言行缺少 `Assert:` 前缀、section 不完整等），只有逐行检查才能发现。

## 标准格式规范

每条用例输出必须严格符合以下结构：

```
> 一句话描述测试目标

- **Priority**: ...（如有）
- **Platform**: ...（如有）
- **Pkg**: ...（如有）

**Path**:
功能路径

**Context**:（如有）
- kind | 值

**Precondition**:
- label | 条件文本

**Setup**:（如有）
- 准备步骤

**Steps**:
1. 操作描述
    - Assert: category | 预期结果

**Assert**:
- category | 全局断言

**Notes**:（如有）
- 补充说明
```

**多条用例之间用 `---` 分隔**（独占一行，前后各一个空行）。

### 强制格式规则

- 第一行必须以 `>` 开头，写测试目标
- `**Path**:` 必须有，从源文件中提取或推断功能路径
- `**Precondition**:` 必须有，至少一条，格式 `- label | 条件文本`
- `**Steps**:` 必须有，每步用数字编号。Assert 行缩进写在步骤下方，格式 `- Assert: category | 预期结果`
- `**Assert**:` 必须有，至少一条全局断言
- Precondition label 允许值：`mock`、`navigate`、`assume`
- Assert category 允许值：`text`、`state`、`visual`、`data`、`defer`

## 标签判定协议

### Precondition label 判定（按顺序，首个命中即确定）

每条 Precondition 必须标注一个 label。如果源文件已写标签前缀，直接使用；如果未写，按决策树判定：

1. 要通过改变 App 内/环境的**配置型状态**（配置/实验/开关/泳道/账号登录态/业务数据/网络 mock/设备配置）来满足？ → `mock`
2. 要通过**用户操作**让 App 到达指定页面/入口/状态？ → `navigate`
3. 以上都不是（纯声明性假设/前提）？ → `assume`

说明：`mock` 是**文案标签**（环境/账号/数据/设备配置类前置）。转 Bits（`$ui-md-case-upload`）时按诉求选真实工具：PPE→`环境名称`；Libra→`libra实验`；地区/语言/AB KV→`ttmock_preset`。凡写 `ab_settings` / `ab_settings_live`，**必须先**用
`ui-xmind-case-gen/script.py check-json-object` 校验为 JSON **对象**。**仅当有 Libra 链接**且缺 `group_id` 时分别问实验组与对照组并按 case 极性分配（正向→实验组、对照/反向→对照组），见 [`../../references/libra-group-assignment.md`](../../references/libra-group-assignment.md)。
`python skills/tt-nova-ui/ui-xmind-case-gen/script.py check-json-object --param ab_settings '<值>'`
确认是 JSON **对象** string（如 `{"72192329":"1"}`）；禁止数组 / `flight:` / 非 JSON；不要把一切都塞进 ttmock。

### Assert category 判定（按顺序，首个命中即确定）

每条 Assert 必须标注一个 category。如果源文件已写标签前缀，直接使用；如果未写，按决策树判定：

1. 可通过文本匹配确定性验证（界面上出现/包含某段具体文字）？ → `text`
2. 描述的是 App/页面/元素的结构化状态（跳转/前台/可点击/启用/选中）？ → `state`
3. 描述的是视觉外观（颜色/样式/布局/动画/对齐/视觉差异）？ → `visual`
4. 描述的是客户端的数据行为（请求/埋点/缓存/上报），当前工具链暂无法自动验证？ → `data`（等价于 `defer`，trace 中标记为未验证）
5. 其余当前工具链无法自动验证？ → `defer`

### 标签自检

写出规范化结果前，逐条复核：

- 每条标记为 `text` 的断言，能明确指出要匹配的文本内容吗？如果不能 → 改为 `visual` 或 `state`
- 每条标记为 `state` 的断言，能映射到一个可查询的结构化属性吗？如果不能 → 改为 `visual`
- 每条标记为 `assume` 的前置条件，确认**不包含**"切换 / 设置 / 修改 / 开启 / 关闭"等动作动词（若包含，应改为 `mock` 或 `navigate`）

## 禁止事项

- 不要把 `- **Pkg**: xxx` 这样的全局元数据行当成独立用例
- **不要把有顺序依赖的多个条目拆成多条独立用例**（参见"用例边界判定"）
- 不要把一条用例内的多个步骤拆成多条独立用例
- 不要重命名或改写断言中引号括起的精确文案
- 不要在输出中添加 markdown 代码块包裹（除非调用方明确要求）
- **不要直接复制源文件**。即使源文件看起来已经是标准格式，也必须逐行检查后输出

## 输出前自检

**逐条、逐行**检查：

1. 每条用例是否以 `>` 开头？
2. 每条用例是否有 `**Path**:` section？
3. 每条用例是否有 `**Precondition**:`（至少一条）？
4. 每条用例是否有 `**Steps**:`（数字编号）？
5. **Steps 下的每一行断言是否都有 `- Assert: category | text` 格式？** 如果源文件中某行写了 `- category | text` 但缺少 `Assert:` 前缀，必须补上
6. 每条用例是否有 `**Assert**:`（至少一条）？
7. 多条用例之间是否用 `---` 分隔？
8. 全局元数据（`**Pkg**:` 等）是否正确继承到了每条用例？
9. 所有 Precondition label 是否属于 `{mock, navigate, assume}`？
10. 所有 Assert category 是否属于 `{text, state, visual, data, defer}`？

## 工作流程

1. **接收输入**
   - 必需：源 md 文件的绝对路径，或直接传入的 md 文本
   - 可选：输出目标路径（若不提供，默认只返回文本内容，不写盘）

2. **阅读源文件**
   - 完整读取源文件
   - 识别全部候选用例及全局元数据

3. **逐条、逐行规范化**
   - 对每条用例，按"标准格式规范"与"标签判定协议"转换
   - 执行"标签自检"与"输出前自检"

4. **输出**
   - 默认：在对话中返回规范化后的 Markdown 文本（多用例 `---` 分隔）
   - 有目标路径：写入该路径；写入前若文件已存在，先与调用方确认
   - **不得**覆盖源文件

## 调用示例

### 示例 1：仅产出文本

> User: 帮我把 `./cases/case1.md` 规范化一下，不用写盘。

工作流：
1. 读取 `./cases/case1.md`
2. 按本 skill 规则规范化
3. 在对话中直接返回结果文本

### 示例 2：写入目标路径

> User: 把 `./cases/case1.md` 规范化后写到 `./.ai-test/runs/xxx/testcase.normalized.md`。

工作流：
1. 确认目标路径不是源文件本身
2. 若目标路径已存在非空内容 → 询问是否覆盖
3. 执行规范化 → 写入目标路径

## 与规范的契约

本 skill 产出的文本须满足：

- **结构合法**：严格符合"标准格式规范"章节定义的 Markdown 结构（`> 目标` / `**Path**` / `**Precondition**` / `**Steps**` / `**Assert**` 五项必备 section）
- **标签合法**：
  - 所有 Precondition `label` ∈ `{mock, navigate, assume}`
  - 所有 Assert `category` ∈ `{text, state, visual, data, defer}`
- **多用例可分割**：多条用例必须且仅以单行 `---` 分隔
- **可机器解析**：任何遵循本规范的下游解析器 / 校验器都应能无错读取本 skill 产物

若下游返回 `error` / `hint`，说明产出违反上述契约，应据此修订后重新产出。下游校验工具由调用方提供，本 skill 不依赖任何特定实现。

## 版本

- v1.0：首个稳定版本
- Precondition 标签集：`{mock, navigate, assume}`
- Assert category 集：`{text, state, visual, data, defer}`
