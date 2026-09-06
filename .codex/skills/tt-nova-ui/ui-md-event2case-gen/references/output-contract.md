# 输出契约（两份对齐产物 + 备注附属）

本 skill 产出**两份逻辑一一对齐**的文件；埋点断言（`data`）在两份里必须一致。

## 零、双边用例质量分轨（每次改动必守）

改任一用例 = **同时改两边**，禁止只改 xmind 或只改自动化 md。权威源永远是自动化 md；xmind 由转换脚本从 md 生成，改完必须重跑转换。

| 产物 | 读者 | 质量条 |
|------|------|--------|
| **BITS xmind**（`*_cases.md` / `*_richtext.md`） | **人**（手工执行 / 评审） | 事件优先树；标题写清「谁 + 哪入口 + 点什么 + 报什么」；步骤用人话控件名（打开 App→进房/开播→点自己麦位→点麦克风）；预期结果用 **ETD 词表**写埋点断言。矩阵叶子要铺满，不要只留抽样。 |
| **自动化 Markdown**（KB `*_cases.md`） | **UI 自动化执行器** | 与人读**同一套事件/维度/断言逻辑**；`Path`/`Precondition`/`Steps` **逐步可执行、导航链内联**（禁止「按 Path」）；**断言只用 `data`（埋点），不写功能断言**（见 tracking-assertion-contract 第零节）；**一条用例只挂一个埋点断言时机**，前置操作不带断言（R18，见 3.0）。允许步骤比 xmind 更细，不允许逻辑少维度。 |

自动化 md 写糊 → 两边都不合格（xmind 会原样变糊）。**覆盖密度以矩阵为准**，且矩阵上限 = **本需求 ETD 正文**（R12）：人读叶子数应对上「事件×角色×ETD入口×断言枚举轴×show|click」，**不是** GT 全量笛卡尔积；红线用例另增，不冲掉矩阵，也不借红线塞旁路入口。

**禁止「按 Path」**：`**Steps**` / xmind 操作步骤里禁止写「按 Path」「同上 Path」——必须把导航链**内联展开**进步骤。

**GT（旧手工用例集）只做事后反思，不进推理**：生成阶段（锁定表 / 矩阵 / 写用例）**不读 GT**，全部只认本需求 ETD 正文 + PRD 触发条件。终稿写完后才可选地跑一次 GT 对账（`check_etd_scope.py --gt-seeds`），看旧用例集里有什么是这次没覆盖的：差异只用来**反问用户**（是抽漏了，还是本次确实不验），确认后再回头改 scope 重跑。**禁止**把 GT 的维度/入口/枚举直接铺进矩阵，也禁止照抄 GT 的写法。测新没有 GT，这一步直接跳过。

## 一、自动化 Markdown 用例（单一事实源，落 git 知识库）

路径（**权威源在 git 仓库 `live_tracking_knowledge_base`，不走 TOS**）：
`<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`（`<KB>` 为本地 clone）
推荐并排产出 sidecar `<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.cases.yaml`。

`biz_line` **必须**由用户指定，且只能是：`SMB` / `activity_platform` / `game` / `multi_guest` / `revenue` / `user_product` / `wallet`。未指定 → 反问（选项见 SKILL「业务线反问模板」），禁止猜、禁止落到 `ui-test/` 根目录。

产出后 `cd <KB> && python tools/build_mapping.py` 重建映射图；在分支 **`tt_nova`** 上提交/提 MR。

格式严格遵守 [`../../ui-md-case-gen/references/testcase-normalize-SKILL.md`](../../ui-md-case-gen/references/testcase-normalize-SKILL.md)
与 [`../../ui-md-case-gen/references/output-contract.md`](../../ui-md-case-gen/references/output-contract.md)：每条用例含
`> 目标` / `**Path**` / `**Precondition**` / `**Steps**` / `**Assert**` 五个必备 section，多用例仅以单行 `---` 分隔。

**不要写 `**Platform**`**：埋点用例默认双端执行，写「双端 / Android / iOS」都无信息量（端差异若有，放 Test Kit 的 Platform Differences 或 Notes）。禁止每条刷 `- **Platform**: …`。

