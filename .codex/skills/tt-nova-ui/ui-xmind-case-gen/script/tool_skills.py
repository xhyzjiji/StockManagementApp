"""
工具 Skills 注册表 —— 将前置条件中的文本映射为 ${richText_<uuid>: <工具名称>} 占位符。

每个 ToolSkill 定义一个工具：名称、richtext 元数据、语义描述。
apply_tool_skills() 对 CaseBlock 做后处理：前置条件仅允许 `_PRECONDITION_TOOLS`
（测试账号、ttmock_preset、Gecko 配置、环境名称、libra实验）中的工具占位符；
其余匹配到的工具会移入 steps 前部；非工具文本移入 steps。

Hard constraint：每一次工具调用都会分配独立的 mentionId（及 richtext uuid），
即使同工具、相同 inputData 也不得复用；注册表里的静态 mention_id 仅作历史标签，不参与绑定。

工具匹配策略：由 LLM 在用例生成时直接输出工具名称（name 或 name_en），
apply_tool_skills() 通过精确名称匹配将工具名转为 richtext 占位符。
不再使用 keyword 正则匹配，避免误召回。

扩展新工具：在 TOOL_SKILLS 列表中新增 ToolSkill 定义即可。
"""

from __future__ import annotations

import inspect
import json
import os
import re
import secrets
import string
import uuid as _uuid_mod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from script.test_model import CaseBlock, StepExpected

# Bits richtext mentionId 约定：小写字母+数字，长度 14（与平台历史工具实例格式对齐）。
_MENTION_ID_ALPHABET = string.ascii_lowercase + string.digits
_MENTION_ID_LEN = 14
_used_mention_ids: set = set()


def _new_mention_id() -> str:
    """Generate a per-invocation unique mentionId (never reuse within a render run)."""
    while True:
        mid = "".join(
            secrets.choice(_MENTION_ID_ALPHABET) for _ in range(_MENTION_ID_LEN)
        )
        if mid not in _used_mention_ids:
            _used_mention_ids.add(mid)
            return mid


class MissingRequiredToolParams(ValueError):
    def __init__(self, tool_name: str, missing_params: List[str], params_hint: str):
        self.tool_name = tool_name
        self.missing_params = missing_params
        self.params_hint = params_hint
        super().__init__(
            f"{tool_name} missing required params: {', '.join(missing_params)}"
        )


class AccountPoolMissingRequiredParams(ValueError):
    def __init__(self, pool_name: str):
        self.pool_name = pool_name
        self.tool_name = "测试账号"
        self.missing_params = ["pool_id"]
        self.params_hint = (
            f"账号池 {pool_name} 缺少 pool_id。请同时提供 pool_name 和 pool_id，"
            "或确保该账号池存在于业务线知识库中。"
        )
        super().__init__(self.params_hint)


class AccountPoolTagSuggestionNeeded(ValueError):
    def __init__(self, pool_name: str, suggested_tag: str):
        self.pool_name = pool_name
        self.suggested_tag = suggested_tag
        self.tool_name = "测试账号"
        self.params_hint = (
            f"账号池 {pool_name} 当前没有配置 tag。"
            f"根据设备角色建议补充 tag_name_list=[\"{suggested_tag}\"]。"
            "如需添加，请确认是否按该建议写入。"
        )
        super().__init__(self.params_hint)


@dataclass
class ToolSkill:
    name: str
    name_en: str
    # Legacy registry label only — NOT used as the Bits binding mentionId.
    # Every real tool call allocates a fresh mentionId via ``_new_invocation_ids()``.
    mention_id: str
    saitama_template_id: str = ""
    app_id: int = 1233
    mention_type: int = 31
    token: str = "32"
    input_data_builder: Optional[Callable] = None
    # Base uuid stem for this tool type; each call appends a unique suffix.
    uuid: str = field(default_factory=lambda: str(_uuid_mod.uuid4().int)[:12])
    semantic_description: str = ""
    output_fields: List[str] = field(default_factory=list)
    output_namespace: str = ""
    post_ui_state: str = ""
    keywords: List[str] = field(default_factory=list)
    params_hint: str = ""
    requires: str = ""
    role_constraint: str = ""

    def build_input_data(
        self, context: str = "", validate_required: bool = True
    ) -> str:
        if self.input_data_builder:
            sig = inspect.signature(self.input_data_builder)
            params = list(sig.parameters.keys())
            # Pass validate_required if the builder accepts it
            if "validate_required" in params:
                input_data = self.input_data_builder(
                    context, validate_required=validate_required
                )
            elif len(params) >= 1:
                input_data = self.input_data_builder(context)
            else:
                input_data = self.input_data_builder()

            # Skip params_hint validation if builder handles it internally
            builder_validates_internally = getattr(
                self.input_data_builder, "_validates_internally", False
            )
            if (
                validate_required
                and self.params_hint
                and not builder_validates_internally
            ):
                _validate_required_params_from_hint(
                    tool_name=self.name_en or self.name,
                    params_hint=self.params_hint,
                    input_data=input_data,
                )
            return input_data
        if self.params_hint:
            return _build_input_data_from_params_hint(self.params_hint)
        return "[]"

    def richtext_placeholder(self, variant_uuid: str = "") -> str:
        uid = variant_uuid or self.uuid
        return f"${{richText_{uid}:{self.name}}}"

    @property
    def resp_namespace(self) -> str:
        return self.output_namespace or f"{self.name_en}_resp"

    def cross_device_ref(self, device_name: str, field: str) -> str:
        """Generate a cross-device variable reference string."""
        return f"${{{device_name}.{self.resp_namespace}[{field}]}}"

    def _new_invocation_ids(self) -> tuple:
        """Allocate a unique (call_uuid, mention_id) for this tool invocation.

        Hard constraint: every tool call must get its own mentionId. Do not reuse the
        registry's static ``mention_id`` or share ids across calls (even with identical
        inputData). ``call_uuid`` is also unique so richtext registry entries never collide.
        """
        call_uuid = f"{self.uuid}_{secrets.token_hex(4)}"
        return call_uuid, _new_mention_id()

    # Back-compat alias for callers that still pass input_data (ignored).
    def _derive_variant_ids(self, input_data: str = "") -> tuple:
        return self._new_invocation_ids()

    def richtext_struct(
        self,
        context: str = "",
        variant_uuid: str = "",
        variant_mention_id: str = "",
        validate_required: bool = True,
    ) -> Dict[str, Any]:
        # Prefer explicit per-call ids; never fall back to the static registry mention_id
        # unless the caller forgot to allocate (legacy path).
        uid = variant_uuid or f"{self.uuid}_{secrets.token_hex(4)}"
        mid = variant_mention_id or _new_mention_id()
        return {
            "type": 2,
            "text": self.name,
            "id": mid,
            "mentionType": self.mention_type,
            "token": self.token,
            "uuid": uid,
            "pluginData": {
                "autoxToolSaveBindItem": {
                    "mentionId": mid,
                    "biz": 1,
                    "saitamaTemplateId": self.saitama_template_id,
                    "inputData": self.build_input_data(
                        context, validate_required=validate_required
                    ),
                    "appId": self.app_id,
                }
            },
        }


# ---- inputData 构建器 ----


def _env_name_input_data(context: str = "", validate_required: bool = True) -> str:
    """环境名称 builder：env 由外部参数输入（env=xxx），构建 {"env":"xxx"}。"""
    env = _parse_inline_context_params(context).get("env", [""])[0].strip()
    if validate_required and not env:
        raise MissingRequiredToolParams(
            tool_name="环境名称",
            missing_params=["env"],
            params_hint="env=Required(环境名称，如ppe_my_test)",
        )
    value_item = json.dumps(
        {"env": env}, ensure_ascii=False, separators=(",", ":")
    )
    return json.dumps(
        [{"key": "envName", "value": [value_item]}],
        ensure_ascii=False,
        separators=(",", ":"),
    )


_env_name_input_data._validates_internally = True


_ACCOUNT_REGION_RE = re.compile(
    r'(?:region|地区|区域)[=:：\s]*["\']?(\w+)',
    re.IGNORECASE,
)
_ACCOUNT_POOL_RE = re.compile(
    r'(?:pool_name|账号池|pool)[=:：\s]*["\']?([\w.\-]+)',
    re.IGNORECASE,
)
_ACCOUNT_POOL_ID_RE = re.compile(
    r'(?:pool_id)[=:：\s]*["\']?(\d+)',
    re.IGNORECASE,
)
_ACCOUNT_TAG_RE = re.compile(
    r'(?:tag_name_list|tag_name|tag)[=:：\s]*["\']?([\w.\-]+)',
    re.IGNORECASE,
)
_PIPE_ACCOUNT_TRIGGER_RE = re.compile(
    r"(?:use_pipe_account|pipe_account|ttAccount|ttAcount|造数账号|造数\s*\+\s*测试账号)",
    re.IGNORECASE,
)
_PIPE_ACCOUNT_COUNTRY_RE = re.compile(
    r'(?:country|国家)[=:：\s]*["\']?([A-Za-z]{2})',
    re.IGNORECASE,
)
_PIPE_ACCOUNT_LIVE_PERMISSION_RE = re.compile(
    r'(?:livePermission|live_permission|直播权限)[=:：\s]*["\']?(true|false|1|0|yes|no|有|无|是|否)',
    re.IGNORECASE,
)
_PIPE_ACCOUNT_BIRTHDAY_RE = re.compile(
    r'(?:birthday|birth_date|生日)[=:：\s]*["\']?(\d{4}-\d{2}-\d{2})',
    re.IGNORECASE,
)

_DEFAULT_ACCOUNT_PARAMS = {
    "is_used_pipe_pool": "ttAccountPool",
    "ttat_account_pool": {
        "region": "sg",
        "pool_id": "7156428109783241730",
        "pool_name": "GameLiveOpen",
        "occupy_second": "1200",
        "tag_name_list": ["game_anchor_auto_case"],
    },
}


def _normalize_tag_name_list(tag_name: str) -> List[str]:
    cleaned = (tag_name or "").strip()
    return [cleaned] if cleaned else []


def _normalize_bool_param(value: str) -> Optional[bool]:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "yes", "y", "有", "是", "开启", "开", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "无", "否", "关闭", "关", "off"}:
        return False
    return None


def _build_pipe_account_params(
    context: str, validate_required: bool = True
) -> Optional[dict]:
    if not context or not _PIPE_ACCOUNT_TRIGGER_RE.search(context):
        return None

    country_match = _PIPE_ACCOUNT_COUNTRY_RE.search(context)
    live_permission_match = _PIPE_ACCOUNT_LIVE_PERMISSION_RE.search(context)
    missing: List[str] = []
    if not country_match:
        missing.append("country")
    if not live_permission_match:
        missing.append("livePermission")
    if missing and validate_required:
        raise MissingRequiredToolParams(
            "测试账号",
            missing,
            "Input必填。country=Required(如 sg/us/jp)；livePermission=Required(true/false)；birthday=Optional(YYYY-MM-DD)。",
        )
    if missing:
        return None

    live_permission = _normalize_bool_param(live_permission_match.group(1))
    if live_permission is None:
        if validate_required:
            raise MissingRequiredToolParams(
                "测试账号",
                ["livePermission"],
                "Input必填。livePermission=Required(true/false)。",
            )
        return None

    tt_account = {
        "livePermission": live_permission,
        "country": country_match.group(1).lower(),
    }
    birthday_match = _PIPE_ACCOUNT_BIRTHDAY_RE.search(context)
    if birthday_match:
        tt_account["birthday"] = birthday_match.group(1)

    return {
        "is_used_pipe_pool": "ttAcount",
        "ttAccount": tt_account,
    }


def _suggest_account_pool_tag(device_name: str) -> str:
    device = (device_name or "").strip()
    if device.startswith("TT-主播设备-"):
        return "HOST"
    if device.startswith("TT-非主播设备-"):
        return "VIEWER"
    return ""


@dataclass
class AccountPool:
    pool_name: str
    pool_id: str
    region: str
    tag_name: str
    description: str


@dataclass
class FixedAccount:
    phone_number: str
    password: str
    description: str
    role: str = ""  # "host" or "viewer", parsed from accounts.txt


_ACCOUNT_POOLS: List[AccountPool] = []
_FIXED_ACCOUNTS: List[FixedAccount] = []


def _load_accounts_config(text: str = None) -> None:
    """
    Parse accounts configuration from text content or local file.

    If *text* is provided, parse it directly (used by reload_accounts for remote content).
    Otherwise fall back to reading the local data/accounts.txt file.
    """
    if text is None:
        cfg_path = os.path.join(os.path.dirname(__file__), "data", "accounts.txt")
        if not os.path.isfile(cfg_path):
            return
        with open(cfg_path, "r", encoding="utf-8") as f:
            text = f.read()

    _ACCOUNT_POOLS.clear()
    _FIXED_ACCOUNTS.clear()
    lines = text.splitlines()

    section = ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            if line.startswith("# ==="):
                if "账号池" in line or "Account Pool" in line:
                    section = "pools"
                elif "指定账号" in line or "Fixed Account" in line:
                    section = "fixed"
            continue
        parts = [p.strip() for p in line.split("|")]
        if section == "pools" and len(parts) >= 4:
            _ACCOUNT_POOLS.append(
                AccountPool(
                    pool_name=parts[0],
                    pool_id=parts[1],
                    region=parts[2],
                    tag_name=parts[3],
                    description=parts[4] if len(parts) > 4 else "",
                )
            )
        elif section == "fixed" and len(parts) >= 2:
            desc = parts[2] if len(parts) > 2 else ""
            role = ""
            if len(parts) > 3:
                role_part = parts[3].strip()
                if role_part.startswith("role="):
                    role = role_part[5:].strip()
            if not role:
                dl = desc.lower()
                if "主播" in dl or "host" in dl:
                    role = "host"
                elif "观众" in dl or "viewer" in dl:
                    role = "viewer"
            _FIXED_ACCOUNTS.append(
                FixedAccount(
                    phone_number=parts[0],
                    password=parts[1],
                    description=desc,
                    role=role,
                )
            )


_load_accounts_config()


def reload_accounts(text: str) -> None:
    """
    Reload account pools and fixed accounts from new text content.

    Called by the knowledge_loader pipeline when remote Lark doc content
    is fetched for a specific business line.
    """
    _load_accounts_config(text)


def _get_pool_by_name(name: str) -> Optional[AccountPool]:
    for p in _ACCOUNT_POOLS:
        if p.pool_name.lower() == name.lower():
            return p
    return None


