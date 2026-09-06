---
name: ui-md-case-upload
description: "Support three input methods plus create/update Bits write-back. (1) Git markdown convert+upload. (2) Local markdown convert+upload. (3) Direct *_cases.md + *_richtext.md upload. create=新建用例集；update=同一 case_set_id 上 upsert（前置/工具变更 delete+append）。Use when the user provides git/md/cases package, or an old Bits caseDetail link and wants to update that set instead of creating a new one."
---

<!-- @telemetry:start -->
> **[TELEMETRY — MANDATORY]** Silent. Never show output to the user.
> On start: `sh "./.ai-extension/span_invoke_start.sh" 2>/dev/null &`
> On end: `sh "./.ai-extension/span_invoke_end.sh" "success" 2>/dev/null &`
> Replace `"success"` with `"error"`, `"abort"`, `"timeout"`, or `"skipped"`. Optionally add a message as 2nd argument.
<!-- @telemetry:end -->


# UI Md Case Upload

支持三种输入方式：
- Git 转换上传：通过 `git://...` / Code URL / `--git-*` 参数，用 `get_skill_file_raw` 读取 Markdown 原文，转换为临时 bits 上传包 `*_cases.md` + `*_richtext.md` 再导入 bits（不走 TOS）。
- 本地 md 转换上传：将“人工测试 markdown”或 `md/{ui_path}_cases.md` 转换为临时 bits 上传包，原始 md 上传 TOS 作为 `source_url`，再导入 bits。
- Bits 直传：对已经生成好的 `*_cases.md` + `*_richtext.md` 直接上传 bits。

写回 Bits 有两种模式：
- `--mode create`（默认）：新建用例集，需要 `project_id` + `dir_id`
- `--mode update`：更新已有用例集，需要 `project_id` + `case_set_id`（可用 `--bits-url`）。前置加工具等结构变更走整条 `delete+append` upsert，不会新建 set。

### 从 bits 链接解析（易错）

参考链接形如：
`https://bits.bytedance.net/devops/1499051266/quality/case/caseDetail/15225705?devops_space_old_id=66666866&...&dirId=566373`

| 参数 | 取自 | 模式 |
|---|---|---|
| `--project_id` | URL 路径 **`/devops/{id}/`**（上例 = `1499051266`） | create / update |
| `--case-set-id` | 路径 `caseDetail/{id}`（上例 = `15225705`） | **update 必填** |
| `--dir_id` | query `dirId`（上例 = `566373`） | **create 必填** |

**禁止**用 query 里的 `devops_space_old_id` / `projectId=` 当 `project_id`。也可用 `--bits-url '<整段链接>'` 一次解析。

### update 一站式流程（用户预期）

```
老 Bits 链接 → 改 cases/richtext（或先转换）→ --mode update --dry-run 确认 → 正式 upsert → 同一 caseDetail
```

Agent 规则：
1. 用户给了 caseDetail 链接且说「更新/改前置/加工具」→ **必须** `--mode update`，禁止再 create 出新 set
2. 先 `--dry-run` 把 upsert 列表给用户确认，再去掉 dry-run 提交
3. 只改部分用例时加 `--only-case-title '...'`（可重复）
4. 读回 Bits 脑图用 `ui-md-case-gen/scripts/fetch_bits_case.py`；本 skill 负责转换+写回

用户给了参考用例链接时，**必须**按上表解析后再上传；解析不清先反问。

适用输入示例：
- `ui-cases.md`
- 手工回归文档
- 按 `## TC-...` 组织的测试 markdown
- `tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md`
- `cases.md` + `richtext.md`
- `xxx_cases.md` + `xxx_richtext.md`

## Workflow

1. 判断输入模式：
   - 若提供原始 md：走“转换上传模式”
   - 若提供 Git 地址：先通过 `get_skill_file_raw` 读取 Markdown 原文，再走“转换上传模式”
   - 若提供 `cases.md` + `richtext.md`：走“直传模式”
