# Output Contract

输出是单文件 Markdown。它既要给人读，也要给 AI 或 UI 自动化执行。
产物格式必须严格符合 [testcase-normalize-SKILL.md](./testcase-normalize-SKILL.md) 定义的规范化结构；本文件在其之上只补充"文件级的 Test Kit 骨架"与"改写规则"。

生成顺序：**原始素材（BITS 脑图分支 或 PRD / 需求文档功能点） → 内部分支清单（仅推理用） → AI 可执行 Case**。

> **产物用语红线**：内部术语 `seed`、`seed-preserving`、`seed-first`、`Raw Seeds` **严禁**出现在最终落盘的 md 产物中（包括 frontmatter `tags` / `suite` / 正文标题 / 正文说明 / Notes / Summary 任何位置）。需要表达这类意思时，一律写成"分支 / 场景 / 用例"。

## Top-Level Structure

```markdown
---
title: <标题>
tags: [ui-case, <module>, regression, bitsgui]
date: YYYY-MM-DD
last_updated: YYYY-MM-DD
suite: <回归集>
module: <模块名>
source_bits_case: "<bits_case_url>"
---

# <标题>

## 测试物料(Test Kit)
### 1. Deeplink
### 2. UI Mapping（扩展）
### 3. Platform Differences
### 4. Common Test Accounts

<!-- 以下为多条规范化用例，彼此用单行 `---` 分隔 -->

> <一句话描述测试目标>

- **Priority**: P0 / P1 / P2
- **Platform**: iOS / Android / 双端
- **Pkg**: <包名或应用标识>

**Path**:
<功能路径，如 `直播/开播工具区/ENHANCE/Face`>

**Context**:（如有）
- <kind> | <值>

**Precondition**:
- <label> | <条件文本>

**Setup**:（如有）
- <准备步骤>

**Steps**:
1. <操作描述>
    - Assert: <category> | <预期结果>

**Assert**:
- <category> | <全局断言>

**Notes**:（如有）
- <补充说明，可用于放 TODO-KNOWLEDGE、PD-xx 引用等>

---

> <下一条用例的测试目标>
...
```

### 强制字段

每条用例必须包含以下 5 个 section（顺序不可调）：

1. 首行 `> 测试目标`
2. `**Path**:`
3. `**Precondition**:`（至少 1 条）
4. `**Steps**:`（至少 1 步，步骤用数字编号，Assert 行作为子项缩进）
5. `**Assert**:`（至少 1 条全局断言）

其余 section（`**Priority**`、`**Platform**`、`**Pkg**`、`**Context**`、`**Setup**`、`**Notes**`）按需出现。

### 标签体系

- Precondition `label` 只能取自 `{ mock, navigate, assume }`
- Assert `category` 只能取自 `{ text, state, visual, data, defer }`

判定顺序与标签自检规则以 [testcase-normalize-SKILL.md](./testcase-normalize-SKILL.md) 为准。

### 多用例分隔

多条独立用例之间，**仅用单行 `---`** 分隔（前后各一个空行）。不得使用额外标题、代码块或其他分隔符。

## Rewrite Rules

### 0. Branch-First, Never Compress First

先把原始素材（BITS 脑图 或 PRD / 需求文档）展开成**内部分支清单**（在 skill 文档里用内部术语 `Raw Seeds` 指代；**该术语不得写入产物 md**），再改写 UI case。

约束：

- 每条分支对应一条独立可执行路径
- 入口状态不同的分支绝不合并
- 只有同入口、同动作、同页面的并列静态断言才允许在 case 层合并

### 1. Start From A Concrete Entry

每条 case 都要从可复现入口开始：

- 优先 deeplink（放在 `**Precondition**:` 的 `navigate` 或 `**Setup**:`）
- 其次手动入口路径（写成一串 `navigate | ...` 前置条件，或 Setup 步骤）

不要默认"已经在目标页"。

### 2. Use Visible UI Anchors

`**Steps**:` 下的每个动作必须带视觉定位信息：

- 页面名
- 图标/文案
- 位置关系

例如：

- `1. 在主播开播预览页点击工具区内带有魔法棒图标的 "美颜" 文本按钮。`
- `2. 在 Settings 面板点击 "Video quality" 行。`

不要只写：

- `点击设置`
- `进入下一页`

### 3. Keep One Action Per Step

每一步只写一个动作。复杂动作拆开成多步。

不要写：

- `点击设置并进入视频质量页并切换为 720p`

应拆成：

```
1. 点击设置入口。
    - Assert: state | 进入 Settings 页面。
2. 点击 "Video quality" 行。
    - Assert: state | 进入 Video quality 子页面。
3. 选择 "720p"。
    - Assert: text | 当前选项显示为 "720p"。
```

### 4. Assert Must Be Observable And Labeled

每条 Assert 必须写成 `<category> | <描述>`，且描述只写"能看见、能定位、能判断"的结果：

- `text | 顶部可见 "Face"、"Filters" 等 tab。`
- `state | 底部美颜面板展开且置于最上层。`
- `visual | 工具区图标切换为高亮选中态。`
- `data | 上报事件 "livesdk_beauty_panel_show"，当前工具链暂无法自动验证。`
- `defer | <其余当前无法自动验证的断言>`

不要写：

- `功能正常`
- `设置成功`
- `交互符合预期`

若描述无法映射到具体类别，参考 [testcase-normalize-SKILL.md](./testcase-normalize-SKILL.md) 的"标签判定协议"重新归类。

### 5. Precondition Must Be Labeled

每条 Precondition 必须写成 `<label> | <条件文本>`：

- `mock | 账号 A-HOST-BASIC 已登录，地区=US。`
- `mock | 实验 livesdk_beauty_v2 命中实验组。`
- `navigate | 已进入主播开播预览页。`
- `assume | 设备已安装当前版本客户端。`

判定口诀：

- 改变 App/环境的**配置型状态** → `mock`
- 通过用户操作到达某页面/入口/状态 → `navigate`
- 纯声明性假设 → `assume`

注意：`assume` 标签下的文本不得包含"切换 / 设置 / 修改 / 开启 / 关闭"等动作动词，否则必须改为 `mock` 或 `navigate`。

### 6. Centralize Platform Differences

所有端差异统一写在 Test Kit 的 `Platform Differences` 表：

- `PD-01`
- `PD-02`

正文里只在 `**Notes**:` 中引用：

- `- 见 PD-01`

### 7. Preserve Traceability

每条 case 都要能回溯原始来源。统一写在 `**Notes**:` 中：

- 原始 BITS case id
- 原始目录路径
- 原始节点标题或路径

例如：

```
**Notes**:
- 来源：BITS case #13956026 / 开播工具区 / ENHANCE / Face
- 见 PD-01
```

## Minimum Acceptance Bar

最终文稿至少满足：

1. 新同学不看原始脑图也能执行
2. AI 不需要额外猜页面路径
3. 关键断言都是可观察的，且都带合法 `category` 前缀
4. 缺失知识都被显式标注为 `TODO-KNOWLEDGE:`（放在 `**Notes**:` 或对应 Precondition 文本中）
5. 每个原始互斥分支都有对应 case，不存在 `热启动/冷启动` 被压成一条的情况
6. 规范化自检（见 [testcase-normalize-SKILL.md](./testcase-normalize-SKILL.md) "输出前自检"）全部通过
