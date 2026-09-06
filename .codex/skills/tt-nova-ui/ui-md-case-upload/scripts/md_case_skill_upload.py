from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import re
import ssl
import sys
import time
import subprocess
import types
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import parse as urllib_parse
from urllib import request as urllib_request
import bytedtos
import random
import string
import traceback

_RICHTEXT_PLACEHOLDER_RE = re.compile(r"\$\{richText_([^:]+):\s*([^}]*)\}")
_CASE_HEADER_RE = re.compile(r"^#{2,3}\s+(TC-[^\n]+)$", re.MULTILINE)
_FALLBACK_CASE_TITLE_RE = re.compile(r"^>\s*(.+?)\s*$", re.MULTILINE)
_META_LINE_RE = re.compile(r"^- \*\*([^*]+)\*\*:\s*(.*?)\s*$", re.MULTILINE)
_NUMBERED_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")
_STEP_ASSERTION_RE = re.compile(
    r"^\s*[-*]\s*(?:(?:\*\*)?(?:预期|expected)(?:\*\*)?\s*[:：]\s*(.+)|Assert\s*:\s*(.+))\s*$",
    re.IGNORECASE,
)
_TEMPLATE_HEADER_RE = re.compile(r"^####\s+([A-Za-z0-9\-_]+)\s*$", re.MULTILINE)
_DEEPLINK_RE = re.compile(r"(([A-Za-z][A-Za-z0-9+.\-]*)://[^\s`]+)")
_EXPLICIT_DEVICE_RE = re.compile(r"\b(?:设备|device)\s*([A-Z]|[1-9])\b", re.IGNORECASE)
_EXPLICIT_DEVICE_WITH_ROLE_RE = re.compile(
    r"(?:设备|device)\s*([A-Z]|[1-9])\s*(?:（([^）]+)）|\(([^)]+)\))?",
    re.IGNORECASE,
)
_HOST_HINT_RE = re.compile(r"(主播|host|开播方|preview)", re.IGNORECASE)
_VIEWER_HINT_RE = re.compile(r"(观众|\bviewer\b|A-VIEWER|T-VIEWER|public chat|room_id)", re.IGNORECASE)
_MODERATOR_HINT_RE = re.compile(r"(管理员|moderator)", re.IGNORECASE)
_GUEST_HINT_RE = re.compile(r"(嘉宾|guest)", re.IGNORECASE)
_LIVE_ROOM_HINT_RE = re.compile(r"(开播中|直播间|live room|同一直播间|Go Live)", re.IGNORECASE)
_ENTER_ROOM_HINT_RE = re.compile(
    r"(进入(?:该)?直播间|进入[^，。,；;\n]{0,20}直播间|尝试进入|看播|送礼|发送评论|输入.*评论|gift|comment|公屏|following|inbox|搜索)",
    re.IGNORECASE,
)

# env 只决定路由 header；network 只决定访问域名。两者正交：办公网访问 prod 时
# 域名仍是 tiktok-row，byteintl 只有机房内网能连通。
_OPEN_API_ENV_HEADERS = {
    "ppe": {
        "x-custom-token": "Z3VvZmVuZy5nZi8yMDI1LTAxLTE1IDA2OjMzOjQ1",
        "x-tt-env": "ppe_prd2case_tools",
        "x-use-ppe": "1",
    },
    "prod": {},
}
_OPEN_API_NETWORK_HOSTS = {
    "office": "ttat-openapi-sg.tiktok-row.net",
    "server": "ttat-openapi-sg.byteintl.net",
}
_GET_SKILL_FILE_RAW_PATH = "/ui/open_api/get_skill_file_raw"
_OPEN_API_TIMEOUT = 300
_OPEN_API_SSL_CTX = ssl.create_default_context()
_OPEN_API_SSL_CTX.check_hostname = False
_OPEN_API_SSL_CTX.verify_mode = ssl.CERT_NONE

_NON_HOST_DEVICE_NAMES = [
    "TT-非主播设备-1",
    "TT-非主播设备-2",
    "TT-非主播设备-3",
    "TT-非主播设备-4",
    "TT-非主播设备-5",
    "TT-非主播设备-6",
    "TT-非主播设备-7",
]
_HOST_DEVICE_NAMES = [
    "TT-主播设备-1",
    "TT-主播设备-2",
    "TT-主播设备-3",
    "TT-主播设备-4",
]

# 该设备只提供前置环境、本用例不对它下动作时的占位动作。
# 不能留空：设备在前置条件里声明了却在步骤里没有节点，UI 执行会报错。
_IDLE_STEP_TEXT = "保持当前状态，本用例不对该设备下发操作（仅提供前置环境）"


@dataclass
class AccountMapping:
    account_id: str
    role: str
    pool_name: str
    pool_id: str
    tag_name: str
    uid: str = ""
    phone: str = ""
    password: str = ""
    username: str = ""
    country_code: str = ""


@dataclass
class PreconditionToolRequirement:
    tool: str
    params: Dict[str, Any] = field(default_factory=dict)
    target: str = "all"
    role: str = ""
    device: str = ""
    account_id: str = ""
    case_id: str = ""
    tool_text: str = ""
    validate_required: bool = True


@dataclass
class GitMarkdownInput:
    repo_id: str
    path: str
    ref: str = "master"
    original: str = ""


@dataclass
class ParsedCase:
    title: str
    raw_title: str
    dir_name: str = "未分组"
    priority: str = ""
    tags: List[str] = field(default_factory=list)
    precondition_ref: str = ""
    extra: str = ""
    remark: str = ""
    steps: List[str] = field(default_factory=list)
    assertions: List[str] = field(default_factory=list)
    step_assertions: List[List[str]] = field(default_factory=list)
    block_text: str = ""


@dataclass
class DevicePlan:
    host_devices: List[str] = field(default_factory=list)
    non_host_devices: List[str] = field(default_factory=list)
    alias_to_device: Dict[str, str] = field(default_factory=dict)
    device_to_account_id: Dict[str, str] = field(default_factory=dict)

    @property
    def ordered_devices(self) -> List[str]:
        return self.host_devices + self.non_host_devices


@dataclass
class DevicePreconditions:
    tools: List[str] = field(default_factory=list)
    step_tools: List[str] = field(default_factory=list)
    remarks: List[str] = field(default_factory=list)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _is_git_markdown_input(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if text.startswith("git://"):
        return True
    parsed = urllib_parse.urlparse(text)
    if parsed.netloc == "code.byted.org" and ("/blob/" in parsed.path or "/tree/" in parsed.path):
        return True
    query = urllib_parse.parse_qs(parsed.query)
    return bool(query.get("repo_id") and query.get("path"))


def _split_code_by_ref(repo_id: str, rest: str) -> Tuple[str, str]:
    """Best-effort split for code.byted.org /blob|tree/<ref>/<path> URLs.

    Branch names may contain slashes. Prefer splitting at known content roots
    so URLs like /blob/agi/benchmark/businesses/... become:
    ref=agi/benchmark, path=businesses/...
    """
    parts = [part for part in rest.split("/") if part]
    if not parts:
        return "master", ""

    content_roots = (
        "businesses",
        "business",
        "tt-nova",
        "docs",
        "cases",
        "features",
    )
    for idx, part in enumerate(parts):
        if idx > 0 and part in content_roots:
            return "/".join(parts[:idx]), "/".join(parts[idx:])

    common_refs = ("master", "main", "develop", "dev", "agi/benchmark", "agi")
    for ref in common_refs:
        ref_parts = ref.split("/")
        if parts[: len(ref_parts)] == ref_parts and len(parts) > len(ref_parts):
            return ref, "/".join(parts[len(ref_parts):])
    return parts[0], "/".join(parts[1:])


def _parse_git_markdown_input(value: str, ref_override: str = "") -> GitMarkdownInput:
    text = (value or "").strip()
    parsed = urllib_parse.urlparse(text)
    query = urllib_parse.parse_qs(parsed.query)

    if parsed.scheme == "git":
        repo_id = parsed.netloc
        path = urllib_parse.unquote(parsed.path.lstrip("/"))
        ref = query.get("ref", [""])[0] or ref_override or "master"
    elif parsed.netloc == "code.byted.org" and ("/blob/" in parsed.path or "/tree/" in parsed.path):
        mode = "/blob/" if "/blob/" in parsed.path else "/tree/"
        repo_part, rest = parsed.path.lstrip("/").split(mode.strip("/"), 1)
        repo_id = repo_part.rstrip("/")
        ref, path = _split_code_by_ref(repo_id, urllib_parse.unquote(rest.lstrip("/")))
        ref = ref_override or query.get("ref", [""])[0] or ref
    else:
        repo_id = query.get("repo_id", [""])[0]
        path = query.get("path", [""])[0]
        ref = query.get("ref", [""])[0] or ref_override or "master"

    if not repo_id or not path:
        raise ValueError(
            "Git 输入需要包含 repo_id 和 path，例如 "
            "`git://999892/businesses/localservice/affiliate/docs/_index.md?ref=main`"
        )
    return GitMarkdownInput(repo_id=repo_id, path=path, ref=ref, original=text)


def _git_input_has_explicit_ref(value: str, ref_override: str = "") -> bool:
    """Whether a Git/Code markdown input carries an explicit ref.

    Explicit ref means either a non-empty ``--git-ref`` override, or a ``ref``
    query parameter on the URL/URI (e.g. ``...?ref=master``). The
    ``/blob/<ref>/`` path segment and GitLab's ``ref_type`` parameter are
    intentionally NOT treated as explicit: branch inference from the path is
    best-effort and can silently resolve the wrong commit, so we require the
    caller to confirm the branch before reading/uploading.
    """
    if (ref_override or "").strip():
        return True
    text = (value or "").strip()
    if not text:
        return False
    query = urllib_parse.parse_qs(urllib_parse.urlparse(text).query)
    return bool((query.get("ref", [""])[0] or "").strip())


def _missing_ref_error_message(value: str) -> str:
    return (
        f"检测到 Git/Code 链接缺少显式 ref，已停止，未上传：{value}\n"
        "请先向用户反问确认要使用的分支 / tag / commit，再二选一执行：\n"
        "  1) 在链接上补显式 ref，例如 `.../case-01-host.md?ref=master`；\n"
        "  2) 或追加命令参数 `--git-ref <branch>`。\n"
        "注意：链接里的 `ref_type=heads` 或路径中的 `/blob/<branch>/` 都不算显式 ref，"
        "脚本不会据此猜测分支并直接上传。"
    )


def _post_open_api_json(env: str, network: str, api_path: str, body: dict) -> dict:
    headers = _OPEN_API_ENV_HEADERS.get(env)
    if headers is None:
        raise ValueError(f"未知 env: {env}")
    host = _OPEN_API_NETWORK_HOSTS.get(network)
    if not host:
        raise ValueError(f"未知 network: {network}")
    url = f"https://{host}{api_path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=_OPEN_API_TIMEOUT, context=_OPEN_API_SSL_CTX) as resp:
        logid = resp.headers.get("x-tt-logid") or resp.headers.get("X-Tt-Logid", "")
        if logid:
            print(f"[git] logid: {logid}")
        return json.loads(resp.read().decode("utf-8"))


def _fetch_git_markdown(git_input: GitMarkdownInput, env: str, network: str) -> dict:
    payload = {
        "repo_id": git_input.repo_id,
        "ref": git_input.ref or "master",
        "path": git_input.path,
    }
    result = _post_open_api_json(env, network, _GET_SKILL_FILE_RAW_PATH, payload)
    if isinstance(result.get("data"), dict) and "content" in result["data"]:
        result = result["data"]
    content = result.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"get_skill_file_raw 未返回 content 字符串: {result}")
    return result


def _materialize_git_markdown(raw: dict, git_input: GitMarkdownInput, tmp_dir: str) -> str:
    _mkdir(tmp_dir)
    stem = _normalize_title_as_filename(Path(git_input.path).stem or "git_input")
    path = os.path.join(tmp_dir, f"{stem}_git_raw.md")
    _write_text(path, raw["content"])
    return path


def _resolve_standardized_dir(
    workspace_root: str,
    bucket: str,
    vc: str,
    module: str,
    skill_name: str,
) -> str:
    path = os.path.join(workspace_root, "tt-nova", "ui", bucket, vc, module, skill_name)
    _mkdir(path)
    return path


