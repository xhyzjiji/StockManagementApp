#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional


REPO_MARKERS = [".git"]
SOURCE_EXTS = {".swift", ".m", ".mm", ".h", ".kt", ".kts", ".java"}
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


def collect_paths(args: argparse.Namespace) -> list[str]:
    """Gather one or more target paths from `--path`. `--path` takes one or more
    values directly (`--path a b c`) and may also be repeated (`--path a --path b`);
    both forms are flattened to a single ordered list. Order is preserved and
    duplicates are dropped, so a single multi-path invocation resolves to exactly
    the same set of targets as looping the original single-path tool over each path.

    When no path is supplied at all, default to ["."] (repo root) — matching the
    original tool's single-path default. Each path is used verbatim downstream
    (no trimming) so single-path resolution stays byte-identical to the original,
    including legitimately whitespace-bearing directory names. An explicitly
    empty / whitespace-only path is rejected loudly rather than silently scanning
    the whole repo (original) or nothing: it almost always means an unset path
    variable expanded into `--path ""`, and silently doing either is a footgun
    for a doc-mutating tool."""
    raw = getattr(args, "path", None)
    if not raw:
        return ["."]

    # action="append" + nargs="+" gives a list of lists; flatten it.
    flat = [p for group in raw for p in group]

    seen: set[str] = set()
    out: list[str] = []
    for p in flat:
        if p.strip() == "":
            raise SystemExit(
                "kb_tool.py: empty/whitespace target path is not allowed "
                "(got an empty --path value). Pass a real path, or omit --path "
                "entirely to default to the repo root."
            )
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _resolve_scan_root(repo: Path, rel: str) -> Path:
    # pathlib returns the RHS unchanged when it is absolute, so this handles
    # both repo-relative and absolute inputs.
    return (repo / rel).resolve()


def _refuse_outside_repo(repo: Path, resolved: Path) -> None:
    if not resolved.is_relative_to(repo.resolve()):
        raise SystemExit(
            f"kb_tool.py: refusing to scan outside the repo (repo={repo.resolve()}, path={resolved}); "
            "pass a repo-relative path. plan-doc-update is the only subcommand that accepts such "
            "paths, and it reports them as uncovered."
        )


def _resolve_scan_root_strict(repo: Path, rel: str) -> Path:
    # For subcommands that WALK the resolved root (list-doc-*, scan-types): a
    # path that resolves outside the repo (absolute input, .., symlink) must be
    # refused loudly instead of traversing the local filesystem at large.
    scan_root = _resolve_scan_root(repo, rel)
    _refuse_outside_repo(repo, scan_root)
    return scan_root


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


def _repo_from_args(args: argparse.Namespace) -> Path:
    """Resolve the repository the tool operates on. `--repo-root` wins; without
    it the root is detected from the current working directory, so the tool MUST
    be invoked from inside the target repo checkout — running it from anywhere
    else (e.g. the skill directory) silently resolves a different repo and every
    changed path comes back `uncovered`."""
    explicit = getattr(args, "repo_root", None)
    if explicit is not None:
        if not explicit.strip():
            raise SystemExit(
                "kb_tool.py: empty --repo-root is not allowed (an unset shell variable "
                "probably expanded to \"\"). Pass a real checkout path, or omit "
                "--repo-root to detect the repo from the cwd."
            )
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"kb_tool.py: --repo-root is not a directory: {explicit}")
        if not any((root / m).exists() for m in REPO_MARKERS):
            raise SystemExit(
                f"kb_tool.py: --repo-root has no repo marker ({', '.join(REPO_MARKERS)}): {explicit}"
            )
        return root
    return repo_root(Path.cwd())


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
# Two negative lookaheads reject non-declarations the bare `@(interface|protocol)\s+(\w+)` counted:
#   - `(?!\s*[;,])` drops `@protocol Foo;` / `@protocol Foo, Bar;` forward declarations
#     (they shadowed the real Swift/ObjC definition and mis-attributed first_seen to the .h);
#   - `(?!\s*(?:<[^>]*>\s*)?\()` drops `@interface Base (Cat)` / `@interface Base ()` categories &
#     extensions, including on a lightweight-generic class `@interface NSArray<T> (Cat)`
#     (e.g. a `GPBMessage (Capsule)` category surfaced GPBMessage as a module type).
# The trailing `\b` blocks the lookaheads from forcing a partial-name backtrack.
OBJC_TYPE_RE = re.compile(r"^\s*@(interface|protocol)\s+(\w+)\b(?!\s*[;,])(?!\s*(?:<[^>]*>\s*)?\()")
KOTLIN_TYPE_RE = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|internal|private|protected|abstract|final|open|sealed|data|inner"
    r"|value|inline|enum|annotation|companion|expect|actual|external|fun)\s+)*"
    r"(class|interface|object|typealias)\s+([A-Za-z_]\w*)"
)
JAVA_TYPE_RE = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed|strictfp)\s+)*"
    r"(class|interface|enum|record)\s+([A-Za-z_]\w*)"
)

# scan-types matchers by file suffix: tuples of (regex, kind_prefix); first match
# per line wins. The Swift→ObjC cascade for the original extensions is frozen
# behavior (e.g. a C++ `class` in a .h is caught by the Swift regex) — keep it.
_DEFAULT_TYPE_MATCHERS = ((SWIFT_TYPE_RE, ""), (OBJC_TYPE_RE, "objc-"))
_TYPE_MATCHERS_BY_SUFFIX = {
    ".kt": ((KOTLIN_TYPE_RE, ""),),
    ".kts": ((KOTLIN_TYPE_RE, ""),),
    ".java": ((JAVA_TYPE_RE, "java-"),),
}


def _doc_root_for_path(p: Path) -> Optional[Path]:
    if p.name == "CLAUDE.md":
        return p.parent.resolve()
    if p.parent.name == "docs" and p.name in DOC_FILES:
        return p.parent.parent.resolve()
    return None


def _exists_safe(p: Path) -> bool:
    """`Path.exists()` that returns False instead of raising on OSError (e.g. a
    marker whose parent dir is unreadable, EACCES), so doc-root detection never
    crashes on an odd filesystem state."""
    try:
        return p.exists()
    except OSError:
        return False


def _dir_has_docs(dir_path: Path) -> bool:
    # _exists_safe (not bare .exists()) so a chmod-000 docs/ never crashes
    # doc-root detection on an odd filesystem state.
    if _exists_safe(dir_path / "CLAUDE.md"):
        return True
    docs_dir = dir_path / "docs"
    if not docs_dir.is_dir():
        return False
    for name in DOC_FILES:
        if _exists_safe(docs_dir / name):
            return True
    return False


def _dir_has_evals(dir_path: Path) -> bool:
    """True if this doc root already ships an evals suite (`docs/evals/evals.json`).

    Used to scope evals-refresh (evals-update v1) to roots that ALREADY have evals —
    keep-fresh only, never create evals where absent (creating from scratch is a
    separate, bigger capability). `_exists_safe` so an odd filesystem state never
    crashes plan resolution, same as `_dir_has_docs`."""
    return _exists_safe(dir_path / "docs" / "evals" / "evals.json")


def _contains_texts(data) -> list[str]:
    """Deduped, sorted `contains`-assertion texts from a parsed evals.json object."""
    syms: set[str] = set()
    for ev in (data.get("evals") or []):
        for q in (ev.get("questions") or []):
            for a in (q.get("assertions") or []):
                if isinstance(a, dict) and a.get("type") == "contains":
                    t = a.get("text")
                    if isinstance(t, str) and t.strip():
                        syms.add(t.strip())
    return sorted(syms)


