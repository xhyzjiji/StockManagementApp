import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import kb_select_key_classes as key_classes
from kb_common import DEFAULT_EXCLUDES, SOURCE_EXTS, count_lines, first_build_marker_hint, has_build_marker, iter_files, module_anchor_for, repo_root, resolve_repo_path


@dataclass(frozen=True)
class DirStats:
    source_files: int
    source_lines: int
    bytes_total: int


def dir_stats(root: Path, excludes: set[str]) -> DirStats:
    source_files = 0
    source_lines = 0
    bytes_total = 0
    for p in iter_files(root, SOURCE_EXTS, excludes):
        source_files += 1
        source_lines += count_lines(p)
        try:
            bytes_total += p.stat().st_size
        except OSError:
            pass
    return DirStats(source_files=source_files, source_lines=source_lines, bytes_total=bytes_total)


def nearest_ancestor_with_file(start: Path, filename: str) -> Optional[Path]:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    while True:
        if (cur / filename).exists():
            return cur
        if cur == cur.parent:
            return None
        cur = cur.parent


def nearest_ancestor_with_build_marker(start: Path, repo: Path) -> Optional[Path]:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    while True:
        if has_build_marker(cur):
            return cur
        if cur == repo or cur == cur.parent:
            return None
        cur = cur.parent


def stable_doc_root_with_reason(target: Path, repo: Path) -> tuple[Path, str]:
    cur = target.resolve()
    if cur.is_file():
        cur = cur.parent

    if (cur / "CLAUDE.md").exists():
        return cur, "scope root: target directory contains CLAUDE.md"

    build = nearest_ancestor_with_build_marker(cur, repo)
    if build:
        hint = first_build_marker_hint(build)
        if hint:
            return build, f"scope root: nearest ancestor containing build marker ({hint})"
        return build, "scope root: nearest ancestor containing build marker"

    anchor = module_anchor_for(cur, repo)
    if anchor:
        return anchor, "scope root: module anchor under Modules/* or Vendors/*"

    existing = nearest_ancestor_with_file(cur, "CLAUDE.md")
    if existing:
        return existing, "scope root: nearest ancestor containing CLAUDE.md"

    return cur, "scope root: target directory"


def iter_child_dirs(root: Path, excludes: set[str]) -> Iterable[Path]:
    try:
        for p in root.iterdir():
            if not p.is_dir():
                continue
            if p.name.startswith(".") or p.name in excludes:
                continue
            yield p
    except OSError:
        return


def suggest_submodules_for_dir(
    module_root: Path,
    repo: Path,
    excludes: set[str],
    min_files: int,
    min_lines: int,
    max_items: int,
) -> list[tuple[Path, DirStats, str]]:
    children: list[tuple[Path, DirStats, str]] = []
    for p in iter_child_dirs(module_root, excludes):
        stats = dir_stats(p, excludes)
        if stats.source_files < min_files and stats.source_lines < min_lines:
            continue
        reasons: list[str] = []
        if stats.source_lines >= min_lines:
            reasons.append(f"source_lines >= {min_lines}")
        if stats.source_files >= min_files:
            reasons.append(f"source_files >= {min_files}")
        reason = "shortlisted: " + (" and ".join(reasons) if reasons else "size threshold met")
        children.append((p, stats, reason))

    children.sort(key=lambda x: (x[1].source_lines, x[1].source_files, x[1].bytes_total), reverse=True)
    picked = children[:max_items]
    ranked: list[tuple[Path, DirStats, str]] = []
    for idx, (p, stats, reason) in enumerate(picked, start=1):
        ranked.append((p, stats, f"{reason}; rank #{idx} by source_lines/files/bytes among siblings"))
    return ranked


