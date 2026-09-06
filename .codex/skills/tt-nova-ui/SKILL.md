---
name: tt-nova-ui
description: "TT Nova UI 自动化测试 skill 集合，覆盖 spec 生成、XMind 用例生成、Markdown 用例生成、上传和云上调试执行。当用户提到 UI 自动化、UI 测试、spec、用例生成、脑图用例、Markdown 用例、上传用例、智能调试、调试任务或 case_set_id 执行时自动路由到对应子 skill。"
---

# TT Nova UI 自动化测试 Skill 集

覆盖 UI 自动化测试的两条主路径：**spec → XMind cases → 上传 → 云上调试执行**，以及 **脑图/Markdown → 本地 Markdown → 上传 → 云上调试执行**。6 个子 skill 各自承担一个独立职责，按输入类型协作。

---

## 统一产物路径

6 个子 skill 的中间产物统一遵循以下目录契约（以当前仓库根目录为 `<repo_root>`）：

- **XMind（BITS）关键产物**：
  - `<repo_root>/tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_spec.md`
  - `<repo_root>/tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_cases.md`
  - `<repo_root>/tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_richtext.md`
- **Markdown（适配 AppUse）关键产物**：
  - `<repo_root>/tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md`
- **临时中间产物**：
  - `<repo_root>/tt-nova/ui/tmp/{vc}/{module}/{skill_name}/...`

约束说明：

- `ui_path` 只表示模块级文件 stem，不再自带 `_spec` / `_cases` / `_richtext` 后缀。
- `skill_name` 固定使用 6 个子 skill 的目录名：`ui-xmind-case-specify`、`ui-xmind-case-gen`、`ui-md-case-gen`、`ui-md-case-upload`、`ui-xmind-case-upload`、`ui-debug-task-exec`。
- `ui-xmind-case-specify` 负责写入 `xmind/{ui_path}_spec.md`。
- `ui-xmind-case-gen` 负责写入 `xmind/{ui_path}_cases.md` 与 `xmind/{ui_path}_richtext.md`。
- `ui-md-case-gen` 负责写入 `md/{ui_path}_cases.md`。
- `ui-md-case-upload`、`ui-xmind-case-upload` 与 `ui-debug-task-exec` 仅在需要时生成辅助文件，这些文件统一放到 `tt-nova/ui/tmp/{vc}/{module}/{skill_name}/`。
- 所有 JSON、Prompt、Coverage 报告、manifest、验证脚本、临时调试文件统一放到 `tt-nova/ui/tmp/{vc}/{module}/{skill_name}/` 下。

---

## 版本说明（vendored 内置副本，无自动更新）

本目录是随 `ttadk/mobile-core` 插件分发的**固定版本副本**（tt-nova-ui 1.0.156，vendored 自
`skills.byted.org/ttat/tt_nova`）。原版的「每日自更新」前置步骤在此副本中**移除**：
- 不检查 `/tmp/.skill-tt-nova-ui-updated`，不执行任何 agentbuddy/npx 更新命令，直接进入下方路由；
- 目的：版本确定、离线可用（自更新中断会留下只有目录没有 SKILL.md 的空壳，曾导致探测假阳性）。

升级方式：维护者以新版本包替换本目录后随 mobile-core 发版。临时想用官方最新版可手动执行
`npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-ui --agent claude-code --yes`
覆盖本地副本（下次 `ttadk plugin update` 会还原为内置版本）。

---

## 子 Skill 索引

| # | 子 Skill | 定位 | 子技能路径 |
|---|---------|------|-----------|
| 1 | **ui-xmind-case-gen** | 从 spec 生成可执行的 UI 自动化测试用例 | [ui-xmind-case-gen/SKILL.md](ui-xmind-case-gen/SKILL.md) |
| 2 | **ui-md-case-gen** | 将 BITS 脑图用例改写为本地 Markdown UI 用例 | [ui-md-case-gen/SKILL.md](ui-md-case-gen/SKILL.md) |
| 3 | **ui-md-case-upload** | 将 Markdown 用例转换并上传到 bits（create 新建 / update 同一 case_set），或直传已有 `*_cases.md` + `*_richtext.md` | [ui-md-case-upload/SKILL.md](ui-md-case-upload/SKILL.md) |
| 4 | **ui-xmind-case-upload** | 上传或更新 `*_cases.md` + `*_richtext.md` 到 bits（update=delete+append upsert） | [ui-xmind-case-upload/SKILL.md](ui-xmind-case-upload/SKILL.md) |
| 5 | **ui-xmind-case-specify** | 从 PRD、手工用例或 BITS 用例生成测试规格文档（spec） | [ui-xmind-case-specify/SKILL.md](ui-xmind-case-specify/SKILL.md) |
| 6 | **ui-debug-task-exec** | 基于已有 `case_set_id` 和安装包信息创建/预检 ByTest/Bits 云上调试任务 | [ui-debug-task-exec/SKILL.md](ui-debug-task-exec/SKILL.md) |
| 7 | **ui-md-event2case-gen** | 从埋点需求（PRD + ETD + 提测 + 可选 MR）生成 BITS xmind + 自动化 md；矩阵范围=本需求 ETD 正文（先 `etd_scope.json`，R12–R16）；Path 从 App 主页起 | [ui-md-event2case-gen/SKILL.md](ui-md-event2case-gen/SKILL.md) |

