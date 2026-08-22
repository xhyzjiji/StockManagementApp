# Codebase OpenAPI CLI (`scripts/codebase.py`)

纯标准库实现的 Codebase (code.byted.org) API 命令行工具，支持仓库/分支/MR 查询及 MR 行级评论。

## 目录

- 认证
- 子命令：`get-repository` / `get-branch` / `get-mr` / `get-mr-commits` / `create-comment`
- Python 直接调用

## 认证

脚本会**自动获取** Codebase JWT Token（内部调用 `skills get-codebase-jwt`，失败回退 `npx skills get-codebase-jwt`），一般无需关心。

仅在需要覆盖默认行为时手动提供，优先级从高到低：

1. 命令行参数 `--codebase-jwt <token>`
2. 环境变量 `CODEBASE_JWT`
3. 自动获取（默认）

当 `get-mr-commits` 接收 bits devops change URL 时会额外使用 Cloud JWT 访问 `bits.bytedance.net/api/...`，优先级从高到低：

1. 命令行参数 `--cloud-jwt <token>`
2. 环境变量 `CLOUD_JWT`
3. 自动获取（`skills get-jwt`，失败回退 `npx skills get-jwt`）

详见 `references/auth.md`。

## 子命令

### get-repository — 获取仓库信息

```bash
python3 {SKILL_ROOT}/scripts/codebase.py get-repository \
  --path "<repo_path>"      # 例如 "pdi-qa/agent_report_service"

# 或通过仓库 ID 查询
python3 {SKILL_ROOT}/scripts/codebase.py get-repository \
  --id "<repo_id>"

# 可选：同时返回权限信息
python3 {SKILL_ROOT}/scripts/codebase.py get-repository \
  --path "<repo_path>" --with-permissions
```

从返回 JSON 的 `Result.Repository.Id` 字段取得 `repo_id`。

### get-branch — 获取分支信息

```bash
python3 {SKILL_ROOT}/scripts/codebase.py get-branch \
  --repo-id "<repo_id>" \
  --name "<branch_name>"
```

返回 JSON 中包含分支的最新 commit 信息（`Result.Branch.Commit.Id` 等）。

### get-mr — 获取 Merge Request 详情

```bash
python3 {SKILL_ROOT}/scripts/codebase.py get-mr \
  --repo-id "<repo_id>" \
  --number <mr_number>

# 可选：同时返回 commits 列表
python3 {SKILL_ROOT}/scripts/codebase.py get-mr \
  --repo-id "<repo_id>" \
  --number <mr_number> \
  --with-commits
```

返回 JSON 示例（含 `--with-commits` 时的关键字段）：

```json
{
  "Result": {
    "MergeRequest": {
      "SourceBranch": "feature/xxx",
      "TargetBranch": "master",
      "Commits": [
        {"Id": "abc1234"},
        {"Id": "def5678"}
      ]
    }
  }
}
```

- `from_commit` = `Commits` 列表中**最早**那条的 `Id`（列表末尾，时间最早）
- `to_commit` = `Commits` 列表中**最新**那条的 `Id`（列表开头，时间最近）

> 注意：若只需获取 MR 的 commit 范围，推荐使用 `get-mr-commits` 子命令，更简洁。

### get-mr-commits — 获取 MR 的 commit 范围

快捷获取 Merge Request 的首尾 commit，用于确定 code review 的审查范围。

```bash
# 通过 MR URL
python3 {SKILL_ROOT}/scripts/codebase.py get-mr-commits \
  --url "<mr_url>"    # 例如 https://code.byted.org/org/repo/merge_requests/123

# 通过 bits devops change URL
python3 {SKILL_ROOT}/scripts/codebase.py get-mr-commits \
  --url "https://bits.bytedance.net/devops/<ns>/develop/detail/<devBasicId>/change/<changeId>"

# 通过 repo-id + MR 编号
python3 {SKILL_ROOT}/scripts/codebase.py get-mr-commits \
  --repo-id "<repo_id>" --number <mr_number>
```

返回 JSON 示例：

```json
{
  "from_commit": "abc1234",
  "to_commit": "def5678"
}
```

- `from_commit`：MR 中最早的 commit
- `to_commit`：MR 中最新的 commit

> 推荐在 code review 场景中优先使用此命令，而非手动调用 `get-mr --with-commits` 再自行提取。

### create-comment

在 MR 上创建行级评论。**推荐**直接传 `--url`，脚本会内部调 `get-repository` + `get-mr --with-versions`，自动推断 `repo_id` / `commentable_id` 以及最新 Version 的 base/source commit，避免手动串联多次 API。

| 参数               | 必填                  | 说明                                              |
| ------------------ | --------------------- | ------------------------------------------------- |
| `--url`            | 推荐                  | MR 链接；传入后下面 4 个 ID 都可省略，自动推断    |
| `--repo-id`        | 不传 `--url` 时必填   | 仓库 ID                                           |
| `--commentable-id` | 不传 `--url` 时必填   | MR 内部 ID（= `get-mr` 返回的 `Result.MergeRequest.Id`，非 Number） |
| `--old-commit-id`  | 不传 `--url` 时必填   | Base commit ID（默认取最新 Version 的 `BaseCommitId`）  |
| `--new-commit-id`  | 不传 `--url` 时必填   | Source commit ID（默认取最新 Version 的 `SourceCommitId`）|
| `--content`        | 是                    | 评论内容                                          |
| `--path`           | 是                    | 文件路径                                          |
| `--start-line`     | 是                    | 起始行号                                          |
| `--end-line`       | 是                    | 结束行号                                          |

> `--url` 传入后，仍可显式提供任一 ID 覆盖自动推断值（例如评论到历史 Version 而非最新）。

```bash
# 推荐：通过 MR URL 一步打评论
python3 {SKILL_ROOT}/scripts/codebase.py create-comment \
  --url "https://code.byted.org/pdi-qa/agent_report_service/merge_requests/696" \
  --content "此处存在并发安全问题" \
  --path "src/service/user.go" \
  --start-line 42 \
  --end-line 45

# 需要精确控制时，也可显式传所有 ID
python3 {SKILL_ROOT}/scripts/codebase.py create-comment \
  --repo-id "123456" \
  --commentable-id "789" \
  --content "此处存在并发安全问题" \
  --old-commit-id "abc123" \
  --new-commit-id "def456" \
  --path "src/service/user.go" \
  --start-line 42 \
  --end-line 45
```

## Python 直接调用

脚本中的函数可直接 import 使用，无需通过 CLI：

```python
from scripts.codebase import (
    resolve_jwt,
    resolve_cloud_jwt,
    get_repository,
    get_branch,
    get_merge_request,
    get_mr_commits,
    create_comment,
    parse_mr_url,
    parse_change_url,
)

jwt = resolve_jwt()  # 从环境变量读取

# 获取 MR commit 范围（支持 MR URL 与 bits change URL）
commits = get_mr_commits(url="https://code.byted.org/org/repo/merge_requests/123", jwt_token=jwt)
# {"from_commit": "...", "to_commit": "..."}

# 创建行级评论
create_comment(
    repo_id="123456",
    commentable_id="789",
    content="问题描述",
    old_commit_id=commits["from_commit"],
    new_commit_id=commits["to_commit"],
    path="src/file.go",
    start_line=10,
    end_line=12,
    jwt_token=jwt,
)
```
