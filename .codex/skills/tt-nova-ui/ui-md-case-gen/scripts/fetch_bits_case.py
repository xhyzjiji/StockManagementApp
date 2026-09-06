#!/usr/bin/env python3
"""
Fetch a BITS/bytest test case detail via the ByTest web API (curl-equivalent).

This replaces the previous `gdpa-cli run bytest_case` pull. It calls
`POST https://bytest.bytedance.net/caseApi/getCaseDetail` directly, so the
response includes fields the gdpa wrapper dropped — notably `ByteIOCaseInfo`
(埋点用例映射：节点 id -> 埋点用例列表).

Authentication (在 skill 里就该「该登录登录」，不要让用户手抠浏览器 cookie)：
the ByTest domain accepts a ByteCloud `X-Jwt-Token`. The JWT is resolved in
priority order:
  1. CLI flag:          --jwt <x-jwt-token>
  2. Environment var:   BYTEST_JWT (or X_JWT_TOKEN)
  3. Creds file (JSON): --creds <path> or ~/.bytest_creds.json  → key "jwt"
  4. **Auto-login (default)**: prints the cn JWT via the machine's login CLI —
     `gdpa-cli login -p cn` (preferred), else
     `byte-cli login --control-plane cn get-jwt`. Disable with --no-auto-jwt.
     If not logged in yet, run `gdpa-cli login cn` once, then retry.

Cookie is OPTIONAL — only needed if a deployment rejects a bare X-Jwt-Token.
Provide it via --cookie / BYTEST_COOKIE / creds-file "cookie" when required.

`operator` defaults to the `username` claim decoded from the jwt when not given.

Optional creds file (~/.bytest_creds.json) — only if you can't/don't want to
rely on byte-cli auto-login:
  {
    "jwt": "eyJhbGciOiJSUzI1Ni...",   // value of the `x-jwt-token` header
    "cookie": "fid=...; user_token=...; (full Cookie header string, optional)",
    "operator": "huangyiran.dd",
    "space_id": "1499051266"
  }

Usage:
  # 正常情况：已 byte-cli 登录，直接拉（自动取 JWT）
  python3 fetch_bits_case.py --test-case-id 14584786 --product-id 66666866 \
      --space-id 1499051266 \
      --output /abs/path/bytest-case-14584786.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

API_URL = "https://bytest.bytedance.net/caseApi/getCaseDetail"
DEFAULT_CREDS_FILE = Path("~/.bytest_creds.json").expanduser()

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--test-case-id", "--test_case_id", dest="test_case_id", required=True, type=int)
    parser.add_argument("--product-id", "--product_id", dest="product_id", required=True, type=int)
    parser.add_argument("--space-id", "--space_id", dest="space_id", default="")
    parser.add_argument("--operator", default="")
    parser.add_argument("--jwt", default="", help="x-jwt-token header value (overrides env/creds/byte-cli)")
    parser.add_argument("--cookie", default="", help="OPTIONAL full Cookie header value (only if bare JWT is rejected)")
    parser.add_argument("--creds", default="", help="Path to a JSON creds file (default ~/.bytest_creds.json)")
    parser.add_argument(
        "--no-auto-jwt",
        dest="auto_jwt",
        action="store_false",
        help="Disable automatic `byte-cli login --control-plane cn get-jwt` fallback.",
    )
    parser.set_defaults(auto_jwt=True)
    parser.add_argument("--output", help="Output JSON path. Prints to stdout if omitted.")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--verify-tls",
        dest="verify_tls",
        action="store_true",
        help="Verify TLS certs. Off by default because the internal ByTest domain "
        "presents a corporate self-signed CA chain (same as ui-debug-task-exec).",
    )
    parser.set_defaults(verify_tls=False)
    return parser.parse_args()


def _load_creds_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _decode_jwt_username(jwt: str) -> str:
    """Best-effort: decode the jwt payload and return the `username` claim."""
    try:
        payload_seg = jwt.split(".")[1]
        payload_seg += "=" * (-len(payload_seg) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_seg).decode("utf-8"))
        return str(payload.get("username") or payload.get("email", "").split("@")[0] or "")
    except Exception:
        return ""


def _extract_jwt_from_output(out: str) -> str:
    """Parse a JWT out of CLI stdout (JSON {data:{jwt}} / {jwt} or a bare token)."""
    out = (out or "").strip()
    if not out:
        return ""
    try:
        payload = json.loads(out)
        if isinstance(payload, dict):
            data = payload.get("data") or {}
            jwt = data.get("jwt") or payload.get("jwt")
            if isinstance(jwt, str) and jwt:
                return jwt
    except json.JSONDecodeError:
        pass
    # Bare token: three base64url segments separated by dots, no whitespace.
    if out.count(".") == 2 and not any(c.isspace() for c in out):
        return out
    # Some CLIs print a trailing token on the last non-empty line.
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.count(".") == 2 and not any(c.isspace() for c in line):
            return line
    return ""


def _run_cli(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(
            cmd, check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return _extract_jwt_from_output(proc.stdout)


def _resolve_bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    local = os.path.expanduser(f"~/.local/bin/{name}")
    return local if os.path.exists(local) else ""


def get_jwt_via_login_cli() -> str:
    """Resolve a ByteCloud (cn) JWT via the machine's login CLI. Never prints the token.

    Tries, in order:
      1. `gdpa-cli login -p cn`     (this repo's standard login; prints cn JWT)
      2. `byte-cli login --control-plane cn get-jwt`  (same mechanism ui-debug-task-exec uses)
    Returns "" when no CLI is available or none is logged in.
    """
    gdpa = _resolve_bin("gdpa-cli")
    if gdpa:
        jwt = _run_cli([gdpa, "login", "-p", "cn"])
        if jwt:
            return jwt

    byte_cli = _resolve_bin("byte-cli")
    if byte_cli:
        jwt = _run_cli([byte_cli, "login", "--control-plane", "cn", "get-jwt"])
        if jwt:
            return jwt

    return ""


def resolve_credentials(args: argparse.Namespace) -> dict[str, str]:
    creds_path = Path(args.creds).expanduser() if args.creds else DEFAULT_CREDS_FILE
    file_creds = _load_creds_file(creds_path)

    jwt = args.jwt or os.environ.get("BYTEST_JWT") or os.environ.get("X_JWT_TOKEN") or file_creds.get("jwt", "")
    jwt_source = "explicit(jwt/env/creds)" if jwt else ""
    if not jwt and args.auto_jwt:
        jwt = get_jwt_via_login_cli()
        if jwt:
            jwt_source = "login-cli"
    cookie = args.cookie or os.environ.get("BYTEST_COOKIE") or file_creds.get("cookie", "")
    space_id = str(args.space_id or os.environ.get("BYTEST_SPACE_ID") or file_creds.get("space_id", ""))
    operator = (
        args.operator
        or os.environ.get("BYTEST_OPERATOR")
        or file_creds.get("operator", "")
        or _decode_jwt_username(jwt)
    )

    if not jwt:
        raise SystemExit(
            "ERROR: 无法获取 JWT。请「该登录登录」，任选其一：\n"
            "  - 正规登录（推荐）: gdpa-cli login cn   （登录一次后本脚本用 `gdpa-cli login -p cn` 自动取 JWT）\n"
            "                     或 byte-cli login --control-plane cn（若装了 byte-cli）\n"
            "  - CLI 显式传:      --jwt <x-jwt-token>\n"
            "  - 环境变量:        BYTEST_JWT / X_JWT_TOKEN\n"
            f"  - 凭证文件:        {creds_path} (JSON: {{\"jwt\":..}})\n"
            "若已登录仍失败：登录态可能过期，重跑 `gdpa-cli login -f cn` 强制刷新后重试。"
        )
    if not operator:
        raise SystemExit("ERROR: 无法解析 operator（jwt 无 username 声明）。请显式传 --operator 或写入凭证文件。")

    return {
        "jwt": jwt,
        "jwt_source": jwt_source,
        "cookie": cookie,
        "space_id": space_id,
        "operator": operator,
    }


def fetch_case_detail(args: argparse.Namespace, creds: dict[str, str]) -> dict[str, Any]:
    body = json.dumps(
        {"ProductId": args.product_id, "TestCaseId": args.test_case_id, "Operator": creds["operator"]}
    ).encode("utf-8")

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh",
        "content-type": "application/json",
        "origin": "https://bits.bytedance.net",
        "referer": "https://bits.bytedance.net/",
        "projectid": str(args.product_id),
        "service": "CaseService",
        "servicefunc": "GetTestCase",
        "user-agent": _UA,
        "x-jwt-token": creds["jwt"],
        "x-trigger-source": "onesite",
    }
    if creds.get("cookie"):
        headers["cookie"] = creds["cookie"]
    if creds["space_id"]:
        headers["x-onesite-space-id"] = creds["space_id"]

    context = None if args.verify_tls else ssl._create_unverified_context()
    req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=args.timeout, context=context) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"ERROR: HTTP {exc.code} 调用失败: {detail}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"ERROR: 网络错误: {exc}")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"ERROR: 响应不是合法 JSON: {raw[:500]}")

    err_code = payload.get("errCode")
    if err_code not in (0, None):
        msg = payload.get("message", "")
        hint = ""
        if err_code == 40 or "Jwt" in msg or "Auth" in msg:
            if creds.get("jwt_source") == "login-cli":
                hint = (
                    "（登录态可能过期或无 ByTest 访问权限：先跑 "
                    "`gdpa-cli login -f cn` 强制刷新登录后重试；"
                    "若该部署要求 Cookie，再通过 --cookie/BYTEST_COOKIE 补一个浏览器 Cookie）"
                )
            else:
                hint = "（凭证已失效：重新登录 `gdpa-cli login -f cn`，或刷新 --jwt/--cookie 后重试）"
        raise SystemExit(f"ERROR: 接口返回 errCode={err_code} message={msg} {hint}")

    return payload


def main() -> int:
    args = parse_args()
    creds = resolve_credentials(args)
    payload = fetch_case_detail(args, creds)

    data = payload.get("data", payload)
    byteio = (data.get("ByteIOCaseInfo") or {}).get("CaseList") or {} if isinstance(data, dict) else {}

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        title = data.get("TestCaseTitle", "") if isinstance(data, dict) else ""
        print(f"[fetch_bits_case] OK TestCaseId={args.test_case_id} title={title!r} jwt_source={creds.get('jwt_source','')}")
        print(f"[fetch_bits_case] ByteIOCaseInfo 节点数={len(byteio)}"
              + (f" (节点: {', '.join(list(byteio)[:5])})" if byteio else " (无埋点用例)"))
        print(f"[fetch_bits_case] file_path={out_path}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