2. Git 输入读取：
   - **【强约束】显式 ref 检查**：Git / Code 链接必须带显式 `ref`（`?ref=<branch|tag|commit>`），或由调用方显式传 `--git-ref <ref>`。
     - 链接里只有 `ref_type=heads`、或仅靠路径 `/blob/<branch>/` 推断的分支，**都不算显式 ref**。
     - 若缺少显式 ref：**先停下来反问用户**要用哪个分支 / tag / commit，拿到确认后再补 `?ref=` 或 `--git-ref` 执行，**禁止直接读取/上传**。
     - 脚本已内置该校验：URL 输入缺少显式 ref 时会直接报错中止（不会猜测分支），据此提示用户补充即可。
   - 支持 `git://{repo_id}/{path}?ref={ref}` 作为 `--input`
   - 支持 Code 文件 URL：`https://code.byted.org/{repo_id}/blob/{ref}/{path}`
   - Code URL 的分支名可能包含 `/`；解析时优先在 `businesses/`、`tt-nova/`、`docs/`、`cases/`、`features/` 等内容根目录前切分 ref/path，例如 `/blob/agi/benchmark/businesses/...` 解析为 `ref=agi/benchmark`、`path=businesses/...`
   - Code 目录 URL（`/tree/...`）只能解析出 repo/ref/path，`get_skill_file_raw` 仍要求 path 指向具体 Markdown 文件；如果传目录会返回 404，需要用户提供具体 `.md` 文件路径
   - 也支持显式参数：`--git-repo-id <repo_id> --git-ref <ref> --git-path <path>`
   - 调用 `POST /ui/open_api/get_skill_file_raw` 获取 `content` / `uri` / `resolved_commit_sha` / `base_commit_sha`
   - 将 `content` 写入临时 raw md 文件继续复用后续转换逻辑
   - Git 模式的 `source_url` 直接使用接口返回的 `uri`；如果后续要提 MR，保留 `resolved_commit_sha` 和 `base_commit_sha`
3. 转换上传模式下，读取输入 md 文件，解析：
   - 文档标题
   - `Precondition Templates`
   - 每个 `## TC-...` 用例块
   - `Priority` / `Dir` / `Precondition` / `Extra` / `Remark` / `Steps` / `Assertions`
   - `### Steps` 下内嵌的 `- **预期**：...` / `- Assert: ...` 也视为断言点
4. 前置条件理解（必须由 agent/LLM 完成，不依赖固定 Markdown 格式）：
   - 通读源 md 中关于账号、角色、账号池、pool_id、标签、UID、固定账号的描述
   - 将“账号占位符 / 角色 / 账号池 / pool_id / tag”抽取为结构化 JSON
   - 不要假设输入一定是固定表格，也不要依赖正则从 md 中硬取列；表格、段落、列表、自然语言说明都要由大模型理解后归一化
   - 若用例 `Precondition` 同时引用多个账号占位符（如主播 + 观众 + 18- 观众），上传脚本会按设备角色分别绑定对应账号
   - 调用脚本时通过 `--account-mapping-json '<json>'` 或 `--account-mapping-file <json_path>` 显式传入
   - 账号之外按**工具选型**抽取 `precondition_tools` JSON（对齐 `ui-xmind-case-gen`）：
     | 诉求 | 工具 | params |
     |---|---|---|
     | PPE / 泳道 | `环境名称` | `env=` |
     | Libra 加实验 | `libra实验` | `region=` + `libra_id=` + `group_id=`。**仅当有 Libra 链接**且缺 `group_id` 时分别问实验组与对照组，正向挂实验组、对照/反向挂对照组（见 [`../references/libra-group-assignment.md`](../references/libra-group-assignment.md)） |
     | 地区 / 语言 / debug AB KV | `ttmock_preset` | `region=` / `language=` / `ab_settings={"k":"v"}`（**必须是 JSON 对象 string**，禁止数组/`flight:`/`libra=`） |
     | Gecko Channel/Package 等 | `Gecko 配置` | 见 xmind-case-gen |
   - **禁止混塞**：不要把 `env`/`libra` 塞进 `ttmock_preset.params`；不要把 deeplink、enter_room、GeckoX（仅改 local_test/boe/online 时用步骤工具 `GeckoX_settings`）、场景 Mock 等乱转成前置工具
   - 每个设备必须有 `测试账号`；`ttmock_preset` 仅在有 region/language/ab_settings 需求时传入，否则可省略或空 inputData
   - 调用脚本时通过 `--precondition-tools-json '<json>'` 或 `--precondition-tools-file <json_path>` 显式传入
   - `ab_settings` / `ab_settings_live` **强制校验（有则必检）**：凡 `ttmock_preset` 带这两个字段，必须是 JSON **对象**（dict 或 `{"k":"v"}` string）。Agent 在调用转换脚本**之前**必须自检：
     ```bash
     python ../ui-xmind-case-gen/script.py check-json-object --param ab_settings '<值>'
     ```
     输出 `ok:false` 或脚本报 `[INVALID_JSON_OBJECT]` → 重写后再转换，禁止数组 / `flight:` / 非 JSON。脚本在加载 `--precondition-tools-json` 与 render 时也会硬拦。
