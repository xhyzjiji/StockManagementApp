#!/usr/bin/env python3
"""
Conversation miner for kb-update-docs.

Discovers and parses agent conversation logs from Claude Code and Cursor,
filters for high-value SDD sessions, and outputs normalized text for subagent
extraction.

Discovery identifies SDD sessions *positively* by fingerprint -- the session
invoked adk-mobile's spec MCP tools and/or touched the .adk-mobile/specs/<NUM>-<name>
workspace path. This matches the real usage scenario: summarize the session the
user just finished doing SDD in, locally in Claude Code / Cursor.

Sources: local Claude Code / Cursor logs are the DEFAULT (and are auto-discovered).
Fornax is an opt-in REMOTE source -- there is nothing to auto-discover locally, so you
point `export --source fornax` at an already-downloaded trace JSON. Fornax has two trace
shapes and the adapter auto-detects both: the default (llmgw) space embeds the model
conversation as a serialized [{"role", "parts": [...]}] array (codex / claude-cli), while
the cursor space is JSONL hook spans (beforeSubmitPrompt / afterAgentThought). Either way
the adapter normalizes into the same record shape the local pipeline understands, so the
EXACT SAME SDD extraction runs on remote traces as on local ones. (The sibling
find-sdd-trace skill selects the right workspace-id and downloads the trace from an MR.)

Export keeps human text AND the structured signals that carry the KB value of an
SDD trace: AskUserQuestion interactions (question + options + the user's actual
selection) and the generated spec / requirements / design / tasks / explore
artifacts. Pure-noise tool calls (Read / Grep / Bash ...) are dropped.

Usage:
    python3 conversation_miner.py discover --project-path <path> [--min-sessions 3] [--max-sessions 10] [--within-hours 24]
    python3 conversation_miner.py export --jsonl-path <session.jsonl> --source <claude-code|cursor>
    # Fornax (remote): point at an already-downloaded trace JSON
    python3 conversation_miner.py export --jsonl-path <trace.json> --source fornax
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Unified session model
# ---------------------------------------------------------------------------

@dataclass
class SessionMeta:
    session_id: str
    source: str  # "claude-code" | "cursor"
    project_path: str
    jsonl_path: str
    timestamp: float  # epoch seconds of first user message
    user_turn_count: int
    assistant_turn_count: int
    total_user_chars: int
    has_tool_heavy: bool  # assistant mostly tool_use, little text
    is_sdd: bool = False  # invoked spec MCP tools / touched .adk-mobile/specs
    spec_name: Optional[str] = None  # e.g. "028-reward-arch-migration-jsb"


@dataclass
class ConversationTurn:
    role: str  # "user" | "assistant"
    content: str
    timestamp: Optional[str] = None
    files_mentioned: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# Default to the real local stores; overridable via env so the local path can be
# exercised against a fixture (see tests/test_local_mining.py) without touching
# the user's real ~/.claude / ~/.cursor.
CLAUDE_CODE_BASE = Path(os.environ.get("CONV_MINER_CLAUDE_BASE") or (Path.home() / ".claude" / "projects"))
CURSOR_BASE = Path(os.environ.get("CONV_MINER_CURSOR_BASE") or (Path.home() / ".cursor" / "projects"))


def _find_matching_project_dirs(base: Path, project_path: str) -> list[Path]:
    """Find project directories that match the given project path.

    Claude Code and Cursor encode paths as slugs in directory names, but the
    exact encoding varies (underscores vs hyphens, leading dashes, etc.).
    Instead of guessing the slug, we derive a canonical form and do a
    normalized comparison against all directories.
    """
    if not base.exists():
        return []

    p = Path(project_path).resolve()
    # Normalize: lowercase, replace /, _, space with -
    canonical = str(p).lower().replace("/", "-").replace("_", "-").replace(" ", "-").strip("-")

    results = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        dir_canonical = d.name.lower().replace("_", "-").strip("-")
        if dir_canonical == canonical:
            results.append(d)
    return results


def _find_claude_code_sessions(project_path: str) -> list[Path]:
    """Find all .jsonl session files for a project in Claude Code."""
    results = []
    for proj_dir in _find_matching_project_dirs(CLAUDE_CODE_BASE, project_path):
        for f in proj_dir.glob("*.jsonl"):
            results.append(f)
    return results


def _find_cursor_sessions(project_path: str) -> list[Path]:
    """Find all .jsonl session files for a project in Cursor."""
    results = []
    for proj_dir in _find_matching_project_dirs(CURSOR_BASE, project_path):
        transcripts_dir = proj_dir / "agent-transcripts"
        if transcripts_dir.is_dir():
            for session_dir in transcripts_dir.iterdir():
                if session_dir.is_dir():
                    for f in session_dir.glob("*.jsonl"):
                        results.append(f)
    return results


# ---------------------------------------------------------------------------
# Adapters: parse JSONL into SessionMeta
# ---------------------------------------------------------------------------

FILE_REF_RE = re.compile(r'[\w./\\-]+\.(?:swift|m|mm|h|kt|java|py|ts|tsx|js|jsx)')


def _extract_files(text: str) -> list[str]:
    return list(set(FILE_REF_RE.findall(text)))


# SDD fingerprints ----------------------------------------------------------
# Identify a real SDD session *positively*: it calls adk-mobile's spec MCP tools
# and/or touches the .adk-mobile/specs/<NUM>-<name> workspace path. Turn-count and
# "tool-heavy" heuristics misfire on SDD -- such sessions have FEW user turns
# (mostly phase approvals + AskUserQuestion answers) and are tool-heavy by nature,
# so the legacy filters tended to exclude exactly the sessions we want.
SPEC_PATH_RE = re.compile(r"\.adk-mobile/specs/(\d+-[\w.\-]+)")
SDD_ARTIFACT_RE = re.compile(
    r"/specs/\d+-[\w.\-]+/(?:spec|requirements|design|tasks|explore)\.md"
)
ASK_USER_QUESTION = "AskUserQuestion"
_ARTIFACT_WRITE_TOOLS = {
    "write", "create_file", "edit_file", "str_replace_editor",
    "str_replace_based_edit_tool", "apply_patch", "multiedit",
}


def _is_sdd_tool_name(name) -> bool:
    """True if a tool name looks like an adk-mobile SDD / spec MCP tool."""
    n = (name or "").lower()
    return (
        "prd-to-spec" in n or "prd_to_spec" in n
        or "sdd-guide" in n or "sdd_guide" in n or "sddguide" in n
        or ("adk" in n and "spec" in n)
    )


def _input_paths(tool_input) -> str:
    """Concatenate the file-path-ish fields of a tool input for matching."""
    if not isinstance(tool_input, dict):
        return ""
    return " ".join(
        str(tool_input.get(k, ""))
        for k in ("file_path", "path", "target_file", "filePath", "notebook_path")
    )


# Matches a JSON `"name": "<spec-mcp-tool>"` field on a raw transcript line.
_SDD_TOOL_LINE_RE = re.compile(
    r'"name"\s*:\s*"[^"]*'
    r'(?:prd[-_]to[-_]spec|sdd[-_]guide|adk[-_]?mobile[^"]*spec|'
    r'spec[-_](?:guide|status|continue|clarify|save))[^"]*"',
    re.I,
)


def _scan_line_sdd(line: str, is_sdd: bool, spec_name):
    """Cheap per-line SDD fingerprint scan (path + spec MCP tool name)."""
    if not is_sdd and (SPEC_PATH_RE.search(line) or _SDD_TOOL_LINE_RE.search(line)):
        is_sdd = True
    if spec_name is None:
        m = SPEC_PATH_RE.search(line)
        if m:
            spec_name = m.group(1)
    return is_sdd, spec_name


def _parse_claude_code_meta(jsonl_path: Path, project_path: str) -> Optional[SessionMeta]:
    """Parse a Claude Code .jsonl and return session metadata."""
    user_turns = 0
    assistant_text_chars = 0
    assistant_tool_blocks = 0
    assistant_text_blocks = 0
    total_user_chars = 0
    first_ts = None
    is_sdd = False
    spec_name = None

    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                is_sdd, spec_name = _scan_line_sdd(line, is_sdd, spec_name)

                msg_type = obj.get("type", "")
                msg = obj.get("message", {})
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role", "")
                content = msg.get("content", "")

                if msg_type == "user" and role == "user":
                    user_turns += 1
                    text = content if isinstance(content, str) else ""
                    if isinstance(content, list):
                        text = " ".join(
                            c.get("text", "") for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        )
                    total_user_chars += len(text)
                    ts_str = obj.get("timestamp")
                    if ts_str and first_ts is None:
                        try:
                            first_ts = datetime.fromisoformat(
                                ts_str.replace("Z", "+00:00")
                            ).timestamp()
                        except (ValueError, TypeError):
                            pass

                elif msg_type == "assistant" and role == "assistant":
                    if isinstance(content, str):
                        assistant_text_chars += len(content)
                        assistant_text_blocks += 1 if content.strip() else 0
                    elif isinstance(content, list):
                        for c in content:
                            if not isinstance(c, dict):
                                continue
                            if c.get("type") == "text":
                                assistant_text_chars += len(c.get("text", ""))
                                assistant_text_blocks += 1
                            elif c.get("type") == "tool_use":
                                assistant_tool_blocks += 1
    except OSError:
        return None

    if user_turns == 0:
        return None

    total_assistant = assistant_text_blocks + assistant_tool_blocks
    tool_heavy = (
        total_assistant > 0
        and assistant_tool_blocks / total_assistant > 0.8
        and assistant_text_chars < 500
    )

    return SessionMeta(
        session_id=jsonl_path.stem,
        source="claude-code",
        project_path=project_path,
        jsonl_path=str(jsonl_path),
        timestamp=first_ts or jsonl_path.stat().st_mtime,
        user_turn_count=user_turns,
        assistant_turn_count=assistant_text_blocks + assistant_tool_blocks,
        total_user_chars=total_user_chars,
        has_tool_heavy=tool_heavy,
        is_sdd=is_sdd,
        spec_name=spec_name,
    )


def _parse_cursor_meta(jsonl_path: Path, project_path: str) -> Optional[SessionMeta]:
    """Parse a Cursor agent-transcript .jsonl and return session metadata."""
    user_turns = 0
    assistant_text_chars = 0
    assistant_tool_blocks = 0
    assistant_text_blocks = 0
    total_user_chars = 0
    first_ts = None
    is_sdd = False
    spec_name = None

    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                is_sdd, spec_name = _scan_line_sdd(line, is_sdd, spec_name)

                role = obj.get("role", "")
                msg = obj.get("message", {})
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content", [])

                if role == "user":
                    user_turns += 1
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                total_user_chars += len(c.get("text", ""))
                    elif isinstance(content, str):
                        total_user_chars += len(content)
                    if first_ts is None:
                        ts_match = re.search(
                            r"<timestamp>(.*?)</timestamp>",
                            json.dumps(content, ensure_ascii=False),
                        )
                        if ts_match:
                            try:
                                first_ts = datetime.strptime(
                                    ts_match.group(1).strip(),
                                    "%A, %B %d, %Y, %I:%M %p (UTC%z)",
                                ).timestamp()
                            except (ValueError, TypeError):
                                pass

                elif role == "assistant":
                    if isinstance(content, list):
                        for c in content:
                            if not isinstance(c, dict):
                                continue
                            if c.get("type") == "text":
                                assistant_text_chars += len(c.get("text", ""))
                                assistant_text_blocks += 1
                            elif c.get("type") == "tool_use":
                                assistant_tool_blocks += 1
                    elif isinstance(content, str):
                        assistant_text_chars += len(content)
                        assistant_text_blocks += 1
    except OSError:
        return None

    if user_turns == 0:
        return None

    total_assistant = assistant_text_blocks + assistant_tool_blocks
    tool_heavy = (
        total_assistant > 0
        and assistant_tool_blocks / total_assistant > 0.8
        and assistant_text_chars < 500
    )

    return SessionMeta(
        session_id=jsonl_path.stem,
        source="cursor",
        project_path=project_path,
        jsonl_path=str(jsonl_path),
        timestamp=first_ts or jsonl_path.stat().st_mtime,
        user_turn_count=user_turns,
        assistant_turn_count=assistant_text_blocks + assistant_tool_blocks,
        total_user_chars=total_user_chars,
        has_tool_heavy=tool_heavy,
        is_sdd=is_sdd,
        spec_name=spec_name,
    )


# ---------------------------------------------------------------------------
# Fornax adapter (opt-in remote source)
# ---------------------------------------------------------------------------
# Local Claude Code / Cursor logs are the default, auto-discovered source. Fornax
# is a remote trace store: you fetch a specific trace and point the miner at it --
# there is nothing to "discover" locally. A Fornax trace embeds the full model
# conversation as a serialized JSON string of [{"role", "parts": [...]}] messages
# (OpenAI "parts" shape) nested somewhere in the span tree. We locate that array
# and normalize it into the same claude-code-shaped records the local pipeline
# already understands, so the identical SDD extraction (AskUserQuestion + the
# spec / design / requirements / tasks / explore artifacts) runs on remote traces.


def _fornax_part_text(part: dict) -> str:
    c = part.get("content")
    return c if isinstance(c, str) else part.get("text", "")


def _find_fornax_messages(trace_obj) -> Optional[list]:
    """Find the conversation message array inside a Fornax trace.

    The message list is serialized as a JSON string nested in the span tree. We
    walk the whole structure and pick the embedded {"role","parts"} array with the
    MOST MESSAGES -- the most complete model call carries the fullest conversation
    history (not necessarily the longest string, so we compare message count).
    """
    best = {"arr": None, "count": -1}

    def walk(o):
        if isinstance(o, str):
            t = o.lstrip()
            if t[:1] == "[" and '"parts"' in o:
                try:
                    arr = json.loads(o)
                except (json.JSONDecodeError, ValueError):
                    arr = None
                if (
                    isinstance(arr, list)
                    and len(arr) > best["count"]
                    and any(isinstance(m, dict) and "parts" in m and "role" in m for m in arr)
                ):
                    best["arr"] = arr
                    best["count"] = len(arr)
            if t[:1] in "[{":
                try:
                    walk(json.loads(o))
                except (json.JSONDecodeError, ValueError):
                    pass
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(trace_obj)
    return best["arr"]


def _fornax_messages_to_records(msgs: list) -> list[dict]:
    """Normalize Fornax [{role, parts}] messages into claude-code-shaped records
    ({"type", "message": {"role", "content": [...]}}).

    text -> text block; tool_call -> tool_use; tool_call_response -> a separate
    user message carrying a tool_result. reasoning / other part types are dropped
    as noise (consistent with how the export stage treats them).
    """
    out: list[dict] = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant", "tool", "system"):
            continue
        cur: list[dict] = []
        for p in m.get("parts") or []:
            if not isinstance(p, dict):
                continue
            typ = p.get("type")
            if typ == "text":
                # Only user/assistant text is conversation content. A `system`
                # message is the harness/system prompt and a `tool` message is
                # tool output -- neither is user knowledge, so their text is
                # dropped and never mined into docs as if the user said it.
                if role in ("user", "assistant"):
                    t = _fornax_part_text(p)
                    if t:
                        cur.append({"type": "text", "text": t})
            elif typ == "tool_call":
                cur.append({
                    "type": "tool_use",
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "input": p.get("arguments", {}),
                })
            elif typ in ("tool_call_response", "tool_response"):
                if cur:
                    out.append({"type": "assistant",
                                "message": {"role": "assistant", "content": cur}})
                    cur = []
                out.append({"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": p.get("id"),
                     "content": p.get("response", "")},
                ]}})
        if cur:
            r = "assistant" if role == "assistant" else "user"
            out.append({"type": r, "message": {"role": r, "content": cur}})
    return out


# --- Cursor-space fornax traces --------------------------------------------
# Cursor uploads its trace as JSONL: one hook span per line (beforeSubmitPrompt,
# afterAgentThought, preToolUse, afterShellExecution, ...), NOT the single
# model-call span carrying an embedded OpenAI-parts array that codex / claude-cli
# produce in the default (llmgw) space. The conversation lives in the hook spans:
#   beforeSubmitPrompt.input.prompt          -> the user's message
#   afterAgentThought/afterAgentResponse.output.text -> the assistant's message
# Everything else (tool-use hooks, shell execution) is noise, matching how the
# local pipeline drops non-KB tool calls. find-sdd-trace selects the right
# workspace-id (cursor vs llmgw) before the trace is downloaded.

_CURSOR_USER_SPANS = {"beforeSubmitPrompt"}
_CURSOR_ASSISTANT_SPANS = {"afterAgentThought", "afterAgentResponse"}
_CURSOR_CONV_SPANS = _CURSOR_USER_SPANS | _CURSOR_ASSISTANT_SPANS


def _parse_jsonl(raw: str) -> list:
    """Parse a JSONL string into a list of objects. Returns [] if any non-empty
    line is not valid JSON (i.e. the payload is not clean line-delimited JSON)."""
    objs = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objs.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            return []
    return objs


def _looks_like_cursor_spans(objs: list) -> bool:
    """True if the line objects look like Cursor hook spans (a cursor_version tag
    or a known conversation hook span_type)."""
    for o in objs:
        if not isinstance(o, dict):
            continue
        ct = o.get("custom_tags")
        if isinstance(ct, dict) and ct.get("cursor_version"):
            return True
        if (o.get("span_type") or o.get("span_name") or "") in _CURSOR_CONV_SPANS:
            return True
    return False


def _cursor_span_field(span: dict, key: str) -> dict:
    """Return span[key] as a dict; the cursor payload nests its JSON as a string."""
    v = span.get(key)
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except (json.JSONDecodeError, ValueError):
            return {}
    return v if isinstance(v, dict) else {}


def _cursor_span_order(span: dict, idx: int):
    """Best-effort chronological sort key: numeric started_at, else the hook's
    trigger_timestamp, else fall back to file order."""
    try:
        return (0, float(span.get("started_at")), idx)
    except (TypeError, ValueError):
        pass
    ct = span.get("custom_tags")
    co = ct.get("call_options") if isinstance(ct, dict) else None
    if isinstance(co, str):
        try:
            co = json.loads(co)
        except (json.JSONDecodeError, ValueError):
            co = None
    if isinstance(co, dict):
        try:
            return (0, float(co.get("trigger_timestamp")), idx)
        except (TypeError, ValueError):
            pass
    return (1, idx, idx)


def _cursor_spans_to_records(spans: list) -> list[dict]:
    """Normalize Cursor hook spans into claude-code-shaped records so the SAME
    extraction runs on them as on local / codex / claude traces."""
    events = []
    for idx, s in enumerate(spans):
        if not isinstance(s, dict):
            continue
        st = s.get("span_type") or s.get("span_name") or ""
        if st in _CURSOR_USER_SPANS:
            prompt = _cursor_span_field(s, "input").get("prompt")
            if isinstance(prompt, str) and prompt.strip():
                events.append((_cursor_span_order(s, idx), "user", prompt.strip()))
        elif st in _CURSOR_ASSISTANT_SPANS:
            text = _cursor_span_field(s, "output").get("text")
            if isinstance(text, str) and text.strip():
                events.append((_cursor_span_order(s, idx), "assistant", text.strip()))
    events.sort(key=lambda e: e[0])
    return [
        {"type": role, "message": {"role": role, "content": [{"type": "text", "text": text}]}}
        for _, role, text in events
    ]


def load_fornax_records(trace_path: str) -> list[dict]:
    """Load a Fornax trace file and return claude-code-shaped records.

    Handles both Fornax trace shapes transparently (the caller passes the same
    `--source fornax` for either):
    - cursor space: JSONL, one hook span per line; the conversation is in the
      beforeSubmitPrompt / afterAgentThought(Response) spans.
    - default (llmgw) space: a single model-call span carrying an embedded
      OpenAI-parts message array (codex / claude-cli).

    Returns [] if the file is missing/unreadable or no conversation is found,
    so callers degrade gracefully instead of raising.
    """
    path = Path(trace_path)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError:
        return []
    # Cursor traces are line-delimited hook spans; try that shape first.
    line_objs = _parse_jsonl(raw)
    if line_objs and _looks_like_cursor_spans(line_objs):
        recs = _cursor_spans_to_records(line_objs)
        if recs:
            return recs
    # Otherwise treat it as the embedded OpenAI-parts shape: parse the whole file
    # as one object when possible, else search each JSONL line for a parts array.
    try:
        trace = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        trace = line_objs
    msgs = _find_fornax_messages(trace)
    if not msgs:
        return []
    return _fornax_messages_to_records(msgs)


# ---------------------------------------------------------------------------
# Discovery: progressive time window
# ---------------------------------------------------------------------------

TIME_WINDOWS = [
    timedelta(hours=24),
    timedelta(days=3),
    timedelta(days=7),
]

MIN_USER_TURNS = 10


def discover_sessions(
    project_path: str,
    min_sessions: int = 3,
    max_sessions: int = 10,
    min_user_turns: int = MIN_USER_TURNS,
    within_hours: Optional[float] = None,
) -> list[SessionMeta]:
    """
    Discover SDD conversation sessions for KB extraction.

    Primary signal is a positive SDD fingerprint (the session invoked adk-mobile
    spec MCP tools and/or touched .adk-mobile/specs/<NUM>-<name>). This matches the
    real usage: summarize the session the user *just finished* doing SDD in, locally
    in Claude Code / Cursor. SDD sessions are returned most-recent-first; the time
    window is only a soft recency ordering, not a hard gate.

    When no SDD-fingerprinted session is found, falls back to the legacy depth
    heuristic (>= min_user_turns and not tool-heavy, across a progressive time
    window) so generic conversation mining still degrades gracefully.
    """
    cc_files = _find_claude_code_sessions(project_path)
    cursor_files = _find_cursor_sessions(project_path)

    all_metas: list[SessionMeta] = []
    for f in cc_files:
        meta = _parse_claude_code_meta(f, project_path)
        if meta:
            all_metas.append(meta)
    for f in cursor_files:
        meta = _parse_cursor_meta(f, project_path)
        if meta:
            all_metas.append(meta)

    all_metas.sort(key=lambda m: m.timestamp, reverse=True)
    now = datetime.now(timezone.utc).timestamp()

    # Primary: positively-identified SDD sessions, most recent first.
    sdd = [m for m in all_metas if m.is_sdd]
    if within_hours:
        cutoff = now - within_hours * 3600.0
        recent = [m for m in sdd if m.timestamp >= cutoff]
        if recent:
            sdd = recent
    if sdd:
        return sdd[:max_sessions]

    # Fallback: legacy depth heuristic across progressive time windows.
    for window in TIME_WINDOWS:
        cutoff = now - window.total_seconds()
        candidates = [
            m
            for m in all_metas
            if m.timestamp >= cutoff
            and m.user_turn_count >= min_user_turns
            and not m.has_tool_heavy
        ]
        if len(candidates) >= min_sessions:
            return candidates[:max_sessions]

    fallback = [
        m for m in all_metas
        if m.user_turn_count >= min_user_turns and not m.has_tool_heavy
    ]
    return fallback[:max_sessions]


# ---------------------------------------------------------------------------
# Export: render a session as readable text for subagent consumption
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    text = re.sub(r"<timestamp>.*?</timestamp>\s*", "", text)
    text = re.sub(r"<user_query>\s*", "", text)
    text = re.sub(r"\s*</user_query>", "", text)
    return text.strip()


# Secret redaction ----------------------------------------------------------
# Mined conversation / trace text can carry credentials (API keys, tokens,
# cookies). They must not flow out of this tool into a KB doc or a shared
# subagent prompt. We mask the high-confidence credential SHAPES, preserving the
# surrounding label so the redaction is auditable (e.g. `token=[REDACTED]`).
# We deliberately do NOT blanket-mask long hex / base64 strings: that would also
# destroy commit SHAs, trace ids, and legitimate artifact content. Toggle off
# with `--no-redact` for local debugging.
_REDACTORS = [
    # JWT (header.payload.signature)
    (re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
    # OpenAI-style secret key
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "[REDACTED_KEY]"),
    # AWS access key id
    (re.compile(r"\bAKIA[0-9A-Z]{12,}\b"), "[REDACTED_AWS_KEY]"),
    # Bearer token (keep the "Bearer " label)
    (re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._\-]{12,}"), r"\1[REDACTED]"),
    # cookie / set-cookie value (keep the label)
    (re.compile(r"(?i)(\b(?:set-)?cookie\s*[:=]\s*)[^\s;,]{8,}"), r"\1[REDACTED]"),
    # key / secret / token / password assignment (keep the label, mask the value)
    (re.compile(
        r"(?i)(\b(?:api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key|"
        r"private[_-]?key|app[_-]?secret)\b\s*[:=]\s*)['\"]?[A-Za-z0-9._\-/+=]{8,}['\"]?"
    ), r"\1[REDACTED]"),
]


def redact_secrets(text: str) -> str:
    """Mask high-confidence credential patterns in mined text. Conservative by
    design (targeted shapes only) so it never clobbers SHAs / ids / legit content."""
    if not text:
        return text
    for pat, repl in _REDACTORS:
        text = pat.sub(repl, text)
    return text


def _result_to_text(content) -> str:
    """Flatten a tool_result content (str or list of blocks) into text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(p for p in parts if p).strip()
    return ""


