#!/usr/bin/env python3
"""Grade answers that were produced by subagent orchestration.

This supports Claude Code / subagent orchestration:

1. The outer agent creates answer.md files under the normal benchmark workspace:
   <workspace>/eval-<eval_id>-<question_id>/<configuration>/run-<n>/outputs/answer.md
2. This script reads those answers, evaluates assertions from evals.json, writes
   grading/timing/manifest artifacts, and regenerates benchmark.json/benchmark.md.

It intentionally does not call any model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, List

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.aggregate_benchmark import generate_benchmark, generate_markdown
from scripts.eval_helpers import (
    canonical_configuration_name,
    docs_bundle_stats,
    eval_qa_assertions,
    load_docs_bundle,
    make_eval_dir_name,
    normalized_provenance,
    read_text,
    resolve_doc_root,
    utc_now,
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_text(path: Path) -> str:
    return read_text(path)


def _parse_configurations(raw: str) -> List[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("at least one configuration is required")
    return values


def _iter_qa_questions(evals_path: Path) -> Iterable[tuple[dict, int, dict]]:
    data = json.loads(evals_path.read_text(encoding="utf-8"))
    for eval_item in data.get("evals") or []:
        if str(eval_item.get("mode") or "docs") != "qa":
            continue
        for question_index, question_item in enumerate(eval_item.get("questions") or []):
            yield eval_item, question_index, question_item


def _docs_leakage_terms(doc_paths: List[str]) -> List[str]:
    terms = {"CLAUDE.md", "docs/evals", "evals.json"}
    for rel in doc_paths:
        normalized = str(rel).replace("\\", "/").lstrip("./")
        terms.add(normalized)
        terms.add(Path(normalized).name)
    return sorted(term for term in terms if term)


def _find_docs_leakage(answer: str, doc_paths: List[str]) -> List[str]:
    answer_lower = answer.lower()
    leaked = []
    for term in _docs_leakage_terms(doc_paths):
        if term.lower() in answer_lower:
            leaked.append(term)
    return leaked


def grade_existing_answers(
    *,
    evals_path: Path,
    workspace: Path,
    configurations: List[str],
    run_number: int,
    base_dir: Path,
    executor_model: str,
    granularity: str,
    allow_partial: bool,
) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    graded = 0
    missing_answers: list[str] = []

    for eval_item, question_index, question_item in _iter_qa_questions(evals_path):
        eval_id = int(eval_item["id"])
        eval_name = str(eval_item.get("name") or f"eval-{eval_id}")
        doc_root = resolve_doc_root(str(eval_item["doc_root"]), base_dir)
        doc_paths = list(eval_item.get("doc_paths") or [])
        docs_bundle, missing_docs = load_docs_bundle(doc_root, doc_paths)

        question_id = str(question_item.get("id") or f"q{question_index + 1}")
        question_text = str(question_item.get("question") or "").strip()
        assertions = list(question_item.get("assertions") or [])
        question_provenance = normalized_provenance(question_item)

        eval_dir = workspace / make_eval_dir_name(eval_id, question_id, question_index)
        derived_eval_id = eval_id * 1000 + question_index
        derived_eval_name = f"{eval_name}::{question_id}"

        eval_metadata = {
            "eval_id": derived_eval_id,
            "base_eval_id": eval_id,
            "eval_name": derived_eval_name,
            "question_id": question_id,
            "question_index": question_index,
            "prompt": question_text,
            "assertions": [assertion.get("id") for assertion in assertions],
            "provenance": question_provenance,
            "doc_root": str(doc_root),
        }
        _write_json(eval_dir / "eval_metadata.json", eval_metadata)

        for configuration in configurations:
            canonical_configuration = canonical_configuration_name(configuration)
            run_dir = eval_dir / canonical_configuration / f"run-{run_number}"
            outputs_dir = run_dir / "outputs"
            answer_path = outputs_dir / "answer.md"
            if not answer_path.exists():
                missing_answers.append(str(answer_path))
                continue

            outputs_dir.mkdir(parents=True, exist_ok=True)
            if not (outputs_dir / "question.md").exists():
                (outputs_dir / "question.md").write_text(question_text + "\n", encoding="utf-8")
            if not (outputs_dir / "prompt.md").exists():
                (outputs_dir / "prompt.md").write_text(question_text + "\n", encoding="utf-8")
            if missing_docs:
                _write_json(outputs_dir / "missing_docs.json", {"missing": missing_docs})

            answer = _read_text(answer_path)
            if canonical_configuration == "with_docs":
                output_docs_bundle_path = outputs_dir / "docs_bundle.md"
                existing_docs_bundle = (
                    _read_text(output_docs_bundle_path)
                    if output_docs_bundle_path.is_file()
                    else ""
                )
                docs_stats = docs_bundle_stats(docs_bundle)
                if existing_docs_bundle != docs_bundle:
                    output_docs_bundle_path.write_text(docs_bundle + "\n", encoding="utf-8")
            else:
                docs_stats = docs_bundle_stats("")
            leakage_terms = []
            if canonical_configuration == "without_docs":
                leakage_terms = _find_docs_leakage(answer, doc_paths)
            check_results = eval_qa_assertions(answer, assertions)
            passed = sum(1 for result in check_results if result.passed)
            total = len(check_results)
            failed = total - passed
            pass_rate = (passed / total) if total else 1.0

            timing_path = run_dir / "timing.json"
            if timing_path.exists():
                try:
                    timing = json.loads(timing_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    timing = {}
            else:
                timing = {}
            timing.setdefault("total_tokens", 0)
            timing.setdefault("duration_ms", 0)
            timing.setdefault("total_duration_seconds", 0.0)
            timing.setdefault("tool_uses", 0)
            timing.setdefault("duration_source", "missing" if int(timing.get("duration_ms") or 0) == 0 else "subagent_usage")
            timing.setdefault("granularity", granularity)
            timing.setdefault("batch_id", "")
            timing.setdefault("batch_index", 0)
            timing.setdefault("batch_size", 0)
            timing.setdefault("batch_question_count", int(timing.get("allocation_count") or 1))
            timing.setdefault("allocation_strategy", "none" if granularity == "cold_start_per_question" else "even")
            timing.setdefault("allocation_count", 1)
            if canonical_configuration == "with_docs":
                timing["docs_bundle_hash"] = docs_stats["docs_bundle_hash"]
                timing["docs_bundle_chars"] = docs_stats["docs_bundle_chars"]
                timing["estimated_docs_tokens"] = docs_stats["estimated_docs_tokens"]
                timing["docs_token_estimate_method"] = docs_stats["docs_token_estimate_method"]
            else:
                if not str(timing.get("docs_bundle_hash") or ""):
                    timing["docs_bundle_hash"] = docs_stats["docs_bundle_hash"]
                if int(timing.get("docs_bundle_chars") or 0) <= 0:
                    timing["docs_bundle_chars"] = docs_stats["docs_bundle_chars"]
                if int(timing.get("estimated_docs_tokens") or 0) <= 0:
                    timing["estimated_docs_tokens"] = docs_stats["estimated_docs_tokens"]
                if not str(timing.get("docs_token_estimate_method") or ""):
                    timing["docs_token_estimate_method"] = docs_stats["docs_token_estimate_method"]
            _write_json(timing_path, timing)

            notes = ["answer generated by subagent orchestration"]
            if leakage_terms:
                notes.append(
                    "without_docs answer may have docs leakage; referenced docs terms: "
                    + ", ".join(leakage_terms)
                )

            grading = {
                "expectations": [
                    {"text": f"[{result.assertion_id}] {result.text}", "passed": result.passed, "evidence": result.evidence}
                    for result in check_results
                ],
                "summary": {
                    "passed": passed,
                    "failed": failed,
                    "total": total,
                    "pass_rate": round(pass_rate, 4),
                },
                "execution_metrics": {
                    "tool_calls": {},
                    "total_tool_calls": int(timing.get("tool_uses") or 0),
                    "total_steps": 1,
                    "errors_encountered": 0,
                    "output_chars": len(answer),
                    "transcript_chars": 0,
                },
                "timing": {
                    "total_duration_seconds": timing["total_duration_seconds"],
                    "total_tokens": timing["total_tokens"],
                },
                "notes": notes,
            }
            _write_json(run_dir / "grading.json", grading)

            run_manifest = {
                "suite_name": "kb-docs-benchmark",
                "eval_id": derived_eval_id,
                "base_eval_id": eval_id,
                "eval_name": derived_eval_name,
                "question_id": question_id,
                "question_index": question_index,
                "question": question_text,
                "question_provenance": question_provenance,
                "configuration": configuration,
                "canonical_configuration": canonical_configuration,
                "include_docs": canonical_configuration == "with_docs",
                "run_number": run_number,
                "doc_root": str(doc_root),
                "doc_paths": doc_paths,
                "missing_docs": missing_docs,
                "docs_leakage_terms": leakage_terms,
                "executor_model": executor_model,
                "duration_ms": timing["duration_ms"],
                "total_duration_seconds": timing["total_duration_seconds"],
                "duration_source": str(timing.get("duration_source") or ""),
                "total_tokens": timing["total_tokens"],
                "tool_uses": int(timing.get("tool_uses") or 0),
                "granularity": str(timing.get("granularity") or granularity),
                "batch_id": str(timing.get("batch_id") or ""),
                "batch_index": int(timing.get("batch_index") or 0),
                "batch_size": int(timing.get("batch_size") or 0),
                "batch_question_count": int(timing.get("batch_question_count") or timing.get("allocation_count") or 1),
                "allocation_strategy": str(timing.get("allocation_strategy") or ""),
                "allocation_count": int(timing.get("allocation_count") or 1),
                "source_total_tokens": int(timing.get("source_total_tokens") or timing.get("total_tokens") or 0),
                "source_duration_ms": int(timing.get("source_duration_ms") or timing.get("duration_ms") or 0),
                "source_tool_uses": int(timing.get("source_tool_uses") or timing.get("tool_uses") or 0),
                "docs_bundle_hash": str(timing.get("docs_bundle_hash") or ""),
                "docs_bundle_chars": int(timing.get("docs_bundle_chars") or 0),
                "estimated_docs_tokens": int(timing.get("estimated_docs_tokens") or 0),
                "docs_token_estimate_method": str(timing.get("docs_token_estimate_method") or ""),
                "assertion_ids": [assertion.get("id") for assertion in assertions],
                "generated_at": utc_now(),
            }
            _write_json(run_dir / "run_manifest.json", run_manifest)
            graded += 1

    print(f"[kb-docs-benchmark] graded {graded} answer(s)")
    if missing_answers:
        print(f"[kb-docs-benchmark] missing {len(missing_answers)} answer(s):", file=sys.stderr)
        for item in missing_answers[:20]:
            print(f"  - {item}", file=sys.stderr)
        if len(missing_answers) > 20:
            print(f"  ... and {len(missing_answers) - 20} more", file=sys.stderr)
        if not allow_partial:
            print("[kb-docs-benchmark] refusing to publish a partial benchmark; pass --allow-partial to override", file=sys.stderr)
            sys.exit(1)

    benchmark = generate_benchmark(workspace, skill_name="kb-docs-benchmark", skill_path=str(workspace))
    _write_json(workspace / "benchmark.json", benchmark)
    (workspace / "benchmark.md").write_text(generate_markdown(benchmark), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade existing answer.md files produced by subagents.")
    parser.add_argument("--evals", required=True, type=Path, help="Path to evals.json")
    parser.add_argument("--workspace", required=True, type=Path, help="Workspace containing answer.md outputs")
    parser.add_argument(
        "--configurations",
        default="without_docs,with_docs",
        help="Comma-separated configuration names to grade (default: without_docs,with_docs)",
    )
    parser.add_argument("--run-number", type=int, default=1)
    parser.add_argument("--base-dir", type=Path, default=Path.cwd(), help="Base dir to resolve relative doc_root paths")
    parser.add_argument("--executor-model", default="subagent", help="Label to record in run_manifest.json")
    parser.add_argument(
        "--granularity",
        choices=["session_batch", "cold_start_per_question"],
        default="session_batch",
        help="Subagent granularity used to generate answers",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow benchmark generation to succeed when some expected answer.md files are missing",
    )
    args = parser.parse_args()

    grade_existing_answers(
        evals_path=args.evals.expanduser().resolve(),
        workspace=args.workspace.expanduser(),
        configurations=_parse_configurations(args.configurations),
        run_number=int(args.run_number),
        base_dir=args.base_dir.expanduser().resolve(),
        executor_model=str(args.executor_model),
        granularity=str(args.granularity),
        allow_partial=bool(args.allow_partial),
    )


if __name__ == "__main__":
    main()
