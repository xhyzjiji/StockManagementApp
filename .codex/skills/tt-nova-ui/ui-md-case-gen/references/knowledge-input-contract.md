# Knowledge Input Contract

生成 AI 可执行 UI 用例前，先补齐下表中的知识。目标是把原始业务测试点转成"可定位、可执行、可验证"的 UI 动作链。

最终产物的格式与标签体系见 [testcase-normalize-SKILL.md](./testcase-normalize-SKILL.md)；本文件只负责定义"生成前需要输入什么"。

| 类别 | 是否必需 | 需要什么 | 用在产物哪里 |
|---|---|---|---|
| BITS 来源 | 必需 | `bits_case_url` 或 `test_case_id/product_id/space_id` | 追溯原始 case、抓取脑图 |
| 模块焦点 | 必需 | `module_focus`，例如 `开播工具区 / Settings / Video quality` | 裁剪目标子树、写入每条 case 的 `**Path**:` |
| 输出路径 | 必需 | 正式 Markdown 产物路径，统一为 `<repo_root>/tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md` | 落盘 |
| 入口信息 | 强烈建议 | deeplink；若没有，则给手动入口路径 | Test Kit 与每条 case 的 `navigate` 型 Precondition / Setup |
| UI Mapping | 强烈建议 | 页面名、控件视觉描述、控件作用 | 每条 case 的 `**Steps**:` 视觉锚点与 `text`/`state`/`visual` 类 Assert |
| 账号信息 | 建议 | 主播/观众/管理员账号占位符，地区、角色差异 | `mock` 型 Precondition 与公共账号表 |
| 平台差异 | 建议 | iOS/Android 差异、仅单端可见项 | Test Kit 的 Platform Differences 表 + 每条 case 的 `**Notes**:` 引用 |
| 业务规则 | 建议 | 实验开关、地区差异、机型限制、状态前置 | `mock` 型 Precondition 或 `**Notes**:` 补充 |
| 术语解释 | 可选 | 业务黑话对应的 UI 含义 | 改写 `**Steps**:` 时消歧 |

## 最小知识包

如果时间很紧，至少先补这 3 项：

1. 入口方式（产出 `navigate` 型 Precondition 或 Setup）
2. 目标页面和控件的视觉描述（产出 `text` / `state` / `visual` 类 Assert）
3. 账号/角色要求（产出 `mock` 型 Precondition）

没有这三项，生成出来的步骤大概率只能"看懂"，不能"执行"。

## 缺失处理规则

缺知识时这样做：

- 不编造
- 在对应位置保留 `<待补充>`
- 用 `TODO-KNOWLEDGE:` 明确写出缺口，放在 `**Notes**:` 或相关 Precondition 文本中

示例：

```markdown
**Precondition**:
- mock | 账号 A-HOST-BASIC 已登录。
- assume | 设备已安装当前版本客户端。

**Notes**:
- TODO-KNOWLEDGE: 缺少 Android 端进入该面板的稳定入口；当前步骤按 iOS 路径改写。
```

## UI 路径化改写原则

把业务测试点改写成 UI 路径时，优先补充以下信息：

1. 页面起点（写进 `navigate` 型 Precondition 或 Setup）
2. 页面层级（写进 `**Path**:`）
3. 控件视觉特征（写进 `**Steps**:` 的动作描述）
4. 操作类型（一步一个动作）
5. 操作后的可观察结果（写进 `Assert: <category> | ...` 子项，或 `**Assert**:` 全局断言）

例如：

- 原始测试点：`验证打开美颜面板`
- 改写后：

  ```markdown
  > 验证主播开播预览页可正常打开美颜面板

  **Path**:
  直播/开播工具区/ENHANCE/Face

  **Precondition**:
  - mock | 账号 A-HOST-BASIC 已登录，地区=US。
  - navigate | 已进入主播开播预览页。

  **Steps**:
  1. 在主播开播预览页点击工具区内带魔法棒图标的 "美颜" 文本按钮。
      - Assert: state | 底部弹出美颜面板。
      - Assert: text | 面板顶部可见 "Face"、"Filters" 等 tab。

  **Assert**:
  - state | 美颜面板已展开且置于最上层。
  ```

## 建议补充来源

优先使用这些来源，而不是凭记忆写：

- 现有回归 markdown
- 页面截图或录屏
- UI mapping 文档
- PRD / 飞书文档
- 已有可执行 case
