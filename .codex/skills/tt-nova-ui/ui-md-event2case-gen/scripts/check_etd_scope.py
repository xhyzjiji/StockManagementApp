#!/usr/bin/env python3
"""Gate for R12–R16: validate etd_scope.json and scan source cases for anti-patterns.

Usage:
  python check_etd_scope.py --scope path/etd_scope.json
  python check_etd_scope.py --scope path/etd_scope.json --cases path/source_cases.md
  python check_etd_scope.py --self-check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # 同目录脚本；缺失时降级为「只做事件名反查」，不静默当成通过
    from etd_sheet_load import parse_etd_table
except ImportError:  # pragma: no cover
    parse_etd_table = None  # type: ignore[assignment]

PARAM_KINDS = {"enum", "opaque", "semantic"}
# 反例形态由此决定：new_event 的反例是「事件不上报」，param_added 的反例是
# 「旧场景仍上报、但不带新增参数」——老埋点新增参数时上报时机不变。
CHANGE_TYPES = {"new_event", "param_added"}
POLICIES = {"per_click", "dedup", "per_emit", "n/a"}
TEST_KIT_FIELDS = ("packages", "env", "libra_flights", "accounts")
RESOLVED_CONFLICT_STATUSES = {"resolved", "accepted", "waived", "ignored", "out_of_scope"}
ROLE_TAG_MAP = {
    "anchor": ("主播",),
    "viewer": ("观众", "用户", "看播"),
    "guest": ("嘉宾",),
    "moderator": ("管理员",),
}
LEGACY_DEVICE_PREFIXES = ("TT-主播设备", "TT-观众设备", "TT-用户设备", "TT-嘉宾设备")
DEVICE_PREFIX_RE = re.compile(r"设备([A-Z])[（(]([^）)]+)[）)]：")
STRICT_ENV_LINE_RE = re.compile(r"-\s*mock\s*\|\s*env\s*=\s*\S+")
STRICT_FLIGHT_LINE_RE = re.compile(
    r"-\s*mock\s*\|\s*.{0,20}libra\s+flight\s*/\s*\S+"
)
OR_MERGE_ENUM_RE = re.compile(
    r"`[^`]+`\s*(?:=\s*`[^`]+`\s*(?:、|，|,)\s*`[^`]+`|=\s*`[^`]+`\s*或\s*`[^`]+`)"
)
GENERIC_OR_MERGE_RE = re.compile(
    r"(?:=\s*[`']?[^`'；。\n]+[`']?\s*(?:、|，|,)\s*[`']?[^`'；。\n]+[`']?\s*(?:或|and)\s*[`']?[^`'；。\n]+[`']?)"
)

# Titles that imply per-emoji cartesian product (R13 anti-pattern when opaque)
_EMOJI_TITLE_RE = re.compile(
    r"点击(?:点赞|鼓掌|大笑|爱心|烟花|Hi|hi|❤️|👍|👏|😂|🎆)表情"
    r"|发送(?:点赞|鼓掌|大笑|爱心|烟花|Hi|hi)表情"
)


def _err(msg: str, errors: list[str]) -> None:
    errors.append(msg)


def validate_scope(data: dict[str, Any], errors: list[str]) -> None:
    if data.get("authority") != "user_etd_body":
        _err("authority must be 'user_etd_body' (本需求 ETD 正文为准)", errors)
    if not data.get("etd_url"):
        _err("missing etd_url", errors)
    events = data.get("events")
    if not isinstance(events, list) or not events:
        _err("events must be a non-empty list", errors)
        return
    for i, ev in enumerate(events):
        prefix = f"events[{i}]"
        if not isinstance(ev, dict):
            _err(f"{prefix} must be object", errors)
            continue
        if not ev.get("event_name"):
            _err(f"{prefix}.event_name required", errors)
        if not isinstance(ev.get("entrances"), list) or not ev["entrances"]:
            _err(f"{prefix}.entrances must be non-empty list (R12)", errors)
        if not isinstance(ev.get("roles"), list) or not ev["roles"]:
            _err(f"{prefix}.roles must be non-empty list", errors)
        params = ev.get("params")
        if not isinstance(params, list):
            _err(f"{prefix}.params must be list", errors)
            params = []
        for j, p in enumerate(params):
            pk = f"{prefix}.params[{j}]"
            if not isinstance(p, dict) or not p.get("key"):
                _err(f"{pk} needs key", errors)
                continue
            kind = p.get("kind")
            if kind not in PARAM_KINDS:
                _err(f"{pk}.kind must be one of {sorted(PARAM_KINDS)}", errors)
            if kind == "enum":
                vals = p.get("values")
                if not isinstance(vals, list) or not vals:
                    _err(f"{pk} enum needs non-empty values (R13)", errors)
            if kind == "semantic":
                if not p.get("meaning"):
                    _err(f"{pk} semantic needs meaning (R15)", errors)
                if not p.get("example_expect"):
                    _err(f"{pk} semantic needs example_expect (R15)", errors)
        change_type = ev.get("change_type")
        if change_type not in CHANGE_TYPES:
            _err(
                f"{prefix}.change_type 必填 (R19)，取值 {sorted(CHANGE_TYPES)}："
                "new_event→反例=事件不上报；param_added→反例=仍上报但不带新增参数。"
                "取自 ETD 变更类型/是否新增列，认不出就反问，禁止默认",
                errors,
            )
        elif change_type == "param_added" and not [
            p for p in params if isinstance(p, dict) and p.get("added")
        ]:
            _err(
                f"{prefix} change_type=param_added 必须用 params[].added=true 标出本需求新增的参数"
                "（反例要断言这些参数不携带，不是整个事件不上报）",
                errors,
            )

        for pol_key in ("show_policy", "click_policy"):
            pol = ev.get(pol_key)
            if pol is not None and pol not in POLICIES:
                _err(f"{prefix}.{pol_key} must be one of {sorted(POLICIES)}", errors)

        combos = ev.get("expected_combinations")
        if combos is not None:
            if not isinstance(combos, list) or not combos:
                _err(f"{prefix}.expected_combinations must be non-empty list when present", errors)
            else:
                param_keys = {
                    str(p.get("key"))
                    for p in params
                    if isinstance(p, dict) and p.get("key")
                }
                for k, combo in enumerate(combos):
                    ck = f"{prefix}.expected_combinations[{k}]"
                    if not isinstance(combo, dict) or not combo:
                        _err(f"{ck} must be non-empty object", errors)
                        continue
                    unknown_keys = set(map(str, combo.keys())) - param_keys
                    if unknown_keys:
                        _err(
                            f"{ck} has key(s) not declared in params: {sorted(unknown_keys)}",
                            errors,
                        )
    validate_test_kit(data.get("test_kit"), errors)

    oos = data.get("out_of_scope", [])
    if oos is not None and not isinstance(oos, list):
        _err("out_of_scope must be list", errors)

    conflicts = data.get("conflicts", [])
    if conflicts is not None and not isinstance(conflicts, list):
        _err("conflicts must be list", errors)
    elif isinstance(conflicts, list):
        for i, item in enumerate(conflicts):
            if not isinstance(item, dict):
                _err(f"conflicts[{i}] must be object", errors)
                continue
            severity = str(item.get("severity", "")).lower()
            status = str(item.get("status", "")).lower()
            if severity == "blocking" and status not in RESOLVED_CONFLICT_STATUSES:
                _err(
                    f"unresolved blocking conflict: conflicts[{i}] "
                    f"{item.get('kind') or item.get('title') or item.get('value') or ''}"
                    "（GT/PRD/ETD 冲突必须先反问并 resolve，禁止静默 out-of-scope）",
                    errors,
                )


def validate_test_kit(kit: Any, errors: list[str]) -> None:
    """R6：测试物料必须抽取并落盘，缺项必须显式登记，不能靠一句散文 checklist。

    G1 增强：
    - source_doc（提测/测试说明文档 URL/标题）必填，确保 agent 确实解析了 release_doc 而不是跳过。
    - 不允许所有四个核心字段（packages/env/libra_flights/accounts）全空且 missing 也空，
      那说明 agent 什么都没抽到也没承认没抽到。
    """
    if kit is None:
        _err(
            "missing test_kit (R6)：提测/测试说明文档里的 包/env/实验/账号 必须抽进 scope.test_kit；"
            "确实没有的字段写进 test_kit.missing[] 带 reason",
            errors,
        )
        return
    if not isinstance(kit, dict):
        _err("test_kit must be object", errors)
        return
    source_doc = str(kit.get("source_doc") or "").strip()
    if not source_doc:
        _err(
            "test_kit.source_doc 必填 (R6/G1)：记录本次解析的提测/测试说明文档 URL 或标题，"
            "用来证明 release_doc 确实被读取（认内容不认标题，叫测试说明/质量保障也算）",
            errors,
        )
    declared_missing = {
        str(m.get("field"))
        for m in kit.get("missing") or []
        if isinstance(m, dict) and m.get("field") and m.get("reason")
    }
    empty_fields: list[str] = []
    for field in TEST_KIT_FIELDS:
        value = kit.get(field)
        if isinstance(value, dict):
            value = [v for v in value.values() if v]
        if not value and field not in declared_missing:
            empty_fields.append(field)
    if empty_fields:
        _err(
            f"test_kit.{empty_fields} 为空且未登记 (R6)：从提测/测试说明文档抽取，"
            f"或写 test_kit.missing[{{'field':'<name>','reason':…,'gap_id':…}}]",
            errors,
        )
    non_empty = [f for f in TEST_KIT_FIELDS if f not in empty_fields]
    if not non_empty and not declared_missing:
        _err(
            "test_kit 所有核心字段（packages/env/libra_flights/accounts）全空且 missing[] 也空 (G1)："
            "说明 release_doc 完全没被解析，禁止交付。要么补抽要么显式登记缺失原因。",
            errors,
        )


_PRECONDITION_RE = re.compile(r"\*\*Precondition\*\*:?(.*?)(?=\n\*\*|\Z)", re.S)


def check_test_kit_in_cases(text: str, scope: dict[str, Any], errors: list[str]) -> None:
    """P0：env / libra 实验必须落到每条用例 Precondition，且格式严格（G3）。

    - 只写在文件头的 `## 测试物料(Test Kit)` 段不会被 md→xmind 转换器搬走。
    - 散文写法（「环境：ppe_xxx」、「加了实验 xxx」）不会被 BITS 前置条件工具识别。
    - 必须是 `- mock | env=<value>` 和 `- mock | ... libra flight/<id>` 这种管道格式。
    """
    kit = scope.get("test_kit")
    if not isinstance(kit, dict):
        return
    env = str(kit.get("env") or "").strip()
    flights = [str(f).strip() for f in kit.get("libra_flights") or [] if str(f).strip()]
    if not env and not flights:
        return

    missing_env: list[str] = []
    missing_flight: list[str] = []
    bad_format_env: list[str] = []
    bad_format_flight: list[str] = []
    for block in _split_cases(text):
        title = (re.search(r"^> (.+)$", block, re.M) or [None, "?"])[1]
        pre = "".join(_PRECONDITION_RE.findall(block))
        if env:
            if env not in pre:
                missing_env.append(str(title))
            elif not STRICT_ENV_LINE_RE.search(pre):
                bad_format_env.append(str(title))
        if flights:
            has_any_flight = False
            bad_format = True
            for f in flights:
                if f in pre:
                    has_any_flight = True
                    if STRICT_FLIGHT_LINE_RE.search(pre):
                        bad_format = False
                        break
            if not has_any_flight:
                missing_flight.append(str(title))
            elif bad_format:
                bad_format_flight.append(str(title))

    if env and missing_env:
        _err(
            f"测试物料未落到用例 (P0): {len(missing_env)} 条用例 Precondition 缺 env `{env}`"
            f"（例：{missing_env[0][:50]}）。格式必须是 `- mock | env={env}`",
            errors,
        )
    if flights and missing_flight:
        _err(
            f"测试物料未落到用例 (P0): {len(missing_flight)} 条用例 Precondition 缺 libra 实验 {flights}"
            f"（例：{missing_flight[0][:50]}）。格式必须是 `- mock | 账号已加实验 libra flight/<id>`",
            errors,
        )
    if bad_format_env:
        _err(
            f"Precondition env 行格式不规范 (G3): {len(bad_format_env)} 条用例包含 env 但不是 `- mock | env=xxx` 管道格式"
            f"（例：{bad_format_env[0][:50]}）。散文写法不会被门禁认作 env 下沉；可执行节点靠 Step 5 `环境名称` 工具。",
            errors,
        )
    if bad_format_flight:
        _err(
            f"Precondition libra 行格式不规范 (G3): {len(bad_format_flight)} 条用例包含 flight 但不是 `- mock | ... libra flight/<id>` 管道格式"
            f"（例：{bad_format_flight[0][:50]}）。散文写法不会被门禁认作实验下沉；可执行节点靠 Step 5 `libra实验` 工具。",
            errors,
        )


def scan_cases(text: str, scope: dict[str, Any] | None, errors: list[str]) -> None:
    # R14: legacy confusing title
    if re.search(r"不去重失败", text) and not re.search(r"按次上报|点几次报几次", text):
        _err("R14: found '不去重失败' without per-click wording; rewrite to 点几次报几次", errors)

    # R15: show_ucnt only 有值
    for m in re.finditer(r"`?stage_reaction_show_ucnt`?\s*有值", text):
        window = text[max(0, m.start() - 80) : m.end() + 120]
        if "不含主播" not in window and "口径" not in window and "能看到" not in window:
            _err(
                "R15: stage_reaction_show_ucnt asserted as 有值 without meaning/口径 nearby",
                errors,
            )
            break

    # R16: interact_panel assert with bottom entrance step nearby in same case-ish window
    if "link_page_entrance" in text and "interact_panel" in text:
        if re.search(r"底部连麦入口.*管理面板|底部连麦入口打开管理", text):
            _err(
                "R16: bottom_linkmic manage path coexists with interact_panel asserts; bind Path to 自己麦位→manage",
                errors,
            )

    # G4（R11）：禁止旧格式设备前缀 TT-主播设备 / TT-观众设备 / TT-用户设备，必须用 设备A（角色）：
    legacy_hits = []
    for legacy in LEGACY_DEVICE_PREFIXES:
        for m in re.finditer(re.escape(legacy), text):
            # find the whole line
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)
            legacy_hits.append(text[line_start:line_end].strip()[:120])
    if legacy_hits:
        _err(
            f"R11/G4: 发现 {len(legacy_hits)} 处旧格式设备前缀（{LEGACY_DEVICE_PREFIXES}），"
            f"必须改为新格式「设备X（角色）：」（如 设备A（主播）：开播）。例：{legacy_hits[0]}",
            errors,
        )

    # G4 新格式：多角色场景下，操作步骤/断言行必须以 设备X（角色）： 开头（非多角色场景放宽）
    device_prefix_hits = DEVICE_PREFIX_RE.findall(text)
    multi_role = False
    if scope is not None:
        all_roles: set[str] = set()
        for ev in scope.get("events") or []:
            if isinstance(ev, dict):
                for r in ev.get("roles") or []:
                    all_roles.add(str(r).lower())
        multi_role = len(all_roles) >= 2

    # G6：Assert 行中「参数 = A 或 B」「参数 = A、B、C」反模式
    or_merge_hits: list[str] = []
    for m in OR_MERGE_ENUM_RE.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end].strip()
        if "不上报" in line:
            continue
        or_merge_hits.append(line[:160])
    if or_merge_hits:
        _err(
            f"R13/G6: Assert 中出现 {len(or_merge_hits)} 处「或/、合并枚举」反模式，"
            f"必须按 R13 拆成独立用例，禁止把多个枚举值写在同一条断言里。例：{or_merge_hits[0]}",
            errors,
        )

    if scope is None:
        return

    oos_entrances = {
        str(x.get("value", "")).lower()
        for x in scope.get("out_of_scope") or []
        if isinstance(x, dict) and x.get("dim") == "entrance"
    }
    if "bottom_linkmic" in oos_entrances or "底部连麦" in oos_entrances:
        titles = re.findall(r"^> (.+)$", text, re.M)
        bad = [t for t in titles if "底部连麦" in t]
        if bad:
            _err(
                f"R12: {len(bad)} case(s) use out_of_scope entrance 底部连麦: e.g. {bad[0][:60]}",
                errors,
            )

    # R13: opaque stage_reaction_id + many emoji-specific titles
    opaque_reaction = False
    for ev in scope.get("events") or []:
        for p in ev.get("params") or []:
            if p.get("key") == "stage_reaction_id" and p.get("kind") == "opaque":
                opaque_reaction = True
    if opaque_reaction:
        title_hits = [t for t in re.findall(r"^> (.+)$", text, re.M) if _EMOJI_TITLE_RE.search(t)]
        if len(title_hits) >= 3:
            _err(
                f"R13: stage_reaction_id is opaque but {len(title_hits)} per-emoji titles found; "
                "collapse to role-only click/show",
                errors,
            )


def _split_cases(text: str) -> list[str]:
    """Split source_cases.md into per-case blocks (title `> ` + `**Steps**`)."""
    return [
        b
        for b in re.split(r"^---$", text, flags=re.M)
        if re.search(r"^> ", b, re.M) and "**Steps**" in b
    ]


def _polarity(block: str, event: str) -> tuple[bool, bool]:
    """(asserted_positive, asserted_negative) for one event inside one case block.

    按分句判极性：`上报 \\`event\\` 埋点；不上报 \\`new_param\\`` 里的事件仍是正向
    （老埋点新增参数的反例形态），只有事件本身被否定才算反向。
    """
    pos = neg = False
    for line in block.splitlines():
        if event not in line:
            continue
        for clause in re.split(r"[；;。]", line):
            if event not in clause:
                continue
            if _NEG_EMIT_RE.search(clause):
                neg = True
            elif "上报" in clause:
                pos = True
    return pos, neg


_PAIR_RE = re.compile(r"`(\w+)`\s*=\s*`([^`]+)`")


def _pairs_in_block(block: str) -> set[tuple[str, str]]:
    return {(str(k), str(v)) for k, v in _PAIR_RE.findall(block)}


def _combo_items(combo: dict[str, Any]) -> set[tuple[str, str]]:
    return {(str(k), str(v)) for k, v in combo.items()}


def _scope_events(scope: dict[str, Any]) -> set[str]:
    return {
        str(ev.get("event_name"))
        for ev in scope.get("events") or []
        if isinstance(ev, dict) and ev.get("event_name")
    }


def _scope_enum_pairs(scope: dict[str, Any]) -> set[tuple[str, str, str]]:
    pairs: set[tuple[str, str, str]] = set()
    for ev in scope.get("events") or []:
        if not isinstance(ev, dict):
            continue
        event = str(ev.get("event_name") or "")
        if not event:
            continue
        for p in ev.get("params") or []:
            if not isinstance(p, dict) or p.get("kind") != "enum":
                continue
            key = str(p.get("key") or "")
            for val in p.get("values") or []:
                pairs.add((event, key, str(val)))
        for combo in ev.get("expected_combinations") or []:
            if not isinstance(combo, dict):
                continue
            for key, val in combo.items():
                pairs.add((event, str(key), str(val)))
    return pairs


def _norm_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("step", "text", "content", "title", "name"):
            if value.get(key):
                return str(value[key])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(_norm_text(x) for x in value)
    return "" if value is None else str(value)


def _gt_extract_from_seeds(path: Path) -> tuple[set[str], set[tuple[str, str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    seeds = payload.get("seeds") if isinstance(payload, dict) else None
    if not isinstance(seeds, list):
        raise ValueError("--gt-seeds must be extract_bits_case.py JSON with top-level seeds[]")

    events: set[str] = set()
    pairs: set[tuple[str, str, str]] = set()
    event_re = re.compile(r"livesdk_[A-Za-z0-9_]+")
    loose_pair_re = re.compile(r"`?([A-Za-z_][A-Za-z0-9_]*)`?\s*=\s*`?([A-Za-z0-9_]+)`?")
    for seed in seeds:
        if not isinstance(seed, dict):
            continue
        chunks: list[str] = []
        # 字段名对齐 extract_bits_case.py 的 SeedBlock（分支路径在 seed_path_text，
        # 事件名常只出现在分支标签上，漏读会让 GT 反查失效）
        for key in ("seed_path_text", "feature_path_text", "title", "note"):
            chunks.append(_norm_text(seed.get(key)))
        chunks.extend(_norm_text(x) for x in seed.get("steps") or [])
        chunks.extend(_norm_text(x) for x in seed.get("expected") or [])
        text = "\n".join(chunks)
        events.update(event_re.findall(text))
        for line in text.splitlines():
            line_events = event_re.findall(line)
            if not line_events:
                continue
            # Associate pairs on a line with the first event on that same line.
            event = line_events[0]
            for key, value in loose_pair_re.findall(line):
                if key.startswith("livesdk_"):
                    continue
                pairs.add((event, str(key), str(value)))
    return events, pairs


def _resolved_conflict_values(scope: dict[str, Any]) -> set[tuple[str, str, str]]:
    values: set[tuple[str, str, str]] = set()
    for item in (scope.get("conflicts") or []) + (scope.get("out_of_scope") or []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).lower()
        # out_of_scope entries historically do not always carry status.
        if status and status not in RESOLVED_CONFLICT_STATUSES:
            continue
        event = str(item.get("event_name") or item.get("event") or "")
        key = str(item.get("param") or item.get("key") or item.get("dim") or "")
        value = str(item.get("value") or "")
        if event and key and value:
            values.add((event, key, value))
    return values


_EVENT_RE = re.compile(r"livesdk_[A-Za-z0-9_]+")


def _waived_events(scope: dict[str, Any]) -> set[str]:
    """out_of_scope / 已 resolve 的 conflicts 里显式豁免掉的事件（支持 `前缀*` 通配）。"""
    waived: set[str] = set()
    for item in (scope.get("out_of_scope") or []) + (scope.get("conflicts") or []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).lower()
        if status and status not in RESOLVED_CONFLICT_STATUSES:
            continue
        if item.get("dim") == "event" and item.get("value"):
            waived.add(str(item["value"]))
        for key in ("event_name", "event"):
            if item.get(key):
                waived.add(str(item[key]))
    return waived


def _is_waived(event: str, waived: set[str]) -> bool:
    return any(
        event == w or (w.endswith("*") and event.startswith(w[:-1])) for w in waived
    )


def _text_from_etd(path: Path) -> str:
    """ETD 原文：etd_sheet_load.py 的 JSON（取去删除线后的 tsv/cells）或纯文本。"""
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() != ".json":
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(data, dict):
        if data.get("tsv"):
            return str(data["tsv"])
        cells = data.get("cells")
        if isinstance(cells, list):
            return "\n".join(
                _norm_text(c.get("text") if isinstance(c, dict) else c) for c in cells
            )
    return raw


def check_etd_events(scope: dict[str, Any], etd_path: Path, errors: list[str]) -> None:
    """测新主路径的第二源：ETD 原文里出现的事件必须都在 scope 里（防 scope 抽漏）。

    GT 只有回归场景才有；ETD 原文是每次都有的，所以这条才是主路径门禁。
    """
    text = _text_from_etd(etd_path)
    etd_events = set(_EVENT_RE.findall(text))
    if not etd_events:
        _err(
            f"ETD 反查失败: `{etd_path}` 里没抽到任何 `livesdk_*` 事件名"
            "（文件路径/字段不对，或 ETD 用了别的事件名前缀 —— 别当成通过）",
            errors,
        )
        return
    waived = _waived_events(scope)
    missing = sorted(
        e
        for e in etd_events - _scope_events(scope)
        if not _is_waived(e, waived)
    )
    if missing:
        _err(
            "ETD 原文有、scope 没有的事件: "
            + ", ".join(f"`{x}`" for x in missing)
            + "（Step 1.5 抽漏了，或确实不验 —— 后者必须写进 out_of_scope/conflicts）",
            errors,
        )


def _is_param_waived(event: str, key: str, resolved: set[tuple[str, str, str]]) -> bool:
    return any(e == event and v == key for e, _, v in resolved)


def check_etd_params(scope: dict[str, Any], payload: dict[str, Any], errors: list[str]) -> bool:
    """按列头解析 ETD，反查 scope 是否抽漏「上报端 / 必传参 / 枚举取值」。

    只反查事件名挡不住「事件对了但枚举只抽了一半」——那正是漏 case 的主要形态。
    返回 False 表示列头没认出来（回退人工核对），调用方需要提示，不能当成通过。
    """
    table = parse_etd_table(payload) if parse_etd_table else None
    if table is None:
        return False

    waived = _waived_events(scope)
    resolved = _resolved_conflict_values(scope)
    scope_by_name = {
        str(ev.get("event_name")): ev
        for ev in scope.get("events") or []
        if isinstance(ev, dict) and ev.get("event_name")
    }
    for ev in table["events"]:
        name = ev["event_name"]
        if _is_waived(name, waived):
            continue
        sev = scope_by_name.get(name)
        if sev is None:
            continue  # check_etd_events 已经报过漏事件

        scope_roles = {str(r).lower() for r in sev.get("roles") or []}
        missing_roles = [r for r in ev["roles"] if r not in scope_roles]
        if missing_roles:
            _err(
                f"上报端不符: `{name}` ETD「用户类型/上报端」={ev['roles']}，"
                f"scope.roles={sorted(scope_roles)}，缺 {missing_roles}"
                "（默认写成主播侧是常见错误：用户侧事件要用观众设备执行和校验）",
                errors,
            )

        scope_params = {
            str(p.get("key")): p for p in sev.get("params") or [] if isinstance(p, dict)
        }
        for p in ev["params"]:
            sp = scope_params.get(p["key"])
            if sp is None:
                if p["required"] and not _is_param_waived(name, p["key"], resolved):
                    _err(
                        f"漏必传参: `{name}`.`{p['key']}` 在 ETD 标了必传，但 scope.params 里没有"
                        "（确不验请写 out_of_scope: {dim:param, event_name, value:<参数名>, reason}）",
                        errors,
                    )
                continue
            if sp.get("coverage_waiver"):
                continue
            have = {str(v) for v in sp.get("values") or []}
            missing_vals = [
                v for v in p["values"] if v not in have and (name, p["key"], v) not in resolved
            ]
            if missing_vals:
                _err(
                    f"漏枚举取值: `{name}`.`{p['key']}` ETD 取值列有 {missing_vals}，"
                    f"scope 只写了 {sorted(have) or '无'}"
                    "（Step 1.5 抽漏 → 补进 scope；确不验 → 写 conflicts/out_of_scope 或给该参数加 coverage_waiver）",
                    errors,
                )
    return True


def check_etd_params_text(scope: dict[str, Any], text: str, errors: list[str]) -> None:
    """G7 Docx/md 形态 ETD 的弱反查（不依赖列头解析）。

    当 parse_etd_table 无法识别列头（ETD 是 Docx/md 而非 Sheet，或格式非标准）时，
    不能直接跳过——那是「肉眼漏抽枚举」的主要入口。这里做启发式检查：

    1. 对每个 enum 参数 key，在 ETD 原文中找该参数名附近的 1~4 行窗口，
       搜索 `xxx` 反引号包裹的英文值（code 字体的枚举值通常会在表格里），
       如果有值完全没在 scope.params[].values 里，报警。
    2. 搜索「用户类型」「上报端」「端」「端上」等角色关键词附近的角色词，
       和 scope 聚合 roles 对比。
    """
    resolved = _resolved_conflict_values(scope)
    scope_by_name = {
        str(ev.get("event_name")): ev
        for ev in scope.get("events") or []
        if isinstance(ev, dict) and ev.get("event_name")
    }

    # 角色弱反查：在「用户类型」「上报端」「端上」这些列关键词附近（最多 200 字窗口）找角色词
    scope_all_roles: set[str] = set()
    for ev in scope.get("events") or []:
        if isinstance(ev, dict):
            for r in ev.get("roles") or []:
                scope_all_roles.add(str(r).lower())
    role_hints: set[str] = set()
    for m in re.finditer(r"(?:用户类型|上报端|端上|客户端|触发端|角色)", text):
        start = m.start()
        end = min(len(text), m.end() + 200)
        window = text[start:end]
        for canon, aliases in ROLE_TAG_MAP.items():
            if canon in ("moderator",) and "管理员" not in window and "主持" not in window:
                continue
            if any(a in window for a in aliases):
                role_hints.add(canon)
    missing_role_hints = role_hints - scope_all_roles
    if missing_role_hints:
        _err(
            f"G7 上报端弱反查（Docx ETD）：ETD 「用户类型/上报端」附近出现 {sorted(missing_role_hints)}，"
            f"但 scope.roles 只有 {sorted(scope_all_roles)}（若该角色不验请写 out_of_scope/conflicts，"
            f"若验则补 scope.roles 和对应观众/用户设备用例）",
            errors,
        )

    # 枚举值弱反查：对每个 enum 参数 key，在全文找 `<key>` 附近的反引号值
    for ev_name, ev in scope_by_name.items():
        for p in ev.get("params") or []:
            if not isinstance(p, dict) or p.get("kind") != "enum":
                continue
            key = str(p.get("key") or "")
            if not key:
                continue
            have_vals = {str(v) for v in p.get("values") or []}
            # 在 ETD 中搜 `key` 或 key 的出现位置
            found_vals: set[str] = set()
            for m in re.finditer(re.escape(f"`{key}`") + r"|" + re.escape(key), text):
                # 取前后 400 字符窗口
                start = max(0, m.start() - 50)
                end = min(len(text), m.end() + 350)
                window = text[start:end]
                # 反引号包裹的英文 snake_case 值
                for vm in re.finditer(r"`([a-z][a-z0-9_]{1,40})`", window):
                    v = vm.group(1)
                    if v == key or v.startswith("livesdk_"):
                        continue
                    # 排除明显不是枚举值的词
                    if v in ("true", "false", "null", "string", "int", "number", "boolean"):
                        continue
                    found_vals.add(v)
            candidate_missing = sorted(
                v for v in (found_vals - have_vals)
                if (ev_name, key, v) not in resolved
                and not v.startswith("is_") and not v.startswith("has_")
                and v not in ("event", "params", "上报", "参数", "必传", "取值", "类型")
            )
            if candidate_missing and len(candidate_missing) <= 6:
                # 太多可能是把全文的变量名都抓进来了，降噪；只在少量疑似值时报
                _err(
                    f"G7 枚举弱反查（Docx ETD）：`{ev_name}`.`{key}` ETD 中 `{key}` 附近出现 "
                    f"反引号值 {candidate_missing}，scope 只写了 {sorted(have_vals) or '无'}"
                    f"（可能漏抽枚举；确不验请写 out_of_scope/conflicts）",
                    errors,
                )


def compare_gt_scope(scope: dict[str, Any], gt_seeds_path: Path) -> dict[str, Any]:
    gt_events, gt_pairs = _gt_extract_from_seeds(gt_seeds_path)
    scope_events = _scope_events(scope)
    scope_pairs = _scope_enum_pairs(scope)
    resolved = _resolved_conflict_values(scope)
    return {
        "gt_seeds_path": str(gt_seeds_path),
        "gt_events": sorted(gt_events),
        "scope_events": sorted(scope_events),
        "gt_events_not_in_scope": sorted(gt_events - scope_events),
        "scope_events_not_in_gt": sorted(scope_events - gt_events),
        "gt_pairs": [list(x) for x in sorted(gt_pairs)],
        "scope_enum_pairs": [list(x) for x in sorted(scope_pairs)],
        "gt_pairs_not_in_scope": [list(x) for x in sorted(gt_pairs - scope_pairs)],
        "scope_pairs_not_in_gt": [list(x) for x in sorted(scope_pairs - gt_pairs)],
        "unresolved_gt_pairs_not_in_scope": [
            list(x) for x in sorted((gt_pairs - scope_pairs) - resolved)
        ],
    }


def check_coverage(text: str, scope: dict[str, Any], errors: list[str]) -> None:
    """防漏（R5/R8/R13 + 隐性规则反向用例）：scope 声明的期望集合必须在产物里出现。

    与 scan_cases（防多写）方向相反：这里查 scope 有、产物没有的缺口。
    """
    blocks = _split_cases(text)
    if not blocks:
        _err("coverage: no case blocks parsed (需 `> 标题` + `**Steps**`，用例间单行 ---)", errors)
        return

    for ev in scope.get("events") or []:
        event = ev.get("event_name")
        if not event:
            continue
        pos_blocks = []
        has_neg = False
        for b in blocks:
            p, n = _polarity(b, event)
            if p:
                pos_blocks.append(b)
            has_neg = has_neg or n

        # R5: 事件全集
        if not pos_blocks:
            _err(f"R5 漏事件: scope 声明的 `{event}` 没有任何正向上报用例", errors)
            continue

        # R13/R8: enum 轴每个取值都要落叶子
        for p in ev.get("params") or []:
            if p.get("kind") != "enum" or p.get("coverage_waiver"):
                continue
            key = p.get("key")
            for val in p.get("values") or []:
                want = (str(key), str(val))
                if not any(want in set(_PAIR_RE.findall(b)) for b in pos_blocks):
                    _err(
                        f"R13 漏枚举叶子: `{event}` 缺 `{key}` = `{val}` 的用例"
                        f"（enum 轴每个取值都要有；确实不适用则给该参数加 coverage_waiver）",
                        errors,
                    )

        # R13+R8: 有效组合也要逐条覆盖。仅检查“每个枚举值出现过”
        # 无法发现 `position_before=down` 与 `is_button=0` 被错误拼在一起
        # 这类组合错位，因此 scope 可声明 expected_combinations。
        for combo in ev.get("expected_combinations") or []:
            if not isinstance(combo, dict) or not combo:
                continue
            combo_pairs = _combo_items(combo)
            if not any(combo_pairs <= _pairs_in_block(b) for b in pos_blocks):
                pretty = ", ".join(f"`{k}` = `{v}`" for k, v in combo_pairs)
                _err(
                    f"组合矩阵 漏组合: `{event}` 缺 {pretty} 的用例"
                    "（scope.expected_combinations 声明的有效组合必须整体出现；"
                    "不能只让单个枚举值分别出现）",
                    errors,
                )

        # 隐性规则：反向用例（什么情况不该报）。形态按 change_type 分流
        if str(ev.get("change_type")) == "param_added":
            for key in [
                str(p.get("key"))
                for p in ev.get("params") or []
                if isinstance(p, dict) and p.get("added")
            ]:
                absent_re = re.compile(
                    r"(?:不上报|不带|不含|不携带|未上报)\s*`" + re.escape(key) + r"`"
                    r"|`" + re.escape(key) + r"`\s*(?:不上报|不下发|不携带|无值|缺省)"
                )
                if not any(absent_re.search(b) and _polarity(b, event)[0] for b in blocks):
                    _err(
                        f"反例形态错: `{event}` 是已有埋点新增参数（change_type=param_added），"
                        f"缺「旧场景仍上报但不带 `{key}`」的反例。"
                        f"写法：上报 `{event}` 埋点；不上报 `{key}`",
                        errors,
                    )
            no_emit_re = re.compile(r"不上报\s*`" + re.escape(event) + r"`")
            bad = [b for b in blocks if no_emit_re.search(b)]
            if bad and not ev.get("no_emit_negative"):
                title = re.search(r"^> (.+)$", bad[0], re.M)
                _err(
                    f"反例形态错: `{event}` 是已有埋点新增参数，新场景只改参数不改上报时机，"
                    f"不能用「不上报 `{event}`」当反例（应改成仍上报但不带新增参数）；"
                    f"确有整事件不上报的场景请在 scope 该事件写 no_emit_negative 说明理由。"
                    f"例：{(title.group(1) if title else '?')[:60]}",
                    errors,
                )
        elif not has_neg and not ev.get("negatives_waiver"):
            _err(
                f"隐性规则 漏反向用例: `{event}` 没有任何「不上报」用例"
                f"（拖动未生效/条件不满足/重复操作等；确无反向场景请在 scope 该事件加 negatives_waiver 说明理由）",
                errors,
            )


_NEG_EMIT_RE = re.compile(r"(?:不|未)\s*(?:应|会|再)?\s*(?:重复)?\s*上报")
_MOMENT_WAIVER_RE = re.compile(r"多时机例外\s*[:：]\s*\S")
_STEP_NO_RE = re.compile(r"^\s*(\d+)[.、]\s")
# show / click / mic … 同一事件靠它区分上报时机，`banner_action_type` 等变体同理
_ACTION_TYPE_RE = re.compile(r"`(\w*action_type)`\s*=\s*`([^`]+)`")


def _assert_atoms(line: str, events: set[str]) -> tuple[set[str], set[tuple[str, str]]]:
    """一行断言里的正向埋点断言原子：(事件集合, {(action_type 参数, 取值)})。

    按分句判极性，`上报 A；本次不上报 B` 里的 B 不算正向；负向分句里的 action_type
    也不计入时机（反向断言不是一个独立时机）。
    """
    evs: set[str] = set()
    acts: set[tuple[str, str]] = set()
    for clause in re.split(r"[；;。]", line):
        if _NEG_EMIT_RE.search(clause):
            continue
        acts |= {(k, v) for k, v in _ACTION_TYPE_RE.findall(clause)}
        # 不要求出现「上报」二字：`data | \`event\`；\`action_type\`=\`show\`` 也是断言
        evs |= {ev for ev in events if ev in clause}
    return evs, acts


def check_assert_moments(text: str, scope: dict[str, Any], errors: list[str]) -> None:
    """R18/G11：一条用例只验一个埋点断言时机。

    「时机」由 (事件, action_type 取值) 决定 —— 同一个 `livesdk_xxx_panel` 的
    `action_type=show` 与 `=mic` 是两次不同的上报，合在一条用例里（哪怕挂在同一个
    操作步骤下）执行器也分不清哪条断言对应哪一次操作，早报/漏报/串报全验不出来。

    前置操作只能是无断言的导航步骤，被吃掉的断言另开一条。基线+增量（去重/频控/
    生命周期）或同一刻多事件齐报属例外，须在该用例 Notes 写 `- 多时机例外: <理由>`。
    """
    events = _scope_events(scope)
    if not events:
        return
    merged: list[str] = []
    cross_event: list[str] = []
    merged_actions: list[str] = []
    for block in _split_cases(text):
        if _MOMENT_WAIVER_RE.search(block):
            continue
        m_title = re.search(r"^> (.+)$", block, re.M)
        title = (m_title.group(1) if m_title else "?")[:60]
        steps = block.split("**Steps**", 1)[1].split("**Assert**")[0]

        moments: dict[str, set[str]] = {}
        case_events: set[str] = set()
        case_actions: set[tuple[str, str]] = set()
        step_no: str | None = None
        for idx, line in enumerate(steps.splitlines()):
            m_no = _STEP_NO_RE.match(line)
            if m_no:
                step_no = m_no.group(1)
            if "Assert" not in line or "data" not in line:
                continue
            evs, acts = _assert_atoms(line, events)
            case_events |= evs
            case_actions |= acts
            if evs:
                # 没写步骤序号时退化成一行一时机，避免用无编号步骤绕过门禁
                label = f"第{step_no}步" if step_no else f"第{idx + 1}行"
                moments.setdefault(label, set()).update(evs)

        m_tail = re.search(r"\*\*Assert\*\*:(.*?)(?=\n\*\*|\Z)", block, re.S)
        if m_tail:
            for line in m_tail.group(1).splitlines():
                if "data" in line:
                    evs, acts = _assert_atoms(line, events)
                    case_events |= evs
                    case_actions |= acts

        if len(moments) > 1:
            detail = "；".join(
                f"{no} " + "/".join(f"`{e}`" for e in sorted(evs))
                for no, evs in sorted(
                    moments.items(), key=lambda kv: int(re.sub(r"\D", "", kv[0]) or 0)
                )
            )
            merged.append(f"「{title}」{detail}")
        elif len(case_events) > 1:
            cross_event.append(f"「{title}」" + "、".join(f"`{e}`" for e in sorted(case_events)))
        elif len(case_actions) > 1:
            merged_actions.append(
                f"「{title}」" + "、".join(f"`{k}`=`{v}`" for k, v in sorted(case_actions))
            )

    buckets = (
        ("多操作合并（断言分散在多个步骤）", merged),
        ("一条用例跨多个事件", cross_event),
        ("一条用例合并多个上报时机（同事件不同 action_type）", merged_actions),
    )
    for label, hits in buckets:
        if not hits:
            continue
        preview = "；".join(hits[:6])
        more = "" if len(hits) <= 6 else f" 等共 {len(hits)} 条"
        _err(
            f"R18/G11 {label}（{len(hits)} 条）: {preview}{more}。"
            "修法：一条用例只验一个触发时机（一个事件 + 一个 action_type）—— "
            "前置操作降级为不带断言的导航步骤，被去掉的那个断言另开一条用例（曝光一条、点击一条）；"
            "确需基线+增量（去重/频控/生命周期）或同一刻齐报时，在该用例 Notes 写 `- 多时机例外: <理由>`",
            errors,
        )


def _extract_case_roles(text: str) -> dict[str, set[str]]:
    """从每个用例块中提取出现的设备标签对应的角色集合。

    返回 {title: set(role_label)}，role_label 来自 `设备X（YYY）：` 中的括号内文本。
    """
    result: dict[str, set[str]] = {}
    for block in _split_cases(text):
        m_title = re.search(r"^> (.+)$", block, re.M)
        title = m_title.group(1) if m_title else "?"
        roles: set[str] = set()
        for _d, role_label in DEVICE_PREFIX_RE.findall(block):
            roles.add(role_label.strip())
        # 兜底：旧格式已经在 scan_cases 报了；这里只看新格式标签
        result[title] = roles
    return result


def _role_label_matches(role_label: str, scope_role: str) -> bool:
    """判断用例中出现的角色标签文本是否匹配 scope 中的标准角色 key。"""
    label = role_label.strip()
    aliases = ROLE_TAG_MAP.get(scope_role.lower(), (scope_role,))
    return any(alias in label for alias in aliases)


def check_role_device_consistency(
    text: str, scope: dict[str, Any], errors: list[str]
) -> None:
    """G5：scope.roles 声明的角色集合，必须和用例里实际出现的设备角色一致。

    - scope 有 viewer 角色但全文件找不到「观众/用户」设备 → 报默认主播侧错误。
    - scope 只有 anchor 但用例里出现观众设备 → 报多写。
    - 多角色场景下 Assert 行也要带设备前缀。
    """
    case_roles = _extract_case_roles(text)
    if not case_roles:
        return

    # 汇总 scope 里所有角色
    scope_roles: set[str] = set()
    role_event_map: dict[str, list[str]] = {}
    for ev in scope.get("events") or []:
        if not isinstance(ev, dict):
            continue
        ev_name = str(ev.get("event_name") or "")
        for r in ev.get("roles") or []:
            rl = str(r).lower()
            scope_roles.add(rl)
            role_event_map.setdefault(rl, []).append(ev_name)
    if not scope_roles:
        return

    # 汇总全文出现的角色标签
    all_case_role_labels: set[str] = set()
    for roles in case_roles.values():
        all_case_role_labels.update(roles)

    # 检查 scope 需要的角色是否都在用例里出现
    for sr in sorted(scope_roles):
        matched = any(_role_label_matches(rl, sr) for rl in all_case_role_labels)
        if not matched:
            evs = role_event_map.get(sr, [])
            label_hint = "/".join(ROLE_TAG_MAP.get(sr, (sr,)))
            _err(
                f"R17/G5: scope 声明了 `{sr}` 角色（事件 {evs[:3]}），但用例里找不到「{label_hint}」角色的设备步骤/断言"
                f"（常见错误：默认所有操作都写在主播设备上，用户侧/观众侧事件必须用观众设备执行并断言）",
                errors,
            )

    # 多角色场景下：断言行也必须带设备前缀（否则不知道哪个端报的）
    if len(scope_roles) >= 2:
        assertion_lines_without_device: list[str] = []
        for block in _split_cases(text):
            for line in block.splitlines():
                if "上报" not in line and "不上报" not in line:
                    continue
                if line.lstrip().startswith("-") or "Assert" in line or "Expected" in line:
                    if not DEVICE_PREFIX_RE.search(line):
                        # 排除文件头/分组标题类行（不带「设备」关键词但含「上报」的标题行）
                        if re.match(r"^> ", line) or re.match(r"^#", line):
                            continue
                        assertion_lines_without_device.append(line.strip()[:120])
        if assertion_lines_without_device:
            _err(
                f"R11/G5: 多角色场景下有 {len(assertion_lines_without_device)} 条断言未带设备前缀"
                f"（必须以「设备X（角色）：」开头，否则无法区分哪个端上报）。例：{assertion_lines_without_device[0]}",
                errors,
            )


def _scope_enum_triples(scope: dict[str, Any]) -> set[tuple[str, str, str]]:
    triples: set[tuple[str, str, str]] = set()
    for ev in scope.get("events") or []:
        if not isinstance(ev, dict):
            continue
        event = str(ev.get("event_name") or "")
        if not event:
            continue
        for p in ev.get("params") or []:
            if not isinstance(p, dict) or p.get("kind") != "enum":
                continue
            key = str(p.get("key") or "")
            if not key:
                continue
            for val in p.get("values") or []:
                triples.add((event, key, str(val)))
    return triples


def check_draft_not_pruned(
    scope: dict[str, Any], draft: dict[str, Any], errors: list[str]
) -> None:
    """G8：etd_scope.draft.json（etd_sheet_load.py --emit-scope-draft 草稿）里抽出来的
    event/param/enum 三元组，终稿 scope 不得删减。

    删了就等于 agent 在肉眼复核时偷偷丢了几个取值/参数/事件；如果真的不验，必须显式写进
    out_of_scope 或 conflicts 带理由。
    """
    draft_triples = _scope_enum_triples(draft)
    final_triples = _scope_enum_triples(scope)
    resolved = _resolved_conflict_values(scope)
    waived = _waived_events(scope)

    # draft 事件集 vs final 事件集
    draft_events = {
        str(ev.get("event_name"))
        for ev in draft.get("events") or []
        if isinstance(ev, dict) and ev.get("event_name")
    }
    final_events = _scope_events(scope)
    missing_events = sorted(
        e for e in draft_events - final_events
        if not _is_waived(e, waived)
    )
    if missing_events:
        _err(
            f"G8 草稿事件被删减: draft 有 {len(missing_events)} 个事件在终稿里没有: "
            + ", ".join(f"`{e}`" for e in missing_events)
            + "（草稿里 ETD 抽到的事件不能直接删；若不验请写 out_of_scope/conflicts 带 reason）",
            errors,
        )

    # draft 枚举三元组 vs final
    missing_triples = sorted(
        t for t in (draft_triples - final_triples)
        if not _is_waived(t[0], waived) and t not in resolved
    )
    if missing_triples:
        preview = ", ".join(
            f"`{e}`.`{k}`=`{v}`" for e, k, v in missing_triples[:8]
        )
        more = "" if len(missing_triples) <= 8 else f" 等共 {len(missing_triples)} 项"
        _err(
            f"G8 草稿枚举/参数被删减: draft 有但终稿没有的 event/param/value 共 {len(missing_triples)} 项"
            f"（{preview}{more}）。etd_sheet_load.py 草稿里抽到的取值禁止手动删除；"
            f"若不验请写 out_of_scope/conflicts 带 reason。",
            errors,
        )


def self_check() -> int:
    good = {
        "etd_url": "https://example.com/etd",
        "authority": "user_etd_body",
        "events": [
            {
                "event_name": "livesdk_multi_stage_reaction_select",
                "entrances": ["self_spot_panel"],
                "roles": ["anchor", "guest"],
                "change_type": "new_event",
                "params": [
                    {"key": "action_type", "kind": "enum", "values": ["show", "click"]},
                    {"key": "stage_reaction_id", "kind": "opaque"},
                    {
                        "key": "stage_reaction_show_ucnt",
                        "kind": "semantic",
                        "meaning": "可见人数不含主播",
                        "example_expect": "1+1 => 1",
                    },
                ],
                "show_policy": "dedup",
                "click_policy": "per_click",
            }
        ],
        "out_of_scope": [{"dim": "entrance", "value": "bottom_linkmic", "reason": "not in etd"}],
        "test_kit": {
            "source_doc": "https://example.com/release",
            "packages": {"ios": "bits://ios", "android": "bits://android"},
            "env": "ppe_unified_im",
            "libra_flights": ["72057031"],
            "accounts": [{"role": "anchor", "id": "A-HOST"}],
            "missing": [],
        },
    }
    errors: list[str] = []
    validate_scope(good, errors)
    if errors:
        print("self-check FAIL on good scope:", errors)
        return 1

    # R6：test_kit 缺失/空字段必须报，除非显式登记 missing
    errors = []
    validate_test_kit(None, errors)
    if not errors:
        print("self-check FAIL: missing test_kit must fail")
        return 1
    # G1: 缺 source_doc 必须报
    errors = []
    validate_test_kit({"env": "", "packages": {}, "libra_flights": [], "accounts": []}, errors)
    joined = " ".join(errors)
    if "source_doc" not in joined:
        print("self-check FAIL: missing source_doc must fail, got", errors)
        return 1
    # G1: 所有核心字段全空且 missing 也空 → 必须报"全空"错误
    errors = []
    validate_test_kit({"source_doc": "x", "env": "", "packages": {}, "libra_flights": [], "accounts": [], "missing": []}, errors)
    joined = " ".join(errors)
    if "所有核心字段" not in joined:
        print("self-check FAIL: all-empty test_kit with no missing[] must fail, got", errors)
        return 1
    errors = []
    validate_test_kit({"env": "ppe_x", "packages": {}, "libra_flights": [], "accounts": []}, errors)
    # source_doc missing（1 条）+ 3 empty fields 合报（1 条）= 2 条；env 非空所以不触发"全空"
    if len(errors) != 2:
        print("self-check FAIL: expected source_doc+3-empty errors (2), got", len(errors), errors)
        return 1
    errors = []
    validate_test_kit(
        {
            "source_doc": "https://example.com/release",
            "env": "ppe_x",
            "packages": {"ios": "x"},
            "libra_flights": ["1"],
            "accounts": [],
            "missing": [{"field": "accounts", "reason": "待 RD 补", "gap_id": "G-REL-001"}],
        },
        errors,
    )
    if errors:
        print("self-check FAIL: declared-missing field should pass:", errors)
        return 1

    # P0：env / flight 必须出现在每条用例 Precondition，否则 bits 上看不到测试物料
    kit_scope = {"test_kit": {"source_doc": "x", "env": "ppe_unified_im", "libra_flights": ["72057031"]}}
    naked = "---\n> 点击 CTA\n\n**Precondition**:\n- assume | 冷启动\n\n**Steps**:\n1. 点。\n---\n"
    errors = []
    check_test_kit_in_cases(naked, kit_scope, errors)
    if len(errors) != 2:
        print("self-check FAIL: expected env+flight gaps, got", errors)
        return 1
    # G3：散文写法（`环境：xxx`）必须被拦截
    prose = (
        "---\n> 点击 CTA\n\n**Precondition**:\n- 环境：ppe_unified_im\n"
        "- 已加实验 72057031\n\n**Steps**:\n1. 点。\n---\n"
    )
    errors = []
    check_test_kit_in_cases(prose, kit_scope, errors)
    if not any("格式不规范" in e for e in errors):
        print("self-check FAIL: prose-format precondition should fail, got", errors)
        return 1
    dressed = (
        "---\n> 点击 CTA\n\n**Precondition**:\n- mock | env=ppe_unified_im（来源：提测文档）\n"
        "- mock | 账号已加实验 libra flight/72057031\n\n**Steps**:\n1. 点。\n---\n"
    )
    errors = []
    check_test_kit_in_cases(dressed, kit_scope, errors)
    if errors:
        print("self-check FAIL on dressed precondition:", errors)
        return 1

    bad_case = "> 点击点赞表情\n> 点击鼓掌表情\n> 点击大笑表情\n`stage_reaction_show_ucnt` 有值\n不去重失败\n"
    errors = []
    scan_cases(bad_case, good, errors)
    if len(errors) < 3:
        print("self-check FAIL: expected anti-pattern hits (R13+R14+R15), got", errors)
        return 1

    # coverage gate (防漏)：用提词器回归案例做样本 —— 缺事件 / 缺枚举叶子 / 缺反向
    cov_scope = {
        "etd_url": "https://example.com/etd",
        "authority": "user_etd_body",
        "events": [
            {
                "event_name": "cues_msg_click",
                "entrances": ["cues"],
                "roles": ["anchor"],
                "params": [{"key": "is_button", "kind": "enum", "values": [0, 1]}],
            },
            {
                "event_name": "cues_msg_change_position",
                "entrances": ["cues"],
                "roles": ["anchor"],
                "params": [
                    {"key": "position_before", "kind": "enum", "values": ["up", "down"]},
                    {"key": "position_after", "kind": "enum", "values": ["up", "down"]},
                    {"key": "is_button", "kind": "enum", "values": [1]},
                ],
                "expected_combinations": [
                    {"position_before": "up", "position_after": "down", "is_button": 1},
                    {"position_before": "down", "position_after": "up", "is_button": 1},
                ],
            },
        ],
    }
    bad_cov = (
        "---\n> 点击 CTA\n**Steps**:\n1. 点。\n"
        "    - Assert: data | 上报 `cues_msg_click` 埋点；`is_button` = `1`。\n---\n"
    )
    errors = []
    check_coverage(bad_cov, cov_scope, errors)
    joined = " ".join(errors)
    if not ("漏事件" in joined and "漏枚举叶子" in joined and "漏反向用例" in joined):
        print("self-check FAIL: coverage gate missed under-coverage:", errors)
        return 1

    bad_combo_cov = (
        "> 错误组合\n**Steps**:\n1. 拖。\n"
        "    - Assert: data | 上报 `cues_msg_change_position` 埋点；`position_before` = `up`；`position_after` = `down`；`is_button` = `0`。\n---\n"
        "> 拖动未生效不上报\n**Steps**:\n1. 拖。\n"
        "    - Assert: data | 不上报 `cues_msg_change_position` 埋点。\n---\n"
    )
    errors = []
    check_coverage(bad_combo_cov, {"events": [cov_scope["events"][1]]}, errors)
    if not any("漏组合" in e for e in errors):
        print("self-check FAIL: expected combination gap, got", errors)
        return 1

    good_cov = bad_cov + (
        "> 无按钮点击\n**Steps**:\n1. 点。\n"
        "    - Assert: data | 上报 `cues_msg_click` 埋点；`is_button` = `0`。\n---\n"
        "> 拖动未生效不上报\n**Steps**:\n1. 拖。\n"
        "    - Assert: data | 不上报 `cues_msg_change_position` 埋点。\n---\n"
        "> 拖动生效上报\n**Steps**:\n1. 拖。\n"
        "    - Assert: data | 上报 `cues_msg_change_position` 埋点；`position_before` = `up`；`position_after` = `down`；`is_button` = `1`。\n---\n"
        "> 反向拖动生效上报\n**Steps**:\n1. 拖。\n"
        "    - Assert: data | 上报 `cues_msg_change_position` 埋点；`position_before` = `down`；`position_after` = `up`；`is_button` = `1`。\n---\n"
    )
    errors = []
    check_coverage(good_cov, cov_scope, errors)
    if len(errors) != 1 or "cues_msg_click" not in errors[0] or "漏反向用例" not in errors[0]:
        print("self-check FAIL: expected only click-negative gap, got", errors)
        return 1

    cov_scope["events"][0]["negatives_waiver"] = "ETD 无不上报场景"
    errors = []
    check_coverage(good_cov, cov_scope, errors)
    if errors:
        print("self-check FAIL on fully covered cases:", errors)
        return 1

    # 反例形态：已有埋点新增参数（param_added）不能拿「事件不上报」当反例
    pa_scope = {
        "events": [
            {
                "event_name": "livesdk_room_enter",
                "entrances": ["room"],
                "roles": ["viewer"],
                "change_type": "param_added",
                "params": [
                    {"key": "enter_from", "kind": "opaque"},
                    {"key": "guide_type", "kind": "opaque", "added": True},
                ],
            }
        ]
    }
    positive_case = (
        "---\n> 新场景上报新增参数\n**Steps**:\n1. 进房。\n"
        "    - Assert: data | 上报 `livesdk_room_enter` 埋点；`guide_type` 有值。\n---\n"
    )
    errors = []
    check_coverage(
        positive_case + "> 对照组不上报\n**Steps**:\n1. 进房。\n"
        "    - Assert: data | 不上报 `livesdk_room_enter` 埋点。\n---\n",
        pa_scope,
        errors,
    )
    joined = " ".join(errors)
    if "反例形态错" not in joined or "guide_type" not in joined:
        print("self-check FAIL: param_added wrong negative must fail, got", errors)
        return 1

    errors = []
    check_coverage(
        positive_case + "> 旧场景仍上报但不带新增参数\n**Steps**:\n1. 进房。\n"
        "    - Assert: data | 上报 `livesdk_room_enter` 埋点；不上报 `guide_type`。\n---\n",
        pa_scope,
        errors,
    )
    if errors:
        print("self-check FAIL: param_added correct negative should pass, got", errors)
        return 1

    # change_type 必填；param_added 必须标出新增参数
    no_change_type = json.loads(json.dumps(good))
    no_change_type["events"][0].pop("change_type")
    errors = []
    validate_scope(no_change_type, errors)
    if not any("change_type" in e for e in errors):
        print("self-check FAIL: missing change_type must fail")
        return 1

    unmarked = json.loads(json.dumps(good))
    unmarked["events"][0]["change_type"] = "param_added"
    errors = []
    validate_scope(unmarked, errors)
    if not any("params[].added" in e for e in errors):
        print("self-check FAIL: param_added without added params must fail")
        return 1

    # R18/G11：多操作合并（等曝光校验 show + 点击校验 click 塞一条）必须报
    moment_scope = {
        "events": [
            {"event_name": "cues_msg_show"},
            {"event_name": "cues_msg_click"},
        ]
    }
    merged = (
        "---\n> 点击 CTA 上报 click\n**Steps**:\n"
        "1. 开播进直播间。\n"
        "2. 等提词器展现。\n"
        "    - Assert: data | 上报 `cues_msg_show` 埋点；`is_button` = `1`。\n"
        "3. 点击 CTA。\n"
        "    - Assert: data | 上报 `cues_msg_click` 埋点；`action_type` = `click_cta`。\n\n"
        "**Assert**:\n- data | 上报 `cues_msg_click` 埋点。\n---\n"
    )
    errors = []
    check_assert_moments(merged, moment_scope, errors)
    if len(errors) != 1 or "多操作合并" not in errors[0]:
        print("self-check FAIL: merged multi-step asserts must fail, got", errors)
        return 1
    # 例外声明放行
    errors = []
    check_assert_moments(
        merged.replace("**Assert**:", "**Notes**:\n- 多时机例外: 去重基线+增量\n\n**Assert**:"),
        moment_scope,
        errors,
    )
    if errors:
        print("self-check FAIL: declared 多时机例外 should pass, got", errors)
        return 1
    # 拆开后：前置只导航不断言 → 放行；且 `本次不上报 X` 不算跨事件
    split_ok = (
        "---\n> 提词器展现上报 show\n**Steps**:\n"
        "1. 开播并等提词器展现。\n"
        "    - Assert: data | 上报 `cues_msg_show` 埋点；`is_button` = `1`。\n"
        "**Assert**:\n- data | 上报 `cues_msg_show` 埋点。\n"
        "---\n> 点击 CTA 上报 click\n**Steps**:\n"
        "1. 开播并等提词器展现（不校验埋点）。\n"
        "2. 点击 CTA。\n"
        "    - Assert: data | 上报 `cues_msg_click` 埋点；本次不上报 `cues_msg_show` 埋点。\n"
        "**Assert**:\n- data | 上报 `cues_msg_click` 埋点。\n---\n"
    )
    errors = []
    check_assert_moments(split_ok, moment_scope, errors)
    if errors:
        print("self-check FAIL: split cases should pass, got", errors)
        return 1
    # 断言全塞在 **Assert** 里横跨多事件，也要拦
    tail_merged = (
        "---\n> 双端一致性\n**Steps**:\n1. 走完展现与点击。\n\n"
        "**Assert**:\n- data | 上报 `cues_msg_show` 埋点。\n- data | 上报 `cues_msg_click` 埋点。\n---\n"
    )
    errors = []
    check_assert_moments(tail_merged, moment_scope, errors)
    if len(errors) != 1 or "跨多个事件" not in errors[0]:
        print("self-check FAIL: multi-event final Assert must fail, got", errors)
        return 1

    # 同一事件靠 action_type 区分时机：show 与 mic 合在一条（哪怕挂在同一个步骤下）也要拦
    one_event = {"events": [{"event_name": "livesdk_panel"}]}
    for name, body in (
        (
            "同步多行",
            "1. 打开面板并点麦克风。\n"
            "    - Assert: data | 上报 `livesdk_panel` 埋点；`action_type` = `show`。\n"
            "    - Assert: data | 上报 `livesdk_panel` 埋点；`action_type` = `mic`。\n",
        ),
        (
            "同行合并",
            "1. 打开面板并点麦克风。\n"
            "    - Assert: data | 上报 `livesdk_panel` 埋点 `action_type` = `show` 与 `action_type` = `mic`。\n",
        ),
        (
            "无编号步骤",
            "- 打开面板。\n    - Assert: data | 上报 `livesdk_panel` 埋点；`action_type` = `show`。\n"
            "- 点麦克风。\n    - Assert: data | 上报 `livesdk_panel` 埋点；`action_type` = `mic`。\n",
        ),
        (
            "banner_action_type 变体",
            "1. 看到 banner 后点击。\n"
            "    - Assert: data | 上报 `livesdk_panel` 埋点；`banner_action_type` = `show`；"
            "随后 `banner_action_type` = `click`。\n",
        ),
    ):
        errors = []
        check_assert_moments(f"---\n> {name}\n**Steps**:\n{body}---\n", one_event, errors)
        if not errors:
            print(f"self-check FAIL: 单步合并多个上报时机（{name}）must fail")
            return 1

    # 不误伤：顶层 Assert 复述（不带 action_type）+ 反向断言里的 action_type
    single_ok = (
        "---\n> 点麦克风\n**Steps**:\n1. 打开面板（本条不校验展现埋点）。\n2. 点麦克风。\n"
        "    - Assert: data | 上报 `livesdk_panel` 埋点；`action_type` = `mic`；"
        "本次不上报 `livesdk_panel` 埋点的 `action_type` = `show`。\n\n"
        "**Assert**:\n- data | 上报 `livesdk_panel` 埋点。\n---\n"
    )
    errors = []
    check_assert_moments(single_ok, one_event, errors)
    if errors:
        print("self-check FAIL: single-moment case should pass, got", errors)
        return 1

    # ETD 原文反查（测新主路径）：ETD 有、scope 没有的事件必须报
    etd_scope = {
        "events": [{"event_name": "livesdk_cues_msg_show"}],
        "out_of_scope": [{"dim": "event", "value": "livesdk_cues_switch_*", "reason": "非本需求"}],
    }
    with tempfile.TemporaryDirectory() as td:
        etd_txt = Path(td) / "etd.json"
        etd_txt.write_text(
            json.dumps(
                {
                    "tsv": "livesdk_cues_msg_show\tshow\n"
                    "livesdk_cues_msg_change_position\tdrag\n"
                    "livesdk_cues_switch_on\tswitch\n"
                }
            ),
            encoding="utf-8",
        )
        errors = []
        check_etd_events(etd_scope, etd_txt, errors)
        if len(errors) != 1 or "change_position" not in errors[0]:
            print("self-check FAIL: etd back-check", errors)
            return 1
        if "cues_switch_on" in errors[0]:
            print("self-check FAIL: out_of_scope 通配未生效", errors)
            return 1

        empty_txt = Path(td) / "empty.txt"
        empty_txt.write_text("没有任何事件名", encoding="utf-8")
        errors = []
        check_etd_events(etd_scope, empty_txt, errors)
        if not errors or "没抽到" not in errors[0]:
            print("self-check FAIL: empty ETD must not pass silently", errors)
            return 1

    # ETD 结构化反查：上报端写反 / 枚举只抽一半 / 漏必传参，事件名反查都发现不了
    etd_cells = [
        {"addr": f"{chr(65 + c)}{r + 1}", "text": v}
        for r, row in enumerate(
            [
                ["event", "用户类型", "param名称", "是否必传", "param取值"],
                ["livesdk_cues_msg_click", "用户侧", "action_type", "TRUE",
                 "click_cta：点击cta、fold：收起、slide_up：上滑"],
                ["", "", "msg_id", "TRUE", "消息 id"],
            ]
        )
        for c, v in enumerate(row)
    ]
    half_scope = {
        "events": [
            {
                "event_name": "livesdk_cues_msg_click",
                "roles": ["anchor"],
                "params": [{"key": "action_type", "kind": "enum", "values": ["click_cta"]}],
            }
        ]
    }
    errors = []
    if not check_etd_params(half_scope, {"cells": etd_cells}, errors):
        print("self-check FAIL: header-driven ETD parse should succeed")
        return 1
    joined = " ".join(errors)
    if not ("上报端不符" in joined and "漏枚举取值" in joined and "漏必传参" in joined):
        print("self-check FAIL: etd param back-check missed gaps:", errors)
        return 1

    full_scope = {
        "events": [
            {
                "event_name": "livesdk_cues_msg_click",
                "roles": ["viewer"],
                "params": [
                    {"key": "action_type", "kind": "enum",
                     "values": ["click_cta", "fold", "slide_up"]},
                    {"key": "msg_id", "kind": "opaque"},
                ],
            }
        ]
    }
    errors = []
    check_etd_params(full_scope, {"cells": etd_cells}, errors)
    if errors:
        print("self-check FAIL on fully-extracted scope:", errors)
        return 1

    # 列头认不出 → 返回 False（调用方降级提示），不能静默判过
    errors = []
    if check_etd_params(full_scope, {"cells": [{"addr": "A1", "text": "随手写的"}]}, errors):
        print("self-check FAIL: unrecognized header must report fallback")
        return 1

    # G4：旧格式 TT-主播设备 / TT-观众设备 必须拦截
    legacy_device = (
        "---\n> 旧格式点击\n**Steps**:\n1. TT-主播设备-1 点按钮。\n"
        "    - Assert: data | TT-主播设备-1 上报 `livesdk_cues_msg_click` 埋点。\n---\n"
    )
    errors = []
    scan_cases(legacy_device, full_scope, errors)
    if not any("旧格式设备前缀" in e for e in errors):
        print("self-check FAIL: legacy TT-主播设备 prefix must fail, got", errors)
        return 1

    # G6：或/、合并枚举必须拦截
    or_merge = (
        "---\n> 合并枚举\n**Steps**:\n1. 设备A（主播）：点。\n"
        "    - Assert: data | 设备A（主播）：上报 `livesdk_cues_msg_click` 埋点；`action_type` = `click_cta` 或 `fold`。\n---\n"
    )
    errors = []
    scan_cases(or_merge, full_scope, errors)
    if not any("或/、合并枚举" in e for e in errors):
        print("self-check FAIL: OR-merge enum must fail, got", errors)
        return 1

    # G5：scope 声明 viewer 角色但用例里全是主播设备 → 必须报
    viewer_scope = {
        "etd_url": "https://example.com/etd",
        "authority": "user_etd_body",
        "events": [
            {
                "event_name": "livesdk_viewer_click",
                "entrances": ["live"],
                "roles": ["anchor", "viewer"],
                "params": [{"key": "action", "kind": "enum", "values": ["tap"]}],
            }
        ],
        "test_kit": {"source_doc": "x", "env": "ppe", "libra_flights": [], "packages": {"ios": "x"}, "accounts": []},
    }
    anchor_only = (
        "---\n> 主播操作\n**Precondition**:\n- mock | env=ppe\n"
        "**Steps**:\n1. 设备A（主播）：点。\n"
        "    - Assert: data | 设备A（主播）：上报 `livesdk_viewer_click` 埋点；`action` = `tap`。\n---\n"
    )
    errors = []
    scan_cases(anchor_only, viewer_scope, errors)
    check_role_device_consistency(anchor_only, viewer_scope, errors)
    check_test_kit_in_cases(anchor_only, viewer_scope, errors)
    if not any("找不到「观众" in e or "找不到「用户" in e for e in errors):
        print("self-check FAIL: viewer role missing in cases must fail, got", errors)
        return 1

    # G5 多角色场景：Assert 不带设备前缀必须拦截
    no_prefix_assert = (
        "---\n> 双端操作\n**Precondition**:\n- mock | env=ppe\n"
        "**Steps**:\n1. 设备A（主播）：点。\n2. 设备B（观众）：看。\n"
        "    - Assert: data | 上报 `livesdk_viewer_click` 埋点；`action` = `tap`。\n---\n"
    )
    errors = []
    check_role_device_consistency(no_prefix_assert, viewer_scope, errors)
    if not any("断言未带设备前缀" in e for e in errors):
        print("self-check FAIL: multi-role assert without device prefix must fail, got", errors)
        return 1

    # G5 正确场景：双角色都覆盖，Assert 带前缀 → 通过
    dual_role_ok = (
        "---\n> 双端操作\n**Precondition**:\n- mock | env=ppe\n"
        "**Steps**:\n1. 设备A（主播）：开播。\n2. 设备B（观众）：进入直播间。\n"
        "    - Assert: data | 设备B（观众）：上报 `livesdk_viewer_click` 埋点；`action` = `tap`。\n"
        "    - Assert: data | 设备A（主播）：上报 `livesdk_viewer_click` 埋点；`action` = `tap`。\n---\n"
    )
    errors = []
    check_role_device_consistency(dual_role_ok, viewer_scope, errors)
    if errors:
        print("self-check FAIL on dual-role OK case:", errors)
        return 1

    # G8：draft 有、final 没有 = 删减拦截
    draft_scope = {
        "etd_url": "x",
        "authority": "user_etd_body",
        "events": [
            {
                "event_name": "livesdk_demo",
                "entrances": ["home"],
                "roles": ["anchor"],
                "params": [
                    {"key": "a", "kind": "enum", "values": ["1", "2", "3"]},
                    {"key": "b", "kind": "enum", "values": ["x", "y"]},
                ],
            },
            {
                "event_name": "livesdk_demo_extra",
                "entrances": ["home"],
                "roles": ["anchor"],
                "params": [{"key": "c", "kind": "enum", "values": ["z"]}],
            },
        ],
    }
    pruned_scope = {
        "etd_url": "x",
        "authority": "user_etd_body",
        "events": [
            {
                "event_name": "livesdk_demo",
                "entrances": ["home"],
                "roles": ["anchor"],
                "params": [
                    {"key": "a", "kind": "enum", "values": ["1"]},
                    {"key": "b", "kind": "enum", "values": ["x", "y"]},
                ],
            }
        ],
    }
    errors = []
    check_draft_not_pruned(pruned_scope, draft_scope, errors)
    joined = " ".join(errors)
    if not ("草稿事件被删减" in joined and "草稿枚举/参数被删减" in joined):
        print("self-check FAIL: G8 draft prune detection missed, got", errors)
        return 1
    # 已 resolve/out_of_scope 的不算删减
    waived_scope = json.loads(json.dumps(pruned_scope))
    waived_scope["out_of_scope"] = [
        {"dim": "event", "value": "livesdk_demo_extra", "reason": "非本需求"},
    ]
    waived_scope["conflicts"] = [
        {"event_name": "livesdk_demo", "param": "a", "value": "2", "status": "out_of_scope", "reason": "..."},
        {"event_name": "livesdk_demo", "param": "a", "value": "3", "status": "resolved", "reason": "..."},
    ]
    errors = []
    check_draft_not_pruned(waived_scope, draft_scope, errors)
    if errors:
        print("self-check FAIL: G8 waived entries should pass, got", errors)
        return 1

    # G7 Docx 弱反查：能从纯文本 ETD 中找到角色和枚举线索
    docx_etd = (
        "# 埋点设计\n\n"
        "| 事件 | 用户类型 | 参数 | 取值 |\n"
        "| livesdk_docx_demo | 主播、观众 | `action_type` | `click`、`dismiss`、`auto_hide` |\n"
        "| livesdk_docx_demo | 主播、观众 | `target` | `btn`、`card` |\n"
    )
    docx_scope = {
        "events": [
            {
                "event_name": "livesdk_docx_demo",
                "entrances": ["home"],
                "roles": ["anchor"],
                "params": [{"key": "action_type", "kind": "enum", "values": ["click"]}],
            }
        ]
    }
    errors = []
    check_etd_params_text(docx_scope, docx_etd, errors)
    joined = " ".join(errors)
    if not ("viewer" in joined or "观众" in joined):
        print("self-check FAIL: G7 missed viewer role, got", errors)
        return 1
    if "action_type" not in joined or "dismiss" not in joined:
        print("self-check FAIL: G7 missed missing enum value dismiss, got", errors)
        return 1

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "etd_scope.json"
        p.write_text(json.dumps(good), encoding="utf-8")
        errors = []
        validate_scope(json.loads(p.read_text()), errors)
        if errors:
            print("self-check FAIL roundtrip", errors)
            return 1
    print("check_etd_scope self-check OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", help="path to etd_scope.json")
    ap.add_argument("--cases", help="path to *_source_cases.md")
    ap.add_argument(
        "--etd-text",
        help="ETD 原文（etd_sheet_load.py 的 JSON 或纯文本）；反查 scope 是否抽漏事件（测新主路径）",
    )
    ap.add_argument("--gt-seeds", help="optional extract_bits_case.py seeds JSON for GT/scope diff")
    ap.add_argument("--gt-diff-output", help="write GT/scope diff JSON here")
    ap.add_argument("--gt-diff-only", action="store_true", help="do not fail on GT/scope diff")
    ap.add_argument(
        "--etd-draft",
        help="etd_sheet_load.py --emit-scope-draft 产出的 etd_scope.draft.json；终稿不得删减草稿抽出来的事件/参数/枚举（G8）",
    )
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    if not args.scope:
        ap.error("need --scope (or --self-check)")

    scope_path = Path(args.scope)
    if not scope_path.is_file():
        print(f"[check_etd_scope] missing scope file: {scope_path}", file=sys.stderr)
        return 2

    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[check_etd_scope] invalid JSON: {e}", file=sys.stderr)
        return 2

    errors: list[str] = []
    if not isinstance(scope, dict):
        print("[check_etd_scope] scope root must be object", file=sys.stderr)
        return 2
    validate_scope(scope, errors)

    # G8：draft 草稿对比 —— 必须在 validate_scope 之后做（draft 也要结构合法）
    if args.etd_draft:
        draft_path = Path(args.etd_draft)
        if not draft_path.is_file():
            print(f"[check_etd_scope] missing etd-draft: {draft_path}", file=sys.stderr)
            return 2
        try:
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[check_etd_scope] invalid etd-draft JSON: {e}", file=sys.stderr)
            return 2
        if not isinstance(draft, dict):
            print("[check_etd_scope] etd-draft root must be object", file=sys.stderr)
            return 2
        check_draft_not_pruned(scope, draft, errors)

    if args.cases:
        cases_path = Path(args.cases)
        if not cases_path.is_file():
            print(f"[check_etd_scope] missing cases: {cases_path}", file=sys.stderr)
            return 2
        cases_text = cases_path.read_text(encoding="utf-8")
        scan_cases(cases_text, scope, errors)
        check_coverage(cases_text, scope, errors)
        check_assert_moments(cases_text, scope, errors)
        check_test_kit_in_cases(cases_text, scope, errors)
        check_role_device_consistency(cases_text, scope, errors)

    if args.etd_text:
        etd_path = Path(args.etd_text)
        if not etd_path.is_file():
            print(f"[check_etd_scope] missing etd text: {etd_path}", file=sys.stderr)
            return 2
        check_etd_events(scope, etd_path, errors)
        payload: Any = None
        if etd_path.suffix.lower() == ".json":
            try:
                payload = json.loads(etd_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
        if not isinstance(payload, dict) or not check_etd_params(scope, payload, errors):
            # G7：结构化反查失败时，降级为纯文本弱反查（针对 Docx/md 形态 ETD）
            try:
                etd_text = _text_from_etd(etd_path)
                if etd_text.strip():
                    check_etd_params_text(scope, etd_text, errors)
                    print(
                        "[check_etd_scope] NOTE: ETD 结构化列头未识别，已执行 Docx 弱反查（启发式），"
                        "仍建议人工核对 scope 枚举/上报端完整性",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "[check_etd_scope] WARN: ETD 表头未识别且文本为空，"
                        "无法反查 上报端/必传参/枚举取值 —— 请人工逐列核对 scope",
                        file=sys.stderr,
                    )
            except Exception as e:  # pragma: no cover
                print(
                    f"[check_etd_scope] WARN: ETD 弱反查失败 ({e})，请人工核对 scope",
                    file=sys.stderr,
                )

    if args.gt_seeds:
        try:
            diff = compare_gt_scope(scope, Path(args.gt_seeds))
        except Exception as exc:
            errors.append(f"GT diff failed: {exc}")
        else:
            if not diff["gt_events"]:
                errors.append(
                    f"GT 反查失败: `{args.gt_seeds}` 没抽到任何事件名"
                    "（seeds 格式/过滤不对 —— 别当成通过）"
                )
            if args.gt_diff_output:
                Path(args.gt_diff_output).write_text(
                    json.dumps(diff, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if not args.gt_diff_only:
                if diff["gt_events_not_in_scope"]:
                    errors.append(
                        "GT 事件不在 scope 中: "
                        + ", ".join(f"`{x}`" for x in diff["gt_events_not_in_scope"])
                        + "（若不并入必须写 out_of_scope/conflicts 并确认）"
                    )
                if diff["unresolved_gt_pairs_not_in_scope"]:
                    pretty = ", ".join(
                        f"`{e}`.{k}=`{v}`"
                        for e, k, v in diff["unresolved_gt_pairs_not_in_scope"]
                    )
                    errors.append(
                        "GT 参数/枚举不在 scope 中且未 resolve: "
                        + pretty
                        + "（必须反问并写 conflicts/out_of_scope，禁止静默丢弃）"
                    )

    if errors:
        print(f"[check_etd_scope] FAIL ({len(errors)}):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("[check_etd_scope] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
