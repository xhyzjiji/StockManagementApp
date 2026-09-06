#!/usr/bin/env python3
"""Regression tests for `kb_tool.py eval-bootstrap-signal` — the third evals gate:
a doc root that ships NO evals suite at all.

Why this gate exists, restated so the tests are readable without the SKILL:
the freshness gate keeps an existing suite honest and the coverage gate adds a
question to an existing suite. Both find their roots by *evals presence*, so a
root with no suite is never visited at all — leaving the single most common
production shape (docs exist, evals never did) completely untested. The chain
then reports `no_evals` and scores nothing, which on a dashboard is
indistinguishable from "the benchmark is broken".

Each test builds a REAL temporary git repo with two commits (base -> head) and
asserts on the JSON contract.

Covers:
  (a) docs-bearing root, no suite, MR adds a new symbol -> bootstrap candidate
  (b) same root but a suite EXISTS at head              -> skipped_have_suite,
                                                           never a candidate
  (c) only the docs bundle changed under the root       -> no_new_symbols
      (a doc-only edit introduces no code symbol to test)
  (d) the symbol already existed at base                -> filtered out, not "new"
  (e) a root that does not exist at head                -> unknown_roots, and it
      does NOT quietly read as a clean result
  (f) --roots is required (the tool must never re-derive "what is a doc root")

Run with pytest or directly.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "kb_tool.py"


# --------------------------------------------------------------------------- helpers
def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _write(repo: Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _init(repo: Path) -> None:
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _run(repo: Path, base: str, head: str, roots: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), "eval-bootstrap-signal",
         "--repo-root", str(repo), "--base", base, "--head", head, "--roots", roots],
        capture_output=True, text=True,
    )


ROOT = "features/media/src/main/kotlin/com/kbtest/media"


def _base_repo(tmp: Path, with_suite: bool = False) -> str:
    """A doc-bearing root with one source file. Optionally ships an evals suite."""
    _init(tmp)
    _write(tmp, f"{ROOT}/CLAUDE.md", "# media\n")
    _write(tmp, f"{ROOT}/docs/rule.md", "WHEN uploading: MUST retry.\n")
    _write(tmp, f"{ROOT}/MediaUploader.kt",
           "class MediaUploader {\n    fun upload() {}\n}\n")
    if with_suite:
        _write(tmp, f"{ROOT}/docs/evals/evals.json",
               json.dumps({"questions": [
                   {"id": "q1", "question": "how?", "expect": {"contains": ["upload"]}}
               ]}))
    return _commit(tmp, "base")


# --------------------------------------------------------------------------- tests
def test_root_without_suite_yields_bootstrap_candidate():
    """(a) The whole point: docs exist, evals do not, the MR adds a new symbol."""
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        base = _base_repo(repo)
        _write(repo, f"{ROOT}/MediaUploader.kt",
               "class MediaUploader {\n"
               "    fun upload() {}\n"
               "    fun resumeUpload(from: Long) {}\n"
               "}\n")
        _write(repo, f"{ROOT}/docs/rule.md",
               "WHEN uploading: MUST retry.\nWHEN resuming: MUST NOT re-send confirmed chunks.\n")
        head = _commit(repo, "add resume")

        r = _run(repo, base, head, ROOT)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)

        assert out["checked_roots"] == [ROOT]
        assert out["skipped_have_suite"] == []
        assert out["unknown_roots"] == []
        cands = {c["root"]: c for c in out["bootstrap_candidates"]}
        assert ROOT in cands, out
        assert "resumeUpload" in cands[ROOT]["new_symbols"], cands[ROOT]
        # the docs bundle must not be offered as evidence of a code symbol
        assert all(not f.startswith(f"{ROOT}/docs/") for f in cands[ROOT]["changed_files"])


def test_root_with_existing_suite_is_handed_off_not_bootstrapped():
    """(b) A root that already has a suite belongs to the other two gates.

    It must be reported under `skipped_have_suite` — visible hand-off, never a
    silent drop: 'absent from the output' and 'deliberately not ours' look the
    same to a reader, and only one of them is a bug.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        base = _base_repo(repo, with_suite=True)
        _write(repo, f"{ROOT}/MediaUploader.kt",
               "class MediaUploader {\n    fun upload() {}\n    fun resumeUpload() {}\n}\n")
        head = _commit(repo, "add resume")

        out = json.loads(_run(repo, base, head, ROOT).stdout)
        assert out["skipped_have_suite"] == [ROOT]
        assert out["bootstrap_candidates"] == []


