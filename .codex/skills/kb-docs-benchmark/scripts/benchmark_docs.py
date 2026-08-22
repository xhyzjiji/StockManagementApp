#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.aggregate_benchmark import generate_benchmark, generate_markdown
from scripts.eval_helpers import (
    normalize_rel_path as _normalize_rel_path,
    read_text as _read_text,
    resolve_doc_root as _resolve_doc_root,
)


@dataclass(frozen=True)
class AssertionResult:
    assertion_id: str
    text: str
    passed: bool
    evidence: str


def _describe_assertion(a: dict[str, Any]) -> str:
    a_type = a.get("type")
    if a_type == "files_exist":
        paths = list(a.get("paths", []))
        return "Required files exist: " + ", ".join(paths)
    if a_type == "required_headings":
        path = str(a.get("path", ""))
        headings = list(a.get("headings", []))
        return f"{path} contains required headings: " + ", ".join(headings)
    if a_type == "no_placeholder":
        patterns = list(a.get("patterns", []))
        return "Docs contain no placeholder patterns: " + ", ".join(patterns)
    if a_type == "links_resolve":
        return "All local markdown links resolve"
    if a_type == "mermaid_fenced":
        return "Mermaid blocks (if present) are fenced properly"
    if a_type == "max_lines":
        path = str(a.get("path", ""))
        max_lines = a.get("max", 0)
        return f"{path} has <= {max_lines} lines"
    return f"Unknown assertion type: {a_type}"


def _safe_output_name(rel_path: str) -> str:
    rel = _normalize_rel_path(rel_path)
    return rel.replace("/", "__")


def _is_local_link(target: str) -> bool:
    target = target.strip()
    if not target:
        return False
    if target.startswith("#"):
        return False
    parsed = urlparse(target)
    if parsed.scheme in {"http", "https", "mailto"}:
        return False
    return True


def _extract_markdown_links(markdown: str) -> list[str]:
    targets: list[str] = []
    for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", markdown):
        targets.append(m.group(1).strip())
    for m in re.finditer(r"<([^ >]+)>", markdown):
        targets.append(m.group(1).strip())
    return targets


def _check_files_exist(doc_root: Path, paths: list[str], assertion_id: str, assertion_text: str) -> AssertionResult:
    missing: list[str] = []
    for rel in paths:
        p = doc_root / _normalize_rel_path(rel)
        if not p.exists():
            missing.append(rel)
    if missing:
        return AssertionResult(assertion_id, assertion_text, False, "Missing: " + ", ".join(missing))
    return AssertionResult(assertion_id, assertion_text, True, "All required files exist")


def _check_required_headings(
    doc_root: Path,
    path: str,
    headings: list[str],
    assertion_id: str,
    assertion_text: str,
) -> AssertionResult:
    p = doc_root / _normalize_rel_path(path)
    if not p.exists():
        return AssertionResult(assertion_id, assertion_text, False, f"File not found: {path}")
    content = _read_text(p)
    missing = [h for h in headings if h not in content]
    if missing:
        return AssertionResult(assertion_id, assertion_text, False, "Missing headings: " + ", ".join(missing))
    return AssertionResult(assertion_id, assertion_text, True, "All required headings found")


def _check_no_placeholder(
    doc_root: Path,
    paths: list[str],
    patterns: list[str],
    assertion_id: str,
    assertion_text: str,
) -> AssertionResult:
    found: list[str] = []
    lowered_patterns = [p.lower() for p in patterns]
    for rel in paths:
        p = doc_root / _normalize_rel_path(rel)
        if not p.exists():
            continue
        content = _read_text(p).lower()
        for pat in lowered_patterns:
            if pat in content:
                found.append(f"{rel}: {pat}")
    if found:
        return AssertionResult(assertion_id, assertion_text, False, "Found placeholders: " + "; ".join(found[:10]))
    return AssertionResult(assertion_id, assertion_text, True, "No placeholder patterns found")


def _check_max_lines(doc_root: Path, path: str, max_lines: int, assertion_id: str, assertion_text: str) -> AssertionResult:
    p = doc_root / _normalize_rel_path(path)
    if not p.exists():
        return AssertionResult(assertion_id, assertion_text, False, f"File not found: {path}")
    line_count = len(_read_text(p).splitlines())
    if line_count > max_lines:
        return AssertionResult(assertion_id, assertion_text, False, f"{path} has {line_count} lines (max {max_lines})")
    return AssertionResult(assertion_id, assertion_text, True, f"{path} has {line_count} lines (<= {max_lines})")


