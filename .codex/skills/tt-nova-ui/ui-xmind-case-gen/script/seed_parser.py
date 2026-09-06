"""
Spec 第 7 章 Raw Case Seeds 解析器。

将 Markdown 表格格式的 seed 解析为结构化 Seed 对象，
同时提取 spec 中的 Feature 元数据（依赖关系、角色列表）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Seed:
    seed_id: str
    feature_id: str
    entry_state: str
    core_action: str
    expected_result: str
    # 埋点需求：spec 第 7 章可选第 5 列（byteio_case_list JSON 数组）。
    # 非空即表示该 seed 需绑定 et_checker_G20 埋点断言。
    byteio_cases: List[dict] = field(default_factory=list)


@dataclass
class SetupRecipe:
    """A dependency's setup recipe: how to reach the prerequisite state from scratch."""
    dependency_desc: str
    target_feature: str
    steps: str

@dataclass
class FeatureMeta:
    feature_id: str
    feature_name: str
    primary_roles: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    setup_recipes: List[SetupRecipe] = field(default_factory=list)


@dataclass
class ParsedSpec:
    seeds: Dict[str, List[Seed]] = field(default_factory=dict)
    features: Dict[str, FeatureMeta] = field(default_factory=dict)
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    feature_sections: Dict[str, str] = field(default_factory=dict)

    @property
    def feature_ids(self) -> List[str]:
        all_ids = set(self.seeds.keys()) | set(self.features.keys())
        return sorted(all_ids, key=lambda x: (int(re.sub(r"\D", "", x) or "0"), x))

    def total_seed_count(self) -> int:
        return sum(len(v) for v in self.seeds.values())


_TABLE_ROW_RE = re.compile(
    r"^\|\s*(F\d+-S\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|(.*)$",
    re.MULTILINE,
)


def _parse_byteio_cell(cell: str) -> List[dict]:
    """Parse the optional 5th seed column (byteio_case_list JSON array).

    Tolerates a trailing table pipe, escaped pipes (\\|), and non-JSON
    placeholders like "（无）" / empty → returns []."""
    raw = (cell or "").strip()
    # drop trailing table pipe + surrounding whitespace
    raw = raw.rstrip()
    if raw.endswith("|"):
        raw = raw[:-1].strip()
    raw = raw.replace("\\|", "|").strip()
    if not raw.startswith("["):
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(parsed, list):
        return [c for c in parsed if isinstance(c, dict)]
    return []

_FEATURE_HEADER_RE = re.compile(
    r"^(?:#{1,6}\s+)?(F-\d+)\s+(.+)$",
    re.MULTILINE,
)

_SEPARATOR_ROW_RE = re.compile(r"^\|[\s\-:|]+\|", re.MULTILINE)


def parse_seeds_from_spec(spec_text: str) -> ParsedSpec:
    result = ParsedSpec()

    _extract_feature_index(spec_text, result)
    _extract_feature_sections(spec_text, result)
    _extract_dependency_graph(spec_text, result)
    _extract_seeds(spec_text, result)

    return result


def _extract_seeds(spec_text: str, result: ParsedSpec) -> None:
    """Parse Chapter 7 seed tables."""
    ch7_match = re.search(
        r"(?m)^(?:#{1,6}\s+)?7[.、．]\s*(?:原始用例分组|Raw Case Seeds)",
        spec_text,
    )
    if not ch7_match:
        return

    ch7_text = spec_text[ch7_match.start():]
    end_match = re.search(
        r"(?m)^(?:#{1,6}\s+)?(?:附录|8[.、．]|---\s*\n\s*##\s)",
        ch7_text[100:],
    )
    if end_match:
        ch7_text = ch7_text[: 100 + end_match.start()]

    sections = re.split(r"(?m)^(?:#{1,6}\s+)(F-\d+)\s+[^\n]*$", ch7_text)
    it = iter(sections)
    next(it, None)
    for fid, content in zip(it, it):
        fid = fid.strip()
        seeds: List[Seed] = []
        for m in _TABLE_ROW_RE.finditer(content):
            if _SEPARATOR_ROW_RE.match(m.group(0)):
                continue
            seed_id = m.group(1).strip()
            entry_state = m.group(2).strip()
            core_action = m.group(3).strip()
            expected_result = m.group(4).strip()
            byteio_cases = _parse_byteio_cell(m.group(5) if m.lastindex and m.lastindex >= 5 else "")
            if not seed_id or seed_id.lower().startswith("seed"):
                continue
            seeds.append(Seed(
                seed_id=seed_id,
                feature_id=fid,
                entry_state=entry_state,
                core_action=core_action,
                expected_result=expected_result,
                byteio_cases=byteio_cases,
            ))
        if seeds:
            result.seeds[fid] = seeds