def _key_class_files(
    module_root: Path, excludes: set[str], top_files: int, damping: float, iters: int
) -> list[Path]:
    decls, file_to_decls = key_classes._collect_type_decls(module_root, excludes)
    if not decls:
        return []

    file_idents = key_classes._collect_file_idents(module_root, excludes)
    symbol_names = set(decls.keys())

    fan_in_files: dict[str, int] = {name: 0 for name in symbol_names}
    fan_in_file_sets: dict[str, set[Path]] = {name: set() for name in symbol_names}

    for file_path, idents in file_idents.items():
        touched = idents.intersection(symbol_names)
        if not touched:
            continue
        for name in touched:
            decl_file = decls[name].file_path
            if file_path == decl_file:
                continue
            fan_in_file_sets[name].add(file_path)

    for name, s in fan_in_file_sets.items():
        fan_in_files[name] = len(s)

    file_refs: dict[Path, set[str]] = {}
    for file_path, idents in file_idents.items():
        file_refs[file_path] = idents.intersection(symbol_names)

    fan_out: dict[str, int] = {}
    edges: dict[str, set[str]] = {name: set() for name in symbol_names}
    for name, decl in decls.items():
        refs_in_file = set(file_refs.get(decl.file_path, set()))
        same_file_decls = file_to_decls.get(decl.file_path, set())
        refs_in_file.difference_update(same_file_decls)
        refs_in_file.discard(name)
        fan_out[name] = len(refs_in_file)
        edges[name] = refs_in_file

    pr = key_classes._pagerank({k: set(v) for k, v in edges.items()}, damping=damping, iters=iters)
    loc_by_type, cx_by_type = key_classes._collect_type_loc_complexity(module_root, excludes, decls)

    implementers: dict[str, int] = {name: 0 for name in symbol_names}
    protocol_names = {n for n, d in decls.items() if d.kind in {"protocol", "objc_protocol", "interface"}}

    for file_path, decl_names in file_to_decls.items():
        suffix = file_path.suffix.lower()
        if suffix not in {".swift", ".kt", ".java"}:
            continue
        try:
            raw = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in raw.splitlines():
            if suffix == ".swift":
                m = key_classes.SWIFT_TYPE_DECL_RE.match(line)
                if not m:
                    continue
                _name = m.group(2)
                if _name not in decl_names:
                    continue
                if ":" not in line:
                    continue
                for proto in key_classes.SWIFT_CONFORMANCE_RE.findall(line):
                    if proto in protocol_names:
                        implementers[proto] = implementers.get(proto, 0) + 1
                continue

            if suffix == ".kt":
                m4 = key_classes.KOTLIN_TYPE_DECL_RE.match(line)
                if not m4:
                    continue
                _name = m4.group("name")
                if _name not in decl_names:
                    continue
                if ":" not in line:
                    continue
                tail = line.split(":", 1)[1]
                if "{" in tail:
                    tail = tail.split("{", 1)[0]
                for t in key_classes.IDENT_RE.findall(tail):
                    if t in protocol_names:
                        implementers[t] = implementers.get(t, 0) + 1
                continue

            m6 = key_classes.JAVA_TYPE_DECL_RE.match(line)
            if not m6:
                continue
            _name = m6.group("name")
            if _name not in decl_names:
                continue
            kw = m6.group("kw")
            if kw == "interface":
                if "extends" not in line:
                    continue
                tail = line.split("extends", 1)[1]
                if "{" in tail:
                    tail = tail.split("{", 1)[0]
                for t in key_classes.IDENT_RE.findall(tail):
                    if t in protocol_names:
                        implementers[t] = implementers.get(t, 0) + 1
                continue

            if "implements" not in line:
                continue
            tail = line.split("implements", 1)[1]
            if "{" in tail:
                tail = tail.split("{", 1)[0]
            for t in key_classes.IDENT_RE.findall(tail):
                if t in protocol_names:
                    implementers[t] = implementers.get(t, 0) + 1

    def norm_log_map(values: dict[str, float]) -> dict[str, float]:
        if not values:
            return {}
        max_v = max(values.values())
        if max_v <= 0:
            return {k: 0.0 for k in values}
        max_log = math.log1p(max_v)
        if max_log <= 0:
            return {k: 0.0 for k in values}
        return {k: (math.log1p(v) / max_log) for k, v in values.items()}

    fan_in_norm = norm_log_map({k: float(v) for k, v in fan_in_files.items()})
    fan_out_norm = norm_log_map({k: float(v) for k, v in fan_out.items()})
    loc_norm = norm_log_map({k: float(v) for k, v in loc_by_type.items()})
    cx_norm = norm_log_map({k: float(v) for k, v in cx_by_type.items()})
    impl_norm = norm_log_map({k: float(v) for k, v in implementers.items()})
    pr_norm = norm_log_map({k: float(v) for k, v in pr.items()})

    scored: list[tuple[str, float]] = []
    for name, decl in decls.items():
        score = 0.27 * fan_out_norm.get(name, 0.0)
        score += 0.25 * loc_norm.get(name, 0.0)
        score += 0.25 * cx_norm.get(name, 0.0)
        score += 0.15 * pr_norm.get(name, 0.0)
        score += 0.06 * fan_in_norm.get(name, 0.0)
        score += 0.02 * impl_norm.get(name, 0.0)
        if decl.is_public:
            score += 0.05
        scored.append((name, score))

    scored.sort(
        key=lambda x: (
            x[1],
            fan_out.get(x[0], 0),
            loc_by_type.get(x[0], 0),
            cx_by_type.get(x[0], 0),
            fan_in_files.get(x[0], 0),
        ),
        reverse=True,
    )

    files: list[Path] = []
    seen: set[Path] = set()
    for name, _score in scored:
        kind = decls[name].kind
        if kind in {"enum", "struct"}:
            continue
        p = decls[name].file_path
        if p in seen:
            continue
        seen.add(p)
        files.append(p)
        if len(files) >= top_files:
            break
    return files


