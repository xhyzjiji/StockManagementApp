#!/usr/bin/env python3
"""Regression tests for `kb_tool.py enforce-writeset` — the deterministic,
file-level write-domain guard.

Each test spins up a REAL temporary git repo (git init + user config + an initial
commit so there is a clean baseline), drives the two-phase snapshot/apply flow,
and asserts on the JSON report, the exit code, and what is left on disk.

Covers:
  (a) editing an allowed `rule.md`               -> kept, exit 0
  (b) creating implementation_map.md + a yaml    -> both reverted, two basename
                                                    violations, exit 1
  (c) editing README.md                          -> reverted (not in ALLOWED)
  (d) mixed allowed rule.md + stray key_logic.md -> only the stray reverted
  (f) baseline safety: a pre-dirty foo.yaml this run never touches is NOT reverted
  (g) rename rule.md -> notes.txt (non-allowed)  -> judged by the NEW path, reverted
      rename rule.md -> workflow.md (allowed)    -> judged by the NEW path, kept
  (h) --no-revert                                -> reports violations, files untouched
  scope warnings: allowed file with no doc root above it -> kept + warned (exit 0);
                  a deeply-nested allowed file under a real doc root -> not warned
  `git rm` of an allowed file                    -> nothing to revert, exit 0
  porcelain parser (synthetic streams via _parse_porcelain_z):
      C  (copy)                                  -> NEW path keyed, OLD consumed
      RM (rename + modify)                        -> NEW path keyed, OLD consumed
      D + ?? remnant (`git rm --cached`)          -> untracked remnant dropped, in
                  either order (a pre-existing committed file, NOT a new violation)

Run with pytest (discovered via the `test_*` functions) or directly.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "kb_tool.py"


# --------------------------------------------------------------------------- helpers
def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), "enforce-writeset", *args, "--repo-root", str(repo)],
        capture_output=True, text=True,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _new_repo(td: str) -> Path:
    repo = Path(td) / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    return repo


def _write(repo: Path, rel: str, content: str = "x\n") -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _commit_all(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")


def _snapshot(repo: Path) -> dict:
    r = _run(repo, "--snapshot")
    assert r.returncode == 0, f"snapshot failed: {r.stderr}"
    return json.loads(r.stdout.strip())


def _apply(repo: Path, *extra: str) -> tuple[dict, int]:
    r = _run(repo, "--apply", *extra)
    return json.loads(r.stdout.strip()), r.returncode


def _exists(repo: Path, rel: str) -> bool:
    return (repo / rel).exists()


def _read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text()


# --------------------------------------------------------------------------- (a)
def test_a_allowed_rule_md_kept():
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        _snapshot(repo)
        _write(repo, "Mod/docs/rule.md", "orig\nedited\n")
        res, rc = _apply(repo)
        assert rc == 0, res
        assert res["allowed_touched"] == ["Mod/docs/rule.md"], res
        assert res["reverted"] == [] and res["violations_basename"] == [], res
        # kept on disk with the edit intact
        assert _read(repo, "Mod/docs/rule.md") == "orig\nedited\n"
        assert res["scope_warnings"] == [], res


# --------------------------------------------------------------------------- (b)
def test_b_new_out_of_domain_files_reverted():
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        _snapshot(repo)
        # two brand-new untracked files, neither an allowed basename
        _write(repo, "Mod/docs/implementation_map.md", "bad\n")
        _write(repo, "Mod/docs/ranking.yaml", "bad\n")
        res, rc = _apply(repo)
        assert rc == 1, res
        assert set(res["violations_basename"]) == {
            "Mod/docs/implementation_map.md", "Mod/docs/ranking.yaml"}, res
        assert set(res["reverted"]) == {
            "Mod/docs/implementation_map.md", "Mod/docs/ranking.yaml"}, res
        # untracked => removed from disk
        assert not _exists(repo, "Mod/docs/implementation_map.md")
        assert not _exists(repo, "Mod/docs/ranking.yaml")


def test_b_tracked_out_of_domain_file_checkout_restored():
    # The (b) variant where the out-of-domain file is already TRACKED and this run
    # MODIFIES it: revert restores the committed content via `git checkout --`.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _write(repo, "Mod/docs/implementation_map.md", "committed\n")
        _commit_all(repo)
        _snapshot(repo)
        _write(repo, "Mod/docs/implementation_map.md", "committed\nTAMPERED\n")
        res, rc = _apply(repo)
        assert rc == 1, res
        assert res["violations_basename"] == ["Mod/docs/implementation_map.md"], res
        # tracked => restored to committed content, NOT deleted
        assert _exists(repo, "Mod/docs/implementation_map.md")
        assert _read(repo, "Mod/docs/implementation_map.md") == "committed\n"


# --------------------------------------------------------------------------- (c)
def test_c_readme_md_reverted():
    # README.md is deliberately NOT in the allow-list.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _write(repo, "Mod/README.md", "readme\n")
        _commit_all(repo)
        _snapshot(repo)
        _write(repo, "Mod/README.md", "readme\nedited\n")
        res, rc = _apply(repo)
        assert rc == 1, res
        assert res["violations_basename"] == ["Mod/README.md"], res
        assert _read(repo, "Mod/README.md") == "readme\n"  # restored


# --------------------------------------------------------------------------- (d)
def test_d_mixed_only_out_of_domain_reverted():
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        _snapshot(repo)
        _write(repo, "Mod/docs/rule.md", "orig\nedited\n")    # allowed -> keep
        _write(repo, "Mod/docs/key_logic.md", "stray\n")      # not allowed -> revert
        res, rc = _apply(repo)
        assert rc == 1, res
        assert res["allowed_touched"] == ["Mod/docs/rule.md"], res
        assert res["violations_basename"] == ["Mod/docs/key_logic.md"], res
        assert res["reverted"] == ["Mod/docs/key_logic.md"], res
        # rule.md kept with its edit; key_logic.md gone
        assert _read(repo, "Mod/docs/rule.md") == "orig\nedited\n"
        assert not _exists(repo, "Mod/docs/key_logic.md")


# --------------------------------------------------------------------------- (f)
def test_f_baseline_safety_pre_dirty_file_untouched():
    # KEY SAFETY PROPERTY: a file already dirty at snapshot time that THIS run never
    # touches must NOT be reverted by --apply, even though it is an out-of-domain
    # basename. The baseline records it as a user/unrelated change.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _write(repo, "foo.yaml", "committed\n")
        _commit_all(repo)
        # dirty foo.yaml BEFORE snapshot (user/unrelated change)
        _write(repo, "foo.yaml", "committed\nUSER EDIT\n")
        snap = _snapshot(repo)
        assert "foo.yaml" in snap["baseline"], snap
        # this run only touches the allowed rule.md
        _write(repo, "Mod/docs/rule.md", "orig\nedited\n")
        res, rc = _apply(repo)
        assert rc == 0, res
        assert res["reverted"] == [], res
        assert res["allowed_touched"] == ["Mod/docs/rule.md"], res
        # foo.yaml's user edit is preserved untouched
        assert _read(repo, "foo.yaml") == "committed\nUSER EDIT\n"


def test_f_baseline_dirty_untracked_file_untouched():
    # Same property for an untracked pre-existing file: a stray untracked file
    # present at snapshot time is in the baseline and must not be deleted.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        _write(repo, "scratch.yaml", "preexisting untracked\n")   # untracked before snapshot
        snap = _snapshot(repo)
        assert "scratch.yaml" in snap["baseline"], snap
        _write(repo, "Mod/docs/rule.md", "orig\nedited\n")
        res, rc = _apply(repo)
        assert rc == 0, res
        assert _exists(repo, "scratch.yaml"), "pre-existing untracked file must survive"
        assert _read(repo, "scratch.yaml") == "preexisting untracked\n"


# --------------------------------------------------------------------------- (g)
def test_g_rename_judged_by_new_path():
    # Renaming an allowed rule.md to a non-allowed notes.txt: porcelain reports the
    # rename via the NEW path; enforce-writeset must judge notes.txt (a violation).
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        _snapshot(repo)
        _git(repo, "mv", "Mod/docs/rule.md", "Mod/docs/notes.txt")  # staged rename
        res, rc = _apply(repo)
        assert rc == 1, res
        # judged by the NEW path
        assert "Mod/docs/notes.txt" in res["violations_basename"], res
        # the old path must NOT appear as a separate entry
        assert "Mod/docs/rule.md" not in res["reverted"], res


def test_g_rename_to_allowed_basename_kept():
    # Renaming an allowed rule.md to ANOTHER allowed basename (workflow.md) is judged
    # by the NEW path, which is in the allow-list → kept, exit 0, no revert.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        _snapshot(repo)
        _git(repo, "mv", "Mod/docs/rule.md", "Mod/docs/workflow.md")  # allowed -> allowed
        res, rc = _apply(repo)
        assert rc == 0, res
        assert res["allowed_touched"] == ["Mod/docs/workflow.md"], res
        assert res["reverted"] == [] and res["violations_basename"] == [], res
        # new path kept on disk, old path gone
        assert _exists(repo, "Mod/docs/workflow.md")
        assert not _exists(repo, "Mod/docs/rule.md")


# Real git does not emit a `C` (copy) status for a plain `git add` of a copied
# file — copy detection is a diff-time feature, not a status-of-an-add one — so the
# `C` branch of the porcelain parser is exercised directly via a synthetic stream
# through the extracted pure parser `_parse_porcelain_z`.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("kb_tool", TOOL)
_kb_tool = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_kb_tool)


def test_parser_copy_code_keys_new_path_and_consumes_old():
    # `C` (copy): `Cxy <new>\0<old>\0`. The parser must key on the NEW path and
    # consume the OLD token (not surface it as its own entry).
    raw = "C  Mod/docs/notes.txt\x00Mod/docs/rule.md\x00"
    entries = _kb_tool._parse_porcelain_z(raw)
    assert entries == {"Mod/docs/notes.txt": "C "}, entries


def test_parser_rename_with_modification_keys_new_path():
    # `RM` (rename + worktree modification): NEW path keyed, OLD consumed, code RM.
    raw = "RM Mod/docs/workflow.md\x00Mod/docs/rule.md\x00"
    entries = _kb_tool._parse_porcelain_z(raw)
    assert entries == {"Mod/docs/workflow.md": "RM"}, entries


def test_parser_index_delete_plus_untracked_remnant_drops_untracked():
    # `git rm --cached <p>` stream: `D  <p>\0?? <p>\0`. The `??` remnant of an
    # index-only delete must be dropped (it is a pre-existing committed file, not a
    # new untracked one), leaving NO entry for that path.
    raw = "D  Mod/docs/notes.txt\x00?? Mod/docs/notes.txt\x00"
    entries = _kb_tool._parse_porcelain_z(raw)
    assert entries == {}, entries


def test_parser_untracked_remnant_dropped_regardless_of_order():
    # Order-independence: even if the `??` appeared BEFORE the `D` (it never does
    # from real git, but the parser must not rely on order), the remnant is dropped.
    raw = "?? Mod/docs/notes.txt\x00D  Mod/docs/notes.txt\x00"
    entries = _kb_tool._parse_porcelain_z(raw)
    assert entries == {}, entries


# --------------------------------------------------------------------------- scope warnings
def test_scope_warnings_populated_but_kept():
    # An allowed basename (rule.md) created in a dir with NO doc root anywhere above
    # it (no CLAUDE.md, no docs/{...}) is KEPT (allowed basename, exit semantics
    # unaffected) but recorded as a non-blocking scope warning so the author can
    # eyeball the placement. This is the only path that populates scope_warnings.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        # commit something unrelated so there is a clean baseline
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        _snapshot(repo)
        # rule.md under Mod/notdocs/ — allowed basename, but Mod/notdocs is not a
        # doc root and has no doc root above it below the ceiling.
        _write(repo, "Mod/notdocs/rule.md", "stray-but-allowed\n")
        res, rc = _apply(repo)
        assert rc == 0, res  # non-blocking: nothing reverted
        assert res["allowed_touched"] == ["Mod/notdocs/rule.md"], res
        assert res["scope_warnings"] == ["Mod/notdocs/rule.md"], res
        assert res["reverted"] == [] and res["violations_basename"] == [], res
        # kept on disk
        assert _exists(repo, "Mod/notdocs/rule.md")


def test_scope_warnings_nested_under_doc_root_not_warned():
    # Regression: a deeply nested allowed file UNDER a real doc root's docs/ tree
    # (Mod/docs/sub/rule.md, owned by the Mod doc root) must NOT be flagged — the
    # scope check walks to the ceiling, not just changed_dir / a literal docs/ parent.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")   # establishes Mod as a doc root
        _commit_all(repo)
        _snapshot(repo)
        _write(repo, "Mod/docs/sub/rule.md", "nested\n")
        res, rc = _apply(repo)
        assert rc == 0, res
        assert "Mod/docs/sub/rule.md" in res["allowed_touched"], res
        assert res["scope_warnings"] == [], res


# --------------------------------------------------------------------------- deletion + untracked remnant (P1)
def test_index_delete_leaves_untracked_remnant_not_a_violation():
    # `git rm --cached <p>` removes a committed file from the index but leaves it on
    # disk, so porcelain reports BOTH `D  <p>` (index delete) AND `?? <p>` (now
    # untracked). That `??` is a PRE-EXISTING committed file, not one this run
    # created — the guard must NOT treat it as a new untracked violation and must
    # NOT delete it, even though `notes.txt` is an out-of-domain basename.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _write(repo, "Mod/docs/notes.txt", "committed\n")  # out-of-domain basename
        _commit_all(repo)
        _snapshot(repo)
        # index-only delete: file stays on disk, becomes untracked
        _git(repo, "rm", "--cached", "-q", "Mod/docs/notes.txt")
        res, rc = _apply(repo)
        # the cached-deleted-but-on-disk file is NOT this run's creation:
        assert "Mod/docs/notes.txt" not in res["violations_basename"], res
        assert "Mod/docs/notes.txt" not in res["reverted"], res
        # and it survives on disk untouched
        assert _exists(repo, "Mod/docs/notes.txt"), "committed file must NOT be deleted"
        assert _read(repo, "Mod/docs/notes.txt") == "committed\n"
        assert rc == 0, res


def test_deletion_of_allowed_file_no_revert():
    # `git rm` of an allowed doc file: the file is gone from disk → nothing to
    # revert, no violation, exit 0. Confirms the D-skip path.
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _write(repo, "Mod/docs/workflow.md", "orig\n")
        _commit_all(repo)
        _snapshot(repo)
        _git(repo, "rm", "-q", "Mod/docs/rule.md")   # staged deletion, file gone
        res, rc = _apply(repo)
        assert rc == 0, res
        assert res["reverted"] == [], res
        assert res["allowed_touched"] == [], res
        assert res["violations_basename"] == [], res
        assert not _exists(repo, "Mod/docs/rule.md")


# --------------------------------------------------------------------------- (h)
def test_h_no_revert_reports_but_does_not_touch():
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        _snapshot(repo)
        _write(repo, "Mod/docs/implementation_map.md", "bad\n")   # untracked violation
        _write(repo, "Mod/docs/rule.md", "orig\nedited\n")        # allowed edit
        res, rc = _apply(repo, "--no-revert")
        # exit code still reflects that violations exist
        assert rc == 1, res
        assert res["violations_basename"] == ["Mod/docs/implementation_map.md"], res
        assert res["reverted"] == ["Mod/docs/implementation_map.md"], res
        # ...but nothing was actually touched on disk
        assert _exists(repo, "Mod/docs/implementation_map.md"), "file must NOT be removed"
        assert _read(repo, "Mod/docs/implementation_map.md") == "bad\n"
        assert _read(repo, "Mod/docs/rule.md") == "orig\nedited\n"


# --------------------------------------------------------------------------- error handling
def test_apply_without_snapshot_errors():
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _write(repo, "Mod/docs/rule.md", "orig\n")
        _commit_all(repo)
        r = _run(repo, "--apply")   # no snapshot was taken
        assert r.returncode != 0
        assert "baseline file not found" in (r.stderr + r.stdout)


def test_non_git_dir_errors():
    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / "plain"
        plain.mkdir()
        r = subprocess.run(
            [sys.executable, str(TOOL), "enforce-writeset", "--snapshot",
             "--repo-root", str(plain)],
            capture_output=True, text=True,
        )
        # --repo-root with no .git marker is refused by _repo_from_args
        assert r.returncode != 0
        assert "repo marker" in r.stderr or "not a git repository" in r.stderr


def test_snapshot_and_apply_mutually_exclusive():
    with tempfile.TemporaryDirectory() as td:
        repo = _new_repo(td)
        _commit_all(repo) if False else _write(repo, "x.md", "x")
        _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "init")
        r = _run(repo, "--snapshot", "--apply")
        assert r.returncode != 0  # argparse mutually-exclusive group


def _run_all_directly() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = []
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failures.append(fn.__name__)
    print(f"\n==== {'OK' if not failures else 'FAILED: ' + ', '.join(failures)} ====")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all_directly())
