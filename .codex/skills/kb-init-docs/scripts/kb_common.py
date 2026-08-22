import os
from pathlib import Path
from typing import Iterable, Optional

REPO_MARKERS = [".git"]
MODULE_ANCHORS = [("Modules", 2), ("Vendors", 2)]
SOURCE_EXTS = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".swift",
    ".rs",
}
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
BUILD_MARKERS = {
    "Package.swift",
}
BUILD_GLOBS = [
    "*.podspec",
    "*.xcodeproj",
    "*.xcworkspace",
]


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


def resolve_repo_path(raw: str, repo: Path) -> Path:
    """Resolve CLI inputs as repo-relative paths unless they are absolute.

    Skill scripts are commonly executed from the skill directory, while user
    inputs are documented as repo-relative paths. Prefer the repository root so
    both invocation styles behave the same.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (repo / path).resolve()


def iter_files(root: Path, exts: set[str], excludes: set[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            if p.suffix.lower() in exts:
                yield p


def count_lines(path: Path) -> int:
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def has_build_marker(d: Path) -> bool:
    for name in BUILD_MARKERS:
        if (d / name).exists():
            return True
    for glob_pat in BUILD_GLOBS:
        if any(d.glob(glob_pat)):
            return True
    return False


def first_build_marker_hint(d: Path) -> Optional[str]:
    for name in BUILD_MARKERS:
        if (d / name).exists():
            return name
    for glob_pat in BUILD_GLOBS:
        if any(d.glob(glob_pat)):
            return glob_pat
    return None


def module_anchor_for(path: Path, root: Path) -> Optional[Path]:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    parts = rel.parts
    for anchor, depth in MODULE_ANCHORS:
        if len(parts) >= depth and parts[0] == anchor:
            return (root / Path(*parts[:depth])).resolve()
    return None