def _suggest_doc_roots_from_key_files(
    module_root: Path,
    excludes: set[str],
    key_files: list[Path],
    max_roots: int,
    max_fraction: float,
) -> list[tuple[Path, DirStats, str]]:
    if not key_files:
        return []

    module_stats = dir_stats(module_root, excludes)
    if module_stats.source_lines > 0:
        cap_lines = max(1, int(module_stats.source_lines * max_fraction))
    else:
        cap_lines = 0

    if module_stats.source_files > 0:
        cap_files = max(1, int(module_stats.source_files * max_fraction))
    else:
        cap_files = 0

    def within_cap(stats: DirStats) -> bool:
        if module_stats.source_lines > 0:
            return stats.source_lines <= cap_lines
        if module_stats.source_files > 0:
            return stats.source_files <= cap_files
        return True

    key_files_set = set(key_files)

    key_files_by_dir: dict[Path, set[Path]] = {}
    key_count_by_dir: dict[Path, int] = {}
    for f in key_files:
        d = f.parent
        while True:
            if d == module_root or d.is_relative_to(module_root):
                key_files_by_dir.setdefault(d, set()).add(f)
                key_count_by_dir[d] = key_count_by_dir.get(d, 0) + 1
            if d == module_root or d == d.parent:
                break
            d = d.parent

    stats_cache: dict[Path, DirStats] = {}

    def stats_for(d: Path) -> DirStats:
        s = stats_cache.get(d)
        if s is None:
            if d.is_file():
                try:
                    bytes_total = d.stat().st_size
                except OSError:
                    bytes_total = 0
                s = DirStats(source_files=1, source_lines=count_lines(d), bytes_total=bytes_total)
            else:
                s = dir_stats(d, excludes)
            stats_cache[d] = s
        return s

    candidates = [d for d, c in key_count_by_dir.items() if c >= 1 and (d == module_root or d.is_relative_to(module_root))]
    candidates.sort(key=lambda d: (key_count_by_dir.get(d, 0), len(d.parts)), reverse=True)

    picked: list[tuple[Path, DirStats, str]] = []
    remaining = set(key_files_set)

    def overlaps_existing(d: Path) -> bool:
        for existing, _s, _r in picked:
            if d == existing:
                return True
            if d.is_relative_to(existing) or existing.is_relative_to(d):
                return True
        return False

    for d in candidates:
        if len(picked) >= max_roots:
            break
        if overlaps_existing(d):
            continue
        covered = {f for f in remaining if f.is_relative_to(d)}
        if not covered:
            continue
        s = stats_for(d)
        if not within_cap(s):
            continue
        reason = f"covers {len(covered)}/{len(key_files)} key files; cap {max_fraction:.0%}"
        picked.append((d, s, reason))
        remaining.difference_update(covered)

    if len(picked) < max_roots and remaining:
        for f in key_files:
            if len(picked) >= max_roots:
                break
            if f not in remaining:
                continue
            d = f.parent
            candidates2 = [d, f]
            added = False
            for cand in candidates2:
                if overlaps_existing(cand):
                    continue
                s = stats_for(cand)
                if not within_cap(s):
                    continue
                reason = f"single key file root; cap {max_fraction:.0%}"
                picked.append((cand, s, reason))
                added = True
                break
            if added:
                remaining.discard(f)
            else:
                remaining.discard(f)

    picked.sort(key=lambda x: (len(key_files_by_dir.get(x[0], set())), x[1].source_lines, x[1].source_files), reverse=True)
    return picked