5. 为每条用例推断设备数：
   - 主播 → `TT-主播设备-*`
   - 观众 / 管理员 / 嘉宾 / 设备 A/B/C → `TT-非主播设备-*`
   - 若观众场景依赖“直播间已开播 / 同一直播间”，自动补主播设备以保证前置逻辑完整
6. 工具转换：
   - 每个设备默认补 `测试账号`，并按账号映射 / UID 填充参数，原有账号绑定逻辑不变
   - **账号凭证字段（重要）**：`测试账号` 的登录凭证按账号标识类型自动选择，**不要混用**：
     - 账号标识是**普通用户名**（非手机号，如 `zgwflkids01`）→ 凭证写入 `password`（密码）字段，对应 `account.password`。
     - 账号标识是**手机号**（纯数字、可带 `+`，如 `12346699929`）→ 凭证写入 `captcha`（验证码）字段，对应 `account.captcha`。
     - **手机号必须带国家区号**，写成 `+<区号><号码>`（如 `+8112345228746`）。平台缺区号时按 `+86` 解析，非 86 账号登录直接失败。`account_mapping` 里可以给裸号码 + `country_code`（如 `"country_code": "81"`）由脚本拼接；两者都没有会在转换阶段报错，不会静默按 86 上传。
     - `account_mapping` 里无论写 `password=` 还是 `captcha=`，脚本都会根据 `username` 是否为手机号自动落到正确字段（`_looks_like_phone_number` 判定）；账号文件里给的是登录密码就按用户名+密码登录，给的是验证码就按手机号+验证码登录。
   - 每个设备默认补 `ttmock_preset`（无匹配参数则空 inputData）；`precondition_tools` 里显式传入的 `环境名称` / `libra实验` / `Gecko 配置` 等按 target 绑定到设备
   - 不要自动检索流程工具（deeplink/enter_room 等）进前置；只注册 JSON 里声明的前置工具 + 默认账号/ttmock
7. 确定原始 md 来源标识：
   - 若用户已提供 `--source-url`，直接复用
   - Git 输入模式使用 `get_skill_file_raw` 返回的 `uri`，不上传 TOS
   - 本地 md 输入模式：未提供 `--source-url` 时，调用脚本内置的 `_upload_source_to_tos(input_path)` 上传原始 md 到 TOS，并以返回的 obj_key 作为 `source_url`
   - TOS 所需参数都在方法内部固定，不暴露外部参数
8. 生成中间产物：
   - `tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/{ui_path}_cases.md`
   - `tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/{ui_path}_richtext.md`
   - `tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/{ui_path}_manifest.json`
9. 调用 `ui-xmind-case-upload` 的上传逻辑导入 bits

直传模式下：
- 不解析原始用例
- 若未提供 `richtext.md`，脚本按同目录自动推断：
  - `*_cases.md` -> `*_richtext.md`
  - `cases.md` -> `richtext.md`

## Output Rules

## Unified Path Contract

- **正式 AppUse Markdown 输入/产物**：
  - `<repo_root>/tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md`
- **临时上传辅助产物**：
  - `<repo_root>/tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/{ui_path}_cases.md`
  - `<repo_root>/tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/{ui_path}_richtext.md`
  - `<repo_root>/tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/{ui_path}_manifest.json`
  - 其他上传前校验 JSON、验证脚本、调试文件也统一放到 `tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/`