def _eval_asserted_symbols(evals_path: Path) -> list[str]:
    """The concrete symbols/concepts a root's evals assert via `contains` assertions
    (a class / component / event name, e.g. `PostViewHistoryItemComponent`). A code
    change that renames or removes one of these is what makes an eval stale — the
    cheap, precise static signal for evals-refresh: because these assertions reference
    concrete symbols, a `diff × symbols` check is exact, not a fuzzy guess. Returns the
    RAW texts (natural-language phrases included — real suites mix both kinds); the
    authoritative staleness intersection is `eval-gate`, which additionally applies
    `_is_code_symbol_shaped`. Fail-open: returns [] on any read/parse error so it can
    never break the plan / gate."""
    try:
        # _contains_texts stays INSIDE the try: valid-JSON-wrong-shape files
        # (top-level list, non-dict eval entries) raise AttributeError there,
        # and the fail-open contract covers those exactly like unparseable
        # JSON (Aime P1 on !1270). eval-gate wraps its own copy the same way.
        return _contains_texts(json.loads(evals_path.read_text(encoding="utf-8")))
    except Exception:
        return []


_SYMBOL_SHAPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{2,}$")


def _is_code_symbol_shaped(text: str) -> bool:
    """True when a contains-assertion text looks like a concrete code symbol
    (class / method / event name) rather than a natural-language phrase. Shape
    rule: one identifier-ish token that carries at least one uppercase letter,
    underscore, digit or dot — `PostViewHistoryItemComponent`, `on_event`,
    `Foo.bar` pass; `MUST NOT` (whitespace) and plain lowercase English words
    (`component`) fail. Real suites mix both kinds in `contains` assertions;
    only symbol-shaped texts make the diff × symbols intersection of the
    evals-refresh gate precise instead of a fuzzy text match."""
    return bool(_SYMBOL_SHAPE.match(text)) and bool(re.search(r"[A-Z_0-9.]", text))


# Bare identifier tokens on a diff line (eval-add-signal) — NOT dotted member
# chains: capturing `Foo.bar.baz` whole would surface import filenames
# (`GBLFoo.h`) and method-access noise (`Type.parse`); splitting on `.` instead
# lets the noisy atoms (`h`, `parse`) fall to the shape/base filters while the
# real symbols (the type, a snake_case AB key) survive as their own tokens.
# Over-generates on purpose — `_is_new_symbol_candidate` + base-existence + the
# already-asserted filter narrow it to genuinely new code symbols.
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# All-caps English words that pass the code-symbol shape check (they carry an
# uppercase letter) but are grammatical prose / comment markers, never an
# asserted code symbol. A MINIMAL, high-precision denoiser so eval-add-signal
# output stays readable. Kept DELIBERATELY SHORT — only tokens that are never a
# plausible symbol: WARNING/WARN/NOTE/BUG/IMPORTANT/DEPRECATED/HACK were REMOVED
# because they are real log-level / severity / annotation enum cases (a new
# `Severity.WARNING` case is exactly the untested-new-behavior this gate must
# surface). Pure-caps CODE symbols (JOINED/WAITING, acronym prefixes like GBL)
# are left in; base-existence + docs-updated gate + agent judgment are the real
# precision layers (recall-first).
_PROSE_UPPER = {
    "MUST", "NOT", "AND", "OR", "THE", "FOR", "WITH", "TODO", "FIXME",
}


def _is_new_symbol_candidate(text: str) -> bool:
    """`_is_code_symbol_shaped` plus a minimal prose-directive denoiser (drop
    `MUST`/`NOT`/`TODO`… from added comment lines). See `_PROSE_UPPER`."""
    return _is_code_symbol_shaped(text) and text not in _PROSE_UPPER


# Write-domain allow-list (CASE-SENSITIVE): the only basenames automatic
# distillation may create or write. README.md is deliberately excluded because
# distillation must stay out of files outside this spec, even when the
# target KB already ships them. Enforced deterministically by `enforce-writeset`.
ALLOWED_DOC_BASENAMES = {
    "workflow.md", "domain.md", "interface.md", "rule.md",
    "architecture.md", "CLAUDE.md", "AGENTS.md",
}

# Opt-in extension (`--allow-evals`): a distillation run refreshes a root's evals
# suite in the same run that updates its docs, so the suite must survive the gate.
# Docs and evals describe the same knowledge; letting them drift apart is what
# produces a fake-green benchmark.
#
# 🔴 Deliberately matched by PATH SHAPE, not by basename. A bare `evals.json`
# allow-entry would admit the file anywhere in the tree; the suite has exactly one
# legal home per doc root, and anything calling itself evals.json elsewhere is the
# kind of stray write this gate exists to revert. Keep the hole the exact size of
# the thing that needs to fit through it.
EVALS_SUITE_SUFFIX = "docs/evals/evals.json"


def _is_chain_evals_path(rel: str) -> bool:
    """True for `<doc root>/docs/evals/evals.json` (POSIX-normalised)."""
    norm = rel.replace("\\", "/")
    return norm == EVALS_SUITE_SUFFIX or norm.endswith("/" + EVALS_SUITE_SUFFIX)


def _rels(roots: Iterable[Path], repo: Path) -> list[str]:
    return [str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p) for p in roots]


def _rel1(p: Path, repo: Path) -> str:
    return str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p)


# Directory names that hold a *.podspec but are NOT real pod roots: sample apps,
# test targets, and templates. Treating their podspec as a ceiling would wrongly
# split a group or drop a change into `uncovered`, so they are skipped.
NON_POD_SEGMENTS = {
    "Example", "Examples", "Demo", "Demos", "Sample", "Samples",
    "Tests", "Test", "template", "templates",
}


def _is_ceiling(dir_path: Path, repo: Path) -> bool:
    """A directory the upward walk must never include or climb above: the repo
    root (detected via `.git` by `repo_root`), or an iOS pod root — a directory
    that holds a `*.podspec`. A podspec that lives under an Example / Tests /
    template / Pods-style segment is a sample app, test target or template, not a
    module boundary, so it is NOT treated as a ceiling. Android has no podspecs,
    so only the repo root acts as the ceiling there."""
    if dir_path == repo:
        return True
    try:
        segments = dir_path.relative_to(repo).parts
    except ValueError:
        segments = dir_path.parts
    if any(seg in NON_POD_SEGMENTS or seg in DEFAULT_EXCLUDES for seg in segments):
        return False
    try:
        next(iter(dir_path.glob("*.podspec")))
        return True
    except (StopIteration, OSError):
        return False


def _nearest_doc_root_below_ceiling(start_dir: Path, repo: Path) -> Optional[Path]:
    """Walk up from start_dir (inclusive); return the nearest doc root at or below
    the pod ceiling, or None if the repo root is reached without finding one.

    A doc root co-located with a `*.podspec` (the module's KB living at the pod
    root, e.g. `Vendors/PNSFoundation/{CLAUDE.md,docs}` next to its podspec) is a
    valid leaf: the podspec ceiling only stops the walk from climbing into a
    *parent* pod, it must not hide a doc root sitting in the same directory. So
    `_dir_has_docs` is checked BEFORE the podspec ceiling. The repo root is the one
    hard ceiling that is never itself a doc leaf (checked first)."""
    cur = start_dir.resolve()
    while True:
        if cur == repo:
            return None
        if _dir_has_docs(cur):
            return cur
        if _is_ceiling(cur, repo):
            return None
        if cur == cur.parent:
            return None
        cur = cur.parent


