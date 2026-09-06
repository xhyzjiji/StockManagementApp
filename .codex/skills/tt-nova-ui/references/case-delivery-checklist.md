# TT Nova UI 用例交付检查清单（隐性问题）

> 用途：上传 Bits / 交付前给用户过一遍。很多失败只有跑起来或打开 Bits 节点后才暴露。
> Agent：**交付前必须把本清单中「P0」项逐条核对，未通过的先反问用户或修完再交。**

## 最短必过（P0）

| # | 检查项 | 怎么验 | 漏了会怎样 | 所属阶段 |
|---|---|---|---|---|
| P0-1 | `project_id` 取自 URL 路径 `/devops/{id}/`，**不是** `devops_space_old_id` | 对照 Bits 链接：`1499051266` ✅ / `66666866` ❌ | 上传进错空间 | upload |
| P0-2 | 溯源 remark（`标题 + git url`）在**操作步骤**里，且挂在**最后一台设备行末** | Bits 步骤节点 note 有 git 链接；多设备步骤 text 含 `\n` | 下游读不到 git；多设备被拼成一行（实测 15794265） | upload |
| P0-3 | 前置声明的每台设备，步骤里都有真实动作（闲置设备有占位文案） | 步骤节点每台设备各一行且有动作 | UI 执行报错（空设备节点） | upload |
| P0-4 | 所有步骤行带 `**[parallel]**`；首设备行有 `[md]` | cases.md / Bits 步骤节点 | 并行语义丢失 | upload |
| P0-5 | 每台设备前置有 `测试账号`，凭证字段未混用（用户名→password，手机号→captcha），**手机号带国家区号** `+<区号><号码>` | richtext 里 `account.username` 以 `+` 开头 | 登录失败；缺区号平台按 +86 解析 | upload |
| P0-6 | env / libra 写进**每条用例 Precondition**；Step 5 `--precondition-tools-json` 按选型：`环境名称`(env) / `libra实验`(flight+group_id) / 可选 `ttmock_preset`(region 或 `ab_settings` JSON 对象)；**禁止**把 env/libra 塞进 ttmock。**仅当有 Libra 链接**且缺 group_id 时分别问实验组/对照组并按 case 极性分配（见 [`libra-group-assignment.md`](./libra-group-assignment.md)） | Bits 有对应工具节点；有链接时正反 case 的 `group_id` 不同；`ab_settings` 若有则是 `{"k":"v"}` | bits 上看不见环境/实验，或无链接乱追问，或正反共用一个 group，或工具空参 | event2case → upload |
| P0-6b | 凡创建 `ttmock_preset` 且带 `ab_settings`/`ab_settings_live`：必须是 JSON 对象；Agent 先跑 `check-json-object`，转换/render 也会硬拦 | `check-json-object` → `ok:true`；无 `[INVALID_JSON_OBJECT]` | AB 配置写了却执行不到 / 节点空 | 任何产出 ttmock 的 skill |
| P0-7 | Git 输入带显式 `--git-ref` / `?ref=` | 命令行参数 | 读错分支或中止 | upload |
| P0-8 | 埋点用例 Assert **只**验埋点，不写功能断言；转 xmind 后预期节点是 `data_assertion`（AppLog，`data_filter_name=<event>`） | Bits 预期 richtext 含 `data_assertion`；inputData 有 event 名 | 埋点用例当功能验收；或断言不可执行 | event2case → upload |
| P0-9 | 更新已有集时用 `--mode update` + `case_set_id`（Bits caseDetail），**禁止**再 create 出新 set；前置/工具变更走 delete+append | 命令行 / 同一 caseDetail | 目录里堆出重复用例集 | upload |
| P0-10 | 设备角色 `pluginData.id` = 目标空间真实 role_id（脚本自动校验，勿加 `--skip-role-check`） | 上传日志「设备角色校验通过」；或 `autox_case/role/query` 返回非空 | 用例集能建但「没有调试角色」，无法调试（实测 15921991） | upload |

## 设备与编排（P1）

