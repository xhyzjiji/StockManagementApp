"""
将 _cases.md + _richtext.md 上传至 TTAT OpenAPI。

模式:
  create（默认）— POST /ui/open_api/upload_bits_test_case_mind 新建用例集
  update         — 对已有 case_set_id 做 upsert：每条用例 delete_subtree + append_branch
                   （前置/工具变更只能整条重写；update_node 只改步骤，本脚本默认不用）

用法:
    # 新建
    python upload_cases.py --cases a_cases.md --richtext a_richtext.md \\
        --project_id <id> --dir_id <id>

    # 更新已有用例集（前置加工具等结构变更走整条重写）
    python upload_cases.py --mode update --cases a_cases.md --richtext a_richtext.md \\
        --project_id <id> --case-set-id <id> [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

# env → 路由 header；network → 域名。正交。
_ENV_HEADERS = {
    "ppe": {
        "x-custom-token": "Z3VvZmVuZy5nZi8yMDI1LTAxLTE1IDA2OjMzOjQ1",
        "x-tt-env": "ppe_prd2case_tools",
        "x-use-ppe": "1",
    },
    "prod": {},
}

_NETWORK_HOSTS = {
    "office": "ttat-openapi-sg.tiktok-row.net",
    "server": "ttat-openapi-sg.byteintl.net",
}

_CREATE_PATH = "/ui/open_api/upload_bits_test_case_mind"
_APPEND_BRANCH_PATH = "/ui/open_api/bits_case_atomic/append_branch"
_DELETE_SUBTREE_PATH = "/ui/open_api/bits_case_atomic/delete_subtree"
_ROLE_LIST_URL = "https://bits-cn-gw.bytedance.net/test_case/role/list"
_TIMEOUT = 300

_TT_NOVA_PREFIX = "[TT-Nova]"
_RICHTEXT_RE = re.compile(r"\$\{richText_([^:}]+):")
_H1_RE = re.compile(r"^#\s+(.+)$")
_H2_RE = re.compile(r"^##\s+(.+)$")
_H3_RE = re.compile(r"^###\s+(.+)$")

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_richtext(raw: str) -> list:
    m = re.search(r"```json\s*\n(.*?)\n```", raw, re.DOTALL)
    text = m.group(1) if m else raw
    return json.loads(text)


def _add_tt_nova_prefix(md: str) -> str:
    def _prefix_line(m: re.Match) -> str:
        hashes, title = m.group(1), m.group(2)
        if _TT_NOVA_PREFIX in title:
            return m.group(0)
        return f"{hashes} {_TT_NOVA_PREFIX} {title}"

    return re.sub(r"^(#{1,3})\s+(.+)$", _prefix_line, md, flags=re.MULTILINE)


def _strip_heading(title: str) -> str:
    return title.strip()


@dataclass
class CaseBranch:
    primary_title: str
    case_title: str
    body_lines: List[str]  # from #### onward (no ## / ### lines)
    root_title: str

    def branch_markdown(self) -> str:
        parts = [
            f"# {self.root_title}",
            "",
            f"## {self.primary_title}",
            f"### {self.case_title}",
        ]
        parts.extend(self.body_lines)
        text = "\n".join(parts).rstrip() + "\n"
        return text


def parse_case_branches(md: str) -> Tuple[str, List[CaseBranch]]:
    """Split bits-format cases.md into (root_title, branches)."""
    lines = md.splitlines()
    root = "Feature 测试规格文档（Spec）"
    primary = ""
    branches: List[CaseBranch] = []
    cur: Optional[CaseBranch] = None

    def _flush() -> None:
        nonlocal cur
        if cur is not None:
            while cur.body_lines and not cur.body_lines[-1].strip():
                cur.body_lines.pop()
            branches.append(cur)
            cur = None

    for line in lines:
        m1 = _H1_RE.match(line)
        if m1 and not line.startswith("##"):
            root = _strip_heading(m1.group(1))
            continue
        m2 = _H2_RE.match(line)
        if m2:
            _flush()
            primary = _strip_heading(m2.group(1))
            continue
        m3 = _H3_RE.match(line)
        if m3:
            _flush()
            if not primary:
                raise ValueError(f"用例缺少一级标题(##): {line}")
            cur = CaseBranch(
                primary_title=primary,
                case_title=_strip_heading(m3.group(1)),
                body_lines=[],
                root_title=root,
            )
            continue
        if cur is not None:
            cur.body_lines.append(line)

    _flush()
    return root, branches


def _richtext_uuids_in_text(text: str) -> List[str]:
    return _RICHTEXT_RE.findall(text)


def filter_richtext_for_branch(branch_md: str, rich_text_array: list) -> list:
    """Keep richtext items whose uuid appears in ${richText_<uuid>:...} placeholders."""
    needed = set(_richtext_uuids_in_text(branch_md))
    if not needed:
        return []
    out = []
    seen = set()
    for item in rich_text_array:
        uid = str(item.get("uuid") or "")
        if uid in needed and uid not in seen:
            out.append(item)
            seen.add(uid)
    return out


def parse_bits_case_url(url: str) -> Dict[str, int]:
    """Parse Bits caseDetail URL → project_id (/devops/{id}/) + case_set_id.

    project_id MUST come from path /devops/{id}/, never devops_space_old_id.
    """
    parsed = urlparse(url.strip())
    m = re.search(r"/devops/(\d+)/", parsed.path)
    if not m:
        raise ValueError(f"Bits 链接缺少 /devops/{{id}}/: {url}")
    project_id = int(m.group(1))
    m2 = re.search(r"/caseDetail/(\d+)", parsed.path)
    if not m2:
        raise ValueError(f"Bits 链接缺少 /caseDetail/{{case_set_id}}: {url}")
    case_set_id = int(m2.group(1))
    qs = parse_qs(parsed.query)
    dir_raw = (qs.get("dirId") or qs.get("dir_id") or [""])[0]
    out: Dict[str, int] = {"project_id": project_id, "case_set_id": case_set_id}
    if dir_raw.isdigit():
        out["dir_id"] = int(dir_raw)
    return out


def _post_json(url: str, body: dict, headers: dict) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=_TIMEOUT, context=_SSL_CTX) as resp:
        resp_headers = dict(resp.headers)
        logid = resp_headers.get("x-tt-logid") or resp_headers.get("X-Tt-Logid", "")
        if logid:
            print(f"[upload] logid: {logid}")
        resp_body = json.loads(resp.read().decode("utf-8"))
        body_logid = resp_body.get("logid") or resp_body.get("log_id", "")
        if body_logid and body_logid != logid:
            print(f"[upload] logid (body): {body_logid}")
        return resp_body


def _resolve_host(env: str, network: str) -> Tuple[str, dict]:
    env_headers = _ENV_HEADERS.get(env)
    if env_headers is None:
        raise ValueError(f"未知环境: {env}，可选 ppe / prod")
    host = _NETWORK_HOSTS.get(network)
    if not host:
        raise ValueError(f"未知网络: {network}，可选 office / server")
    return host, dict(env_headers)


def _api_ok(result: dict) -> bool:
    if result.get("status_code") in (0, 200):
        return True
    if result.get("code") in (0, 200):
        return True
    base = result.get("base_response") or {}
    if base.get("status_code") in (0, 200):
        return True
    msg = str(base.get("status_message") or base.get("status_msg") or "").strip().lower()
    return msg in ("success", "ok")


def _raise_api(action: str, result: dict) -> None:
    preview = json.dumps(result, ensure_ascii=False)[:800]
    raise RuntimeError(f"{action} 失败: {preview}")


def _call_atomic(
    host: str,
    headers: dict,
    path: str,
    body: dict,
    action: str,
) -> dict:
    url = f"https://{host}{path}"
    print(f"[sync] {action}: {path}")
    try:
        result = _post_json(url, body, headers)
    except (HTTPError, URLError, OSError) as exc:
        is_timeout = "timed out" in str(exc).lower() or "504" in str(exc)
        if is_timeout:
            raise RuntimeError(
                f"{action} 请求超时，状态未知；请先确认 Bits，不要直接重试"
            ) from exc
        raise RuntimeError(f"{action} API 调用失败: {exc}") from exc
    return result


def _role_mismatches(rich_text_array: list, role_list: list) -> List[str]:
    """设备角色 richtext 的 pluginData.id 与平台角色表比对，返回不一致描述（空=通过）。"""
    by_alias = {str(r.get("alias") or ""): str(r.get("role_id") or "") for r in role_list}
    out: List[str] = []
    for item in rich_text_array:
        if str(item.get("mentionType")) != "33":
            continue
        alias = str(item.get("text") or "")
        used = str((item.get("pluginData") or {}).get("id") or "")
        expect = by_alias.get(alias)
        if expect is None:
            out.append(f"{alias}: 平台该空间没有这个角色")
        elif expect != used:
            out.append(f"{alias}: richtext={used} 平台={expect}")
    return out


def check_device_roles(rich_text_array: list, bits_space_id: int) -> None:
    """上传前硬校验设备角色 id；对不上直接报错（角色 id 漂移会导致 bits「没有调试角色」）。"""
    if not any(str(i.get("mentionType")) == "33" for i in rich_text_array):
        return
    jwt = os.environ.get("BYTEST_JWT") or os.environ.get("X_JWT_TOKEN")
    if not jwt:
        sys.path.insert(
            0,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ui-md-case-gen", "scripts"),
        )
        from fetch_bits_case import get_jwt_via_login_cli  # noqa: PLC0415

        jwt = get_jwt_via_login_cli()
    if not jwt:
        raise RuntimeError(
            "设备角色校验取不到 JWT：先 `gdpa-cli login cn`，或传 --skip-role-check（不推荐）"
        )
    result = _post_json(
        _ROLE_LIST_URL,
        {"bits_space_id": int(bits_space_id)},
        {"X-Jwt-Token": jwt, "domain": "bits_test_management_api;v1"},
    )
    mismatches = _role_mismatches(rich_text_array, result.get("role_list") or [])
    if mismatches:
        raise RuntimeError(
            "设备角色 id 与 bits 空间不一致，上传后会「没有调试角色」：\n  "
            + "\n  ".join(mismatches)
            + f"\n  空间={bits_space_id}；请修正 richtext 的 pluginData.id 后重试"
        )
    print(f"[upload] 设备角色校验通过（space={bits_space_id}）")


def _delete_not_found(result: dict) -> bool:
    """True if delete failed because the branch is missing (safe for upsert)."""
    blob = json.dumps(result, ensure_ascii=False).lower()
    needles = (
        "not found",
        "找不到",
        "不存在",
        "no such",
        "not exist",
        "未找到",
        "无法找到",
    )
    return any(n in blob for n in needles)


def upload(
    cases_path: str,
    richtext_path: str,
    project_id: int,
    dir_id: int,
    env: str = "ppe",
    creator: str = "",
    network: str = "office",
    skip_role_check: bool = False,
) -> dict:
    """新建用例集（create）。"""
    cases_path = os.path.abspath(cases_path)
    richtext_path = os.path.abspath(richtext_path)
    if not os.path.isfile(cases_path):
        raise FileNotFoundError(f"cases 文件不存在: {cases_path}")
    if not os.path.isfile(richtext_path):
        raise FileNotFoundError(f"richtext 文件不存在: {richtext_path}")

    host, headers = _resolve_host(env, network)
    markdown_content = _add_tt_nova_prefix(_read_text(cases_path))
    rich_text_array = _parse_richtext(_read_text(richtext_path))
    creator = creator or os.environ.get("USER", "unknown")
    if not skip_role_check:
        check_device_roles(rich_text_array, project_id)

    body: dict = {
        "markdown_content": markdown_content,
        "creator": creator,
        "rich_text_array": rich_text_array,
        "project_id": project_id,
        "dir_id": dir_id,
        "register_same_value_tool_once": True,
    }

    url = f"https://{host}{_CREATE_PATH}"
    print(f"[upload] mode=create  env={env}  network={network}  url={url}")
    print(f"[upload] project_id={project_id}  dir_id={dir_id}")
    print(f"[upload] markdown_content length: {len(markdown_content)} chars")
    print(f"[upload] rich_text_array items: {len(rich_text_array)}")
    print("[upload] 发送请求（不重试，仅执行一次）...")
    try:
        result = _post_json(url, body, headers)
    except (HTTPError, URLError, OSError) as exc:
        is_timeout = "timed out" in str(exc).lower() or "504" in str(exc)
        if is_timeout:
            print(f"[upload] 请求超时: {exc}")
            print("[upload] ⚠️ 上传状态未知：请求可能未到达服务端，也可能已完成但响应丢失。")
            print("[upload] 请先前往 bits 平台确认；未确认前不要重复提交，以免创建重复用例。")
            print(f"[upload]   projectId={project_id}, dirId={dir_id}")
            raise RuntimeError("上传请求超时，状态未知；请先确认 Bits 结果，不要直接重试") from exc
        raise RuntimeError(f"API 调用失败: {exc}") from exc

    if not _api_ok(result):
        status_code = result.get("status_code", result.get("code", -1))
        status_msg = result.get("status_msg", result.get("msg", ""))
        preview = json.dumps(result, ensure_ascii=False)[:800]
        raise RuntimeError(
            f"上传失败: status_code={status_code}, status_msg={status_msg}\n"
            f"  response preview={preview}"
        )

    print(f"[upload] SUCCESS: status_code={result.get('status_code', result.get('code'))}")
    case_detail_url = result.get("case_detail_url", "")
    if case_detail_url:
        print(f"[upload] case_detail_url: {case_detail_url}")
    print(f"[upload] 请前往 bits 平台查看: projectId={project_id}, dirId={dir_id}")
    return result


def sync_case_set(
    cases_path: str,
    richtext_path: str,
    project_id: int,
    case_set_id: int,
    env: str = "ppe",
    creator: str = "",
    network: str = "office",
    only_case_titles: Optional[Sequence[str]] = None,
    delete_titles: Optional[Sequence[Tuple[str, str]]] = None,
    dry_run: bool = False,
    skip_delete_missing: bool = True,
    skip_role_check: bool = False,
) -> dict:
    """Update an existing case_set: upsert local branches via delete + append.

    Preconditions / tools cannot use update_node — whole-branch rewrite only.
    """
    cases_path = os.path.abspath(cases_path)
    richtext_path = os.path.abspath(richtext_path)
    if not os.path.isfile(cases_path):
        raise FileNotFoundError(f"cases 文件不存在: {cases_path}")
    if not os.path.isfile(richtext_path):
        raise FileNotFoundError(f"richtext 文件不存在: {richtext_path}")

    host, headers = _resolve_host(env, network)
    creator = creator or os.environ.get("USER", "unknown")
    md = _add_tt_nova_prefix(_read_text(cases_path))
    rich_text_array = _parse_richtext(_read_text(richtext_path))
    if not (dry_run or skip_role_check):
        check_device_roles(rich_text_array, project_id)
    _, branches = parse_case_branches(md)

    only_set = None
    if only_case_titles:
        only_set = {t.strip() for t in only_case_titles if t.strip()}
        # allow match with or without [TT-Nova] prefix in filter
        expanded = set(only_set)
        for t in list(only_set):
            if _TT_NOVA_PREFIX not in t:
                expanded.add(f"{_TT_NOVA_PREFIX} {t}")
            else:
                expanded.add(t.replace(_TT_NOVA_PREFIX, "").strip())
        only_set = expanded

    selected = [
        b
        for b in branches
        if only_set is None
        or b.case_title in only_set
        or b.case_title.replace(_TT_NOVA_PREFIX, "").strip() in only_set
    ]
    if only_case_titles and not selected:
        raise ValueError(f"--only-case-title 未匹配到任何用例: {only_case_titles}")

    plan = {
        "mode": "update",
        "project_id": project_id,
        "case_set_id": case_set_id,
        "upsert": [
            {"primary_title": b.primary_title, "case_title": b.case_title}
            for b in selected
        ],
        "delete_only": [
            {"primary_title": p, "case_title": c}
            for p, c in (delete_titles or [])
        ],
        "dry_run": dry_run,
    }
    print(f"[sync] env={env} network={network} host={host}")
    print(f"[sync] project_id={project_id} case_set_id={case_set_id}")
    print(f"[sync] upsert={len(plan['upsert'])} delete_only={len(plan['delete_only'])}")
    for item in plan["upsert"]:
        print(f"[sync]   upsert: ## {item['primary_title']} / ### {item['case_title']}")
    for item in plan["delete_only"]:
        print(f"[sync]   delete: ## {item['primary_title']} / ### {item['case_title']}")

    if dry_run:
        print("[sync] dry-run：不调用接口")
        return {"plan": plan, "dry_run": True}

    results: List[dict] = []

    def _do_delete(primary: str, case_title: str) -> dict:
        body = {
            "project_id": project_id,
            "case_set_id": case_set_id,
            "creator": creator,
            "case_ref": {"primary_title": primary, "case_title": case_title},
        }
        result = _call_atomic(
            host, headers, _DELETE_SUBTREE_PATH, body, f"delete {case_title}"
        )
        if _api_ok(result):
            print(f"[sync] deleted: {case_title}")
            return result
        if skip_delete_missing and _delete_not_found(result):
            print(f"[sync] delete skip (not found): {case_title}")
            return result
        _raise_api(f"delete {case_title}", result)
        return result  # unreachable

    for primary, case_title in delete_titles or []:
        # ensure [TT-Nova] on titles if caller omitted
        p = primary if _TT_NOVA_PREFIX in primary else f"{_TT_NOVA_PREFIX} {primary}"
        c = case_title if _TT_NOVA_PREFIX in case_title else f"{_TT_NOVA_PREFIX} {case_title}"
        results.append({"action": "delete", "case_title": c, "response": _do_delete(p, c)})

    for branch in selected:
        _do_delete(branch.primary_title, branch.case_title)
        branch_md = branch.branch_markdown()
        branch_rich = filter_richtext_for_branch(branch_md, rich_text_array)
        body = {
            "project_id": project_id,
            "case_set_id": case_set_id,
            "creator": creator,
            "branch_markdown": branch_md,
            "rich_text_array": branch_rich,
        }
        result = _call_atomic(
            host,
            headers,
            _APPEND_BRANCH_PATH,
            body,
            f"append {branch.case_title}",
        )
        if not _api_ok(result):
            _raise_api(f"append {branch.case_title}", result)
        print(f"[sync] appended: {branch.case_title} (richtext={len(branch_rich)})")
        results.append(
            {
                "action": "upsert",
                "primary_title": branch.primary_title,
                "case_title": branch.case_title,
                "response": result,
            }
        )

    print(f"[sync] SUCCESS: upserted={len(selected)} deleted_only={len(delete_titles or [])}")
    print(
        f"[sync] bits: https://bits.bytedance.net/devops/{project_id}/quality/case/caseDetail/{case_set_id}"
    )
    return {"plan": plan, "results": results}


def _self_check() -> int:
    sample = """# Demo Set