---

## 路由规则

根据用户意图自动匹配子 skill，**不要求用户点名子 skill**。

| 用户意图 / 触发信号 | 路由目标 |
|-------------------|---------|
| 提供 `spec.md`（含 Raw Case Seeds），要求生成测试用例；说 "生成用例"、"generate cases" | **ui-xmind-case-gen** |
| 提供 bits 脑图用例链接 / case ID，要求改写为本地 Markdown UI 用例 | **ui-md-case-gen** |
| 提供原始 Markdown 用例或 `cases.md` + `richtext.md`，希望一键转换并上传；或给老 Bits caseDetail 链接要求更新同一用例集 | **ui-md-case-upload** |
| 要求上传/更新 `*_cases.md` + `*_richtext.md` 到 bits；说 "上传用例"、"更新用例"、"update case set"、"导入用例"、"同步到 bits" | **ui-xmind-case-upload** |
| 提供 PRD / 飞书文档，要求生成测试规格；提供 xlsx/md 手工用例要求结构化；或提供 BITS 链接 / case ID 希望直接转 spec；说 "生成 spec"、"测试规格" | **ui-xmind-case-specify** |
| 要求云上调试、智能调试、创建/执行调试任务；提供 `project_id` + `case_set_id` + 安装包 URL；说 "run debug"、"debug task"、"执行 case_set" | **ui-debug-task-exec** |
| 提供**埋点需求**（PRD + 埋点设计文档 / ETD + 提测文档，可选 MR 包），要求生成埋点测试用例 / 埋点验证用例 / tracking case；说 "埋点用例"、"埋点验证"、"tracking case" | **ui-md-event2case-gen** |

**歧义处理**：当用户意图不明确时，列出候选子 skill 并一次性询问，不要猜测。

---

## 流水线协作关系

```
ui-xmind-case-specify
   │  输入: PRD / 飞书文档 / 手工用例 xlsx/md / BITS case URL
   │  输出: `tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_spec.md`
   ▼
ui-xmind-case-gen
   │  输入: spec.md
   │  输出: `tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_cases.md`
   │        `tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_richtext.md`
   ▼
   └─► ui-xmind-case-upload ──► bits 平台
          输入: `*_cases.md` + `*_richtext.md` + project_id + dir_id
          输出: bits case set / case_set_id（若接口未返回则由用户提供）
          └─► ui-debug-task-exec ──► ByTest/Bits 云上调试任务
                 输入: project_id + case_set_id + 安装包 / mapping URL

ui-md-case-gen
   │  输入: bits 脑图用例 / case URL / case ID
   │  输出: `tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md`
   ▼
ui-md-case-upload
          输入: 原始 Markdown 或 `md/{ui_path}_cases.md`
          输出: bits 平台
          └─► ui-debug-task-exec ──► ByTest/Bits 云上调试任务
                 输入: project_id + case_set_id + 安装包 / mapping URL

ui-md-event2case-gen（埋点需求专用）
   │  输入: PRD + ETD + 提测文档 + **biz_line**（必选）+ 可选 MR；知识源 live_tracking_knowledge_base
   │  输出: 自动化用例 → git `tt_nova` 分支
   │        live_tracking_knowledge_base/knowledge-business/ui-test/{biz_line}/{ui_path}_cases.md
   │        biz_line ∈ {SMB, activity_platform, game, multi_guest, revenue, user_product, wallet}
   │        `xmind/{ui_path}_cases.md` + `{ui_path}_richtext.md`（人读+可执行 BITS 用例）
   ▼
   └─► ui-md-case-upload / ui-xmind-case-upload ──► bits（备注 source_url = 自动化 md 的 git 地址，不走 TOS）
          └─► ui-debug-task-exec ──► 云上调试执行
```

### 子 Skill 说明

**ui-xmind-case-gen** — 用例生成

从 spec.md 的 Seeds 表出发，通过规则引擎（导航链、设备角色、工具注册）+ LLM（步骤展开）生成可执行的 TestModel JSON，再渲染为 `tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_cases.md` 和 `.../{ui_path}_richtext.md`。支持按 Feature 并行生成、大规模分批处理（>50 条）。

**ui-md-case-gen** — Markdown 用例生成

将 BITS 脑图用例改写为“AI 可执行 + 人工可读”的本地 Markdown UI 用例，正式产物统一落到 `tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md`，强调明确入口、页面路径、视觉锚点和可观察断言。

**ui-md-case-upload** — Markdown 用例转换上传

支持两种模式：直接消费 `tt-nova/ui/business/{vc}/{module}/md/{ui_path}_cases.md` 或原始 Markdown，再在 `tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/` 下生成上传辅助文件并导入 bits；也支持直传已有的 `*_cases.md` / `*_richtext.md` 对。`--mode create` 新建用例集；`--mode update` 对已有 `case_set_id` 做 upsert（前置/工具变更走 delete+append）。