| # | 检查项 | 怎么验 | 漏了会怎样 |
|---|---|---|---|
| P1-1 | 多设备步骤是**同一节点内换行**（一台设备一行），不是挤在一个字符串里无 `\n` | 拉 Bits mind，步骤 `text` 含换行 | 第二台设备拿不到自己的动作 |
| P1-2 | 设备归属：显式前缀 > 唯一角色词 > 句首角色 > 标题角色；「主播地区」等修饰语不判给主播 | 观众侧用例步骤挂在非主播设备 | 操作打到错误设备 |
| P1-3 | 集合内只要有一条多角色，其余单角色用例也带设备占位符 | cases.md 全文 | Bits 设备槽位不一致 |
| P1-4 | 步骤 remark **不带** `<ttat>`；`<ttat>` 只出现在前置条件 | 步骤 note / 前置 note | 标记语义混乱 |
| P1-5 | remark / `**[parallel]**` **不单独成行** | cases.md | BITS 导入器把独立标记行当空预期结果 |

## 测试物料与前置工具（P1）

| # | 检查项 | 怎么验 | 漏了会怎样 |
|---|---|---|---|
| P1-6 | 提测/测试说明/QA 方案**认内容不认标题**，已解析进 `test_kit` | `etd_scope.json.test_kit` | 前置无 env/实验 |
| P1-7 | Precondition 用管道格式：`- mock \| env=...`、`- mock \| ... libra flight/<id>`（给人看+门禁）；可执行节点靠正确工具 | source md + richtext | 散文过不了 G3；工具选错执行失败 |
| P1-8 | `test_kit` 空字段在 `missing[]` 有 reason + gap_id，缺参已反问用户 | `etd_scope.json` / `kb_gaps.json` | 静默空跑 |
| P1-9 | 涉及时才生成：`环境名称` / `libra实验` / `GeckoX_settings` / `ttmock_preset.ab_settings*`；缺必填参数先反问 | 工具列表 + 用户确认 | 工具节点空参执行失败 |

## 埋点矩阵（P1，仅 event2case）

| # | 检查项 | 怎么验 | 漏了会怎样 |
|---|---|---|---|
| P1-10 | 一条用例一个断言时机 =（一个事件 + 一个 `action_type`）；**没有任一操作步骤挂两条埋点断言**；点击用例不对前置曝光断言 | Assert 段 / `run_gates.py` 的 G11 | 埋点合并校验、时机没拆，用例无法直接执行 |
| P1-11 | 用户侧事件 roles 来自 ETD 上报端，未默认主播 | etd_scope roles | 设备写反 |
| P1-11b | 反例形态对：`change_type=param_added`（老埋点加参数）的反例写「仍上报但不带新参」，不是「不上报该埋点」 | `etd_scope.change_type` / `run_gates.py` 的 `反例形态错` | 反例在旧场景必然挂，新参数根本没验（营收 15917403） |
| P1-12 | `run_gates.py` 退出码 0（不能用「我自检过了」代替） | 命令输出 | 弱模型静默漏覆盖 |

## Git / 产物（P1）

| # | 检查项 | 怎么验 | 漏了会怎样 |
|---|---|---|---|
| P1-13 | `biz_line` 用户选定，上传路径 `knowledge-business/ui-test/{biz_line}/`，分支 `tt_nova` | git 远端路径 | 落错目录 |
| P1-14 | UI 执行读的是 **git 文件**；本地改完未 push = 无效 | 远端 blob | 执行仍是旧内容 |
| P1-15 | 改 `skills/` 后已同步 `.agents/skills/`（`diff -rq` 无差） | 双副本 | 跑的是旧逻辑 |

## 上传卫生（P2）

| # | 检查项 | 怎么验 | 漏了会怎样 |
|---|---|---|---|
| P2-1 | 超时后先去 Bits 确认，禁止盲重试 | Bits 目录 | 重复 case set |
| P2-2 | 多个 md 文件不要循环上传成 N 个 set；先合并 | Bits 目录个数 | 历史：28 文件 → 28 set |
| P2-3 | CI/机房上传显式 `--network server` | 命令行 | 打到办公网域名失败 |

## Agent 交付话术（必须对用户说）

交付 Bits 链接前，用下面模板提醒用户自查（只列未自动门禁的项）：

```
交付前请确认：
1. project_id 是否取自 /devops/{id}/（不是 old_id）
2. Bits 步骤节点里：多设备是否换行；remark/git 链接是否在步骤 note
3. 前置每台设备是否都有测试账号；env/libra/AB 是否按正确工具落地；`ab_settings` 是否 JSON 对象（有则必检）
4. 若改过 git 用例：是否已 push，执行读的是远端文件
未确认前不要直接开云上调试。
```