def _suggest_doc_roots_for_target(
    repo: Path, target: Path, args: argparse.Namespace
) -> tuple[Path, str, list[tuple[Path, DirStats, str]]]:
    root, root_reason = stable_doc_root_with_reason(target, repo)
    excludes = DEFAULT_EXCLUDES

    key_files = _key_class_files(root, excludes, top_files=args.key_files, damping=args.key_damping, iters=args.key_iters)
    suggested = _suggest_doc_roots_from_key_files(
        module_root=root,
        excludes=excludes,
        key_files=key_files,
        max_roots=args.key_root_items,
        max_fraction=args.max_root_fraction,
    )
    if not suggested and not key_files:
        suggested = suggest_submodules_for_dir(
            module_root=root,
            repo=repo,
            excludes=excludes,
            min_files=args.min_files,
            min_lines=args.min_lines,
            max_items=args.max_items,
        )

    return root, root_reason, suggested


def _print_suggested_doc_roots_markdown(
    repo: Path, root: Path, root_reason: str, suggested: list[tuple[Path, DirStats, str]]
) -> list[str]:
    excludes = DEFAULT_EXCLUDES

    def to_rel(p: Path) -> str:
        return str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p)

    print(f"**repo_root:** {repo}")
    print(f"**stable_root:** {to_rel(root)}")
    print(f"**stable_root_reason:** {root_reason}")
    print("")
    base_stats = dir_stats(root, excludes)
    base_lines = base_stats.source_lines

    rel_paths: list[str] = []
    print("### Suggested doc roots (copy/paste)")
    for i, (p, stats, reason) in enumerate(suggested, start=1):
        rel = to_rel(p)
        rel_paths.append(rel)
        if base_lines > 0:
            pct = (stats.source_lines / base_lines) * 100.0
            short_desc = f"source_files:{stats.source_files}, source_lines:{stats.source_lines} ({pct:.1f}%), bytes:{stats.bytes_total}; {reason}"
        else:
            short_desc = f"source_files:{stats.source_files}, source_lines:{stats.source_lines}, bytes:{stats.bytes_total}; {reason}"
        print(f"- `{rel}` - {short_desc} (rank #{i})")

    return rel_paths


def suggest_doc_roots(args: argparse.Namespace) -> int:
    repo = repo_root(Path.cwd())
    paths = getattr(args, "paths", None)
    if not paths:
        paths = [getattr(args, "path", ".")]

    all_rel_roots: list[str] = []
    for idx, raw in enumerate(paths, start=1):
        target = resolve_repo_path(raw, repo)

        if len(paths) > 1:
            print(f"## Analysis ({idx}/{len(paths)}): `{raw}`")
            print("")

        root, root_reason, suggested = _suggest_doc_roots_for_target(repo=repo, target=target, args=args)
        rel_paths = _print_suggested_doc_roots_markdown(repo=repo, root=root, root_reason=root_reason, suggested=suggested)
        all_rel_roots.extend(rel_paths)

        if len(paths) > 1:
            print("")

    if len(paths) > 1:
        uniq = sorted(set(all_rel_roots))
        print("## Aggregated suggested doc roots")
        print("")
        for rel in uniq:
            print(f"- `{rel}`")

    return 0


def register(sub) -> None:
    p_suggest_docs = sub.add_parser("suggest-doc-roots")
    p_suggest_docs.add_argument("paths", nargs="+")
    p_suggest_docs.add_argument("--min-files", type=int, default=30)
    # 与看板资格门对齐：达标 = (源文件 >=30 或 行数 >=3000)。
    # 口径 SoT = 共享口径仓 kb-crawler/kb_caliber.py（同日新增 test/generated/AB注册 排除，
    # 本工具的 DEFAULT_EXCLUDES 只排构建产物——扫描范围差异见该文件注释）。
    p_suggest_docs.add_argument("--min-lines", type=int, default=3000)
    p_suggest_docs.add_argument("--max-items", type=int, default=12)
    p_suggest_docs.add_argument("--expand-lines", type=int, default=200000)
    p_suggest_docs.add_argument("--expand-max-items", type=int, default=12)
    p_suggest_docs.add_argument("--key-files", type=int, default=10)
    p_suggest_docs.add_argument("--key-root-items", type=int, default=10)
    p_suggest_docs.add_argument("--max-root-fraction", type=float, default=0.2)
    p_suggest_docs.add_argument("--key-damping", type=float, default=0.85)
    p_suggest_docs.add_argument("--key-iters", type=int, default=50)
    p_suggest_docs.set_defaults(func=suggest_doc_roots)