def _is_in_doc_scope(changed_dir: Path, repo: Path) -> bool:
    """True if `changed_dir` is a legitimate home for an allowed doc file: it is
    EITHER a doc root itself (an allowed file like `CLAUDE.md` / `AGENTS.md` sits
    directly at the module root), OR it lives inside a `docs/` directory — at any
    depth — whose owning doc root actually carries docs (so `Mod/docs/rule.md` and
    a deeply nested `Mod/docs/sub/rule.md` are both in scope under the `Mod` root).

    This is deliberately STRICTER than `_nearest_doc_root_below_ceiling`: a stray
    `Mod/notdocs/rule.md` is NOT in scope merely because the sibling `Mod` module
    has a KB — it sits in neither a doc root nor a `docs/` subtree, so it is flagged
    (non-blocking) for the author to eyeball. Walk stops at the pod/repo ceiling."""
    changed_dir = changed_dir.resolve()
    # (1) changed_dir IS the doc root (allowed file directly at the module root).
    if _dir_has_docs(changed_dir):
        return True
    # (2) changed_dir is a module's `docs/` dir, or any descendant of one, whose
    # owning doc root (the `docs/`'s parent) actually carries docs. Walk up looking
    # for the FIRST `docs/` segment on the chain; do NOT accept an arbitrary ancestor
    # doc root reached without passing through a `docs/` (that would let a sibling
    # `notdocs/` ride on the module's KB).
    cur = changed_dir
    while not (_is_ceiling(cur, repo) or cur == repo or cur == cur.parent):
        if cur.name == "docs":
            return _dir_has_docs(cur.parent)
        cur = cur.parent
    return False


def _topmost_doc_root_below_ceiling(start_dir: Path, repo: Path) -> Optional[Path]:
    """Walk up; return the highest doc root that is still strictly below the
    ceiling (the changed file's 'big module' — used to split unrelated groups).

    The ceiling is checked BEFORE docs here, deliberately unlike
    `_nearest_doc_root_below_ceiling`: a doc root co-located with the pod's
    `*.podspec` is intentionally NOT treated as a 'big module', so distinct
    sub-area doc roots under one pod stay in separate groups instead of all
    merging under the pod root. When a co-located pod-root doc is the *only* doc
    root, this returns None and `plan_doc_update` falls back to the leaf (which IS
    the pod root from `_nearest_doc_root_below_ceiling`), so the change is still
    covered — the pod root just isn't used as a grouping key. Do not reorder
    these two checks without also revisiting the grouping tests."""
    cur = start_dir.resolve()
    top: Optional[Path] = None
    while True:
        if _is_ceiling(cur, repo):
            break
        if _dir_has_docs(cur):
            top = cur
        if cur == cur.parent:
            break
        cur = cur.parent
    return top


def list_doc_roots(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    excludes = DEFAULT_EXCLUDES | {"infra"}

    roots: set[Path] = set()
    for rel in collect_paths(args):
        scan_root = _resolve_scan_root_strict(repo, rel)
        for dirpath, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith(".")]
            if "CLAUDE.md" in filenames:
                roots.add(Path(dirpath).resolve())

    out = sorted(roots, key=lambda p: p.as_posix())
    _print_output(_rels(out, repo), args.format)
    return 0