- **角色 / 设备**：
  - 用例**涉及 2 个及以上角色**时，按设备角色分行，每台设备一行并带设备角色 richtext 占位符
  - 用例**只有 1 个角色**时，默认不指定设备角色（不输出 `${richText:TT-*设备-*}` 占位符），前置与步骤直接平铺
  - **集合级规则**：只要整个 case 集里有**任意一条**用例涉及多角色，则该集合内**所有**用例（包括单角色）都要配置一个默认设备（带设备角色占位符）
  - **`**[parallel]**` 默认全加**：所有步骤行一律并行，单设备用例也加，不再按设备数区分

  - **【硬约束】设备编排必须前后对齐**（脚本门禁 `_assert_device_consistency`，不满足直接中止转换/直传，不会产出上传包）：
  - 前置条件里出现的每台设备，**必须**在操作步骤里有一个**带真实动作**的节点。
    只有 `**[parallel]**`（或再加一个 `**[remark]**`）而没有动作文本的行 = 空节点，
    等同于该设备没进步骤，**UI 执行会直接报错**。
  - 该设备本用例确实不需要操作时（只提供前置环境，例如观众侧用例里的主播只负责开播），
    **不允许留空**，脚本会自动写入占位动作
    `保持当前状态，本用例不对该设备下发操作（仅提供前置环境）`。
  - 步骤 / 预期结果里不允许出现前置条件未声明的设备。
  - 前置条件渲染同理：设备没有任何工具也要单独成行（补一条空 `**[remark]** <ttat>`），
    不能因为「没工具」就把这台设备从前置里省掉。
  - **步骤行禁止出现 `<ttat>`**：`<ttat>` 只属于前置条件节点；步骤 remark 带了会中止。

- **步骤的设备归属（易错）**：中文里角色词常作修饰语而非执行者，按字面 token 匹配会判错人。
  优先级如下：
  1. 显式 `设备X（角色）：` 前缀
  2. 步骤文本里**唯一**命中的角色词
  3. 步骤文本里**最先出现**的角色词（处理「观众给主播送礼物」这类双角色句，主语在前）
  4. **用例标题里最先出现**的角色词
  5. 默认主播设备

  额外纠偏：标题点名的是非主播角色，而某步骤只因**句中**出现「主播」被判给主播时
  （如「点击入口，打开**主播地区**的小时榜」「进入该**主播**直播间」），改判给标题角色。
  句首就点名主播的（「主播开播」）视为真执行者，不纠。
- **前置条件**：
  - 每台设备输出 `测试账号`，以及 JSON 声明的前置工具（`ttmock_preset` / `环境名称` / `libra实验` / `Gecko 配置` 等）
  - **Hard constraint**：每一次工具调用的 `mentionId`（及 richtext `uuid`）必须唯一，即使同工具、相同 inputData 也不得复用
  - 无法结构化的补充说明写成 `**[remark]** <ttat> ...`（不再单独标识优先级 / 标签）
  - 用例溯源 remark（`**[remark]** [md] <用例标题> + <source_url>`）**恒定**内联挂在「操作步骤」行末（与步骤同行、不单独成行）——下游要从步骤里读回这个 git 链接，落到前置条件就读不到了
    - **必须挂在最后一台设备行**：服务端剥离「非末行」行尾的 `**[remark]**` 时，会把该行的行分隔符一起吃掉，多台设备被拼成一行，UI 执行时第二台设备拿不到自己的动作。note 是步骤节点级属性，挂末行不丢任何信息。实测见 case set 15794265（remark 在首行行尾/首行行尾不带分号 → 换行丢失；挪到动作之前/挂末行 → 换行保留）
    - `_assert_device_consistency` 已把这条设为硬门禁：非末行步骤行尾出现 `**[remark]**` 直接中止转换
    - 该 remark **不带** `<ttat>`：`<ttat>` 只是前置条件节点的标记约定
    - 前置条件节点只保留一条空 `**[remark]** <ttat>` 占位
    - **禁止**在操作步骤与预期结果之间单独成行（BITS 导入器会把独立 `**[...]**` 行当成空预期结果节点）
    - `--source-url-in-step` 已废弃为空操作，加不加结果一样；保留只为不打断已有调用
- **步骤**：
  - 通用执行标记由 `[skill]` 改为 `[md]`
  - 多角色：每个设备节点简要写**该角色要做的事情**（按 角色词/账号/设备标签 归属原始步骤）
  - 单角色：不指定角色，在步骤节点直接写用例要求做的事情
- **预期结果**：
  - **不再写 `nova-assert` 占位符**
  - 按输入 case.md 的 `Assert` / 步骤内 `- Assert:` 逐条搬到 `预期结果` 节点（一条断言一个节点）
  - **多角色时必须带设备**：源 md 写 `设备X（角色）：…`；转换后为 `###### **预期结果** ${richText:TT-主播设备-1|TT-非主播设备-*} …`（与操作步骤同一套设备槽位）
  - 若用例有优先级 / 标签，在**每个**`预期结果`节点内、断言文本**同一行行内追加**（**不换行**）`**[priority]** <值>` 和 `**[tag]** <值>`
