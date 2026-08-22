"""Pure local helpers for kb-docs-benchmark evaluation artifacts."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGACY_CONFIGURATION_NAMES = {
    "with_docs": "with_docs",
    "without_docs": "without_docs",
}


@dataclass(frozen=True)
class CheckResult:
    assertion_id: str
    text: str
    passed: bool
    evidence: str


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_configuration_name(configuration: str) -> str:
    key = configuration.strip()
    return LEGACY_CONFIGURATION_NAMES.get(key, key)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def validate_doc_root_value(doc_root: str) -> None:
    normalized = doc_root.replace("\\", "/").rstrip("/")
    if normalized.endswith("/docs"):
        raise ValueError(
            f"Invalid eval doc_root: {doc_root}. doc_root must be the module root containing CLAUDE.md and docs/, not the docs directory itself."
        )


def resolve_doc_root(doc_root: str, base_dir: Path) -> Path:
    validate_doc_root_value(doc_root)
    p = Path(doc_root)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


def load_docs_bundle(doc_root: Path, doc_paths: list[str]) -> tuple[str, list[str]]:
    chunks: list[str] = []
    missing: list[str] = []
    for rel in doc_paths:
        p = doc_root / normalize_rel_path(rel)
        if not p.exists() or not p.is_file():
            missing.append(rel)
            continue
        chunks.append(f"=== FILE: {rel} ===\n{read_text(p)}")
    return "\n\n".join(chunks).strip(), missing


def estimate_text_tokens(text: str) -> int:
    """Estimate model tokens when exact per-subagent tokenizer usage is unavailable."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def docs_bundle_stats(text: str) -> dict[str, Any]:
    if not text:
        return {
            "docs_bundle_hash": "",
            "docs_bundle_chars": 0,
            "estimated_docs_tokens": 0,
            "docs_token_estimate_method": "chars_div_4_ceil",
        }
    return {
        "docs_bundle_hash": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
        "docs_bundle_chars": len(text),
        "estimated_docs_tokens": estimate_text_tokens(text),
        "docs_token_estimate_method": "chars_div_4_ceil",
    }


def describe_qa_assertion(assertion: dict[str, Any]) -> str:
    assertion_type = assertion.get("type")
    if assertion_type == "contains":
        return f"Answer contains: {assertion.get('text', '')}"
    if assertion_type == "regex":
        return f"Answer matches regex: {assertion.get('pattern', '')}"
    return f"Unknown assertion type: {assertion_type}"


def eval_qa_assertions(answer: str, assertions: list[dict[str, Any]]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for assertion in assertions:
        assertion_id = str(assertion.get("id") or assertion.get("type") or "assertion")
        assertion_type = assertion.get("type")
        text = describe_qa_assertion(assertion)

        if assertion_type == "contains":
            needle = str(assertion.get("text", ""))
            if not needle.strip():
                results.append(CheckResult(assertion_id, text, False, "Empty contains text"))
                continue
            case_sensitive = bool(assertion.get("case_sensitive", False))
            haystack = answer if case_sensitive else answer.lower()
            needle_cmp = needle if case_sensitive else needle.lower()
            passed = needle_cmp in haystack
            evidence = "Found" if passed else f"Not found: {needle}"
            results.append(CheckResult(assertion_id, text, passed, evidence))
            continue

        if assertion_type == "regex":
            pattern = str(assertion.get("pattern", ""))
            if not pattern.strip():
                results.append(CheckResult(assertion_id, text, False, "Empty regex pattern"))
                continue
            flags = 0
            if not bool(assertion.get("case_sensitive", False)):
                flags |= re.IGNORECASE
            try:
                match = re.search(pattern, answer, flags=flags)
            except re.error as exc:
                results.append(CheckResult(assertion_id, text, False, f"Invalid regex: {exc}"))
                continue
            passed = match is not None
            evidence = f"Matched: {match.group(0)[:120]}" if passed else "No match"
            results.append(CheckResult(assertion_id, text, passed, evidence))
            continue

        results.append(CheckResult(assertion_id, text, False, f"Unknown assertion type: {assertion_type}"))

    return results


def make_eval_dir_name(eval_id: int, question_id: str, question_index: int) -> str:
    safe_question = re.sub(r"[^a-zA-Z0-9_-]+", "-", question_id).strip("-")
    if not safe_question:
        safe_question = f"q{question_index}"
    return f"eval-{eval_id}-{safe_question}"


def normalized_provenance(question: dict[str, Any]) -> dict[str, Any]:
    provenance = question.get("provenance")
    if isinstance(provenance, dict):
        normalized = dict(provenance)
        normalized["type"] = str(normalized.get("type") or "unknown")
        return normalized
    return {"type": "unknown"}
