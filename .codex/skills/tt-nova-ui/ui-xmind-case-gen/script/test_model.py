"""
测试用例结构化中间层（TestModel）

多节点补充信息时写入同一套结构，避免只在 markdown 里改导致丢失。
渲染时按角色聚合操作步骤，输出 ${richText_<uuid>:<角色名>} [auto] 格式。
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, List, Optional, Literal, Tuple

from pydantic import BaseModel, Field

from script.device_role_skills import all_name_to_richtext_tag

_NAME_TO_TAG: Dict[str, str] = {}


def _get_name_to_tag() -> Dict[str, str]:
    global _NAME_TO_TAG
    if not _NAME_TO_TAG:
        _NAME_TO_TAG = all_name_to_richtext_tag()
    return _NAME_TO_TAG


def _normalize_role_tag(raw: str) -> str:
    """将裸角色名映射为 ${richText_...} 标签；已是 richText 格式则原样返回。"""
    s = raw.strip()
    if s.startswith("${richText_"):
        return s
    mapping = _get_name_to_tag()
    return mapping.get(s, s)


def _split_role_tag_and_action(step: str, default_role_tag: str) -> Tuple[str, str]:
    """从单步文案中拆出「角色标签」与「动作文本」。"""
    s = (step or "").strip()
    default_tag = _normalize_role_tag(default_role_tag)
    if not s:
        return default_tag, ""

    m = re.match(r"^(\$\{richText_[^}]+\})\s*", s)
    if m:
        return m.group(1), s[m.end():].strip() or s

    mapping = _get_name_to_tag()
    for name, tag in mapping.items():
        if s.startswith(name):
            rest = s[len(name):]
            if not rest or not rest[0].isalnum():
                action = rest.lstrip(" \t，,：:;；")
                return tag, action or s

    if s.startswith("@"):
        rest = s[1:].lstrip()
        parts = rest.split(None, 1)
        if len(parts) >= 2:
            return _normalize_role_tag(parts[0].strip()), parts[1].strip()
        if len(parts) == 1:
            return _normalize_role_tag(parts[0].strip()), ""

    return default_tag, s


def _extract_explicit_role_tag_and_text(text: str) -> Tuple[Optional[str], str]:
    """Only extract role tag when the text explicitly starts with a device / role prefix."""
    s = (text or "").strip()
    if not s:
        return None, ""

    m = re.match(r"^(\$\{richText_[^}]+\})\s*", s)
    if m:
        return m.group(1), s[m.end():].strip()

    mapping = _get_name_to_tag()
    for name, tag in mapping.items():
        if s.startswith(name):
            rest = s[len(name):]
            if not rest or not rest[0].isalnum():
                return tag, rest.lstrip(" \t，,：:;；").strip()

    if s.startswith("@"):
        rest = s[1:].lstrip()
        parts = rest.split(None, 1)
        if len(parts) >= 2:
            return _normalize_role_tag(parts[0].strip()), parts[1].strip()
        if len(parts) == 1:
            return _normalize_role_tag(parts[0].strip()), ""

    return None, s


def _format_expected_text(text: str) -> str:
    """Normalize expected text so explicit device prefixes also render as richText tags."""
    role_tag, content = _extract_explicit_role_tag_and_text(text)
    if role_tag:
        return f"{role_tag} {content}".strip()
    return (text or "").strip()


def _expected_text_without_role(text: str) -> str:
    """Return expected text with any explicit device/role prefix stripped (单机渲染用)。"""
    _, content = _extract_explicit_role_tag_and_text(text)
    return (content or "").strip()


def _action_without_role(step: str) -> str:
    """Return a step's action text with any explicit device/role prefix stripped (单机渲染用)。"""
    _, action = _split_role_tag_and_action(step, "")
    return (action or "").strip()