def test_docs_only_change_is_not_a_candidate():
    """(c) A doc-only edit introduces no code symbol — nothing to test."""
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        base = _base_repo(repo)
        _write(repo, f"{ROOT}/docs/rule.md", "WHEN uploading: MUST retry twice.\n")
        head = _commit(repo, "docs only")

        out = json.loads(_run(repo, base, head, ROOT).stdout)
        assert out["bootstrap_candidates"] == []
        assert out["no_new_symbols"] == [ROOT]


def test_symbol_that_already_existed_is_not_new():
    """(d) A pre-existing symbol appearing on an added line is not new knowledge.

    ⚠ This test was written wrong TWICE and mutation testing caught both. Read
    this before "simplifying" it:

      v1 re-indented the file with blank lines → the added lines carried no
      tokens at all → `bootstrap_candidates` was empty → the `for c in ...` loop
      asserted nothing. Deleting the base-existence filter left it green.

      v2 put `upload()` on the added line. But `upload` never reaches the filter:
      `_is_new_symbol_candidate("upload")` is **False** (the denoiser drops bare
      all-lowercase words). Asserting "upload is absent" therefore held for a
      completely different reason than the one under test — still green with the
      filter deleted.

    So the old symbol on the added line must ALSO clear the denoiser.
    `MediaUploader` does (PascalCase) and exists at base; `cloneUploader` is new.
    Same added line, opposite verdicts — that asymmetry is the only shape that
    actually exercises the filter, and both halves are asserted so the test can
    never pass by finding nothing.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        base = _base_repo(repo)
        _write(repo, f"{ROOT}/MediaUploader.kt",
               "class MediaUploader {\n"
               "    fun upload() {}\n"
               "    fun cloneUploader(): MediaUploader = MediaUploader()\n"
               "}\n")
        head = _commit(repo, "add cloneUploader returning the existing MediaUploader")

        out = json.loads(_run(repo, base, head, ROOT).stdout)
        cands = {c["root"]: c for c in out["bootstrap_candidates"]}
        # positive half: without this the test could pass by finding nothing
        assert ROOT in cands, out
        assert "cloneUploader" in cands[ROOT]["new_symbols"], cands[ROOT]
        # negative half: the filter under test. MediaUploader is on the SAME
        # added line and clears the denoiser — the only thing that removes it is
        # the base-existence check.
        assert "MediaUploader" not in cands[ROOT]["new_symbols"], cands[ROOT]


def test_unknown_root_is_surfaced_not_swallowed():
    """(e) A root absent at head is a caller mistake, not 'nothing to do'.

    Returning a quiet empty result here would read as a clean bill of health for
    a root nobody ever looked at.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        base = _base_repo(repo)
        _write(repo, f"{ROOT}/MediaUploader.kt",
               "class MediaUploader {\n    fun upload() {}\n    fun resumeUpload() {}\n}\n")
        head = _commit(repo, "add resume")

        out = json.loads(_run(repo, base, head, "features/does-not-exist").stdout)
        assert out["unknown_roots"] == ["features/does-not-exist"]
        assert out["checked_roots"] == []
        assert out["bootstrap_candidates"] == []


def test_roots_is_required():
    """(f) The tool must never guess what counts as a doc root.

    The other two gates find roots by evals presence — the very thing that is
    false by construction here. Inferring it would put a SECOND definition of
    'doc root' in a second place, and the two would drift.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        base = _base_repo(repo)
        head = _commit(repo, "noop") if False else base
        r = subprocess.run(
            [sys.executable, str(TOOL), "eval-bootstrap-signal",
             "--repo-root", str(repo), "--base", base, "--head", head],
            capture_output=True, text=True,
        )
        assert r.returncode != 0
        assert "--roots" in r.stderr


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