def _check_links_resolve(doc_root: Path, paths: list[str], assertion_id: str, assertion_text: str) -> AssertionResult:
    missing: list[str] = []
    for rel in paths:
        p = doc_root / _normalize_rel_path(rel)
        if not p.exists():
            continue
        content = _read_text(p)
        for target in _extract_markdown_links(content):
            if not _is_local_link(target):
                continue
            path_only = target.split("#", 1)[0].strip()
            if not path_only:
                continue
            resolved = (p.parent / path_only).resolve()
            if not resolved.exists():
                missing.append(f"{rel} -> {target}")
    if missing:
        return AssertionResult(assertion_id, assertion_text, False, "Broken links: " + "; ".join(missing[:10]))
    return AssertionResult(assertion_id, assertion_text, True, "All local links resolve")


def _check_mermaid_fenced(doc_root: Path, paths: list[str], assertion_id: str, assertion_text: str) -> AssertionResult:
    for rel in paths:
        p = doc_root / _normalize_rel_path(rel)
        if not p.exists():
            continue
        in_mermaid = False
        for line in _read_text(p).splitlines():
            stripped = line.strip()
            if not in_mermaid and stripped.startswith("```mermaid"):
                in_mermaid = True
                continue
            if in_mermaid and stripped.startswith("```"):
                in_mermaid = False
                continue
        if in_mermaid:
            return AssertionResult(assertion_id, assertion_text, False, f"Unclosed ```mermaid block in {rel}")
    return AssertionResult(assertion_id, assertion_text, True, "Mermaid blocks (if present) are fenced properly")


def run_assertions(doc_root: Path, assertions: list[dict[str, Any]]) -> list[AssertionResult]:
    results: list[AssertionResult] = []
    for a in assertions:
        assertion_id = str(a.get("id") or a.get("type") or "assertion")
        a_type = a.get("type")
        text = _describe_assertion(a)
        if a_type == "files_exist":
            results.append(_check_files_exist(doc_root, list(a.get("paths", [])), assertion_id, text))
        elif a_type == "required_headings":
            results.append(
                _check_required_headings(
                    doc_root,
                    str(a.get("path", "")),
                    list(a.get("headings", [])),
                    assertion_id,
                    text,
                )
            )
        elif a_type == "no_placeholder":
            results.append(
                _check_no_placeholder(
                    doc_root,
                    list(a.get("paths", [])),
                    list(a.get("patterns", [])),
                    assertion_id,
                    text,
                )
            )
        elif a_type == "max_lines":
            results.append(
                _check_max_lines(
                    doc_root,
                    str(a.get("path", "")),
                    int(a.get("max", 0)),
                    assertion_id,
                    text,
                )
            )
        elif a_type == "links_resolve":
            results.append(_check_links_resolve(doc_root, list(a.get("paths", [])), assertion_id, text))
        elif a_type == "mermaid_fenced":
            results.append(_check_mermaid_fenced(doc_root, list(a.get("paths", [])), assertion_id, text))
        else:
            results.append(AssertionResult(assertion_id, text, False, f"Unknown assertion type: {a_type}"))
    return results


def write_rubric_template(path: Path, eval_name: str, doc_root: Path) -> None:
    content = f"""# Docs Rubric: {eval_name}

Doc root: {doc_root}

Score each item as 0 / 1 / 2 and add short notes.

## A. Cross-cutting (applies to all docs)

| Criterion | Score (0-2) | Notes |
|---|---:|---|
| Locality |  |  |
| Groundedness |  |  |
| Task Usefulness |  |  |
| Signal-to-Noise |  |  |
| Navigability |  |  |
| Stability |  |  |

## B. Per-file rubric

### CLAUDE.md

| Item | Score (0-2) | Notes |
|---|---:|---|
| Module Overview clarity |  |  |
| Key Classes correctness |  |  |
| Coverage |  |  |

### docs/interface.md

| Item | Score (0-2) | Notes |
|---|---:|---|
| Public surface completeness |  |  |
| Contract quality |  |  |
| Usability |  |  |

### docs/workflow.md

| Item | Score (0-2) | Notes |
|---|---:|---|
| Flow correctness |  |  |
| Failure modes |  |  |
| Diagram utility |  |  |

### docs/domain.md

| Item | Score (0-2) | Notes |
|---|---:|---|
| Glossary quality |  |  |
| Concept relationships |  |  |
| Pitfalls/gotchas |  |  |

### docs/rule.md

| Item | Score (0-2) | Notes |
|---|---:|---|
| Module-specific rules |  |  |
| Do/Don’t discriminators |  |  |
| Examples quality |  |  |
"""
    path.write_text(content, encoding="utf-8")


