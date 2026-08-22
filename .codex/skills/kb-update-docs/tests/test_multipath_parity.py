#!/usr/bin/env python3
"""Self-contained regression test for kb_tool.py multi-path support.

Headline guarantee (the property Nathan asked us to guarantee): for the
target-resolution commands that decide WHICH doc roots get updated
(list-doc-targets / list-doc-ancestors / list-doc-roots), resolving N paths in a
SINGLE invocation of the new tool yields exactly the same set of doc roots as
running the ORIGINAL single-path tool once per path and union-deduping:

    new.once(p1..pN)  ==  union( orig.single(p1) .. orig.single(pN) )

The original is checked in verbatim at tests/fixtures/kb_tool_orig.py (see its
README) so this is a genuine cross-tool proof, not a tautological new-vs-new
check. We also cover: explicit expected results, edge cases, the loud rejection
of empty/whitespace paths, the pinned child-first ordering of multi-path
ancestors, the --format text branch, and scan-types' file-deduped aggregation
(a DIFFERENT, intentional invariant — NOT union-of-singles; see Part D). No
network, no big checkout needed. Run:

    python3 plugins/ttadk/mobile-core/skills/kb-update-docs/tests/test_multipath_parity.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

NEW = Path(__file__).resolve().parent.parent / "scripts" / "kb_tool.py"
ORIG = Path(__file__).resolve().parent / "fixtures" / "kb_tool_orig.py"
FAILURES: list[str] = []


def run(tool, cmd, paths, cwd, extra=None, single_flag=False,
        fmt="json", expect_fail=False):
    argv = [sys.executable, str(tool), cmd]
    if single_flag:
        # one --path taking several values: --path a b c
        argv += ["--path", *paths]
    else:
        # repeated flag: --path a --path b  (also supported)
        for p in paths:
            argv += ["--path", p]
    argv += ["--format", fmt]
    if extra:
        argv += extra
    r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if expect_fail:
        return r.returncode
    if r.returncode != 0:
        raise AssertionError(f"{tool.name} {cmd} {paths} failed rc={r.returncode}: {r.stderr}")
    out = r.stdout.strip()
    if fmt == "text":
        return [ln for ln in out.splitlines() if ln]
    return json.loads(out) if out else []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f"  -- {detail}" if (detail and not cond) else ""))
    if not cond:
        FAILURES.append(name)


def xparity(name, cmd, paths, cwd):
    """new.once(paths) == union( orig.single(p) for p in paths ) -- cross-tool."""
    orig_union = set()
    for p in paths:
        orig_union |= set(run(ORIG, cmd, [p], cwd))
    once = run(NEW, cmd, paths, cwd)
    once_set = set(once)
    check(f"{name}: new.once == union(orig.single)", orig_union == once_set,
          f"orig-only={sorted(orig_union - once_set)} new-only={sorted(once_set - orig_union)}")
    check(f"{name}: new.once has no duplicates", len(once) == len(once_set))
    return once


def build_repo(td: Path) -> Path:
    repo = td / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "CLAUDE.md").write_text("root\n")
    (repo / "A").mkdir()
    (repo / "A" / "CLAUDE.md").write_text("public class AFoo {}\n")
    (repo / "A" / "B" / "docs").mkdir(parents=True)
    (repo / "A" / "B" / "docs" / "rule.md").write_text("rule\n")
    (repo / "A" / "B" / "C").mkdir()
    (repo / "A" / "B" / "C" / "CLAUDE.md").write_text("struct CBar {}\n")
    (repo / "A" / "B" / "C" / "c.swift").write_text("public class CFoo {}\n")
    (repo / "D" / "docs").mkdir(parents=True)
    (repo / "D" / "docs" / "workflow.md").write_text("flow\n")
    (repo / "E").mkdir()  # no docs at all
    (repo / "E" / "e.swift").write_text("struct EBar {}\n")
    return repo


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = build_repo(Path(tmp))
        cwd = str(repo)

        print("== Part A: cross-tool parity  new.once == union(orig.single) ==")
        t = xparity("targets[A, D]", "list-doc-targets", ["A", "D"], cwd)
        check("targets[A, D] == {A, A/B, A/B/C, D}", set(t) == {"A", "A/B", "A/B/C", "D"}, str(t))

        t = xparity("targets[A, A/B] overlap", "list-doc-targets", ["A", "A/B"], cwd)
        check("targets[A, A/B] == {A, A/B, A/B/C}", set(t) == {"A", "A/B", "A/B/C"}, str(t))

        # list-doc-roots only matches CLAUDE.md roots, scanning *under* each path
        # (never walks up to the repo root), so D (docs-only) and '.' are absent.
        r = xparity("roots[A, D]", "list-doc-roots", ["A", "D"], cwd)
        check("roots[A, D] == {A, A/B/C}", set(r) == {"A", "A/B/C"}, str(r))

        a = xparity("ancestors[A/B/C/c.swift]", "list-doc-ancestors", ["A/B/C/c.swift"], cwd)
        check("ancestors child-first == [A/B/C, A/B, A, '.']", a == ["A/B/C", "A/B", "A", "."], str(a))

        a = xparity("ancestors[A/B/C, D/docs/workflow.md]", "list-doc-ancestors",
                    ["A/B/C", "D/docs/workflow.md"], cwd)
        check("ancestors multi set == {A/B/C, A/B, A, '.', D}",
              set(a) == {"A/B/C", "A/B", "A", ".", "D"}, str(a))

        print("\n== Part B: pinned multi-path ancestors ORDER (child-first, input order) ==")
        # First path's full child->root chain, then each later path's NEW roots.
        a = run(NEW, "list-doc-ancestors", ["A/B/C", "A/B"], cwd)
        check("order[A/B/C, A/B] == [A/B/C, A/B, A, '.']", a == ["A/B/C", "A/B", "A", "."], str(a))
        a = run(NEW, "list-doc-ancestors", ["A/B/C", "D/docs/workflow.md"], cwd)
        check("order[A/B/C, D/..] == [A/B/C, A/B, A, '.', D]",
              a == ["A/B/C", "A/B", "A", ".", "D"], str(a))

        print("\n== Part C: edge cases & input forms ==")
        t = xparity("targets[A/CLAUDE.md] file-input", "list-doc-targets", ["A/CLAUDE.md"], cwd)
        check("file-input -> {A}", set(t) == {"A"}, str(t))

        t = xparity("targets[abs(A), D]", "list-doc-targets", [str(repo / "A"), "D"], cwd)
        check("abs path -> {A, A/B, A/B/C, D}", set(t) == {"A", "A/B", "A/B/C", "D"}, str(t))

        t = xparity("targets[missing, D]", "list-doc-targets", ["Znope", "D"], cwd)
        check("missing path ignored -> {D}", set(t) == {"D"}, str(t))

        # input-form equivalence: one --path with several values == repeated --path
        flag = set(run(NEW, "list-doc-targets", ["A", "D"], cwd))                    # --path A --path D
        single = set(run(NEW, "list-doc-targets", ["A", "D"], cwd, single_flag=True))  # --path A D
        check("--path A D (one flag) == --path A --path D", single == flag,
              f"single={single} repeated={flag}")

        # duplicate path collapses (idempotent)
        dup = run(NEW, "list-doc-targets", ["A", "A", "A"], cwd)
        check("duplicate paths collapse", set(dup) == {"A", "A/B", "A/B/C"} and len(dup) == len(set(dup)), str(dup))

        # default (no path at all) reproduces the original whole-repo default
        d_orig = set(run(ORIG, "list-doc-targets", [], cwd))
        d_new = set(run(NEW, "list-doc-targets", [], cwd))
        check("default(no path) new == orig", d_orig == d_new, f"orig={d_orig} new={d_new}")

        # --format text branch resolves to the same set as json
        txt = set(run(NEW, "list-doc-targets", ["A", "D"], cwd, fmt="text"))
        check("--format text == --format json set", txt == flag, f"text={txt} json={flag}")

        print("\n== Part C2: empty/whitespace paths are rejected loudly (not silent) ==")
        check("--path '' rejected (rc!=0)", run(NEW, "list-doc-targets", [""], cwd, expect_fail=True) != 0)
        check("--path '   ' rejected (rc!=0)", run(NEW, "list-doc-targets", ["   "], cwd, expect_fail=True) != 0)
        check("mixed ['', D] rejected (rc!=0)", run(NEW, "list-doc-targets", ["", "D"], cwd, expect_fail=True) != 0)
        check("--path A '' (one flag, mixed) rejected (rc!=0)",
              run(NEW, "list-doc-targets", ["A", ""], cwd, single_flag=True, expect_fail=True) != 0)

        print("\n== Part D: scan-types multi is a FILE-DEDUPED aggregation (a different invariant) ==")
        BIG = ["--max-items", "100000"]
        # D1: disjoint roots -> multi == sum of per-root singles (oracle valid here)
        once = {it["name"]: it["count"] for it in run(NEW, "scan-types", ["A/B/C", "E"], cwd, BIG)}
        summed: dict[str, int] = {}
        for p in ["A/B/C", "E"]:
            for it in run(NEW, "scan-types", [p], cwd, BIG):
                summed[it["name"]] = summed.get(it["name"], 0) + it["count"]
        check("D1 disjoint: scan-types multi == sum of per-root single", once == summed,
              f"once={once} summed={summed}")

        # D2: OVERLAPPING roots -> the `scanned` file-dedup branch fires; multi is
        # file-deduped (each .swift counted once) and is NOT the sum of singles.
        # A/B recursively contains A/B/C, so c.swift (CFoo) must be counted ONCE.
        once_ov = {it["name"]: it["count"] for it in run(NEW, "scan-types", ["A/B/C", "A/B"], cwd, BIG)}
        sum_ov: dict[str, int] = {}
        for p in ["A/B/C", "A/B"]:
            for it in run(NEW, "scan-types", [p], cwd, BIG):
                sum_ov[it["name"]] = sum_ov.get(it["name"], 0) + it["count"]
        check("D2 overlap: multi file-deduped == {CFoo: 1}", once_ov == {"CFoo": 1}, str(once_ov))
        check("D2 overlap: naive sum would double-count == {CFoo: 2}", sum_ov == {"CFoo": 2}, str(sum_ov))
        check("D2 overlap: multi != sum-of-singles (dedup branch proven)", once_ov != sum_ov,
              f"multi={once_ov} sum={sum_ov}")

    print(f"\n==== {'OK' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)} ====")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
