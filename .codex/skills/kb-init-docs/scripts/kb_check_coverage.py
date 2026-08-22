"""Doc-coverage self-check: catch important code symbols the generated KB docs don't anchor.

Motivation (2026-06-22 review): the key-class list (`select-key-classes`, ranked by
LOC/complexity/fan-in) is top-N bounded, so two classes of important symbols slip through
and get dropped from generated docs. This adds two PRECISE, low-noise backstops:

  - Prong 1 — public-interface protocols: protocols declared in a deliberate public-interface
    directory (e.g. `.../ModuleInterface/Interface/`, `.../Public/`, `.../API/`) that the docs
    never mention. These are the cross-module contract surface. (A module with no such directory
    convention — e.g. a prefix-scoped SDK — yields nothing here; that is correct, not a miss.)
  - Prong 2 — same-header collaborators: a type declared in the SAME header as a documented
    type, but itself never mentioned. Same-header siblings are part of one public surface, so a
    documented manager whose paired helper (e.g. a streaming "chunk manager") is undocumented is
    a real gap.

Both are deliberately narrow to stay actionable (fan-in alone over-flags internal infra).
Reuses the `select-key-classes` source scanner so the two stay consistent. Advisory by default;
`--strict` fails on Prong 1.

CEILING (do not over-rely): this only catches WHOLE types that the docs drop. It does NOT catch a
documented type that is missing key *methods* (e.g. a manager row with no methods), nor missing
*rule content* (e.g. a dropped dispatch-safety rule). Those still require human review of the diff.
On a large module Prong 1 can be 100+ rows — a ranked hint list, not a clean pass/fail gate.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from kb_common import DEFAULT_EXCLUDES, repo_root, resolve_repo_path
from kb_select_key_classes import _collect_file_idents, _collect_type_decls

PROTOCOL_KINDS = {"protocol", "objc_protocol", "interface"}
TYPEISH_KINDS = {"class", "objc_class", "protocol", "objc_protocol", "interface", "actor"}
# path segments that mark a deliberate public-interface surface (lowercased posix match)
INTERFACE_DIR_MARKERS = ("moduleinterface", "publicinterface", "/interface/", "/public/", "/publicapi/", "/api/")


def _load_doc_text(doc_root: Path) -> str:
    parts: list[str] = []
    claude = doc_root / "CLAUDE.md"
    if claude.is_file():
        parts.append(claude.read_text(encoding="utf-8", errors="ignore"))
    docs = doc_root / "docs"
    if docs.is_dir():
        for p in sorted(docs.rglob("*.md")):
            if "evals" in p.relative_to(docs).parts:  # the test suite, not KB content
                continue
            parts.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def _in_interface_dir(path: Path) -> bool:
    posix = path.as_posix().lower()
    return any(m in posix for m in INTERFACE_DIR_MARKERS)


def check_doc_coverage(args: argparse.Namespace) -> int:
    repo = repo_root(Path.cwd())
    module_root = resolve_repo_path(args.path, repo)

    decls, file_to_decls = _collect_type_decls(module_root, DEFAULT_EXCLUDES)
    if not decls:
        print(f"[kb-check-coverage] no type declarations under {module_root}; nothing to check")
        return 0
    file_idents = _collect_file_idents(module_root, DEFAULT_EXCLUDES)
    symbol_names = set(decls)

    fan_in: dict[str, set[Path]] = {n: set() for n in symbol_names}
    for fp, idents in file_idents.items():
        for name in idents & symbol_names:
            if fp != decls[name].file_path:
                fan_in[name].add(fp)
    fan_in_n = {n: len(s) for n, s in fan_in.items()}

    doc_text = _load_doc_text(module_root)
    if not doc_text.strip():
        print(f"[kb-check-coverage] no CLAUDE.md / docs/*.md under {module_root}; generate docs first")
        return 0
    # token-set membership, NOT bare substring: a substring match falsely "anchors" a short
    # symbol whose characters happen to appear inside an unrelated word, hiding real misses and
    # spawning garbage Prong-2 rows. Symbol names are single identifiers, so tokenizing is exact.
    doc_tokens = set(re.findall(r"[A-Za-z_]\w*", doc_text))

    def anchored(name: str) -> bool:
        return name in doc_tokens

    # ---- Prong 1: public-interface-dir protocols not anchored ----
    interface_dirs_present = any(_in_interface_dir(d.file_path) for d in decls.values())
    p1: list[tuple[str, int, Path]] = []
    for name, d in decls.items():
        if d.kind in PROTOCOL_KINDS and _in_interface_dir(d.file_path) and not anchored(name):
            if fan_in_n[name] >= args.min_fanin:
                p1.append((name, fan_in_n[name], d.file_path))
    p1.sort(key=lambda x: x[1], reverse=True)

    # ---- Prong 2: same-header siblings of anchored types, themselves not anchored ----
    candidates: dict[str, set[str]] = {}
    for fp, names_in_file in file_to_decls.items():
        # only cohesive headers: a small header with a documented type + a sibling = tight
        # coupling (e.g. a manager + its chunk manager). A big "catalog" header that bundles
        # 20 internal protocols is not a collaborator set — skip it (kills bridge-header noise).
        if len(names_in_file) > args.max_header_decls:
            continue
        anchored_here = [n for n in names_in_file if anchored(n)]
        if not anchored_here:
            continue
        for c in names_in_file:
            if anchored(c):
                continue
            cd = decls.get(c)
            if cd is None or cd.kind not in TYPEISH_KINDS:
                continue
            if not (cd.is_public or fan_in_n.get(c, 0) >= args.min_fanin):
                continue
            candidates.setdefault(c, set()).update(anchored_here)
    p2 = sorted(
        ((c, fan_in_n.get(c, 0), sorted(via)) for c, via in candidates.items()),
        key=lambda x: (x[1], len(x[2])),
        reverse=True,
    )

    def to_rel(p: Path) -> str:
        return str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p)

    print(f"# kb-check-coverage: {to_rel(module_root)}")
    print(f"scanned {len(decls)} type decls; doc text {len(doc_text)} chars\n")

    print(f"## Prong 1 — public-interface-dir protocols not anchored ({len(p1)})")
    if not interface_dirs_present:
        print("- (module has no public-interface directory convention "
              "[ModuleInterface/Interface/Public/API]; Prong 1 N/A here)")
    elif not p1:
        print(f"- (none — every interface-dir protocol with fan-in >= {args.min_fanin} is anchored)")
    else:
        print("| Protocol | fan-in(files) | declared in |")
        print("|---|---|---|")
        for name, fin, fp in p1[: args.top]:
            print(f"| `{name}` | {fin} | `{to_rel(fp)}` |")
        if len(p1) > args.top:
            print(f"| … +{len(p1) - args.top} more | | |")

    print(f"\n## Prong 2 — same-header collaborators of documented types, not anchored ({len(p2)})")
    if not p2:
        print("- (none)")
    else:
        print("| Collaborator | kind | fan-in | in same header as (documented) |")
        print("|---|---|---|---|")
        for c, fin, via in p2[: args.top]:
            via_s = ", ".join(f"`{v}`" for v in via[:3]) + (" …" if len(via) > 3 else "")
            print(f"| `{c}` | {decls[c].kind} | {fin} | {via_s} |")
        if len(p2) > args.top:
            print(f"| … +{len(p2) - args.top} more | | | |")

    print("\nFix: anchor the genuinely-important ones (name + relative path) in the relevant doc "
          "(interface.md / domain.md / workflow.md / architecture.md). Advisory — not every symbol "
          "needs documenting, but an interface-dir protocol or a same-header sibling of a documented "
          "type usually does. Tune with --min-fanin.")

    if args.strict and p1:
        print(f"\n[kb-check-coverage] STRICT: {len(p1)} public-interface protocol(s) unanchored", flush=True)
        return 1
    return 0


def register(sub) -> None:
    p = sub.add_parser("check-doc-coverage")
    p.add_argument("path", help="doc root (module dir with CLAUDE.md + docs/), repo-relative or absolute")
    p.add_argument("--min-fanin", type=int, default=2, help="min cross-file fan-in to count a symbol important (default 2)")
    p.add_argument("--max-header-decls", type=int, default=4, help="Prong 2 only inspects headers declaring <= this many types (cohesive units, not catalog headers; default 4)")
    p.add_argument("--top", type=int, default=30, help="max rows printed per prong")
    p.add_argument("--strict", action="store_true", help="exit non-zero if any interface-dir protocol is unanchored (Prong 1)")
    p.set_defaults(func=check_doc_coverage)