def _build_account_params(pool: Optional[AccountPool] = None) -> dict:
    if pool is None:
        pool = (
            _ACCOUNT_POOLS[0]
            if _ACCOUNT_POOLS
            else AccountPool(
                pool_name="GameLiveOpen",
                pool_id="7156428109783241730",
                region="sg",
                tag_name="game_UI-Most",
                description="fallback",
            )
        )
    return {
        "is_used_pipe_pool": "ttAccountPool",
        "ttat_account_pool": {
            "region": pool.region,
            "pool_id": pool.pool_id,
            "pool_name": pool.pool_name,
            "occupy_second": "1200",
            "tag_name_list": _normalize_tag_name_list(pool.tag_name),
        },
    }


_ACCOUNT_PHONE_RE = re.compile(
    r'(?:phone_number|phone|手机号)[=:：\s]*["\']?(\+?\d[\d\s]*\d)',
    re.IGNORECASE,
)
_ACCOUNT_CAPTCHA_RE = re.compile(
    r'(?:captcha|password|密码|验证码)[=:：\s]*["\']?([^\s"\',；;]+)',
    re.IGNORECASE,
)
_ACCOUNT_UID_RE = re.compile(
    r'(?:UID|uid)[=:：\s]*["\']?(\d{15,25})',
    re.IGNORECASE,
)


_ACCOUNT_USERNAME_RE = re.compile(
    r'(?:username|用户名)[=:：\s]*["\']?(\+?[A-Za-z0-9][A-Za-z0-9_.@\-]+)',
    re.IGNORECASE,
)


def _looks_like_phone_number(value: str) -> bool:
    """用户名是否为纯手机号（可带 + 前缀、7 位及以上纯数字）。

    手机号登录用验证码(captcha)，普通用户名登录用密码(password)。
    """
    cleaned = (value or "").strip().lstrip("+")
    return bool(cleaned) and cleaned.isdigit() and len(cleaned) >= 7


def _require_country_code(phone: str, validate_required: bool) -> str:
    """手机号登录必须显式带国家区号：平台缺区号时按 +86 处理，非 86 账号会登录失败。"""
    normalized = (phone or "").strip().replace(" ", "")
    if normalized.startswith("+") or not validate_required:
        return normalized
    raise MissingRequiredToolParams(
        "测试账号",
        ["country_code"],
        f"手机号登录必须带国家区号（写成 +<区号><号码>，如 +81{normalized}）；"
        "平台默认按 +86 解析，区号缺失会登录失败。",
    )