def _case_explicit_devices(case: "CaseBlock") -> List[str]:
    """收集用例中**显式**出现的设备占位（步骤 + 预期 + 仅步骤/仅预期），去重保序。

    仅统计显式写出的设备前缀（裸设备名或 ${richText_...} 标签），不含默认兜底角色。
    用于判定单机（≤1 台设备）/多机（≥2 台设备）。
    """
    seen: "OrderedDict[str, None]" = OrderedDict()
    texts: List[str] = []
    for pair in (case.step_expected_pairs or []):
        texts.append(pair.step or "")
        texts.extend(pair.expected or [])
    texts.extend(case.steps_only or [])
    texts.extend(case.expected_only or [])
    for text in texts:
        tag, _ = _extract_explicit_role_tag_and_text(text)
        if tag and tag not in seen:
            seen[tag] = None
    return list(seen.keys())


def _case_is_single_device(case: "CaseBlock") -> bool:
    """单机用例：显式设备占位 ≤ 1 台。单机时渲染不输出任何设备角色前缀。"""
    return len(_case_explicit_devices(case)) <= 1


def _format_preconditions_no_role(preconditions: List[str]) -> List[str]:
    """单机前置条件渲染：剥离设备前缀，工具占位与 remark 合并为一行，不带任何角色标签。"""
    items: List[str] = []
    for pc in preconditions:
        s = (pc or "").strip()
        if not s:
            continue
        m = _DEVICE_TAG_RE.match(s)
        if m:
            s = s[m.end():].strip()
        if s:
            items.append(s)
    if not items:
        return []
    return ["; ".join(items) + ";\n"]


def _collect_role_tags_from_steps(case: "CaseBlock", default_role_tag: str) -> List[str]:
    """扫描用例所有步骤 + 预期结果，按出现顺序收集去重的角色标签。"""
    seen: "OrderedDict[str, None]" = OrderedDict()
    sources: List[str] = []
    for pair in (case.step_expected_pairs or []):
        sources.append(pair.step or "")
        sources.extend(pair.expected or [])
    sources.extend(case.steps_only or [])
    sources.extend(case.expected_only or [])
    for text in sources:
        tag, _ = _split_role_tag_and_action(text, default_role_tag)
        if tag not in seen:
            seen[tag] = None
    return list(seen.keys())


_DEVICE_TAG_RE = re.compile(r"^(\$\{richText_\d+:[^}]+\})\s+")


def _format_preconditions_by_role(
    preconditions: List[str],
    role_tags: List[str],
) -> List[str]:
    """前置条件按设备角色输出。带设备前缀的工具只分配给对应设备，无前缀的分配给所有设备。"""
    global_tools: List[str] = []
    device_tools: Dict[str, List[str]] = {}
    hint_items: List[str] = []

    for pc in preconditions:
        s = (pc or "").strip()
        if not s:
            continue
        if s.startswith(">") or s.startswith("**[note]**") or s.startswith("**[remark]**"):
            hint_items.append(s)
            continue
        m = _DEVICE_TAG_RE.match(s)
        if m:
            tag = m.group(1)
            tool_part = s[m.end():].strip()
            if tool_part:
                device_tools.setdefault(tag, []).append(tool_part)
        else:
            global_tools.append(s)

    out: List[str] = []
    has_per_device = bool(device_tools)
    if role_tags:
        for idx, role_tag in enumerate(role_tags):
            if has_per_device:
                base = global_tools if idx == 0 else []
            else:
                base = global_tools
            tools = base + device_tools.get(role_tag, [])
            if tools:
                joined = "; ".join(tools) + ";"
                out.append(role_tag + " " + joined + "\n")
    elif global_tools:
        for item in global_tools:
            out.append(f"{item}\n")
    for hint in hint_items:
        out.append(f"{hint}\n")
    return out


_PURE_RICHTEXT_RE = re.compile(r"^\$\{richText_[^}]+\}$")


