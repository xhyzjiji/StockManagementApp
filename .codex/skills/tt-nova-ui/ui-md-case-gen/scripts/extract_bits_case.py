#!/usr/bin/env python3
"""
Extract focused branch blocks from a BITS/bytest case JSON file.

The script is intentionally mechanical and branch-first:
- locate TestCaseMind in nested response wrappers
- parse the mind map tree
- expand every leaf branch that ends in expected results into one branch block
- preserve mutually-exclusive branches instead of merging them
- optionally filter by focus keywords
- render normalized JSON or a quick Markdown preview
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


STEP_NODE_TYPES = {6}
EXPECTED_NODE_TYPES = {13}


@dataclass
class SeedStep:
    step: str
    note: str | None
    images: list[str]


@dataclass
class SeedBlock:
    title: str
    seed_path: list[str]
    seed_path_text: str
    feature_path: list[str]
    feature_path_text: str
    priority: int | None
    tags: list[str]
    note: str | None
    steps: list[SeedStep]
    expected: list[str]
    # 埋点需求：从 ByteIOCaseInfo.CaseList[<预期节点id>] 关联到的 ByteIO 埋点用例列表。
    # 非空即表示该 seed 是埋点需求，需要在生成用例时绑定 et_checker_G20 埋点断言。
    byteio_cases: list[dict[str, Any]] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="BITS/bytest JSON file path")
    parser.add_argument(
        "--focus",
        default="",
        help="Comma-separated focus keywords. Example: '开播工具区,ENHANCE,Face'",
    )
    parser.add_argument(
        "--match",
        choices=("any", "all"),
        default="all",
        help="How focus keywords match against branch path text",
    )
    parser.add_argument(
        "--format",
        choices=("json", "md"),
        default="json",
        help="Output format",
    )
    parser.add_argument("--output", help="Optional output path. Prints to stdout if omitted")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def parse_nested_json_string(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def node_payload(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    if isinstance(data, dict):
        return data
    return node


def looks_like_mind_node(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    payload = node_payload(value)
    return "text" in payload and "children" in value


def find_test_case_mind(value: Any) -> Any:
    value = parse_nested_json_string(value)

    if looks_like_mind_node(value):
        return value

    if isinstance(value, dict):
        if "TestCaseMind" in value:
            return find_test_case_mind(value["TestCaseMind"])
        for child in value.values():
            found = find_test_case_mind(child)
            if found is not None:
                return found

    if isinstance(value, list):
        for item in value:
            found = find_test_case_mind(item)
            if found is not None:
                return found

    return None


def find_byteio_case_map(value: Any) -> dict[str, Any]:
    """Locate ByteIOCaseInfo.CaseList ({node_id: [case,...]}) in nested response wrappers.

    Returns an empty dict when no 埋点用例映射 is present.
    """
    value = parse_nested_json_string(value)
    if isinstance(value, dict):
        info = value.get("ByteIOCaseInfo")
        if isinstance(info, dict) and isinstance(info.get("CaseList"), dict):
            return info["CaseList"]
        for child in value.values():
            found = find_byteio_case_map(child)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_byteio_case_map(item)
            if found:
                return found
    return {}


_BYTEIO_CASE_FIELDS = ("ID", "Name", "InvokeNum", "AppID", "Region")


def normalize_byteio_case(case: dict[str, Any]) -> dict[str, Any]:
    """Normalize a ByteIOCaseInfo case object to the field order et_checker expects."""
    normalized: dict[str, Any] = {}
    for key in _BYTEIO_CASE_FIELDS:
        if key in case:
            normalized[key] = case[key]
    for key, val in case.items():
        if key not in normalized:
            normalized[key] = val
    return normalized


def node_id(node: dict[str, Any]) -> str:
    return str(node_payload(node).get("id", "")).strip()


def node_text(node: dict[str, Any]) -> str:
    return str(node_payload(node).get("text", "")).strip()


def node_note(node: dict[str, Any]) -> str | None:
    note = str(node_payload(node).get("note", "")).strip()
    return note or None


def node_tags(node: dict[str, Any]) -> list[str]:
    resource = node_payload(node).get("resource")
    if not isinstance(resource, list):
        return []
    values = []
    for item in resource:
        text = str(item).strip()
        if text:
            values.append(text)
    return values


def node_images(node: dict[str, Any]) -> list[str]:
    image = str(node_payload(node).get("image", "")).strip()
    return [image] if image else []


def node_priority(node: dict[str, Any]) -> int | None:
    priority = node_payload(node).get("priority")
    if isinstance(priority, int) and priority > 0:
        return priority
    return None


def node_type(node: dict[str, Any]) -> int | None:
    value = node_payload(node).get("nodeType")
    return value if isinstance(value, int) else None


def direct_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = node.get("children")
    if isinstance(children, list):
        return [child for child in children if isinstance(child, dict)]
    return []


def priority_from_path(path_nodes: list[dict[str, Any]]) -> int | None:
    for item in reversed(path_nodes):
        priority = node_priority(item)
        if priority is not None:
            return priority
    return None


def tags_from_path(path_nodes: list[dict[str, Any]]) -> list[str]:
    merged: list[str] = []
    for item in path_nodes:
        for tag in node_tags(item):
            if tag not in merged:
                merged.append(tag)
    return merged


def feature_path_from_seed_path(path_nodes: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in path_nodes:
        if node_type(item) in STEP_NODE_TYPES | EXPECTED_NODE_TYPES:
            continue
        text = node_text(item)
        if text:
            values.append(text)
    return values


def build_step_chain(step_nodes: list[dict[str, Any]]) -> list[SeedStep]:
    if step_nodes:
        return [
            SeedStep(
                step=node_text(item),
                note=node_note(item),
                images=node_images(item),
            )
            for item in step_nodes
            if node_text(item)
        ]
    return []


def collect_byteio_cases(
    path_nodes: list[dict[str, Any]],
    expected_nodes: list[dict[str, Any]],
    byteio_map: dict[str, Any],
) -> list[dict[str, Any]]:
    """Collect ByteIO 埋点用例 attached to this branch's expected/leaf nodes.

    ByteIOCaseInfo.CaseList is keyed by mind-map node id; 埋点 is bound at the
    expected (assertion) node in the source case, so we look up expected node ids
    first, then fall back to the current leaf node id.
    """
    if not byteio_map:
        return []
    candidate_ids: list[str] = [node_id(n) for n in expected_nodes]
    if path_nodes:
        candidate_ids.append(node_id(path_nodes[-1]))
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for nid in candidate_ids:
        if not nid or nid not in byteio_map:
            continue
        cases = byteio_map.get(nid) or []
        if not isinstance(cases, list):
            continue
        for case in cases:
            if not isinstance(case, dict):
                continue
            marker = str(case.get("ID") or case.get("Name") or json.dumps(case, sort_keys=True))
            if marker in seen:
                continue
            seen.add(marker)
            collected.append(normalize_byteio_case(case))
    return collected


def make_seed(
    current_node: dict[str, Any],
    path_nodes: list[dict[str, Any]],
    step_nodes: list[dict[str, Any]],
    expected_nodes: list[dict[str, Any]],
    byteio_map: dict[str, Any] | None = None,
) -> SeedBlock:
    seed_path = [node_text(item) for item in path_nodes if node_text(item)]
    feature_path = feature_path_from_seed_path(path_nodes)
    steps = build_step_chain(step_nodes)

    if not steps:
        steps = [
            SeedStep(
                step=node_text(current_node) or "TODO: 原始节点只有预期，没有明确步骤，请人工补齐动作。",
                note=node_note(current_node),
                images=node_images(current_node),
            )
        ]

    title = seed_path[-1] if seed_path else "Untitled"
    return SeedBlock(
        title=title,
        seed_path=seed_path,
        seed_path_text=" / ".join(seed_path),
        feature_path=feature_path,
        feature_path_text=" / ".join(feature_path),
        priority=priority_from_path(path_nodes),
        tags=tags_from_path(path_nodes),
        note=node_note(current_node),
        steps=steps,
        expected=[node_text(item) for item in expected_nodes if node_text(item)],
        byteio_cases=collect_byteio_cases(path_nodes, expected_nodes, byteio_map or {}),
    )


def collect_seed_blocks(
    node: dict[str, Any],
    ancestor_nodes: list[dict[str, Any]],
    step_nodes: list[dict[str, Any]],
    out: list[SeedBlock],
    byteio_map: dict[str, Any] | None = None,
) -> None:
    current_path = ancestor_nodes + [node]
    current_step_nodes = step_nodes + ([node] if node_type(node) in STEP_NODE_TYPES else [])

    children = direct_children(node)
    expected_children = [child for child in children if node_type(child) in EXPECTED_NODE_TYPES]
    non_expected_children = [child for child in children if node_type(child) not in EXPECTED_NODE_TYPES]

    if expected_children:
        out.append(
            make_seed(node, current_path, current_step_nodes, expected_children, byteio_map)
        )

    for child in non_expected_children:
        collect_seed_blocks(child, current_path, current_step_nodes, out, byteio_map)


def focus_keywords(raw_focus: str) -> list[str]:
    return [item.strip().lower() for item in raw_focus.split(",") if item.strip()]


def match_seed(seed: SeedBlock, keywords: list[str], match_mode: str) -> bool:
    if not keywords:
        return True
    haystack = seed.seed_path_text.lower()
    if match_mode == "any":
        return any(keyword in haystack for keyword in keywords)
    return all(keyword in haystack for keyword in keywords)


def render_json(input_path: Path, keywords: list[str], match_mode: str, seeds: list[SeedBlock]) -> str:
    payload = {
        "input": str(input_path),
        "focus_keywords": keywords,
        "match_mode": match_mode,
        "seed_count": len(seeds),
        "byteio_seed_count": sum(1 for seed in seeds if seed.byteio_cases),
        "seeds": [
            {
                **asdict(seed),
                "steps": [asdict(step) for step in seed.steps],
            }
            for seed in seeds
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_md(input_path: Path, keywords: list[str], match_mode: str, seeds: list[SeedBlock]) -> str:
    lines = [
        "# Extracted Branches",
        "",
        f"- Input: `{input_path}`",
        f"- Focus keywords: `{', '.join(keywords) if keywords else '<none>'}`",
        f"- Match mode: `{match_mode}`",
        f"- Branch count: `{len(seeds)}`",
        "",
    ]

    for index, seed in enumerate(seeds, start=1):
        lines.append(f"## {index}. {seed.title}")
        lines.append("")
        lines.append(f"- Branch path: `{seed.seed_path_text}`")
        lines.append(f"- Feature path: `{seed.feature_path_text or '<none>'}`")
        lines.append(f"- Priority: `{seed.priority if seed.priority is not None else 'unknown'}`")
        lines.append(f"- Tags: `{', '.join(seed.tags) if seed.tags else '<none>'}`")
        if seed.note:
            lines.append(f"- Note: {seed.note}")
        lines.append("")
        lines.append("### Steps")
        for step_index, step in enumerate(seed.steps, start=1):
            lines.append(f"{step_index}. {step.step}")
            if step.note:
                lines.append(f"   - Note: {step.note}")
            for image in step.images:
                lines.append(f"   - Image: {image}")
        lines.append("")
        lines.append("### Expected")
        for item in seed.expected:
            lines.append(f"- {item}")
        if seed.byteio_cases:
            lines.append("")
            lines.append("### ByteIO 埋点用例（需绑定 et_checker_G20 埋点断言）")
            for case in seed.byteio_cases:
                lines.append(
                    f"- `{case.get('Name', '')}` (ID={case.get('ID', '')}, "
                    f"AppID={case.get('AppID', '')}, Region={case.get('Region', '')})"
                )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)

    data = load_json(input_path)
    mind = find_test_case_mind(data)
    if mind is None:
        print("error: unable to locate TestCaseMind in input JSON", file=sys.stderr)
        return 1

    byteio_map = find_byteio_case_map(data)

    seeds: list[SeedBlock] = []
    collect_seed_blocks(mind, [], [], seeds, byteio_map)

    keywords = focus_keywords(args.focus)
    filtered = [seed for seed in seeds if match_seed(seed, keywords, args.match)]

    if args.format == "json":
        rendered = render_json(input_path, keywords, args.match, filtered)
    else:
        rendered = render_md(input_path, keywords, args.match, filtered)

    if args.output:
        Path(args.output).write_text(rendered)
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