def _test_account_input_data(context: str = "", validate_required: bool = True) -> str:
    if context:
        pipe_account_params = _build_pipe_account_params(context, validate_required)
        if pipe_account_params is not None:
            value_item = json.dumps(
                pipe_account_params, ensure_ascii=False, separators=(",", ":")
            )
            return json.dumps(
                [{"key": "account", "value": [value_item]}],
                ensure_ascii=False,
                separators=(",", ":"),
            )

        username_match = _ACCOUNT_USERNAME_RE.search(context)
        if username_match:
            username = username_match.group(1)
            credential = ""
            credential_match = _ACCOUNT_CAPTCHA_RE.search(context)
            if credential_match:
                credential = credential_match.group(1)
            # 用户名为纯手机号 → 走验证码(captcha)登录；否则（普通用户名）→ 走密码(password)登录
            if _looks_like_phone_number(username):
                account_obj = {
                    "username": _require_country_code(username, validate_required),
                    "captcha": credential,
                }
            else:
                account_obj = {"username": username, "password": credential}
            params = {
                "is_used_pipe_pool": "account",
                "account": account_obj,
            }
            value_item = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            return json.dumps(
                [{"key": "account", "value": [value_item]}],
                ensure_ascii=False,
                separators=(",", ":"),
            )

        phone_match = _ACCOUNT_PHONE_RE.search(context)
        if phone_match:
            phone = _require_country_code(phone_match.group(1), validate_required)
            captcha = ""
            captcha_match = _ACCOUNT_CAPTCHA_RE.search(context)
            if captcha_match:
                captcha = captcha_match.group(1)
            else:
                for fa in _FIXED_ACCOUNTS:
                    if fa.phone_number.replace(" ", "").lstrip("+") in phone:
                        captcha = fa.password
                        break
            params = {
                "is_used_pipe_pool": "account",
                "account": {"username": phone, "captcha": captcha},
            }
            value_item = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            return json.dumps(
                [{"key": "account", "value": [value_item]}],
                ensure_ascii=False,
                separators=(",", ":"),
            )

        uid_match = _ACCOUNT_UID_RE.search(context)
        if uid_match:
            uid_val = uid_match.group(1)
            params = _build_account_params()
            params["ttat_account_pool"]["uid"] = uid_val
            params["ttat_account_pool"]["uid_str"] = uid_val
            params["ttat_account_pool"]["pool_name"] = ""
            params["ttat_account_pool"]["pool_id"] = ""
            params["ttat_account_pool"]["tag_name_list"] = []
            value_item = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            return json.dumps(
                [{"key": "account", "value": [value_item]}],
                ensure_ascii=False,
                separators=(",", ":"),
            )

        pool: Optional[AccountPool] = None
        explicit_pool_name: Optional[str] = None
        pool_match = _ACCOUNT_POOL_RE.search(context)
        if pool_match:
            explicit_pool_name = pool_match.group(1)
            pool = _get_pool_by_name(explicit_pool_name)
        region_override = None
        region_match = _ACCOUNT_REGION_RE.search(context)
        if region_match:
            region_override = region_match.group(1).lower()

        if pool is None and explicit_pool_name:
            pool = AccountPool(
                pool_name=explicit_pool_name,
                pool_id="",
                region=region_override or "sg",
                tag_name="",
                description=f"from context: {explicit_pool_name}",
            )

        params = _build_account_params(pool)

        if region_override:
            params["ttat_account_pool"]["region"] = region_override
        pool_id_match = _ACCOUNT_POOL_ID_RE.search(context)
        if pool_id_match:
            params["ttat_account_pool"]["pool_id"] = pool_id_match.group(1)
        elif explicit_pool_name and not params["ttat_account_pool"]["pool_id"] and validate_required:
            raise AccountPoolMissingRequiredParams(explicit_pool_name)

        tag_match = _ACCOUNT_TAG_RE.search(context)
        if tag_match:
            params["ttat_account_pool"]["tag_name_list"] = _normalize_tag_name_list(
                tag_match.group(1)
            )
        elif validate_required and pool is not None:
            device_name = _parse_inline_context_params(context).get("__device__", [""])[0]
            suggested_tag = _suggest_account_pool_tag(device_name)
            if suggested_tag and not _normalize_tag_name_list(pool.tag_name):
                raise AccountPoolTagSuggestionNeeded(pool.pool_name, suggested_tag)
    else:
        params = _build_account_params()

    value_item = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(
        [{"key": "account", "value": [value_item]}],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def accounts_prompt_context() -> str:
    """Generate account pool + fixed account knowledge for LLM prompts."""
    lines = []

    # --- Account Pools (scenario-specific, NO default) ---
    if _ACCOUNT_POOLS:
        lines.append(
            "**可用账号池（Account Pools）** — 在 `测试账号` 工具中通过 `pool_name=XXX` 指定："
        )
        for p in _ACCOUNT_POOLS:
            lines.append(
                f"- **{p.pool_name}**（region={p.region}）：仅适用于「{p.description}」场景"
            )
        lines.append(
            "- **⛔ 没有默认账号池**：禁止在未匹配场景时随意使用任何池子。必须根据 seed 的业务场景选择匹配的池子或指定账号"
        )

    # --- Fixed Accounts (with role tags) ---
    if _FIXED_ACCOUNTS:
        lines.append("")
        lines.append(
            "**指定账号（Fixed Accounts）** — 使用 `测试账号` 工具，通过 `phone_number` + `captcha` 参数指定："
        )

        host_accounts = [a for a in _FIXED_ACCOUNTS if a.role == "host"]
        viewer_accounts = [a for a in _FIXED_ACCOUNTS if a.role == "viewer"]
        other_accounts = [
            a for a in _FIXED_ACCOUNTS if a.role not in ("host", "viewer")
        ]

        if host_accounts:
            lines.append("  主播账号（role=host，用于 TT-主播设备-N）：")
            for a in host_accounts:
                lines.append(
                    f"  - `{a.phone_number}` / `{a.password}` — {a.description}"
                )
        if viewer_accounts:
            lines.append("  观众账号（role=viewer，用于 TT-非主播设备-N）：")
            for a in viewer_accounts:
                lines.append(
                    f"  - `{a.phone_number}` / `{a.password}` — {a.description}"
                )
        if other_accounts:
            lines.append("  其他账号：")
            for a in other_accounts:
                lines.append(
                    f"  - `{a.phone_number}` / `{a.password}` — {a.description}"
                )

        lines.append(
            "- 使用方式：`测试账号 phone_number=XXX captcha=XXX`（系统自动切换为指定账号登录模式）"
        )

    # --- Account Selection Rules ---
    lines.append("")
    lines.append("**⚠️ 账号选择强制规则**：")
    lines.append(
        "1. **场景匹配优先**：根据 seed 的业务场景（如「送礼」「竞猜」「游戏直播」）匹配 Fixed Accounts 或 Account Pool 的适用描述。"
        "例如送礼场景必须使用「送礼场景」的指定账号，游戏直播场景使用 GameLiveOpen 池"
    )
    lines.append(
        "2. **多设备必须用不同账号**：主播设备和非主播设备**严禁使用同一账号**。"
        "主播设备用 role=host 的账号，观众设备用 role=viewer 的账号"
    )
    lines.append(
        "3. **无匹配时不猜测**：如果没有匹配的池子或指定账号，使用 `hint: 需要XX场景账号，请人工配置` 而非随意选池"
    )

    return "\n".join(lines)


def _extract_balanced_json_prefix(text: str) -> str:
    """Return the leading balanced ``{...}`` or ``[...]`` substring, or ``\"\"``."""
    if not text or text[0] not in "{[":
        return ""
    open_ch = text[0]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[: i + 1]
    return ""


_TTMOCK_PARAM_KEYS = (
    "ab_settings_live",
    "ab_settings",
    "language",
    "region",
    "__device__",
)
_TTMOCK_NEXT_PARAM_RE = re.compile(
    r"(?:^|\s)(?:"
    + "|".join(re.escape(k) for k in _TTMOCK_PARAM_KEYS)
    + r")\s*[=:：]",
    re.IGNORECASE,
)

_AB_SETTINGS_STANDARD_HINT = (
    "必须是 JSON 对象字符串，例如 {\"72192329\":\"1\",\"72218451\":\"1\"}；"
    "禁止数组、禁止非 JSON 写法。"
)


def is_json_object_string(text: str) -> bool:
    """Return True iff *text* is a JSON string whose top-level value is a JSON object.

    Arrays, primitives, empty string, and non-JSON text all return False.
    Skill agents should call this (or ``check-json-object`` CLI) to self-check
    ``ab_settings`` / ``ab_settings_live`` and regenerate when False.
    """
    ok, _obj, _reason = parse_json_object_string(text)
    return ok


def parse_json_object_string(
    text: str,
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Parse *text* as a JSON object string.

    Returns ``(ok, obj_or_none, reason)``.
    ``ok`` is True only when the top-level JSON value is a ``dict`` (object).
    """
    if text is None:
        return False, None, "empty"
    raw = str(text).strip()
    if not raw:
        return False, None, "empty"
    # Allow one layer of wrapping quotes around the whole JSON blob.
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        inner = raw[1:-1].strip()
        if inner.startswith("{") or inner.startswith("["):
            raw = inner
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return False, None, f"not_json:{exc}"
    if isinstance(parsed, dict):
        return True, parsed, "ok"
    if isinstance(parsed, list):
        return False, None, "json_array_not_object"
    return False, None, f"json_{type(parsed).__name__}_not_object"


class InvalidJsonObjectParam(ValueError):
    """Tool param must be a JSON object string but the provided value is not."""

    def __init__(self, tool_name: str, param_name: str, raw: str, reason: str):
        self.tool_name = tool_name
        self.param_name = param_name
        self.raw = raw
        self.reason = reason
        self.params_hint = _AB_SETTINGS_STANDARD_HINT
        preview = (raw or "")[:120]
        super().__init__(
            f"{tool_name}.{param_name} must be a JSON object string "
            f"(reason={reason}, raw={preview!r})"
        )


def _extract_ttmock_named_raw(context: str, key: str) -> str:
    """Extract raw value for a ttmock param, supporting JSON object/array blobs."""
    if not context:
        return ""
    m = re.search(
        rf"(?:^|\s){re.escape(key)}\s*[=:：]\s*",
        context,
        re.IGNORECASE,
    )
    if not m:
        return (_parse_inline_context_params(context).get(key) or [""])[0].strip()

    rest = context[m.end() :].lstrip()
    if not rest:
        return ""
    if rest[0] in "{[":
        blob = _extract_balanced_json_prefix(rest)
        if blob:
            return blob

    next_m = None
    for km in _TTMOCK_NEXT_PARAM_RE.finditer(rest):
        # Next param starts immediately -> current key has an empty value.
        if km.start() == 0:
            return ""
        next_m = km
        break
    end = next_m.start() if next_m else len(rest)
    return rest[:end].strip()


def _extract_ttmock_json_object_param(
    context: str,
    key: str,
    *,
    tool_name: str = "ttmock_preset",
    validate_required: bool = True,
) -> list:
    """Extract ``ab_settings`` / ``ab_settings_live`` as ``[compact_json_object_str]``.

    Empty / absent → ``[]``.
    Present but not a JSON object → **always** raise ``InvalidJsonObjectParam``
    (format check is independent of ``validate_required``; never silently drop/rewrite).
    """
    del validate_required  # format is always enforced when the key is present
    raw = _extract_ttmock_named_raw(context, key)
    if not raw:
        return []
    ok, obj, reason = parse_json_object_string(raw)
    if not ok or obj is None:
        raise InvalidJsonObjectParam(tool_name, key, raw, reason)
    return [json.dumps(obj, ensure_ascii=False, separators=(",", ":"))]


def _ttmock_preset_input_data(context: str = "", validate_required: bool = True) -> str:
    region = "US"
    language = "zh"
    ab_settings: list = []
    ab_settings_live: list = []

    if context:
        region_m = re.search(
            r'(?:region|区域)[=:：\s]*["\']?([A-Za-z]{2})', context, re.IGNORECASE
        )
        if region_m:
            region = region_m.group(1).upper()
        lang_m = re.search(
            r'(?:language|语言)[=:：\s]*["\']?([A-Za-z]{2,5})', context, re.IGNORECASE
        )
        if lang_m:
            language = lang_m.group(1).lower()
        ab_settings = _extract_ttmock_json_object_param(
            context,
            "ab_settings",
            validate_required=validate_required,
        )
        ab_settings_live = _extract_ttmock_json_object_param(
            context,
            "ab_settings_live",
            validate_required=validate_required,
        )

    return json.dumps(
        [
            {"key": "language", "value": [language]},
            {"key": "region", "value": [region]},
            {"key": "ab_settings", "value": ab_settings},
            {"key": "ab_settings_live", "value": ab_settings_live},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


_ttmock_preset_input_data._validates_internally = True


_ENTER_ROOM_ROLE_RE = re.compile(
    r'(?:role|设备)[=:：\s]*["\']?([^,\s]+)',
    re.IGNORECASE,
)
_ENTER_ROOM_UID_RE = re.compile(
    r'(?:uid)[=:：\s]*["\']?(\d+)',
    re.IGNORECASE,
)
_ENTER_ROOM_ID_RE = re.compile(
    r'(?:room_id)[=:：\s]*["\']?(\d+)',
    re.IGNORECASE,
)


class EnterRoomMissingRequiredParams(ValueError):
    """enter_room 工具缺失必填参数：uid/role/room_id 至少需要一项"""

    def __init__(self):
        super().__init__("enter_room 缺少必填参数：uid/role/room_id 至少需要一项")


def _enter_room_input_data(context: str = "", validate_required: bool = True) -> str:
    role_value: list = []
    uid_value: list = []
    room_id_value: list = []

    if context:
        role_m = _ENTER_ROOM_ROLE_RE.search(context)
        if role_m:
            role_value = [role_m.group(1)]
        uid_m = _ENTER_ROOM_UID_RE.search(context)
        if uid_m:
            uid_value = [uid_m.group(1)]
        room_id_m = _ENTER_ROOM_ID_RE.search(context)
        if room_id_m:
            room_id_value = [room_id_m.group(1)]

    # 验证：uid/role/room_id 至少需要一个（仅在 validate_required=True 时）
    if validate_required and not uid_value and not role_value and not room_id_value:
        raise EnterRoomMissingRequiredParams()

    return json.dumps(
        [
            {"key": "room_id", "value": room_id_value},
            {"key": "uid", "value": uid_value},
            {"key": "role", "value": role_value},
            {"key": "retry", "value": []},
            {"key": "required", "value": ["True"]},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _parse_inline_context_params(context: str) -> Dict[str, List[str]]:
    if not context:
        return {}

    matches = list(re.finditer(r"([A-Za-z0-9_./-]+)=", context))
    parsed: Dict[str, List[str]] = {}

    for index, match in enumerate(matches):
        key = match.group(1)
        value_start = match.end()
        value_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(context)
        )
        value = context[value_start:value_end].strip()
        if value:
            parsed[key] = [value]

    return parsed


def _make_kv_builder(params: dict) -> Callable:
    """工厂函数：生成声明了指定 key 和默认值的 input_data_builder。
    params: {"key_name": [default_values], ...}"""

    def _builder(context: str = "") -> str:
        overrides = _parse_inline_context_params(context)
        payload = [
            {"key": key, "value": list(overrides.get(key, value))}
            for key, value in params.items()
        ]
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    _builder._is_make_kv_builder = True
    _builder._declared_params = params
    return _builder


def _ai_get_nickname_input_data(context: str = "") -> str:
    """ai_get_nickname 专用 builder：uid 根据 __device__ 填充 <设备名.SYSTEM_GET_UID>。"""
    overrides = _parse_inline_context_params(context)
    device = overrides.get("__device__", ["TT-主播设备-1"])[0]
    payload = [
        {"key": "prompt", "value": ["查询昵称"]},
        {"key": "uid", "value": [f"<{device}.SYSTEM_GET_UID>"]},
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


_ai_get_nickname_input_data._is_make_kv_builder = True
_ai_get_nickname_input_data._declared_params = {"prompt": ["查询昵称"], "uid": []}


_DEFAULT_ALLOWLIST_PROMPT = "白名单添加Item"
_DEFAULT_ALLOWLIST_OPERATOR = "liuminyi.naomi"
_DEFAULT_ALLOWLIST_REASON = "aidatagen add allowlist item"
_DEFAULT_ALLOWLIST_CALLER = "explorer.api.executor"

_ALLOWLIST_PARAMS_HINT = (
    "Input必填。list_id=Required(白名单ID)；"
    "operator=Optional(默认liuminyi.naomi，须有写权限的邮箱前缀)；"
    "reason=Optional(默认aidatagen add allowlist item，<100字)；"
    "item_id=Conditional(与item_ids至少填一个)；"
    "item_ids=Conditional(批量，JSON数组或逗号分隔)；"
    "caller=Optional(默认explorer.api.executor)；"
    "valid_begin_time=Optional(Unix秒，空则当前时间)；"
    "valid_end_time=Optional(Unix秒，空则当前+365天)；"
    "exec_region=Optional；prompt=Optional(默认白名单添加Item)。"
)


def _ai_allowlist_add_item_input_data(
    context: str = "", validate_required: bool = True
) -> str:
    """Build ai_allowlist_add_item inputData from flat params."""
    overrides = _parse_inline_context_params(context)

    def _one(key: str, default: str = "") -> str:
        vals = overrides.get(key)
        if vals and vals[0].strip():
            return vals[0].strip()
        return default

    list_id = _one("list_id")
    item_id = _one("item_id")
    item_ids = _one("item_ids")
    operator = _one("operator", _DEFAULT_ALLOWLIST_OPERATOR)
    reason = _one("reason", _DEFAULT_ALLOWLIST_REASON)
    caller = _one("caller", _DEFAULT_ALLOWLIST_CALLER)
    prompt = _one("prompt", _DEFAULT_ALLOWLIST_PROMPT)
    valid_begin_time = _one("valid_begin_time")
    valid_end_time = _one("valid_end_time")
    exec_region = _one("exec_region")

    if validate_required:
        missing: List[str] = []
        if not list_id:
            missing.append("list_id")
        if not item_id and not item_ids:
            missing.append("item_id/item_ids")
        if missing:
            raise MissingRequiredToolParams(
                "ai_allowlist_add_item", missing, _ALLOWLIST_PARAMS_HINT
            )

    def _val(raw: str) -> list:
        return [raw] if raw else []

    return json.dumps(
        [
            {"key": "prompt", "value": _val(prompt)},
            {"key": "list_id", "value": _val(list_id)},
            {"key": "operator", "value": _val(operator)},
            {"key": "reason", "value": _val(reason)},
            {"key": "item_id", "value": _val(item_id)},
            {"key": "item_ids", "value": _val(item_ids)},
            {"key": "caller", "value": _val(caller)},
            {"key": "valid_begin_time", "value": _val(valid_begin_time)},
            {"key": "valid_end_time", "value": _val(valid_end_time)},
            {"key": "exec_region", "value": _val(exec_region)},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


_ai_allowlist_add_item_input_data._validates_internally = True


# Libra 实验参数正则
_LIBRA_REGION_RE = re.compile(
    r"(?:region|区域)[=:：\s]*['\"]?([a-zA-Z]{2,3})", re.IGNORECASE
)
_LIBRA_ID_RE = re.compile(
    r"(?:libra_id|libraid|实验ID)[=:：\s]*['\"]?([a-zA-Z0-9_]+)", re.IGNORECASE
)
_LIBRA_GROUP_ID_RE = re.compile(
    r"(?:group_id|groupid|分组ID)[=:：\s]*['\"]?([a-zA-Z0-9_]+)", re.IGNORECASE
)
# 支持两种格式：libra_title="带空格的标题" 或 libra_title=simple_title
_LIBRA_TITLE_RE = re.compile(
    r"(?:libra_title|libratitle|实验名称|标题)[=:：\s]*(?:['\"]([^'\"]+)['\"]|([^\s]+))",
    re.IGNORECASE,
)


def _libra_experiment_input_data(
    context: str = "", validate_required: bool = True
) -> str:
    """构建 libra 实验的 input_data。

    格式：[{"key": "libraExperiment", "value": ["{\"region\":\"sg\",\"fids\":[\"71315741\"],\"libra\":[{\"libra_title\":\"...\",\"libra_id\":71315741,\"group_id\":74002288,\"region\":\"sg\"}]}"]}]
    """
    region = None
    libra_id = None
    group_id = None
    libra_title = None

    if context:
        region_match = _LIBRA_REGION_RE.search(context)
        if region_match:
            region = region_match.group(1).lower()

        libra_id_match = _LIBRA_ID_RE.search(context)
        if libra_id_match:
            libra_id = libra_id_match.group(1).strip()

        group_id_match = _LIBRA_GROUP_ID_RE.search(context)
        if group_id_match:
            group_id = group_id_match.group(1).strip()

        title_match = _LIBRA_TITLE_RE.search(context)
        if title_match:
            title = title_match.group(1).strip()
            # 去除引号
            if (title.startswith("'") and title.endswith("'")) or (
                title.startswith('"') and title.endswith('"')
            ):
                title = title[1:-1]
            libra_title = title

    if validate_required:
        missing = []
        if not region:
            missing.append("region")
        if not libra_id:
            missing.append("libra_id")
        if not group_id:
            missing.append("group_id")
        if missing:
            raise MissingRequiredToolParams(
                tool_name="libra experiment",
                missing_params=missing,
                params_hint="region=区域代码(如sg/us/jp)；libra_id=实验ID；group_id=分组ID；libra_title=实验标题(可选)",
            )

    # 构建 libra 数组
    libra_item = {
        "libra_title": libra_title or f"实验_{libra_id}",
        "libra_id": int(libra_id) if libra_id else 0,
        "group_id": int(group_id) if group_id else 0,
        "region": region or "",
    }

    value_obj = {
        "region": region or "",
        "fids": [libra_id] if libra_id else [],
        "libra": [libra_item],
    }
    value_str = json.dumps(value_obj, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(
        [{"key": "libraExperiment", "value": [value_str]}],
        ensure_ascii=False,
        separators=(",", ":"),
    )


# 标记此函数自己处理验证，不需要 params_hint 验证
_libra_experiment_input_data._validates_internally = True


_SIMPLE_PARAMS_HINT_RE = re.compile(
    r"([A-Za-z0-9_./]+)\s*=\s*(Required|Optional)(\([^)]*\))?",
    re.IGNORECASE,
)
_DEFAULT_VALUE_RE = re.compile(r"default\s+([^)；。]+)", re.IGNORECASE)


def _extract_params_hint_default(details: str) -> Optional[str]:
    match = _DEFAULT_VALUE_RE.search(details)
    if not match:
        return None
    return match.group(1).strip()


def _parse_params_hint_fields(params_hint: str) -> List[Tuple[str, List[str]]]:
    fields: List[Tuple[str, List[str]]] = []
    normalized = params_hint.replace("Input必填。", "")

    for raw_names, _requiredness, details in _SIMPLE_PARAMS_HINT_RE.findall(normalized):
        default_value = _extract_params_hint_default(details or "")
        value = [default_value] if default_value is not None else []
        for key in raw_names.split("/"):
            cleaned_key = key.strip()
            if cleaned_key:
                fields.append((cleaned_key, list(value)))

    return fields


def _build_input_data_from_params_hint(params_hint: str) -> str:
    return json.dumps(
        [
            {"key": key, "value": value}
            for key, value in _parse_params_hint_fields(params_hint)
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _required_param_names_from_hint(params_hint: str) -> List[str]:
    required: List[str] = []
    normalized = params_hint.replace("Input必填。", "")

    for raw_names, requiredness, _details in _SIMPLE_PARAMS_HINT_RE.findall(normalized):
        if requiredness.lower() != "required":
            continue
        for key in raw_names.split("/"):
            cleaned_key = key.strip()
            if cleaned_key:
                required.append(cleaned_key)

    return required


def _input_data_map(input_data: str) -> Dict[str, List[str]]:
    parsed = json.loads(input_data)
    return {
        item.get("key", ""): item.get("value", [])
        for item in parsed
        if isinstance(item, dict) and item.get("key")
    }


def _validate_required_params_from_hint(
    tool_name: str, params_hint: str, input_data: str
) -> None:
    if not params_hint:
        return

    required_params = _required_param_names_from_hint(params_hint)
    if not required_params:
        return

    values_by_key = _input_data_map(input_data)
    missing = [key for key in required_params if not values_by_key.get(key)]
    if missing:
        raise MissingRequiredToolParams(tool_name, missing, params_hint)


_TOOL_NAME_PREFIX_RE = re.compile(
    r"^(?:ui_assert|data_assertion)\s*",
    re.IGNORECASE,
)
_DEVICE_PLACEHOLDER_RE = re.compile(
    r"\$\{richText_[^}]+\}\s*",
)


def _extract_assertion_text(context: str) -> str:
    """Extract assertion text from context by stripping tool name and device placeholders."""
    text = _TOOL_NAME_PREFIX_RE.sub("", context.strip())
    text = _DEVICE_PLACEHOLDER_RE.sub("", text).strip()
    return text


def _ui_assert_input_data(context: str = "") -> str:
    assertion_text = _extract_assertion_text(context) if context else ""
    assertion_value = [assertion_text] if assertion_text else []
    return json.dumps(
        [
            {"key": "assertion", "value": assertion_value},
            {"key": "required", "value": ["True"]},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _data_assertion_input_data(context: str = "", validate_required: bool = True) -> str:
    """构建 data_assertion inputData。

    埋点（AppLog）约定写法（ui-md-event2case-gen 强制）：
      data_assertion data_filter_name=<event> assert_type=AppLog assertion=<参数断言正文>
    例：上报 `livesdk_ai_guide_entrance_show` 埋点；`anchor_id` 有值；…
      → data_filter_name=livesdk_ai_guide_entrance_show
         assert_type=AppLog
         assertion=`anchor_id` 有值；`enter_from` 有值；`room_id` 有值
    """
    overrides = _parse_inline_context_params(context)
    filter_name = (overrides.get("data_filter_name") or [""])[0].strip()
    assert_type = (overrides.get("assert_type") or [""])[0].strip()
    if not assert_type:
        # 有 event 名时默认 AppLog（埋点）；否则保持历史 Network 默认
        assert_type = "AppLog" if filter_name else "Network"
    if overrides.get("assertion"):
        assertion_text = overrides["assertion"][0].strip()
    else:
        assertion_text = _extract_assertion_text(context) if context else ""
    delay_vals = overrides.get("delay") or []

    if validate_required:
        missing = []
        if not filter_name:
            missing.append("data_filter_name")
        if not assert_type:
            missing.append("assert_type")
        if not assertion_text:
            missing.append("assertion")
        if missing:
            raise MissingRequiredToolParams(
                "data_assertion",
                missing,
                "data_assertion data_filter_name=<event> assert_type=AppLog assertion=<正文>",
            )

    return json.dumps(
        [
            {"key": "data_filter_name", "value": [filter_name] if filter_name else []},
            {"key": "assert_type", "value": [assert_type] if assert_type else []},
            {"key": "assertion", "value": [assertion_text] if assertion_text else []},
            {"key": "delay", "value": list(delay_vals)},
            {"key": "required", "value": ["True"]},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


_data_assertion_input_data._validates_internally = True


# ---- ByteIO 埋点校验工具 (et_checker) ----

_BYTEIO_CASE_LIST_RE = re.compile(
    r"byteio_case_list\s*[=:：]\s*(\[.*\])", re.IGNORECASE | re.DOTALL
)
_DEVICE_ANNOTATION_TAIL_RE = re.compile(r"\s*__device__=\S+\s*$")
# ByteIOCaseInfo 用例元素的规范字段顺序（与平台 et_checker inputData 对齐）
_BYTEIO_CASE_FIELDS = ("ID", "Name", "InvokeNum", "AppID", "Region")


class MissingByteIOCaseList(MissingRequiredToolParams):
    """埋点校验工具缺少 byteio_case_list 参数。"""

    def __init__(self):
        super().__init__(
            "et_checker_G20",
            ["byteio_case_list"],
            "Input必填。byteio_case_list=Required(埋点用例列表 JSON 数组，"
            "每个元素含 ID/Name/InvokeNum/AppID/Region)。"
            "该列表来自 getCaseDetail 响应的 ByteIOCaseInfo.CaseList[<节点id>]。",
        )


def normalize_byteio_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """把 ByteIOCaseInfo 里的用例对象规范成 et_checker 需要的字段顺序。"""
    normalized: Dict[str, Any] = {}
    for key in _BYTEIO_CASE_FIELDS:
        if key in case:
            normalized[key] = case[key]
    # 保留未知字段，避免丢信息
    for key, value in case.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def build_byteio_case_list_json(cases: List[Dict[str, Any]]) -> str:
    """把一组 ByteIO 用例序列化成 et_checker byteio_case_list 需要的内层 JSON 字符串。"""
    normalized = [normalize_byteio_case(c) for c in cases if isinstance(c, dict)]
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _et_checker_input_data(context: str = "", validate_required: bool = True) -> str:
    """构建 et_checker (ByteIO 埋点校验) 的 inputData。

    从 context 中解析 `byteio_case_list=[...]`（JSON 数组，元素为埋点用例对象），
    产出 [{"key":"byteio_case_list","value":["<压缩后的 JSON 数组字符串>"]}]。

    识别为埋点需求（存在该工具占位）但缺少/非法用例列表时抛错，由 skill 层反问用户。
    """
    parsed_cases: Optional[list] = None
    if context:
        ctx = _DEVICE_ANNOTATION_TAIL_RE.sub("", context)
        m = _BYTEIO_CASE_LIST_RE.search(ctx)
        if m:
            try:
                candidate = json.loads(m.group(1).strip())
                if isinstance(candidate, list) and candidate:
                    parsed_cases = candidate
            except (json.JSONDecodeError, ValueError):
                parsed_cases = None

    if parsed_cases is None:
        if validate_required:
            raise MissingByteIOCaseList()
        return json.dumps(
            [{"key": "byteio_case_list", "value": []}],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    case_list_json = build_byteio_case_list_json(parsed_cases)
    return json.dumps(
        [{"key": "byteio_case_list", "value": [case_list_json]}],
        ensure_ascii=False,
        separators=(",", ":"),
    )


# 该 builder 自行完成必填校验，跳过基于 params_hint 的通用校验
_et_checker_input_data._validates_internally = True


# ---- Gecko 配置（前置条件环境工具） ----

_DEFAULT_GECKO_APP_ID = 1
_DEFAULT_GECKO_APP_NAME = "TIKTOK"

# 前端「Gecko 环境」：线上=1 / 内测=2；部署 id/name 随环境固定。
_GECKO_DEPLOYMENT_PRESETS: Dict[int, Dict[str, Any]] = {
    1: {
        "geckoDeployment": 1,
        "geckoDeploymentType": 1,
        "geckoDeploymentId": 2,
        "geckoDeploymentName": "线上部署",
    },
    2: {
        "geckoDeployment": 2,
        "geckoDeploymentType": 2,
        "geckoDeploymentId": 7,
        "geckoDeploymentName": "内测部署",
    },
}

_GECKO_DEPLOYMENT_ALIASES = {
    "1": 1,
    "线上": 1,
    "online": 1,
    "2": 2,
    "内测": 2,
    "inhouse": 2,
    "in_house": 2,
}

_GECKO_CONFIGS_JSON_RE = re.compile(
    r"geckoConfigs\s*[=:：]\s*(\{.*\}|\[.*\])",
    re.IGNORECASE | re.DOTALL,
)


def _resolve_gecko_deployment(raw: str) -> Optional[int]:
    key = (raw or "").strip().lower()
    if not key:
        return None
    if key in _GECKO_DEPLOYMENT_ALIASES:
        return _GECKO_DEPLOYMENT_ALIASES[key]
    # Also accept Chinese keys as typed (not lowercased map hit for mixed)
    for alias, value in _GECKO_DEPLOYMENT_ALIASES.items():
        if alias.lower() == key or alias == (raw or "").strip():
            return value
    return None


def _parse_gecko_bool(raw: Optional[str], default: Optional[bool] = None) -> Optional[bool]:
    if raw is None or raw == "":
        return default
    parsed = _normalize_bool_param(raw)
    return default if parsed is None else parsed


def _gecko_config_input_data(context: str = "", validate_required: bool = True) -> str:
    """Build geckoConfigs inputData by assembling nested JSON from flat user params.

    Preferred flat form (LLM / seed 只写扁平字段，JSON 由本函数拼装)::
        Gecko 配置 geckoEnv=test_ppe geckoChannelId=288340379 geckoDeployment=线上
            geckoChannelName=madonna_campaign_ai_test_2 geckoPackageIdStr=1234 isRow=true

    Legacy escape hatch: geckoConfigs={...} full JSON blob is still accepted; if geckoEnv=
    is also provided, outer+inner geckoEnv are kept in sync.
    """
    overrides = _parse_inline_context_params(context)
    params_hint = (
        "Input必填。geckoEnv=Required(如test_ppe)；geckoChannelId=Required；"
        "geckoDeployment=Optional(默认1/线上，亦可填2/内测)；"
        "geckoAppId=Optional(默认1/TIKTOK)；geckoChannelName=Optional；"
        "geckoPackageIdStr=Optional；gecko_update_enable=Optional(默认false)；"
        "isRow=Optional。"
    )

    # Full JSON override (prefer balanced extract so trailing flat params aren't swallowed)
    raw_blob = ""
    if context:
        gm = re.search(r"(?:^|\s)geckoConfigs\s*[=:：]\s*", context, re.IGNORECASE)
        if gm:
            rest = context[gm.end() :].lstrip()
            if rest.startswith("{") or rest.startswith("["):
                raw_blob = _extract_balanced_json_prefix(rest)
    if not raw_blob and overrides.get("geckoConfigs"):
        raw_blob = overrides["geckoConfigs"][0].strip()

    if raw_blob:
        try:
            blob = json.loads(raw_blob)
        except (json.JSONDecodeError, ValueError):
            if validate_required:
                raise MissingRequiredToolParams(
                    "Gecko Config",
                    ["geckoConfigs"],
                    params_hint,
                )
            blob = {}
        if not isinstance(blob, dict):
            if validate_required:
                raise MissingRequiredToolParams(
                    "Gecko Config",
                    ["geckoConfigs"],
                    params_hint + " geckoConfigs必须是JSON对象。",
                )
            blob = {}
        env_override = (overrides.get("geckoEnv") or [""])[0].strip()
        if env_override:
            blob["geckoEnv"] = env_override
            for item in blob.get("geckoConfigs") or []:
                if isinstance(item, dict):
                    item["geckoEnv"] = env_override
        value_str = json.dumps(blob, ensure_ascii=False, separators=(",", ":"))
        return json.dumps(
            [{"key": "geckoConfigs", "value": [value_str]}],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    # Flat-param aliases from natural language / LLM variants
    def _flat(*names: str) -> str:
        for n in names:
            vals = overrides.get(n)
            if vals and vals[0].strip():
                return vals[0].strip()
        return ""

    gecko_env = _flat("geckoEnv", "gecko_env", "env")
    channel_id_raw = _flat(
        "geckoChannelId", "gecko_channel_id", "channelId", "channel_id", "ChannelId"
    )
    missing: List[str] = []
    if not gecko_env:
        missing.append("geckoEnv")
    if not channel_id_raw:
        missing.append("geckoChannelId")
    if missing and validate_required:
        raise MissingRequiredToolParams("Gecko Config", missing, params_hint)

    deployment_raw = _flat("geckoDeployment", "gecko_deployment", "deployment") or "1"
    deployment_key = _resolve_gecko_deployment(deployment_raw)
    if deployment_key is None:
        deployment_key = 1
    preset = dict(_GECKO_DEPLOYMENT_PRESETS[deployment_key])

    # Allow explicit overrides of deployment id/name/type
    if overrides.get("geckoDeploymentId"):
        try:
            preset["geckoDeploymentId"] = int(overrides["geckoDeploymentId"][0].strip())
        except ValueError:
            pass
    if overrides.get("geckoDeploymentName"):
        preset["geckoDeploymentName"] = overrides["geckoDeploymentName"][0].strip()
    if overrides.get("geckoDeploymentType"):
        try:
            preset["geckoDeploymentType"] = int(
                overrides["geckoDeploymentType"][0].strip()
            )
        except ValueError:
            pass

    app_id_raw = (
        _flat("geckoAppId", "gecko_app_id", "appId", "app_id")
        or str(_DEFAULT_GECKO_APP_ID)
    )
    try:
        gecko_app_id = int(app_id_raw) if app_id_raw else _DEFAULT_GECKO_APP_ID
    except ValueError:
        gecko_app_id = _DEFAULT_GECKO_APP_ID
    gecko_app_name = (
        _flat("geckoAppName", "gecko_app_name", "appName", "app_name")
        or _DEFAULT_GECKO_APP_NAME
    )

    # Allow "44255308" or messy "ChannelId=44255308" / extract leading digits
    channel_digits = re.search(r"\d+", channel_id_raw or "")
    try:
        gecko_channel_id = int(channel_digits.group(0)) if channel_digits else 0
    except ValueError:
        gecko_channel_id = 0

    inner: Dict[str, Any] = {
        "geckoDeploymentType": preset["geckoDeploymentType"],
        "geckoEnv": gecko_env,
        "geckoAppId": gecko_app_id,
        "geckoAppName": gecko_app_name,
        "geckoChannelId": gecko_channel_id,
        "geckoDeploymentId": preset["geckoDeploymentId"],
        "geckoDeploymentName": preset["geckoDeploymentName"],
    }
    channel_name = _flat(
        "geckoChannelName", "gecko_channel_name", "channelName", "channel_name"
    )
    if channel_name:
        inner["geckoChannelName"] = channel_name
    package_id = _flat(
        "geckoPackageIdStr", "packageId", "PackageId", "package_id", "Package ID"
    )
    if package_id:
        inner["geckoPackageIdStr"] = package_id

    update_enable = _parse_gecko_bool(
        _flat("gecko_update_enable", "geckoUpdateEnable", "update_enable") or None,
        default=False,
    )
    is_row = _parse_gecko_bool(_flat("isRow", "is_row", "row") or None, default=None)
    if is_row is not None:
        inner["isRow"] = is_row

    outer: Dict[str, Any] = {
        "gecko_update_enable": bool(update_enable),
        "geckoDeployment": preset["geckoDeployment"],
        "geckoConfigs": [inner],
        "geckoEnv": gecko_env,
    }
    if is_row is not None:
        outer["isRow"] = is_row

    value_str = json.dumps(outer, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(
        [{"key": "geckoConfigs", "value": [value_str]}],
        ensure_ascii=False,
        separators=(",", ":"),
    )


_gecko_config_input_data._validates_internally = True


# ---- 工具注册表（Top 30 高频工具） ----

TOOL_SKILLS: List[ToolSkill] = [
    # ═══════════════════════ 基础设施级（几乎每条用例必用） ═══════════════════════
    ToolSkill(
        name="测试账号",
        name_en="Test Account",
        saitama_template_id="0b7af52c-f6bc-4eb3-afb7-8584abb3d574",
        mention_id="e3wvg33qo2w6tm",
        app_id=1233,
        input_data_builder=_test_account_input_data,
        uuid="789012",
        semantic_description=(
            "自动从账号池获取测试账号并完成登录。"
            "覆盖能力：获取主播账号/观众账号/粉丝账号、完成登录认证、切换用户身份。"
            "支持按区域（region）、账号池（pool_name）筛选。"
            "支持造数创建/设置测试账号：当场景需要构造生日、年龄、国家或直播权限时，"
            "使用 use_pipe_account=true country=sg livePermission=false birthday=YYYY-MM-DD。"
            "不同业务使用不同账号池（见下方账号池列表），通过 pool_name 参数指定。"
            "账号池 tag_name 为空时必须输出空列表，不得输出空字符串。"
            "当此工具存在时，用例无需编写获取账号、登录等步骤，直接从已登录状态开始。"
            "若未指明账号池，需要指定手机号登录"
        ),
        post_ui_state="TikTok 首页（已登录状态）",
        params_hint="Input必填。region=Optional(默认va)；pool_name=Optional；pool_id=Conditional(pool_name存在时必填)；tag_name_list为空时传空数组[]，不要传[\"\"]；use_pipe_account=Optional(造数账号时填true)；country=Conditional(use_pipe_account存在时必填，如sg)；livePermission=Conditional(use_pipe_account存在时必填，true/false)；birthday=Optional(YYYY-MM-DD)。",
    ),
    ToolSkill(
        name="ttmock_preset",
        name_en="TT Mock Preset",
        saitama_template_id="0483288f-36fa-4396-983c-edd501693826",
        mention_id="nrai3nx4ydcbjw",
        app_id=1233,
        input_data_builder=_ttmock_preset_input_data,
        uuid="345678",
        semantic_description=(
            "预设 TikTok App 的区域（region）、语言（language）和 AB Test / Settings 配置。"
            "覆盖能力：切换 App 区域（如 US/JP/SG/ID/BR 等）、切换 App 语言（如 en/ja/zh 等）、"
            "写入 ab_settings（通用 AB/实验，对应长按 Inbox 进入的 debug tool）与 "
            "ab_settings_live（直播间/连麦相关 settings，对应进房→点主播头像→个人资料卡→高级调试 debug tool）。"
            "⚠️ ab_settings / ab_settings_live 若填写，必须直接输出标准 JSON **对象**字符串，"
            "例如 ab_settings={\"72192329\":\"1\",\"72218451\":\"1\"}。"
            "禁止 JSON 数组、禁止非 JSON 文本；填写后必须用 check-json-object 自检，"
            "render/转换也会硬拦，不会自动改写。"
            "未传则留空。适用于需要特定地区、语言或 AB/直播 settings 的测试场景。"
        ),
        params_hint=(
            "Input必填。region=Optional(默认US)；language=Optional(默认zh)；"
            "ab_settings=Optional(必须是JSON对象string，如{\"72192329\":\"1\"}，禁止数组/非JSON，有则必检)；"
            "ab_settings_live=Optional(必须是JSON对象string，有则必检)。"
            "当seed涉及特定地区时必须指定region。"
        ),
    ),
    ToolSkill(
        name="Gecko 配置",
        name_en="Gecko Config",
        saitama_template_id="311de6e6-6254-4596-93c0-bed43d53275e",
        mention_id="uo3wgloeskesos",
        # 环境工具：app_id=1180；token 对齐平台 mentionType=31。
        app_id=1180,
        mention_type=31,
        token="31",
        uuid="401061",
        input_data_builder=_gecko_config_input_data,
        semantic_description=(
            "配置客户端 Gecko 资源通道（Channel / Package / 部署环境），写入前置条件。"
            "⚠️ 路由规则：凡是与 GeckoX env（仅 local_test / boe / online 三选一）无关的 Gecko/GeckoX 设置，"
            "一律用本工具，不要用 GeckoX_settings。"
            "覆盖能力：Gecko 部署环境（线上/内测）、是否 Row、是否开启 Gecko 自动更新、"
            "绑定 Gecko 应用 + Channel（可选 Package ID）。"
            "入参只写扁平字段；geckoConfigs 的嵌套 JSON 由工具自动拼装（geckoEnv 写一次，内外层自动一致）。"
            "name 类字段与 Package ID 可选；ChannelId 等 id 必填；geckoAppId 缺省为 TIKTOK(1)。"
            "入参格式：Gecko 配置 geckoEnv=test_ppe geckoChannelId=288340379 "
            "geckoDeployment=线上 geckoChannelName=madonna_campaign_ai_test_2 "
            "geckoPackageIdStr=1234 isRow=true gecko_update_enable=false"
        ),
        params_hint=(
            "Input必填。geckoEnv=Required(如test_ppe)；geckoChannelId=Required；"
            "geckoDeployment=Optional(默认1/线上，亦可填2/内测)；"
            "geckoAppId=Optional(默认1/TIKTOK)；geckoChannelName=Optional；"
            "geckoPackageIdStr=Optional；gecko_update_enable=Optional(默认false)；"
            "isRow=Optional。"
        ),
    ),
    # ═══════════════════════ 场景构造级（直播/实验类高频） ═══════════════════════
    ToolSkill(
        name="libra实验",
        name_en="libra experiment",
        saitama_template_id="762ecac8-c463-48c0-8aa1-21a2bbabe4aa",
        mention_id="d4xr9km7y2w1ea",
        uuid="401003",
        app_id=1233,
        input_data_builder=_libra_experiment_input_data,
        semantic_description=(
            "配置 libra AB 实验，将指定用户加入到特定实验分组。"
            "覆盖能力：设置实验 ID（libra_id）、分组 ID（group_id）、配置实验区域（region）。"
            "适用于所有需要灰度发布、AB 实验、功能开关控制的测试场景，"
            "如新功能灰度验证、实验分组行为差异测试。"
            "入参格式：libra实验 region=sg libra_id=71315741 group_id=74002288 libra_title=实验名称(可选)"
        ),
        params_hint="Input必填。region=Required(区域代码如sg/us/jp)；libra_id=Required(实验ID)；group_id=Required(分组ID)；libra_title=Optional(实验标题)。",
    ),
    # ToolSkill(
    #     name="ai_room_start",
    #     name_en="ai_room_start",
    #     saitama_template_id="7affb85b-9919-4200-90bb-d1bf32271ff8",
    #     mention_id="z6tn1gi9u4s3aw", uuid="401024", app_id=1233,
    #     input_data_builder=_make_kv_builder({"app_id": [], "prompt": ["开始直播间"], "uid": []}),
    #     semantic_description=(
    #         "使用指定主播 UID 通过服务端接口发起开播（开始直播）。"
    #         "覆盖能力：创建直播间、使主播上线、启动推流。"
    #         "适用于需要主播已开播状态的所有测试场景，如观众进房、直播间互动、"
    #         "礼物打赏、连麦、PK、竞猜等功能的前置条件。"
    #         "该工具不经过客户端 UI，直接通过后端接口开播，效率更高。"
    #     ),
    # ),
    ToolSkill(
        name="enter_room",
        name_en="enter_room",
        saitama_template_id="ea8bf9e7-e2a6-4579-9267-04ff3ca99643",
        mention_id="b8vp3ik1w6u5cy",
        uuid="401026",
        app_id=1233,
        input_data_builder=_enter_room_input_data,
        semantic_description=(
            "通过服务端接口让指定用户进入指定直播间（进房）。"
            "通过 role 字段指定要进入哪个主播的直播间，role 填对应的主播设备名称（如 TT-主播设备-1）。"
            "执行层根据 role 自动定位直播间。"
            "⚠️ role 必须与实际的主播设备名称严格一致（如 TT-主播设备-1、TT-主播设备-2），写错会导致进房失败。"
            "适用于观众侧测试场景的前置条件，如需要观众在直播间内才能验证的功能："
            "弹幕聊天、礼物面板、粉丝团互动、观众排行榜等。"
            "该工具不经过客户端 UI 流程，直接通过接口进房。"
        ),
        requires="需在主播设备已完成 GUI 开播步骤之后执行（直播间必须已就绪）",
        role_constraint="仅非主播设备使用（主播是开播方，不存在进房语义）",
        params_hint="Input必填。role=Required(主播设备名称，如TT-主播设备-1)；uid/room_id=Optional(二者至少一项)；retry=Optional；appid=Optional(default 1233)。",
    ),
    # ToolSkill(
    #     name="ai_end_live",
    #     name_en="ai_end_live",
    #     saitama_template_id="a30985f0-2d49-4eca-9cde-0b2eba617038",
    #     mention_id="y5sm0fh8t3r2zv",
    #     uuid="401023",
    #     app_id=1233,
    #     input_data_builder=_make_kv_builder({"prompt": ["关闭直播"], "uid": []}),
    #     semantic_description=(
    #         "通过服务端接口结束指定主播的直播（关播/停播）。"
    #         "覆盖能力：关闭直播间、停止推流、释放直播资源。"
    #         "适用于测试关播后的状态验证（如关播页数据展示）、"
    #         "以及作为测试后清理步骤确保直播间正确关闭。"
    #         "与 ai_room_start 配对使用。"
    #     ),
    # ),
    ToolSkill(
        name="GeckoX_settings",
        name_en="GeckoX_settings",
        saitama_template_id="a36871f6-2737-4c47-ba8e-ce10cfff95a3",
        mention_id="j6dx1qs9e4c3kg",
        uuid="401034",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {"env": ["local_test"], "required": ["True"]}
        ),
        semantic_description=(
            "仅用于切换 GeckoX 动态配置下发环境 env，可选值只有 local_test / boe / online 三个。"
            "⚠️ 路由规则：只要需求不是改这三个 env 之一（例如 Channel、Package ID、线上/内测部署、"
            "Row 环境、Gecko 自动更新开关等），不要用本工具，改用前置条件工具「Gecko 配置」。"
            "入参格式：GeckoX_settings env=local_test"
        ),
        params_hint="Input必填。env=Required(仅local_test/boe/online)。",
    ),
    ToolSkill(
        name="环境名称",
        name_en="env_name",
        saitama_template_id="baf0161b-b4b3-41af-a7cf-81c8d60b0c85",
        mention_id="qjhwrv44eo2w4t",
        uuid="401050",
        app_id=1233,
        input_data_builder=_env_name_input_data,
        semantic_description=(
            "指定测试运行的环境名称（envName），如 ppe/boe/线上泳道等。"
            "覆盖能力：切换请求路由到指定环境（泳道）。"
            "适用于需要在特定环境（如个人 ppe 泳道）下验证的测试场景。"
            "环境名称由外部参数 env 传入，格式：环境名称 env=ppe_my_test"
        ),
        params_hint="Input必填。env=Required(环境名称，如ppe_my_test)。",
    ),
    ToolSkill(
        name="场景Mock",
        name_en="Scene Mock",
        saitama_template_id="1649499f-1891-4f7a-afbe-4075f60ffa48",
        mention_id="pv3hq8nj5f2c6w",
        uuid="401002",
        app_id=1233,
        input_data_builder=_make_kv_builder({"scene": []}),
        semantic_description=(
            "配置场景 Mock，模拟特定的直播业务场景数据。"
            "覆盖能力：mock 活动入口、mock 运营位数据、mock 任务列表、"
            "mock 特定业务状态（如首充状态、等级数据、资格条件等）。"
            "入参为 scene JSON，包含 scene-scene ID 和 scene-nodes 节点列表。"
            "适用于需要特定业务数据状态但难以在测试环境真实构造的场景。"
        ),
    ),
    # ═══════════════════════ 高频辅助级 ═══════════════════════
    ToolSkill(
        name="open_schema",
        name_en="open_schema",
        saitama_template_id="8e529ad0-c243-41b0-b6f0-8997cb629bec",
        mention_id="l8fz3su1g6e5mi",
        uuid="401036",
        app_id=1233,
        input_data_builder=_make_kv_builder({"url": [], "required": ["True"]}),
        semantic_description=(
            "通过 Schema / Deeplink 打开指定页面或链接。"
            "覆盖能力：跳转到 App 内任意页面（如直播间、个人主页、商城、设置页等）、"
            "打开外部链接、通过 URL Scheme 唤起特定功能。"
            "适用于需要快速跳转到特定页面的测试场景，"
            "避免通过多步 UI 操作导航到目标页面。"
        ),
        params_hint="Input必填。url=Required；validation_str=Optional。",
    ),
    ToolSkill(
        name="mock_message",
        name_en="mock_message",
        saitama_template_id="b2d2c324-7c5e-4837-8512-4cc6e5dbe777",
        mention_id="s3mg4zb2n7l6tp",
        uuid="401043",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "uid": [],
                "role": [],
                "msg_type": ["WebcastMemberMessage"],
                "times": [],
                "template_id": [],
                "required": ["True"],
            }
        ),
        semantic_description=(
            "下发直播间模拟消息，支持多种消息类型。"
            "覆盖能力：模拟进房消息（WebcastMemberMessage）、"
            "聊天消息（WebcastChatMessage）、点赞消息（WebcastLikeMessage）、"
            "礼物公屏消息（WebcastGiftMessage）、观众分享消息（WebcastSocialMessage）、"
            "感知消息（WebcastPerceptionMessage）、目标更新消息（WebcastGoalUpdateMessage）。"
            "适用于直播间消息展示、互动效果、消息排序、公屏渲染等测试场景。"
        ),
        params_hint="Input必填。msg_type=Required；times=Required；template_id=Optional；uid=Optional；role=Optional。",
    ),
    ToolSkill(
        name="ui_assert",
        name_en="ui_assert",
        saitama_template_id="1b40e2b7-9f13-4caf-b0c2-5494ff5d46ff",
        mention_id="c9wq4jl2x7v6dz",
        uuid="401027",
        app_id=1233,
        input_data_builder=_ui_assert_input_data,
        semantic_description=(
            "执行 UI 视觉断言，通过 AI 视觉理解校验当前界面是否符合预期。"
            "覆盖能力：验证页面元素存在性、文案正确性、布局合理性、"
            "图标/按钮状态（高亮/置灰/隐藏）、弹窗展示内容等。"
            "输入一段自然语言描述的断言语句，工具自动截图并进行视觉校验。"
            "适用于无法通过接口验证、需要视觉确认的 UI 展示类测试场景。"
        ),
        params_hint="Input必填。assertion=Required(断言路径)。",
    ),
    ToolSkill(
        name="data_assertion",
        mention_type=41,
        name_en="data_assertion",
        saitama_template_id="31fce211-cf37-4684-8bd8-cfb168443d63",
        mention_id="r2lf3ya1m6k5so",
        uuid="401042",
        app_id=1233,
        input_data_builder=_data_assertion_input_data,
        semantic_description=(
            "执行数据层断言，通过抓包/日志/埋点等数据源校验后端行为。"
            "覆盖能力：网络请求断言（Network）、直播消息断言（LiveMessage）、"
            "JSBridge 调用断言（JSB）、Schema 跳转断言（Schema）、"
            "AppLog 埋点断言（AppLog）、ALOG 日志断言（ALOG）、"
            "性能监控断言（Appmonitor）。"
            "适用于需要验证接口返回值、埋点上报、消息下发等非 UI 层面的测试场景。"
        ),
        params_hint=(
            "Input必填。埋点断言强制：data_filter_name=<event_name> assert_type=AppLog "
            "assertion=<参数断言正文，不含「上报 event 埋点」前缀>。"
            "其它路径：assert_type∈{Network,LiveMessage,JSB,Schema,AppLog,ALOG,Appmonitor}；"
            "delay=Optional(异常时回退 5)。"
        ),
    ),
    ToolSkill(
        name="埋点断言",
        name_en="et_checker_G20",
        saitama_template_id="8e33fdd1-2d9f-4ac0-ad07-28adabf9c4c0",
        mention_id="gzrvjcyp2mwpc6",
        # ByteIO 埋点校验是 type=41 的环境工具（非 type=31 saitama 工具），app_id=0。
        # 对齐线上 case_step_tools：type 41 / saitama_template_id 8e33fdd1 / app_id 0 / input=byteio_case_list。
        app_id=0,
        mention_type=41,
        token="41",
        uuid="401060",
        input_data_builder=_et_checker_input_data,
        semantic_description=(
            "ByteIO 埋点校验工具（埋点断言）。校验当前操作是否正确上报了指定的 ByteIO 埋点用例。"
            "覆盖能力：绑定一组 ByteIO 埋点用例（byteio_case_list），执行后自动比对埋点上报是否命中。"
            "入参 byteio_case_list 为 JSON 数组，元素含 ID/Name/InvokeNum/AppID/Region，"
            "取自用例的 ByteIOCaseInfo.CaseList[<预期节点id>]。"
            "适用于埋点需求的验证场景：当某个预期结果节点关联了 ByteIO 埋点用例时，"
            "在该预期结果节点上挂本工具作为埋点断言（非独立操作步骤）。"
            "入参格式：et_checker_G20 byteio_case_list=[{\"ID\":\"...\",\"Name\":\"...\",\"InvokeNum\":1,\"AppID\":1233,\"Region\":\"sg\"}]"
        ),
        params_hint="Input必填。byteio_case_list=Required(埋点用例列表JSON数组，元素含ID/Name/InvokeNum/AppID/Region)。",
    ),
    ToolSkill(
        name="ai_get_nickname",
        name_en="ai_get_nickname",
        saitama_template_id="09ce6abe-6f94-43b1-a06b-cd3d39aaeb9e",
        mention_id="k1ey6rt4f9d8lh",
        uuid="401009",
        app_id=1233,
        input_data_builder=_ai_get_nickname_input_data,
        semantic_description=(
            "查询当前设备登录用户的昵称（uid 自动取当前设备 SYSTEM_GET_UID，无需手动传参）。"
            "执行后可通过 `${设备名.ai_data_gen_resp[nick_name]}` 在其他设备步骤中引用该昵称。"
            "适用于按昵称定位目标用户、校验邀请弹窗中的邀请人昵称等场景。"
        ),
        output_fields=["nick_name"],
        output_namespace="ai_data_gen_resp",
        post_ui_state="设备 UI 不变",
    ),
    ToolSkill(
        name="ai_uid_add_exp",
        name_en="ai_uid_add_exp",
        saitama_template_id="194cbe58-7cba-4ae9-9a10-7eb10db961d0",
        mention_id="m3ga8tv6h1f0nj",
        uuid="401011",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {"id": [], "lst": [], "prompt": ["添加实验"]}
        ),
        semantic_description=(
            "给指定测试账号 UID 添加到特定实验组。"
            "覆盖能力：将 UID 加入实验分组、批量添加多个 UID（逗号分隔）。"
            "可用 <SYSTEM_GET_UID> 获取当前登录账号的 UID。"
            "与 libra实验 的区别：libra实验 是全局实验配置，本工具是精确到 UID 级别的实验控制。"
            "适用于需要精确控制某个用户所在实验组的测试场景。"
        ),
    ),
    ToolSkill(
        name="ai_allowlist_add_item",
        name_en="ai_allowlist_add_item",
        saitama_template_id="491ac984-529b-4e5d-9022-548e2ef353c6",
        mention_id="p4kx7uv5g0e9mi",
        uuid="401062",
        app_id=1233,
        input_data_builder=_ai_allowlist_add_item_input_data,
        semantic_description=(
            "向指定 Allowlist（白名单）添加 Item。"
            "覆盖能力：按 list_id 写入单个 item_id，或通过 item_ids 批量添加；"
            "可指定生效起止时间（Unix 秒）、操作人 operator、原因 reason、caller、exec_region。"
            "item_id 与 item_ids 至少填一个；operator 须对目标白名单有写权限。"
            "默认：operator=liuminyi.naomi，reason=aidatagen add allowlist item，"
            "caller=explorer.api.executor；valid_begin_time 空=当前时间，"
            "valid_end_time 空=当前+365天。"
            "适用于测试账号/UID/设备等需要加白才能走通的场景。"
            "入参格式：ai_allowlist_add_item list_id=123 item_id=456 "
            "或 ai_allowlist_add_item list_id=123 item_ids=1,2,3"
        ),
        params_hint=_ALLOWLIST_PARAMS_HINT,
    ),
    ToolSkill(
        name="mutual_follow",
        name_en="mutual_follow",
        saitama_template_id="278a328c-8981-420a-9e31-f414da936024",
        mention_id="e1ys6ln4z9x8fb",
        uuid="401029",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {"user1": [], "user2": [], "required": ["True"]}
        ),
        semantic_description=(
            "让两个用户互相关注，建立双向关注关系。"
            "覆盖能力：发起关注、接受关注、建立互关关系。"
            "适用于需要互关状态作为前置条件的测试场景，"
            "如私信功能、连麦邀请、好友互动、粉丝团加入等。"
        ),
        params_hint=(
            "Input必填。"
            "user1=<设备名A.SYSTEM_GET_UID>；"
            "user2=<设备名B.SYSTEM_GET_UID>。"
            "值必须使用 SYSTEM_GET_UID 占位符格式，例如 <TT-主播设备-1.SYSTEM_GET_UID>。"
        ),
    ),
    # ai_wallet_send_coins_to_user 已移除：该工具被滥用于非必要场景，
    # 测试账号池中的账号已预置余额，无需额外充值。
    ToolSkill(
        name="ai_wallet_coin_balance",
        name_en="ai_wallet_coin_balance",
        saitama_template_id="03b1e2c3-13ae-4828-9304-668043a38b5a",
        mention_id="p6jd1wy9k4i3qm",
        uuid="401014",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {"prompt": ["wallet get coin balance"], "uid": []}
        ),
        semantic_description=(
            "查询指定用户的钱包虚拟币余额。"
            "覆盖能力：获取 Coin 余额、验证充值/消费后的余额变化。"
            "适用于需要验证钱包余额数值、充值到账、消费扣款等测试场景。"
        ),
    ),
    ToolSkill(
        name="fan_club_handy_tool",
        name_en="fan_club_handy_tool",
        saitama_template_id="d5134c73-0642-4650-8cbd-49b10b6522a1",
        mention_id="q7ke2xz0l5j4rn",
        uuid="401015",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "anchor_id": [],
                "cmd": [],
                "prompt": ["fan_club_handy_tool"],
                "room_id": [],
                "user_id": [],
            }
        ),
        semantic_description=(
            "粉丝团便捷工具，通过后端接口操作粉丝团相关功能。"
            "覆盖能力：创建粉丝团、加入粉丝团、修改粉丝团等级/积分、"
            "设置粉丝团成员状态、调用创作者 Bot 执行粉丝团管理命令。"
            "适用于粉丝团等级、社群、积分兑换、任务系统等功能的前置数据构造。"
        ),
    ),
    # ToolSkill(
    #     name="check_live_success",
    #     name_en="check_live_success",
    #     saitama_template_id="b1c1e7b9-d0ca-43c8-a733-f79c9aac548d",
    #     mention_id="q1ke2xz0l5j4rn", uuid="401041", app_id=1233,
    #     input_data_builder=_make_kv_builder({"required": ["True"]}),
    #     semantic_description=(
    #         "检测直播是否成功开播，验证开播状态是否就绪。"
    #         "覆盖能力：轮询检查直播间状态、确认推流成功、验证直播间可被访问。"
    #         "通常在 ai_room_start 之后使用，确保直播间稳定后再执行后续步骤。"
    #         "适用于开播后需要等待直播间就绪的测试场景。"
    #     ),
    #     requires="需在主播 GUI 开播操作之后执行",
    #     role_constraint="仅主播设备使用",
    # ),
    ToolSkill(
        name="文本动作",
        name_en="ocr_action",
        saitama_template_id="83f0a436-b530-47f5-8c88-7818e20e1905",
        mention_id="t4nh5ac3o8m7uq",
        uuid="401044",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "condition": [],
                "btn": [],
                "interval": [],
                "expire_time": [],
                "raise_error": ["结束执行"],
                "required": ["True"],
            }
        ),
        semantic_description=(
            "通过 OCR 文字识别循环检测屏幕上的文本，并在匹配后执行点击动作。"
            "覆盖能力：等待特定文本出现、点击包含指定文字的按钮、"
            "设置匹配超时时间和循环间隔、控制未匹配时的行为（结束/继续）。"
            "适用于常规 UI 定位方式无法准确找到元素、需要基于文本内容操作的场景，"
            "如弹窗按钮点击、动态文案匹配、Toast 确认等。"
        ),
        params_hint="Input必填。condition=Optional；btn=Optional；internval=Optional(default 2)；expire_time=Optional(default 20)；raise_error=Optional(default 继续执行)。",
    ),
    ToolSkill(
        name="ai_create_video",
        name_en="ai_create_video",
        saitama_template_id="34af5bbb-199a-4a8b-b0cb-8cdafac42d5f",
        mention_id="u1oi6bd4p9n8vr",
        uuid="401019",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "app_id": [],
                "effect": [],
                "env": [],
                "is_live_photo": [],
                "mature_theme_type": [],
                "product_num": [],
                "prompt": ["创建视频"],
                "prority_region": [],
                "store_region": [],
                "user_id": [],
                "vid_idc": [],
                "video_name": [],
                "video_status": [],
                "video_type": [],
            }
        ),
        semantic_description=(
            "通过 AI 数据构造在后端创建视频或 Photo 内容。"
            "覆盖能力：发布视频/Photo、设置视频区域和状态、指定视频类型和特效。"
            "适用于需要用户已发布视频/Photo 作为前置条件的测试场景，"
            "如视频详情页、评论功能、个人主页内容展示等。"
        ),
    ),
    ToolSkill(
        name="mock_set_keva",
        name_en="mock_set_keva",
        saitama_template_id="64e3db5d-addc-4f16-accd-c3b529e6c24c",
        mention_id="n8hb9uw7i2g1ok",
        uuid="401038",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {"repo": [], "keva": [], "required": ["True"]}
        ),
        semantic_description=(
            "修改直播场景的 Keva 状态管理配置（key-value 存储）。"
            "覆盖能力：设置直播间状态标记、修改业务逻辑开关、"
            "mock 特定的 Keva repo 下的 key-value 数据。"
            "输入 repo（字符串）和 keva（JSON 格式的 key:value）。"
            "适用于需要修改直播间内部状态标记的测试场景，"
            "如功能开关、状态机控制、特定条件触发等。"
        ),
        params_hint="Input必填。repo=Required；keva=Required。",
    ),
    ToolSkill(
        name="block_user",
        name_en="block_user",
        saitama_template_id="be94a59e-2781-4656-a79d-f7e8c96d6f86",
        mention_id="u5oi6bd4p9n8vr",
        uuid="401045",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "from_uid": [],
                "to_uids": [],
                "to_roles": [],
                "required": ["True"],
            }
        ),
        semantic_description=(
            "通过接口执行拉黑/屏蔽操作，将目标用户加入黑名单。"
            "覆盖能力：指定发起拉黑的用户 ID、被拉黑的用户 ID 列表（逗号分隔）、"
            "被拉黑的角色列表。"
            "适用于拉黑/屏蔽功能测试、拉黑后行为验证（如消息不可见、无法互动）等场景。"
        ),
        params_hint="Input必填。from_uid=Optional(default 当前登录uid)；to_uids=Optional；to_roles=Optional；to_uids/to_roles 建议至少一项。",
    ),
    ToolSkill(
        name="create_account",
        name_en="create_account",
        saitama_template_id="37a7043c-ee27-470b-9751-96af3e254506",
        mention_id="a7uo2hj0v5t4bx",
        uuid="401025",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "Country": [],
                "Birthday": [],
                "LivePermission": [],
                "required": ["True"],
            }
        ),
        semantic_description=(
            "通过 AI 数据构造实时创建全新测试账号。"
            "覆盖能力：指定国家/地区、设置生日（年龄）、授予直播权限。"
            "与 测试账号 的区别：测试账号 是从已有账号池获取，"
            "create_account 是创建全新账号，适用于需要纯净新账号的场景，"
            "如新用户引导流程、首次登录体验、注册流程测试等。"
        ),
        params_hint="Input必填。Country=Required；Birthday=Required；LivePermission=Required。",
    ),
    ToolSkill(
        name="ai_game_live_tool",
        name_en="ai_game_live_tool",
        saitama_template_id="6fdd37e3-10a1-4af1-86e1-970c8cde63df",
        mention_id="j0dx5qs3e8c7kg",
        uuid="401008",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "count": [],
                "gift_id": [],
                "prompt": ["游戏直播-测试工具"],
                "room_id": [],
                "scene": [],
                "to_user_id": [],
                "user_number": [],
            }
        ),
        semantic_description=(
            "游戏直播间专属测试工具，支持送礼和评论等互动操作。"
            "覆盖能力：在游戏直播间发送礼物（send_gift，需指定 gift_id、count、to_user_id）、"
            "发送评论（send_comment）、模拟多用户互动（user_number）。"
            "适用于游戏直播场景下的互动功能测试，如竞猜、送礼、评论等。"
        ),
    ),
    ToolSkill(
        name="popup_whitelist",
        name_en="popup_whitelist",
        saitama_template_id="738e66e7-39ed-4eaa-9933-eb517f1bb865",
        mention_id="y9sm0fh8t3r2zv",
        uuid="401049",
        app_id=1233,
        input_data_builder=_make_kv_builder({"popups": [], "required": ["True"]}),
        semantic_description=(
            "配置弹窗白名单，控制测试期间哪些系统弹窗允许展示。"
            "覆盖能力：屏蔽干扰性弹窗（如更新提示、运营活动弹窗）、"
            "放行需要测试的特定弹窗、确保测试流程不被无关弹窗打断。"
            "适用于自动化测试中需要控制弹窗行为的场景。"
        ),
        params_hint="Input必填。popups=Required。",
    ),
    ToolSkill(
        name="adb command",
        name_en="adb command",
        saitama_template_id="31265cf2-2a56-44a2-9a93-ce340f2e34e7",
        mention_id="d4xr5km3y8w7ea",
        uuid="401054",
        app_id=1233,
        input_data_builder=_make_kv_builder({"command": []}),
        semantic_description=(
            "在测试设备上执行 ADB（Android Debug Bridge）命令。"
            "覆盖能力：执行任意 adb shell 命令、安装/卸载应用、"
            "修改系统设置、清除应用缓存、模拟按键事件等。"
            "如需动态获取包名请使用 {package_name} 占位符。"
            "适用于需要直接操作设备底层的测试场景。"
        ),
    ),
    ToolSkill(
        name="ai_execute_punish",
        name_en="ai_execute_punish",
        saitama_template_id="76b95189-2159-44f0-89c9-ded8baf07caa",
        mention_id="i9cw4pr2d7b6jf",
        uuid="401007",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "execute_type": [],
                "object_id": [],
                "object_type": [],
                "prompt": ["edison_execute_punish"],
                "punish_info_id": [],
            }
        ),
        semantic_description=(
            "通过后端接口执行或解除账号处罚。"
            "覆盖能力：执行处罚（punish）或解除处罚（unpunish）、"
            "支持多种处罚对象类型（uid / did / room_id / session_id / group_id）、"
            "指定处罚措施 ID。"
            "适用于需要账号处于被处罚状态的测试场景，"
            "如封禁提示展示、处罚后功能限制验证、申诉流程测试等。"
        ),
    ),
    ToolSkill(
        name="弱网模拟",
        name_en="bynet traffic simulate",
        saitama_template_id="56cb2b89-2bc8-4559-b62e-3c8bd112ea20",
        mention_id="g7kw2xqm4b8t1r",
        uuid="401001",
        app_id=1233,
        input_data_builder=_make_kv_builder(
            {
                "down delay": ["0"],
                "up delay": ["0"],
                "down loss": ["0"],
                "up loss": ["0"],
                "down bandwidth": ["-1"],
                "up bandwidth": ["-1"],
            }
        ),
        semantic_description=(
            "模拟弱网络环境，控制设备的网络质量参数。"
            "覆盖能力：设置下行延迟（down delay, ms）、上行延迟（up delay, ms）、"
            "下行丢包率（down loss, %）、上行丢包率（up loss, %）、"
            "下行带宽限制（down bandwidth, -1 为不限制）、上行带宽限制（up bandwidth）。"
            "适用于弱网环境下的功能稳定性测试、网络异常恢复、加载超时处理等场景。"
        ),
    ),
    # ToolSkill(
    #     name="ai_privilege_enigma_handy_tool", name_en="ai_privilege_enigma_handy_tool",
    #     keywords=["权限工具", "privilege", "enigma"],
    #     saitama_template_id="0e67aeba-ec0b-458d-8637-6603a7924929",
    #     mention_id="w3qk8df6r1p0xt", uuid="401021", app_id=1233,
    #     input_data_builder=_make_kv_builder({"action": [], "prompt": ["privilege_enigma_handy_tool"], "sessionid": []}),
    #     semantic_description=(
    #         "权限 Enigma 便捷工具，通过后端接口批量设置用户权限。"
    #         "覆盖能力：开启/关闭直播权限、竞猜权限、连麦权限、管理员权限等。"
    #         "适用于需要特定权限状态的测试场景。"
    #     ),
    # ),
    # get_roomid_var: 已移除 — enter_room 通过 role 字段直接定位直播间，无需 get_roomid_var
    # ToolSkill(
    #     name="get_roomid_var", name_en="get_roomid_var",
    #     ...
    # ),
    # ToolSkill(
    #     name="ai_privilege_enigma_handy_tool", name_en="ai_privilege_enigma_handy_tool",
    #     keywords=["权限工具", "privilege", "enigma"],
    #     saitama_template_id="0e67aeba-ec0b-458d-8637-6603a7924929",
    #     mention_id="w3qk8df6r1p0xt", uuid="401021", app_id=1233,
    #     input_data_builder=_make_kv_builder({"action": [], "prompt": ["privilege_enigma_handy_tool"], "sessionid": []}),
    #     semantic_description=(
    #         "权限 Enigma 便捷工具，通过后端接口批量设置用户权限。"
    #         "覆盖能力：开启/关闭直播权限、竞猜权限、连麦权限、管理员权限等。"
    #         "适用于需要特定权限状态的测试场景。"
    #     ),
    # ),
    # ToolSkill(
    #     name="get_roomid_var", name_en="get_roomid_var",
    #     keywords=["roomid", "get_roomid", "房间ID变量"],
    #     saitama_template_id="c4e83f2b-bbc2-494b-82b7-95d5bfa774bd",
    #     mention_id="h8bv9oq7c2a1ie", uuid="401058", app_id=1233,
    #     input_data_builder=_make_kv_builder({"uid": []}),
    #     semantic_description="根据 uid 查询其直播间的 room_id 并存入公参。",
    #     output_fields=["get_room_id_var"],
    #     post_ui_state="设备 UI 不变",
    #     role_constraint="仅主播设备使用",
    # ),
]


# ---- 系统指令注册表（框架内置能力，非 saitama 工具） ----


@dataclass
class SystemCommand:
    """框架内置的系统指令，直接写入步骤文本，渲染时原样透传。 暂时包含UID的获取方式以及有限的MCP调用方式"""

    name: str
    syntax: str
    description: str
    requires: str = ""
    role_constraint: str = ""


SYSTEM_COMMANDS: List[SystemCommand] = [
    SystemCommand(
        name="SYSTEM_GET_UID",
        syntax="<设备名.SYSTEM_GET_UID>",
        description="获取指定设备当前登录账号的 UID，可内联在任意步骤文本中作为变量引用",
    ),
    SystemCommand(
        name="设置管理员",
        syntax="#<主播<主播设备.SYSTEM_GET_UID> 设置 <目标设备.SYSTEM_GET_UID> 为管理员>",
        description="在直播间中将目标用户设置为管理员",
        requires="需在主播 GUI 开播完成之后执行",
        role_constraint="仅主播设备执行",
    ),
]


# ---- 名称索引（用于 LLM 输出的工具名精确匹配） ----

_NAME_TO_SKILL: Dict[str, ToolSkill] = {}


def _build_name_index() -> None:
    """构建 name / name_en → ToolSkill 映射索引，供 apply_tool_skills 使用。"""
    _NAME_TO_SKILL.clear()
    for skill in TOOL_SKILLS:
        _NAME_TO_SKILL[skill.name] = skill
        _NAME_TO_SKILL[skill.name_en] = skill
        _NAME_TO_SKILL[skill.name.lower()] = skill
        _NAME_TO_SKILL[skill.name_en.lower()] = skill


_build_name_index()


def _match_tool_by_name(text: str, allow_prefix: bool = False) -> Optional[ToolSkill]:
    """通过精确名称匹配查找工具。LLM 应在前置条件中直接输出工具名。

    当 allow_prefix=True 时，支持前缀匹配：
    ``"ttmock_preset region=JP"`` → 匹配到 ttmock_preset 工具。
    调用方需自行将完整 text 作为 context 传给 build_input_data。
    """
    stripped = text.strip()
    if stripped in _NAME_TO_SKILL:
        return _NAME_TO_SKILL[stripped]
    lower = stripped.lower()
    if lower in _NAME_TO_SKILL:
        return _NAME_TO_SKILL[lower]
    for name, skill in _NAME_TO_SKILL.items():
        if stripped == name or lower == name.lower():
            return skill

    if allow_prefix:
        best: Optional[ToolSkill] = None
        best_len = 0
        for name, skill in _NAME_TO_SKILL.items():
            nl = name.lower()
            if lower.startswith(nl) and len(nl) > best_len:
                rest = lower[len(nl) :]
                if not rest or rest[0] in " \t(（":
                    best = skill
                    best_len = len(nl)
        return best

    return None


def _format_params_hint_for_prompt(skill_name: str, params_hint: str) -> str:
    """将 params_hint 格式化为 LLM prompt 中的参数化说明。

    输入格式：Input必填。param=Required(说明)；param=Optional(说明)。
    输出格式：参数化：`工具名 required_param=...`（Required 参数说明）。
    """
    if not params_hint:
        return ""

    # 移除 "Input必填。" 前缀
    normalized = params_hint.replace("Input必填。", "").strip()

    # 提取 Required 参数
    required_params = []
    required_hints = []
    for match in _SIMPLE_PARAMS_HINT_RE.finditer(normalized):
        raw_names, requiredness, details = match.groups()
        if requiredness and requiredness.lower() == "required":
            # 取第一个参数名（处理 a/b 格式）
            first_name = raw_names.split("/")[0].strip()
            required_params.append(first_name)
            if details:
                # 提取括号内的说明
                hint = details.strip("()")
                required_hints.append(f"{first_name}={hint}")

    # 生成参数示例
    if required_params:
        example = " ".join(f"{p}=..." for p in required_params)
        hint_str = "、".join(required_hints) if required_hints else ""
        return f" 参数化：`{skill_name} {example}`（{hint_str}）。"
    else:
        # 无 Required 参数，只显示 Optional 说明
        return f" 参数化：`{skill_name}`（可选参数：{normalized}）。"


def tools_prompt_context(skills: Optional[List[ToolSkill]] = None) -> str:
    """生成工具说明文本，注入 LLM prompt 让生成阶段就感知工具语义并精确使用工具名。"""
    if skills is None:
        skills = TOOL_SKILLS
    if not skills:
        return ""

    env_tools = [s for s in skills if s.name_en in _PRECONDITION_TOOLS]
    step_tools = [s for s in skills if s.name_en not in _PRECONDITION_TOOLS]

    lines = ["**【可用工具列表】**"]
    lines.append("")
    lines.append(
        "**A. 前置条件允许的环境工具（仅可写入 preconditions）** — "
        "`测试账号`、`ttmock_preset`、`Gecko 配置`、`环境名称`、`libra实验`："
    )
    lines.append(
        "  **工具选型（禁止混塞）**：PPE/泳道 → `环境名称 env=`；"
        "地区/语言/debug AB KV → `ttmock_preset`（`ab_settings`/`ab_settings_live` 必须是 JSON **对象** string，"
        "如 `{\"72192329\":\"1\"}`，禁止 `libra=`/`flight:`/数组）；"
        "Libra 加实验 → `libra实验`（`region`+`libra_id`+`group_id`；仅当有 Libra 链接且缺 group_id 时分别问实验组/对照组，正向挂实验组、对照/反向挂对照组）；"
        "Gecko Channel/Package 等 → `Gecko 配置`；仅改 GeckoX env 三选一 → 步骤工具 `GeckoX_settings`。"
    )
    for s in env_tools:
        desc = f"- **{s.name}**：{s.semantic_description}"
        if s.post_ui_state:
            desc += f" 执行后UI状态：{s.post_ui_state}。"
        if s.params_hint:
            desc += _format_params_hint_for_prompt(s.name, s.params_hint)
        lines.append(desc)

    lines.append("")
    lines.append(
        "**B. 流程工具（放 step_expected_pairs）** — 在 GUI 步骤之间调用，依赖前序步骤产生的状态："
    )
    for s in step_tools:
        desc = f"- **{s.name}**：{s.semantic_description}"
        if s.requires:
            desc += f" ⚠️ 前置：{s.requires}。"
        if s.role_constraint:
            desc += f" 约束：{s.role_constraint}。"
        if s.params_hint:
            desc += _format_params_hint_for_prompt(s.name, s.params_hint)
        if s.post_ui_state:
            desc += f" 执行后UI状态：{s.post_ui_state}。"
        if s.output_fields:
            ns = s.resp_namespace
            fields_str = ", ".join(f"`{f}`" for f in s.output_fields)
            desc += f" 输出公参：命名空间 `{ns}`，字段：{fields_str}。"
        lines.append(desc)

    if SYSTEM_COMMANDS:
        lines.append("")
        lines.append(
            "**C. 系统指令（System Commands）** — 框架内置能力，直接写入步骤文本："
        )
        for cmd in SYSTEM_COMMANDS:
            desc = f"- **`{cmd.syntax}`**：{cmd.description}。"
            if cmd.requires:
                desc += f" 前置：{cmd.requires}。"
            if cmd.role_constraint:
                desc += f" 约束：{cmd.role_constraint}。"
            lines.append(desc)

    acct_ctx = accounts_prompt_context()
    if acct_ctx:
        lines.append("")
        lines.append("**D. 账号与登录策略（Account & Login Strategy）**：")
        lines.append(acct_ctx)

    lines.append("")
    lines.append("**规则**：")
    lines.append(
        "- preconditions 中引用工具时，必须使用上方的精确工具名（name 或 name_en），不要自行改写或缩写"
    )
    lines.append(
        "- 部分工具支持参数化（见上方标注「参数化」的工具），格式：`工具名 参数名=值`。当 seed 需要非默认配置时**必须**追加参数"
    )
    lines.append(
        "- preconditions **仅允许**上方 A 节的环境工具名称（可带参数）或 `hint:`，"
        "**禁止**在其中写任何其他工具；其余工具一律写在 step_expected_pairs"
    )
    lines.append(
        "- **Gecko 路由**：`GeckoX_settings` 只改 env（`local_test`/`boe`/`online`）；"
        "Channel / Package / 线上·内测部署 / Row / 自动更新等一律用前置条件工具 `Gecko 配置`（扁平参数，geckoConfigs JSON 由工具拼装）"
    )
    lines.append(
        "- **流程工具**作为 step 写入 step_expected_pairs，格式：`{\"step\": \"设备占位符 工具名\", \"expected\": []}`"
    )
    lines.append("- 不要在 step 中重复编写被**环境工具**覆盖的操作（如登录、环境配置）")
    lines.append(
        "- **步骤起点取决于环境工具的「执行后UI状态」**：若标注「设备仍在首页」，步骤从首页导航开始；若标注「已进入直播间」，步骤可从直播间内操作开始"
    )
    lines.append(
        "- **流程工具排序**：严格遵守每个流程工具标注的「前置」约束，确保依赖工具在被依赖方之前执行"
    )
    lines.append(
        "- **设备约束**：严格遵守每个流程工具标注的「约束」，不要在不适用的设备上调用"
    )
    lines.append(
        "- **系统指令**可以替代 hint 实现自动化设置（如管理员授权），当系统指令能覆盖时**禁止**用 hint"
    )
    lines.append(
        "- **跨设备公参**：当设备 A 的工具输出需被设备 B 引用时，使用 `${设备名.命名空间[字段名]}`。生产工具必须在消费方之前执行"
    )
    lines.append("")
    lines.append("**Hint（人工设置提示）**：")
    lines.append("- **仅当**上方工具列表和系统指令中确实没有对应能力时，才可使用 hint")
    lines.append("- 优先级：工具 > 系统指令 > hint")
    lines.append("- 格式：`hint: <说明文字>`，例如：`hint: 客户端 ≥ 38.0`")
    lines.append("- 一条 hint 只描述一项配置，如有多项请分别写多条 hint")
    lines.append("")
    lines.append("**多设备前置条件**：")
    lines.append(
        "- 当用例涉及多个设备时，仅 A 节环境工具可加设备前缀；**无设备前缀**的 "
        "`测试账号` / `ttmock_preset` / `Gecko 配置` / `环境名称` / `libra实验` → 分配给**主播设备**"
    )
    lines.append(
        "- 需要在非主播设备上领取账号、环境预设或 Gecko 配置 → 仅用设备占位符前缀 + A 节工具："
        "`设备占位符 测试账号` / `设备占位符 ttmock_preset` / `设备占位符 Gecko 配置` / "
        "`设备占位符 环境名称` / `设备占位符 libra实验`"
    )

    return "\n".join(lines)


_PRECONDITION_TOOLS = frozenset({
    "Test Account",
    "TT Mock Preset",
    "Gecko Config",
    "env_name",
    "libra experiment",
})

_STEP_ONLY_TOOLS = frozenset(["enter_room", "ai_get_nickname"])


def _matches_tool_by_keyword(text: str, skill: ToolSkill) -> bool:
    """Fuzzy keyword matching — used only by nav_builder for natural-language steps."""
    t = text.lower().strip()
    if len(t) <= 3:
        return False
    return any(kw.lower() in t for kw in skill.keywords if len(kw) > 2)


def _matches_tool_by_name(text: str, skill: ToolSkill) -> bool:
    """Exact name matching — used by apply_tool_skills for preconditions."""
    t = text.lower().strip()
    return t == skill.name.lower() or t == skill.name_en.lower()


def _already_has_placeholder(text: str) -> bool:
    return "${richText_" in text or text.strip().startswith(">")


# ---- Hint 格式 ---------------------------------------------------------------

_HINT_PREFIX_RE = re.compile(
    r"^(?:hint[：:]\s*|>\s*|\*\*\[note\]\*\*\s*)", re.IGNORECASE
)


def _is_hint(text: str) -> bool:
    return bool(_HINT_PREFIX_RE.match(text.strip()))


_TTAT_REMARK_PREFIX_RE = re.compile(r"^\*\*\[remark\]\*\*\s*", re.IGNORECASE)
_TTAT_TAG_RE = re.compile(r"<ttat>", re.IGNORECASE)


def _with_ttat_remark(body: str) -> str:
    """将一段备注文本格式化为带 `<ttat>` 标记的 remark：`**[remark]** <ttat> {body}`。

    所有节点前置条件里的 remark 都必须打上 `<ttat>` 标记（幂等，不会重复添加）。
    """
    cleaned = (body or "").strip()
    # 去掉可能已有的 **[remark]** 前缀，避免重复嵌套
    cleaned = _TTAT_REMARK_PREFIX_RE.sub("", cleaned).strip()
    # 去掉文本里已有的 <ttat>，统一放到固定位置
    cleaned = _TTAT_TAG_RE.sub("", cleaned).strip()
    return f"**[remark]** <ttat> {cleaned}".rstrip()


def _format_hint(text: str) -> str:
    """将 'hint: 配置有权限账号' / '> 配置有权限账号' / '**[note]** ...' 统一转为
    带 `<ttat>` 标记的 remark：'**[remark]** <ttat> 配置有权限账号'。"""
    body = _HINT_PREFIX_RE.sub("", text.strip())
    return _with_ttat_remark(body)


def _ensure_ttat_on_remark(text: str) -> str:
    """对已是 `**[remark]**` / `**[note]**` 形态的前置条件补打 `<ttat>` 标记。"""
    s = (text or "").strip()
    if s.startswith("**[remark]**") or s.startswith("**[note]**"):
        body = re.sub(r"^\*\*\[(?:remark|note)\]\*\*\s*", "", s, flags=re.IGNORECASE)
        return _with_ttat_remark(body)
    return text


_dynamic_richtext_entries: Dict[str, Dict[str, Any]] = {}


_DEVICE_NAME_RE: Optional[re.Pattern] = None


def _get_device_name_re() -> re.Pattern:
    """Lazy-build regex that matches any known device / alias name at the start of text."""
    global _DEVICE_NAME_RE
    if _DEVICE_NAME_RE is None:
        from script.device_role_skills import all_name_to_richtext_tag

        names = sorted(all_name_to_richtext_tag().keys(), key=len, reverse=True)
        escaped = "|".join(re.escape(n) for n in names)
        _DEVICE_NAME_RE = re.compile(rf"^({escaped})\s+")
    return _DEVICE_NAME_RE


_RICHTEXT_TAG_PREFIX_RE = re.compile(r"^(\$\{richText_\d+:[^}]+\})\s+")
_DEVICE_NAME_FROM_TAG_RE = re.compile(r"\$\{richText_[^:]+:([^}]+)\}")

_DEFAULT_HOST_DEVICE = "TT-主播设备-1"


def _extract_device_name(device_tag: str) -> str:
    """Extract raw device name from richtext tag, default to host device."""
    if not device_tag:
        return _DEFAULT_HOST_DEVICE
    m = _DEVICE_NAME_FROM_TAG_RE.match(device_tag.strip())
    return m.group(1).strip() if m else _DEFAULT_HOST_DEVICE


def _split_device_prefix(text: str):
    """Split optional device prefix (raw name or richtext tag) from the rest.

    Returns (device_richtext_tag_or_empty, remaining_text).
    """
    s = text.strip()
    m = _RICHTEXT_TAG_PREFIX_RE.match(s)
    if m:
        return m.group(1), s[m.end() :].strip()

    m = _get_device_name_re().match(s)
    if m:
        from script.device_role_skills import all_name_to_richtext_tag

        tag = all_name_to_richtext_tag().get(m.group(1), "")
        return tag, s[m.end() :].strip()

    return "", s


def _register_skill_placeholder(skill: ToolSkill, context: str, validate_required: bool = True) -> str:
    """Register a tool skill and return its richtext placeholder string.

    Each call allocates a fresh uuid + mentionId. Identical tools / identical
    inputData still get distinct mentionIds (hard constraint for Bits binding).
    """
    # Validate / build inputData once so MissingRequiredToolParams still fires early.
    skill.build_input_data(context=context, validate_required=validate_required)
    use_uuid, use_mid = skill._new_invocation_ids()

    _dynamic_richtext_entries[use_uuid] = skill.richtext_struct(
        context=context,
        variant_uuid=use_uuid,
        variant_mention_id=use_mid,
        validate_required=validate_required,
    )
    return skill.richtext_placeholder(variant_uuid=use_uuid)


def reset_dynamic_registry():
    """重置动态 richtext 注册表。在渲染管线开始前调用一次。"""
    _dynamic_richtext_entries.clear()
    _used_mention_ids.clear()


def apply_tool_skills(
    cases: List[CaseBlock], skills: Optional[List[ToolSkill]] = None
) -> List[CaseBlock]:
    """
    对 CaseBlock 列表做后处理：
    1. 前置条件：工具名 → richtext 占位符；支持设备前缀（仅分配给对应设备）。
    2. 步骤中的工具调用：步骤 action 部分精确匹配工具名时替换为占位符。

    注意：跨 Feature 的工具调用实例会累积在 _dynamic_richtext_entries 中
    （每次调用独立 mentionId / uuid），调用方应在所有 Feature 处理完毕后通过
    richtext_registry() 读取完整注册表。使用 reset_dynamic_registry() 在渲染管线开始前重置。
    """
    if skills is None:
        skills = TOOL_SKILLS

    for case in cases:
        tool_preconditions: List[str] = []
        prepend_steps: List[StepExpected] = []

        for pc in case.preconditions:
            stripped_pc = (pc or "").strip()
            if stripped_pc.startswith("**[remark]**") or stripped_pc.startswith(
                "**[note]**"
            ):
                tool_preconditions.append(_ensure_ttat_on_remark(pc))
                continue

            if _already_has_placeholder(pc):
                tool_preconditions.append(pc)
                continue

            if _is_hint(pc):
                tool_preconditions.append(_format_hint(pc))
                continue

            device_tag, tool_text = _split_device_prefix(pc)

            matched_skill = _match_tool_by_name(tool_text, allow_prefix=True)

            if matched_skill:
                device_name = _extract_device_name(device_tag)
                enriched_context = f"{tool_text} __device__={device_name}"
                placeholder = _register_skill_placeholder(
                    matched_skill, context=enriched_context
                )
                if not device_tag:
                    from script.device_role_skills import all_name_to_richtext_tag
                    device_tag = all_name_to_richtext_tag().get(
                        _DEFAULT_HOST_DEVICE, ""
                    )
                full = f"{device_tag} {placeholder}"
                if matched_skill.name_en not in _PRECONDITION_TOOLS:
                    prepend_steps.append(StepExpected(step=full, expected=[]))
                elif full not in tool_preconditions:
                    tool_preconditions.append(full)
            else:
                prepend_steps.append(StepExpected(step=pc, expected=[]))

        # 强约束：只要用例存在前置条件节点，该节点就必须带 `**[remark]** <ttat>` 标记
        # （无论内容是工具占位还是备注）。若处理后没有任何带 <ttat> 的 remark，
        # 追加一条空 body 的 `**[remark]** <ttat>`，确保整个前置条件节点被标记为 TTAT 管理。
        if tool_preconditions and not any(
            _TTAT_TAG_RE.search(pc or "") for pc in tool_preconditions
        ):
            tool_preconditions.append(_with_ttat_remark(""))

        case.preconditions = tool_preconditions

        if prepend_steps:
            case.step_expected_pairs = prepend_steps + list(case.step_expected_pairs)

        for pair in case.step_expected_pairs:
            step_text = (pair.step or "").strip()
            if step_text:
                device_tag, action = _split_device_prefix(step_text)
                if action and not _already_has_placeholder(action):
                    matched_skill = _match_tool_by_name(action, allow_prefix=True)
                    if matched_skill:
                        placeholder = _register_skill_placeholder(matched_skill, context=action)
                        pair.step = f"{device_tag} {placeholder}" if device_tag else placeholder

            # 预期结果里的断言工具（如 et_checker_G20 埋点校验）→ richtext 占位符。
            # 埋点校验挂在预期结果节点上（非独立步骤），保留断言事件文本在占位符前。
            if pair.expected:
                pair.expected = [
                    _convert_assertion_tool_in_expected(e) for e in pair.expected
                ]

    return cases


# 预期结果中内联的断言工具（工具名 + 参数，跑到字符串末尾）。
# data_assertion：埋点 AppLog；et_checker_G20：ByteIO 用例列表。
_EXPECTED_ASSERTION_TOOL_RE = re.compile(
    r"(?:^|(?<=[\s，,；;：:]))((?:data_assertion|et_checker_G20)(?:\s+\S.*)?)$"
)


def _convert_assertion_tool_in_expected(text: str) -> str:
    """把预期结果字符串末尾内联的断言工具（et_checker_G20 ...）转成 richtext 占位符，
    保留占位符前的断言事件文本（含可能已有的设备占位符）。

    幂等性由正则保证：转换后字符串里只剩 `${richText_...:埋点断言}`（不含原始
    `et_checker_G20 byteio_case_list=` token），正则不会再次命中。多设备用例的
    预期结果本身带设备 `${richText_...}` 前缀，也不影响本转换。"""
    s = text or ""
    m = _EXPECTED_ASSERTION_TOOL_RE.search(s)
    if not m:
        return s
    tool_ctx = m.group(1).strip()
    matched = _match_tool_by_name(tool_ctx, allow_prefix=True)
    if not matched:
        return s
    placeholder = _register_skill_placeholder(matched, context=tool_ctx)
    prefix = s[: m.start(1)].strip()
    return f"{prefix} {placeholder}".strip() if prefix else placeholder


# ---- 地区（US / EU）识别 + ttmock_preset 与标签强制 -------------------------

_REGION_PARAM_RE = re.compile(
    r'(?:region|区域|地区)\s*[=:：]\s*["\']?([A-Za-z]{2,3})', re.IGNORECASE
)
# 账号相关参数中的「账号名」字段
_ACCOUNT_NAME_PARAM_RE = re.compile(
    r'(?:pool_name|username|user_name|tag_name|tag|账号名|账号)\s*[=:：]\s*["\']?([^\s"\';，,；]+)',
    re.IGNORECASE,
)
# 文本里的独立大写地区词（避免误命中 user / bus / plus 等）
_US_WORD_RE = re.compile(r'(?<![A-Za-z])US(?![A-Za-z])')
_EU_WORD_RE = re.compile(r'(?<![A-Za-z])EU(?![A-Za-z])')


def _detect_case_region(case: CaseBlock) -> Optional[str]:
    """识别用例归属地区，返回 "US" / "EU" / None。

    触发规则（与 SKILL.md 一致）：
    1. 任意文本中出现 `region=us`/`region=eu` 等显式地区参数；
    2. 前置条件账号参数（pool_name/username/tag 等）的取值包含 "us"/"eu" 字样；
    3. 标题或前置条件里出现独立大写地区词 US/EU，或「美国 / 欧盟 / 欧洲」。
    """
    pre_texts = [p for p in (case.preconditions or []) if p]

    # 规则 2：账号名包含 us/eu（仅在前置条件账号参数取值里判断，降低误判）
    for pc in pre_texts:
        for m in _ACCOUNT_NAME_PARAM_RE.finditer(pc):
            name = (m.group(1) or "").lower()
            if "us" in name:
                return "US"
            if "eu" in name:
                return "EU"

    # 规则 1：显式 region 参数
    blob_all = [case.title or "", case.summary or ""]
    blob_all.extend(pre_texts)
    for pair in case.step_expected_pairs or []:
        blob_all.append(pair.step or "")
        blob_all.extend(pair.expected or [])
    blob_all.extend(case.steps_only or [])
    blob_all.extend(case.expected_only or [])
    blob = "\n".join(blob_all)
    for m in _REGION_PARAM_RE.finditer(blob):
        val = (m.group(1) or "").upper()
        if val == "US":
            return "US"
        if val == "EU":
            return "EU"

    # 规则 3：标题 / 前置条件里的独立地区词
    head = "\n".join([case.title or ""] + pre_texts)
    if _US_WORD_RE.search(head) or "美国" in head:
        return "US"
    if _EU_WORD_RE.search(head) or "欧盟" in head or "欧洲" in head:
        return "EU"
    return None


_TTMOCK_TOKEN_RE = re.compile(r"ttmock_preset", re.IGNORECASE)


def _ensure_ttmock_region(case: CaseBlock, region: str) -> None:
    """确保用例前置条件里存在 `ttmock_preset region=<REGION>`（就地修改 case.preconditions）。

    只就地改写 `ttmock_preset` 之后的 region 取值，**保留原始设备前缀文本**（裸设备名或
    已有占位符），避免把裸设备名提前转成 `${richText_...}` 导致 apply_tool_skills 跳过工具替换。
    """
    target = f"region={region}"
    new_pre: List[str] = []
    found = False
    for pc in case.preconditions or []:
        m = _TTMOCK_TOKEN_RE.search(pc or "")
        if m:
            found = True
            prefix = pc[: m.start()]
            rest = pc[m.start():]
            if re.search(r"region\s*[=:：]", rest, re.IGNORECASE):
                rest = re.sub(
                    r"region\s*[=:：]\s*[\"']?[A-Za-z]{2,3}",
                    target,
                    rest,
                    count=1,
                    flags=re.IGNORECASE,
                )
            else:
                rest = rest.rstrip().rstrip(";").rstrip() + " " + target
            pc = prefix + rest
        new_pre.append(pc)
    if not found:
        new_pre.append(f"ttmock_preset {target}")
    case.preconditions = new_pre


def enforce_region_and_tags(cases: List[CaseBlock]) -> List[CaseBlock]:
    """对涉及 US / EU 的用例强制：
    1. 前置条件使用 `ttmock_preset` 把地区设为对应区域；
    2. 在用例（分支根节点）上打上 `US` / `EU` 标签。

    需在 apply_tool_skills 之前调用（此时前置条件仍是文本，便于补 ttmock_preset）。
    """
    for case in cases:
        region = _detect_case_region(case)
        if not region:
            continue
        _ensure_ttmock_region(case, region)
        if region not in (case.tags or []):
            case.tags = list(case.tags or []) + [region]
    return cases


def richtext_registry(
    skills: Optional[List[ToolSkill]] = None,
) -> Dict[str, Dict[str, Any]]:
    """返回 uuid → RichText 结构映射：多机角色设备 + 本次渲染中实际调用的工具实例。

    工具条目只来自 ``_dynamic_richtext_entries``（每次调用分配唯一 mentionId / uuid），
    不再把 ``TOOL_SKILLS`` 注册表里的静态 mention_id / base uuid 写入产物。
    ``skills`` 参数保留以兼容旧调用方，已忽略。
    """
    from script.device_role_skills import role_richtext_registry

    del skills  # unused; kept for call-site compatibility
    base: Dict[str, Dict[str, Any]] = dict(role_richtext_registry())
    base.update(_dynamic_richtext_entries)
    return base
