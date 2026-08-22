#!/usr/bin/env python3
"""Self-contained test for the Fornax remote-trace adapter, both shapes.

Fornax returns two different trace shapes and `--source fornax` must handle both
transparently:

  - cursor space  : JSONL, one hook span per line. The conversation lives in
                    beforeSubmitPrompt.input.prompt (user) and
                    afterAgentThought/afterAgentResponse.output.text (assistant).
  - default/llmgw : a single model-call span with an embedded [{"role","parts"}]
                    array (codex / claude-cli).

This builds a synthetic fixture for each shape (no network, no real trace file)
and asserts the adapter:
  * extracts the cursor conversation in chronological order, dropping tool/shell
    noise spans;
  * still handles the embedded-parts shape (regression);
  * redacts secrets by default;
  * degrades to [] on missing / malformed input;
  * lets pick_complete_trace count messages for BOTH shapes (a cursor trace must
    not score 0, which used to drop it whenever llmgw candidates were present).

Run:  python3 plugins/ttadk/mobile-core/skills/kb-update-docs/tests/test_fornax_cursor.py
"""

import importlib.util
import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
MINER = SCRIPTS / "conversation_miner.py"
PICKER = SCRIPTS.parent.parent / "find-sdd-trace" / "scripts" / "pick_complete_trace.py"

FAKE_SECRET = "NOTAREALSECRET_test_dummy_0123456789"


def _tags(hook, ts):
    return {
        "cursor_version": "3.7.27",
        "conversation_id": "conv-abc",
        "fornax_space_id": "7590053680642274820",
        "call_options": json.dumps({"hook_event_name": hook, "trigger_timestamp": ts}),
    }


def _conv_span(cid, hook, ts, text, user=False):
    """One cursor conversation span tagged with an explicit conversation_id, used
    to build fragmented-across-files fixtures for the conversation_id regrouping."""
    tags = {
        "cursor_version": "3.7.27",
        "conversation_id": cid,
        "fornax_space_id": "7590053680642274820",
        "call_options": json.dumps({"hook_event_name": hook, "trigger_timestamp": ts, "conversation_id": cid}),
    }
    span = {"span_name": hook, "span_type": hook, "started_at": str(ts), "custom_tags": tags}
    if user:
        span["input"], span["output"] = json.dumps({"prompt": text}), "{}"
    else:
        span["input"], span["output"] = "{}", json.dumps({"text": text})
    return span


# Cursor hook spans, written to the file OUT OF ORDER on purpose (started_at must
# drive the reconstructed order, not file order). Noise spans (preToolUse,
# afterShellExecution) must be dropped. One assistant text carries a planted
# secret to exercise redaction.
CURSOR_SPANS = [
    {"span_name": "afterAgentResponse", "span_type": "afterAgentResponse", "started_at": "1004",
     "input": "{}", "output": json.dumps({"duration_ms": 20, "text": "方案：复用 SPI，MUST NOT hardcode。token=" + FAKE_SECRET}),
     "custom_tags": _tags("afterAgentResponse", 1004)},
    {"span_name": "beforeSubmitPrompt", "span_type": "beforeSubmitPrompt", "started_at": "1000",
     "input": json.dumps({"attachments": [], "prompt": "帮我给 demo 加个新 jsb，走 SDD"}), "output": "{}",
     "custom_tags": _tags("beforeSubmitPrompt", 1000)},
    {"span_name": "afterShellExecution", "span_type": "afterShellExecution", "started_at": "1003",
     "input": "{}", "output": json.dumps({"exit_code": 0}), "custom_tags": _tags("afterShellExecution", 1003)},
    {"span_name": "afterAgentThought", "span_type": "afterAgentThought", "started_at": "1002",
     "input": "{}", "output": json.dumps({"duration_ms": 10, "text": "先看仓库状态。"}),
     "custom_tags": _tags("afterAgentThought", 1002)},
    {"span_name": "preToolUse", "span_type": "preToolUse", "started_at": "1001",
     "input": json.dumps({"tool": "Read"}), "output": "{}", "custom_tags": _tags("preToolUse", 1001)},
]