def _render_askuserquestion(tool_input) -> str:
    """Render an AskUserQuestion call as question + options (the user's choice
    arrives separately in the matching tool_result)."""
    if not isinstance(tool_input, dict):
        return ""
    lines = ["[AskUserQuestion]"]
    for q in tool_input.get("questions") or []:
        if not isinstance(q, dict):
            continue
        lines.append(f"  Q: {q.get('question', '')}")
        labels = [
            o.get("label", "")
            for o in (q.get("options") or [])
            if isinstance(o, dict)
        ]
        if labels:
            lines.append(f"     options: {' | '.join(l for l in labels if l)}")
    return "\n".join(lines)


def _is_sdd_artifact_write(tool_name, tool_input) -> bool:
    if (tool_name or "").lower() not in _ARTIFACT_WRITE_TOOLS:
        return False
    return bool(SDD_ARTIFACT_RE.search(_input_paths(tool_input)))


def _render_sdd_artifact(tool_input, cap: int) -> str:
    path = _input_paths(tool_input).strip()
    name = path.split("/")[-1] if path else "artifact"
    body = ""
    if isinstance(tool_input, dict):
        body = (
            tool_input.get("content")
            or tool_input.get("file_text")
            or tool_input.get("new_str")
            or ""
        )
    # content fields are normally strings, but some tools nest dict/list payloads;
    # coerce so len()/slicing below never raises on a non-string body.
    if not isinstance(body, str):
        body = json.dumps(body, ensure_ascii=False) if body else ""
    if len(body) > cap:
        body = body[:cap] + f"\n...[truncated, {len(body)} chars total]"
    return f"[SDD artifact: {name}]\n{body}".strip()


