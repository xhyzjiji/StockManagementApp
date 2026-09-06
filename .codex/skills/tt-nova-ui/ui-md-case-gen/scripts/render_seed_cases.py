#!/usr/bin/env python3
"""
Render extracted BITS branches into AI-executable Markdown UI cases.

Design goals:
- branch-first: one raw mutually-exclusive branch becomes one case
- structure-driven: infer navigation, state, action, and assertions from branch data
- no business-specific mapping table embedded in the renderer
- observable assertions: prefer "是否..." instead of action-like expectations
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


SECTION_PATTERN = re.compile(r"^[A-Z][A-Z0-9 _-]{2,}$")
DEEPLINK_PATTERN = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^\s]+)")
INTERFACE_PATTERN = re.compile(r"(/[A-Za-z0-9_./-]+/?)")
TIME_PATTERN = re.compile(r"\b\d{1,2}:\d{2}\b")
TECHNICAL_FLOW_PATTERN = re.compile(
    r"(接口|api|token|sdk|sender|device|did|uid|版本|上报|请求|查询|install|uninstall|register|upload)",
    re.IGNORECASE,
)
CASE_TYPE_ORDER = ("UI类 Case", "半UI类 Case", "非UI类 Case")

SEMANTIC_CONFIG = {
    "operators": {
        "action": (
            "点击", "输入", "设置", "选择", "打开", "关闭", "观察", "切换", "发送",
            "请求", "上报", "查询", "登录", "注册", "安装", "使用", "下载", "返回",
            "查看", "同意", "拒绝", "模拟", "准备", "执行",
        ),
        "assertion": ("进入", "定位", "跳转到", "跳转至", "跳转", "正常跳转至", "展示", "关闭", "请求", "上报"),
        "state_mode": ("当", "首次", "首启", "登录之后"),
    },
    "tokens": {
        "negative_polarity": ("不", "无", "未", "失败", "收不到", "不会", "无法"),
        "positive_toggle": ("打开", "开启", "启用"),
        "negative_toggle": ("关闭", "关掉", "停用"),
        "observable_outcome": ("收到", "出现", "展示", "显示", "跳转", "上报", "触发"),
        "precondition_entity": ("登录", "账号", "地区", "系统", "实验", "授权", "新用户", "安装"),
        "excluded_page_prefix": ("openurl", "deeplink"),
        "non_page_category": ("用例", "测试", "消息", "场景"),
    },
    "regex": {
        "labeled_assertion": (r"^([^：]{1,16})：(.*)$", 0),
        "state_suffix": (r"(后|时|前|中|启动)$", 0),
        "state_phrase": (r"(状态|情况下|之后|以前|以后|期间|过程)", 0),
        "explicit_page": (r"^(打开：|进入[^；]*?(页面|page)$)", 0),
        "toast": (r"toast", re.IGNORECASE),
        "app_lifecycle_state": (r"^[冷热]启动$", 0),
        "after_action": (r"^(.{1,20})后(.{1,20})$", 0),
        "normal_display": (r"^(.*)正常展示$", 0),
    },
    "renderers": {
        "labeled_assertion": {
            "标题": lambda payload: f"页面标题是否为 `{payload}`。",
            "文案": lambda payload: f"页面是否展示文案 `{payload}`。",
            "按钮": lambda payload: f"页面是否展示 `{payload}` 按钮。",
            "Button": lambda payload: f"页面是否展示 `{payload}` 按钮。",
            "图片": lambda payload: f"页面是否展示 `{payload}`。",
        },
        "assertion_operator": {
            "进入": lambda payload: f"当前页面是否为 `{payload}`。",
            "定位": lambda payload: f"当前页面是否为 `{payload}`。",
            "跳转到": lambda payload: f"当前页面是否跳转到 `{payload}`。",
            "跳转至": lambda payload: f"当前页面是否跳转到 `{payload}`。",
            "跳转": lambda payload: f"当前页面是否跳转到 `{payload}`。",
            "正常跳转至": lambda payload: f"当前页面是否跳转到 `{payload}`。",
            "展示": lambda payload: f"页面是否展示 `{payload}`。",
            "关闭": lambda payload: f"`{payload}` 是否关闭或消失。",
            "请求": lambda payload: f"`{payload}` 是否被请求，且请求内容是否符合当前场景。",
            "上报": lambda payload: f"`{payload}` 是否被正确上报。",
        },
        "state_mode": {
            "当": lambda value: f"将场景切换为 `{value}`。",
            "首次": lambda value: f"按 `{value}` 场景启动应用。",
            "首启": lambda value: f"按 `{value}` 场景启动应用。",
            "登录之后": lambda value: f"完成登录后，执行 `{value}` 对应的场景动作。",
        },
    },
}


def compile_operator_prefix_pattern(operators: tuple[str, ...]) -> re.Pattern[str]:
    escaped = "|".join(sorted((re.escape(item) for item in operators), key=len, reverse=True))
    return re.compile(rf"^({escaped})(.*)$")


def compile_contains_pattern(tokens: tuple[str, ...], *, ignore_case: bool = False) -> re.Pattern[str]:
    escaped = "|".join(re.escape(item) for item in tokens)
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(rf"({escaped})", flags)


def compile_config_pattern(name: str) -> re.Pattern[str]:
    pattern, flags = SEMANTIC_CONFIG["regex"][name]
    return re.compile(pattern, flags)


SEMANTIC_PATTERNS = {
    "explicit_action": compile_operator_prefix_pattern(SEMANTIC_CONFIG["operators"]["action"]),
    "labeled_assertion": compile_config_pattern("labeled_assertion"),
    "assertion_operator": compile_operator_prefix_pattern(SEMANTIC_CONFIG["operators"]["assertion"]),
    "negative_polarity": compile_contains_pattern(SEMANTIC_CONFIG["tokens"]["negative_polarity"]),
    "positive_toggle": compile_contains_pattern(SEMANTIC_CONFIG["tokens"]["positive_toggle"]),
    "negative_toggle": compile_contains_pattern(SEMANTIC_CONFIG["tokens"]["negative_toggle"]),
    "observable_outcome": compile_contains_pattern(SEMANTIC_CONFIG["tokens"]["observable_outcome"]),
    "state_suffix": compile_config_pattern("state_suffix"),
    "state_phrase": compile_config_pattern("state_phrase"),
    "explicit_page": compile_config_pattern("explicit_page"),
    "non_page_category": compile_contains_pattern(SEMANTIC_CONFIG["tokens"]["non_page_category"]),
    "state_mode": compile_operator_prefix_pattern(SEMANTIC_CONFIG["operators"]["state_mode"]),
    "precondition_entity": compile_contains_pattern(SEMANTIC_CONFIG["tokens"]["precondition_entity"]),
    "toast": compile_config_pattern("toast"),
    "app_lifecycle_state": compile_config_pattern("app_lifecycle_state"),
    "after_action": compile_config_pattern("after_action"),
    "normal_display": compile_config_pattern("normal_display"),
    "excluded_page_prefix": compile_contains_pattern(SEMANTIC_CONFIG["tokens"]["excluded_page_prefix"], ignore_case=True),
}


@dataclass
class SeedSemantics:
    seed: dict
    deeplink: str | None
    navigation_nodes: list[str]
    page_hierarchy: list[str]
    context_nodes: list[str]
    state_nodes: list[str]
    action_nodes: list[str]
    knowledge_hints: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to extracted branches JSON")
    parser.add_argument("--output", required=True, help="Markdown output path")
    parser.add_argument("--title", default="AI-Executable Branch-Preserving UI Cases")
    parser.add_argument("--module", default="BITS UI Module")
    parser.add_argument("--app-home-label", default="应用首页")
    parser.add_argument("--source-bits-case", default="")
    parser.add_argument("--knowledge-base", default="")
    return parser.parse_args()


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def clean_text(text: str) -> str:
    return text.strip().replace("\n", "；").replace(" ", " ")


def normalize_label(text: str) -> str:
    value = clean_text(text).strip("：:。； ")
    value = re.sub(r"\s+", " ", value)
    return value


def split_phrases(text: str) -> list[str]:
    raw = normalize_label(text)
    if not raw:
        return []
    parts = re.split(r"[；\n]+", raw)
    return [normalize_label(part) for part in parts if normalize_label(part)]


def is_deeplink(text: str) -> bool:
    return bool(DEEPLINK_PATTERN.search(text))


def extract_deeplink(text: str) -> str | None:
    match = DEEPLINK_PATTERN.search(text)
    if not match:
        return None
    return match.group(1)


def is_action_like(text: str) -> bool:
    normalized = normalize_label(text)
    if not normalized:
        return False
    return is_deeplink(normalized) or bool(SEMANTIC_PATTERNS["explicit_action"].match(normalized))


def is_state_like(text: str) -> bool:
    normalized = normalize_label(text)
    if not normalized:
        return False
    if "；" in normalized:
        return True
    if normalized.count("-") >= 3:
        return True
    if SEMANTIC_PATTERNS["state_suffix"].search(normalized):
        return True
    if SEMANTIC_PATTERNS["state_phrase"].search(normalized):
        return True
    if "，" in normalized and len(normalized) > 12:
        return True
    return False


def is_page_like(text: str) -> bool:
    normalized = normalize_label(text)
    if not normalized:
        return False
    if is_deeplink(normalized):
        return False
    if SEMANTIC_PATTERNS["explicit_page"].search(normalized):
        return True
    if SEMANTIC_PATTERNS["excluded_page_prefix"].search(normalized):
        return False
    if SEMANTIC_PATTERNS["non_page_category"].search(normalized):
        return False
    return False


def is_section_like(text: str) -> bool:
    normalized = normalize_label(text)
    if not normalized or is_state_like(normalized):
        return False
    if SECTION_PATTERN.match(normalized):
        return True
    if normalized.isupper():
        return True
    return False


def looks_like_ui_target(text: str) -> bool:
    normalized = normalize_label(text)
    if not normalized:
        return False
    if is_state_like(normalized) or is_page_like(normalized):
        return False
    return len(normalized) <= 40


def title_case_if_ascii(text: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9 _./-]+", text):
        return " ".join(part.capitalize() for part in text.split())
    return text


def parse_page_hierarchy(nodes: list[str]) -> list[str]:
    for node in nodes:
        text = normalize_label(node)
        if not text:
            continue
        if is_state_like(text):
            continue
        if is_action_like(text) and not SEMANTIC_PATTERNS["explicit_page"].match(text):
            continue
        if not is_page_like(text):
            continue
        candidate = text
        candidate = re.sub(r"^打开：", "", candidate)
        candidate = re.sub(r"^进入", "", candidate)
        if is_deeplink(candidate):
            continue
        if len(candidate) > 80:
            continue
        segments = re.split(r"\s*[-/>]+\s*|\s+/\s+", candidate)
        cleaned: list[str] = []
        for segment in segments:
            value = normalize_label(segment)
            if not value:
                continue
            value = re.sub(r"^(打开|进入到|进入|跳转到|跳转)", "", value).strip()
            value = re.sub(r"(页面|page)$", "", value, flags=re.IGNORECASE).strip()
            value = title_case_if_ascii(value)
            if value and value not in cleaned:
                cleaned.append(value)
        if cleaned:
            return cleaned
    return []


def load_knowledge_lines(path: str) -> list[str]:
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        return []
    lines: list[str] = []
    for raw_line in file_path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" in line:
            continue
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        if line.startswith(("-", "*")):
            line = line[1:].strip()
        if line:
            lines.append(line)
    return lines


def select_knowledge_hints(seed: dict, knowledge_lines: list[str]) -> list[str]:
    if not knowledge_lines:
        return []

    candidate_terms: list[str] = []
    for text in seed["seed_path"] + [step["step"] for step in seed["steps"]]:
        normalized = normalize_label(text)
        if not normalized or len(normalized) > 40:
            continue
        if is_action_like(normalized):
            continue
        candidate_terms.append(normalized.lower())

    hints: list[str] = []
    for line in knowledge_lines:
        lowered = line.lower()
        if any(term in lowered for term in candidate_terms):
            hints.append(line)
        if len(hints) >= 3:
            break
    return hints


def parse_seed_semantics(seed: dict, knowledge_lines: list[str]) -> SeedSemantics:
    all_nodes = [normalize_label(node) for node in seed["seed_path"] if normalize_label(node)]
    step_nodes = [normalize_label(step["step"]) for step in seed["steps"] if normalize_label(step["step"])]
    page_hierarchy = parse_page_hierarchy(all_nodes + [node for node in step_nodes if is_page_like(node)])

    state_nodes: list[str] = []
    action_nodes: list[str] = []
    context_nodes: list[str] = []

    for node in all_nodes:
        if node in page_hierarchy:
            continue
        if is_deeplink(node):
            continue
        if is_state_like(node):
            if node not in state_nodes:
                state_nodes.append(node)
            continue
        if is_action_like(node):
            if node not in action_nodes:
                action_nodes.append(node)
            continue
        if looks_like_ui_target(node) or is_section_like(node):
            if node not in context_nodes and node not in page_hierarchy:
                context_nodes.append(node)

    for node in step_nodes:
        if node in page_hierarchy:
            continue
        if is_deeplink(node):
            continue
        if is_state_like(node):
            if node not in state_nodes:
                state_nodes.append(node)
            continue
        if node not in action_nodes:
            action_nodes.append(node)

    deeplink = None
    for text in all_nodes + step_nodes:
        deeplink = extract_deeplink(text)
        if deeplink:
            break

    navigation_nodes = page_hierarchy + context_nodes
    return SeedSemantics(
        seed=seed,
        deeplink=deeplink,
        navigation_nodes=navigation_nodes,
        page_hierarchy=page_hierarchy,
        context_nodes=context_nodes,
        state_nodes=state_nodes,
        action_nodes=action_nodes,
        knowledge_hints=select_knowledge_hints(seed, knowledge_lines),
    )


def tc_priority(seed: dict) -> str:
    value = seed.get("priority")
    if value == 99:
        return "P0"
    if value and value >= 50:
        return "P1"
    return "P2"


def build_precondition(semantics: SeedSemantics) -> str:
    items: list[str] = []
    for node in semantics.state_nodes:
        if SEMANTIC_PATTERNS["precondition_entity"].search(node):
            items.append(f"`{node}`")
    if not items:
        items.append("`按原始互斥分支前置准备测试环境`")
    return " + ".join(dict.fromkeys(items))


def build_extra(semantics: SeedSemantics) -> str:
    details: list[str] = []
    if semantics.deeplink:
        details.append(f"原始 deeplink/openUrl: `{semantics.deeplink}`")
    if not details:
        details.append("保持分支独立，不与其他分支合并。")
    return "；".join(details)


def build_title(seed: dict) -> str:
    parts = [normalize_label(item) for item in seed["seed_path"] if normalize_label(item)]
    tail = parts[-3:] if len(parts) >= 3 else parts
    return " - ".join(tail)


def format_breadcrumb(text: str) -> str:
    parts = [normalize_label(part) for part in text.split("/") if normalize_label(part)]
    return " - ".join(parts)


def primary_business_dir(seed: dict) -> str:
    parts = [normalize_label(item) for item in seed["seed_path"] if normalize_label(item)]
    if len(parts) >= 2:
        return parts[1]
    if parts:
        return parts[0]
    return "未分类"


def action_operator(text: str) -> str | None:
    match = SEMANTIC_PATTERNS["explicit_action"].match(normalize_label(text))
    if not match:
        return None
    return match.group(1)


def is_technical_flow_seed(seed: dict, semantics: SeedSemantics) -> bool:
    if semantics.page_hierarchy or semantics.deeplink:
        return False

    combined_texts = [
        *[normalize_label(node) for node in seed["seed_path"]],
        *[normalize_label(step["step"]) for step in seed["steps"]],
        *[normalize_label(item) for item in seed["expected"]],
    ]
    score = 0
    for text in combined_texts:
        if not text:
            continue
        if "接口" in text or INTERFACE_PATTERN.search(text):
            score += 2
        if TECHNICAL_FLOW_PATTERN.search(text):
            score += 1

    technical_actions = {
        "请求", "上报", "查询", "安装", "注册", "下载",
    }
    action_hits = sum(
        1
        for item in semantics.action_nodes
        if action_operator(item) in technical_actions
    )
    return score >= 3 or action_hits >= 1


def classify_case(seed: dict, semantics: SeedSemantics) -> str:
    if semantics.page_hierarchy:
        return "UI类 Case"
    if semantics.deeplink:
        return "半UI类 Case"
    if is_technical_flow_seed(seed, semantics):
        return "非UI类 Case"
    if semantics.context_nodes or semantics.action_nodes or semantics.state_nodes:
        return "半UI类 Case"
    return "非UI类 Case"


def step_for_page_hierarchy(semantics: SeedSemantics, app_home_label: str) -> list[str]:
    pages = semantics.page_hierarchy
    if not pages:
        return []

    steps: list[str] = []
    first_page = pages[0]
    steps.append(f"从{app_home_label}，通过可见入口进入 `{first_page}` 页面。")
    for current, nxt in zip(pages, pages[1:]):
        steps.append(f"在 `{current}` 页面进入 `{nxt}` 页面。")
    return steps


def normalize_state_to_step(text: str, app_home_label: str) -> str:
    value = normalize_label(text)
    if SEMANTIC_PATTERNS["app_lifecycle_state"].search(value):
        return f"确保应用处于 `{value}` 状态。"
    mode_match = SEMANTIC_PATTERNS["state_mode"].match(value)
    if mode_match:
        mode, _ = mode_match.groups()
        renderer = SEMANTIC_CONFIG["renderers"]["state_mode"].get(mode)
        if renderer:
            return renderer(value)
    return f"确保前置状态满足 `{value}`。"


def normalize_action_to_step(text: str) -> str:
    value = normalize_label(text)
    if not value:
        return value
    if is_deeplink(value):
        return f"准备一条 openUrl 为 `{value}` 的触发链路，并下发到目标设备。"
    after_action_match = SEMANTIC_PATTERNS["after_action"].match(value)
    if after_action_match:
        left, right = after_action_match.groups()
        left = normalize_label(left)
        right = normalize_label(right)
        if left and right:
            return f"完成 `{left}` 后，执行 `{right}`。"
    match = SEMANTIC_PATTERNS["explicit_action"].match(value)
    if match:
        operator, payload = match.groups()
        payload = normalize_label(payload)
        if payload:
            return f"执行 `{operator}` 操作，目标为 `{payload}`。"
        return f"执行 `{operator}` 操作。"
    return f"执行 `{value}`。"


def normalize_context_to_step(text: str, container: str | None) -> str:
    value = normalize_label(text)
    if is_section_like(value):
        if container:
            return f"在 `{container}` 页面确认 `{value}` 分组可见。"
        return f"在当前页面确认 `{value}` 分组可见。"
    if container:
        return f"在 `{container}` 页面定位 `{value}` 入口或控件。"
    return f"在当前页面定位 `{value}` 入口或控件。"


def is_negative_statement(text: str) -> bool:
    return bool(SEMANTIC_PATTERNS["negative_polarity"].search(text))


def should_split_compound_assertion(text: str) -> bool:
    if "，" not in text:
        return False
    parts = [normalize_label(part) for part in text.split("，") if normalize_label(part)]
    if len(parts) != 2:
        return False
    return all(len(part) <= 40 for part in parts)


def parse_labeled_assertion(text: str) -> tuple[str, str] | None:
    match = SEMANTIC_PATTERNS["labeled_assertion"].match(text)
    if not match:
        return None
    label, payload = match.groups()
    return normalize_label(label), normalize_label(payload)


def parse_assertion_operator(text: str) -> tuple[str, str] | None:
    match = SEMANTIC_PATTERNS["assertion_operator"].match(text)
    if not match:
        return None
    operator, payload = match.groups()
    return operator, normalize_label(payload)


def infer_dual_state_target(seed: dict, semantics: SeedSemantics) -> str | None:
    combined_expected = "；".join(normalize_label(item) for item in seed["expected"])
    if not combined_expected:
        return None
    has_positive_action = bool(SEMANTIC_PATTERNS["positive_toggle"].search(combined_expected))
    has_negative_action = bool(SEMANTIC_PATTERNS["negative_toggle"].search(combined_expected))
    has_observable_result = bool(SEMANTIC_PATTERNS["observable_outcome"].search(combined_expected))
    has_negative_result = is_negative_statement(combined_expected)
    if has_positive_action and has_negative_action and has_observable_result and has_negative_result:
        return target_from_semantics(semantics)
    return None


def infer_case_steps(semantics: SeedSemantics, app_home_label: str) -> list[str]:
    seed = semantics.seed
    steps: list[str] = []

    if not semantics.page_hierarchy and not semantics.deeplink:
        steps.append(
            f"TODO-KNOWLEDGE: 当前分支未提供从{app_home_label}进入该场景的明确 UI 路径，"
            "需要补充可执行入口后再执行。"
        )

    steps.extend(step_for_page_hierarchy(semantics, app_home_label))

    container = semantics.page_hierarchy[-1] if semantics.page_hierarchy else None
    seen = set()

    for raw_step in seed["steps"]:
        text = normalize_label(raw_step["step"])
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)

        if is_deeplink(text):
            steps.append(normalize_action_to_step(text))
        elif is_state_like(text):
            steps.append(normalize_state_to_step(text, app_home_label))
        elif is_action_like(text):
            steps.append(normalize_action_to_step(text))
        elif text in semantics.context_nodes and not is_action_like(text):
            steps.append(normalize_context_to_step(text, container))
        else:
            steps.append(f"在当前页面执行 `{text}` 对应的操作。")

    toggle_target = infer_dual_state_target(seed, semantics)
    if toggle_target:
        steps.append(f"打开 `{toggle_target}` 开关。")
        steps.append(f"关闭 `{toggle_target}` 开关。")

    return steps


def target_from_semantics(semantics: SeedSemantics) -> str | None:
    for value in reversed(semantics.context_nodes):
        if not is_section_like(value):
            return value
    if semantics.context_nodes:
        return semantics.context_nodes[-1]
    if semantics.page_hierarchy:
        return semantics.page_hierarchy[-1]
    return None


def assertion_from_fragment(fragment: str, semantics: SeedSemantics) -> list[str]:
    text = normalize_label(fragment)
    target = target_from_semantics(semantics)

    if not text or text == "-":
        if target:
            return [f"当前展示结果是否满足 `{target}`。"]
        if semantics.action_nodes:
            return [f"执行结果是否满足 `{semantics.action_nodes[-1]}` 对应预期。"]
        return ["结果是否符合原始 BITS 预期。"]

    if should_split_compound_assertion(text):
        left, right = text.split("，", 1)
        return assertion_from_fragment(left, semantics) + assertion_from_fragment(right, semantics)

    after_action_match = SEMANTIC_PATTERNS["after_action"].match(text)
    if after_action_match:
        left, right = after_action_match.groups()
        left = normalize_label(left)
        right = normalize_label(right)
        if left and right and is_action_like(right):
            action_match = SEMANTIC_PATTERNS["explicit_action"].match(right)
            if action_match and action_match.group(1) == "点击":
                click_target = right.removeprefix("点击").strip() or "目标项"
                return [f"完成 `{left}` 后，`{click_target}` 是否可被点击。"]
            return [f"完成 `{left}` 后，`{right}` 是否可执行。"]

    labeled = parse_labeled_assertion(text)
    if labeled:
        label, payload = labeled
        renderer = SEMANTIC_CONFIG["renderers"]["labeled_assertion"].get(label)
        if renderer:
            return [renderer(payload)]

    parsed_operator = parse_assertion_operator(text)
    if parsed_operator:
        operator, payload = parsed_operator
        renderer = SEMANTIC_CONFIG["renderers"]["assertion_operator"].get(operator)
        if renderer:
            return [renderer(payload)]

    normal_display_match = SEMANTIC_PATTERNS["normal_display"].match(text)
    if normal_display_match:
        subject = normalize_label(normal_display_match.group(1))
        if not subject or subject in {"页面", "当前页面"}:
            return ["当前页面是否加载完成，且关键元素是否可见。"]
        return [f"`{subject}` 是否正常展示。"]

    has_positive_action = bool(SEMANTIC_PATTERNS["positive_toggle"].search(text))
    has_negative_action = bool(SEMANTIC_PATTERNS["negative_toggle"].search(text))
    has_observable_result = bool(SEMANTIC_PATTERNS["observable_outcome"].search(text))
    has_negative_result = is_negative_statement(text)
    if has_positive_action and has_negative_action and has_observable_result and has_negative_result:
        label = target or "对应控件"
        return [
            f"打开 `{label}` 后，相关可观察结果是否出现。",
            f"关闭 `{label}` 后，相同可观察结果是否不出现。",
        ]

    if TIME_PATTERN.search(text) and "请求" not in text:
        return [f"页面显示的时间是否为 `{text}`。"]

    interface_match = INTERFACE_PATTERN.search(text)
    if interface_match:
        interface = interface_match.group(1)
        if "上报" in text:
            return [f"`{interface}` 对应的数据是否被正确上报。"]
        return [f"`{interface}` 是否按预期被触发。"]

    if SEMANTIC_PATTERNS["toast"].search(text):
        return [f"页面是否展示预期 toast：`{text}`。"]

    if "标题" in text and "文案" in text:
        return [f"页面标题和文案是否与原始预期一致：`{text}`。"]

    return [f"结果是否满足：`{text}`。"]


def infer_assertions(seed: dict, semantics: SeedSemantics) -> list[str]:
    assertions: list[str] = []
    for expected in seed["expected"]:
        for fragment in split_phrases(expected):
            assertions.extend(assertion_from_fragment(fragment, semantics))
    deduped: list[str] = []
    for item in assertions:
        if item not in deduped:
            deduped.append(item)
    return deduped or ["结果是否符合原始 BITS 预期。"]


def render_markdown(args: argparse.Namespace, seeds: list[dict], knowledge_lines: list[str]) -> str:
    today = date.today().isoformat()
    rendered_cases: list[dict] = []
    business_order: list[str] = []
    business_seen: set[str] = set()
    type_counts = {case_type: 0 for case_type in CASE_TYPE_ORDER}
    business_counts: dict[str, int] = {}
    business_type_counts: dict[str, dict[str, int]] = {}

    for index, seed in enumerate(seeds, start=1):
        semantics = parse_seed_semantics(seed, knowledge_lines)
        business_dir = primary_business_dir(seed)
        case_type = classify_case(seed, semantics)
        rendered_cases.append(
            {
                "index": index,
                "seed": seed,
                "semantics": semantics,
                "business_dir": business_dir,
                "case_type": case_type,
            }
        )
        type_counts[case_type] += 1
        business_counts[business_dir] = business_counts.get(business_dir, 0) + 1
        if business_dir not in business_type_counts:
            business_type_counts[business_dir] = {item: 0 for item in CASE_TYPE_ORDER}
        business_type_counts[business_dir][case_type] += 1
        if business_dir not in business_seen:
            business_seen.add(business_dir)
            business_order.append(business_dir)

    lines = [
        "---",
        f"title: {args.title}",
        "tags: [ui-case, ai-executable, branch-preserving]",
        f"date: {today}",
        f"last_updated: {today}",
        f"suite: {args.module} / Branch Preserving",
        f"module: {args.module}",
    ]
    if args.source_bits_case:
        lines.append(f'source_bits_case: "{args.source_bits_case}"')
    if args.knowledge_base:
        lines.append(f'knowledge_base: "{args.knowledge_base}"')
    lines.extend(
        [
            "---",
            "",
            f"# {args.title}",
            "",
            "> 本文件按分支保留原则生成：每个原始互斥分支单独保留，不压缩 `冷启动/热启动/登录态/实验态` 等分支。",
            "",
            "## Test Kit",
            "",
            f"- 入口原则：优先使用原始分支中已有的 deeplink/openUrl；若缺入口，则从{args.app_home_label}开始补齐页面链路。",
            "- 路径原则：优先按 BITS 脑图里的页面层级、分组层级和控件层级推导 UI 路径，不在脚本内写业务专属映射表。",
            "- 断言原则：预期统一改写为可观察的 `是否...` 断言，不把动作句直接当断言。",
            "- 缺失知识：若账号、实验组、地区或稳定入口缺失，保留 `TODO-KNOWLEDGE`，但不删除对应分支。",
            "- 结构原则：先按 BITS 一级业务目录分组，再按 `UI类 / 半UI类 / 非UI类` 拆分 case。",
            "- 分类口径：`UI类 Case` 表示存在明确页面链路；`半UI类 Case` 表示依赖 deeplink、系统外入口或缺少完整 UI 路径；`非UI类 Case` 表示以接口、注册、上报、安装等技术验证为主。",
        ]
    )

    if knowledge_lines and args.knowledge_base:
        lines.extend(
            [
                f"- 知识输入：`{args.knowledge_base}`",
            ]
        )
    lines.append("")

    lines.extend(
        [
            "## Business Overview",
            "",
        ]
    )
    for business_dir in business_order:
        counts = business_type_counts[business_dir]
        lines.append(
            f"- `{business_dir}`: `{business_counts[business_dir]}` cases "
            f"(UI: `{counts['UI类 Case']}` / 半UI: `{counts['半UI类 Case']}` / 非UI: `{counts['非UI类 Case']}`)"
        )
    lines.extend(
        [
            "",
            "## Case Type Overview",
            "",
        ]
    )
    for case_type in CASE_TYPE_ORDER:
        lines.append(f"- `{case_type}`: `{type_counts[case_type]}` cases")
    lines.append("")

    for case_type in CASE_TYPE_ORDER:
        typed_cases = [item for item in rendered_cases if item["case_type"] == case_type]
        if not typed_cases:
            continue
        for business_dir in business_order:
            scoped_cases = [
                item for item in typed_cases if item["business_dir"] == business_dir
            ]
            if not scoped_cases:
                continue
            lines.append(f"## {case_type} - {business_dir}")
            lines.append("")
            for item in scoped_cases:
                index = item["index"]
                seed = item["seed"]
                semantics = item["semantics"]
                dir_path = seed.get("feature_path_text") or seed["seed_path_text"]
                lines.append(f"### TC-{index:03d}: {build_title(seed)}")
                lines.append("")
                lines.append(f"- **Priority**: {tc_priority(seed)}")
                lines.append(f"- **Case Type**: {case_type}")
                lines.append(f"- **Business Dir**: {business_dir}")
                lines.append(f"- **Dir**: {format_breadcrumb(dir_path)}")
                tag_text = ", ".join(seed.get("tags") or ["branch-preserving"])
                lines.append(f"- **Tags**: {tag_text}")
                lines.append(f"- **Precondition**: {build_precondition(semantics)}")
                lines.append(f"- **Extra**: {build_extra(semantics)}")
                lines.append(f"- **Remark**: {format_breadcrumb(seed['seed_path_text'])}")
                lines.append("")
                lines.append("#### Steps")
                lines.append("")

                steps = infer_case_steps(semantics, args.app_home_label)
                assertions = infer_assertions(seed, semantics)

                for step_index, step in enumerate(steps, start=1):
                    lines.append(f"{step_index}. {step}")
                    if step_index == len(steps):
                        for assertion in assertions:
                            lines.append(f"   - **预期**：{assertion}")
                lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Summary",
            "",
            f"- 总 cases: `{len(seeds)}`",
            f"- UI类 Case: `{type_counts['UI类 Case']}`",
            f"- 半UI类 Case: `{type_counts['半UI类 Case']}`",
            f"- 非UI类 Case: `{type_counts['非UI类 Case']}`",
            "- 生成原则：`一条原始互斥分支 = 一条独立 case`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    data = load_json(args.input)
    seeds = data["seeds"]
    knowledge_lines = load_knowledge_lines(args.knowledge_base)
    content = render_markdown(args, seeds, knowledge_lines)
    Path(args.output).write_text(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