def _format_role_auto_lines(pairs: List[Tuple[str, str]]) -> List[str]:
    """多设备并行渲染：按设备聚合（每个设备一行/一条并行 lane）。

    - 同一步骤块内出现多个设备时，视为并行：每条设备行追加 `**[parallel]**` 标记。
    - `[auto]` 仅加在**第一个设备**行，其余设备行不再重复添加。
    - 单设备时不加并行标记。
    """
    if not pairs:
        return []
    groups: "OrderedDict[str, List[str]]" = OrderedDict()
    for role_tag, action in pairs:
        if not action:
            continue
        groups.setdefault(role_tag, []).append(action)
    if not groups:
        return []
    multi_device = len(groups) > 1
    out: List[str] = []
    for idx, (role_tag, actions) in enumerate(groups.items()):
        segments = list(actions)
        if multi_device:
            segments.append("**[parallel]**")
        joined = "; ".join(segments) + ";"
        prefix = " [auto]" if idx == 0 else ""
        out.append(f"{role_tag}{prefix} {joined}\n")
    return out


def _format_case_meta_lines(case: "CaseBlock") -> List[str]:
    """优先级 / 标签元信息。

    ⚠️ 不再以 `**[priority]** xx` / `**[tag]** xx` 独立行输出：bits 的
    upload_bits_test_case_mind 导入器会把用例末尾这种独立 `**[...]**` 行
    当成一个**空文本的预期结果节点（nodeType=13）**导入（priority 写进该空节点的
    priority 字段，并未应用到用例本身），导致每条用例多出一个「空的预期结果」节点。
    因此这里直接返回空，不在渲染产物里写这两类独立行。
    （如需把优先级落到 bits，应使用平台原生的优先级字段，而非 markdown 文本标记。）
    """
    return []


# ---------- 溯源 / 关联 ----------

class SourceRef(BaseModel):
    source_type: Literal["doc", "requirement", "bug", "rag", "manual"] = "doc"
    ref_id: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None


class RelatedRequirement(BaseModel):
    requirement_id: str
    summary: Optional[str] = None
    sources: List[SourceRef] = Field(default_factory=list)


class BugRef(BaseModel):
    bug_id: str
    summary: Optional[str] = None
    impact: Optional[str] = None
    sources: List[SourceRef] = Field(default_factory=list)


# ---------- 可落地用例块 ----------

class StepExpected(BaseModel):
    step: str
    expected: List[str] = Field(default_factory=list)


class CaseBlock(BaseModel):
    case_id: str = ""
    title: str = ""
    summary: Optional[str] = None
    preconditions: List[str] = Field(default_factory=list)
    step_expected_pairs: List[StepExpected] = Field(default_factory=list)
    steps_only: List[str] = Field(default_factory=list)
    expected_only: List[str] = Field(default_factory=list)
    related_bugs: List[BugRef] = Field(default_factory=list)
    related_requirements: List[RelatedRequirement] = Field(default_factory=list)
    priority: str = ""
    tags: List[str] = Field(default_factory=list)


# ---------- 功能点（Feature） ----------

class FeatureModel(BaseModel):
    feature_id: str
    feature_name: str
    feature_summary: Optional[str] = None
    primary_roles: List[str] = Field(default_factory=list)
    entry_points: List[str] = Field(default_factory=list)
    business_rules: List[str] = Field(default_factory=list)
    state_dependencies: List[str] = Field(default_factory=list)
    related_modules: List[str] = Field(default_factory=list)
    test_dimensions: List[str] = Field(default_factory=list)
    risk_points: List[str] = Field(default_factory=list)
    out_of_scope: List[str] = Field(default_factory=list)
    exception_cases: List[ExceptionCase] = Field(default_factory=list)
    observability: Optional[Observability] = None
    automation_hints: Optional[AutomationHints] = None
    cases: List[CaseBlock] = Field(default_factory=list)
    sources: List[SourceRef] = Field(default_factory=list)


class ExceptionCase(BaseModel):
    type: str
    description: str
    sources: List[SourceRef] = Field(default_factory=list)


class Observability(BaseModel):
    ui_signals: List[str] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    events: List[str] = Field(default_factory=list)
    data_states: List[str] = Field(default_factory=list)


class AutomationHints(BaseModel):
    stable_ui_anchor: List[str] = Field(default_factory=list)
    automation_signals: List[str] = Field(default_factory=list)


# ---------- 功能点关系 ----------

class FeatureRelationship(BaseModel):
    source_id: str
    target_id: str
    relation_type: str  # "depends_on" | "mutual_exclusive" | "strong_link"
    description: str = ""