### 角色 × 任务（R11，多端执行硬约束）

直播/连麦等多角色场景，自动化 md **必须**让执行器知道「哪台设备、哪个角色、做什么」：

1. **Test Kit** 含角色表（设备 / 角色 / 账号占位 / 职责），例如：

| 设备 | 角色 | 账号占位 | 职责 |
|------|------|----------|------|
| 设备A | 主播 | A-HOST | 开播、保持直播间、主播侧面板/表情 |
| 设备B | 普通嘉宾 | A-GUEST | 进房上麦、嘉宾侧面板/表情 |
| 设备B | 管理员嘉宾 | A-MOD | 进房上麦（管理员权限）、嘉宾侧面板 |

2. **Precondition** 写清登录绑定：`mock | 账号 A-HOST（主播）已登录设备A`；`mock | 账号 A-GUEST（嘉宾）已登录设备B`。
3. **Steps / Path** 每一步必须以 `设备X（角色）：` 开头，例如：

```markdown
**Steps**:
1. 设备A（主播）：打开 TikTok 应用 → 点击【+】→ 选择【直播】→ 直播预览页点击【Go Live】→ 进入直播间 → 开启多人连麦布局 → 保持开播。
2. 设备B（嘉宾）：打开 TikTok 应用 → 进入本场目标多人直播间 → 申请或接受上麦 → 确认自己已在麦上 → 点击自己的麦位区域 → 等待麦位操作面板完全弹出。
    - Assert: 设备B（嘉宾）：data | 上报 `livesdk_multi_guest_interact_panel`；`action_type` = `show`。

**Assert**:
- 设备B（嘉宾）：data | 上报 `livesdk_multi_guest_interact_panel`；`action_type` = `show`。
```

禁止「打开 App → 进入直播间 → 上麦」这种**未声明主语**的步骤（转换脚本会把无角色词的步骤默认挂到主播设备，导致嘉宾用例无法执行）。

**Assert 也必须带设备前缀**：哪台设备上看 UI、哪台设备上查埋点，都要写清。转换到 BITS 时会变成 `###### **预期结果** ${richText:TT-非主播设备-1} …`。

**措辞注意（避免步骤串设备）**：`设备B（嘉宾）` 步骤/断言正文里不要再写 `设备A`/`主播` 等对端标签（例如写成「进入设备A主播的直播间」会让转换器把该步同时挂到主播设备）。对端房间用「本场目标多人直播间」等中性说法；对端关系放在 Path 总览或 Precondition。

### 文件级 Test Kit（把 `测试准备` 前置到顶部；来源=提测文档）

手工埋点用例集的 `测试准备` 节点（安装包 / env / 实验 / 服务端配置）在这里落成 Test Kit + 各用例 Precondition。
**取自 `etd_scope.json.test_kit`**（它又来自提测/测试说明文档，认内容不认标题）；缺字段登记在 `test_kit.missing[]` 并标 `TODO-KNOWLEDGE`，禁止臆造 ppe / flight id。

> **必须两处都写（P0，历史故障）**：文件头这段 Test Kit **只给人看**。md→xmind 转换器只解析 `## TC-` 用例块，文件头段落不会变成 bits 的前置条件节点 —— 只写这里，bits 上就一个字都看不到测试物料。
> 因此 `env` 和每个 `libra flight` **必须同时**出现在**每一条用例**的 `**Precondition**` 里（给人看 + 门禁扫）；Step 5 还要通过 `--precondition-tools-json` 按正确工具落地：`环境名称`（env）/ `libra实验`（flight，需 group_id）/ 可选 `ttmock_preset`（region 或 `ab_settings` JSON 对象）。**禁止**把 `env`/`libra` 塞进 `ttmock_preset.params`。**仅当有 Libra 链接**且缺 `group_id` 时分别问实验组与对照组并按 case 极性分配（见 [`../../references/libra-group-assignment.md`](../../references/libra-group-assignment.md)）。
> 门禁：`check_etd_scope.py --cases` 会逐条用例反查，缺一条就失败；`check_xmind_precondition.py` 验 richtext 工具选型。

