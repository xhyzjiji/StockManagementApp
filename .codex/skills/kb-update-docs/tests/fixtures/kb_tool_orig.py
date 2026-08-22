#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Optional


REPO_MARKERS = [".git"]
SOURCE_EXTS = {".swift", ".m", ".mm", ".h"}
DOC_FILES = {"workflow.md", "domain.md", "interface.md", "rule.md"}
DEFAULT_EXCLUDES = {
    ".git",
    ".build",
    "Pods",
    "DerivedData",
    "node_modules",
    "bazel-bin",
    "bazel-out",
    "bazel-testlogs",
    "bazel-TikTok",
    ".trae",
    ".seer",
    ".ttkanalyzer",
    "xcuserdata",
}


def _print_output(data, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False))
        return
    if isinstance(data, list):
        for item in data:
            print(item)
        return
    raise TypeError(f"Unsupported output type for text format: {type(data)}")


def repo_root(start: Path) -> Path:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    while True:
        if any((cur / m).exists() for m in REPO_MARKERS):
            return cur
        if cur == cur.parent:
            return start.resolve()
        cur = cur.parent


def iter_files(root: Path, exts: set[str], excludes: set[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            if p.suffix.lower() in exts:
                yield p


SWIFT_TYPE_RE = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|internal|fileprivate|private|open)\s+)?"
    r"(?:(?:final|indirect|dynamic)\s+)?"
    r"(actor|class|struct|enum|protocol|extension|typealias)\s+([A-Za-z_]\w*)"
)
OBJC_TYPE_RE = re.compile(r"^\s*@(interface|protocol)\s+(\w+)")


def _doc_root_for_path(p: Path) -> Optional[Path]:
    if p.name == "CLAUDE.md":
        return p.parent.resolve()
    if p.parent.name == "docs" and p.name in DOC_FILES:
        return p.parent.parent.resolve()
    return None


def _dir_has_docs(dir_path: Path) -> bool:
    if (dir_path / "CLAUDE.md").exists():
        return True
    docs_dir = dir_path / "docs"
    if not docs_dir.is_dir():
        return False
    for name in DOC_FILES:
        if (docs_dir / name).exists():
            return True
    return False


def list_doc_roots(args: argparse.Namespace) -> int:
    repo = repo_root(Path.cwd())
    scan_root = (repo / args.path).resolve() if args.path else repo
    excludes = DEFAULT_EXCLUDES | {"infra"}

    roots: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(scan_root):
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith(".")]
        if "CLAUDE.md" in filenames:
            roots.append(Path(dirpath).resolve())

    roots.sort(key=lambda p: p.as_posix())
    rels = [str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p) for p in roots]
    _print_output(rels, args.format)
    return 0


def list_doc_targets(args: argparse.Namespace) -> int:
    repo = repo_root(Path.cwd())
    scan_root = (repo / args.path).resolve() if args.path else repo
    excludes = DEFAULT_EXCLUDES | {"infra"}

    roots: set[Path] = set()

    if scan_root.is_file():
        root = _doc_root_for_path(scan_root)
        if root:
            roots.add(root)
    else:
        for dirpath, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith(".")]
            d = Path(dirpath)
            if "CLAUDE.md" in filenames:
                roots.add(d.resolve())
                continue
            if d.name == "docs":
                for name in DOC_FILES:
                    if name in filenames:
                        roots.add(d.parent.resolve())
                        break

    out = sorted(roots, key=lambda p: p.as_posix())
    rels = [str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p) for p in out]
    _print_output(rels, args.format)
    return 0


def list_doc_ancestors(args: argparse.Namespace) -> int:
    repo = repo_root(Path.cwd())
    raw = Path(args.path) if args.path else Path(".")
    target = raw if raw.is_absolute() else (repo / raw)
    cur = target.resolve()
    if cur.is_file():
        cur = cur.parent

    roots: list[Path] = []
    while True:
        if _dir_has_docs(cur):
            roots.append(cur.resolve())
        if cur == repo or cur == cur.parent:
            break
        cur = cur.parent

    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in roots:
        if p not in seen:
            seen.add(p)
            uniq.append(p)

    rels = [str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p) for p in uniq]
    _print_output(rels, args.format)
    return 0


def scan_types(args: argparse.Namespace) -> int:
    repo = repo_root(Path.cwd())
    root = (repo / args.path).resolve() if args.path else repo
    excludes = DEFAULT_EXCLUDES

    counts: dict[str, int] = {}
    kinds: dict[str, str] = {}
    first_seen: dict[str, str] = {}

    for p in iter_files(root, SOURCE_EXTS, excludes):
        try:
            rel = str(p.relative_to(repo))
        except ValueError:
            rel = str(p)
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            m = SWIFT_TYPE_RE.match(line)
            if m:
                kind = m.group(1)
                name = m.group(2)
                counts[name] = counts.get(name, 0) + 1
                kinds.setdefault(name, kind)
                first_seen.setdefault(name, rel)
                continue
            m = OBJC_TYPE_RE.match(line)
            if m:
                kind = m.group(1)
                name = m.group(2)
                counts[name] = counts.get(name, 0) + 1
                kinds.setdefault(name, f"objc-{kind}")
                first_seen.setdefault(name, rel)

    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[: args.max_items]
    if args.format == "json":
        out = [
            {
                "name": name,
                "kind": kinds.get(name, "type"),
                "count": cnt,
                "first_seen": first_seen.get(name, "-"),
            }
            for name, cnt in items
        ]
        _print_output(out, args.format)
        return 0

    for name, cnt in items:
        print(f"- {name} ({kinds.get(name, 'type')}, {cnt}, {first_seen.get(name, '-')})")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kb_tool.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=["text", "json"], default="text")

    p_list_roots = sub.add_parser("list-doc-roots", parents=[common])
    p_list_roots.add_argument("--path", default=".")
    p_list_roots.set_defaults(func=list_doc_roots)

    p_list_targets = sub.add_parser("list-doc-targets", parents=[common])
    p_list_targets.add_argument("--path", default=".")
    p_list_targets.set_defaults(func=list_doc_targets)

    p_list_ancestors = sub.add_parser("list-doc-ancestors", parents=[common])
    p_list_ancestors.add_argument("--path", default=".")
    p_list_ancestors.set_defaults(func=list_doc_ancestors)

    p_scan_types = sub.add_parser("scan-types", parents=[common])
    p_scan_types.add_argument("--path", default=".")
    p_scan_types.add_argument("--max-items", type=int, default=40)
    p_scan_types.set_defaults(func=scan_types)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