def list_doc_targets(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    excludes = DEFAULT_EXCLUDES | {"infra"}

    roots: set[Path] = set()
    for rel in collect_paths(args):
        scan_root = _resolve_scan_root_strict(repo, rel)
        if scan_root.is_file():
            root = _doc_root_for_path(scan_root)
            if root:
                roots.add(root)
            continue
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
    _print_output(_rels(out, repo), args.format)
    return 0


def list_doc_ancestors(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)

    seen: set[Path] = set()
    ordered: list[Path] = []
    for rel in collect_paths(args):
        raw = Path(rel)
        target = raw if raw.is_absolute() else (repo / raw)
        cur = target.resolve()
        if cur.is_file():
            cur = cur.parent
        _refuse_outside_repo(repo, cur)

        while True:
            if _dir_has_docs(cur):
                root = cur.resolve()
                if root not in seen:
                    seen.add(root)
                    ordered.append(root)
            if cur == repo or cur == cur.parent:
                break
            cur = cur.parent

    _print_output(_rels(ordered, repo), args.format)
    return 0


def scan_types(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    excludes = DEFAULT_EXCLUDES

    counts: dict[str, int] = {}
    kinds: dict[str, str] = {}
    first_seen: dict[str, str] = {}
    scanned: set[Path] = set()

    for rel in collect_paths(args):
        root = _resolve_scan_root_strict(repo, rel)
        for p in iter_files(root, SOURCE_EXTS, excludes):
            rp = p.resolve()
            if rp in scanned:
                continue
            scanned.add(rp)
            try:
                rel_path = str(p.relative_to(repo))
            except ValueError:
                rel_path = str(p)
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            matchers = _TYPE_MATCHERS_BY_SUFFIX.get(p.suffix.lower(), _DEFAULT_TYPE_MATCHERS)
            for line in lines:
                for type_re, kind_prefix in matchers:
                    m = type_re.match(line)
                    if m:
                        kind = m.group(1)
                        name = m.group(2)
                        counts[name] = counts.get(name, 0) + 1
                        kinds.setdefault(name, f"{kind_prefix}{kind}")
                        first_seen.setdefault(name, rel_path)
                        break

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


def plan_doc_update(args: argparse.Namespace) -> int:
    """Resolve a doc-update plan from a set of changed paths (files/dirs).

    For each changed path, find its owning doc root (the nearest doc directory
    below the ceiling). Partition the changed paths by their topmost doc root
    below the ceiling (their "big module"): changes in different big modules form
    independent groups (the independent-group case). Within a group, the umbrella is
    the nearest doc root at/above the group's common ancestor. The per-group
    update set is the umbrella (reviewed for needed edits) plus the leaves (the
    owning doc roots that actually contain code changes). The ceiling — the repo
    root, plus an iOS pod root (a `*.podspec` directory) — is never updated.

    Output (JSON):
      {"groups": [{"umbrella": <root|null>, "leaves": [<root>...],
                   "changed": [<changed path>...]} ...],
       "evals_roots": [<plan root (leaf/umbrella/review_higher) that already
                        ships docs/evals/evals.json> ...],
       "review_higher": [<ancestor doc root above the umbrellas and below the repo
                          root, incl the iOS pod root> ...],
       "uncovered": [<path with no doc root below the ceiling> ...],
       "no_op_reason_hint": "covered_unchanged"|"uncovered"}
    """
    repo = _repo_from_args(args)

    covered: list[tuple[Path, Path, str]] = []  # (changed_dir, leaf_doc_root, rel)
    uncovered: list[str] = []
    rels = collect_paths(args)
    missing = [rel for rel in rels if not _resolve_scan_root(repo, rel).exists()]
    if missing and len(missing) == len(rels):
        # Every single target is absent from the resolved repo: that is not a
        # legitimate "uncovered" outcome, it means the tool is looking at the
        # wrong repository (the root is detected from the cwd). Fail loudly so
        # an automated caller cannot mistake a misconfiguration for a no-op.
        hint = (
            "the root came from --repo-root: check that it points at the intended checkout"
            if getattr(args, "repo_root", None)
            else "the root is detected from the current working directory: cd into the "
                 "target repo checkout (or pass --repo-root <checkout>)"
        )
        raise SystemExit(
            f"kb_tool.py: none of the {len(rels)} target path(s) exist under the resolved repo root "
            f"({repo}) — {hint}, then retry. First missing path: {missing[0]}"
        )
    for rel in rels:
        resolved = _resolve_scan_root(repo, rel)
        changed_dir = (resolved if resolved.is_dir() else resolved.parent).resolve()
        if not changed_dir.is_relative_to(repo):
            # A path outside this repo can never resolve to a doc root we should
            # edit; surface it as uncovered rather than escaping the repo ceiling.
            uncovered.append(rel)
            continue
        if changed_dir == repo:
            # The repo root itself (e.g. an empty/omitted change set defaulting to
            # ".") has no module doc to update — skip it; never report it as a
            # kb-init candidate.
            continue
        leaf = _nearest_doc_root_below_ceiling(changed_dir, repo)
        if leaf is None:
            uncovered.append(rel)
        else:
            covered.append((changed_dir, leaf, rel))

    # Partition by the topmost doc root below the ceiling (the "big module").
    partitions: dict[str, list[tuple[Path, Path, str]]] = {}
    for changed_dir, leaf, rel in covered:
        top = _topmost_doc_root_below_ceiling(changed_dir, repo)
        key = (top if top is not None else leaf).as_posix()
        partitions.setdefault(key, []).append((changed_dir, leaf, rel))

    groups: list[dict] = []
    all_leaves: set[Path] = set()
    all_umbrellas: set[Path] = set()
    for items in partitions.values():
        dirs = [it[0] for it in items]
        leaves: list[Path] = []
        seen: set[Path] = set()
        for _cd, leaf, _rel in items:
            all_leaves.add(leaf)
            if leaf not in seen:
                seen.add(leaf)
                leaves.append(leaf)
        ca = Path(os.path.commonpath([d.as_posix() for d in dirs]))
        umbrella = _nearest_doc_root_below_ceiling(ca, repo)
        if umbrella is not None:
            all_umbrellas.add(umbrella)
        groups.append({
            "umbrella": _rel1(umbrella, repo) if umbrella else None,
            "leaves": sorted(_rel1(x, repo) for x in leaves),
            "changed": sorted({it[2] for it in items}),
        })

    # Higher-level review candidates: ancestor doc roots above the group umbrellas
    # and below the repo root (this includes the iOS pod root, e.g. TikTokSocial).
    # These are reviewed with a rising bar — edit only if the change materially
    # affects that level's overview / architecture / public surface; usually a
    # no-op. The repo root itself is never reviewed or updated.
    review_higher: set[Path] = set()
    # Walk up from every covered leaf. Start the walk AT the leaf, not leaf.parent:
    # when the leaf is itself a co-located pod root (doc root sharing the pod's
    # `*.podspec` dir), the `_is_ceiling` break below must fire ON it so the walk
    # never climbs above the pod and leaks ancestor docs into review_higher. A
    # covered leaf strictly below the ceiling is a standard doc root, so it gets
    # added here but is removed again by `-= all_leaves`.
    for _cd, leaf, _r in covered:
        cur = leaf
        while cur != repo and cur != cur.parent:
            if _dir_has_docs(cur):
                review_higher.add(cur.resolve())
            if _is_ceiling(cur, repo):
                # Reached the pod root (iOS): include its doc above, then stop —
                # never review doc roots above the pod ceiling.
                break
            cur = cur.parent
    review_higher -= all_umbrellas
    review_higher -= all_leaves

    groups.sort(key=lambda g: ((g["umbrella"] or ""), tuple(g["leaves"])))
    # evals-refresh eligibility (evals-update v1): the doc roots in THIS plan that
    # already ship docs/evals/evals.json — leaves, umbrellas AND review_higher
    # ancestors (an evals suite often lives at an aggregate root above the group
    # umbrella; leaving those out would under-report the plan's evals scope). The
    # downstream flow only refreshes evals for these (never creates evals where
    # absent); the actual staleness signal is `eval-gate` (which walks ancestors
    # itself and does not depend on this list), and any refresh lands in a
    # SEPARATE, human-reviewed MR — this list is just the plan-scope report.
    evals_roots = sorted(
        _rel1(p, repo)
        for p in (all_leaves | all_umbrellas | review_higher)
        if _dir_has_evals(p)
    )
    out = {
        "groups": groups,
        "evals_roots": evals_roots,
        "review_higher": sorted(_rel1(p, repo) for p in review_higher),
        "uncovered": sorted(uncovered),
        # Machine-readable hint for the distillation/callback flow to classify a
        # no-op (`groups` empty) outcome WITHOUT re-deriving it: if any changed
        # path resolved to no doc root below the repo ceiling, the no-op is
        # because that path is uncovered (a kb-init candidate); otherwise every
        # change was covered by a doc root that this run left unchanged. The hint
        # is always emitted (it is meaningful only when `groups` is empty, but
        # the caller decides that) so the contract is stable.
        "no_op_reason_hint": "uncovered" if uncovered else "covered_unchanged",
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def eval_symbols(args: argparse.Namespace) -> int:
    """Per requested doc root, the concrete symbols its evals assert (contains-
    assertions). Input = doc roots (repo-relative, via --path); output JSON =
    {root: [symbols]}. The evals-refresh gate (evals-update v1) intersects these with
    an MR's changed symbols: a hit means the change may have made that root's evals
    stale — a per-MR, zero-model static pre-filter that then goes to mandatory human
    review. Roots without evals (or unreadable evals) yield []."""
    repo = _repo_from_args(args)
    out: dict[str, list[str]] = {}
    for rel in collect_paths(args):
        evals_path = _resolve_scan_root(repo, rel) / "docs" / "evals" / "evals.json"
        out[rel] = _eval_asserted_symbols(evals_path)
    print(json.dumps(out, ensure_ascii=False))
    return 0


# Config pinned onto every gate git call so parsing never depends on user/CI
# gitconfig: core.quotepath=false (non-ASCII paths would otherwise come back
# C-quoted and the ancestor walk / pathspec would silently miss those roots).
_GIT_GATE_CFG = ("-c", "core.quotepath=false")
# Flags pinned onto every gate `git diff`: --no-ext-diff/--no-color (an external
# differ like difftastic or forced color replaces/decorates the ±-prefixed lines
# with rc=0 — silent zero hits), --no-renames (rename detection would list only
# the NEW path, dropping the OLD root — a class moved out of a module — from the
# ancestor walk; delete+add is exactly the recall this gate wants).
_GIT_DIFF_FLAGS = ("--no-ext-diff", "--no-color", "--no-renames")


def _git_lines(repo: Path, *argv: str) -> list[str]:
    """Run git in `repo` and return stdout lines. Output is decoded with
    errors='replace' — a changed line carrying non-UTF-8 bytes (legacy GBK
    comments exist in these monorepos) must not crash the gate, and replacement
    chars cannot affect a word-boundary symbol match. A git failure here means
    the gate is misconfigured (bad ref, not a git checkout) — fail loudly,
    mirroring plan-doc-update's all-missing check: a silent [] would read as
    "evals not stale" when the gate simply did not run."""
    r = subprocess.run(["git", "-C", str(repo), *argv], capture_output=True)
    if r.returncode != 0:
        # First non-config token = the subcommand (skip leading `-c k=v` pairs).
        ix = 0
        while ix < len(argv) and argv[ix] == "-c":
            ix += 2
        sub = argv[ix] if ix < len(argv) else argv[0]
        err = (r.stderr or r.stdout or b"").decode("utf-8", errors="replace")
        raise SystemExit(
            f"kb_tool.py: git {sub} failed (rc={r.returncode}) in {repo}: {err.strip()}"
        )
    return r.stdout.decode("utf-8", errors="replace").splitlines()


def _ref_blob(repo: Path, ref: str, rel: str) -> Optional[bytes]:
    """Content of `<ref>:<rel>`, or None when the path does not exist at that
    ref. A missing path is an EXPECTED probe outcome (that dir ships no evals),
    never a loud failure — the gate validates its refs loudly elsewhere."""
    r = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", f"{ref}:{rel}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def _diff_side_lines(diff_lines: list[str], sides: str = "+-") -> str:
    """The ± content lines of a unified diff, joined. Hunk-aware: lines are
    collected only inside a hunk (after `@@`), so `--- a/…` / `+++ b/…` file
    headers are excluded STRUCTURALLY — a prefix test would also eat real
    changed lines whose content starts with `--`/`++` (a removed Lua/SQL
    comment `-- Foo…` renders as `--- Foo…`). `sides` selects which prefixes to
    keep: "+-" = both (staleness, eval-gate), "+" = added only (new-symbol
    detection, eval-add-signal)."""
    out: list[str] = []
    in_hunk = False
    for ln in diff_lines:
        if ln.startswith("diff --git"):
            in_hunk = False
        elif ln.startswith("@@"):
            in_hunk = True
        elif in_hunk and ln and ln[0] in sides:
            out.append(ln[1:])
    return "\n".join(out)


def _changed_diff_lines(diff_lines: list[str]) -> str:
    """Both added and removed content lines of a unified diff (see
    `_diff_side_lines`)."""
    return _diff_side_lines(diff_lines, "+-")


def _changed_evals_roots(repo: Path, base: str, head: str):
    """Shared front half of eval-gate / eval-add-signal. Returns
    (changed_files, root_files, evals_blob) for a git range:
      - changed_files: non-empty `--name-only` paths of base..head;
      - root_files: {evals-bearing ancestor dir (at head) of a changed non-docs
        file -> {changed files under it}} — the same ancestor walk both gates
        use, so they see the identical root set;
      - evals_blob(rel_dir): cached `head:<rel_dir>/docs/evals/evals.json` bytes,
        or None when that dir ships no suite at head.
    Reading suites at `head` (not the worktree) keeps a stale checkout from
    skewing either gate; the `--no-renames`/quotepath/ext-diff flags are pinned
    in `_GIT_GATE_CFG`/`_GIT_DIFF_FLAGS`."""
    changed = [ln for ln in _git_lines(repo, *_GIT_GATE_CFG, "diff",
                                       *_GIT_DIFF_FLAGS, "--name-only", base, head)
               if ln.strip()]
    blob_cache: dict[str, Optional[bytes]] = {}

    def evals_blob(rel_dir: str) -> Optional[bytes]:
        if rel_dir not in blob_cache:
            blob_cache[rel_dir] = _ref_blob(repo, head, rel_dir + "/docs/evals/evals.json")
        return blob_cache[rel_dir]

    root_files: dict[str, set[str]] = {}
    for rel in changed:
        parts = rel.split("/")  # git outputs POSIX paths
        if "docs" in parts[:-1]:
            continue  # inside a docs bundle (incl. docs/evals itself)
        for i in range(len(parts) - 1, 0, -1):
            d = "/".join(parts[:i])
            if evals_blob(d) is not None:
                root_files.setdefault(d, set()).add(rel)
    return changed, root_files, evals_blob


def _symbol_present_at_ref(repo: Path, sym: str, ref: str, root: str) -> bool:
    """True if `sym` (whole-word, literal) appears anywhere in `root` (excluding
    its docs/ bundle) at `ref`. eval-add-signal uses it to drop symbols that
    already existed — only genuinely MR-introduced symbols are add material.
    git grep rc: 0 found / 1 not-found / >=2 error → treat anything but a clean
    "not found" as present (conservative: never invent a new symbol from a grep
    error; base was already validated by the name-only diff in
    `_changed_evals_roots`)."""
    r = subprocess.run(["git", "-C", str(repo), *_GIT_GATE_CFG, "grep", "-qwFI",
                        "-e", sym, ref, "--", root, f":(exclude){root}/docs"],
                       capture_output=True)
    return r.returncode != 1


def eval_gate(args: argparse.Namespace) -> int:
    """evals-update v1 static gate: which doc roots' evals may have gone stale
    because THIS MR touched a code symbol their evals assert.

    Input = a real git range (`--base <ref>`, `--head <ref>` default HEAD).
    Everything is read FROM THE REFS, never from the worktree: evals suites are
    probed and parsed at `<head>:<dir>/docs/evals/evals.json`, so a stale
    checkout (fetched but not checked out at head) cannot skew the result. For
    every changed file OUTSIDE a docs/ bundle (doc/evals edits are maintenance,
    not a staleness signal — this is also the self-loop breaker: an
    evals-refresh MR passes the gate with zero action), walk up its path
    ancestors below the repo root and collect every directory that ships an
    evals suite at head — leaf and umbrella suites are both checked. Per such
    root, intersect its symbol-shaped asserted symbols (`contains` texts ×
    `_is_code_symbol_shaped`) with the root's changed diff lines: added AND
    removed lines, word-boundary match — a removed/renamed symbol is the
    classic staleness, and new code around an asserted symbol can change the
    right answer too. This is a recall-oriented zero-model pre-filter: every
    candidate goes to a mandatory human review in a SEPARATE evals MR (never
    auto-merged), so an over-flag costs one review minute while a miss ships a
    fake-green eval.

    Output JSON: {"base", "head", "changed_file_count",
      "checked_roots": [roots with an evals suite seen on ancestor walks],
      "unreadable_evals": [checked roots whose evals.json failed to parse —
        surfaced instead of silently treated as no-signal],
      "candidates": [{"root", "hit_symbols", "changed_files"} ...]}.
    Empty candidates → no evals action for this MR. Misconfiguration (bad ref /
    not a git checkout) fails loudly — a silent [] would read as "evals not
    stale" when the gate simply did not run."""
    repo = _repo_from_args(args)
    base, head = args.base, args.head
    changed, root_files, evals_blob = _changed_evals_roots(repo, base, head)
    checked_roots: list[str] = []
    unreadable: list[str] = []
    candidates: list[dict] = []
    for root in sorted(root_files):
        checked_roots.append(root)
        try:
            data = json.loads(evals_blob(root).decode("utf-8", errors="replace"))
            texts = _contains_texts(data)
        except Exception:
            unreadable.append(root)  # surfaced in output, root stays non-candidate
            continue
        syms = [s for s in texts if _is_code_symbol_shaped(s)]
        if not syms:
            continue
        files = sorted(root_files[root])
        diff_lines = _git_lines(repo, *_GIT_GATE_CFG, "diff", *_GIT_DIFF_FLAGS,
                                "-U0", base, head, "--",
                                *(f":(literal){f}" for f in files))
        changed_text = _changed_diff_lines(diff_lines)
        hits = [s for s in syms
                if re.search(r"\b" + re.escape(s) + r"\b", changed_text)]
        if hits:
            candidates.append({
                "root": root,
                "hit_symbols": hits,
                "changed_files": files,
            })
    out = {
        "base": base,
        "head": head,
        "changed_file_count": len(changed),
        "checked_roots": checked_roots,
        "unreadable_evals": unreadable,
        "candidates": candidates,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


_NEW_SYMBOL_CAP = 80  # max distinct candidate tokens base-checked per root


def eval_add_signal(args: argparse.Namespace) -> int:
    """evals-update v1.5 ADD signal — the DETERMINISTIC half of "should this MR
    add a NEW eval question?". Mirror of eval-gate's ancestor walk, but instead
    of intersecting the diff with ALREADY-asserted symbols (staleness), it
    surfaces, per evals-root, the code symbols this MR genuinely INTRODUCED that
    no existing eval covers:
      - symbol-shaped tokens on the root's ADDED diff lines,
      - absent from the root's code at base (a real new symbol, not a new
        reference to a pre-existing one),
      - not already in the root's `contains` assertions.
    This is ONLY the trigger, deliberately recall-first (over-surfacing costs one
    agent judgment; under-surfacing ships an untested new behavior — the mirror
    blind spot of staleness). Whether any surfaced symbol DESERVES a question is
    an agent judgment (new public entry / flow / constraint, not a private
    detail); the question itself is authored by kb-evals-creator (the declared
    evals-generation SoT); and both are gated downstream on the distillation
    having actually updated this root's docs — none of that logic lives here.
    Never CREATES a suite where absent (keep-fresh only): a root with no evals
    at head is simply not walked.

    Output JSON: {"base","head","checked_roots","unreadable_evals",
      "capped_roots":[roots whose candidate tokens exceeded the base-check cap —
        surfaced, never silently truncated],
      "add_candidates":[{"root","new_symbols","changed_files"}...]}."""
    repo = _repo_from_args(args)
    base, head = args.base, args.head
    _changed, root_files, evals_blob = _changed_evals_roots(repo, base, head)
    checked_roots: list[str] = []
    unreadable: list[str] = []
    capped: list[str] = []
    add_candidates: list[dict] = []
    for root in sorted(root_files):
        checked_roots.append(root)
        try:
            asserted = set(_contains_texts(
                json.loads(evals_blob(root).decode("utf-8", errors="replace"))))
        except Exception:
            unreadable.append(root)  # surfaced, same contract as eval-gate
            continue
        files = sorted(root_files[root])
        added = _diff_side_lines(
            _git_lines(repo, *_GIT_GATE_CFG, "diff", *_GIT_DIFF_FLAGS, "-U0",
                       base, head, "--", *(f":(literal){f}" for f in files)),
            sides="+")
        cands = sorted({t for t in _TOKEN_RE.findall(added)
                        if _is_new_symbol_candidate(t) and t not in asserted})
        if len(cands) > _NEW_SYMBOL_CAP:
            capped.append(root)
            cands = cands[:_NEW_SYMBOL_CAP]
        new_syms = [t for t in cands
                    if not _symbol_present_at_ref(repo, t, base, root)]
        if new_syms:
            add_candidates.append({
                "root": root,
                "new_symbols": new_syms,
                "changed_files": files,
            })
    out = {
        "base": base,
        "head": head,
        "checked_roots": checked_roots,
        "unreadable_evals": unreadable,
        "capped_roots": capped,
        "add_candidates": add_candidates,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def eval_bootstrap_signal(args: argparse.Namespace) -> int:
    """evals-update v2 — the third gate: a doc root that has NO evals suite at all.

    The freshness gate keeps an existing suite honest; the coverage gate adds a
    question to an existing suite. Both walk ancestors by *evals presence*, so a
    root with no suite is not merely rejected — it is never even visited
    (`_changed_evals_roots` only records a dir when `evals_blob(d) is not None`).
    That leaves the single most common production shape completely untested:
    **docs exist, evals never did**. The whole chain then reports `no_evals` and
    scores nothing, which reads on a dashboard exactly like "benchmark is broken".

    Candidate = the conjunction of three things, none of them optional:
      1. THIS run actually updated that root's docs — same trigger as the
         coverage gate. A new symbol whose knowledge the distillation judged not
         doc-worthy does not deserve an eval either.
      2. The root ships NO `docs/evals/evals.json` at `head` — if it has one,
         this is the other two gates' business, not ours (reported under
         `skipped_have_suite` so the hand-off is visible, never silent).
      3. This MR introduced at least one genuinely new symbol under it — same
         token extraction, same base-existence check, same per-root cap as the
         coverage gate.

    🔴 The candidate roots come in on `--roots`, from the caller. This tool does
    NOT re-derive "what counts as a doc root". The existing ancestor walk finds
    its way by asking "is there an evals suite here?" — the exact question that
    is false by construction here. Re-deriving it would mean a SECOND definition
    of "doc root" living in a second place, and the two would drift; the card-fold
    bug of 2026-08-25 was precisely that shape (a predicate keyed on a proxy that
    a new path quietly falsified). The skill already knows the answer exactly: it
    just edited those directories.

    Output JSON: {"base","head","checked_roots","skipped_have_suite",
      "no_new_symbols","unknown_roots":[roots absent at head],
      "capped_roots","bootstrap_candidates":[{"root","new_symbols","changed_files"}...]}.
    Authoring, discrimination and the write itself all live in SKILL.md — this
    stage stays zero-model and writes nothing."""
    repo = _repo_from_args(args)
    base, head = args.base, args.head

    roots: list[str] = []
    for raw in (args.roots or "").split(","):
        r = raw.strip().strip("/")
        if r and r not in roots:
            roots.append(r)

    changed = [ln for ln in _git_lines(repo, *_GIT_GATE_CFG, "diff",
                                       *_GIT_DIFF_FLAGS, "--name-only", base, head)
               if ln.strip()]

    checked_roots: list[str] = []
    skipped_have_suite: list[str] = []
    no_new_symbols: list[str] = []
    unknown_roots: list[str] = []
    capped: list[str] = []
    bootstrap: list[dict] = []

    for root in roots:
        # A root that does not exist at head is a caller mistake (wrong ref /
        # stale plan), not "nothing to do" — surface it instead of returning a
        # quiet empty result that reads like a clean bill of health.
        if _ref_blob(repo, head, root + "/CLAUDE.md") is None and \
                not _git_lines(repo, *_GIT_GATE_CFG, "ls-tree", "--name-only", head, root + "/"):
            unknown_roots.append(root)
            continue
        checked_roots.append(root)
        if _ref_blob(repo, head, root + "/docs/evals/evals.json") is not None:
            skipped_have_suite.append(root)
            continue
        files = sorted(
            rel for rel in changed
            if (rel == root or rel.startswith(root + "/"))
            and "docs" not in rel.split("/")[:-1]  # skip the docs bundle itself
        )
        if not files:
            no_new_symbols.append(root)
            continue
        added = _diff_side_lines(
            _git_lines(repo, *_GIT_GATE_CFG, "diff", *_GIT_DIFF_FLAGS, "-U0",
                       base, head, "--", *(f":(literal){f}" for f in files)),
            sides="+")
        cands = sorted({t for t in _TOKEN_RE.findall(added)
                        if _is_new_symbol_candidate(t)})
        if len(cands) > _NEW_SYMBOL_CAP:
            capped.append(root)
            cands = cands[:_NEW_SYMBOL_CAP]
        new_syms = [t for t in cands
                    if not _symbol_present_at_ref(repo, t, base, root)]
        if new_syms:
            bootstrap.append({
                "root": root,
                "new_symbols": new_syms,
                "changed_files": files,
            })
        else:
            no_new_symbols.append(root)

    out = {
        "base": base,
        "head": head,
        "checked_roots": checked_roots,
        "skipped_have_suite": skipped_have_suite,
        "no_new_symbols": no_new_symbols,
        "unknown_roots": unknown_roots,
        "capped_roots": capped,
        "bootstrap_candidates": bootstrap,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# enforce-writeset: deterministic, file-level write-domain guard.
#
# Two-phase, baseline-anchored so it is safe to run on a dirty checkout (local)
# AND in CI, and only ever touches THIS run's edits:
#   1. --snapshot  (BEFORE the skill edits docs): record the baseline = the set
#      of paths git already reports dirty/untracked. These are user/unrelated
#      changes the guard must never touch.
#   2. --apply     (AFTER the skill edits docs): re-read git status; this run's
#      changes = current dirty/untracked set MINUS the baseline. For each, revert
#      it unless it is an allowed basename.
# ---------------------------------------------------------------------------
DEFAULT_BASELINE_RELPATH = os.path.join(".git", "kb-writeset-baseline.json")


def _git_status_entries(repo: Path) -> dict[str, str]:
    """Map repo-relative path -> 2-char porcelain status code for everything git
    reports as changed. Parsed from
    `git status --porcelain -z --untracked-files=all`.

    porcelain -z format: each entry is `XY <path>\0`; a rename/copy (status code
    starting R or C in either column) is `XY <new>\0<old>\0` — we key on the NEW
    path (what now exists on disk) and drop the OLD token. A pure deletion
    (status `D`, file gone) is skipped: there is nothing on disk to revert and it
    cannot be a doc we wrote. Untracked entries carry code `??`.

    A path can appear TWICE in one status output: `git rm --cached <p>` (or an
    index-only delete) leaves the file on disk, so git emits BOTH `D  <p>` (index
    deletion) AND `?? <p>` (now-untracked worktree file). That `??` is NOT a file
    this run created — it is a pre-existing committed file the index forgot, and
    treating it as "new untracked" would let the guard `rm` a real committed file
    if its basename is out-of-domain. So deletions are collected FIRST, and a `??`
    whose path was also reported deleted is dropped.

    Refuses loudly (SystemExit) if git is unavailable or `repo` is not a git
    repo: a write-domain guard must never silently pass through.
    """
    if not (repo / ".git").exists():
        raise SystemExit(
            f"kb_tool.py enforce-writeset: not a git repository (no .git at {repo}). "
            "This guard requires git; refusing to run."
        )
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "-z",
             "--untracked-files=all"],
            capture_output=True, check=True,
        )
    except FileNotFoundError:
        raise SystemExit(
            "kb_tool.py enforce-writeset: `git` executable not found on PATH; "
            "refusing to run (this guard requires git)."
        )
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", "replace").strip() if e.stderr else ""
        raise SystemExit(
            f"kb_tool.py enforce-writeset: `git status` failed (rc={e.returncode}): {msg}"
        )

    raw = proc.stdout.decode("utf-8", "replace")
    return _parse_porcelain_z(raw)


def _parse_porcelain_z(raw: str) -> dict[str, str]:
    """Pure parser for `git status --porcelain -z --untracked-files=all` output:
    map repo-relative path -> 2-char status code. Split out from
    `_git_status_entries` so the rename/copy/delete edge cases can be unit-tested
    against synthetic streams without coaxing real git into emitting a `C` (copy)
    code, which it does only under copy detection."""
    # Split on NUL. A trailing NUL yields a final empty token we drop.
    tokens = [t for t in raw.split("\0") if t != ""]

    # First pass: parse every porcelain record into (xy, path), correctly
    # consuming the extra OLD-path token a rename/copy emits, and remember which
    # paths git reported as deleted (`D` in either column, no rename).
    parsed: list[tuple[str, str]] = []
    deleted: set[str] = set()
    i = 0
    while i < len(tokens):
        entry = tokens[i]
        if len(entry) < 4:
            # Defensive: every porcelain entry is `XY <space><path>` (>= 4 chars).
            i += 1
            continue
        xy = entry[:2]
        path = entry[3:]
        i += 1
        if xy[0] in ("R", "C") or xy[1] in ("R", "C"):
            # Rename/copy: the NEXT token is the OLD path; consume & ignore it,
            # judge by the NEW path (`path`, already captured above).
            if i < len(tokens):
                i += 1
        # Pure deletion: file no longer on disk → nothing to revert, not a doc we
        # wrote. `D` in either index or worktree column with no rename.
        if xy in ("D ", " D", "DD"):
            deleted.add(path)
            continue
        parsed.append((xy, path))

    # Second pass: build the result. Drop any `??` whose path was ALSO reported
    # deleted — that untracked entry is the on-disk remnant of an index-only
    # delete (`git rm --cached`), a pre-existing committed file, NOT a file this
    # run created. Order-independent: deletions were gathered across the whole
    # output first.
    entries: dict[str, str] = {}
    for xy, path in parsed:
        if xy == "??" and path in deleted:
            continue
        entries[path] = xy
    return entries


def _write_baseline(repo: Path, baseline_path: Path, paths: set[str]) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps({"baseline": sorted(paths)}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_baseline(baseline_path: Path) -> set[str]:
    if not baseline_path.exists():
        raise SystemExit(
            f"kb_tool.py enforce-writeset --apply: baseline file not found at "
            f"{baseline_path}. Run `enforce-writeset --snapshot` BEFORE editing docs."
        )
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(
            f"kb_tool.py enforce-writeset --apply: cannot read baseline {baseline_path}: {e}"
        )
    return set(data.get("baseline", []))


def _revert_path(repo: Path, rel: str, was_tracked: bool) -> None:
    """Undo this run's change to `rel`. A path that existed in the baseline (was
    already dirty as a TRACKED file) is restored with `git checkout --`; a path
    this run newly created (untracked, not in baseline) is removed from disk."""
    if was_tracked:
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "--", rel],
            capture_output=True, check=False,
        )
    else:
        try:
            (repo / rel).unlink()
        except OSError:
            pass


def enforce_writeset(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    baseline_path = (
        Path(args.baseline).expanduser().resolve()
        if getattr(args, "baseline", None)
        else (repo / DEFAULT_BASELINE_RELPATH)
    )

    if args.snapshot:
        baseline = set(_git_status_entries(repo).keys())
        _write_baseline(repo, baseline_path, baseline)
        print(json.dumps({
            "phase": "snapshot",
            "baseline_path": str(baseline_path),
            "baseline": sorted(baseline),
        }, ensure_ascii=False))
        return 0

    # --apply
    baseline = _read_baseline(baseline_path)
    current = _git_status_entries(repo)
    # This run's changes = paths now dirty/untracked that were NOT already dirty in
    # the baseline. Baseline paths are user/unrelated edits the guard never touches.
    this_run = {p: xy for p, xy in current.items() if p not in baseline}

    reverted: list[str] = []
    violations_basename: list[str] = []
    allowed_touched: list[str] = []
    scope_warnings: list[str] = []

    no_revert = getattr(args, "no_revert", False)

    for rel in sorted(this_run):
        abs_path = (repo / rel).resolve()
        changed_dir = abs_path.parent
        basename = abs_path.name
        # `??` = untracked: this run newly created it → revert by `rm`. Anything
        # else is a tracked file → revert by `git checkout --`. This covers the
        # rename/copy-then-modify codes too (`RM`/`MR`/`CM`/`MC`, etc.): the entry
        # is already keyed on the NEW path (the only token that exists on disk),
        # the code is non-`??` so it is tracked, and `git checkout -- <new path>`
        # restores it from the index — undoing the extra worktree modification as
        # well as the rename target's content.
        was_tracked = this_run[rel] != "??"

        # (a0) opt-in: the root's own evals suite, at its one legal path.
        # Still behind an explicit flag even though the skill now passes it by
        # default — the *tool* must not silently gain write power, so that any
        # other caller (and every existing script) keeps the strict 7-basename
        # domain unless it asks. Flag off ⇒ byte-identical to before.
        if getattr(args, "allow_evals", False) and _is_chain_evals_path(rel):
            allowed_touched.append(rel)
            continue

        # (a) basename not in the write-domain allow-list (CASE-SENSITIVE).
        if basename not in ALLOWED_DOC_BASENAMES:
            violations_basename.append(rel)
            reverted.append(rel)
            if not no_revert:
                _revert_path(repo, rel, was_tracked)
            continue

        # (b) kept: an allowed file.
        allowed_touched.append(rel)
        # Non-blocking scope hint (scope check): a kept file that does not sit under a
        # real doc root is suspicious — record it, do NOT revert. The skill author
        # should eyeball it. `_is_in_doc_scope` accepts a file directly at a doc root
        # (CLAUDE.md / AGENTS.md next to the module) OR anywhere under that root's
        # `docs/` subtree at any depth (so `Mod/docs/sub/rule.md` is in scope), while
        # a stray `Mod/notdocs/rule.md` — in neither — is flagged.
        if changed_dir.is_relative_to(repo):
            if not _is_in_doc_scope(changed_dir, repo):
                scope_warnings.append(rel)

    out = {
        "phase": "apply",
        "reverted": sorted(reverted),
        "violations_basename": sorted(violations_basename),
        "allowed_touched": sorted(allowed_touched),
        "scope_warnings": sorted(scope_warnings),
        "baseline_used": str(baseline_path),
    }
    print(json.dumps(out, ensure_ascii=False))
    return 1 if (reverted or violations_basename) else 0


def _add_path_args(p: argparse.ArgumentParser) -> None:
    # `--path` takes one or more values (`--path a b c`) and may be repeated.
    # Single `--path X` stays byte-for-byte backward compatible.
    p.add_argument("--path", action="append", nargs="+", default=None,
                   metavar="PATH",
                   help="target path(s); pass several after one --path, or repeat --path")
    p.add_argument("--repo-root", default=None, metavar="DIR",
                   help="repository checkout to operate on; defaults to the repo "
                        "containing the current working directory")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kb_tool.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=["text", "json"], default="text")

    p_list_roots = sub.add_parser("list-doc-roots", parents=[common])
    _add_path_args(p_list_roots)
    p_list_roots.set_defaults(func=list_doc_roots)

    p_list_targets = sub.add_parser("list-doc-targets", parents=[common])
    _add_path_args(p_list_targets)
    p_list_targets.set_defaults(func=list_doc_targets)

    p_list_ancestors = sub.add_parser("list-doc-ancestors", parents=[common])
    _add_path_args(p_list_ancestors)
    p_list_ancestors.set_defaults(func=list_doc_ancestors)

    p_scan_types = sub.add_parser("scan-types", parents=[common])
    _add_path_args(p_scan_types)
    p_scan_types.add_argument("--max-items", type=int, default=40)
    p_scan_types.set_defaults(func=scan_types)

    p_plan = sub.add_parser("plan-doc-update")
    p_plan.add_argument(
        "--format",
        choices=["text", "json"],
        default="json",
        help="accepted for symmetry with the other subcommands but ignored: plan-doc-update always prints JSON",
    )
    _add_path_args(p_plan)
    p_plan.set_defaults(func=plan_doc_update)

    p_eval_symbols = sub.add_parser("eval-symbols", parents=[common])
    _add_path_args(p_eval_symbols)
    p_eval_symbols.set_defaults(func=eval_symbols)

    p_eval_gate = sub.add_parser("eval-gate")
    p_eval_gate.add_argument(
        "--format",
        choices=["text", "json"],
        default="json",
        help="accepted for symmetry with the other subcommands but ignored: eval-gate always prints JSON",
    )
    p_eval_gate.add_argument("--base", required=True, metavar="REF",
                             help="git ref the MR diff starts from (e.g. the merge "
                                  "commit's first parent, or the target-branch ref)")
    p_eval_gate.add_argument("--head", default="HEAD", metavar="REF",
                             help="git ref of the MR result state (default: HEAD)")
    p_eval_gate.add_argument("--repo-root", default=None, metavar="DIR",
                             help="repository checkout to operate on; defaults to the repo "
                                  "containing the current working directory")
    p_eval_gate.set_defaults(func=eval_gate)

    p_eval_add = sub.add_parser("eval-add-signal")
    p_eval_add.add_argument(
        "--format",
        choices=["text", "json"],
        default="json",
        help="accepted for symmetry with the other subcommands but ignored: eval-add-signal always prints JSON",
    )
    p_eval_add.add_argument("--base", required=True, metavar="REF",
                            help="git ref the MR diff starts from (same as eval-gate)")
    p_eval_add.add_argument("--head", default="HEAD", metavar="REF",
                            help="git ref of the MR result state (default: HEAD)")
    p_eval_add.add_argument("--repo-root", default=None, metavar="DIR",
                            help="repository checkout to operate on; defaults to the repo "
                                 "containing the current working directory")
    p_eval_add.set_defaults(func=eval_add_signal)

    p_eval_bootstrap = sub.add_parser("eval-bootstrap-signal")
    p_eval_bootstrap.add_argument(
        "--format",
        choices=["text", "json"],
        default="json",
        help="accepted for symmetry with the other subcommands but ignored: "
             "eval-bootstrap-signal always prints JSON",
    )
    p_eval_bootstrap.add_argument("--base", required=True, metavar="REF",
                                  help="git ref the MR diff starts from (same value the "
                                       "freshness/coverage gates already resolved)")
    p_eval_bootstrap.add_argument("--head", default="HEAD", metavar="REF",
                                  help="git ref of the MR result state (default: HEAD)")
    p_eval_bootstrap.add_argument("--repo-root", default=None, metavar="DIR",
                                  help="repository checkout to operate on; defaults to the "
                                       "repo containing the current working directory")
    p_eval_bootstrap.add_argument("--roots", required=True, metavar="LIST",
                                  help="comma-separated doc roots THIS run edited. Required and "
                                       "never inferred: the ancestor walk the other two gates use "
                                       "finds roots by evals presence, which is false by "
                                       "construction here — re-deriving it would put a second "
                                       "definition of 'doc root' in a second place")
    p_eval_bootstrap.set_defaults(func=eval_bootstrap_signal)

    p_enforce = sub.add_parser(
        "enforce-writeset",
        help="deterministic file-level write-domain guard: snapshot a git baseline "
             "before editing docs, then apply to revert any out-of-domain "
             "change this run made.",
    )
    p_enforce.add_argument("--repo-root", default=None, metavar="DIR",
                           help="repository checkout to operate on; defaults to the "
                                "repo containing the current working directory")
    p_enforce.add_argument("--baseline", default=None, metavar="PATH",
                           help="baseline file path (default: <repo>/.git/kb-writeset-baseline.json)")
    g_phase = p_enforce.add_mutually_exclusive_group(required=True)
    g_phase.add_argument("--snapshot", action="store_true",
                         help="record the pre-edit git baseline")
    g_phase.add_argument("--apply", action="store_true",
                         help="after editing: revert this run's out-of-domain changes")
    p_enforce.add_argument("--no-revert", action="store_true",
                           help="report violations but do NOT revert any file")
    p_enforce.add_argument("--allow-evals", action="store_true",
                           help="also admit each touched doc root's own "
                                "docs/evals/evals.json (matched by path shape, not "
                                "basename). Off by default — the strict 7-basename "
                                "domain is what a normal distillation run gets.")
    p_enforce.set_defaults(func=enforce_writeset)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
