#!/usr/bin/env python3
"""Materialize canonical docs bundles for kb-docs-benchmark runs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.eval_helpers import (
    docs_bundle_stats,
    load_docs_bundle,
    normalize_rel_path,
    resolve_doc_root,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle_from_ref(base_dir: Path, ref: str, doc_root: Path, doc_paths: list[str]) -> tuple[str, list[str]]:
    """Materialize the docs bundle for `doc_paths` as they existed at git `ref`.

    Checks out each doc file at `ref` into a temp dir mirroring the doc_root layout,
    then reuses load_docs_bundle so the compare bundle is byte-for-byte identical in
    format to the current-docs bundle (only the doc content differs). Files absent at
    `ref` are reported as missing, exactly like the filesystem path. Returns
    ("", doc_paths) when doc_root is not under base_dir (not a git-tracked path).
    """
    try:
        doc_root_rel = doc_root.relative_to(base_dir).as_posix()
    except ValueError:
        return "", list(doc_paths)
    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)
        for rel in doc_paths:
            norm = normalize_rel_path(rel)
            proc = subprocess.run(
                ["git", "-C", str(base_dir), "show", f"{ref}:{doc_root_rel}/{norm}"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode != 0:
                continue  # absent at ref → load_docs_bundle marks it missing
            dest = tmp_root / norm
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(proc.stdout, encoding="utf-8")
        return load_docs_bundle(tmp_root, doc_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare canonical docs_bundle.md files")
    parser.add_argument("--evals", required=True, type=Path, help="Path to docs/evals/evals.json")
    parser.add_argument("--workspace", required=True, type=Path, help="Benchmark workspace")
    parser.add_argument("--base-dir", required=True, type=Path, help="Repo root for relative doc_root values")
    parser.add_argument(
        "--compare-docs-ref",
        default=None,
        help="Optional git ref (commit/branch/tag). When set, also materialize the docs as they existed "
             "at that ref into docs_bundles_compare/, for a second with_docs_compare answer run. The report "
             "then shows passRate(current docs) vs passRate(ref docs) — e.g. slim before/after when the ref "
             "is the pre-slim commit. No effect on the default with_docs/without_docs flow when unset.",
    )
    args = parser.parse_args()

    evals_path = args.evals.expanduser().resolve()
    workspace = args.workspace.expanduser().resolve()
    base_dir = args.base_dir.expanduser().resolve()
    bundle_dir = workspace / "docs_bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    compare_ref = args.compare_docs_ref
    compare_dir = workspace / "docs_bundles_compare"
    compare_manifest: list[dict] = []
    if compare_ref:
        compare_dir.mkdir(parents=True, exist_ok=True)

    payload = _load_json(evals_path)
    eval_items = payload.get("evals", [])
    manifest: list[dict] = []

    for eval_item in eval_items:
        eval_id = int(eval_item["id"])
        doc_root = resolve_doc_root(str(eval_item["doc_root"]), base_dir)
        doc_paths = list(eval_item.get("doc_paths") or [])
        docs_bundle, missing_docs = load_docs_bundle(doc_root, doc_paths)
        bundle_path = bundle_dir / f"eval-{eval_id}.md"
        bundle_path.write_text(docs_bundle + "\n", encoding="utf-8")
        stats = docs_bundle_stats(docs_bundle)
        manifest.append(
            {
                "eval_id": eval_id,
                "doc_root": str(doc_root),
                "doc_paths": doc_paths,
                "bundle_path": str(bundle_path),
                "missing_docs": missing_docs,
                **stats,
            }
        )

        if compare_ref:
            cmp_bundle, cmp_missing = _bundle_from_ref(base_dir, compare_ref, doc_root, doc_paths)
            cmp_path = compare_dir / f"eval-{eval_id}.md"
            cmp_path.write_text(cmp_bundle + "\n", encoding="utf-8")
            compare_manifest.append(
                {
                    "eval_id": eval_id,
                    "doc_root": str(doc_root),
                    "doc_paths": doc_paths,
                    "compare_ref": compare_ref,
                    "bundle_path": str(cmp_path),
                    "missing_docs": cmp_missing,
                    **docs_bundle_stats(cmp_bundle),
                }
            )

    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[kb-docs-benchmark] wrote {len(manifest)} docs bundle(s) to {bundle_dir}")

    if compare_ref:
        (compare_dir / "manifest.json").write_text(
            json.dumps(compare_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            f"[kb-docs-benchmark] wrote {len(compare_manifest)} compare docs bundle(s) "
            f"(ref={compare_ref}) to {compare_dir}"
        )


if __name__ == "__main__":
    main()
