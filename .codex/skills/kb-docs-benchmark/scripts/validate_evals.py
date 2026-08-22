#!/usr/bin/env python3
"""Validate kb-docs-benchmark eval definitions without calling models."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.eval_helpers import normalize_rel_path, resolve_doc_root, validate_doc_root_value


DOC_PATH_PATTERN = re.compile(r"(^|[`'\"\s(])(?:CLAUDE\.md|docs/(?:[^\s`'\"),]+\.md|evals(?:/|\b)|evals\.json))", re.IGNORECASE)
QA_ASSERTION_TYPES = {"contains", "regex"}
DOCS_ASSERTION_TYPES = {"files_exist", "required_headings", "no_placeholder", "links_resolve", "mermaid_fenced", "max_lines"}


class ValidationError(Exception):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: root must be a JSON object")
    return data


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _error(errors: list[str], location: str, message: str) -> None:
    errors.append(f"{location}: {message}")


def _warn(warnings: list[str], location: str, message: str) -> None:
    warnings.append(f"{location}: {message}")


def _validate_doc_root(
    *,
    eval_item: dict[str, Any],
    eval_index: int,
    base_dir: Path,
    errors: list[str],
    warnings: list[str],
) -> Path | None:
    location = f"evals[{eval_index}].doc_root"
    raw = eval_item.get("doc_root")
    if not isinstance(raw, str) or not raw.strip():
        _error(errors, location, "must be a non-empty string")
        return None

    try:
        validate_doc_root_value(raw)
    except ValueError as exc:
        _error(errors, location, str(exc))
        return None

    doc_root = resolve_doc_root(raw, base_dir)
    raw_path = Path(raw)
    if raw_path.is_absolute() and _is_inside(doc_root, base_dir):
        _warn(warnings, location, "in-repo doc_root should be relative to the repository root; absolute paths are still accepted for compatibility")

    if not doc_root.exists():
        _error(errors, location, f"resolved path does not exist: {doc_root}")
        return doc_root
    if not doc_root.is_dir():
        _error(errors, location, f"resolved path is not a directory: {doc_root}")
        return doc_root

    if not (doc_root / "CLAUDE.md").is_file():
        _warn(warnings, location, "CLAUDE.md is missing")
    if not (doc_root / "docs").is_dir():
        _warn(warnings, location, "docs/ directory is missing")

    return doc_root


def _validate_doc_paths(
    *,
    eval_item: dict[str, Any],
    eval_index: int,
    doc_root: Path | None,
    errors: list[str],
    warnings: list[str],
) -> None:
    location = f"evals[{eval_index}].doc_paths"
    doc_paths = eval_item.get("doc_paths")
    if not isinstance(doc_paths, list) or not all(isinstance(item, str) and item for item in doc_paths):
        _error(errors, location, "must be a list of non-empty relative path strings")
        return

    for idx, rel in enumerate(doc_paths):
        normalized = normalize_rel_path(rel)
        if Path(normalized).is_absolute() or normalized.startswith("../"):
            _error(errors, f"{location}[{idx}]", "must be relative to doc_root and stay inside doc_root")
        if doc_root and not (doc_root / normalized).is_file():
            _warn(warnings, f"{location}[{idx}]", f"file not found under doc_root: {rel}")


def _assertion_text_values(assertion: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("text", "pattern"):
        value = assertion.get(key)
        if isinstance(value, str):
            values.append(value)
    return values


def _validate_assertions(
    *,
    assertions: Any,
    location: str,
    qa_mode: bool,
    errors: list[str],
) -> None:
    if not isinstance(assertions, list):
        _error(errors, location, "must be a list")
        return

    seen_ids: set[str] = set()
    for idx, assertion in enumerate(assertions):
        item_loc = f"{location}[{idx}]"
        if not isinstance(assertion, dict):
            _error(errors, item_loc, "must be an object")
            continue
        assertion_id = assertion.get("id")
        if not isinstance(assertion_id, str) or not assertion_id.strip():
            _error(errors, f"{item_loc}.id", "must be a non-empty string")
        elif assertion_id in seen_ids:
            _error(errors, f"{item_loc}.id", f"duplicate assertion id: {assertion_id}")
        else:
            seen_ids.add(assertion_id)

        if qa_mode:
            assertion_type = assertion.get("type")
            if assertion_type not in QA_ASSERTION_TYPES:
                _error(errors, f"{item_loc}.type", f"unsupported QA assertion type: {assertion_type}; use contains or regex")
            elif assertion_type == "contains":
                text = assertion.get("text")
                if not isinstance(text, str) or not text.strip():
                    _error(errors, f"{item_loc}.text", "contains assertion requires a non-empty text string")
            elif assertion_type == "regex":
                pattern = assertion.get("pattern")
                if not isinstance(pattern, str) or not pattern.strip():
                    _error(errors, f"{item_loc}.pattern", "regex assertion requires a non-empty pattern string")
                else:
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        _error(errors, f"{item_loc}.pattern", f"invalid regex: {exc}")
            for value in _assertion_text_values(assertion):
                if DOC_PATH_PATTERN.search(value):
                    _error(errors, item_loc, "QA assertions must not check for docs path mentions")
        else:
            assertion_type = assertion.get("type")
            if assertion_type not in DOCS_ASSERTION_TYPES:
                _error(errors, f"{item_loc}.type", f"unsupported docs assertion type: {assertion_type}")


def _validate_questions(
    *,
    questions: Any,
    eval_index: int,
    errors: list[str],
) -> None:
    location = f"evals[{eval_index}].questions"
    if not isinstance(questions, list) or not questions:
        _error(errors, location, "must be a non-empty list for qa mode")
        return

    seen_ids: set[str] = set()
    for idx, question in enumerate(questions):
        q_loc = f"{location}[{idx}]"
        if not isinstance(question, dict):
            _error(errors, q_loc, "must be an object")
            continue

        question_id = question.get("id")
        if not isinstance(question_id, str) or not question_id.strip():
            _error(errors, f"{q_loc}.id", "must be a non-empty string")
        elif question_id in seen_ids:
            _error(errors, f"{q_loc}.id", f"duplicate question id: {question_id}")
        else:
            seen_ids.add(question_id)

        if not isinstance(question.get("question"), str) or not question.get("question", "").strip():
            _error(errors, f"{q_loc}.question", "must be a non-empty string")

        provenance = question.get("provenance")
        if provenance is not None:
            if not isinstance(provenance, dict):
                _error(errors, f"{q_loc}.provenance", "must be an object when present")
            elif not isinstance(provenance.get("type"), str) or not provenance.get("type", "").strip():
                _error(errors, f"{q_loc}.provenance.type", "must be a non-empty string")

        for optional_list_key in ("topics", "source_files"):
            value = question.get(optional_list_key)
            if value is not None and (not isinstance(value, list) or not all(isinstance(item, str) for item in value)):
                _error(errors, f"{q_loc}.{optional_list_key}", "must be a list of strings when present")

        _validate_assertions(
            assertions=question.get("assertions"),
            location=f"{q_loc}.assertions",
            qa_mode=True,
            errors=errors,
        )


def validate_evals(evals_path: Path, base_dir: Path) -> tuple[list[str], list[str]]:
    data = _load_json(evals_path)
    errors: list[str] = []
    warnings: list[str] = []

    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        _error(errors, "evals", "must be a non-empty list")
        return errors, warnings

    seen_eval_ids: set[int] = set()
    for eval_index, eval_item in enumerate(evals):
        location = f"evals[{eval_index}]"
        if not isinstance(eval_item, dict):
            _error(errors, location, "must be an object")
            continue

        eval_id = eval_item.get("id")
        if not isinstance(eval_id, int):
            _error(errors, f"{location}.id", "must be an integer")
        elif eval_id in seen_eval_ids:
            _error(errors, f"{location}.id", f"duplicate eval id: {eval_id}")
        else:
            seen_eval_ids.add(eval_id)

        if not isinstance(eval_item.get("name"), str) or not eval_item.get("name", "").strip():
            _error(errors, f"{location}.name", "must be a non-empty string")

        mode = str(eval_item.get("mode") or "docs")
        if mode not in {"docs", "qa"}:
            _error(errors, f"{location}.mode", "must be 'docs' or 'qa'")

        doc_root = _validate_doc_root(
            eval_item=eval_item,
            eval_index=eval_index,
            base_dir=base_dir,
            errors=errors,
            warnings=warnings,
        )
        _validate_doc_paths(
            eval_item=eval_item,
            eval_index=eval_index,
            doc_root=doc_root,
            errors=errors,
            warnings=warnings,
        )

        if mode == "qa":
            _validate_questions(questions=eval_item.get("questions"), eval_index=eval_index, errors=errors)
        else:
            _validate_assertions(
                assertions=eval_item.get("assertions", []),
                location=f"{location}.assertions",
                qa_mode=False,
                errors=errors,
            )

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate kb-docs-benchmark evals.json")
    parser.add_argument("--evals", required=True, type=Path, help="Path to evals.json")
    parser.add_argument("--base-dir", type=Path, default=Path.cwd(), help="Repository root used to resolve relative doc_root paths")
    args = parser.parse_args()

    evals_path = args.evals.expanduser().resolve()
    base_dir = args.base_dir.expanduser().resolve()
    errors, warnings = validate_evals(evals_path, base_dir)

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)

    print(f"[kb-docs-benchmark] evals valid: {evals_path}")


if __name__ == "__main__":
    main()
