#!/usr/bin/env python3
"""Self-contained regression test for `kb_tool.py plan-doc-update`.

The planner turns a set of changed paths into per-group update plans:
  - changed files are grouped by their "big module" (topmost doc root below the
    ceiling); changes in different big modules form independent groups;
  - within a group the umbrella is the nearest doc root at/above the common
    ancestor; leaves are the owning doc roots that actually have code changes;
  - the ceiling is never updated: the repo root (detected via `.git`), plus an
    iOS pod root (a `*.podspec` directory; sample/test/template podspecs ignored);
  - changed paths with no doc root below the ceiling are reported as `uncovered`.

Synthetic iOS-style (podspec ceiling) and Android-style (no podspec, grouping
umbrellas above gradle modules) fixtures exercise every branch. No network. Run:

    python3 plugins/ttadk/mobile-core/skills/kb-update-docs/tests/test_plan_doc_update.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "kb_tool.py"
FAILURES: list[str] = []


def touch(repo: Path, rel: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x\n")


def plan(repo: Path, changed: list[str]) -> dict:
    # The planner rejects a change set whose targets are ALL absent from the repo
    # (that signals a wrong-repo misconfiguration). Real change sets reference
    # files that exist, so materialise each relative changed path before planning.
    # Absolute paths (external-repo cases) are created by their own fixture.
    for rel in changed:
        if not Path(rel).is_absolute():
            touch(repo, rel)
    argv = [sys.executable, str(TOOL), "plan-doc-update", "--path", *changed, "--format", "json"]
    r = subprocess.run(argv, cwd=str(repo), capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"plan failed rc={r.returncode}: {r.stderr}")
    return json.loads(r.stdout.strip())


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if (detail and not cond) else ""))
    if not cond:
        FAILURES.append(name)


def grp(result: dict, umbrella: str):
    for g in result["groups"]:
        if g["umbrella"] == umbrella:
            return g
    return None


def main() -> int:
    # ---------- iOS-style fixture: *.podspec marks the (excluded) pod ceiling ----------
    print("== iOS-style: pod-root + repo-root excluded, umbrella = common ancestor ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "CLAUDE.md")                                  # repo root doc (excluded)
        touch(repo, "Modules/Pod/Pod.podspec")                    # pod ceiling
        touch(repo, "Modules/Pod/CLAUDE.md")                      # pod root doc (excluded)
        for f in ("Feature", "Feature/SubA", "Feature/SubB", "Other"):
            touch(repo, f"Modules/Pod/Classes/{f}/CLAUDE.md")
        base = "Modules/Pod/Classes"
        res = plan(repo, [
            f"{base}/Feature/w.swift",          # directly in Feature
            f"{base}/Feature/SubA/x.swift",
            f"{base}/Feature/SubB/y.swift",
            f"{base}/Other/z.swift",
        ])
        umbrellas = {g["umbrella"] for g in res["groups"]}
        check("two groups", len(res["groups"]) == 2, str(umbrellas))
        gf = grp(res, f"{base}/Feature")
        check("Feature group umbrella + leaves {Feature,SubA,SubB}",
              gf is not None and set(gf["leaves"]) == {f"{base}/Feature", f"{base}/Feature/SubA", f"{base}/Feature/SubB"},
              str(gf))
        go = grp(res, f"{base}/Other")
        check("Other is its own group", go is not None and go["leaves"] == [f"{base}/Other"], str(go))
        flat = " ".join(umbrellas) + " " + " ".join(l for g in res["groups"] for l in g["leaves"])
        check("pod root never appears", "Modules/Pod/CLAUDE" not in flat and "Modules/Pod " not in (flat + " "))
        check("repo root '.' never appears", "." not in umbrellas and all(l != "." for g in res["groups"] for l in g["leaves"]))
        check("nothing uncovered", res["uncovered"] == [])
        check("pod KB surfaced for higher-bar review (not hard-excluded)",
              res["review_higher"] == ["Modules/Pod"], str(res["review_higher"]))

    # ---------- Android-style: no podspec; only repo root is the ceiling ----------
    print("\n== Android-style: gradle modules, grouping-umbrella, uncovered ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "settings.gradle")
        touch(repo, "CLAUDE.md")                                  # repo root doc (excluded)
        # sibling modules with docs, NO grouping doc above them (comp/ has none)
        touch(repo, "comp/modA/CLAUDE.md"); touch(repo, "comp/modA/build.gradle")
        touch(repo, "comp/modB/CLAUDE.md"); touch(repo, "comp/modB/build.gradle")
        touch(repo, "comp/modC/build.gradle")                     # module, NO doc -> uncovered
        # a grouping umbrella ABOVE two gradle modules (business-l8 / social_creation pattern)
        touch(repo, "comp/area/CLAUDE.md")                        # umbrella, no build.gradle
        touch(repo, "comp/area/mod1/CLAUDE.md"); touch(repo, "comp/area/mod1/build.gradle")
        touch(repo, "comp/area/mod2/CLAUDE.md"); touch(repo, "comp/area/mod2/build.gradle")
        res = plan(repo, [
            "comp/modA/src/X.kt",
            "comp/modB/src/Y.kt",
            "comp/modC/src/Z.kt",            # uncovered
            "comp/area/mod1/src/P.kt",
            "comp/area/mod2/src/Q.kt",
            "meta/x.yaml",                   # uncovered (no doc anywhere up)
        ])
        umbrellas = {g["umbrella"] for g in res["groups"]}
        # modA and modB: separate groups (comp/ has no umbrella doc)
        check("modA separate group", grp(res, "comp/modA") is not None and grp(res, "comp/modA")["leaves"] == ["comp/modA"])
        check("modB separate group", grp(res, "comp/modB") is not None and grp(res, "comp/modB")["leaves"] == ["comp/modB"])
        # area: one group, umbrella=area, leaves={mod1, mod2}
        ga = grp(res, "comp/area")
        check("area umbrella over {mod1,mod2}",
              ga is not None and set(ga["leaves"]) == {"comp/area/mod1", "comp/area/mod2"}, str(ga))
        check("three groups total", len(res["groups"]) == 3, str(umbrellas))
        check("repo root doc excluded", "." not in umbrellas)
        check("modC + meta uncovered",
              set(res["uncovered"]) == {"comp/modC/src/Z.kt", "meta/x.yaml"}, str(res["uncovered"]))
        check("no higher review docs above the module umbrellas", res["review_higher"] == [], str(res["review_higher"]))

    # ---------- graded review: a grouping doc ABOVE the umbrella surfaces as review_higher ----------
    print("\n== review_higher: ancestor doc above the umbrella, below repo root ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "settings.gradle")
        touch(repo, "area/CLAUDE.md")            # grouping doc (will be review_higher)
        touch(repo, "area/sub/CLAUDE.md")        # the changed leaf's owning doc root
        res = plan(repo, ["area/sub/deep/A.kt"])
        check("umbrella = sub (the changed leaf)",
              len(res["groups"]) == 1 and res["groups"][0]["umbrella"] == "area/sub", str(res))
        check("area surfaced as higher review", res["review_higher"] == ["area"], str(res["review_higher"]))

    # ---------- single changed file ----------
    print("\n== single file: umbrella == its owning doc root ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "settings.gradle")
        touch(repo, "comp/m/CLAUDE.md")
        res = plan(repo, ["comp/m/src/A.kt"])
        check("one group umbrella=leaf=comp/m",
              len(res["groups"]) == 1 and res["groups"][0]["umbrella"] == "comp/m"
              and res["groups"][0]["leaves"] == ["comp/m"], str(res))

    # ---------- regressions for review findings ----------
    print("\n== regression: sample/test/template podspec is NOT a false ceiling ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "Modules/Pod/Pod.podspec")                              # real pod ceiling
        touch(repo, "Modules/Pod/Classes/Feature/CLAUDE.md")                # the owning doc root
        touch(repo, "Modules/Pod/Classes/Feature/Example/FeatureExample.podspec")  # sample app (NOT a ceiling)
        touch(repo, "Modules/Pod/Classes/Feature/Tests/FeatureTests.podspec")      # test target (NOT a ceiling)
        res = plan(repo, [
            "Modules/Pod/Classes/Feature/Example/Sources/Demo.swift",
            "Modules/Pod/Classes/Feature/Tests/FooTests.swift",
            "Modules/Pod/Classes/Feature/Real/Bar.swift",
        ])
        check("changes under Example/Tests still resolve to Feature (not uncovered)",
              len(res["groups"]) == 1
              and res["groups"][0]["umbrella"] == "Modules/Pod/Classes/Feature"
              and res["uncovered"] == [], str(res))

    print("\n== regression: external path never becomes a group root ==")
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as ext:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "comp/m/CLAUDE.md")
        extp = Path(ext) / "proj"
        (extp / "sub").mkdir(parents=True)
        (extp / "CLAUDE.md").write_text("x\n")           # external doc root — must be ignored
        (extp / "sub" / "bar.swift").write_text("x\n")
        ext_file = str(extp / "sub" / "bar.swift")
        res = plan(repo, ["comp/m/src/A.kt", ext_file])
        roots = {g["umbrella"] for g in res["groups"]} | {l for g in res["groups"] for l in g["leaves"]}
        check("external doc root not edited; external path -> uncovered",
              ext_file in res["uncovered"] and not any("proj" in (r or "") for r in roots), str(res))

    print("\n== regression: doc root CO-LOCATED with the pod podspec is a leaf, not uncovered (FM6) ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        # Pod whose ONLY KB lives at the pod root, in the SAME dir as the podspec
        # (mirrors Vendors/PNSFoundation: CLAUDE.md + docs/ + *.podspec co-located).
        touch(repo, "Vendors/PNSFoundation/PNSFoundation.podspec")
        touch(repo, "Vendors/PNSFoundation/CLAUDE.md")
        touch(repo, "Vendors/PNSFoundation/docs/interface.md")
        # A second co-located pod marked by docs/ only (mirrors Modules/PNSConsentSDK).
        touch(repo, "Modules/PNSConsentSDK/PNSConsentSDK.podspec")
        touch(repo, "Modules/PNSConsentSDK/docs/interface.md")
        res = plan(repo, [
            "Vendors/PNSFoundation/PNSFoundation/Classes/Interface/PNSDeviceInfoService.swift",
            "Modules/PNSConsentSDK/PNSConsentSDKCore/Core/PNSConsentNetworkProvider.swift",
        ])
        check("co-located pod-root docs are covered, not uncovered",
              res["uncovered"] == [], str(res["uncovered"]))
        shape = {g["umbrella"]: g["leaves"] for g in res["groups"]}
        check("each co-located pod root is its own leaf+umbrella group (exact)",
              shape == {"Vendors/PNSFoundation": ["Vendors/PNSFoundation"],
                        "Modules/PNSConsentSDK": ["Modules/PNSConsentSDK"]}, str(res["groups"]))
        check("no ancestor leaks into review_higher (Vendors/ & Modules/ hold no docs)",
              res["review_higher"] == [], str(res["review_higher"]))
        # Precision: a podspec pod with NO docs anywhere must STILL be uncovered
        # (the fix must not over-cover — only reach a doc root that actually exists).
        touch(repo, "Modules/NoKB/NoKB.podspec")
        res2 = plan(repo, ["Modules/NoKB/Classes/Foo.swift"])
        check("podspec pod with zero docs stays uncovered",
              res2["groups"] == [] and res2["uncovered"] == ["Modules/NoKB/Classes/Foo.swift"],
              str(res2))

    print("\n== regression: co-located pod-root leaf must NOT leak ancestor docs into review_higher (FM6 follow-up) ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "Vendors/CLAUDE.md")                              # ancestor KB ABOVE the pod
        touch(repo, "Vendors/PNSFoundation/PNSFoundation.podspec")    # pod ceiling
        touch(repo, "Vendors/PNSFoundation/CLAUDE.md")               # KB co-located with the podspec
        touch(repo, "Vendors/PNSFoundation/docs/interface.md")
        res = plan(repo, ["Vendors/PNSFoundation/Source/PNSThing.m"])
        check("co-located pod root is the covered leaf",
              len(res["groups"]) == 1
              and res["groups"][0]["leaves"] == ["Vendors/PNSFoundation"]
              and res["uncovered"] == [], str(res))
        check("ancestor doc ABOVE the pod ceiling does NOT leak into review_higher",
              res["review_higher"] == [], str(res["review_higher"]))
        # Control: the SAME ancestor layout, but the change is BELOW the pod ceiling,
        # so the walk legitimately passes THROUGH the pod root — the pod root is
        # surfaced for higher-bar review, and the above-pod Vendors/ doc still stays out.
        touch(repo, "Vendors/PNSFoundation/Feature/docs/interface.md")
        res2 = plan(repo, ["Vendors/PNSFoundation/Feature/src/A.m"])
        check("control: leaf below ceiling surfaces the pod root (not the above-pod doc)",
              res2["groups"][0]["leaves"] == ["Vendors/PNSFoundation/Feature"]
              and res2["review_higher"] == ["Vendors/PNSFoundation"]
              and res2["uncovered"] == [], str(res2))

    print("\n== regression: empty change set is a no-op (not '.' as kb-init candidate) ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "CLAUDE.md")
        r = subprocess.run([sys.executable, str(TOOL), "plan-doc-update", "--format", "json"],
                           cwd=str(repo), capture_output=True, text=True)
        res = json.loads(r.stdout.strip())
        check("empty change set -> empty plan",
              res == {"groups": [], "evals_roots": [], "review_higher": [], "uncovered": [],
                      "no_op_reason_hint": "covered_unchanged"}, str(res))

    print("\n== evals-update v1: evals_roots = plan roots that already ship docs/evals/evals.json ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "CLAUDE.md")                                    # repo root doc (excluded)
        touch(repo, "comp/withEvals/CLAUDE.md")
        touch(repo, "comp/withEvals/docs/evals/evals.json")         # this root HAS an evals suite
        touch(repo, "comp/noEvals/CLAUDE.md")                       # this root has NO evals
        res = plan(repo, ["comp/withEvals/a.swift", "comp/noEvals/b.swift"])
        check("evals_roots contains the root that ships docs/evals/evals.json",
              "comp/withEvals" in res["evals_roots"], str(res.get("evals_roots")))
        check("evals_roots excludes the root without evals (v1 keep-fresh only, never create)",
              "comp/noEvals" not in res["evals_roots"], str(res.get("evals_roots")))
        # An evals suite at a review_higher ancestor (above the group umbrella) is
        # part of the plan's evals scope too — leaves∪umbrellas alone under-reports.
        touch(repo, "comp2/hi/CLAUDE.md")
        touch(repo, "comp2/hi/docs/evals/evals.json")
        touch(repo, "comp2/hi/mid/CLAUDE.md")
        touch(repo, "comp2/hi/mid/a/CLAUDE.md")
        touch(repo, "comp2/hi/mid/b/CLAUDE.md")
        touch(repo, "comp2/unrel/CLAUDE.md")
        touch(repo, "comp2/unrel/docs/evals/evals.json")
        res2 = plan(repo, ["comp2/hi/mid/a/x.swift", "comp2/hi/mid/b/y.swift"])
        check("evals_roots includes a review_higher ancestor that ships evals",
              "comp2/hi" in res2["evals_roots"] and "comp2/hi" in res2["review_higher"], str(res2))
        check("evals_roots excludes an evals-bearing root untouched by this plan",
              "comp2/unrel" not in res2["evals_roots"], str(res2.get("evals_roots")))

    print("\n== evals-update v1: eval-symbols extracts contains-assertion symbols per root ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)
        touch(repo, "comp/m/CLAUDE.md")
        evals = repo / "comp/m/docs/evals/evals.json"
        evals.parent.mkdir(parents=True, exist_ok=True)
        evals.write_text(json.dumps({
            "suite_name": "kb-docs-benchmark",
            "evals": [{"id": 1, "mode": "qa", "questions": [
                {"id": "q1", "assertions": [
                    {"id": "a1", "type": "contains", "text": "PostViewHistoryItemComponent"},
                    {"id": "a2", "type": "contains", "text": "customTitle"},
                ]},
                {"id": "q2", "assertions": [
                    {"id": "a3", "type": "contains", "text": "PostViewHistoryItemComponent"},  # dup -> deduped
                    {"id": "a4", "type": "not_contains", "text": "IgnoredType"},               # non-contains -> ignored
                ]},
            ]}],
        }))
        r = subprocess.run([sys.executable, str(TOOL), "eval-symbols", "--path", "comp/m", "--format", "json"],
                           cwd=str(repo), capture_output=True, text=True)
        res = json.loads(r.stdout.strip())
        check("eval-symbols = deduped sorted contains-symbols; non-contains ignored",
              res == {"comp/m": ["PostViewHistoryItemComponent", "customTitle"]}, str(res))
        touch(repo, "comp/n/CLAUDE.md")     # a root with no evals -> []
        r2 = subprocess.run([sys.executable, str(TOOL), "eval-symbols", "--path", "comp/n", "--format", "json"],
                            cwd=str(repo), capture_output=True, text=True)
        check("root without evals -> []", json.loads(r2.stdout.strip()) == {"comp/n": []}, r2.stdout)
        # Valid JSON, wrong shape (top-level list): fail-open [] instead of an
        # AttributeError crash (Aime P1 on !1270).
        wrong = repo / "comp/w/docs/evals/evals.json"
        wrong.parent.mkdir(parents=True, exist_ok=True)
        wrong.write_text("[]")
        r3 = subprocess.run([sys.executable, str(TOOL), "eval-symbols", "--path", "comp/w", "--format", "json"],
                            cwd=str(repo), capture_output=True, text=True)
        check("valid-JSON-wrong-shape evals -> fail-open [], rc 0",
              r3.returncode == 0 and json.loads(r3.stdout.strip()) == {"comp/w": []},
              f"rc={r3.returncode} out={r3.stdout!r} err={r3.stderr[-200:]!r}")

    print("\n== evals-update v1: eval-gate = MR diff × asserted symbols -> candidate roots ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir(parents=True)

        def git(*argv: str) -> None:
            subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *argv],
                           check=True, capture_output=True, text=True)

        def write_evals(root: str, symbols: list[str]) -> None:
            p = repo / root / "docs/evals/evals.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"evals": [{"questions": [{"assertions": [
                {"type": "contains", "text": s} for s in symbols]}]}]}))

        def gate(base: str) -> dict:
            r = subprocess.run([sys.executable, str(TOOL), "eval-gate", "--base", base],
                               cwd=str(repo), capture_output=True, text=True)
            if r.returncode != 0:
                raise AssertionError(f"eval-gate failed rc={r.returncode}: {r.stderr}")
            return json.loads(r.stdout.strip())

        git("init", "-q")
        git("config", "user.email", "t@test.local")
        git("config", "user.name", "t")
        # Hostile-but-real git config: quotepath=true is git's factory default
        # (non-ASCII paths come back C-quoted); an external differ replaces ±
        # lines entirely. The gate must pin both away on its own git calls.
        git("config", "core.quotepath", "true")
        git("config", "diff.external", "echo EXTERNAL-DIFF-RAN")
        # umbrella + leaf both ship evals asserting the same symbol; a sibling root
        # ships evals whose assertions are only grazed by the MR (word-boundary /
        # shape-filter / scope pins); more roots pin one hardening case each.
        touch(repo, "comp/big/CLAUDE.md")
        write_evals("comp/big", ["LiveGiftPanel", "MUST NOT"])          # phrase filtered by shape
        touch(repo, "comp/big/leaf/CLAUDE.md")
        write_evals("comp/big/leaf", ["LiveGiftPanel", "onGiftSent"])
        (repo / "comp/big/leaf/Impl.swift").write_text("class LiveGiftPanel {}\nfunc onGiftSent() {}\n")
        touch(repo, "comp/other/CLAUDE.md")
        write_evals("comp/other", ["OtherThing", "MUST NOT", "component"])
        (repo / "comp/other/O.swift").write_text("class OtherThing {}\n")
        write_evals("comp/addonly", ["AddOnlyService"])                 # pure-addition pin
        (repo / "comp/addonly/A.swift").write_text("// placeholder\n")
        write_evals("comp/lua", ["LuaGiftEntry"])                       # hunk-parsing pin
        (repo / "comp/lua/gift.lua").write_text("-- LuaGiftEntry: legacy lua gifting entry\nprint('x')\n")
        write_evals("comp/mv", ["MovedThing"])                          # --no-renames pin
        (repo / "comp/mv/M.swift").write_text("class MovedThing {}\n")
        write_evals("comp/uni", ["UniThing"])                           # quotepath pin
        (repo / "comp/uni/组件.swift").write_text("class UniThing {}\n")
        write_evals("comp/gbk", ["GbkThing"])                           # non-UTF-8 bytes pin
        (repo / "comp/gbk/G.m").write_bytes(b"// \xd6\xd0\xce\xc4 legacy\nGbkThing *x;\n")
        badjson = repo / "comp/badjson/docs/evals/evals.json"           # unreadable-suite pin
        badjson.parent.mkdir(parents=True, exist_ok=True)
        badjson.write_text("{not json,")
        (repo / "comp/badjson/B.swift").write_text("class BadJsonThing {}\n")
        git("add", "-A")
        git("commit", "-qm", "v1")
        # The "MR": a rename, a pure addition, a Lua-comment removal, a file moved
        # out of its module, a non-ASCII-named file, a GBK-bytes file, a change
        # under a broken suite — plus comp/other's precision-pin lines.
        (repo / "comp/big/leaf/Impl.swift").write_text(
            "class LiveGiftPanelV2 {}\nfunc onGiftSent() {}\n// migrated from OtherThing\n")
        (repo / "comp/other/O.swift").write_text(
            "class OtherThing {}\n// note: callers MUST NOT retain this\n"
            "class OtherThingV2 {}\n// register component here\n")
        (repo / "comp/addonly/N.swift").write_text("let s = AddOnlyService()\n")
        (repo / "comp/lua/gift.lua").write_text("print('x')\n")
        (repo / "comp/outside").mkdir()
        git("mv", "comp/mv/M.swift", "comp/outside/M.swift")
        (repo / "comp/uni/组件.swift").write_text("class UniThingV2 {}\n")
        (repo / "comp/gbk/G.m").write_bytes(b"// \xd6\xd0\xce\xc4 modern\nGbkThingV2 *x;\n")
        (repo / "comp/badjson/B.swift").write_text("class BadJsonThing2 {}\n")
        git("add", "-A")
        git("commit", "-qm", "v2: the MR")
        res = gate("HEAD~1")
        by_root = {c["root"]: c for c in res["candidates"]}
        check("renamed symbol flags BOTH the leaf and the umbrella suite",
              "comp/big" in by_root and "comp/big/leaf" in by_root, str(res))
        check("hit = the renamed symbol only (word boundary: LiveGiftPanelV2 is not a hit; onGiftSent untouched)",
              by_root.get("comp/big/leaf", {}).get("hit_symbols") == ["LiveGiftPanel"], str(by_root))
        check("precision pins hold: OtherThingV2 (word boundary), 'component'/'MUST NOT' (shape), "
              "OtherThing in ANOTHER root's diff (scope) — comp/other checked but NOT a candidate",
              "comp/other" in res["checked_roots"] and "comp/other" not in by_root, str(res))
        check("candidate carries the changed files that hit its subtree",
              by_root.get("comp/big", {}).get("changed_files") == ["comp/big/leaf/Impl.swift"], str(by_root))
        check("PURE ADDITION of an asserted symbol is a candidate (added lines count)",
              by_root.get("comp/addonly", {}).get("hit_symbols") == ["AddOnlyService"], str(by_root))
        check("removed line whose content starts with '--' (Lua comment) still matches (hunk-aware parsing)",
              by_root.get("comp/lua", {}).get("hit_symbols") == ["LuaGiftEntry"], str(by_root))
        check("file MOVED OUT of its module still flags the old root (--no-renames)",
              by_root.get("comp/mv", {}).get("hit_symbols") == ["MovedThing"], str(by_root))
        check("non-ASCII filename works under quotepath=true (git factory default)",
              by_root.get("comp/uni", {}).get("hit_symbols") == ["UniThing"], str(by_root))
        check("non-UTF-8 (GBK) bytes on changed lines: no crash, symbol still hits",
              by_root.get("comp/gbk", {}).get("hit_symbols") == ["GbkThing"], str(by_root))
        check("broken evals.json: checked + surfaced in unreadable_evals, never a candidate, rc 0",
              "comp/badjson" in res["checked_roots"]
              and res["unreadable_evals"] == ["comp/badjson"]
              and "comp/badjson" not in by_root, str(res))
        # docs/evals-only edit -> maintenance, not a staleness signal: nothing
        # checked. This is the self-loop breaker: the follow-up evals-refresh MR
        # itself passes the gate with zero action.
        (repo / "comp/big/leaf/docs/interface.md").write_text("LiveGiftPanel documented\n")
        write_evals("comp/big/leaf", ["LiveGiftPanelV2", "onGiftSent"])
        git("add", "-A")
        git("commit", "-qm", "v3: docs + evals refresh only")
        res3 = gate("HEAD~1")
        check("docs/evals-only change -> no roots checked, no candidates (self-loop breaker)",
              res3["checked_roots"] == [] and res3["candidates"] == [], str(res3))
        # Misconfiguration fails loudly (a silent [] would read as "evals not stale").
        rbad = subprocess.run([sys.executable, str(TOOL), "eval-gate", "--base", "no-such-ref"],
                              cwd=str(repo), capture_output=True, text=True)
        check("bad --base ref fails loudly, not an empty no-op",
              rbad.returncode != 0 and "git diff failed" in rbad.stderr, rbad.stderr)

    print("\n== evals-update v1.5: eval-add-signal = MR-introduced new symbols per root ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir(parents=True)

        def git(*argv: str) -> None:
            subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *argv],
                           check=True, capture_output=True, text=True)

        def write_evals(root: str, symbols: list[str]) -> None:
            p = repo / root / "docs/evals/evals.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"evals": [{"questions": [{"assertions": [
                {"type": "contains", "text": s} for s in symbols]}]}]}))

        def add_signal(base: str) -> dict:
            r = subprocess.run([sys.executable, str(TOOL), "eval-add-signal", "--base", base],
                               cwd=str(repo), capture_output=True, text=True)
            if r.returncode != 0:
                raise AssertionError(f"eval-add-signal failed rc={r.returncode}: {r.stderr}")
            return json.loads(r.stdout.strip())

        git("init", "-q")
        git("config", "user.email", "t@test.local")
        git("config", "user.name", "t")
        git("config", "core.quotepath", "true")
        git("config", "diff.external", "echo EXT")
        # feat: evals assert one in-code symbol (ExistingWidget) + one PRE-REGISTERED
        # symbol not yet in code (PreRegisteredSymbol) to pin asserted-exclusion
        # independently of base-existence.
        touch(repo, "feat/CLAUDE.md")
        write_evals("feat", ["ExistingWidget", "PreRegisteredSymbol"])
        (repo / "feat/W.swift").write_text("class ExistingWidget {}\n")
        # baseref: pins BASE-EXISTENCE independently — asserts something UNRELATED
        # (AssertedThing), base has a NON-asserted symbol (ExistingHelper); the MR
        # only adds a new USE of it → introduces no new symbol. A mutant that drops
        # the base-existence check would (wrongly) surface ExistingHelper here,
        # because asserted-exclusion does NOT mask it (it isn't asserted).
        touch(repo, "baseref/CLAUDE.md")
        write_evals("baseref", ["AssertedThing"])
        (repo / "baseref/H.swift").write_text("class ExistingHelper {}\n")
        # sig: pins snake_case survival + dotted-chain splitting + pre-existing base
        # of a dotted chain dropped. ABTesting exists at base.
        touch(repo, "sig/CLAUDE.md")
        write_evals("sig", ["SigAsserted"])
        (repo / "sig/S.swift").write_text("class ABTesting {}\n")
        # bigmod: pins the per-root cap + capped_roots surfacing (MR adds >80 new
        # distinct symbol-shaped tokens).
        touch(repo, "bigmod/CLAUDE.md")
        write_evals("bigmod", ["BigAsserted"])
        (repo / "bigmod/Base.swift").write_text("class BaseThing {}\n")
        # badjson: broken suite + a code change -> unreadable, never a candidate.
        (repo / "badjson/docs/evals/evals.json").parent.mkdir(parents=True, exist_ok=True)
        (repo / "badjson/docs/evals/evals.json").write_text("{not json,")
        (repo / "badjson/B.swift").write_text("class BadJsonThing {}\n")
        git("add", "-A")
        git("commit", "-qm", "v1")
        # The "MR": feat gains a genuinely new symbol + a use of an existing one +
        # the pre-registered symbol's real definition + prose directives; baseref
        # only references an existing non-asserted symbol; sig adds a dotted chain
        # on a pre-existing base + a snake_case key; bigmod adds >80 new symbols;
        # newmod is a BRAND-NEW module (absent at base) with its own new evals.
        (repo / "feat/W.swift").write_text(
            "class ExistingWidget {}\n"
            "class NewPublicPanel { let w = ExistingWidget() }\n"
            "class PreRegisteredSymbol {}\n"
            "// MUST handle TODO later, uses lowercaseonly helper\n")
        (repo / "baseref/N.swift").write_text("let u = ExistingHelper()\n")
        (repo / "sig/N.swift").write_text("let a = ABTesting.MyPod.enableFoo\nlet b = enable_new_thing_v2\n")
        (repo / "bigmod/N.swift").write_text(
            "".join(f"class NewSymX{i:03d} {{}}\n" for i in range(85)))
        write_evals("newmod", [])                       # brand-new module, own new evals
        (repo / "newmod/M.swift").write_text("class BrandNewClass {}\n")
        (repo / "badjson/B.swift").write_text("class BadJsonThing2 {}\n")
        git("add", "-A")
        git("commit", "-qm", "v2: the MR")
        res = add_signal("HEAD~1")
        by_root = {c["root"]: c for c in res["add_candidates"]}
        check("genuinely new symbol surfaced; existing/asserted/prose/lowercase all dropped",
              by_root.get("feat", {}).get("new_symbols") == ["NewPublicPanel"], str(res))
        check("PreRegisteredSymbol (new to code but ALREADY asserted) is NOT surfaced",
              "PreRegisteredSymbol" not in by_root.get("feat", {}).get("new_symbols", []), str(by_root))
        check("BASE-EXISTENCE: new use of a pre-existing NON-asserted symbol NOT surfaced",
              "baseref" in res["checked_roots"] and "baseref" not in by_root, str(res))
        check("snake_case key survives; dotted chain split (MyPod/enableFoo new, ABTesting at base dropped)",
              by_root.get("sig", {}).get("new_symbols") == ["MyPod", "enableFoo", "enable_new_thing_v2"], str(by_root))
        check("CAP: >80 new tokens -> root in capped_roots (surfaced, not silently truncated)",
              "bigmod" in res["capped_roots"] and len(by_root.get("bigmod", {}).get("new_symbols", [])) == 80, str(res.get("capped_roots")))
        check("BRAND-NEW module (absent at base, git grep rc=1) surfaces its new symbol",
              by_root.get("newmod", {}).get("new_symbols") == ["BrandNewClass"], str(by_root))
        check("SCOPE: a new symbol under one root does not leak into another root",
              "NewPublicPanel" not in by_root.get("sig", {}).get("new_symbols", [])
              and "NewPublicPanel" not in by_root.get("baseref", {}).get("new_symbols", []), str(by_root))
        check("MUST/TODO prose directives filtered by denoiser (not new symbols)",
              not ({"MUST", "TODO"} & set(by_root.get("feat", {}).get("new_symbols", []))), str(by_root))
        check("broken evals.json checked + surfaced in unreadable_evals, never a candidate",
              "badjson" in res["checked_roots"] and res["unreadable_evals"] == ["badjson"]
              and "badjson" not in by_root, str(res))
        # docs/evals-only change -> nothing checked (self-loop breaker, same as gate).
        (repo / "feat/docs/interface.md").write_text("NewPublicPanel documented\n")
        write_evals("feat", ["ExistingWidget", "PreRegisteredSymbol", "NewPublicPanel"])
        git("add", "-A")
        git("commit", "-qm", "v3: docs + evals only")
        res3 = add_signal("HEAD~1")
        check("docs/evals-only change -> no roots checked, no add candidates",
              res3["checked_roots"] == [] and res3["add_candidates"] == [], str(res3))
        # Directly pin _diff_side_lines(sides="+") = ADDED-ONLY. Black-box masks it
        # (a removed-line symbol is always present at base → dropped, so a "+-"
        # mutant is invisible through eval-add-signal); assert the helper in-process.
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("kb_tool_dsl", str(TOOL))
        _kt = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_kt)
        _sample = ["diff --git a/x b/x", "@@ -1 +1 @@", "-RemovedSym here", "+AddedSym here"]
        check("_diff_side_lines(sides='+') keeps ONLY added content (added-only)",
              _kt._diff_side_lines(_sample, "+") == "AddedSym here"
              and _kt._diff_side_lines(_sample, "+-") == "RemovedSym here\nAddedSym here",
              repr(_kt._diff_side_lines(_sample, "+")))
        # After v3 added NewPublicPanel to the assertions, a later MR that renames
        # it would be an UPDATE (eval-gate), and add-signal must NOT re-surface it.
        rbad = subprocess.run([sys.executable, str(TOOL), "eval-add-signal", "--base", "no-such-ref"],
                              cwd=str(repo), capture_output=True, text=True)
        check("eval-add-signal bad --base fails loudly, not an empty no-op",
              rbad.returncode != 0 and "git diff failed" in rbad.stderr, rbad.stderr)

    print(f"\n==== {'OK' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)} ====")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
