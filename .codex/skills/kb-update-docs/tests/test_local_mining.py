#!/usr/bin/env python3
"""Self-contained LOCAL test for the default (local) conversation-mining path.

Builds a synthetic local Claude Code SDD session in a temp dir, points the miner
at it via CONV_MINER_CLAUDE_BASE, and exercises the real default flow end-to-end:

    discover (SDD fingerprint, bypassing the turn-count gate)
      -> export (AskUserQuestion + user selection + SDD artifact extraction)
      -> secret redaction (+ --no-redact toggle)

No Fornax, no network, no real ~/.claude needed. Run:

    python3 plugins/ttadk/mobile-core/skills/kb-update-docs/tests/test_local_mining.py
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

MINER = Path(__file__).resolve().parent.parent / "scripts" / "conversation_miner.py"
# A clearly-fake credential shape that still matches the redactor's `token=` rule,
# but does NOT look like any real provider token (avoids tripping secret scanners).
FAKE_SECRET = "NOTAREALSECRET_test_dummy_0123456789"

# A realistic local Claude Code SDD session: a user ask, an AskUserQuestion the
# user answers, a written spec artifact (with a planted fake secret + a noise
# Read call that must be dropped), and a closing line.
SESSION = [
    {"type": "user", "timestamp": "2026-06-02T10:00:00Z", "message": {"role": "user",
        "content": [{"type": "text", "text": "帮我给 demo 模块加个新 jsb，走 SDD"}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "q1", "name": "AskUserQuestion", "input": {"questions": [
            {"question": "新 jsb 用哪种注册方式？", "options": [
                {"label": "复用现有 ICommerceMultiHostBridgeList SPI"},
                {"label": "starter 直接 registerIDLMethod"}]}]}}]}},
    {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "q1",
         "content": "复用现有 ICommerceMultiHostBridgeList SPI"}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "w1", "name": "Write", "input": {
            "file_path": ".adk-mobile/specs/099-demo-feature/spec.md",
            "content": ("# Spec: demo feature\n\n（测试用假密钥）token=" + FAKE_SECRET
                        + "\n\nMUST reuse the shared SPI; MUST NOT hardcode the method class.")}}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "r1", "name": "Read", "input": {"file_path": "foo/Bar.kt"}}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "spec 已生成，等你确认。"}]}},
]


def _canonical(project_path: str) -> str:
    p = Path(project_path).resolve()
    return str(p).lower().replace("/", "-").replace("_", "-").replace(" ", "-").strip("-")


def _load_miner():
    spec = importlib.util.spec_from_file_location("conv_miner_under_test", MINER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="convminer_localtest_"))
    base = tmp / "claude_projects"
    project_path = "/demo/convminer-localtest"
    projdir = base / _canonical(project_path)
    projdir.mkdir(parents=True)
    fixture = projdir / "sess-demo.jsonl"
    with open(fixture, "w", encoding="utf-8") as f:
        for rec in SESSION:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Point the miner at the fixture base (env is read at import time).
    os.environ["CONV_MINER_CLAUDE_BASE"] = str(base)
    os.environ["CONV_MINER_CURSOR_BASE"] = str(tmp / "cursor_absent")
    cm = _load_miner()

    failures = []

    def check(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            failures.append(msg)

    print("[1] discover — local SDD session found via fingerprint (turn-count gate bypassed)")
    sessions = cm.discover_sessions(project_path=project_path)
    check(len(sessions) == 1, f"found exactly 1 local session (got {len(sessions)})")
    if sessions:
        s = sessions[0]
        check(s.is_sdd, "flagged is_sdd=True via .adk-mobile/specs fingerprint")
        check(s.spec_name == "099-demo-feature", f"spec_name == 099-demo-feature (got {s.spec_name!r})")
        check(s.source == "claude-code", "source == claude-code")

    print("[2] export — structured extraction + redaction (default ON)")
    turns = cm.export_session(str(fixture), "claude-code")
    blob = "\n".join(t["content"] for t in turns)
    check(any(t["content"].startswith("[AskUserQuestion]") for t in turns), "AskUserQuestion preserved")
    check(any(t["content"].startswith("[User selected]") for t in turns), "user selection preserved")
    check("复用现有 ICommerceMultiHostBridgeList SPI" in blob, "the chosen option text is captured")
    check(any(t["content"].startswith("[SDD artifact: spec.md]") for t in turns), "SDD artifact spec.md preserved")
    check("MUST reuse the shared SPI" in blob, "artifact body content kept")
    check(FAKE_SECRET not in blob, "planted secret REDACTED by default")
    check("[REDACTED]" in blob, "redaction marker present")
    check("foo/Bar.kt" not in blob, "noise Read tool-call dropped")

    print("[3] export --no-redact — toggle restores raw content")
    blob_raw = "\n".join(t["content"] for t in cm.export_session(str(fixture), "claude-code", redact=False))
    check(FAKE_SECRET in blob_raw, "secret present when redaction disabled")

    print("\n--- sample extracted turns (redacted) ---")
    for t in turns[:6]:
        print(f"  [{t['role']}] {t['content'].replace(chr(10), ' ')[:100]}")

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} check(s) failed)")
        return 1
    print(f"RESULT: PASS — local mining works end-to-end ({len(turns)} turns from the local fixture)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