# ---------- 根模型 ----------

class TestModel(BaseModel):
    schema_version: str = "1"
    module: str
    requirement_id: Optional[str] = None
    requirement_summary: Optional[str] = None
    features: List[FeatureModel] = Field(default_factory=list)
    feature_relationships: List[FeatureRelationship] = Field(default_factory=list)
    related_requirements: List[RelatedRequirement] = Field(default_factory=list)
    related_bugs: List[BugRef] = Field(default_factory=list)
    sources: List[SourceRef] = Field(default_factory=list)


FeatureModel.model_rebuild()
TestModel.model_rebuild()


# ---------- 单机 trie 合并渲染 ----------

_TRIE_TRAILING_PUNCT_RE = re.compile(r"[\s。．.;；,，、:：!！?？]+$")


def _trie_merge_key(action: str) -> str:
    """步骤文本的合并键：用于判定两个 step 是否应合并为同一 trie 节点。

    对**仅有琐碎差异**的步骤做归一化，避免因尾部标点 / 多余空格 / 中英文引号样式不同
    而让本应共享的前缀拆成多个重复分支（导致路径翻倍膨胀）：
    - 折叠内部连续空白为单个空格；
    - 去掉尾部标点（。.;；,，、:：!！?？ 等）与空白；
    - 统一中文弯引号/单引号为英文直引号。

    注意：归一化只用于**合并判定**，节点实际展示用首次出现的原始文本（保留可读性）。
    归一化保持保守，不改写词序、不删除内容，避免误合并语义不同的步骤。
    """
    s = (action or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = _TRIE_TRAILING_PUNCT_RE.sub("", s)
    s = (
        s.replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u2018", "'").replace("\u2019", "'")
    )
    return s


def _trie_build(cases: List["CaseBlock"]) -> dict:
    """把一组单机用例按「步骤文本」合并成前缀树（trie）。

    多个用例共享相同前缀步骤时只保留一个节点，分叉处生成多个子节点（多个分支），
    从而还原原始脑图「同一前序节点挂多个分支」的结构，而非每条用例各自重复整段前缀。
    每个节点累计其预期结果（来自以该节点为叶子的用例）。

    合并以 `_trie_merge_key(action)` 为键（容忍尾部标点/空白/引号样式差异），
    但节点展示文本取首次出现的原文。
    """
    root: dict = {"step": None, "exp": [], "children": OrderedDict()}
    for case in cases:
        node = root
        for pair in (case.step_expected_pairs or []):
            action = _action_without_role(pair.step)
            if not action:
                continue
            key = _trie_merge_key(action)
            ch = node["children"]
            if key not in ch:
                ch[key] = {"step": action, "exp": [], "children": OrderedDict()}
            node = ch[key]
            for e in (pair.expected or []):
                et = _expected_text_without_role(e)
                if et and et not in node["exp"]:
                    node["exp"].append(et)
    return root


def _trie_render(node: dict, depth: int, lines: List[str]) -> None:
    lines.append(f"{'#' * depth} **操作步骤**\n")
    lines.append(f"[auto] {node['step']};\n")
    for e in node["exp"]:
        lines.append(f"{'#' * (depth + 1)} **预期结果** {e}\n")
    for child in node["children"].values():
        _trie_render(child, depth + 1, lines)


def _common_case_tags(cases: List["CaseBlock"]) -> List[str]:
    """返回一组用例**共有**的标签（保序，以首个用例的顺序为准）。

    trie 合并会丢失各用例标题，但若整组用例共享同一地区标签（如全 US），
    把该标签挂到合并分组的根标题上，避免丢失 `**[tag]** US` 等区域信息。
    """
    if not cases:
        return []
    common: Optional[List[str]] = None
    for c in cases:
        ts = list(c.tags or [])
        if common is None:
            common = list(ts)
        else:
            common = [t for t in common if t in ts]
    return common or []


def _single_group_disc(precond: tuple, gcases: List["CaseBlock"], gi: int) -> str:
    """为「同一前置条件」的单机分组生成判别后缀（仅在存在多个分组时使用）。

    优先级：前置条件里的非空 remark/hint 文本 > 首条用例标题 > 首步动作 > 组序号。
    （空 body 的 `**[remark]** <ttat>` 不作为判别，避免污染分组标题。）
    """
    tag = ""
    for pc in precond:
        s = (pc or "").strip()
        mm = re.match(r"^(?:hint[:：]|\*\*\[remark\]\*\*)\s*(.+)$", s, re.I)
        if mm:
            cand = re.sub(r"^<[^>]*>\s*", "", mm.group(1).strip()).strip()
            if cand:
                tag = cand
                break
    if not tag:
        t0 = (gcases[0].title or "").strip() if gcases else ""
        if t0:
            tag = t0
        else:
            first_pairs = (gcases[0].step_expected_pairs or []) if gcases else []
            tag = _action_without_role(first_pairs[0].step) if first_pairs else f"组{gi}"
    tag = tag.replace("`", "").strip()
    return f" · {tag[:30]}"


def _render_single_trie_groups(
    feat: "FeatureModel", cases: List["CaseBlock"], lines: List[str]
) -> None:
    """单机用例：按前置条件分组后做 trie 合并渲染。

    共享前缀只出现一次，分叉处生成多个分支（还原原始脑图「同一前序节点挂多个分支」
    的结构），避免每条用例重复整段前缀导致路径翻倍膨胀。整组共有的区域标签挂在分组标题上。
    """
    groups: "OrderedDict[tuple, List[CaseBlock]]" = OrderedDict()
    for case in cases:
        groups.setdefault(tuple(case.preconditions), []).append(case)
    multi = len(groups) > 1
    for gi, (precond, gcases) in enumerate(groups.items(), 1):
        disc = _single_group_disc(precond, gcases, gi) if multi else ""
        tag_suffix = ""
        ctags = _common_case_tags(gcases)
        if ctags:
            tag_suffix = " " + "".join(f"**[tag]** {t}" for t in ctags)
        lines.append(f"### {feat.feature_name}{disc}{tag_suffix}\n")
        if precond:
            lines.append("#### **前置条件**\n")
            for line in _format_preconditions_no_role(list(precond)):
                lines.append(line)
            lines.append("\n")
        root = _trie_build(gcases)
        for child in root["children"].values():
            _trie_render(child, 5, lines)
        lines.append("\n")


def _render_case_block(feat: "FeatureModel", case: "CaseBlock", lines: List[str]) -> None:
    """渲染单条用例（多设备/并行用例走此路径，保留各自标题、标签与设备角色前缀）。"""
    case_title = case.title or case.case_id or "未命名用例"
    # 用例（分支）根节点标签：US / EU 等。直接挂在用例标题节点上，
    # 这样标签作用于该分支的根节点，而非额外生成空的预期结果节点。
    tag_suffix = ""
    if case.tags:
        tag_suffix = " " + "".join(f"**[tag]** {t}" for t in case.tags)
    lines.append(f"### {case_title}{tag_suffix}\n")

    default_role_tag = feat.primary_roles[0] if feat.primary_roles else "默认"
    single_device = _case_is_single_device(case)

    if case.preconditions:
        lines.append("#### **前置条件**\n")
        if single_device:
            # 单机：前置条件不带任何设备角色前缀。
            for line in _format_preconditions_no_role(case.preconditions):
                lines.append(line)
        else:
            role_tags = _collect_role_tags_from_steps(case, default_role_tag)
            if role_tags:
                for line in _format_preconditions_by_role(case.preconditions, role_tags):
                    lines.append(line)
            else:
                for i, pc in enumerate(case.preconditions, 1):
                    lines.append(f"{i}. {pc}\n")
        lines.append("\n")

    if case.step_expected_pairs:
        base_step_level = 5

        if single_device:
            # 单机：每个步骤独立成「操作步骤」节点，按层级递增形成顺序链（与原始 case 的
            # 嵌套步骤结构一致）；每个步骤各自跟随自己的「预期结果」。
            # 绝不打平/合并多个步骤；不输出设备角色前缀（单机无需指定角色）。
            depth = 0
            for pair in case.step_expected_pairs:
                action = _action_without_role(pair.step)
                step_hashes = "#" * (base_step_level + depth)
                lines.append(f"{step_hashes} **操作步骤**\n")
                if action:
                    lines.append(f"[auto] {action};\n")
                for exp in (pair.expected or []):
                    exp_hashes = "#" * (base_step_level + depth + 1)
                    lines.append(f"{exp_hashes} **预期结果** {_expected_text_without_role(exp)}\n")
                depth += 1
            lines.append("\n")
        else:
            # 多设备：保留并行分组渲染（同一步骤块内多设备视为并行）
            group_pairs: List[Tuple[str, str]] = []
            depth = 0
            for pair in case.step_expected_pairs:
                r, a = _split_role_tag_and_action(pair.step, default_role_tag)
                group_pairs.append((r, a))
                if pair.expected:
                    step_hashes = "#" * (base_step_level + depth)
                    exp_hashes = "#" * (base_step_level + depth + 1)
                    lines.append(f"{step_hashes} **操作步骤**\n")
                    for line in _format_role_auto_lines(group_pairs):
                        lines.append(line)
                    for exp in pair.expected:
                        lines.append(f"{exp_hashes} **预期结果** {_format_expected_text(exp)}\n")
                    group_pairs = []
                    depth += 1
            if group_pairs:
                step_hashes = "#" * (base_step_level + depth)
                lines.append(f"{step_hashes} **操作步骤**\n")
                for line in _format_role_auto_lines(group_pairs):
                    lines.append(line)
            lines.append("\n")
    elif case.steps_only:
        lines.append("##### **操作步骤**\n")
        only_pairs: List[Tuple[str, str]] = []
        for s in case.steps_only:
            only_pairs.append(_split_role_tag_and_action(s, default_role_tag))
        for line in _format_role_auto_lines(only_pairs):
            lines.append(line)
        if case.expected_only:
            for exp in case.expected_only:
                lines.append(f"###### **预期结果** {_format_expected_text(exp)}\n")
        lines.append("\n")

    meta_lines = _format_case_meta_lines(case)
    if meta_lines:
        lines.extend(meta_lines)
        lines.append("\n")


# ---------- 渲染为 Markdown ----------

def test_model_to_markdown(model: TestModel) -> str:
    """
    TestModel -> Markdown（角色感知渲染）。

    - 前置条件：按设备角色展开，每个角色挂相同的工具占位
    - 操作步骤：${richText_<uuid>:<角色名>} [auto] action1; action2;
    - 预期结果：独立 heading 节点
    """
    lines: List[str] = []
    lines.append(f"# {model.module}\n\n")

    for feat in model.features:
        lines.append(f"## {feat.feature_name}\n")

        # 在 Feature 内部按设备数拆分：
        # - 单机用例（≤1 台设备）→ 按前置条件分组做 trie 合并（共享前缀只渲染一次）。
        # - 多设备用例（≥2 台设备，如跨端联动）→ 逐条渲染（保留并行/设备角色结构）。
        # 这样即使一个 Feature 同时包含单机与多设备用例，单机部分的重复前缀也能被合并，
        # 不再因为「整个 Feature 不是纯单机」而整体退化为逐条重复渲染。
        single_cases = [c for c in feat.cases if _case_is_single_device(c)]
        multi_cases = [c for c in feat.cases if not _case_is_single_device(c)]

        # 仅当存在多设备用例时才输出「主要角色」（单机无需指定角色）。
        if feat.primary_roles and multi_cases:
            lines.append(f"**主要角色**：{', '.join(feat.primary_roles)}\n\n")
        if feat.feature_summary and feat.feature_summary.strip() != feat.feature_name.strip():
            lines.append(f"{feat.feature_summary.strip()}\n\n")

        if single_cases:
            _render_single_trie_groups(feat, single_cases, lines)

        for case in multi_cases:
            _render_case_block(feat, case, lines)

    return "".join(lines)
