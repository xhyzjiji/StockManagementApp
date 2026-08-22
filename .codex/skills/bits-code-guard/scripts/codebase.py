#!/usr/bin/env python3

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

BASE_URL = "https://code.byted.org/api/v2/"
BITS_BASE_URL = "https://bits.bytedance.net"

# bits devops change 详情页 URL，例如：
# https://bits.bytedance.net/devops/3911129090/develop/detail/2270782/change/3432868?devops_space_type=server_fe
CHANGE_URL_RE = re.compile(
    r"bits\.bytedance\.net/devops/\d+/develop/detail/(\d+)/change/(\d+)"
)

# ---------- SSL ----------
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


# ---------- Auth ----------
def fetch_codebase_jwt() -> str:
    """调用 skills CLI 自动获取 Codebase JWT，优先直接命令，失败回退 npx。"""
    errors: List[str] = []
    for cmd in (["skills", "get-codebase-jwt"], ["npx", "skills", "get-codebase-jwt"]):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError as e:
            errors.append(f"{' '.join(cmd)}: {e}")
            continue
        except subprocess.TimeoutExpired:
            errors.append(f"{' '.join(cmd)}: timeout")
            continue
        token = result.stdout.strip()
        if result.returncode == 0 and token:
            return token
        errors.append(
            f"{' '.join(cmd)} rc={result.returncode}: {result.stderr.strip()}"
        )
    raise RuntimeError("; ".join(errors) or "no command available")


def resolve_jwt(codebase_jwt: Optional[str] = None) -> str:
    """解析 JWT token：优先 AIME_USER_CODE_JWT 环境变量，其次命令行参数，
    再次 CODEBASE_JWT 环境变量，最后尝试通过 skills CLI 自动获取；全部失败才报错退出。"""
    aime_token = os.environ.get("AIME_USER_CODE_JWT", "").strip()
    if aime_token:
        return aime_token
    if codebase_jwt:
        return codebase_jwt
    env_token = os.environ.get("CODEBASE_JWT")
    if env_token:
        return env_token
    try:
        return fetch_codebase_jwt()
    except Exception as e:
        print(
            "Error: 未获取到 Codebase JWT token。\n"
            "  自动获取失败: " + str(e) + "\n"
            "  可通过 --codebase-jwt 参数或 CODEBASE_JWT 环境变量手动传入。",
            file=sys.stderr,
        )
        sys.exit(1)


def fetch_cloud_jwt() -> str:
    """调用 skills CLI 自动获取 Cloud JWT，优先直接命令，失败回退 npx。"""
    errors: List[str] = []
    for cmd in (["skills", "get-jwt"], ["npx", "skills", "get-jwt"]):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError as e:
            errors.append(f"{' '.join(cmd)}: {e}")
            continue
        except subprocess.TimeoutExpired:
            errors.append(f"{' '.join(cmd)}: timeout")
            continue
        token = result.stdout.strip()
        if result.returncode == 0 and token:
            return token
        errors.append(
            f"{' '.join(cmd)} rc={result.returncode}: {result.stderr.strip()}"
        )
    raise RuntimeError("; ".join(errors) or "no command available")


def resolve_cloud_jwt(cloud_jwt: Optional[str] = None) -> str:
    """解析 Cloud JWT token：优先 AIME_USER_CLOUD_JWT 环境变量，其次命令行参数，
    再次 CLOUD_JWT 环境变量，最后尝试通过 skills CLI 自动获取；全部失败才报错退出。"""
    aime_token = os.environ.get("AIME_USER_CLOUD_JWT", "").strip()
    if aime_token:
        return aime_token
    if cloud_jwt:
        return cloud_jwt
    env_token = os.environ.get("CLOUD_JWT")
    if env_token:
        return env_token
    try:
        return fetch_cloud_jwt()
    except Exception as e:
        print(
            "Error: 未获取到 Cloud JWT token。\n"
            "  自动获取失败: " + str(e) + "\n"
            "  可通过 --cloud-jwt 参数或 CLOUD_JWT 环境变量手动传入。",
            file=sys.stderr,
        )
        sys.exit(1)