def _render_content(content, role, tool_names, cap):
    """Yield (role, text) tuples for the KB-relevant parts of a message.

    Keeps text, AskUserQuestion (question/options + user selection) and generated
    SDD artifacts; drops noise tool calls (Read / Grep / Bash / Glob ...).
    """
    out = []
    if isinstance(content, str):
        t = _clean_text(content)
        if t:
            out.append((role, t))
        return out
    if not isinstance(content, list):
        return out
    for c in content:
        if not isinstance(c, dict):
            continue
        typ = c.get("type")
        if typ == "text":
            t = _clean_text(c.get("text", ""))
            if t:
                out.append((role, t))
        elif typ == "tool_use":
            cid = c.get("id") or c.get("tool_use_id")
            name = c.get("name", "")
            if cid:
                tool_names[cid] = name
            tin = c.get("input", {})
            if name == ASK_USER_QUESTION:
                rendered = _render_askuserquestion(tin)
                if rendered:
                    out.append(("assistant", rendered))
            elif _is_sdd_artifact_write(name, tin):
                out.append(("assistant", _render_sdd_artifact(tin, cap)))
            # other tool calls: dropped as noise
        elif typ == "tool_result":
            rid = c.get("tool_use_id") or c.get("id")
            if tool_names.get(rid) == ASK_USER_QUESTION:
                ans = _result_to_text(c.get("content"))
                if ans:
                    out.append(("user", f"[User selected] {ans}"))
            # other tool results: dropped as noise
    return out