```markdown
## 测试物料(Test Kit)
### 1. 安装包（MR）— 来源：提测文档 / MR
- iOS: <iOS 包 bits code 链接>
- Android: <Android 包 bits code 链接>
### 2. 环境 — 来源：提测文档
- env=ppe_xxx（Precondition 文案 + Step 5 用 **`环境名称`** 工具承载，不要塞 ttmock）
### 3. 实验 / 服务端配置 — 来源：提测文档
- 实验1：libra flight/<id>（触发提词器）；实验2：libra flight/<id>（V2 初始位置）—— Step 5 用 **`libra实验`**（需 `group_id`）；若另有 debug AB KV 再用 `ttmock_preset ab_settings={...}`
- 服务端配置：无按钮提词器 / 有按钮提词器（区分 is_button=0/1）
### 4. Common Test Accounts — 来源：提测文档 / 账号文档
- <加了实验的开播账号>（真实账号，取自文档，勿臆造）
```

### `**Path**` 必须可执行（从 App 主页起）

禁止写成模块标签（反例：`实时主播中心 / 入口提词器 / 曝光埋点`）。
必须写成从 TikTok 主页起的导航链，权威来源
`live_tracking_knowledge_base/knowledge-business/business-ui_routes/`
（例：`user_product/基础业务- UI_Routes.md`）：

```markdown
**Path**:
TikTok主页 → 【+】→【直播】→ 直播预览 →【Go Live】→ 直播间 → 等待提词器展现 → 点击提词器 CTA 按钮
```

查不到对应 UI 路由时：**不要**把 Path 编成完整可执行链再标 TODO。按 R9：写入 `kb_gaps.json`（`kind=ui_route`, `severity=blocking`）→ 开补齐卡等用户填导航链 → resolve 后再写入 Path（evidence=`user_supplied:G-xxx`）。详见 [`kb-gap-interactive.md`](./kb-gap-interactive.md)。

### 单条埋点用例示例

```markdown
> 点击提词器 CTA 按钮上报 click 埋点，action_type=click_cta、is_button=1

- **Priority**: P0

**Path**:
TikTok主页 → 【+】→【直播】→ 直播预览 →【Go Live】→ 直播间 → 等待提词器（有按钮）→ 点击提词器 CTA 按钮

**Precondition**:
- mock | env=ppe_unified_im（来源：提测文档）
- mock | 账号已加实验（libra flight/72057031 触发提词器；来源：提测文档）
- mock | 服务端配置为「有按钮」提词器（is_button=1）
- mock | <加了实验的开播账号> 已登录
- assume | 冷启动：从 TikTok 主页开始，不依赖上一条用例状态

**Steps**:
1. 依次操作：TikTok主页 → 【+】→【直播】→ 直播预览 →【Go Live】→ 直播间；人脸在镜头前等待约 1min30s，直到展示带按钮的提词器（本条不校验展现埋点）。
2. 点击提词器上的 CTA 按钮（非非 CTA 文案区）。
    - Assert: data | 上报 `livesdk_anchor_manager_cues_msg_click` 埋点；参数 `action_type` = `click_cta`；`is_button` = `1`。

**Assert**:
- data | 上报 `livesdk_anchor_manager_cues_msg_click` 埋点；`action_type` = `click_cta`；`is_button` = `1`。

**Notes**:
- 来源：ETD <本需求 wiki_token> / livesdk_anchor_manager_cues_msg_click.action_type
- 命中红线：RL-00X（见覆盖表）
```

> **注意步骤 1 没有埋点断言（R18）**：`..._cues_msg_show` 的展现断言属于它**自己那条曝光用例**，不寄生在点击用例里。一条用例只有一个断言时机 =（一个事件 + 一个 `action_type`），**同一个操作步骤下挂两条埋点断言同样算合并**，执行时分不清哪条对应哪次操作（门禁 G11 会拦）。基线+增量类用例（去重/频控/生命周期）例外，须在 Notes 写 `- 多时机例外: <理由>`。写法与三种合并形态见 [`tracking-assertion-contract.md`](./tracking-assertion-contract.md) 3.0。

> 反例（不合格）：**一条用例里第 1 步校验 show、第 2 步校验 click**（多操作合并）；Steps 写「构造条件1满足、条件2不满足」却不展开条件；Path 写「实时主播中心 / 入口提词器 / 曝光埋点（反向）」；Assert 漏 `is_button` 或多写本需求 ETD 没有的参数。