def _extract_feature_index(spec_text: str, result: ParsedSpec) -> None:
    """Extract feature names and roles from Chapter 2 table and Chapter 3 headers."""
    ch3_pat = re.compile(
        r"(?m)^(?:#{1,6}\s+)?3\.(F-\d+)\s+(.+)$"
    )
    for m in ch3_pat.finditer(spec_text):
        fid = m.group(1)
        fname = m.group(2).strip()
        if fid not in result.features:
            result.features[fid] = FeatureMeta(feature_id=fid, feature_name=fname)
        else:
            result.features[fid].feature_name = fname

    _extract_roles_from_preconditions(spec_text, result)


def _extract_feature_sections(spec_text: str, result: ParsedSpec) -> None:
    """Extract full Chapter 3 section text for each Feature (scenarios, rules, signals)."""
    feature_sec_pat = re.compile(
        r"(?m)^(?:#{1,6}\s+)?3\.(F-\d+)\s+([^\n]+)\n"
        r"(.*?)"
        r"(?=^(?:#{1,6}\s+)?3\.F-\d+(?!\.)\s|\n(?:#{1,6}\s+)?4[.、．]\s*功能点之间|\Z)",
        re.DOTALL,
    )
    for m in feature_sec_pat.finditer(spec_text):
        fid = m.group(1)
        result.feature_sections[fid] = m.group(0).strip()


def _extract_roles_from_preconditions(spec_text: str, result: ParsedSpec) -> None:
    """Infer primary roles from precondition sections."""
    role_keywords = {
        "主播": "主播",
        "观众": "观众",
        "管理员": "管理员",
        "看播": "观众",
    }
    for fid, meta in result.features.items():
        sec_match = re.search(
            rf"(?m)^(?:#{{1,6}}\s+)?3\.{re.escape(fid)}\s+.*?\n(.*?)(?=^(?:#{{1,6}}\s+)?3\.F-\d+(?!\.)|\Z)",
            spec_text,
            re.DOTALL,
        )
        if not sec_match:
            continue
        section_text = sec_match.group(1)
        roles = []
        for kw, role in role_keywords.items():
            if kw in section_text and role not in roles:
                roles.append(role)
        meta.primary_roles = roles if roles else ["主播"]


def _extract_dependency_graph(spec_text: str, result: ParsedSpec) -> None:
    """Extract feature dependencies and setup recipes from precondition sections."""
    dep_re = re.compile(r"→\s*(F-\d+)")

    for fid, meta in list(result.features.items()):
        sec_match = re.search(
            rf"(?m)^(?:#{{1,6}}\s+)?3\.{re.escape(fid)}\.2\s+.*?前置条件.*?\n(.*?)(?=^(?:#{{1,6}}\s+)?3\.{re.escape(fid)}\.\d|\Z)",
            spec_text,
            re.DOTALL,
        )
        if not sec_match:
            continue
        precond_text = sec_match.group(1)
        deps = dep_re.findall(precond_text)
        if deps:
            meta.depends_on = list(dict.fromkeys(deps))
            result.dependency_graph[fid] = meta.depends_on

        _extract_setup_recipes(precond_text, meta)


def _extract_setup_recipes(precond_text: str, meta: FeatureMeta) -> None:
    """Parse setup recipes from dependency lines.

    Supports two formats:
    1. Structured: '- desc（→ F-XX）\\n  - 前置实现：step1 → step2'
    2. Fallback: extracts dependency desc even without explicit recipe
    """
    dep_line_re = re.compile(
        r"^[-*]\s+(.+?（→\s*(F-\d+)）.*?)$",
        re.MULTILINE,
    )
    recipe_re = re.compile(
        r"^[\s]*[-*]\s+前置实现[：:]\s*(.+)$",
        re.MULTILINE,
    )

    lines = precond_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        dep_match = dep_line_re.match(line.strip())
        if dep_match:
            desc = dep_match.group(1).strip()
            target = dep_match.group(2).strip()
            steps = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                recipe_match = recipe_re.match(next_line)
                if recipe_match:
                    steps = recipe_match.group(1).strip()
                    i += 1
            meta.setup_recipes.append(SetupRecipe(
                dependency_desc=desc,
                target_feature=target,
                steps=steps,
            ))
        i += 1