## Group A
### Case One
#### **前置条件**
${richText_789012:测试账号}; ${richText_401050:环境名称};

##### **操作步骤**
[md] do thing;
###### **预期结果** ok

### Case Two
#### **前置条件**
remark only;

##### **操作步骤**
step;
###### **预期结果** yes
"""
    prefixed = _add_tt_nova_prefix(sample)
    assert "[TT-Nova] Group A" in prefixed
    assert "[TT-Nova] Case One" in prefixed
    _, branches = parse_case_branches(prefixed)
    assert len(branches) == 2
    assert branches[0].primary_title == f"{_TT_NOVA_PREFIX} Group A"
    assert branches[0].case_title == f"{_TT_NOVA_PREFIX} Case One"
    md0 = branches[0].branch_markdown()
    assert md0.startswith("# [TT-Nova] Demo Set\n")
    assert "## [TT-Nova] Group A\n### [TT-Nova] Case One\n" in md0
    rich = [
        {"uuid": "789012", "text": "测试账号"},
        {"uuid": "401050", "text": "环境名称"},
        {"uuid": "999999", "text": "unused"},
    ]
    filtered = filter_richtext_for_branch(md0, rich)
    assert [x["uuid"] for x in filtered] == ["789012", "401050"]
    ids = parse_bits_case_url(
        "https://bits.bytedance.net/devops/1499051266/quality/case/caseDetail/15258509"
        "?devops_space_old_id=66666866&dirId=1422067&projectId=66666866"
    )
    assert ids["project_id"] == 1499051266  # path, NOT old_id
    assert ids["case_set_id"] == 15258509
    assert ids["dir_id"] == 1422067
    roles = [{"alias": "TT-主播设备-1", "role_id": "aaa"}]
    dev = lambda pid: {"mentionType": 33, "text": "TT-主播设备-1", "pluginData": {"id": pid}}
    assert _role_mismatches([dev("aaa")], roles) == []
    assert _role_mismatches([dev("bbb")], roles) == ["TT-主播设备-1: richtext=bbb 平台=aaa"]
    assert _role_mismatches(
        [{"mentionType": 33, "text": "TT-非主播设备-9", "pluginData": {"id": "x"}}], roles
    ) == ["TT-非主播设备-9: 平台该空间没有这个角色"]
    assert _role_mismatches([{"uuid": "789012", "text": "测试账号"}], roles) == []
    print("[self-check] ok")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="上传或更新 _cases.md + _richtext.md 到 bits"
    )
    parser.add_argument("--cases", help="*_cases.md 文件路径")
    parser.add_argument("--richtext", help="*_richtext.md 文件路径")
    parser.add_argument("--project_id", type=int, help="bits project_id（/devops/{id}/）")
    parser.add_argument("--dir_id", type=int, help="bits dir_id（create 模式必填）")
    parser.add_argument(
        "--case-set-id",
        "--case_set_id",
        dest="case_set_id",
        type=int,
        help="bits case_set_id（update 模式必填）",
    )
    parser.add_argument(
        "--bits-url",
        default="",
        help="Bits caseDetail 链接；可解析 project_id + case_set_id（及可选 dir_id）",
    )
    parser.add_argument(
        "--mode",
        choices=["create", "update"],
        default="create",
        help="create=新建用例集；update=同一 case_set 上 upsert（delete+append）",
    )
    parser.add_argument(
        "--only-case-title",
        action="append",
        default=[],
        help="update 时只处理指定 ### 标题（可重复）；默认处理 md 内全部用例",
    )
    parser.add_argument(
        "--delete-case",
        action="append",
        default=[],
        help="update 时额外删除：'primary_title|||case_title'（可重复）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不调接口")
    parser.add_argument("--creator", default="", help="操作人（默认 $USER）")
    parser.add_argument("--env", choices=["ppe", "prod"], default="ppe")
    parser.add_argument("--network", choices=["office", "server"], default="office")
    parser.add_argument(
        "--skip-role-check",
        action="store_true",
        help="跳过设备角色 id 校验（不推荐；角色 id 错会导致 bits 上「没有调试角色」）",
    )
    parser.add_argument("--self-check", action="store_true", help="跑解析自检后退出")
    args = parser.parse_args()

    if args.self_check:
        sys.exit(_self_check())

    if not args.cases or not args.richtext:
        parser.error("--cases 与 --richtext 必填（或 --self-check）")

    project_id = args.project_id
    dir_id = args.dir_id
    case_set_id = args.case_set_id
    if args.bits_url:
        parsed = parse_bits_case_url(args.bits_url)
        project_id = project_id or parsed["project_id"]
        case_set_id = case_set_id or parsed["case_set_id"]
        if dir_id is None and "dir_id" in parsed:
            dir_id = parsed["dir_id"]

    if project_id is None:
        parser.error("需要 --project_id 或 --bits-url")

    delete_titles: List[Tuple[str, str]] = []
    for raw in args.delete_case:
        if "|||" not in raw:
            parser.error("--delete-case 格式应为 'primary_title|||case_title'")
        p, c = raw.split("|||", 1)
        delete_titles.append((p.strip(), c.strip()))

    try:
        if args.mode == "update":
            if case_set_id is None:
                parser.error("update 模式需要 --case-set-id 或 --bits-url")
            result = sync_case_set(
                args.cases,
                args.richtext,
                project_id,
                case_set_id,
                env=args.env,
                creator=args.creator,
                network=args.network,
                only_case_titles=args.only_case_title or None,
                delete_titles=delete_titles or None,
                dry_run=args.dry_run,
                skip_role_check=args.skip_role_check,
            )
        else:
            if dir_id is None:
                parser.error("create 模式需要 --dir_id（或带 dirId 的 --bits-url）")
            if args.dry_run:
                md = _add_tt_nova_prefix(_read_text(args.cases))
                _, branches = parse_case_branches(md)
                print(f"[upload] dry-run create: {len(branches)} cases → dir_id={dir_id}")
                for b in branches:
                    print(f"  ## {b.primary_title} / ### {b.case_title}")
                result = {"dry_run": True, "case_count": len(branches)}
            else:
                result = upload(
                    args.cases,
                    args.richtext,
                    project_id,
                    dir_id,
                    env=args.env,
                    creator=args.creator,
                    network=args.network,
                    skip_role_check=args.skip_role_check,
                )
        print(f"\n完成。响应: {json.dumps(result, ensure_ascii=False, indent=2)[:3000]}")
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