def create_run(
    workspace: Path,
    eval_item: dict[str, Any],
    configuration: str,
    run_number: int,
    base_dir: Path,
) -> Path:
    eval_id = int(eval_item["id"])
    eval_name = str(eval_item.get("name") or f"eval-{eval_id}")
    doc_root = _resolve_doc_root(str(eval_item["doc_root"]), base_dir)

    eval_dir = workspace / f"eval-{eval_id}"
    run_dir = eval_dir / configuration / f"run-{run_number}"
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    eval_metadata = {
        "eval_id": eval_id,
        "eval_name": eval_name,
        "prompt": f"Evaluate generated docs under {doc_root}",
        "assertions": [a.get("id") for a in eval_item.get("assertions", [])],
    }
    (eval_dir / "eval_metadata.json").write_text(json.dumps(eval_metadata, indent=2), encoding="utf-8")

    doc_paths = list(eval_item.get("doc_paths") or [])
    for rel in doc_paths:
        src = doc_root / _normalize_rel_path(rel)
        if not src.exists() or not src.is_file():
            continue
        dst = outputs_dir / _safe_output_name(rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    write_rubric_template(outputs_dir / "rubric.md", eval_name, doc_root)

    assertion_results = run_assertions(doc_root, list(eval_item.get("assertions") or []))
    expectations = [
        {"text": f"[{r.assertion_id}] {r.text}", "passed": r.passed, "evidence": r.evidence}
        for r in assertion_results
    ]

    passed = sum(1 for r in assertion_results if r.passed)
    total = len(assertion_results)
    failed = total - passed
    pass_rate = (passed / total) if total else 1.0

    grading = {
        "expectations": expectations,
        "summary": {
            "passed": passed,
            "failed": failed,
            "total": total,
            "pass_rate": round(pass_rate, 4),
        },
        "execution_metrics": {
            "tool_calls": {},
            "total_tool_calls": 0,
            "total_steps": 1,
            "errors_encountered": 0,
            "output_chars": 0,
            "transcript_chars": 0,
        },
        "timing": {
            "total_duration_seconds": 0.0,
            "total_tokens": 0,
        },
    }
    (run_dir / "grading.json").write_text(json.dumps(grading, indent=2), encoding="utf-8")

    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark documentation sets (doc roots) using programmatic assertions.")
    parser.add_argument("--evals", required=True, type=Path, help="Path to evals.json for docs benchmarking")
    parser.add_argument("--workspace", required=True, type=Path, help="Output workspace directory")
    parser.add_argument("--configuration", default="docs", help="Configuration label (e.g., generated, baseline)")
    parser.add_argument("--run-number", type=int, default=1, help="Run number under the configuration")
    parser.add_argument("--base-dir", type=Path, default=Path.cwd(), help="Base dir to resolve relative doc_root paths")
    parser.add_argument("--write-benchmark", action="store_true", help="Write benchmark.json and benchmark.md into workspace")
    args = parser.parse_args()

    data = json.loads(args.evals.read_text(encoding="utf-8"))
    evals = list(data.get("evals") or [])
    suite_name = str(data.get("suite_name") or "kb-docs-benchmark")

    args.workspace.mkdir(parents=True, exist_ok=True)

    start = time.time()
    for item in evals:
        mode = str(item.get("mode") or "docs")
        if mode == "qa":
            continue
        create_run(args.workspace, item, args.configuration, args.run_number, args.base_dir)
    _ = time.time() - start

    if args.write_benchmark:
        benchmark = generate_benchmark(args.workspace, skill_name=suite_name, skill_path=str(args.workspace))
        (args.workspace / "benchmark.json").write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
        (args.workspace / "benchmark.md").write_text(generate_markdown(benchmark), encoding="utf-8")


if __name__ == "__main__":
    main()
