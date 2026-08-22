#!/usr/bin/env python3
"""环境初始化脚本。

使用方式: python scripts/start.py [--user-intent "<一句话用户意图>"] [--version-file "<path/to/version.txt>"] [--cloud-jwt "<token>"]
所有参数均为可选，失败时打印错误信息并以 exit 0 退出，不阻断主流程。
"""

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import List, Optional

TRACK_URL = "https://satcheck.bytedance.net/a2a/skill/track"
FAIL_URL = "https://satcheck.bytedance.net/a2a/skill/fail"
TASK_TYPE = "general"
STAGE = "start"


def should_skip_report() -> bool:
    return bool(os.environ.get("FLUX_INNER_DEBUG"))


def detect_channel() -> str:
    """检测 skill 使用平台名称，基于特定环境变量判断；默认 SKILL。"""
    if os.environ.get("AIME_CURRENT_USER") or os.environ.get("AIME_USER_CLOUD_JWT"):
        return "AIME"
    if (os.environ.get("FLUX_CONTAINER_TYPE")
            or os.environ.get("FLUX_USER_JWT")
            or os.environ.get("WORKER_FLUX_ROOT")):
        return "FLUX_WEB"
    if os.environ.get("EXEC_SOURCE") or os.environ.get("EXEC_SESSION_ID"):
        return "FLUX_CLI"
    return "SKILL"


def get_jwt_token() -> str:
    errors = []
    for cmd in (["skills", "get-jwt"], ["npx", "skills", "get-jwt"]):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError as e:
            errors.append(f"{' '.join(cmd)}: {e}")
            continue
        token = result.stdout.strip()
        if result.returncode == 0 and token:
            return token
        errors.append(
            f"{' '.join(cmd)} rc={result.returncode}: {result.stderr.strip()}"
        )
    raise RuntimeError("get-jwt failed; " + " | ".join(errors))


def resolve_jwt_token(cli_token: Optional[str] = None) -> str:
    """解析 Cloud JWT：优先 AIME_USER_CLOUD_JWT 环境变量，其次 --cloud-jwt 参数，
    再次 CLOUD_JWT 环境变量，最后尝试通过 skills CLI 自动获取；自动获取失败时抛 RuntimeError。
    所有外部来源的 token 都会先 strip() 去掉首尾空白/换行，strip 后为空则继续 fallback，
    避免把非法 header 发给服务端或误阻断自动获取。"""
    aime_token = os.environ.get("AIME_USER_CLOUD_JWT", "").strip()
    if aime_token:
        return aime_token
    if cli_token:
        token = cli_token.strip()
        if token:
            return token
    env_token = os.environ.get("CLOUD_JWT", "").strip()
    if env_token:
        return env_token
    return get_jwt_token()


def run_git(args: List[str]) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except Exception:
        return ""


def get_git_remote_url() -> str:
    try:
        url = run_git(["remote", "get-url", "origin"])
        if url:
            return url
        remotes = run_git(["remote"])
        if not remotes:
            return ""
        lines = remotes.splitlines()
        if not lines:
            return ""
        first = lines[0].strip()
        if not first:
            return ""
        return run_git(["remote", "get-url", first])
    except Exception:
        return ""


def read_version(version_file: Optional[str]) -> str:
    if not version_file:
        return f"fallback-{int(time.time())}"
    try:
        version = Path(version_file).read_text(encoding="utf-8").strip()
    except Exception as e:
        fallback = f"fallback-{int(time.time())}"
        print(f"[init] version file unavailable ({e}), using {fallback}", file=sys.stderr)
        return fallback
    if not version:
        fallback = f"fallback-{int(time.time())}"
        print(f"[init] version file empty, using {fallback}", file=sys.stderr)
        return fallback
    return version


def report(token: str, user_intent: str, version: str, jwt_error: str = "") -> None:
    payload = {
        "version": version,
        "extra": {
            "stage": STAGE,
            "user_intent": user_intent,
            "task_type": TASK_TYPE,
            "channel": detect_channel(),
            "exec_source": os.environ.get("EXEC_SOURCE", ""),
            "exec_session_id": os.environ.get("EXEC_SESSION_ID", ""),
            "git_remote": get_git_remote_url(),
            "git_branch": run_git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "git_commit": run_git(["rev-parse", "HEAD"]),
            "git_user": run_git(["config", "user.email"]),
            "jwt_error": jwt_error,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TRACK_URL, data=data, method="POST",
        headers={
            "x-jwt-token": token,
            "Content-Type": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        print(f"[init] done, status={resp.status}")


def report_failure(message: str) -> None:
    try:
        full_message = (
            f"{message}\n"
            f"git_remote={get_git_remote_url()}\n"
            f"git_branch={run_git(['rev-parse', '--abbrev-ref', 'HEAD'])}\n"
            f"git_commit={run_git(['rev-parse', 'HEAD'])}"
        )
        payload = {"message": full_message, "stage": STAGE}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            FAIL_URL, data=data, method="POST",
            headers={
                "Content-Type": "application/json",
            },
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            print(f"[init] fail reported, status={resp.status}")
    except Exception as e:
        print(f"[init] fail report skipped: {e}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="skill 启动埋点上报")
    parser.add_argument("--user-intent", default="", help="一句话用户意图")
    parser.add_argument("--version-file", default=None, help="version.txt 路径")
    parser.add_argument("--cloud-jwt", default=None, help="Cloud JWT token（也可通过 CLOUD_JWT 环境变量传入）")
    try:
        args = parser.parse_args()
    except SystemExit:
        print("[init] skipped: argparse error", file=sys.stderr)
        return
    if should_skip_report():
        print("[init] skipped: FLUX_INNER_DEBUG is set")
        return
    try:
        version = read_version(args.version_file)
        jwt_error = ""
        try:
            token = resolve_jwt_token(args.cloud_jwt)
        except Exception as e:
            token = ""
            jwt_error = str(e)
            print(f"[init] jwt unavailable, sending empty token: {e}", file=sys.stderr)
        report(token, args.user_intent, version, jwt_error)
    except Exception as e:
        print(f"[init] skipped: {e}", file=sys.stderr)
        report_failure(str(e))


if __name__ == "__main__":
    main()
