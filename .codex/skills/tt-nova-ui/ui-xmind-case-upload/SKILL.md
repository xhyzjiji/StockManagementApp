---
name: ui-xmind-case-upload
description: Upload or update UI test cases (*_cases.md + *_richtext.md) on bits via TTAT OpenAPI. create=新建用例集；update=对已有 case_set_id 做 upsert（前置/工具变更走 delete+append 整条重写）。Use when the user mentions "上传用例", "更新用例", "update case set", "导入用例", "同步到 bits", or provides a Bits caseDetail link plus markdown case files.
---

# UI Xmind Case Upload

上传 `*_cases.md` + `*_richtext.md` 到 bits 用例平台。上传时自动给所有标题加 `[TT-Nova]` 前缀。

两种模式：
- **create**（默认）：`upload_bits_test_case_mind` 新建用例集，需要 `project_id` + `dir_id`
- **update**：对已有 `case_set_id` 做 upsert（每条：`delete_subtree` → `append_branch`），需要 `project_id` + `case_set_id`。前置条件加/改工具只能走这条（`update_node` 改不了前置）

本 skill 自身不生产正式 Markdown 中间产物；它消费上游 skill 已经生成好的文件。标准输入位置优先使用：

- `tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_cases.md`
- `tt-nova/ui/business/{vc}/{module}/xmind/{ui_path}_richtext.md`
- 或 `tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/{ui_path}_cases.md`
- 或 `tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/{ui_path}_richtext.md`

若上传前需要生成请求预览、校验脚本或临时 payload，一律写到：

- `tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-upload/...`

## Trigger Conditions

Activate when:
- User mentions "上传用例", "更新用例", "update case set", "导入用例", "同步到 bits"
- User provides Bits `caseDetail` 链接并要求在同一用例集上改前置/工具/步骤
- User provides `*_cases.md` / `*_richtext.md` 并要求上传

**Do not activate** for:
- 用例生成 → use **ui-xmind-case-gen** skill
- 原始 Markdown 一键转换上传 → use **ui-md-case-upload** skill（它会再调本脚本）

---

## Workflow

### create

```
确认 cases/richtext → 解析 project_id + dir_id → upload_cases.py --mode create
```

### update（推荐：老 Bits 链接 + 改完的包）

```
1. 用户给老 Bits caseDetail 链接（或 --case-set-id）
2. 确认/生成改后的 *_cases.md + *_richtext.md（前置加工具等）
3. 先 --dry-run 打印 upsert 计划，用户确认
4. upload_cases.py --mode update → 每条 delete_subtree + append_branch
5. 回同一个 caseDetail 链接
```

读回 Bits 脑图做编辑时：先用 `ui-md-case-gen` 的 `fetch_bits_case.py` 拉详情，改完再走本 skill 的 update。本脚本只负责写回。

---

## Step 1: 确认输入文件

用户需提供两个文件：
- `*_cases.md` — 测试用例 markdown
- `*_richtext.md` — richtext 绑定 JSON

确认两个文件的**绝对路径**。若只提供了一个，在同目录下按前缀匹配另一个。

---

## Step 2: 解析目标

### 从 bits 链接解析

```
https://bits.bytedance.net/devops/<project_id>/quality/case/caseDetail/<case_set_id>?...&dirId=<dir_id>
```

| 参数 | 取自 | 模式 |
|---|---|---|
| `--project_id` | URL 路径 **`/devops/{id}/`** | create / update |
| `--case-set-id` | 路径 `caseDetail/{id}` | **update 必填** |
| `--dir_id` | query `dirId` | **create 必填** |

**禁止**用 query 里的 `devops_space_old_id` / `projectId=`（旧空间 id）当 `project_id`。

也可用 `--bits-url '<整段链接>'` 一次解析。

### 缺失时提示

> 新建请提供 project_id + dir_id；更新请提供 Bits caseDetail 链接（或 project_id + case_set_id）。不要猜。

### 设备 richtext 与空间（space_id）必须匹配

`*_richtext.md` 里的**设备角色**绑定的 `pluginData.id` 必须等于目标空间的真实 role_id。上传前脚本会自动查 `POST bits-cn-gw.bytedance.net/test_case/role/list` 比对，对不上直接报错（角色 id 错时用例集上传成功但 bits 提示「没有调试角色」，无法调试）。

校验需要 ByTest 登录态（`gdpa-cli login cn`，或 `BYTEST_JWT`）。`--skip-role-check` 可跳过，仅在明确知道后果时用。

---

## Step 3: 调用上传脚本

### create

```bash
python3 skills/tt-nova-ui/ui-xmind-case-upload/scripts/upload_cases.py \
    --mode create \
    --cases /abs/path/{ui_path}_cases.md \
    --richtext /abs/path/{ui_path}_richtext.md \
    --project_id <project_id> \
    --dir_id <dir_id> \
    --env prod \
    --network office
```

### update（同一用例集；前置加工具走整条重写）

```bash
# 先看计划
python3 skills/tt-nova-ui/ui-xmind-case-upload/scripts/upload_cases.py \
    --mode update --dry-run \
    --cases /abs/path/{ui_path}_cases.md \
    --richtext /abs/path/{ui_path}_richtext.md \
    --bits-url 'https://bits.bytedance.net/devops/1499051266/quality/case/caseDetail/15258509' \
    --env prod --network office

# 只改若干条
python3 skills/tt-nova-ui/ui-xmind-case-upload/scripts/upload_cases.py \
    --mode update \
    --cases /abs/path/{ui_path}_cases.md \
    --richtext /abs/path/{ui_path}_richtext.md \
    --project_id 1499051266 \
    --case-set-id 15258509 \
    --only-case-title 'TC-R-001 最近三场合格 LIVE ASR 数据可用于生成模板' \
    --env prod --network office

# 额外删除（标题可省略 [TT-Nova]，脚本会补）
python3 skills/tt-nova-ui/ui-xmind-case-upload/scripts/upload_cases.py \
    --mode update \
    --cases /abs/path/{ui_path}_cases.md \
    --richtext /abs/path/{ui_path}_richtext.md \
    --bits-url '...' \
    --delete-case 'Group Title|||Case Title To Remove' \
    --env prod --network office
```

`--env` / `--network` 与原先一致（ppe/prod × office/server）。

Use `block_until_ms: 0` 和 `required_permissions: ["full_network"]` 跑真实请求。

**重要：每条原子调用只执行一次，不重试。** 超时先去 Bits 确认，禁止盲重试。

update 语义：本地 md 里选中的每条用例 = 先删后挂；标题必须与 Bits 上一致（脚本会加 `[TT-Nova]`）。找不到旧分支时 delete 会跳过再 append（新建到该 set）。

### 验证输出

**create 成功**：打印 `SUCCESS` 与 projectId/dirId。  
**update 成功**：打印每条 `deleted` / `appended`，并给出同一个 caseDetail 链接。

---

## API Reference

| 模式 | Endpoint |
|---|---|
| create | `POST /ui/open_api/upload_bits_test_case_mind` |
| update delete | `POST /ui/open_api/bits_case_atomic/delete_subtree` |
| update append | `POST /ui/open_api/bits_case_atomic/append_branch` |

- office: `https://ttat-openapi-sg.tiktok-row.net`
- server: `https://ttat-openapi-sg.byteintl.net`
- 自检：`python3 .../upload_cases.py --self-check`