def get_headers(jwt_token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Code-User-JWT": jwt_token,
    }


# ---------- HTTP ----------
def call_api(action: str, payload: Dict[str, Any], jwt_token: str) -> Dict[str, Any]:
    """向 Codebase OpenAPI 发起 POST 请求并返回 JSON 响应。"""
    url = f"{BASE_URL}?Action={action}"
    data = json.dumps(payload).encode("utf-8")
    headers = get_headers(jwt_token)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Error calling API {action}: HTTP {e.code}\n{body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error calling API {action}: {e.reason}", file=sys.stderr)
        sys.exit(1)


# ---------- Actions ----------
def get_repository(
    path: Optional[str] = None,
    repo_id: Optional[str] = None,
    with_permissions: bool = False,
    jwt_token: str = "",
) -> Dict[str, Any]:
    """获取仓库信息。至少传入 path 或 repo_id 之一。"""
    payload: Dict[str, Any] = {}
    if path:
        payload["Path"] = path
    if repo_id:
        payload["Id"] = repo_id
    if with_permissions:
        payload["WithPermissions"] = True

    if not payload:
        print("Error: Either path or repo_id must be provided.", file=sys.stderr)
        sys.exit(1)

    return call_api("GetRepository", payload, jwt_token)


def get_branch(repo_id: str, name: str, jwt_token: str = "") -> Dict[str, Any]:
    """获取分支信息。"""
    payload = {"RepoId": repo_id, "Name": name}
    return call_api("GetBranch", payload, jwt_token)


def get_merge_request(
    repo_id: str,
    number: Optional[int] = None,
    mr_id: Optional[str] = None,
    change_id: Optional[str] = None,
    with_commits: bool = False,
    with_versions: bool = False,
    jwt_token: str = "",
) -> Dict[str, Any]:
    """获取 Merge Request 详情。需提供 number / mr_id / change_id 之一。"""
    payload: Dict[str, Any] = {"RepoId": repo_id}
    if number is not None:
        payload["Number"] = number
    elif mr_id:
        payload["Id"] = mr_id
    elif change_id:
        payload["ChangeId"] = change_id
    else:
        print(
            "Error: Provide --number, --id, or --change-id.",
            file=sys.stderr,
        )
        sys.exit(1)

    if with_commits:
        payload["WithCommits"] = True

    if with_versions:
        payload["Selector"] = {"Version": True}

    return call_api("GetMergeRequest", payload, jwt_token)


def create_comment(
    repo_id: str,
    commentable_id: str,
    content: str,
    old_commit_id: str,
    new_commit_id: str,
    path: str,
    start_line: int,
    end_line: int,
    jwt_token: str = "",
) -> Dict[str, Any]:
    """在 MR 上创建行级评论。"""
    payload: Dict[str, Any] = {
        "CommentableType": "merge_request",
        "CommentableId": commentable_id,
        "RepoId": repo_id,
        "Content": content,
        "Position": {
            "Type": "content",
            "Side": "new",
            "OldCommitId": old_commit_id,
            "NewCommitId": new_commit_id,
            "Path": path,
            "StartLine": start_line,
            "StartColumn": 1,
            "EndLine": end_line,
            "EndColumn": 1000,
        },
    }
    return call_api("CreateComment", payload, jwt_token)


def parse_change_url(url: str) -> Tuple[int, int]:
    """从 bits devops change URL 中解析出 (dev_basic_id, change_id)。

    支持形如：
    - https://bits.bytedance.net/devops/3911129090/develop/detail/2270782/change/3432868
    - 带查询参数的同类链接
    """
    m = CHANGE_URL_RE.search(url)
    if not m:
        print(f"Error: 无法解析 bits change URL: {url}", file=sys.stderr)
        sys.exit(1)
    return int(m.group(1)), int(m.group(2))


def fetch_bits_change_mr_url(
    dev_basic_id: int, change_id: int, cloud_jwt: str
) -> str:
    """调 bits /api/v1/dev/task/changes?devBasicId=... 获取对应 change 的 MR URL。

    从 data.changeList 里按 change.id 精确匹配，返回
    change.manifest.codeElement.url（一条已支持解析的 bits/codebase MR URL）。
    """
    api_url = f"{BITS_BASE_URL}/api/v1/dev/task/changes?devBasicId={dev_basic_id}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "x-jwt-token": cloud_jwt,
    }
    req = urllib.request.Request(api_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(
            f"Error calling bits task/changes: HTTP {e.code}\n{detail}",
            file=sys.stderr,
        )
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error calling bits task/changes: {e.reason}", file=sys.stderr)
        sys.exit(1)

    change_list = (body.get("data") or {}).get("changeList") or []
    if not change_list:
        print(
            f"Error: bits devBasicId={dev_basic_id} 的 changeList 为空，"
            "请确认链接是否正确。",
            file=sys.stderr,
        )
        sys.exit(1)

    for item in change_list:
        change = item.get("change") or {}
        if change.get("id") == change_id:
            code_element = (change.get("manifest") or {}).get("codeElement") or {}
            mr_url = code_element.get("url")
            if not mr_url:
                print(
                    f"Error: change id={change_id} 缺少 codeElement.url，"
                    "无法推断 MR 链接。",
                    file=sys.stderr,
                )
                sys.exit(1)
            return mr_url

    available = ", ".join(str((c.get("change") or {}).get("id")) for c in change_list)
    print(
        f"Error: 在 devBasicId={dev_basic_id} 的 changeList 中未找到 "
        f"change id={change_id}（现有 change ids: {available}）。",
        file=sys.stderr,
    )
    sys.exit(1)


def parse_mr_url(url: str) -> Tuple[str, int]:
    """从 MR URL 中解析出 (repo_path, mr_number)。
    支持两种 URL 格式：
    - https://code.byted.org/pdi-qa/agent_report_service/merge_requests/513
    - https://bits.bytedance.net/code/ugc/Aweme/merge_requests/290510
    """
    m = re.search(r"code\.byted\.org/(.+)/merge_requests/(\d+)", url)
    if not m:
        m = re.search(r"bits\.bytedance\.net/code/(.+)/merge_requests/(\d+)", url)
    if not m:
        print(f"Error: 无法解析 MR URL: {url}", file=sys.stderr)
        sys.exit(1)
    return m.group(1), int(m.group(2))


def resolve_mr_context(url: str, jwt_token: str) -> Dict[str, str]:
    """从 MR URL 解析出打评论 / 取 commit 范围所需的全部字段。

    返回 repo_id、mr_id（=commentable_id）、以及最新 Version 的 base/source commit。
    复用给 get-mr-commits 和 create-comment --url 两个场景。
    """
    repo_path, mr_number = parse_mr_url(url)
    repo_resp = get_repository(path=repo_path, jwt_token=jwt_token)
    repo_id = repo_resp.get("Result", {}).get("Repository", {}).get("Id")
    if not repo_id:
        print(f"Error: 无法从仓库路径 {repo_path} 获取 repo_id", file=sys.stderr)
        sys.exit(1)

    mr_resp = get_merge_request(
        repo_id=repo_id, number=mr_number, with_versions=True, jwt_token=jwt_token
    )
    mr = mr_resp.get("Result", {}).get("MergeRequest", {})
    mr_id = mr.get("Id", "")
    if not mr_id:
        print("Error: MR 响应缺少 Id（commentable_id）", file=sys.stderr)
        sys.exit(1)

    versions = mr.get("Versions", [])
    if not versions:
        print("Error: MR 未返回 Versions 数据", file=sys.stderr)
        sys.exit(1)
    latest = max(versions, key=lambda v: v.get("Number", 0))
    base = latest.get("BaseCommitId", "")
    source = latest.get("SourceCommitId", "")
    if not base or not source:
        print("Error: Versions 中缺少 BaseCommitId 或 SourceCommitId", file=sys.stderr)
        sys.exit(1)

    return {
        "repo_id": repo_id,
        "mr_id": mr_id,
        "base_commit_id": base,
        "source_commit_id": source,
    }


def get_mr_commits(
    url: Optional[str] = None,
    repo_id: Optional[str] = None,
    number: Optional[int] = None,
    jwt_token: str = "",
    cloud_jwt_token: Optional[str] = None,
) -> Dict[str, str]:
    """获取 MR 的 commit 范围，返回 {"from_commit": "...", "to_commit": "..."}。

    url 支持以下三种形式，都走同一个入口：
    - https://code.byted.org/<path>/merge_requests/<num>
    - https://bits.bytedance.net/code/<path>/merge_requests/<num>
    - https://bits.bytedance.net/devops/<ns>/develop/detail/<devBasicId>/change/<changeId>
      （先调 bits API 换出 codeElement.url，再走 MR URL 流程；需要 Cloud JWT）

    也可不传 url，直接传 repo_id + number 直接查询。
    """
    if url:
        if CHANGE_URL_RE.search(url):
            cloud_jwt = resolve_cloud_jwt(cloud_jwt_token)
            dev_basic_id, change_id = parse_change_url(url)
            url = fetch_bits_change_mr_url(dev_basic_id, change_id, cloud_jwt)
        ctx = resolve_mr_context(url, jwt_token)
        return {"from_commit": ctx["base_commit_id"], "to_commit": ctx["source_commit_id"]}

    if not (repo_id and number is not None):
        print("Error: 需要传入 --url 或同时传入 --repo-id 和 --number", file=sys.stderr)
        sys.exit(1)

    mr_resp = get_merge_request(repo_id=repo_id, number=number, with_versions=True, jwt_token=jwt_token)
    versions = mr_resp.get("Result", {}).get("MergeRequest", {}).get("Versions", [])
    if not versions:
        print("Error: MR 未返回 Versions 数据", file=sys.stderr)
        sys.exit(1)

    latest = max(versions, key=lambda v: v.get("Number", 0))
    from_commit = latest.get("BaseCommitId", "")
    to_commit = latest.get("SourceCommitId", "")

    if not from_commit or not to_commit:
        print("Error: Versions 中缺少 BaseCommitId 或 SourceCommitId", file=sys.stderr)
        sys.exit(1)

    return {"from_commit": from_commit, "to_commit": to_commit}


# ---------- CLI ----------
def _build_parser() -> argparse.ArgumentParser:
    # 共享 parent：让 --codebase-jwt 在子命令前后都能识别，避免调用者拼错顺序。
    # 用 SUPPRESS 作默认值，避免子 parser 解析时用 None 覆盖顶层已设置的值。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--codebase-jwt",
        default=argparse.SUPPRESS,
        help="Codebase JWT token（也可通过 CODEBASE_JWT 环境变量传入）",
    )
    common.add_argument(
        "--cloud-jwt",
        default=argparse.SUPPRESS,
        help="Cloud JWT token（也可通过 CLOUD_JWT 环境变量传入；仅 bits change URL 需要）",
    )

    parser = argparse.ArgumentParser(
        description="Codebase OpenAPI CLI（仅标准库）",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", help="可用子命令")

    # get-repository
    p_repo = sub.add_parser("get-repository", help="获取仓库信息", parents=[common])
    p_repo.add_argument("--path", help='仓库路径，例如 "byteapi/bytedcli"')
    p_repo.add_argument("--id", dest="repo_id", help="仓库 ID")
    p_repo.add_argument(
        "--with-permissions",
        action="store_true",
        help="是否返回权限信息",
    )

    # get-branch
    p_branch = sub.add_parser("get-branch", help="获取分支信息", parents=[common])
    p_branch.add_argument("--repo-id", required=True, help="仓库 ID")
    p_branch.add_argument("--name", required=True, help="分支名称")

    # get-mr
    p_mr = sub.add_parser("get-mr", help="获取 Merge Request 详情", parents=[common])
    p_mr.add_argument("--repo-id", required=True, help="仓库 ID")
    p_mr.add_argument("--number", type=int, help="MR 编号")
    p_mr.add_argument("--id", dest="mr_id", help="MR ID")
    p_mr.add_argument("--change-id", help="Change ID")
    p_mr.add_argument(
        "--with-commits",
        action="store_true",
        help="是否包含 commits 信息",
    )

    # get-mr-commits
    p_mr_commits = sub.add_parser("get-mr-commits", help="获取 MR 的 commit 范围", parents=[common])
    p_mr_commits.add_argument("--url", help="MR 链接，例如 https://code.byted.org/org/repo/merge_requests/123")
    p_mr_commits.add_argument("--repo-id", help="仓库 ID（与 --number 配合使用）")
    p_mr_commits.add_argument("--number", type=int, help="MR 编号（与 --repo-id 配合使用）")

    # create-comment
    p_comment = sub.add_parser("create-comment", help="在 MR 上创建行级评论", parents=[common])
    p_comment.add_argument(
        "--url",
        help="MR 链接；传入后自动推断 --repo-id / --commentable-id / --old-commit-id / --new-commit-id"
             "（默认取最新 Version 的 Base/Source commit），显式传值可覆盖",
    )
    p_comment.add_argument("--repo-id", help="仓库 ID（不传 --url 时必填）")
    p_comment.add_argument("--commentable-id", help="MR ID（不传 --url 时必填）")
    p_comment.add_argument("--content", required=True, help="评论内容")
    p_comment.add_argument("--old-commit-id", help="Base commit ID（不传 --url 时必填）")
    p_comment.add_argument("--new-commit-id", help="Source commit ID（不传 --url 时必填）")
    p_comment.add_argument("--path", required=True, help="文件路径")
    p_comment.add_argument("--start-line", required=True, type=int, help="起始行号")
    p_comment.add_argument("--end-line", required=True, type=int, help="结束行号")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    jwt_token = resolve_jwt(getattr(args, "codebase_jwt", None))

    if args.command == "get-repository":
        result = get_repository(
            path=args.path,
            repo_id=args.repo_id,
            with_permissions=args.with_permissions,
            jwt_token=jwt_token,
        )
    elif args.command == "get-branch":
        result = get_branch(repo_id=args.repo_id, name=args.name, jwt_token=jwt_token)
    elif args.command == "get-mr":
        result = get_merge_request(
            repo_id=args.repo_id,
            number=args.number,
            mr_id=args.mr_id,
            change_id=args.change_id,
            with_commits=args.with_commits,
            jwt_token=jwt_token,
        )
    elif args.command == "get-mr-commits":
        result = get_mr_commits(
            url=args.url,
            repo_id=args.repo_id,
            number=args.number,
            jwt_token=jwt_token,
            cloud_jwt_token=getattr(args, "cloud_jwt", None),
        )
    elif args.command == "create-comment":
        repo_id = args.repo_id
        commentable_id = args.commentable_id
        old_commit_id = args.old_commit_id
        new_commit_id = args.new_commit_id
        if args.url:
            ctx = resolve_mr_context(args.url, jwt_token)
            repo_id = repo_id or ctx["repo_id"]
            commentable_id = commentable_id or ctx["mr_id"]
            old_commit_id = old_commit_id or ctx["base_commit_id"]
            new_commit_id = new_commit_id or ctx["source_commit_id"]
        missing = [
            name for name, value in (
                ("--repo-id", repo_id),
                ("--commentable-id", commentable_id),
                ("--old-commit-id", old_commit_id),
                ("--new-commit-id", new_commit_id),
            ) if not value
        ]
        if missing:
            print(
                f"Error: 缺少参数 {', '.join(missing)}；请通过 --url 自动推断或显式传入。",
                file=sys.stderr,
            )
            sys.exit(1)
        result = create_comment(
            repo_id=repo_id,
            commentable_id=commentable_id,
            content=args.content,
            old_commit_id=old_commit_id,
            new_commit_id=new_commit_id,
            path=args.path,
            start_line=args.start_line,
            end_line=args.end_line,
            jwt_token=jwt_token,
        )
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