- **工具参数**：
  - 统一写入 richtext 对应的 `inputData`

## Commands

`--env` 和 `--network` 是两个独立维度，转换上传、Git 输入和直传模式均适用：

`--env` 只控制环境路由 Header：

| Environment | `--env` | Header behavior |
|---|---|---|
| PPE | `ppe` (default) | 携带 `x-tt-env` / `x-use-ppe` 等 PPE 路由 Header |
| Production | `prod` | 不携带 PPE 路由 Header |

`--network` 只控制访问域名：

| Execution network | `--network` | Host |
|---|---|---|
| Office / local agent | `office` (default) | `ttat-openapi-sg.tiktok-row.net` |
| Server intranet | `server` | `ttat-openapi-sg.byteintl.net` |

常用组合：

- 本地/办公网访问 Production：`--env prod --network office`（`--network office` 可省略）。
- 机房/CI 访问 Production：`--env prod --network server`（必须显式指定 `--network server`）。
- 本地/办公网访问 PPE：`--env ppe --network office`（均为默认值）。

> 兼容性迁移：旧版本中 `--env prod` 会隐式选择 `byteintl.net`；新版本中 `--env prod` 仅关闭 PPE Header，域名由 `--network` 决定且默认使用办公网 `tiktok-row.net`。已有机房/CI 调用方必须补充 `--network server`，否则会静默改用办公网域名。

```bash
python3 .codex/skills/ui-md-case-upload/scripts/md_case_skill_upload.py \
  --input /abs/path/ui-cases.md \
  --vc live \
  --module lite_push \
  --ui-path lite_push_comment \
  --project_id 66666866 \
  --dir_id 1420225 \
  --account-mapping-json '[{"account_id":"A-HOST-BASIC","role":"主播","pool_name":"直播-基础-sg","pool_id":"7064529344105812994","tag_name":"live_anchor"}]' \
  --precondition-tools-json '{"precondition_tools":[{"tool":"环境名称","target":"all","params":{"env":"ppe_xxx"}},{"tool":"ttmock_preset","target":"host","params":{"region":"US","language":"en","ab_settings":{"72192329":"1"}}},{"tool":"libra实验","target":"all","params":{"region":"sg","libra_id":"71315741","group_id":"74002288"}}]}' \
  --out-dir /abs/path/to/repo/tt-nova/ui/tmp/live/lite_push/ui-md-case-upload \
  --tmp-dir /abs/path/to/repo/tt-nova/ui/tmp/live/lite_push/ui-md-case-upload
```

> 本地 md 输入时未传 `--source-url`，脚本会自动把原始 md 上传 TOS 并用其链接作为 `source_url`；如已有链接可显式传 `--source-url 'https://tos.../xxx.md'`。

Git 输入示例：

```bash
python3 .codex/skills/ui-md-case-upload/scripts/md_case_skill_upload.py \
  --input 'git://999892/businesses/localservice/affiliate/docs/_index.md?ref=main' \
  --vc localservice \
  --module affiliate \
  --ui-path affiliate_index \
  --project_id 66666866 \
  --dir_id 1420225
```

也可使用显式 Git 参数：

```bash
python3 .codex/skills/ui-md-case-upload/scripts/md_case_skill_upload.py \
  --git-repo-id 999892 \
  --git-ref main \
  --git-path businesses/localservice/affiliate/docs/_index.md \
  --vc localservice \
  --module affiliate \
  --ui-path affiliate_index \
  --project_id 66666866 \
  --dir_id 1420225
```

也支持仅转换不上传：

```bash
python3 .codex/skills/ui-md-case-upload/scripts/md_case_skill_upload.py \
  --input /abs/path/to/repo/tt-nova/ui/business/live/lite_push/md/lite_push_comment_cases.md \
  --vc live \
  --module lite_push \
  --ui-path lite_push_comment \
  --out-dir /abs/path/to/repo/tt-nova/ui/tmp/live/lite_push/ui-md-case-upload \
  --tmp-dir /abs/path/to/repo/tt-nova/ui/tmp/live/lite_push/ui-md-case-upload \
  --skip-upload
```

