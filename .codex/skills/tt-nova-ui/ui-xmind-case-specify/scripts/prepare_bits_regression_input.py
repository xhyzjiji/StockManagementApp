#!/usr/bin/env python3
"""
Prepare BITS/bytest cases for ui-xmind-case-specify regression mode.

This script normalizes two possible inputs into a single intermediate JSON:
1. Raw bytest case detail JSON fetched from gdpa-cli bytest_case
2. Extracted branch JSON produced by ../ui-md-case-gen/scripts/extract_bits_case.py

Output is a regression-friendly JSON object with flattened case rows plus the
original structured lists, so the spec skill can consume it with minimal agent
interpretation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
EXTRACT_SCRIPT = ROOT.parent.parent / "ui-md-case-gen" / "scripts" / "extract_bits_case.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to raw bytest JSON or extracted seeds JSON")
    parser.add_argument(
        "--input-kind",
        choices=("auto", "bytest", "extracted"),
        default="auto",
        help="Input type. 'auto' detects by file content.",
    )
    parser.add_argument(
        "--focus",
        default="",
        help="Optional comma-separated focus keywords, only used when input-kind is bytest or auto->bytest.",
    )
    parser.add_argument(
        "--match",
        choices=("any", "all"),
        default="all",
        help="Focus keyword matching mode when extracting raw bytest JSON.",
    )
    parser.add_argument("--output", help="Optional output path. Prints to stdout if omitted.")
    parser.add_argument(
        "--tmp-dir",
        default="",
        help="Temporary working directory for extracted JSON. Recommended: <repo_root>/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-specify/",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def looks_like_extracted(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("seeds"), list)


def looks_like_bytest(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if "TestCaseMind" in payload:
        return True
    data = payload.get("data")
    return isinstance(data, dict) and "TestCaseMind" in data


def normalize_priority(priority: Any) -> str | None:
    if not isinstance(priority, int):
        return None
    if priority >= 90:
        return "P0"
    if priority >= 70:
        return "P1"
    if priority >= 50:
        return "P2"
    return "P3"


def strip_root(path_parts: list[str]) -> list[str]:
    if not path_parts:
        return []
    if len(path_parts) >= 2:
        return path_parts[1:]
    return path_parts[:]


def join_nonempty(parts: list[str], sep: str) -> str:
    cleaned = [str(item).strip() for item in parts if str(item).strip()]
    return sep.join(cleaned)


def build_precond_list(seed: dict[str, Any]) -> list[str]:
    items: list[str] = []
    feature_path = strip_root(seed.get("feature_path", []))
    if feature_path:
        # Treat all non-leaf feature nodes as entry-state context.
        items.extend(feature_path)
    note = str(seed.get("note") or "").strip()
    if note:
        items.append(f"备注：{note}")
    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def build_case_row(seed: dict[str, Any], index: int) -> dict[str, Any]:
    step_list = [str(item.get("step") or "").strip() for item in seed.get("steps", []) if str(item.get("step") or "").strip()]
    expected_list = [str(item).strip() for item in seed.get("expected", []) if str(item).strip()]
    precond_list = build_precond_list(seed)
    feature_path = strip_root(seed.get("feature_path", []))
    seed_path = strip_root(seed.get("seed_path", []))

    module = join_nonempty(feature_path, " / ")
    title = str(seed.get("title") or "").strip() or (seed_path[-1] if seed_path else f"bits_case_{index:04d}")

    byteio_cases = [c for c in (seed.get("byteio_cases") or []) if isinstance(c, dict)]

    return {
        "id": f"bits_{index:04d}",
        "module": module,
        "title": title,
        "precond": join_nonempty(precond_list, "；"),
        "precond_list": precond_list,
        "steps": join_nonempty(step_list, "\n"),
        "step_list": step_list,
        "expected": join_nonempty(expected_list, "；"),
        "expected_list": expected_list,
        "priority": normalize_priority(seed.get("priority")),
        "tags": [str(tag).strip() for tag in seed.get("tags", []) if str(tag).strip()],
        "note": str(seed.get("note") or "").strip() or None,
        # 埋点需求标记：非空时该用例需绑定 et_checker_G20 埋点断言，
        # 参数 byteio_case_list 直接使用本列表（元素含 ID/Name/InvokeNum/AppID/Region）。
        "byteio_cases": byteio_cases,
        "is_byteio_case": bool(byteio_cases),
        "feature_path": feature_path,
        "feature_path_text": join_nonempty(feature_path, " / "),
        "seed_path": seed_path,
        "seed_path_text": join_nonempty(seed_path, " / "),
        "source_seed_path": str(seed.get("seed_path_text") or "").strip(),
        "step_count": len(step_list),
        "expected_count": len(expected_list),
    }


def resolve_tmp_dir(args: argparse.Namespace) -> Path:
    if args.tmp_dir:
        path = Path(args.tmp_dir).expanduser().resolve()
    elif args.output:
        path = Path(args.output).expanduser().resolve().parent
    else:
        path = Path.cwd()
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_extract(raw_input: Path, focus: str, match: str, tmp_dir: Path) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        prefix="ui_xmind_case_specify_bits_extract_",
        suffix=".json",
        dir=tmp_dir,
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)
    cmd = [
        sys.executable,
        str(EXTRACT_SCRIPT),
        "--input",
        str(raw_input),
        "--format",
        "json",
        "--match",
        match,
        "--output",
        str(tmp_path),
    ]
    if focus.strip():
        cmd.extend(["--focus", focus])
    try:
        subprocess.run(cmd, check=True)
        return load_json(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def resolve_extracted(payload: Any, args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.input)
    kind = args.input_kind
    tmp_dir = resolve_tmp_dir(args)
    if kind == "extracted":
        if not looks_like_extracted(payload):
            raise ValueError("input-kind=extracted but file does not look like extracted seeds JSON")
        return payload
    if kind == "bytest":
        return run_extract(input_path, args.focus, args.match, tmp_dir)
    if looks_like_extracted(payload):
        return payload
    if looks_like_bytest(payload):
        return run_extract(input_path, args.focus, args.match, tmp_dir)
    raise ValueError("auto detection failed: input is neither extracted seeds JSON nor raw bytest case JSON")


def build_output(args: argparse.Namespace, extracted: dict[str, Any]) -> dict[str, Any]:
    seeds = extracted.get("seeds", [])
    rows = [build_case_row(seed, idx) for idx, seed in enumerate(seeds, 1)]
    return {
        "source_type": "bits",
        "source_input": str(Path(args.input).resolve()),
        "focus_keywords": extracted.get("focus_keywords", []),
        "match_mode": extracted.get("match_mode", args.match),
        "seed_count": extracted.get("seed_count", len(seeds)),
        "case_count": len(rows),
        "byteio_case_count": sum(1 for row in rows if row.get("is_byteio_case")),
        "cases": rows,
    }


def main() -> int:
    args = parse_args()
    payload = load_json(Path(args.input))
    extracted = resolve_extracted(payload, args)
    output = build_output(args, extracted)
    body = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(body + "\n")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