反向用例示例（不上报）：

```markdown
> 提词器位置滑动未变化成功时不上报 change_position 埋点

...
**Steps**:
1. 展示提词器后，滑动变化位置但未成功（在上面，滑动后仍在上面）。
    - Assert: data | 不上报 `livesdk_anchor_manager_cues_msg_change_position` 埋点。
```

### 文末必附：命中红线覆盖表

见 [`tracking-assertion-contract.md`](./tracking-assertion-contract.md) 第四节，对 `incident-redlines.md` 每条红线逐条表态。

## 二、BITS xmind 用例包（给人看；备注挂自动化 md）

路径：`<repo_root>/tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_cases.md` + `{ui_path}_richtext.md`

由自动化 md 经 `../../ui-md-case-upload/scripts/md_case_skill_upload.py --skip-upload` 转换得到（先落 `tmp/{vc}/{module}/ui-md-event2case-gen/`，确认后拷到 `xmind/`）。转换约定见
[`../../ui-md-case-upload/SKILL.md`](../../ui-md-case-upload/SKILL.md)：

- **人读优先**：标题 + 预期结果把「测什么 / 报什么」说清即可；步骤文字允许比自动化 md 更概括（转换脚本会把 Steps 拼进操作步骤节点）。
- 埋点断言（`data` 预期）逐条搬进 xmind **预期结果节点**。
- 前置条件节点按需使用 `测试账号` / `环境名称` / `libra实验` / `ttmock_preset` / `Gecko 配置` + 一条空 `**[remark]** <ttat>` 标记（选型见 Step 5 表；禁止把 env/libra 塞进 ttmock）。
- 用例溯源 remark（含自动化 md 的 `source_url`）作为 note **恒定内联挂到「操作步骤」行末**，且**不带** `<ttat>`（`<ttat>` 只属于前置条件节点）。必须**与步骤同行、不单独成行**（BITS 导入器会把独立 `**[...]**` 行当成空预期结果节点）。
- **禁止**只手改 xmind 不回写自动化 md：逻辑变更一律改权威源 md → 再转换。

## 三、"自动化 md 附属在 xmind 用例备注里"的打包方式（git 引用，非 TOS）

自动化 md 存在 git 仓库 `live_tracking_knowledge_base` 里，xmind 用例备注引用它的 **git 地址**：

1. 生成阶段：自动化 md 落在 `<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`，在分支 **`tt_nova`** 上提交/提 MR 到 `live_tracking_knowledge_base`。
2. 转换/上传阶段：给 `ui-md-case-upload` 传 `--source-url` 为该 md 的 git 链接，脚本把它作为 note 内联挂到「操作步骤」行末（`... ; **[remark]** [md] <用例标题> + <source_url>`），前置条件仅留空 `**[remark]** <ttat>` 标记。**不走 TOS**。
   - git 链接两种形态皆可：
     - 页面链接：`https://code.byted.org/livearch/live_tracking_knowledge_base/blob/tt_nova/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`
     - `git://<repo_id>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md?ref=tt_nova`（`ui-md-case-upload` Git 输入模式直接用 git uri 作 `source_url`，天然不传 TOS）
   - `<ref>` 优先分支名 `tt_nova`；合入后可回填 commit sha。

这样最终 bits 用例备注里带的是"专供自动化执行的 md 用例文档"的 git 链接（可版本追溯、随知识库沉淀）。

## 四、路径与临时产物

- 自动化 md（权威源）：`<KB>/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md`（+ sidecar `.cases.yaml`）→ git 仓库 `live_tracking_knowledge_base`，分支 `tt_nova`
- BITS xmind 包：`tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_cases.md` + `_richtext.md`
- 临时产物（知识路由笔记、场景×事件矩阵、spec、转换 manifest、校验脚本）：`tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen/`
- `biz_line` ∈ `{SMB, activity_platform, game, multi_guest, revenue, user_product, wallet}`（用户必选）
- `ui_path` 用模块语义 stem，不带 `_cases`/`_spec` 后缀。