# Default/llmgw shape: single object with a serialized [{"role","parts"}] array
# nested in a stringified field, exactly how _find_fornax_messages walks it.
_PARTS = [
    {"role": "user", "parts": [{"type": "text", "content": "llmgw 用户问题"}]},
    {"role": "assistant", "parts": [{"type": "text", "content": "llmgw 助手回答"}]},
]
LLMGW_TRACE = {
    "span_name": "llmgw.proxy.native", "span_type": "model",
    "input": json.dumps({"conversation": json.dumps(_PARTS)}),
}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    cm = _load(MINER, "conv_miner_under_test")
    pick = _load(PICKER, "pick_trace_under_test")
    tmp = Path(tempfile.mkdtemp(prefix="fornax_cursor_test_"))

    cursor_file = tmp / "trace_cursor.json"
    with open(cursor_file, "w", encoding="utf-8") as f:
        for span in CURSOR_SPANS:
            f.write(json.dumps(span, ensure_ascii=False) + "\n")

    llmgw_file = tmp / "trace_llmgw.json"
    llmgw_file.write_text(json.dumps(LLMGW_TRACE, ensure_ascii=False), encoding="utf-8")

    failures = []

    def check(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            failures.append(msg)

    print("[1] cursor JSONL — shape auto-detected as cursor spans")
    check(cm._looks_like_cursor_spans(CURSOR_SPANS), "_looks_like_cursor_spans True on cursor spans")
    check(not cm._looks_like_cursor_spans([LLMGW_TRACE]), "_looks_like_cursor_spans False on llmgw object")

    print("[2] cursor — load_fornax_records extracts conversation in chronological order")
    recs = cm.load_fornax_records(str(cursor_file))
    roles = [r["message"]["role"] for r in recs]
    check(len(recs) == 3, f"3 conversation records (dropped tool/shell noise) (got {len(recs)})")
    check(roles == ["user", "assistant", "assistant"], f"order user,assistant,assistant (got {roles})")
    if len(recs) == 3:
        texts = [r["message"]["content"][0]["text"] for r in recs]
        check(texts[0].startswith("帮我给 demo"), "first turn is the beforeSubmitPrompt user prompt")
        check(texts[1] == "先看仓库状态。", "second turn is the earlier afterAgentThought (ts 1002 before 1004)")
        check("复用 SPI" in texts[2], "third turn is the afterAgentResponse text")

    print("[3] cursor — export_session(source=fornax) end-to-end + redaction default ON")
    turns = cm.export_session(str(cursor_file), "fornax")
    blob = "\n".join(t["content"] for t in turns)
    check(len(turns) == 3, f"3 turns exported (got {len(turns)})")
    check("帮我给 demo 加个新 jsb" in blob, "user prompt text captured")
    check("MUST NOT hardcode" in blob, "assistant response text captured")
    check(FAKE_SECRET not in blob, "planted secret REDACTED by default")
    check("[REDACTED]" in blob, "redaction marker present")
    check("Read" not in blob and "exit_code" not in blob, "tool/shell noise spans dropped")

    print("[4] llmgw embedded-parts shape — still works (regression)")
    recs2 = cm.load_fornax_records(str(llmgw_file))
    check(len(recs2) == 2, f"2 records from embedded parts (got {len(recs2)})")
    blob2 = "\n".join(
        c.get("text", "")
        for r in recs2 for c in r["message"]["content"] if isinstance(c, dict)
    )
    check("llmgw 用户问题" in blob2 and "llmgw 助手回答" in blob2, "both parts messages extracted")

    print("[5] graceful degradation")
    check(cm.load_fornax_records(str(tmp / "does_not_exist.json")) == [], "missing file -> []")
    bad = tmp / "bad.json"
    bad.write_text("{not json at all", encoding="utf-8")
    check(cm.load_fornax_records(str(bad)) == [], "malformed file -> []")

    print("[6] pick_complete_trace — cursor score is message-comparable (excludes afterAgentThought)")
    # Live scoring: a cursor conversation is scored by message-like turns
    # (beforeSubmitPrompt + afterAgentResponse), NOT by raw span count — so the
    # streaming afterAgentThought spans don't inflate a cursor score past an llmgw
    # message count. CURSOR_SPANS = 1 prompt + 1 thought + 1 response.
    six = pick._collect([str(cursor_file)])
    cranked = pick._group_cursor_conversations(six)
    check(len(cranked) == 1, f"one cursor conversation grouped (got {len(cranked)})")
    _cid, _spans, _score = cranked[0]
    check(len(_spans) == 5, f"ALL 5 spans kept (incl. tool/shell) for SDD-marker survival (got {len(_spans)})")
    check(_score == 2, f"score counts only prompt+response, NOT thought/tool spans (got {_score})")
    lcands = pick._llmgw_candidates(pick._collect([str(llmgw_file)]))
    check(lcands and lcands[0][0] == 2, f"llmgw candidate scored by message count 2 (got {lcands})")

    print("[7] pick_complete_trace — cursor conversation fragmented across trace_ids")
    # Fornax scatters ONE cursor conversation (conv-FULL) across three trace files,
    # OUT OF ORDER. A DISTRACTOR conversation (conv-FRAG) sits wholly in one file —
    # the OLD per-file pick would crown the fragment. Grouping by conversation_id
    # must pick conv-FULL and reassemble it. conv-FULL msg-score = 2 prompts + 2
    # responses = 4 (its 2 thoughts don't count); conv-FRAG = 1 prompt + 1 response = 2.
    fdir = Path(tempfile.mkdtemp(prefix="fornax_cursor_frag_"))
    (fdir / "trace_a.json").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in [
        _conv_span("conv-FULL", "beforeSubmitPrompt", 1000, "问题一", user=True),
        _conv_span("conv-FULL", "afterAgentResponse", 1005, "回答一"),
    ]), encoding="utf-8")
    (fdir / "trace_b.json").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in [
        _conv_span("conv-FRAG", "beforeSubmitPrompt", 1001, "干扰问题", user=True),
        _conv_span("conv-FRAG", "afterAgentThought", 1002, "干扰思考"),
        _conv_span("conv-FRAG", "afterAgentResponse", 1003, "干扰回答"),
    ]), encoding="utf-8")
    (fdir / "trace_c.json").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in [
        _conv_span("conv-FULL", "beforeSubmitPrompt", 1010, "问题二", user=True),
        _conv_span("conv-FULL", "afterAgentResponse", 1015, "回答二"),
    ]), encoding="utf-8")
    (fdir / "trace_d.json").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in [
        _conv_span("conv-FULL", "afterAgentThought", 1012, "思考中"),
        _conv_span("conv-FULL", "afterAgentThought", 1013, "继续思考"),
    ]), encoding="utf-8")

    files = pick._collect([str(fdir)])
    check(pick._file_is_cursor(files[0]), "trace file detected as cursor-shaped")
    ranked = pick._group_cursor_conversations(files)
    top_cid, top_spans, top_score = ranked[0]
    check(top_cid == "conv-FULL", f"winner grouped by conversation_id is conv-FULL (got {top_cid})")
    check(len(top_spans) == 6, f"conv-FULL keeps all 6 spans (incl. thoughts) for materialization (got {len(top_spans)})")
    check(top_score == 4, f"conv-FULL msg-score = 2 prompts + 2 responses = 4 (got {top_score})")
    frag_score = dict((c, sc) for c, s, sc in ranked).get("conv-FRAG")
    check(frag_score == 2, f"distractor conv-FRAG msg-score = 2, ranked below conv-FULL (got {frag_score})")

    materialized = pick._materialize_conversation(top_cid, top_spans, fdir)
    check(materialized.exists() and materialized.name.startswith("_conversation_"), "winner materialized to one _conversation_*.jsonl")
    check("trace_" not in materialized.name, "materialized file is not re-collected as a trace_*.json")
    mrecs = cm.load_fornax_records(str(materialized))
    mtexts = [r["message"]["content"][0]["text"] for r in mrecs]
    check(len(mrecs) == 6, f"miner extracts all 6 records of the reassembled conversation (got {len(mrecs)})")
    check(mtexts[0] == "问题一" and mtexts[-1] == "回答二", f"records ordered by started_at across files (got {mtexts})")

    print("[8] pick_complete_trace — UNIFIED pool: llmgw candidate not dropped when a cursor chat shares the dir")
    # A big llmgw SDD trace (8 msgs) next to a small UNRELATED cursor chat. The
    # pool must rank both shapes together and pick the llmgw trace.
    udir = Path(tempfile.mkdtemp(prefix="fornax_unified_"))
    big_parts = [{"role": ("user" if i % 2 == 0 else "assistant"),
                  "parts": [{"type": "text", "content": f"sdd turn {i}"}]} for i in range(8)]
    (udir / "trace_llmgw_sdd.json").write_text(
        json.dumps({"span_type": "model", "input": json.dumps({"conversation": json.dumps(big_parts)})},
                   ensure_ascii=False), encoding="utf-8")
    (udir / "trace_cursor_chat.json").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in [
        _conv_span("conv-UNREL", "beforeSubmitPrompt", 500, "无关闲聊", user=True),
        _conv_span("conv-UNREL", "afterAgentResponse", 501, "无关回答"),
    ]), encoding="utf-8")
    ucands = pick._build_candidates(pick._collect([str(udir)]), udir)
    kinds = {c[2] for c in ucands}
    check(kinds == {"cursor", "llmgw"}, f"both shapes in the candidate pool (got {kinds})")
    top_score, top_path, top_kind, _ = ucands[0]
    check(top_kind == "llmgw" and top_score == 8, f"unified winner is the 8-msg llmgw SDD trace, not the cursor chat (got {top_kind}/{top_score})")
    # mirror: a big cursor conversation (msg-score 3) beats a small llmgw trace (2 msgs)
    (udir / "trace_cursor_chat.json").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in [
        _conv_span("conv-BIG", "beforeSubmitPrompt", 500, "问", user=True),
        _conv_span("conv-BIG", "afterAgentResponse", 501, "答"),
        _conv_span("conv-BIG", "afterAgentThought", 502, "想"),
        _conv_span("conv-BIG", "afterAgentResponse", 503, "再答"),
    ]), encoding="utf-8")
    (udir / "trace_llmgw_sdd.json").write_text(
        json.dumps({"span_type": "model", "input": json.dumps({"conversation": json.dumps(big_parts[:2])})},
                   ensure_ascii=False), encoding="utf-8")
    ucands2 = pick._build_candidates(pick._collect([str(udir)]), udir)
    check(ucands2[0][2] == "cursor" and ucands2[0][0] == 3, f"winner flips to cursor (msg-score 3 = 1 prompt + 2 responses) (got {ucands2[0][2]}/{ucands2[0][0]})")

    print("[9] pick_complete_trace — llmgw snapshots of ONE session deduped so a DIFFERENT session stays reachable")
    # THE P1 REGRESSION: many llmgw trace files are growing snapshots of the same
    # session (each embeds the conversation-so-far). Without dedup the top-3
    # candidates are all snapshots of session A, and session B (e.g. the real SDD)
    # is ranked #4 and never reaches the prompt's top-N SDD-marker validation.
    ddir = Path(tempfile.mkdtemp(prefix="fornax_llmgw_dedup_"))
    sessA = [{"role": ("user" if i % 2 == 0 else "assistant"),
              "parts": [{"type": "text", "content": f"A{i}"}]} for i in range(6)]
    for n, k in enumerate([2, 4, 6]):  # three growing snapshots of session A
        (ddir / f"trace_a{n}.json").write_text(
            json.dumps({"span_type": "model", "input": json.dumps({"conversation": json.dumps(sessA[:k])})},
                       ensure_ascii=False), encoding="utf-8")
    sessB = [{"role": ("user" if i % 2 == 0 else "assistant"),
              "parts": [{"type": "text", "content": f"B{i}"}]} for i in range(3)]  # different session
    (ddir / "trace_b.json").write_text(
        json.dumps({"span_type": "model", "input": json.dumps({"conversation": json.dumps(sessB)})},
                   ensure_ascii=False), encoding="utf-8")
    dcands = pick._llmgw_candidates(pick._collect([str(ddir)]))
    check(len(dcands) == 2, f"3 snapshots of session A collapse to 1; session B distinct = 2 candidates (got {len(dcands)})")
    check(dcands[0][0] == 6 and dcands[1][0] == 3, f"ranked [A@6, B@3] — session B reachable at rank 2, not buried at rank 4 (got {[c[0] for c in dcands]})")

    print("[10] pick_complete_trace — a malformed line does not drop the whole cursor file")
    mdir = Path(tempfile.mkdtemp(prefix="fornax_malformed_"))
    good1 = json.dumps(_conv_span("conv-M", "beforeSubmitPrompt", 700, "半个下载的会话", user=True), ensure_ascii=False)
    good2 = json.dumps(_conv_span("conv-M", "afterAgentResponse", 701, "仍要保留", user=False), ensure_ascii=False)
    # a truncated/garbage line sits BETWEEN two good spans
    (mdir / "trace_partial.json").write_text(good1 + "\n" + '{"truncated": ' + "\n" + good2 + "\n", encoding="utf-8")
    mspans = list(pick._iter_spans(mdir / "trace_partial.json"))
    check(len(mspans) == 2, f"good spans survive a bad line in between (got {len(mspans)})")
    mranked = pick._group_cursor_conversations(pick._collect([str(mdir)]))
    check(mranked and mranked[0][2] == 2, f"partial cursor conversation still scored (msg-score 2) (got {mranked and mranked[0][2]})")

    print("[11] pick_complete_trace — --json candidate contract the prompt parses")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = pick.main([str(udir), "--json"])
    payload = json.loads(buf.getvalue())
    check(rc == 0, "main --json returns 0")
    check({"winner", "messages", "kind", "candidates"} <= set(payload), f"top-level keys present (got {list(payload)})")
    check(all({"file", "messages", "kind"} <= set(c) for c in payload["candidates"]), "every candidate carries file/messages/kind")
    check(all("conversation_id" in c for c in payload["candidates"] if c["kind"] == "cursor"),
          "cursor candidates carry conversation_id (for the prompt's iteration)")
    check(all("conversation_id" not in c for c in payload["candidates"] if c["kind"] == "llmgw"),
          "llmgw candidates omit conversation_id")

    print("[12] pick_complete_trace — materialized names don't collide on a shared prefix")
    cdir = Path(tempfile.mkdtemp(prefix="fornax_collide_"))
    long_a = "conversation-abcdefghijklmnopqrstuvwxyz-AAAA"
    long_b = "conversation-abcdefghijklmnopqrstuvwxyz-BBBB"  # shares the first >24 chars
    pa = pick._materialize_conversation(long_a, [{"span_type": "beforeSubmitPrompt", "input": json.dumps({"prompt": "a"})}], cdir)
    pb = pick._materialize_conversation(long_b, [{"span_type": "beforeSubmitPrompt", "input": json.dumps({"prompt": "b"})}], cdir)
    check(pa.name != pb.name, f"distinct conversation_ids -> distinct files (got {pa.name} vs {pb.name})")

    print("[13] pick_complete_trace — empty / no-candidate input returns non-zero")
    edir = Path(tempfile.mkdtemp(prefix="fornax_empty_"))
    check(pick.main([str(edir)]) == 1, "empty dir -> return 1")

    print("[14] pick_complete_trace — score-0 tool-only conversation is skipped (no garbage file)")
    # A real conversation (has message spans) + a separate conversation_id that is
    # ONLY tool/tab-read spans (score 0). The score-0 group must NOT become a
    # candidate and must NOT materialize a 0-message _conversation_*.jsonl.
    gdir = Path(tempfile.mkdtemp(prefix="fornax_score0_"))
    (gdir / "trace_real.json").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in [
        _conv_span("conv-REAL", "beforeSubmitPrompt", 900, "真问题", user=True),
        _conv_span("conv-REAL", "afterAgentResponse", 901, "真回答"),
    ]), encoding="utf-8")
    (gdir / "trace_toolonly.json").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in [
        {"span_type": "beforeTabFileRead", "custom_tags": {"cursor_version": "3.7", "conversation_id": "conv-TOOLONLY"}},
        {"span_type": "preToolUse", "custom_tags": {"cursor_version": "3.7", "conversation_id": "conv-TOOLONLY"}},
    ]), encoding="utf-8")
    gcands = pick._build_candidates(pick._collect([str(gdir)]), gdir)
    gcids = {c[3] for c in gcands}
    check(gcids == {"conv-REAL"}, f"only the score>0 conversation is a candidate (got {gcids})")
    materialized_names = [p.name for p in gdir.glob("_conversation_*.jsonl")]
    check(len(materialized_names) == 1 and "convREAL" in materialized_names[0]
          and not any("convTOOLONLY" in n for n in materialized_names),
          f"exactly the score>0 conv-REAL materialized, no score-0 garbage file (got {materialized_names})")

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} check(s) failed)")
        return 1
    print("RESULT: PASS — Fornax cursor + llmgw adapters both work end-to-end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
