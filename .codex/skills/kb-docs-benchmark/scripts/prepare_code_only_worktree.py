#!/usr/bin/env python3
"""Prepare isolated workspaces for kb-docs-benchmark answer workers."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.eval_helpers import normalize_rel_path, resolve_doc_root, utc_now


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nstdout: {result.stdout}\nstderr: {result.stderr}")
    return result.stdout.strip()


def _read_evals_doc_paths(evals_path: Path, doc_root_arg: str) -> list[str]:
    data = json.loads(evals_path.read_text(encoding="utf-8"))
    doc_paths: list[str] = []
    for item in data.get("evals") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("doc_root") or "") != doc_root_arg:
            continue
        for rel in item.get("doc_paths") or []:
            if isinstance(rel, str) and rel not in doc_paths:
                doc_paths.append(rel)
    return doc_paths


def _safe_rmtree(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _normalized_path(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def _registered_worktree_paths(repo_root: Path) -> set[str]:
    try:
        output = _run(["git", "worktree", "list", "--porcelain"], cwd=repo_root)
    except RuntimeError:
        return set()

    paths: set[str] = set()
    for line in output.splitlines():
        if not line.startswith("worktree "):
            continue
        paths.add(_normalized_path(Path(line.removeprefix("worktree ").strip())))
    return paths


def _is_registered_worktree(target: Path, repo_root: Path) -> bool:
    return _normalized_path(target) in _registered_worktree_paths(repo_root)


def _remove_existing_target(target: Path, repo_root: Path) -> None:
    if not target.exists() and _is_registered_worktree(target, repo_root):
        _run(["git", "worktree", "prune"], cwd=repo_root)
        if _is_registered_worktree(target, repo_root):
            _run(["git", "worktree", "remove", "--force", str(target)], cwd=repo_root)
        return
    if not target.exists():
        return
    if _is_registered_worktree(target, repo_root):
        _run(["git", "worktree", "remove", "--force", str(target)], cwd=repo_root)
        return
    git_marker = target / ".git"
    if git_marker.exists():
        _run(["git", "worktree", "remove", "--force", str(target)], cwd=repo_root)
    else:
        shutil.rmtree(target)


def _copy_repo(repo_root: Path, target: Path) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in {".git", "__pycache__"}}

    shutil.copytree(repo_root, target, ignore=ignore)


def _doc_root_rel_for_target(doc_root_arg: str, repo_root: Path) -> str:
    resolved_doc_root = resolve_doc_root(doc_root_arg, repo_root).resolve()
    try:
        return str(resolved_doc_root.relative_to(repo_root.resolve()))
    except ValueError:
        return normalize_rel_path(doc_root_arg)


def _remove_paths(target: Path, doc_root_rel: str, remove_paths: list[str]) -> tuple[list[str], list[str]]:
    target_doc_root = target / normalize_rel_path(doc_root_rel)
    removed: list[str] = []
    missing: list[str] = []
    for rel in remove_paths:
        p = target_doc_root / normalize_rel_path(rel)
        if p.exists():
            _safe_rmtree(p)
            removed.append(str(p.relative_to(target)))
        else:
            missing.append(str((target_doc_root / normalize_rel_path(rel)).relative_to(target)))
    return removed, missing


def _remove_code_only_docs(target: Path, doc_root_rel: str, doc_paths: list[str]) -> tuple[list[str], list[str]]:
    remove_paths = ["CLAUDE.md", "docs"]
    for rel in doc_paths:
        normalized = normalize_rel_path(rel)
        if not normalized.startswith("docs/") and normalized not in remove_paths:
            remove_paths.append(normalized)
    return _remove_paths(target, doc_root_rel, remove_paths)


def _remove_evals_only(target: Path, doc_root_rel: str) -> tuple[list[str], list[str]]:
    return _remove_paths(target, doc_root_rel, ["docs/evals"])


def _doc_bundle_removed(target: Path, doc_root_rel: str, doc_paths: list[str]) -> bool:
    target_doc_root = target / normalize_rel_path(doc_root_rel)
    if (target_doc_root / "CLAUDE.md").exists() or (target_doc_root / "docs").exists():
        return False
    return all(not (target_doc_root / normalize_rel_path(rel)).exists() for rel in doc_paths)


def _evals_removed(target: Path, doc_root_rel: str) -> bool:
    target_doc_root = target / normalize_rel_path(doc_root_rel)
    return not (target_doc_root / "docs" / "evals").exists()


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _reuse_existing_manifest(
    *,
    manifest_path: Path,
    code_only_target: Path,
    with_docs_target: Path,
    repo_root: Path,
    doc_root_arg: str,
    doc_root_rel: str,
    source_ref: str,
    doc_paths: list[str],
) -> tuple[dict[str, Any] | None, str]:
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        return None, "missing_or_invalid_manifest"
    if not code_only_target.exists():
        return None, "missing_code_only_worktree"
    if not with_docs_target.exists():
        return None, "missing_with_docs_worktree"
    if str(manifest.get("repo_root")) != str(repo_root):
        return None, "repo_root_changed"
    if str(manifest.get("doc_root")) != doc_root_arg:
        return None, "doc_root_changed"
    if str(manifest.get("source_ref")) != source_ref:
        return None, "source_ref_changed"
    if str(manifest.get("with_docs_root") or "") != str(with_docs_target):
        return None, "with_docs_root_changed"
    if not _doc_bundle_removed(code_only_target, doc_root_rel, doc_paths):
        return None, "docs_bundle_present"
    if not _evals_removed(with_docs_target, doc_root_rel):
        return None, "evals_present_in_with_docs"

    manifest["reused"] = True
    manifest["recreated_reason"] = ""
    manifest["validated_at"] = utc_now()
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest, ""


def prepare_code_only_workspace(
    *,
    repo_root: Path,
    doc_root_arg: str,
    evals_path: Path,
    workspace: Path,
    force: bool,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    workspace = workspace.resolve()
    code_only_target = workspace / "code_only_worktree"
    with_docs_target = workspace / "with_docs_worktree"
    manifest_path = workspace / "isolation_manifest.json"

    if not repo_root.exists() or not repo_root.is_dir():
        raise ValueError(f"repo root does not exist or is not a directory: {repo_root}")

    resolved_doc_root = resolve_doc_root(doc_root_arg, repo_root).resolve()
    doc_root_exists = resolved_doc_root.exists()
    doc_root_rel = _doc_root_rel_for_target(doc_root_arg, repo_root)

    doc_paths = _read_evals_doc_paths(evals_path, doc_root_arg)
    if not doc_paths:
        doc_paths = ["CLAUDE.md", "docs/interface.md", "docs/workflow.md", "docs/domain.md", "docs/rule.md"]

    source_ref = "HEAD"
    isolation = "git_worktree_pair"
    if (repo_root / ".git").exists():
        source_ref = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    else:
        isolation = "copy_pair"

    workspace.mkdir(parents=True, exist_ok=True)
    recreated_reason = "force" if force else ""
    if (code_only_target.exists() or with_docs_target.exists()) and not force:
        reusable, reason = _reuse_existing_manifest(
            manifest_path=manifest_path,
            code_only_target=code_only_target,
            with_docs_target=with_docs_target,
            repo_root=repo_root,
            doc_root_arg=doc_root_arg,
            doc_root_rel=doc_root_rel,
            source_ref=source_ref,
            doc_paths=doc_paths,
        )
        if reusable is not None:
            return reusable
        recreated_reason = reason

    _remove_existing_target(code_only_target, repo_root)
    _remove_existing_target(with_docs_target, repo_root)

    if (repo_root / ".git").exists():
        _run(["git", "worktree", "add", "--detach", str(code_only_target), "HEAD"], cwd=repo_root)
        _run(["git", "worktree", "add", "--detach", str(with_docs_target), "HEAD"], cwd=repo_root)
    else:
        _copy_repo(repo_root, code_only_target)
        _copy_repo(repo_root, with_docs_target)

    code_only_removed, code_only_missing = _remove_code_only_docs(code_only_target, doc_root_rel, doc_paths)
    with_docs_removed, with_docs_missing = _remove_evals_only(with_docs_target, doc_root_rel)
    manifest = {
        "isolation": isolation,
        "code_only_root": str(code_only_target),
        "with_docs_root": str(with_docs_target),
        "repo_root": str(repo_root),
        "doc_root": doc_root_arg,
        "target_doc_root": doc_root_rel,
        "resolved_doc_root": str(resolved_doc_root),
        "doc_root_exists": doc_root_exists,
        "source_ref": source_ref,
        "removed_paths": code_only_removed,
        "missing_paths": code_only_missing,
        "with_docs_removed_paths": with_docs_removed,
        "with_docs_missing_paths": with_docs_missing,
        "created_at": utc_now(),
        "reused": False,
        "recreated_reason": recreated_reason,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Create isolated worktrees for kb-docs-benchmark workers")
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--doc-root", required=True, help="Doc root as written in evals.json, usually repo-root-relative")
    parser.add_argument("--evals", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="Recreate existing isolated worktrees even when reusable")
    args = parser.parse_args()

    manifest = prepare_code_only_workspace(
        repo_root=args.repo_root.expanduser(),
        doc_root_arg=str(args.doc_root),
        evals_path=args.evals.expanduser().resolve(),
        workspace=args.workspace.expanduser(),
        force=bool(args.force),
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
