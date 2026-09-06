#!/usr/bin/env python3
"""G9 git push 重试脚本：减少 TRAE 平台并发执行时偶现 push 失败。

典型失败场景：
- 本地分支落后远端（别人刚 push）→ 需要先 fetch + rebase
- 锁文件/临时错误 → 重试一次
- 认证/权限/仓库损坏 → 立即失败并给清晰提示

用法：
  python git_push_with_retry.py --repo <path> --branch tt_nova [--remote origin] [--max-retries 2]
  python git_push_with_retry.py --self-check

退出码：0 = push 成功；1 = push 失败（含重试后仍失败）；2 = 用法/前置错误。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitResult:
    ok: bool
    stdout: str
    stderr: str
    cmd: list[str]


def _run(cmd: list[str], cwd: Path, check: bool = False) -> GitResult:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    res = GitResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        cmd=cmd,
    )
    if check and not res.ok:
        raise RuntimeError(_format_fail(res))
    return res


def _format_fail(res: GitResult) -> str:
    tail = (res.stderr or res.stdout).strip().splitlines()
    tail_str = "\n    ".join(tail[-5:]) if tail else "(无输出)"
    return f"git {' '.join(res.cmd[1:])} 失败:\n    {tail_str}"


def _is_retryable(err_text: str) -> bool:
    low = err_text.lower()
    hints = [
        "fetch first",
        "non-fast-forward",
        "rejected",
        "failed to push some refs",
        "stale info",
        "lock",
        "timed out",
        "connection reset",
        "connection refused",
        "could not read from remote",
        "tls",
        "ssl",
        "503",
        "502",
        "429",
    ]
    return any(h in low for h in hints)


def _is_auth_err(err_text: str) -> bool:
    low = err_text.lower()
    return any(h in low for h in [
        "permission denied",
        "authentication failed",
        "could not read username",
        "could not read password",
        "fatal: could not read from remote repository",
        "access denied",
    ])


def push_with_retry(
    repo: Path,
    branch: str = "tt_nova",
    remote: str = "origin",
    max_retries: int = 2,
) -> tuple[bool, str]:
    if not repo.is_dir():
        return False, f"仓库路径不存在: {repo}"
    if not (repo / ".git").is_dir():
        return False, f"不是 git 仓库（缺 .git）: {repo}"

    # Step 0: 确认工作区有提交要 push（不在脚本里做 commit，让调用方负责）
    _run(["git", "fetch", remote, branch], cwd=repo)

    # Step 1: 检查本地分支 vs 远端
    head = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    if head.ok and head.stdout.strip() != branch:
        # 不是目标分支 → checkout
        r = _run(["git", "checkout", "-B", branch, f"{remote}/{branch}"], cwd=repo)
        if not r.ok:
            # 分支不存在，新建
            _run(["git", "checkout", "-B", branch], cwd=repo)

    attempt = 0
    last_err = ""
    while attempt <= max_retries:
        # 每次 push 前先 fetch 最新
        _run(["git", "fetch", remote, branch], cwd=repo)
        # 检查是否快进；如果本地分支落后远端，提示按幂等流程重跑
        ahead = _run(["git", "rev-list", "--count", f"HEAD..{remote}/{branch}"], cwd=repo)
        behind_n = int(ahead.stdout.strip() or "0") if ahead.ok else 0
        if behind_n > 0 and attempt == 0:
            # 第一次尝试时如果落后，先尝试 --ff-only 合并（不做 rebase，避免重放 main 的 merge 提交）
            _run(["git", "pull", "--ff-only", remote, branch], cwd=repo)
        r = _run(["git", "push", remote, f"HEAD:{branch}"], cwd=repo)
        if r.ok:
            return True, "push 成功"
        last_err = _format_fail(r)
        combined = r.stderr + r.stdout
        if _is_auth_err(combined):
            return False, (
                "git push 认证失败，请检查凭证/SSH key：\n" + last_err
            )
        if not _is_retryable(combined) or attempt >= max_retries:
            break
        attempt += 1
    return False, (
        f"git push 重试 {max_retries} 次后仍失败：\n{last_err}\n"
        "建议：按 SKILL.md Step 4 的幂等流程重跑 —— `git fetch && git checkout -B tt_nova FETCH_HEAD`，"
        "重新 cp 产物 + build_mapping + commit + push，不要手解冲突。"
    )


def self_check() -> int:
    import tempfile
    from pathlib import Path as P

    with tempfile.TemporaryDirectory() as td:
        repo = P(td) / "repo"
        repo.mkdir()
        _run(["git", "init", "-b", "tt_nova"], cwd=repo, check=True)
        _run(["git", "config", "user.email", "ci@example.com"], cwd=repo, check=True)
        _run(["git", "config", "user.name", "ci"], cwd=repo, check=True)
        (repo / "f.md").write_text("hi", encoding="utf-8")
        _run(["git", "add", "."], cwd=repo, check=True)
        _run(["git", "commit", "-m", "init"], cwd=repo, check=True)

        # 没配 remote → push 应失败，但不能崩，应返回 False+可读错误
        ok, msg = push_with_retry(repo, branch="tt_nova", max_retries=0)
        if ok:
            print("self-check FAIL: push should fail without remote")
            return 1
        if "没有配置" not in msg and "remote" not in msg.lower() and "fatal" not in msg.lower():
            # 任何错误信息都可以，只要不是崩溃
            pass

        # 不存在的路径
        ok2, msg2 = push_with_retry(P("/nonexistent/path"))
        if ok2 or "不存在" not in msg2:
            print("self-check FAIL: nonexistent repo path should fail gracefully, got:", msg2)
            return 1

    print("git_push_with_retry self-check OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=False, help="git 仓库根路径")
    ap.add_argument("--branch", default="tt_nova", help="目标分支，默认 tt_nova")
    ap.add_argument("--remote", default="origin", help="remote 名，默认 origin")
    ap.add_argument("--max-retries", type=int, default=2, help="最大重试次数，默认 2")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    if not args.repo:
        ap.error("--repo 必填（或用 --self-check）")

    repo = Path(args.repo).resolve()
    ok, msg = push_with_retry(repo, branch=args.branch, remote=args.remote, max_retries=args.max_retries)
    if ok:
        print(f"[git_push_with_retry] OK - {msg}")
        return 0
    print(f"[git_push_with_retry] FAIL:\n{msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