def _derive_ui_path(stem: str) -> str:
    normalized = stem or ""
    for suffix in ("_cases", "_case", "_spec", "_richtext"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)] or normalized
    return normalized


def _workspace_root(start: str) -> str:
    candidates = [
        os.path.abspath(start),
        os.getcwd(),
        str(Path(__file__).resolve()),
    ]
    for candidate in candidates:
        cur = candidate if os.path.isdir(candidate) else os.path.dirname(candidate)
        while True:
            if os.path.isdir(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    raise FileNotFoundError("未找到 workspace root（缺少 .git）")


def _collection_root() -> str:
    return str(Path(__file__).resolve().parents[2])


def _first_existing_path(candidates: List[str], desc: str) -> str:
    for path in candidates:
        if os.path.exists(path):
            return path
    joined = "\n".join(candidates)
    raise FileNotFoundError(f"未找到{desc}，已尝试:\n{joined}")


def _load_upload_module(workspace_root: str):
    path = _first_existing_path(
        [
            os.path.join(_collection_root(), "ui-xmind-case-upload", "scripts", "upload_cases.py"),
            os.path.join(workspace_root, "skills", "tt-nova-ui", "ui-xmind-case-upload", "scripts", "upload_cases.py"),
            os.path.join(workspace_root, ".agents", "skills", "tt-nova-ui", "ui-case-upload", "scripts", "upload_cases.py"),
        ],
        "upload_cases.py",
    )
    spec = importlib.util.spec_from_file_location("ui_case_upload_script", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 upload_cases.py: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 等在 exec 时要查 sys.modules
    spec.loader.exec_module(module)
    return module


def _load_ui_case_gen_helpers(workspace_root: str):
    gen_root = _first_existing_path(
        [
            os.path.join(_collection_root(), "ui-xmind-case-gen"),
            os.path.join(workspace_root, "skills", "tt-nova-ui", "ui-xmind-case-gen"),
            os.path.join(workspace_root, ".agents", "skills", "tt-nova-ui", "ui-case-gen"),
            os.path.join(workspace_root, ".codex", "skills", "ui-xmind-case-gen"),
        ],
        "ui-xmind-case-gen skill root",
    )
    script_pkg_dir = os.path.join(gen_root, "script")
    existing = sys.modules.get("script")
    if existing is None or not hasattr(existing, "__path__"):
        package = types.ModuleType("script")
        package.__path__ = [script_pkg_dir]
        sys.modules["script"] = package
    elif script_pkg_dir not in list(existing.__path__):
        existing.__path__.append(script_pkg_dir)
    if gen_root not in sys.path:
        sys.path.insert(0, gen_root)
    from script.device_role_skills import all_name_to_richtext_tag
    import script.tool_skills as tool_skills_module
    from script.tool_skills import (
        _match_tool_by_name,
        _register_skill_placeholder,
        reset_dynamic_registry,
        richtext_registry,
    )

    return {
        "name_to_tag": all_name_to_richtext_tag(),
        "match_tool": _match_tool_by_name,
        "register_placeholder": _register_skill_placeholder,
        "reset_dynamic_registry": reset_dynamic_registry,
        "richtext_registry": richtext_registry,
        "tool_skills_module": tool_skills_module,
    }


def _extract_title(md_text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
    return (m.group(1).strip() if m else fallback) or fallback


def _extract_precondition_templates(md_text: str) -> Dict[str, str]:
    section_m = re.search(r"^###\s+Precondition Templates\s*$", md_text, re.MULTILINE)
    if not section_m:
        return {}

    next_case_m = _CASE_HEADER_RE.search(md_text, section_m.end())
    end = next_case_m.start() if next_case_m else len(md_text)
    block = md_text[section_m.end():end]

    templates: Dict[str, str] = {}
    matches = list(_TEMPLATE_HEADER_RE.finditer(block))
    for idx, match in enumerate(matches):
        start = match.end()
        stop = matches[idx + 1].start() if idx + 1 < len(matches) else len(block)
        body = block[start:stop]
        code_m = re.search(r"```(?:\w+)?\n(.*?)\n```", body, re.DOTALL)
        content = code_m.group(1) if code_m else body
        templates[match.group(1).strip()] = content.strip()
    return templates


def _extract_account_mappings(md_text: str) -> Dict[str, AccountMapping]:
    """Parse the Common Test Accounts table from the markdown header.

    Expects a table with columns:
    | 账号 ID | 用途 | 角色 | 账号池 | pool_id? | 指定标签 | ...
    """
    section_m = re.search(
        r"^###?\s+\d*\.?\s*(?:通用测试账号|Common Test Accounts)",
        md_text, re.MULTILINE | re.IGNORECASE,
    )
    if not section_m:
        return {}

    next_section = re.search(r"^#{1,3}\s+", md_text[section_m.end():], re.MULTILINE)
    end = section_m.end() + next_section.start() if next_section else len(md_text)
    block = md_text[section_m.end():end]

    mappings: Dict[str, AccountMapping] = {}
    header: List[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cols = [col.strip().strip("`") for col in line.strip("|").split("|")]
        if not cols:
            continue
        if not header:
            header = cols
            continue
        if all(set(col.replace(" ", "")) <= {"-"} for col in cols if col):
            continue

        index_by_header = {name.lower().replace(" ", ""): idx for idx, name in enumerate(header)}

        def col(*names: str) -> str:
            for name in names:
                idx = index_by_header.get(name.lower().replace(" ", ""))
                if idx is not None and idx < len(cols):
                    return cols[idx].strip().strip("`")
            return ""

        acct_id = col("账号ID", "accountid", "id")
        if not acct_id:
            continue
        mappings[acct_id] = AccountMapping(
            account_id=acct_id,
            role=col("角色", "role"),
            pool_name=col("账号池", "pool_name", "pool"),
            pool_id=col("pool_id", "poolid"),
            tag_name=col("指定标签", "tag_name", "tag"),
        )
    return mappings


def _first_non_empty(mapping: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _account_mapping_from_dict(raw: Dict[str, Any]) -> Optional[AccountMapping]:
    account_id = _first_non_empty(raw, ["account_id", "accountId", "id", "账号ID", "账号 ID"])
    if not account_id:
        return None
    return AccountMapping(
        account_id=account_id.strip("`"),
        role=_first_non_empty(raw, ["role", "角色"]),
        pool_name=_first_non_empty(raw, ["pool_name", "poolName", "pool", "账号池"]),
        pool_id=_first_non_empty(raw, ["pool_id", "poolId", "poolid"]),
        tag_name=_first_non_empty(raw, ["tag_name", "tagName", "tag", "指定标签"]),
        uid=_first_non_empty(raw, ["uid", "UID", "uid_str", "用户ID", "用户 ID"]),
        phone=_first_non_empty(raw, ["phone", "phone_number", "mobile", "手机号"]),
        password=_first_non_empty(raw, ["password", "captcha", "密码", "验证码"]),
        username=_first_non_empty(raw, ["username", "user_name", "用户名"]),
        country_code=_first_non_empty(
            raw, ["country_code", "countryCode", "area_code", "区号", "国家区号"]
        ),
    )


def _normalize_account_mappings_payload(payload: Any) -> Dict[str, AccountMapping]:
    if isinstance(payload, dict):
        items = payload.get("account_mappings") or payload.get("accounts")
        if items is None:
            items = [
                {"account_id": key, **value}
                for key, value in payload.items()
                if isinstance(value, dict)
            ]
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    mappings: Dict[str, AccountMapping] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        mapping = _account_mapping_from_dict(item)
        if mapping:
            mappings[mapping.account_id] = mapping
    return mappings


def _load_account_mappings_from_json(json_text: str = "", json_path: str = "") -> Dict[str, AccountMapping]:
    if json_path:
        json_text = _read_text(os.path.abspath(os.path.expanduser(json_path)))
    if not json_text:
        return {}
    payload = json.loads(json_text)
    return _normalize_account_mappings_payload(payload)


def _assert_ttmock_ab_settings_param(param_name: str, value: Any) -> None:
    """Fail fast if ab_settings / ab_settings_live is present but not a JSON object.

    Accepts a dict (will be dumped later) or a JSON object string. Arrays, scalars,
    and non-JSON text are rejected. Empty / absent is allowed (optional param).
    """
    if value is None:
        return
    if isinstance(value, dict):
        return
    if isinstance(value, list):
        raise ValueError(
            f"[INVALID_JSON_OBJECT] tool=ttmock_preset param={param_name} "
            f"reason=json_array_not_object hint=必须是 JSON 对象 "
            f'例如 {{"72192329":"1"}}，禁止数组/flight:/非 JSON'
        )
    raw = str(value).strip()
    if not raw:
        return
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(
            f"[INVALID_JSON_OBJECT] tool=ttmock_preset param={param_name} "
            f"reason=not_json:{exc} hint=必须是 JSON 对象 "
            f'例如 {{"72192329":"1"}} raw={raw[:120]!r}'
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"[INVALID_JSON_OBJECT] tool=ttmock_preset param={param_name} "
            f"reason=json_{type(parsed).__name__}_not_object hint=必须是 JSON 对象 "
            f'例如 {{"72192329":"1"}} raw={raw[:120]!r}'
        )


def _normalize_precondition_tools_payload(payload: Any) -> List[PreconditionToolRequirement]:
    if isinstance(payload, dict):
        items = payload.get("precondition_tools") or payload.get("tools") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    requirements: List[PreconditionToolRequirement] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        tool = _first_non_empty(item, ["tool", "tool_name", "name", "工具"])
        tool_text = _first_non_empty(item, ["tool_text", "text", "工具文本"])
        if not tool and not tool_text:
            continue
        params = item.get("params") or item.get("parameters") or item.get("入参") or {}
        if not isinstance(params, dict):
            params = {}
        tool_l = (tool or tool_text or "").strip().lower()
        if tool_l == "ttmock_preset" or tool_l.startswith("ttmock_preset "):
            for key in ("ab_settings", "ab_settings_live"):
                if key in params:
                    _assert_ttmock_ab_settings_param(key, params.get(key))
        requirements.append(
            PreconditionToolRequirement(
                tool=tool,
                params=params,
                target=_first_non_empty(item, ["target", "scope", "目标", "作用范围"]) or "all",
                role=_first_non_empty(item, ["role", "角色"]),
                device=_first_non_empty(item, ["device", "设备"]),
                account_id=_first_non_empty(item, ["account_id", "accountId", "账号ID", "账号 ID"]),
                case_id=_first_non_empty(item, ["case_id", "caseId", "用例ID"]),
                tool_text=tool_text,
                validate_required=bool(item.get("validate_required", True)),
            )
        )
    return requirements


def _load_precondition_tools_from_json(json_text: str = "", json_path: str = "") -> List[PreconditionToolRequirement]:
    if json_path:
        json_text = _read_text(os.path.abspath(os.path.expanduser(json_path)))
    if not json_text:
        return []
    payload = json.loads(json_text)
    return _normalize_precondition_tools_payload(payload)


def _format_tool_param_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _precondition_tool_text(requirement: PreconditionToolRequirement) -> str:
    if requirement.tool_text:
        return requirement.tool_text
    parts = [requirement.tool]
    for key, value in requirement.params.items():
        if value is None:
            continue
        parts.append(f"{key}={_format_tool_param_value(value)}")
    return " ".join(parts)


def _tool_requirement_matches_case(
    requirement: PreconditionToolRequirement,
    case: ParsedCase,
) -> bool:
    if requirement.case_id and requirement.case_id not in case.title:
        return False
    if requirement.account_id:
        return bool(re.search(_account_id_pattern(requirement.account_id), case.precondition_ref, re.IGNORECASE))
    return True


def _devices_for_tool_requirement(
    requirement: PreconditionToolRequirement,
    plan: DevicePlan,
    matched_mappings: List[AccountMapping],
) -> List[str]:
    if requirement.device:
        for alias, device in plan.alias_to_device.items():
            if requirement.device.lower() == alias.lower() or requirement.device == device:
                return [device]
        if requirement.device in plan.ordered_devices:
            return [requirement.device]

    target = (requirement.target or requirement.role or "").lower()
    if requirement.account_id:
        mapping = next(
            (item for item in matched_mappings if item.account_id.lower() == requirement.account_id.lower()),
            None,
        )
        if mapping:
            target = mapping.role.lower()
        elif "host" in requirement.account_id.lower():
            target = "host"
        elif "viewer" in requirement.account_id.lower() or "audience" in requirement.account_id.lower():
            target = "viewer"

    if target in ("host", "主播", "anchor"):
        return list(plan.host_devices)
    if target in ("viewer", "audience", "观众", "non_host", "non-host"):
        return list(plan.non_host_devices)
    if target in ("all", "全部", ""):
        return list(plan.ordered_devices)
    return list(plan.ordered_devices)


def _with_country_code(number: str, country_code: str) -> str:
    """手机号登录必须带区号（平台缺区号按 +86 解析）；号码自带 + 时不动，非号码不动。"""
    num = (number or "").strip().replace(" ", "")
    cc = (country_code or "").strip().replace(" ", "").lstrip("+")
    if num.startswith("+") or not cc or not num.isdigit():
        return num
    return f"+{cc}{num}"


def _account_mapping_tool_text(mapping: AccountMapping) -> str:
    # 指定账号优先：username > phone+password（fixed account）> UID > 账号池
    if mapping.username:
        parts = [f"username={_with_country_code(mapping.username, mapping.country_code)}"]
        if mapping.password:
            parts.append(f"password={mapping.password}")
        return f"测试账号 {' '.join(parts)}"
    if mapping.phone:
        phone = _with_country_code(re.sub(r"[^\d+]", "", mapping.phone), mapping.country_code)
        parts = [f"phone_number={phone}"]
        if mapping.password:
            parts.append(f"password={mapping.password}")
        return f"测试账号 {' '.join(parts)}"
    if mapping.uid:
        return f"测试账号 UID:{mapping.uid}"
    parts = [f"pool_name={mapping.pool_name}"]
    if mapping.pool_id:
        parts.append(f"pool_id={mapping.pool_id}")
    if mapping.tag_name:
        parts.append(f"tag_name={mapping.tag_name}")
    return f"测试账号 {' '.join(parts)}"


def _account_id_pattern(account_id: str) -> str:
    escaped = re.escape(account_id)
    return rf"(?<![A-Za-z0-9_-]){escaped}(?![A-Za-z0-9_-])"


def _matched_account_mappings(
    precondition_ref: str,
    account_mappings: Optional[Dict[str, AccountMapping]],
) -> List[AccountMapping]:
    if not precondition_ref or not account_mappings:
        return []

    matches: List[Tuple[int, AccountMapping]] = []
    for acct_id, mapping in account_mappings.items():
        m = re.search(_account_id_pattern(acct_id), precondition_ref, re.IGNORECASE)
        if m:
            matches.append((m.start(), mapping))
    matches.sort(key=lambda item: item[0])
    return [mapping for _, mapping in matches]


def _is_host_account_mapping(mapping: AccountMapping) -> bool:
    text = f"{mapping.account_id} {mapping.role}".lower()
    return "host" in text or "主播" in text


def _is_viewer_account_mapping(mapping: AccountMapping) -> bool:
    text = f"{mapping.account_id} {mapping.role}".lower()
    return "viewer" in text or "audience" in text or "观众" in text


def _account_tool_for_device(
    device: str,
    plan: DevicePlan,
    matched_mappings: List[AccountMapping],
) -> Tuple[str, bool]:
    if not matched_mappings:
        return "测试账号", False

    if device in plan.host_devices:
        host_mapping = next(
            (mapping for mapping in matched_mappings if _is_host_account_mapping(mapping)),
            matched_mappings[0],
        )
        return _account_mapping_tool_text(host_mapping), True

    viewer_mappings = [
        mapping for mapping in matched_mappings if _is_viewer_account_mapping(mapping)
    ]
    if not viewer_mappings:
        return _account_mapping_tool_text(matched_mappings[-1]), True

    non_host_idx = plan.non_host_devices.index(device) if device in plan.non_host_devices else 0
    mapping = viewer_mappings[min(non_host_idx, len(viewer_mappings) - 1)]
    return _account_mapping_tool_text(mapping), True


def _extract_section(block: str, heading: str) -> str:
    m = re.search(rf"^###\s+{re.escape(heading)}\s*$", block, re.MULTILINE)
    if not m:
        m = re.search(
            rf"^\*\*{re.escape(heading)}\*\*\s*:\s*$", block, re.MULTILINE
        )
    if not m:
        return ""
    next_heading = re.search(
        r"(?:^###\s+.+$|^\*\*[A-Za-z\u4e00-\u9fff]+\*\*[^:\n]*:\s*$)",
        block[m.end():],
        re.MULTILINE,
    )
    end = m.end() + next_heading.start() if next_heading else len(block)
    return block[m.end():end].strip()


_BULLET_ITEM_RE = re.compile(r"^\s*[-*]\s+(.*)$")


def _parse_numbered_list(section: str) -> List[str]:
    items: List[str] = []
    current: List[str] = []
    for raw in section.splitlines():
        line = raw.rstrip()
        m_num = _NUMBERED_ITEM_RE.match(line)
        m_bul = _BULLET_ITEM_RE.match(line) if not m_num else None
        if m_num:
            if current:
                items.append(" ".join(x.strip() for x in current if x.strip()))
            current = [m_num.group(2).strip()]
        elif m_bul:
            if current:
                items.append(" ".join(x.strip() for x in current if x.strip()))
            current = [m_bul.group(1).strip()]
        elif current and line.strip():
            current.append(line.strip())
    if current:
        items.append(" ".join(x.strip() for x in current if x.strip()))
    return items


def _parse_steps_with_assertions(section: str) -> Tuple[List[str], List[List[str]]]:
    steps: List[str] = []
    step_assertions: List[List[str]] = []
    current_step: List[str] = []
    current_assertions: List[str] = []

    for raw in section.splitlines():
        line = raw.rstrip()
        numbered = _NUMBERED_ITEM_RE.match(line)
        if numbered:
            if current_step:
                steps.append(" ".join(x.strip() for x in current_step if x.strip()))
                step_assertions.append(list(current_assertions))
            current_step = [numbered.group(2).strip()]
            current_assertions = []
            continue

        assertion = _STEP_ASSERTION_RE.match(line)
        if assertion and current_step:
            text = (assertion.group(1) or assertion.group(2) or "").strip()
            if text:
                current_assertions.append(text)
            continue

        if re.fullmatch(r"\s*[-*_]{3,}\s*", line):
            continue

        if current_step and line.strip():
            current_step.append(line.strip())

    if current_step:
        steps.append(" ".join(x.strip() for x in current_step if x.strip()))
        step_assertions.append(list(current_assertions))

    return steps, step_assertions


def _case_precondition_text(block: str, meta: Dict[str, str]) -> str:
    return meta.get("precondition", "") or _extract_section(block, "Precondition")


def _extract_case_remark_text(block: str, meta: Dict[str, str]) -> str:
    return meta.get("remark", "") or _extract_section(block, "Notes")


def _parsed_case_from_block(title: str, block: str) -> ParsedCase:
    meta = {k.strip().lower(): v.strip() for k, v in _META_LINE_RE.findall(block)}
    steps, step_assertions = _parse_steps_with_assertions(_extract_section(block, "Steps"))
    assertions = _parse_numbered_list(_extract_section(block, "Assertions"))
    if not assertions:
        assertions = _parse_numbered_list(_extract_section(block, "Assert"))
    if not assertions and step_assertions:
        assertions = [item for group in step_assertions for item in group]
    tags = [x.strip() for x in meta.get("tags", "").split(",") if x.strip()]
    return ParsedCase(
        title=title,
        raw_title=title,
        dir_name=meta.get("dir", "未分组") or "未分组",
        priority=meta.get("priority", ""),
        tags=tags,
        precondition_ref=_case_precondition_text(block, meta),
        extra=meta.get("extra", ""),
        remark=_extract_case_remark_text(block, meta),
        steps=steps,
        assertions=assertions,
        step_assertions=step_assertions,
        block_text=block.strip(),
    )


def _parse_fallback_cases(md_text: str) -> List[ParsedCase]:
    """Support BITS-export style docs where cases are introduced by blockquote titles."""
    title_matches = []
    for match in _FALLBACK_CASE_TITLE_RE.finditer(md_text):
        next_text = md_text[match.end():]
        next_title = _FALLBACK_CASE_TITLE_RE.search(next_text)
        block_end = match.end() + next_title.start() if next_title else len(md_text)
        block = md_text[match.start():block_end]
        if _extract_section(block, "Steps"):
            title_matches.append((match, block_end))

    cases: List[ParsedCase] = []
    for idx, (match, block_end) in enumerate(title_matches, start=1):
        title_text = match.group(1).strip()
        block = md_text[match.start():block_end]
        cases.append(_parsed_case_from_block(f"TC-R-{idx:03d} {title_text}", block))
    return cases


def _parse_cases(md_text: str) -> List[ParsedCase]:
    cases: List[ParsedCase] = []
    matches = list(_CASE_HEADER_RE.finditer(md_text))
    if not matches:
        return _parse_fallback_cases(md_text)
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(md_text)
        block = md_text[start:end]
        title = match.group(1).strip()
        cases.append(_parsed_case_from_block(title, block))
    return cases


def _ordered_unique(items: Iterable[str]) -> List[str]:
    seen: OrderedDict[str, None] = OrderedDict()
    for item in items:
        text = (item or "").strip()
        if text and text not in seen:
            seen[text] = None
    return list(seen.keys())


def _normalize_title_as_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return safe.strip("_") or "case_upload"


def _collect_text_fields(case: ParsedCase, template_text: str) -> str:
    parts = [
        case.title,
        case.precondition_ref,
        template_text,
        case.extra,
        case.remark,
        "\n".join(case.steps),
        "\n".join(case.assertions),
        case.block_text,
    ]
    return "\n".join(x for x in parts if x).strip()


def _needs_host_device(case: ParsedCase, template_text: str, explicit_non_host_count: int) -> bool:
    combined = _collect_text_fields(case, template_text)
    if _HOST_HINT_RE.search(combined):
        return True
    if explicit_non_host_count > 0 and _LIVE_ROOM_HINT_RE.search(combined):
        return True
    if explicit_non_host_count > 0 and _VIEWER_HINT_RE.search(combined):
        return True
    if case.precondition_ref.upper().startswith("T-HOST"):
        return True
    if case.precondition_ref.upper().startswith("T-VIEWER"):
        return True
    return False


def _infer_explicit_device_roles(case: ParsedCase) -> Tuple[List[str], List[str]]:
    host_labels: List[str] = []
    non_host_labels: List[str] = []
    for match in _EXPLICIT_DEVICE_WITH_ROLE_RE.finditer(case.block_text):
        label = match.group(1).upper()
        role_text = (match.group(2) or match.group(3) or "").strip()
        if role_text and _HOST_HINT_RE.search(role_text):
            _append_unique(host_labels, label)
        else:
            _append_unique(non_host_labels, label)
    return host_labels, non_host_labels


def _account_driven_device_plan(
    case: ParsedCase,
    template_text: str,
    account_mappings: Optional[Dict[str, "AccountMapping"]],
) -> Optional[DevicePlan]:
    """涉及多个账号的用例 → 每个账号一台设备。

    当用例 Precondition 命中 >=2 个不同账号映射时，按账号拆设备：
    host 角色账号 → 主播设备，其它 → 非主播设备，并把每台设备直接绑到对应账号。
    """
    if not account_mappings:
        return None
    ref = " ".join(x for x in [case.precondition_ref, template_text] if x)
    matched = _matched_account_mappings(ref, account_mappings)

    # 按“真实账号”去重：同一物理账号（uid/phone/username/账号池）只占一台设备，
    # 避免同一账号被多个占位符（如 "A" 与 "16+ 账号"）拆成多台。
    def _physical_key(m: AccountMapping) -> str:
        return (
            m.uid
            or re.sub(r"\D", "", m.phone)
            or m.username
            or f"{m.pool_name}|{m.pool_id}|{m.tag_name}"
        )

    distinct: List[AccountMapping] = []
    aids_by_key: Dict[str, List[str]] = {}
    key_index: Dict[str, int] = {}
    for m in matched:
        key = _physical_key(m)
        if key in key_index:
            aids_by_key[key].append(m.account_id)
        else:
            key_index[key] = len(distinct)
            distinct.append(m)
            aids_by_key[key] = [m.account_id]
    if len(distinct) < 2:
        return None

    plan = DevicePlan()
    host_i = 0
    nonhost_i = 0
    for mapping in distinct:
        if _is_host_account_mapping(mapping) and host_i < len(_HOST_DEVICE_NAMES):
            device = _HOST_DEVICE_NAMES[host_i]
            host_i += 1
            plan.host_devices.append(device)
        else:
            if nonhost_i >= len(_NON_HOST_DEVICE_NAMES):
                raise ValueError(f"{case.title}: 非主播设备数超过上限 {len(_NON_HOST_DEVICE_NAMES)}")
            device = _NON_HOST_DEVICE_NAMES[nonhost_i]
            nonhost_i += 1
            plan.non_host_devices.append(device)
        plan.device_to_account_id[device] = mapping.account_id
        for aid in aids_by_key[_physical_key(mapping)]:
            plan.alias_to_device[aid] = device
            plan.alias_to_device[f"账号 {aid}"] = device
            plan.alias_to_device[f"账号{aid}"] = device
        if mapping.role:
            plan.alias_to_device.setdefault(mapping.role, device)
    return plan


def _infer_device_plan(case: ParsedCase, template_text: str) -> DevicePlan:
    combined = _collect_text_fields(case, template_text)
    host_labels, labeled_non_hosts = _infer_explicit_device_roles(case)
    labels = _ordered_unique(m.group(1).upper() for m in _EXPLICIT_DEVICE_RE.finditer(combined))
    precondition_text = " ".join(x for x in [case.precondition_ref, template_text] if x)
    title_text = case.title or ""

    non_host_aliases: List[str] = []
    if labels:
        explicit_non_host_labels = [label for label in labels if label not in host_labels]
        if labeled_non_hosts:
            explicit_non_host_labels = [
                label for label in explicit_non_host_labels if label in labeled_non_hosts
            ]
        non_host_aliases.extend([f"device {label}" for label in explicit_non_host_labels])
    else:
        if _MODERATOR_HINT_RE.search(precondition_text):
            non_host_aliases.append("moderator")
        if _GUEST_HINT_RE.search(precondition_text):
            non_host_aliases.append("guest")
        if (
            _VIEWER_HINT_RE.search(precondition_text)
            or case.precondition_ref.upper().startswith("T-VIEWER")
            or ("观众" in title_text)
        ):
            non_host_aliases.append("viewer")

    non_host_aliases = _ordered_unique(non_host_aliases)
    host_needed = _needs_host_device(case, template_text, len(non_host_aliases))

    if not host_needed and not non_host_aliases:
        host_needed = True

    if len(non_host_aliases) > len(_NON_HOST_DEVICE_NAMES):
        raise ValueError(f"{case.title}: 非主播设备数超过上限 {len(_NON_HOST_DEVICE_NAMES)}")

    plan = DevicePlan()
    if host_needed:
        for idx, label in enumerate(host_labels[: len(_HOST_DEVICE_NAMES)]):
            device_name = _HOST_DEVICE_NAMES[idx]
            plan.host_devices.append(device_name)
            plan.alias_to_device[f"设备 {label}"] = device_name
            plan.alias_to_device[f"device {label}"] = device_name
            plan.alias_to_device[label] = device_name
        if not plan.host_devices:
            plan.host_devices.append(_HOST_DEVICE_NAMES[0])
        plan.alias_to_device["host"] = plan.host_devices[0]
        plan.alias_to_device["主播"] = plan.host_devices[0]

    for idx, alias in enumerate(non_host_aliases):
        device_name = _NON_HOST_DEVICE_NAMES[idx]
        plan.non_host_devices.append(device_name)
        plan.alias_to_device[alias] = device_name
        if alias == "viewer":
            plan.alias_to_device["观众"] = device_name
        if alias == "moderator":
            plan.alias_to_device["管理员"] = device_name
        if alias == "guest":
            plan.alias_to_device["嘉宾"] = device_name
        if alias.startswith("device "):
            label = alias.split(" ", 1)[1]
            plan.alias_to_device[f"设备 {label}"] = device_name
            plan.alias_to_device[f"device {label}"] = device_name
            plan.alias_to_device[label] = device_name

    return plan


def _extract_deeplinks(text: str) -> List[str]:
    urls = [m.group(1).strip() for m in _DEEPLINK_RE.finditer(text or "")]
    code_urls = re.findall(r"`(([A-Za-z][A-Za-z0-9+.\-]*)://[^`]+)`", text or "")
    code_urls = [u[0] if isinstance(u, tuple) else u for u in code_urls]
    return _ordered_unique(urls + code_urls)


def _pick_default_remark_device(plan: DevicePlan) -> str:
    if plan.host_devices:
        return plan.host_devices[0]
    if plan.non_host_devices:
        return plan.non_host_devices[0]
    return _HOST_DEVICE_NAMES[0]


def _deduce_devices_for_deeplink(plan: DevicePlan, line: str) -> List[str]:
    lower = (line or "").lower()
    if "主播" in lower or "host" in lower or "preview" in lower:
        return plan.host_devices[:1]
    if plan.non_host_devices:
        return list(plan.non_host_devices)
    return plan.host_devices[:1]


def _append_unique(target: List[str], item: str) -> None:
    if item and item not in target:
        target.append(item)


def _register_tool_placeholder(tool_text: str, device_name: str, helpers: dict, validate_required: bool = True) -> str:
    matcher = helpers["match_tool"]
    register = helpers["register_placeholder"]
    skill = matcher(tool_text, allow_prefix=True)
    if not skill:
        return ""
    if skill.name_en == "open_schema":
        return _register_open_schema_placeholder(skill, tool_text, helpers)
    if skill.name == "ttmock_preset" and _is_empty_ttmock_tool_text(tool_text):
        return _register_empty_ttmock_placeholder(skill, helpers)
    context = f"{tool_text} __device__={device_name}"
    return register(skill, context=context, validate_required=validate_required)


def _register_open_schema_placeholder(skill, tool_text: str, helpers: dict) -> str:
    module = helpers["tool_skills_module"]
    m = re.search(r"\burl=([^\s]+)", tool_text)
    if not m:
        return ""
    url = m.group(1).strip()
    input_data = json.dumps(
        [
            {"key": "url", "value": [url]},
            {"key": "required", "value": ["True"]},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    # Each tool call must get a unique mentionId (and uuid), even with identical inputData.
    use_uuid, use_mid = skill._new_invocation_ids()
    module._dynamic_richtext_entries[use_uuid] = {
        "type": 2,
        "text": skill.name,
        "id": use_mid,
        "mentionType": skill.mention_type,
        "token": "32",
        "uuid": use_uuid,
        "pluginData": {
            "autoxToolSaveBindItem": {
                "mentionId": use_mid,
                "biz": 1,
                "saitamaTemplateId": skill.saitama_template_id,
                "inputData": input_data,
                "appId": skill.app_id,
            }
        },
    }
    return skill.richtext_placeholder(variant_uuid=use_uuid)


def _register_empty_ttmock_placeholder(skill, helpers: dict) -> str:
    module = helpers["tool_skills_module"]
    input_data = json.dumps(
        [
            {"key": "language", "value": []},
            {"key": "region", "value": []},
            {"key": "ab_settings", "value": []},
            {"key": "ab_settings_live", "value": []},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    # Each tool call must get a unique mentionId (and uuid), even with identical inputData.
    use_uuid, use_mid = skill._new_invocation_ids()
    module._dynamic_richtext_entries[use_uuid] = {
        "type": 2,
        "text": skill.name,
        "id": use_mid,
        "mentionType": skill.mention_type,
        "token": "32",
        "uuid": use_uuid,
        "pluginData": {
            "autoxToolSaveBindItem": {
                "mentionId": use_mid,
                "biz": 1,
                "saitamaTemplateId": skill.saitama_template_id,
                "inputData": input_data,
                "appId": skill.app_id,
            }
        },
    }
    return skill.richtext_placeholder(variant_uuid=use_uuid)


def _is_empty_ttmock_tool_text(tool_text: str) -> bool:
    return (tool_text or "").strip() == "ttmock_preset"


def _is_ttmock_requirement(requirement: PreconditionToolRequirement) -> bool:
    tool = (requirement.tool or requirement.tool_text or "").strip().lower()
    return tool in ("ttmock_preset", "tt mock preset") or tool.startswith("ttmock_preset ")


def _with_ttat_remark_body(body: str) -> str:
    """前置条件 remark 统一带 `<ttat>`，对齐 ui-xmind-case-gen 渲染约定。"""
    cleaned = (body or "").strip()
    if not cleaned:
        return "<ttat>"
    if cleaned.lower().startswith("<ttat>"):
        return cleaned
    return f"<ttat> {cleaned}"


def _build_case_preconditions(
    case: ParsedCase,
    template_text: str,
    plan: DevicePlan,
    helpers: dict,
    account_mappings: Optional[Dict[str, "AccountMapping"]] = None,
    precondition_tools: Optional[List[PreconditionToolRequirement]] = None,
    source_url: str = "",
) -> Dict[str, DevicePreconditions]:
    device_map: Dict[str, DevicePreconditions] = {
        device: DevicePreconditions() for device in plan.ordered_devices
    }

    matched_mappings = _matched_account_mappings(case.precondition_ref, account_mappings)
    uid_m = None if matched_mappings else re.search(
        r'UID[=:：\s]*(\d{15,25})', case.block_text, re.IGNORECASE
    )
    for device in plan.ordered_devices:
        bound_account_id = plan.device_to_account_id.get(device)
        if bound_account_id and account_mappings and bound_account_id in account_mappings:
            account_tool_text = _account_mapping_tool_text(account_mappings[bound_account_id])
            skip_pool_id_validation = True
        elif matched_mappings:
            account_tool_text, skip_pool_id_validation = _account_tool_for_device(
                device, plan, matched_mappings
            )
        elif uid_m:
            account_tool_text = f"测试账号 UID:{uid_m.group(1)}"
            skip_pool_id_validation = False
        else:
            account_tool_text = "测试账号"
            skip_pool_id_validation = False

        placeholder = _register_tool_placeholder(
            account_tool_text, device, helpers,
            validate_required=not skip_pool_id_validation,
        )
        if placeholder:
            _append_unique(device_map[device].tools, placeholder)

    ttmock_by_device: Dict[str, PreconditionToolRequirement] = {}
    for requirement in precondition_tools or []:
        if not _is_ttmock_requirement(requirement):
            continue
        if not _tool_requirement_matches_case(requirement, case):
            continue
        for device in _devices_for_tool_requirement(requirement, plan, matched_mappings):
            ttmock_by_device[device] = requirement

    for device in plan.ordered_devices:
        requirement = ttmock_by_device.get(device)
        tool_text = _precondition_tool_text(requirement) if requirement else "ttmock_preset"
        # ab_settings 格式校验不依赖 validate_required：只要出现就必须是 JSON 对象
        force_validate = bool(
            requirement
            and (
                requirement.validate_required
                or "ab_settings" in (requirement.params or {})
                or "ab_settings_live" in (requirement.params or {})
                or "ab_settings" in tool_text
                or "ab_settings_live" in tool_text
            )
        )
        placeholder = _register_tool_placeholder(
            tool_text,
            device,
            helpers,
            validate_required=force_validate if requirement else False,
        )
        if not placeholder:
            raise ValueError(f"{case.title}: 未匹配到前置工具 `{tool_text}`")
        _append_unique(device_map[device].tools, placeholder)

    # 显式传入的其它前置工具（如 环境名称）：账号/ttmock 之外，按 target 绑定到设备。
    for requirement in precondition_tools or []:
        if _is_ttmock_requirement(requirement):
            continue
        if not _tool_requirement_matches_case(requirement, case):
            continue
        tool_text = _precondition_tool_text(requirement)
        for device in _devices_for_tool_requirement(requirement, plan, matched_mappings):
            placeholder = _register_tool_placeholder(
                tool_text, device, helpers,
                validate_required=requirement.validate_required,
            )
            if not placeholder:
                raise ValueError(f"{case.title}: 未匹配到前置工具 `{tool_text}`")
            _append_unique(device_map[device].tools, placeholder)

    source_lines = []
    if template_text:
        source_lines.extend([x.strip("- ").strip() for x in template_text.splitlines() if x.strip()])
    if case.extra:
        source_lines.append(case.extra.strip())
    if case.remark:
        source_lines.append(case.remark.strip())

    for line in source_lines:
        stripped = line.strip()
        if stripped and any(key in stripped.lower() for key in ["app:", "环境:", "角色:", "直播间:", "进入方式:"]):
            device = _pick_default_remark_device(plan)
            _append_unique(device_map[device].remarks, stripped)

    # 溯源 remark 恒定挂在操作步骤行（见 _render_case_markdown）：下游要从步骤里读回
    # 这个 git 链接，放在前置条件里读不到。这里只留一条空 remark 保持节点被 <ttat> 标记
    # （_append_unique 会丢弃空串，故直接 append）。
    trace_device = _pick_default_remark_device(plan)
    if "" not in device_map[trace_device].remarks:
        device_map[trace_device].remarks.append("")

    return device_map


def _format_precondition_parts(payload: DevicePreconditions) -> List[str]:
    parts: List[str] = []
    for remark in payload.remarks:
        parts.append(f"**[remark]** {_with_ttat_remark_body(remark)}")
    parts.extend(payload.tools)
    return parts


def _render_preconditions_markdown(
    plan: DevicePlan,
    device_preconditions: Dict[str, DevicePreconditions],
    name_to_tag: Dict[str, str],
    multi_role: bool,
) -> List[str]:
    lines: List[str] = []
    if multi_role:
        for device_name in plan.ordered_devices:
            payload = device_preconditions[device_name]
            tag = name_to_tag[device_name]
            parts = _format_precondition_parts(payload)
            if not parts:
                # 设备无工具也要出现在前置条件里：这里漏掉一台，就会和步骤里的设备对不上
                parts = [f"**[remark]** {_with_ttat_remark_body('')}"]
            lines.append(f"{tag} {'; '.join(parts)};\n")
    else:
        parts: List[str] = []
        for device_name in plan.ordered_devices:
            parts.extend(_format_precondition_parts(device_preconditions[device_name]))
        if parts:
            lines.append(f"{'; '.join(parts)};\n")
    return lines


def _skill_step_text(case: ParsedCase, source_url: str) -> str:
    short_title = case.title.split(": ", 1)[1] if ": " in case.title else case.title
    return f"{short_title} + {source_url}"


def _case_remark_text(
    case: ParsedCase,
    source_url: str,
) -> str:
    return f"[md] {_skill_step_text(case, source_url)}"


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u200b", "").strip())


_ASSERT_CATEGORY_RE = re.compile(
    r"^(?:text|state|visual|data|defer)\s*\|\s*", re.IGNORECASE
)


def _strip_assert_category(text: str) -> str:
    return _ASSERT_CATEGORY_RE.sub("", text or "").strip()


_TRACKING_EVENT_RE = re.compile(
    r"(不上报|上报)\s*`([^`]+)`(?:\s*埋点)?",
)


def _to_data_assertion_tool_text(assertion: str) -> Optional[str]:
    """把埋点断言自然语言转成 data_assertion 工具入参串；非埋点返回 None。

    上报 `livesdk_ai_guide_entrance_show` 埋点；`anchor_id` 有值；…
      → data_assertion data_filter_name=livesdk_ai_guide_entrance_show
         assert_type=AppLog assertion=`anchor_id` 有值；…
    不上报 `livesdk_xxx` 埋点。
      → … assertion=不上报
    """
    s = (assertion or "").strip()
    if not s:
        return None
    if s.lower().startswith("data_assertion"):
        return s
    m = _TRACKING_EVENT_RE.search(s)
    if not m:
        return None
    polarity, event = m.group(1), m.group(2).strip()
    if not event:
        return None
    rest = s[m.end() :].lstrip("；;，, \t").rstrip("。.\n\r ")
    if rest:
        body = rest
    else:
        body = "不上报" if polarity == "不上报" else "上报"
    return (
        f"data_assertion data_filter_name={event} "
        f"assert_type=AppLog assertion={body}"
    )


def _wrap_assertion_with_data_tool(
    assertion: str, device_name: Optional[str], helpers: dict
) -> str:
    """埋点断言包成 data_assertion richtext 占位符；非埋点原样返回。"""
    tool_text = _to_data_assertion_tool_text(assertion)
    if not tool_text:
        return assertion
    device = device_name or _HOST_DEVICE_NAMES[0]
    placeholder = _register_tool_placeholder(
        tool_text, device, helpers, validate_required=True
    )
    return placeholder or assertion


_DEVICE_ASSERT_PREFIX_RE = re.compile(
    r"^(?:设备|device)\s*([A-Z]|[1-9])\s*(?:（([^）]+)）|\(([^)]+)\))?\s*[:：]\s*",
    re.IGNORECASE,
)

def _split_device_prefix(text: str) -> Tuple[Optional[str], str]:
    """Return (device_label like 'A'|'B'|None, remainder)."""
    raw = (text or "").strip()
    m = _DEVICE_ASSERT_PREFIX_RE.match(raw)
    if not m:
        return None, raw
    return m.group(1).upper(), raw[m.end() :].strip()


def _resolve_label_to_device(plan: DevicePlan, label: str) -> Optional[str]:
    if not label:
        return None
    for key in (
        label,
        f"设备 {label}",
        f"设备{label}",
        f"device {label}",
        f"device{label}",
    ):
        device = plan.alias_to_device.get(key) or plan.alias_to_device.get(key.lower())
        if device:
            return device
    # labeled host/non-host by registration order in _infer_device_plan
    if label in plan.alias_to_device:
        return plan.alias_to_device[label]
    return None


def _primary_device_for_text(
    text: str, plan: DevicePlan, default_device: Optional[str]
) -> Optional[str]:
    """Pick one device for a step/assert. Explicit 设备X： wins; else unique token match.

    Pass default_device=None to get None when the text names no role or names
    several — lets the caller fall back instead of silently picking the host.
    """
    label, _ = _split_device_prefix(text)
    if label:
        resolved = _resolve_label_to_device(plan, label)
        if resolved:
            return resolved
    low = _collapse_ws(text).lower()
    tokens = {d: _device_match_tokens(plan, d) for d in plan.ordered_devices}
    matched = [d for d in plan.ordered_devices if any(t in low for t in tokens[d])]
    if len(matched) == 1:
        return matched[0]
    if not matched:
        return default_device
    # multi-match (e.g. both 设备A and 设备B words): prefer explicit non-default only if
    # the text starts with that device's role marker; else default.
    return default_device


def _leading_device_in_text(text: str, plan: DevicePlan) -> Optional[str]:
    """文本里最先出现的角色词对应的设备 —— 中文里主语在前，先出现的通常就是执行者。

    比 `_primary_device_for_text` 的唯一匹配更能处理「观众给主播送礼物」这种双角色句。
    """
    low = _collapse_ws(text).lower()
    best, best_pos = None, len(low) + 1
    for device in plan.ordered_devices:
        for token in _device_match_tokens(plan, device):
            pos = low.find(token)
            if 0 <= pos < best_pos:
                best, best_pos = device, pos
    return best


def _starts_with_device_token(text: str, plan: DevicePlan, device: str) -> bool:
    low = _collapse_ws(text).lower()
    return any(low.startswith(t) for t in _device_match_tokens(plan, device))


def _ordered_assertions(case: ParsedCase) -> List[str]:
    """Flat assertion texts (legacy). Prefer _ordered_assertions_with_devices for multi-role."""
    items = _ordered_assertions_with_devices(
        case,
        DevicePlan(host_devices=[_HOST_DEVICE_NAMES[0]]),
    )
    return [text for _device, text in items]


def _ordered_assertions_with_devices(
    case: ParsedCase, plan: DevicePlan
) -> List[Tuple[Optional[str], str]]:
    """Return [(device_name|None, assertion_text)] with category stripped.

    Attribution order:
    1) explicit `设备X（角色）：` prefix on the assert line
    2) inherit device from the parent step (for step-level asserts)
    3) token match / default host
    """
    default_device = plan.host_devices[0] if plan.host_devices else (
        plan.ordered_devices[0] if plan.ordered_devices else None
    )
    out: List[Tuple[Optional[str], str]] = []

    def _emit(raw: str, inherited_device: Optional[str]) -> None:
        label, rest = _split_device_prefix(raw)
        text = _strip_assert_category(_collapse_ws(rest if label else raw))
        if not text:
            return
        device: Optional[str] = None
        if label:
            device = _resolve_label_to_device(plan, label)
        # 断言自身点名的角色优先于父步骤：观众侧的预期挂在主播执行的步骤下时，
        # 校验仍应发生在观众设备上。只有断言没点名或点了多个角色才沿用步骤设备。
        if not device:
            device = _primary_device_for_text(raw, plan, None)
        if not device:
            device = inherited_device
        if not device:
            device = default_device
        out.append((device, text))

    used_step_asserts = False
    if any(case.step_assertions):
        for step, group in zip(case.steps, case.step_assertions):
            if not group:
                continue
            used_step_asserts = True
            step_device = (
                _primary_device_for_text(step, plan, default_device)
                if default_device
                else None
            )
            for item in group:
                _emit(item, step_device)
    if not used_step_asserts:
        for item in case.assertions:
            _emit(item, None)
    return out


def _device_match_tokens(plan: DevicePlan, device: str) -> List[str]:
    tokens: set = set()
    is_host = device in plan.host_devices
    role_words = (
        ["主播", "host", "anchor", "开播方"]
        if is_host
        else ["观众", "viewer", "audience", "嘉宾", "guest", "管理员", "moderator"]
    )
    labels: List[str] = []
    for alias, mapped in plan.alias_to_device.items():
        if mapped != device:
            continue
        a = alias.strip()
        if len(a) >= 2:
            tokens.add(a.lower())
        if len(a) == 1 and re.fullmatch(r"[A-Za-z0-9]", a):
            labels.append(a)
    for label in labels:
        for pre in ("设备", "device", "账号"):
            tokens.add(f"{pre} {label}".lower())
            tokens.add(f"{pre}{label}".lower())
        for rw in role_words:
            tokens.add(f"{rw} {label}".lower())
            tokens.add(f"{rw}{label}".lower())
    # 仅当该角色设备唯一时，才允许裸角色词匹配，避免多设备误判
    if is_host and len(plan.host_devices) == 1:
        for rw in ("主播", "host", "anchor"):
            tokens.add(rw.lower())
    if (not is_host) and len(plan.non_host_devices) == 1:
        for rw in ("观众", "viewer", "audience", "嘉宾", "guest", "管理员", "moderator"):
            tokens.add(rw.lower())
    return list(tokens)


def self_check() -> int:
    """预期结果的设备归属：断言点名的角色 > 父步骤设备 > 默认主播。"""
    plan = DevicePlan(
        host_devices=["TT-主播设备-1"],
        non_host_devices=["TT-非主播设备-1"],
    )
    # 步骤由主播执行，但断言只点名观众 —— 校验必须落在观众设备上
    case = ParsedCase(
        title="t",
        raw_title="t",
        steps=["点击入口，打开主播地区的小时榜"],
        step_assertions=[["state | 观众侧展示小时榜入口"]],
    )
    got = _ordered_assertions_with_devices(case, plan)
    assert got == [("TT-非主播设备-1", "观众侧展示小时榜入口")], got

    # 断言同时点名两个角色 —— 归属不唯一，沿用父步骤（主播）
    case.step_assertions = [["state | （观众侧&主播侧）入口文案变化"]]
    assert _ordered_assertions_with_devices(case, plan)[0][0] == "TT-主播设备-1"

    # 显式 `设备X：` 前缀优先级最高，压过文本里的角色词
    case.step_assertions = [["设备B（观众）：主播侧入口消失"]]
    plan.alias_to_device = {"B": "TT-非主播设备-1"}
    assert _ordered_assertions_with_devices(case, plan)[0][0] == "TT-非主播设备-1"

    # env / network 正交：prod 不带 PPE header，但办公网域名仍是 tiktok-row
    assert _OPEN_API_ENV_HEADERS["prod"] == {}
    assert _OPEN_API_NETWORK_HOSTS["office"] == "ttat-openapi-sg.tiktok-row.net"

    # source_url 恒定落在操作步骤行，且不带 `<ttat>`（那是前置条件节点的标记约定）。
    # 下游要从步骤里读回这个链接，一旦漂回前置条件就读不到了。
    rendered = _render_case_markdown(
        "s",
        {"未分组": [(case, plan, {d: DevicePreconditions() for d in plan.ordered_devices})]},
        "https://code.byted.org/x",
        {"TT-主播设备-1": "${richText_1:TT-主播设备-1}", "TT-非主播设备-1": "${richText_2:TT-非主播设备-1}"},
    )
    section = ""
    step_rows = 0
    step_only: List[str] = []
    for line in rendered.splitlines():
        if line.startswith("#### **前置条件**"):
            section = "pre"
        elif line.startswith("##### **操作步骤**"):
            section = "step"
        elif line.startswith("###### **预期结果**"):
            section = "assert"
        elif section == "step" and line.strip():
            step_rows += 1
            step_only.append(line)
            assert "**[parallel]**" in line, f"步骤行缺 [parallel]: {line}"
        if "https://code.byted.org/x" in line:
            assert section == "step", f"source_url 落在 {section} 而非步骤: {line}"
            assert "<ttat>" not in line, line
    assert step_rows, "没渲染出任何步骤行，用例结构可能变了"
    assert _with_ttat_remark_body("") == "<ttat>"

    # 溯源 remark 只能挂最后一台设备：挂在非末行的行尾会被服务端连同行分隔符一起吃掉，
    # 多台设备被拼成一行（实测 case set 15794265，E/H 无换行、F/G 有换行）
    assert len(step_only) > 1, step_only
    assert "**[remark]**" not in step_only[0], f"remark 挂到了首行: {step_only[0]}"
    assert "**[remark]**" in step_only[-1], f"末行缺 remark: {step_only[-1]}"
    _assert_device_consistency(rendered)
    # 门禁要真拦得住：把 remark 挪回首行应当报错
    swapped = rendered.replace(step_only[-1], step_only[-1].replace("; **[remark]**", "", 1))
    swapped = swapped.replace(step_only[0], step_only[0].rstrip(";\n") + "; **[remark]** [md] x + u;")
    try:
        _assert_device_consistency(swapped)
    except ValueError as exc:
        assert "吃掉设备间换行" in str(exc), exc
    else:
        raise AssertionError("首行行尾 remark 未被门禁拦下")

    # 单设备用例的步骤同样要带 [parallel]（默认全并行）
    solo = DevicePlan(host_devices=["TT-主播设备-1"])
    solo_case = ParsedCase(title="t", raw_title="t", steps=["点一下"], step_assertions=[["state | ok"]])
    solo_md = _render_case_markdown(
        "s",
        {"未分组": [(solo_case, solo, {"TT-主播设备-1": DevicePreconditions()})]},
        "https://code.byted.org/x",
        {"TT-主播设备-1": "${richText_1:TT-主播设备-1}"},
    )
    assert "**[parallel]**" in next(l for l in solo_md.splitlines() if l.startswith("[md]"))

    # 观众侧用例：步骤里的「主播地区」是修饰语不是执行者，动作必须归观众，
    # 否则观众设备会落一行只有 [parallel] 的空步骤，与前置的 2 台设备对不上
    viewer_case = ParsedCase(
        title="观众侧展示小时榜入口；点击入口，打开主播地区的小时榜",
        raw_title="t",
        steps=["点击入口，打开主播地区的小时榜", "点击“？”，打开FAQ"],
        step_assertions=[["state | 观众侧展示小时榜入口"], []],
    )
    v_plan = DevicePlan(host_devices=["TT-主播设备-1"], non_host_devices=["TT-非主播设备-1"])
    by_dev = _attribute_steps_to_devices(viewer_case, v_plan)
    assert by_dev["TT-非主播设备-1"] and not by_dev["TT-主播设备-1"], by_dev

    # 标题同时点名两个角色时不做纠偏，按步骤自身的角色词分派
    dual = ParsedCase(
        title="主播未上榜，观众给主播送礼物达到上榜条件",
        raw_title="t",
        steps=["主播开播", "观众给主播送礼物"],
    )
    dual_by_dev = _attribute_steps_to_devices(dual, v_plan)
    assert dual_by_dev["TT-主播设备-1"] == ["主播开播"], dual_by_dev
    assert dual_by_dev["TT-非主播设备-1"] == ["观众给主播送礼物"], dual_by_dev

    # 确实没有动作的设备要落占位动作，不能留空行
    idle = ParsedCase(title="观众点击入口", raw_title="t", steps=["观众点击入口"])
    idle_md = _render_case_markdown(
        "s",
        {"未分组": [(idle, v_plan, {d: DevicePreconditions() for d in v_plan.ordered_devices})]},
        "https://code.byted.org/x",
        {"TT-主播设备-1": "${richText_1:TT-主播设备-1}", "TT-非主播设备-1": "${richText_2:TT-非主播设备-1}"},
    )
    assert _IDLE_STEP_TEXT in idle_md, idle_md
    _assert_device_consistency(idle_md)  # 不应抛

    # 门禁本身要拦得住：把占位动作抠掉，该行只剩 [parallel] 和 remark
    broken = idle_md.replace(f"[md] {_IDLE_STEP_TEXT}; ", "")
    assert broken != idle_md, "自检数据没构造成功"
    try:
        _assert_device_consistency(broken)
        raise AssertionError("空步骤行没被门禁拦住")
    except ValueError as exc:
        assert "前置有设备但步骤缺动作" in str(exc), exc
    # remark 和 [parallel] 都不算动作，真动作才算
    assert not _has_real_action("${richText_1:TT-主播设备-1} **[parallel]**;")
    assert not _has_real_action("${richText_1:TT-主播设备-1} **[parallel]**; **[remark]** [md] x + url;")
    assert _has_real_action("${richText_1:TT-主播设备-1} [md] 点一下; **[parallel]**;")

    # 步骤行带 `<ttat>` 必须被门禁拦住（前置条件才允许）
    ttat_bad = idle_md.replace(
        f"**[remark]** {_case_remark_text(idle, 'https://code.byted.org/x')}",
        "**[remark]** <ttat> [md] x + url",
        1,
    )
    assert ttat_bad != idle_md, "自检数据没构造成功"
    try:
        _assert_device_consistency(ttat_bad)
        raise AssertionError("步骤行 <ttat> 未被门禁拦下")
    except ValueError as exc:
        assert "步骤行出现 `<ttat>`" in str(exc), exc

    phone_acct = AccountMapping("a1", "主播", "", "", "", username="12345228746",
                                password="009468", country_code="81")
    assert _account_mapping_tool_text(phone_acct) == "测试账号 username=+8112345228746 password=009468"
    assert _account_mapping_tool_text(
        AccountMapping("a2", "", "", "", "", username="+8112345228746", country_code="65")
    ) == "测试账号 username=+8112345228746"
    assert _with_country_code("45.5kids", "81") == "45.5kids"

    pos = _to_data_assertion_tool_text(
        "上报 `livesdk_ai_guide_entrance_show` 埋点；`anchor_id` 有值；`enter_from` 有值；`room_id` 有值。"
    )
    assert pos == (
        "data_assertion data_filter_name=livesdk_ai_guide_entrance_show "
        "assert_type=AppLog assertion=`anchor_id` 有值；`enter_from` 有值；`room_id` 有值"
    ), pos
    neg = _to_data_assertion_tool_text("不上报 `livesdk_ai_guide_entrance_show` 埋点。")
    assert neg == (
        "data_assertion data_filter_name=livesdk_ai_guide_entrance_show "
        "assert_type=AppLog assertion=不上报"
    ), neg
    assert _to_data_assertion_tool_text("入口文案正确") is None

    print("md_case_skill_upload self-check OK")
    return 0


def _attribute_steps_to_devices(case: ParsedCase, plan: DevicePlan) -> Dict[str, List[str]]:
    devices = plan.ordered_devices
    result: Dict[str, List[str]] = {d: [] for d in devices}
    default_device = plan.host_devices[0] if plan.host_devices else devices[0]
    # 标题里最先出现的角色词就是本用例的执行者（"观众侧展示…打开主播地区的小时榜" -> 观众）
    case_device = _leading_device_in_text(case.title or "", plan)
    for step in case.steps:
        text = _collapse_ws(step)
        if not text:
            continue
        # exclusive: explicit 设备X： prefix wins (avoids dual-match on cross mentions)
        label, _ = _split_device_prefix(text)
        device = _resolve_label_to_device(plan, label) if label else None
        if not device:
            device = _primary_device_for_text(text, plan, None) or _leading_device_in_text(
                text, plan
            )
        if not device:
            device = case_device or default_device
        elif (
            case_device
            and case_device not in plan.host_devices
            and device in plan.host_devices
            and not _starts_with_device_token(text, plan, device)
        ):
            # 「观众侧」用例里的「打开主播地区的小时榜」「进入该主播直播间」，主播是修饰语不是执行者。
            # 判给主播会让观众设备一步都没有，与前置条件的设备数对不上，UI 执行报错。
            # 句首就点名主播的（"主播开播"）是真执行者，不纠。
            device = case_device
        result[device].append(text)
    return result


def _expected_result_count(case: ParsedCase) -> int:
    # device plan unknown here; count texts only
    if any(case.step_assertions):
        return sum(len(g) for g in case.step_assertions)
    return len([a for a in case.assertions if a and a.strip()])


_DEVICE_TAG_RE = re.compile(r"\$\{richText_[^:]+:(TT-[^}]+?)\}")


def _has_real_action(step_line: str) -> bool:
    """步骤行去掉设备占位符和 [parallel] / [remark] 这类标记后，还剩可执行内容吗。

    `${设备} **[parallel]**;` 这种只有标记的行在 bits 里是个没有动作的空节点，
    该设备等于没进步骤。
    """
    for segment in _DEVICE_TAG_RE.sub("", step_line).split(";"):
        seg = segment.strip()
        if not seg or seg == "**[parallel]**" or seg.startswith("**[remark]**"):
            continue
        if seg.replace("[md]", "").strip():
            return True
    return False


def _assert_device_consistency(markdown: str) -> None:
    """前置条件声明的设备，必须在操作步骤里各有一个带动作的节点，否则 UI 执行会报错。

    这是渲染后的兜底门禁：不管上游怎么改归属逻辑，设备对不齐就中止转换，
    不允许把坏包传到 bits。
    """
    problems: List[str] = []
    for block in markdown.split("\n### ")[1:]:
        title = block.splitlines()[0].strip()
        pre_devs: set = set()
        step_devs: set = set()
        exp_devs: set = set()
        step_lines: List[str] = []
        section = ""
        for line in block.splitlines()[1:]:
            if line.startswith("#### **前置条件**"):
                section = "pre"
                continue
            if line.startswith("##### **操作步骤**"):
                section = "step"
                continue
            if line.startswith("###### **预期结果**"):
                exp_devs.update(_DEVICE_TAG_RE.findall(line))
                section = "exp"
                continue
            if not line.strip():
                continue
            if section == "pre":
                pre_devs.update(_DEVICE_TAG_RE.findall(line))
            elif section == "step":
                step_lines.append(line)
                found = _DEVICE_TAG_RE.findall(line)
                if found and _has_real_action(line):
                    step_devs.update(found)
                # `<ttat>` 只属于前置条件节点；步骤 remark 带了就语义混乱
                if "<ttat>" in line.lower():
                    problems.append(f"{title}: 步骤行出现 `<ttat>`（只允许出现在前置条件）")
        # 服务端剥离非末行行尾的 **[remark]** 时会连行分隔符一起吃掉，
        # 多台设备会被拼成一行，UI 执行时第二台设备拿不到自己的动作。
        for line in step_lines[:-1]:
            if line.rstrip().rstrip(";").rsplit(";", 1)[-1].strip().startswith("**[remark]**"):
                problems.append(f"{title}: 非末行步骤行尾挂了 **[remark]**，会吃掉设备间换行")
        if missing := pre_devs - step_devs:
            problems.append(f"{title}: 前置有设备但步骤缺动作 -> {sorted(missing)}")
        if extra := step_devs - pre_devs:
            problems.append(f"{title}: 步骤出现前置未声明的设备 -> {sorted(extra)}")
        if orphan := exp_devs - pre_devs:
            problems.append(f"{title}: 预期结果绑定了前置未声明的设备 -> {sorted(orphan)}")
    if problems:
        raise ValueError(
            "设备编排不一致，已中止转换（前置/步骤/预期的设备必须对齐）:\n  "
            + "\n  ".join(problems[:20])
            + (f"\n  …共 {len(problems)} 处" if len(problems) > 20 else "")
        )


def _render_case_markdown(
    suite_title: str,
    grouped_cases: Dict[str, List[Tuple[ParsedCase, DevicePlan, Dict[str, DevicePreconditions]]]],
    source_url: str,
    name_to_tag: Dict[str, str],
    helpers: Optional[dict] = None,
) -> str:
    lines: List[str] = [f"# {suite_title}\n\n"]

    # 规则：整个 case 集里只要有一条用例涉及多角色（多设备），
    # 其余单角色用例也要配置一个默认设备（带设备角色占位符）。
    set_has_multi_role = any(
        len(plan.ordered_devices) > 1
        for items in grouped_cases.values()
        for (_case, plan, _pre) in items
    )

    for dir_name, items in grouped_cases.items():
        lines.append(f"## {dir_name}\n")
        for case, plan, device_preconditions in items:
            multi_device = len(plan.ordered_devices) > 1
            use_device_tags = multi_device or set_has_multi_role
            lines.append(f"### {case.title}\n")
            lines.append("#### **前置条件**\n")
            lines.extend(
                _render_preconditions_markdown(
                    plan, device_preconditions, name_to_tag, use_device_tags
                )
            )
            lines.append("\n")
            lines.append("##### **操作步骤**\n")
            # 溯源 note 内联挂到操作步骤行（同一行，非独立行，避免 BITS 导入器把独立
            # **[...]** 行当成空预期结果节点）。仅挂在第一台设备行。
            # 不加 `<ttat>`：那是前置条件节点的标记约定，步骤 remark 不需要
            step_note = f"**[remark]** {_case_remark_text(case, source_url)}"
            if use_device_tags:
                steps_by_device = _attribute_steps_to_devices(case, plan)
                for idx, device_name in enumerate(plan.ordered_devices):
                    tag = name_to_tag[device_name]
                    step_tools = list(device_preconditions[device_name].step_tools)
                    role_steps = steps_by_device.get(device_name, [])
                    segments: List[str] = []
                    if role_steps:
                        segments.append(" ".join(role_steps))
                    if step_tools:
                        segments.append("; ".join(step_tools))
                    if not segments:
                        # 只有 **[parallel]** 的空步骤行会让该设备在 bits 里没有可执行动作，
                        # 与前置条件里声明的设备数对不上，UI 执行直接报错。
                        segments.append(_IDLE_STEP_TEXT)
                    segments.append("**[parallel]**")
                    # remark 必须挂最后一台设备：服务端剥离非末行行尾的 **[remark]** 时，
                    # 会把该行的行分隔符一起吃掉，多台设备就被拼成一行（实测 case set 15794265）。
                    # note 是步骤节点级属性，挂哪一行都汇总到同一个节点，挂末行不丢信息。
                    if step_note and idx == len(plan.ordered_devices) - 1:
                        segments.append(step_note)
                    body = "; ".join(segments)
                    prefix = "[md] " if idx == 0 else ""
                    content = (prefix + body).strip()
                    lines.append(f"{tag} {content};\n" if content else f"{tag};\n")
            else:
                step_tools: List[str] = []
                for device_name in plan.ordered_devices:
                    step_tools.extend(device_preconditions[device_name].step_tools)
                all_steps = [_collapse_ws(s) for s in case.steps if _collapse_ws(s)]
                segments = []
                if all_steps:
                    segments.append(" ".join(all_steps))
                if step_tools:
                    segments.append("; ".join(step_tools))
                segments.append("**[parallel]**")
                if step_note:
                    segments.append(step_note)
                body = "; ".join(segments)
                lines.append(f"[md] {body};\n" if body else "[md]\n")
            expected_extra: List[str] = []
            if case.priority:
                expected_extra.append(f"**[priority]** {case.priority}")
            if case.tags:
                expected_extra.append(f"**[tag]** {', '.join(case.tags)}")
            suffix = (" " + " ".join(expected_extra)) if expected_extra else ""
            for device, assertion in _ordered_assertions_with_devices(case, plan):
                rendered = (
                    _wrap_assertion_with_data_tool(assertion, device, helpers)
                    if helpers
                    else assertion
                )
                if use_device_tags and device and device in name_to_tag:
                    tag = name_to_tag[device]
                    lines.append(f"###### **预期结果** {tag} {rendered}{suffix}\n")
                else:
                    lines.append(f"###### **预期结果** {rendered}{suffix}\n")
            lines.append("\n")
    return "".join(lines)


def _extract_richtext_from_markdown(markdown: str, registry: Dict[str, dict]) -> List[dict]:
    seen = set()
    order: List[str] = []
    for match in _RICHTEXT_PLACEHOLDER_RE.finditer(markdown):
        uid = match.group(1).strip()
        if uid and uid not in seen:
            seen.add(uid)
            order.append(uid)
    return [registry[uid] for uid in order if uid in registry]


def _render_richtext_markdown(richtext_list: List[dict]) -> str:
    content = json.dumps(richtext_list, ensure_ascii=False, indent=2)
    return f"# RichText List\n\n```json\n{content}\n```\n"


def _manifest_payload(
    input_path: str,
    source_url: str,
    grouped_cases: Dict[str, List[Tuple[ParsedCase, DevicePlan, Dict[str, DevicePreconditions]]]],
) -> dict:
    items = []
    for dir_name, entries in grouped_cases.items():
        for case, plan, device_preconditions in entries:
            items.append(
                {
                    "title": case.title,
                    "dir": dir_name,
                    "devices": plan.ordered_devices,
                    "preconditions": {
                        device: {
                            "remarks": payload.remarks,
                            "tool_count": len(payload.tools),
                            "step_tool_count": len(payload.step_tools),
                        }
                        for device, payload in device_preconditions.items()
                    },
                    "expected_result_count": _expected_result_count(case),
                }
            )
    return {
        "input_path": os.path.abspath(input_path),
        "source_url": source_url,
        "case_count": len(items),
        "cases": items,
    }


def _extract_json_payload(raw: str):
    text = (raw or "").strip()
    if not text:
        raise ValueError("gdpa-cli 返回为空")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"无法解析 gdpa-cli 输出为 JSON: {text[:300]}")


def _extract_tcc_value(response, key: str):
    if isinstance(response, dict):
        data = response.get("data", response)
        if isinstance(data, dict):
            for field in ("conf_value", "value", "config_value", "confValue", "content"):
                value = data.get(field)
                if value is None:
                    continue
                if isinstance(value, str):
                    stripped = value.strip()
                    if stripped.startswith("{") or stripped.startswith("["):
                        try:
                            return json.loads(stripped)
                        except json.JSONDecodeError:
                            return stripped
                    return stripped
                return value
            if key in data:
                return data[key]
    return response


def _resolve_tcc_vregion(space: str) -> str:
    if not space or space == "default":
        return os.environ.get("GDPA_TCC_VREGION", "sg")
    mapping = {
        "sg": "sg",
        "us": "us",
        "ttp": "ttp",
        "cn": "cn",
        "boe": "boe",
    }
    return mapping.get(space, space)


def _ensure_gdpa_session_id() -> str:
    for env_name in ("GDPA_SESSION_ID", "SESSION_ID"):
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value

    result = subprocess.run(
        ["gdpa-cli", "create-session"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "gdpa-cli create-session 失败: "
            f"code={result.returncode}, stderr={result.stderr.strip() or result.stdout.strip()}"
        )
    output = (result.stdout or "").strip()
    match = re.search(r"(sess_[A-Za-z0-9_]+)", output)
    if not match:
        raise RuntimeError(f"无法从 gdpa-cli create-session 输出中解析 session_id: {output}")
    return match.group(1)


def get_tcc_v2(psm, key, space='default'):
    try:
        session_id = _ensure_gdpa_session_id()
        payload = {
            "command": "query",
            "namespace": psm,
            "key": key,
            "vregion": _resolve_tcc_vregion(space),
        }
        result = subprocess.run(
            [
                "gdpa-cli",
                "run",
                "tcc-query",
                "--session-id",
                session_id,
                "--input",
                json.dumps(payload, ensure_ascii=False),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None, (
                f"gdpa-cli run tcc-query 失败: code={result.returncode}, "
                f"stderr={result.stderr.strip() or result.stdout.strip()}"
            )

        response = _extract_json_payload(result.stdout)
        value = _extract_tcc_value(response, key)
        if value in (None, "", []):
            return None, f"gdpa-cli run tcc-query 未返回 {psm}/{key} 的配置值"
        return value, None
    except Exception:
        msg = "get_tcc_v2 exception, " + traceback.format_exc()
        return None, msg


def _upload_source_to_tos(
    input_path: str
) -> str:
    try:
        content = Path(input_path).read_bytes()
        tos_config, error = get_tcc_v2("tiktok.ttat.llm_ai_service", "tos_config")
        if error:
            raise RuntimeError(error)
        if not isinstance(tos_config, dict):
            raise RuntimeError(f"tos_config 格式异常，期望 dict，实际为: {type(tos_config).__name__}")
        ak = tos_config["ak"]
        bucket_name = "tiktok-ttat-uimost-sg"

        tos_psm = "toutiao.tos.tosapi"
        tos_cluster = "default"
        tos_idc = "sg1"
        sub_domain = "tos-sg.tiktok-row.org"
        obj_key = ''.join(random.choices(string.ascii_letters, k=20))+".md"
        client = bytedtos.Client(bucket_name, ak,
                                service=tos_psm,
                                cluster=tos_cluster,
                                endpoint=sub_domain,
                                idc=tos_idc)
        resp = client.put_object(obj_key, content)
        print("action succ. code: {}, request_id: {}".format(resp.status_code, resp.headers[bytedtos.consts.ReqIdHeader]), obj_key)
    except bytedtos.TosException as e:
        raise RuntimeError(
            "upload to tos failed. code: {}, request_id: {}, message: {}".format(
                e.code, e.request_id, e.msg
            )
        ) from e
    return obj_key


def convert_markdown(
    input_path: str,
    source_url: str,
    out_dir: str,
    file_stem: str = "",
    manifest_dir: str = "",
    account_mappings: Optional[Dict[str, AccountMapping]] = None,
    precondition_tools: Optional[List[PreconditionToolRequirement]] = None,
) -> Dict[str, str]:
    workspace_root = _workspace_root(os.path.dirname(input_path))
    helpers = _load_ui_case_gen_helpers(workspace_root)
    helpers["reset_dynamic_registry"]()

    md_text = _read_text(input_path)
    suite_title = _extract_title(md_text, Path(input_path).stem)
    templates = _extract_precondition_templates(md_text)
    if account_mappings is None:
        account_mappings = _extract_account_mappings(md_text)
    cases = _parse_cases(md_text)
    if not cases:
        raise ValueError("未解析到任何 `## TC-...` 用例块")

    grouped_cases: Dict[str, List[Tuple[ParsedCase, DevicePlan, Dict[str, DevicePreconditions]]]] = defaultdict(list)
    for case in cases:
        template_text = templates.get(case.precondition_ref, case.precondition_ref)
        plan = _account_driven_device_plan(case, template_text, account_mappings) or _infer_device_plan(case, template_text)
        payload = _build_case_preconditions(
            case,
            template_text,
            plan,
            helpers,
            account_mappings,
            precondition_tools,
            source_url,
        )
        grouped_cases[case.dir_name].append((case, plan, payload))

    markdown = _render_case_markdown(
        suite_title, grouped_cases, source_url, helpers["name_to_tag"], helpers
    )
    _assert_device_consistency(markdown)
    registry = helpers["richtext_registry"]()
    richtext_list = _extract_richtext_from_markdown(markdown, registry)
    manifest = _manifest_payload(input_path, source_url, grouped_cases)

    _mkdir(out_dir)
    manifest_root = manifest_dir or out_dir
    _mkdir(manifest_root)
    base = _normalize_title_as_filename(file_stem or Path(input_path).stem)
    cases_path = os.path.join(out_dir, f"{base}_cases.md")
    richtext_path = os.path.join(out_dir, f"{base}_richtext.md")
    manifest_path = os.path.join(manifest_root, f"{base}_manifest.json")
    _write_text(cases_path, markdown)
    _write_text(richtext_path, _render_richtext_markdown(richtext_list))
    _write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

    return {
        "cases_path": cases_path,
        "richtext_path": richtext_path,
        "manifest_path": manifest_path,
        "case_count": str(len(cases)),
    }


def _infer_richtext_path(cases_path: str, explicit_richtext: str = "") -> str:
    if explicit_richtext:
        return os.path.abspath(os.path.expanduser(explicit_richtext))

    candidates = []
    base = os.path.basename(cases_path)
    dirname = os.path.dirname(cases_path)
    if base.endswith("_case.md"):
        candidates.append(os.path.join(dirname, base[:-8] + "_richtext.md"))
    if base.endswith("_cases.md"):
        candidates.append(os.path.join(dirname, base[:-9] + "_richtext.md"))
    if base == "cases.md":
        candidates.append(os.path.join(dirname, "richtext.md"))
    if base.endswith(".md"):
        stem = base[:-3]
        candidates.append(os.path.join(dirname, stem + "_richtext.md"))

    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)

    tried = ", ".join(candidates) if candidates else "（无可推断候选）"
    raise FileNotFoundError(f"未找到 richtext 文件。请显式传 --richtext，已尝试: {tried}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert markdown to temporary bits cases/richtext package, or directly upload existing cases/richtext"
    )
    parser.add_argument("--input", help="原始 markdown 文件路径（转换模式）")
    parser.add_argument("--cases", help="已存在的 *_cases.md 路径（直传模式）")
    parser.add_argument("--richtext", default="", help="已存在的 richtext.md 路径（直传模式，可省略自动推断）")
    parser.add_argument("--git-repo-id", default="", help="Git markdown 输入：仓库 ID 或仓库路径")
    parser.add_argument("--git-ref", default="", help="Git markdown 输入：分支、tag 或 commit sha；默认 master")
    parser.add_argument("--git-path", default="", help="Git markdown 输入：仓库内 markdown 文件路径")
    parser.add_argument("--out-dir", default="", help="上传前临时 cases.md / richtext.md 输出目录")
    parser.add_argument("--tmp-dir", default="", help="临时 manifest / 校验产物目录；默认同 --out-dir")
    parser.add_argument("--vc", default="", help="业务大类。与 --module 一起使用时，可自动落到 tt-nova/ui/tmp/{vc}/{module}/ui-md-case-upload/")
    parser.add_argument("--module", default="", help="业务模块。与 --vc 一起使用时启用标准化输出目录")
    parser.add_argument("--ui-path", default="", help="正式产物文件 stem；默认取输入文件名")
    parser.add_argument("--source-url", default="", help="已存在的原始 markdown TOS 链接；本地 md 未提供时自动上传 TOS")
    parser.add_argument("--account-mapping-json", default="", help="由 agent/LLM 从源文档理解后抽取的账号映射 JSON")
    parser.add_argument("--account-mapping-file", default="", help="由 agent/LLM 从源文档理解后抽取的账号映射 JSON 文件")
    parser.add_argument("--precondition-tools-json", default="", help="由 agent/LLM 从 Precondition 理解后抽取的通用前置工具 JSON")
    parser.add_argument("--precondition-tools-file", default="", help="由 agent/LLM 从 Precondition 理解后抽取的通用前置工具 JSON 文件")
    parser.add_argument("--skip-upload", action="store_true", help="仅转换，不上传 bits")
    parser.add_argument(
        "--source-url-in-step",
        action="store_true",
        help="[已废弃，空操作] 溯源 remark 现在恒定挂在操作步骤行；保留本参数只为不打断已有调用",
    )
    parser.add_argument("--project_id", type=int, help="bits project_id（取 /devops/{id}/）")
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
        help="update 时只处理指定 ### 标题（可重复）",
    )
    parser.add_argument(
        "--delete-case",
        action="append",
        default=[],
        help="update 时额外删除：'primary_title|||case_title'（可重复）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不调接口")
    parser.add_argument("--creator", default="", help="bits creator，默认取系统 USER")
    parser.add_argument(
        "--env",
        default="ppe",
        choices=["ppe", "prod"],
        help="上传环境，只控制 PPE 路由 header，默认 ppe",
    )
    parser.add_argument(
        "--network",
        default="office",
        choices=["office", "server"],
        help="调用网络，控制 OpenAPI 域名，默认 office",
    )
    parser.add_argument("--self-check", action="store_true", help="跑内置断言自检后退出")
    args = parser.parse_args()

    if args.self_check:
        sys.exit(self_check())

    explicit_git_input = bool(args.git_repo_id or args.git_path)
    mode_count = sum([bool(args.input), bool(args.cases), explicit_git_input])
    if mode_count != 1:
        raise ValueError("必须且只能提供一种模式：--input（本地/Git URI 转换模式）、--git-repo-id + --git-path（Git 转换模式）或 --cases（直传模式）")

    if args.input or explicit_git_input:
        git_input: Optional[GitMarkdownInput] = None
        raw_git_response: Optional[dict] = None
        if explicit_git_input:
            if not args.git_repo_id or not args.git_path:
                raise ValueError("Git 显式输入需要同时提供 --git-repo-id 和 --git-path")
            git_input = GitMarkdownInput(
                repo_id=args.git_repo_id,
                ref=args.git_ref or "master",
                path=args.git_path,
                original=f"git://{args.git_repo_id}/{args.git_path}?ref={args.git_ref or 'master'}",
            )
        elif _is_git_markdown_input(args.input):
            if not _git_input_has_explicit_ref(args.input, args.git_ref):
                raise ValueError(_missing_ref_error_message(args.input))
            git_input = _parse_git_markdown_input(args.input, args.git_ref)

        if git_input:
            workspace_root = _workspace_root(os.getcwd())
        else:
            input_path = os.path.abspath(os.path.expanduser(args.input))
            if not os.path.isfile(input_path):
                raise FileNotFoundError(f"输入文件不存在: {input_path}")
            workspace_root = _workspace_root(os.path.dirname(input_path))

        if args.out_dir:
            out_dir = os.path.abspath(os.path.expanduser(args.out_dir))
        elif args.vc and args.module:
            out_dir = _resolve_standardized_dir(
                workspace_root, "tmp", args.vc, args.module, "ui-md-case-upload"
            )
        else:
            out_dir = os.path.join(
                os.path.dirname(input_path),
                "output",
                _normalize_title_as_filename(Path(input_path).stem) + "_skill_upload",
            )
            out_dir = os.path.abspath(os.path.expanduser(out_dir))

        if args.tmp_dir:
            tmp_dir = os.path.abspath(os.path.expanduser(args.tmp_dir))
            _mkdir(tmp_dir)
        elif args.vc and args.module:
            tmp_dir = _resolve_standardized_dir(
                workspace_root, "tmp", args.vc, args.module, "ui-md-case-upload"
            )
        else:
            tmp_dir = out_dir

        if git_input:
            raw_git_response = _fetch_git_markdown(
                git_input,
                env=args.env,
                network=args.network,
            )
            input_path = _materialize_git_markdown(raw_git_response, git_input, tmp_dir)
            default_stem = Path(git_input.path).stem
        else:
            default_stem = Path(input_path).stem

        file_stem = args.ui_path or _derive_ui_path(default_stem)
        account_mappings = None
        if args.account_mapping_json or args.account_mapping_file:
            account_mappings = _load_account_mappings_from_json(
                args.account_mapping_json,
                args.account_mapping_file,
            )
        precondition_tools = None
        if args.precondition_tools_json or args.precondition_tools_file:
            precondition_tools = _load_precondition_tools_from_json(
                args.precondition_tools_json,
                args.precondition_tools_file,
            )

        if git_input:
            source_url = (raw_git_response or {}).get("uri") or git_input.original
        else:
            source_url = args.source_url or _upload_source_to_tos(input_path)
        result = convert_markdown(
            input_path,
            source_url,
            out_dir,
            file_stem=file_stem,
            manifest_dir=tmp_dir,
            account_mappings=account_mappings,
            precondition_tools=precondition_tools,
        )

        print(f"[convert] cases: {result['cases_path']}")
        print(f"[convert] richtext: {result['richtext_path']}")
        print(f"[convert] manifest: {result['manifest_path']}")
        print(f"[convert] source_url: {source_url}")
        print(f"[convert] case_count: {result['case_count']}")
        if git_input and raw_git_response:
            print(f"[git] uri: {raw_git_response.get('uri', '')}")
            print(f"[git] resolved_commit_sha: {raw_git_response.get('resolved_commit_sha', '')}")
            print(f"[git] base_commit_sha: {raw_git_response.get('base_commit_sha', '')}")

        cases_path = result["cases_path"]
        richtext_path = result["richtext_path"]
    else:
        cases_path = os.path.abspath(os.path.expanduser(args.cases))
        if not os.path.isfile(cases_path):
            raise FileNotFoundError(f"cases 文件不存在: {cases_path}")
        richtext_path = _infer_richtext_path(cases_path, args.richtext)
        print(f"[direct] cases: {cases_path}")
        print(f"[direct] richtext: {richtext_path}")
        workspace_root = _workspace_root(os.path.dirname(cases_path))
        # 直传也过同一门禁：手写包常把 `<ttat>` 误挂到步骤 remark
        _assert_device_consistency(Path(cases_path).read_text(encoding="utf-8"))

    if args.skip_upload:
        return

    upload_module = _load_upload_module(workspace_root)
    creator = args.creator or os.environ.get("USER", "")
    project_id = args.project_id
    dir_id = args.dir_id
    case_set_id = args.case_set_id
    if args.bits_url:
        parsed = upload_module.parse_bits_case_url(args.bits_url)
        project_id = project_id or parsed["project_id"]
        case_set_id = case_set_id or parsed["case_set_id"]
        if dir_id is None and "dir_id" in parsed:
            dir_id = parsed["dir_id"]

    if project_id is None:
        raise ValueError("上传 bits 需要 --project_id 或 --bits-url")

    delete_titles = []
    for raw in args.delete_case:
        if "|||" not in raw:
            raise ValueError("--delete-case 格式应为 'primary_title|||case_title'")
        primary, case_title = raw.split("|||", 1)
        delete_titles.append((primary.strip(), case_title.strip()))

    if args.mode == "update":
        if case_set_id is None:
            raise ValueError("update 模式需要 --case-set-id 或带 caseDetail 的 --bits-url")
        upload_result = upload_module.sync_case_set(
            cases_path,
            richtext_path,
            project_id,
            case_set_id,
            env=args.env,
            creator=creator,
            network=args.network,
            only_case_titles=args.only_case_title or None,
            delete_titles=delete_titles or None,
            dry_run=args.dry_run,
        )
    else:
        if dir_id is None:
            raise ValueError("create 模式需要 --dir_id（或带 dirId 的 --bits-url）")
        if args.dry_run:
            print(
                f"[upload] dry-run create: project_id={project_id} dir_id={dir_id} "
                f"cases={cases_path}"
            )
            upload_result = {"dry_run": True, "project_id": project_id, "dir_id": dir_id}
        else:
            upload_result = upload_module.upload(
                cases_path,
                richtext_path,
                project_id,
                dir_id,
                env=args.env,
                creator=creator,
                network=args.network,
            )
    print(f"[upload] response: {json.dumps(upload_result, ensure_ascii=False, indent=2)[:2000]}")


if __name__ == "__main__":
    main()