直传模式示例：

```bash
python3 skills/tt-nova-ui/ui-md-case-upload/scripts/md_case_skill_upload.py \
  --cases /abs/path/to/repo/tt-nova/ui/tmp/live/lite_push/ui-md-case-upload/lite_push_comment_cases.md \
  --richtext /abs/path/to/repo/tt-nova/ui/tmp/live/lite_push/ui-md-case-upload/lite_push_comment_richtext.md \
  --project_id 1499051266 \
  --dir_id 1422067 \
  --creator huangyiran.dd \
  --env prod \
  --network office
```

更新已有用例集（前置加工具等；先 dry-run）：

```bash
python3 skills/tt-nova-ui/ui-md-case-upload/scripts/md_case_skill_upload.py \
  --mode update --dry-run \
  --cases /abs/path/.../xxx_cases.md \
  --richtext /abs/path/.../xxx_richtext.md \
  --bits-url 'https://bits.bytedance.net/devops/1499051266/quality/case/caseDetail/15258509' \
  --env prod --network office

python3 skills/tt-nova-ui/ui-md-case-upload/scripts/md_case_skill_upload.py \
  --mode update \
  --cases /abs/path/.../xxx_cases.md \
  --richtext /abs/path/.../xxx_richtext.md \
  --bits-url 'https://bits.bytedance.net/devops/1499051266/quality/case/caseDetail/15258509' \
  --only-case-title 'TC-R-001 最近三场合格 LIVE ASR 数据可用于生成模板' \
  --env prod --network office
```

若 `richtext.md` 与 `cases.md` 同目录且命名符合约定，也可省略：

```bash
python3 skills/tt-nova-ui/ui-md-case-upload/scripts/md_case_skill_upload.py \
  --cases /abs/path/to/repo/tt-nova/ui/tmp/live/lite_push/ui-md-case-upload/lite_push_comment_cases.md \
  --project_id 1499051266 \
  --dir_id 1422067
```

## 上传完成 → 必须提醒用户（P0）

上传成功返回 Bits 链接后，**不要立刻结束**。按父 skill 清单核对并当面提醒：

→ [`../references/case-delivery-checklist.md`](../references/case-delivery-checklist.md)

至少确认并告知用户：
1. `project_id` 是否取自 `/devops/{id}/`（不是 `devops_space_old_id`）
2. Bits 步骤节点：多设备是否换行；git 溯源 remark 是否在步骤 note（末行设备）
3. 前置每台设备是否有 `测试账号`；env→`环境名称`、flight→`libra实验`、AB KV→`ttmock ab_settings` JSON 对象（勿把 env/libra 塞 ttmock）
4. 步骤是否全并行（`**[parallel]**`）；闲置设备是否有占位动作

脚本已硬门禁：设备对齐、remark 不得挂非末行、步骤行禁 `<ttat>`、缺 git ref 中止（转换与直传都过 `_assert_device_consistency`）。门禁过了仍要把上表对用户说一遍——很多坑只能在 Bits UI 上看出来。

## Notes

- **Git / Code 链接必须带显式 `ref`**：缺少显式 `ref`（只有 `ref_type` 或只靠 `/blob/<branch>/` 路径）时，先反问用户确认分支，再补 `?ref=` 或 `--git-ref`，**不要直接上传**。脚本会对缺 ref 的 URL 输入直接报错中止。
- 该 skill 复用根目录 `ui-xmind-case-gen` 的设备槽位和工具 richtext 注册；前置允许 `测试账号` / `ttmock_preset` / `环境名称` / `libra实验` / `Gecko 配置`（与 xmind-case-gen `_PRECONDITION_TOOLS` 对齐）。
- 本地 md 输入模式的 TOS 上传仅使用脚本内置的 `bytedtos` 逻辑；Git 输入模式不上传 TOS。
- bits 上传逻辑直接复用根目录 `ui-xmind-case-upload/scripts/upload_cases.py`。
- 直传模式仍兼容旧命名 `*_case.md`，但统一对外约定为 `*_cases.md`。
- **deeplink 不是必需项**：许多场景（如从 Profile 手动进入频道设置）并不涉及 deeplink，此时用例完全通过手动导航路径描述入口即可。skill 在转换和上传流程中不应因缺少 deeplink 而报错或强制补充。