def _role_and_content(obj, source):
    # Fornax records are normalized into the claude-code shape, so they share the
    # same (type / message) extraction path.
    if source in ("claude-code", "fornax"):
        if obj.get("type") not in ("user", "assistant"):
            return "", None
        msg = obj.get("message", {})
        if not isinstance(msg, dict):
            return "", None
        return msg.get("role", ""), msg.get("content", "")
    # cursor
    msg = obj.get("message", {})
    if not isinstance(msg, dict):
        return "", None
    return obj.get("role", ""), msg.get("content", [])


def _iter_records(jsonl_path: str, source: str):
    """Yield raw message records for a session, regardless of source.

    claude-code / cursor: stream the .jsonl file line by line.
    fornax: load + normalize the remote trace JSON into claude-code-shaped records.
    """
    if source == "fornax":
        yield from load_fornax_records(jsonl_path)
        return
    path = Path(jsonl_path)
    if not path.exists():
        return
    try:
        f = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def export_session(
    jsonl_path: str,
    source: str,
    max_turns: int = 200,
    max_block_chars: int = 6000,
    redact: bool = True,
) -> list[dict]:
    """
    Export a session as a list of {role, content} dicts for subagent extraction.

    Keeps human text AND the structured signals that carry the real KB value of an
    SDD trace: AskUserQuestion interactions (question + options paired with the
    user's actual selection) and the generated SDD artifacts (spec / requirements /
    design / tasks / explore .md). Pure-noise tool calls are dropped.

    Works uniformly across local (claude-code / cursor) and remote (fornax) sources
    -- the records are normalized to a common shape before extraction.

    When `redact` is True (default), credential-shaped substrings (keys / tokens /
    cookies) are masked before the text leaves this function, so secrets in the
    logs never reach a KB doc or a shared subagent prompt.
    """
    turns: list[dict] = []
    tool_names: dict = {}

    for obj in _iter_records(jsonl_path, source):
        role, content = _role_and_content(obj, source)
        if role not in ("user", "assistant"):
            continue
        for r, text in _render_content(content, role, tool_names, max_block_chars):
            if text and text.strip():
                if redact:
                    text = redact_secrets(text)
                turns.append({"role": r, "content": text.strip()})
                if len(turns) >= max_turns:
                    return turns

    return turns


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_discover(args: argparse.Namespace) -> int:
    sessions = discover_sessions(
        project_path=args.project_path,
        min_sessions=args.min_sessions,
        max_sessions=args.max_sessions,
        min_user_turns=args.min_user_turns,
        within_hours=args.within_hours,
    )

    if args.format == "json":
        print(json.dumps([asdict(s) for s in sessions], ensure_ascii=False, indent=2))
    else:
        if not sessions:
            print("No qualifying sessions found.")
            return 0
        print(f"Found {len(sessions)} session(s):\n")
        for s in sessions:
            ts = datetime.fromtimestamp(s.timestamp).strftime("%Y-%m-%d %H:%M")
            tag = f"  SDD={s.spec_name or 'yes'}" if s.is_sdd else ""
            print(
                f"  [{s.source}] {s.session_id[:12]}...  "
                f"{ts}  "
                f"user_turns={s.user_turn_count}  "
                f"user_chars={s.total_user_chars}"
                f"{tag}"
            )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    turns = export_session(
        args.jsonl_path,
        args.source,
        max_turns=args.max_turns,
        max_block_chars=args.max_block_chars,
        redact=not args.no_redact,
    )

    if args.format == "json":
        print(json.dumps(turns, ensure_ascii=False, indent=2))
    else:
        for t in turns:
            prefix = "USER" if t["role"] == "user" else "ASST"
            content = t["content"]
            if len(content) > 500:
                content = content[:500] + "..."
            print(f"[{prefix}] {content}\n")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="conversation_miner.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_discover = sub.add_parser("discover")
    p_discover.add_argument("--project-path", required=True)
    p_discover.add_argument("--min-sessions", type=int, default=3)
    p_discover.add_argument("--max-sessions", type=int, default=10)
    p_discover.add_argument("--min-user-turns", type=int, default=10)
    p_discover.add_argument(
        "--within-hours", type=float, default=None,
        help="soft recency window for SDD sessions (e.g. 24); not a hard gate",
    )
    p_discover.add_argument("--format", choices=["text", "json"], default="text")
    p_discover.set_defaults(func=cmd_discover)

    p_export = sub.add_parser("export")
    p_export.add_argument(
        "--jsonl-path", required=True,
        help="local session .jsonl (claude-code/cursor) OR a downloaded Fornax trace .json (source=fornax)",
    )
    p_export.add_argument(
        "--source", required=True, choices=["claude-code", "cursor", "fornax"],
    )
    p_export.add_argument("--max-turns", type=int, default=200)
    p_export.add_argument(
        "--max-block-chars", type=int, default=6000,
        help="per-artifact content cap before truncation",
    )
    p_export.add_argument(
        "--no-redact", action="store_true",
        help="disable credential/secret masking (default: redact on). Use only for local debugging.",
    )
    p_export.add_argument("--format", choices=["text", "json"], default="text")
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