**ui-xmind-case-upload** — 用例上传 / 更新

将 `*_cases.md` + `*_richtext.md` 通过 TTAT OpenAPI 写到 bits。create 需要 `project_id`+`dir_id`；update 需要 `project_id`+`case_set_id`（可用 Bits caseDetail 链接）。通常消费 `ui-xmind-case-gen` 正式产物或 `ui-md-case-upload` 临时上传包。

**ui-xmind-case-specify** — 测试规格生成

支持两种模式：**测新**（从 PRD 推导功能点、场景、Seeds）和**回归**（从手工用例 xlsx/md 或 BITS 用例结构化为 spec）。输出标准化的 7 章 spec 文档到 `tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_spec.md`，其中第 7 章 Raw Case Seeds 是下游 ui-xmind-case-gen 的直接输入。

**ui-debug-task-exec** — 云上调试执行

基于已有 `project_id`、`case_set_id`、安装包 URL 和可选 mapping URL，走官方 ByTest/Bits API dry-run、preflight 或创建云上智能调试任务。通常接在 `ui-xmind-case-upload` / `ui-md-case-upload` 之后，也支持用户直接提供已有 `case_set_id` 独立执行。调试 manifest 统一落到 `tt-nova/ui/tmp/{vc}/{module}/ui-debug-task-exec/{ui_path}_debug_task_manifest.json`。

**ui-md-event2case-gen** — 埋点需求用例生成

针对**埋点需求**：输入 PRD + 埋点设计文档（ETD）+ **提测文档**（包/ppe/实验）+ **biz_line**（业务线目录，未指定必须反问）+ 可选 MR 包，结合 `live_tracking_knowledge_base` 生成两份对齐产物——自动化 md（KB `knowledge-business/ui-test/{biz_line}/`，分支 **`tt_nova`**）与 BITS xmind。**矩阵范围权威=本需求 ETD 正文**：写终稿前必须落盘并校验 `etd_scope.json`（R12–R16），禁止 GT/外链扩维。`**Path**` 从 App 主页起；事件清单锁定本需求 ETD；断言以自然语言为主，可叠加 `et_checker_G20`。只生成不自动上传 bits（备注用 git `source_url`）。

---

## 交付前检查（隐性问题，强制提醒）

历史上大量故障是「上传成功 / 门禁绿了，但 Bits 上节点不对、执行才炸」。完整清单见：

→ [`references/case-delivery-checklist.md`](references/case-delivery-checklist.md)

**任一子 skill 在给出 Bits 链接或宣称交付前，必须：**
1. 核对清单中全部 **P0** 项（未过则先修或反问用户，禁止直接交付）
2. 用清单末尾「Agent 交付话术」模板，把未自动门禁的项当面提醒用户

高频 P0 速查：`project_id` 取自 `/devops/{id}/`（不是 old_id）；remark/git 在**步骤末行**；多设备步骤必须换行；每台设备有真实动作 + 测试账号；env→`环境名称`、libra→`libra实验`（**仅当有 Libra 链接**且缺 group_id 时分别问实验组/对照组，见 [references/libra-group-assignment.md](references/libra-group-assignment.md)）、AB KV→`ttmock ab_settings` JSON 对象且先 `check-json-object`（勿混塞）；Git 显式 `ref`；埋点 Assert 只验埋点。

---

## 使用规则

1. **按需路由**：本 SKILL.md 是入口索引，具体执行逻辑在各子 skill 中。匹配到子 skill 后，`Read` 对应的 SKILL.md 获取完整指引。
2. **流水线可断点续跑**：用户可以从任意阶段开始（如已有 spec.md 直接跑 ui-xmind-case-gen，已有 Markdown 直接跑 ui-md-case-upload，已有 case_set_id 直接跑 ui-debug-task-exec），不要求从头走完全流程。
3. **路径区分**：`xmind` 路径聚焦 spec → cases → upload，`md` 路径聚焦脑图/Markdown → 转换/上传，`ui-debug-task-exec` 聚焦 case_set 云上调试执行；路由时按用户输入类型选择对应 skill。
4. **API 域名**：ui-md-case-upload 和 ui-xmind-case-upload 保留各自子 skill 的既有上传环境参数。ui-debug-task-exec 使用 ByTest/Bits 官方调试接口，按其子 skill 的 `--bytest_base`、`--bits_base` 和 JWT 规则执行；当使用 app 快捷参数时，用户侧只需确认 TTP App 的 `platform`（Android / iOS）和可选版本，默认应用为 `musically`、分类为 `ttp`，并通过办公网 TTAT `ui/get_app_conf_list`（`ttat-openapi-sg.tiktok-row.net`）解析安装包；`ui/get_layout` 为 best-effort，用于补充 layout mapping，鉴权失败不会阻断 dry-run。`--ttat_base` 仅用于特殊域名覆盖，临时泳道 header 需要用 `--ttat_header KEY=VALUE` 显式传入。
5. **交付检查**：上传或交付前按 [`references/case-delivery-checklist.md`](references/case-delivery-checklist.md) 过 P0，并向用户复述关键风险点。
