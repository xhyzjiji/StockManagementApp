#!/usr/bin/env python3
"""Collect accurate token usage from Claude Code local JSONL session logs.

Parses Claude Code JSONL files to extract per-message token consumption.
Designed as a fallback when the subagent <usage> block is missing or unstable.

For Cursor environments, use cursor-agent CLI (--print --output-format json)
which returns usage directly — no local log parsing needed.

Usage:
    python3 collect_local_usage.py \
        --start-time 2026-05-25T10:00:00Z \
        --end-time   2026-05-25T10:05:00Z \
        [--claude-config-dir ~/.claude] \
        [--claude-jsonl ~/.claude/projects/.../subagents/agent-xxx.jsonl] \
        [--claude-session-id <session-id>] \
        [--claude-agent-id <agent-id>] \
        [--output /path/to/usage.json]

Output JSON:
    {
        "source": "claude-code",
        "entries": [...],
        "summary": {
            "input_tokens": 12000,
            "output_tokens": 3400,
            "cached_input_tokens": 8000,
            "cache_creation_input_tokens": 200,
            "reasoning_output_tokens": 500,
            "total_tokens": 15900,
            "estimated_cost_usd": 0.0842,
            "entry_count": 5
        },
        "time_window": {"start": "...", "end": "..."},
        "collection_method": "claude_code_jsonl"
    }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _filter_set(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    result: set[str] = set()
    for value in values:
        for item in str(value).split(","):
            item = item.strip()
            if item:
                result.add(item)
    return result


def _claude_path_session_ids(path: Path) -> set[str]:
    ids = {path.stem}
    if path.parent.name == "subagents":
        ids.add(path.parent.parent.name)
    return ids


def _claude_path_agent_ids(path: Path) -> set[str]:
    ids = {path.stem}
    if path.stem.startswith("agent-"):
        ids.add(path.stem.removeprefix("agent-"))
    return ids


def parse_ts(s: str) -> datetime | None:
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def json_int(m: dict, key: str) -> int:
    v = m.get(key, 0)
    if isinstance(v, (int, float)):
        return int(v)
    return 0


# ---------------------------------------------------------------------------
# Claude Code: parse ~/.claude/projects/**/*.jsonl
# ---------------------------------------------------------------------------

def find_jsonl_files(directory: Path) -> list[Path]:
    results = []
    if not directory.is_dir():
        return results
    for p in directory.rglob("*.jsonl"):
        if p.is_file():
            results.append(p)
    return results


def parse_claude_code_jsonl(
    path: Path,
    start: datetime,
    end: datetime,
    *,
    session_ids: set[str] | None = None,
    agent_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    session_ids = session_ids or set()
    agent_ids = agent_ids or set()

    path_session_ids = _claude_path_session_ids(path)
    path_agent_ids = _claude_path_agent_ids(path)
    if session_ids and not (path_session_ids & session_ids):
        return entries
    if agent_ids and not (path_agent_ids & agent_ids):
        return entries

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_str = obj.get("timestamp", "")
                if not ts_str:
                    continue
                ts = parse_ts(ts_str)
                if ts is None:
                    continue
                if ts < start or ts > end:
                    continue

                if obj.get("type") != "assistant":
                    continue

                session_id = str(obj.get("sessionId") or "")
                agent_id = str(obj.get("agentId") or "")
                if session_ids and session_id not in session_ids and not (path_session_ids & session_ids):
                    continue
                if agent_ids and agent_id not in agent_ids and not (path_agent_ids & agent_ids):
                    continue

                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue

                api_msg_id = msg.get("id", "")
                local_uuid = obj.get("uuid", "")
                stable_id = api_msg_id or local_uuid

                if stable_id:
                    dedup_key = f"claude-code:{stable_id}"
                else:
                    dedup_key = _content_dedup_key(
                        "claude-code", ts_str,
                        msg.get("model", "unknown"),
                        usage,
                    )
                if dedup_key in seen_ids:
                    continue
                seen_ids.add(dedup_key)

                model = msg.get("model", "unknown")
                input_tokens = json_int(usage, "input_tokens")
                output_tokens = json_int(usage, "output_tokens")
                cached_read = json_int(usage, "cache_read_input_tokens")
                cached_creation = json_int(usage, "cache_creation_input_tokens")
                reasoning = json_int(usage, "reasoning_output_tokens")

                entries.append({
                    "source": "claude-code",
                    "model": model,
                    "timestamp": ts_str,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cached_input_tokens": cached_read,
                    "cache_creation_input_tokens": cached_creation,
                    "reasoning_output_tokens": reasoning,
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "source_file": str(path),
                    "dedup_key": dedup_key,
                })
    except OSError:
        pass

    return entries


def collect_claude_code(
    start: datetime,
    end: datetime,
    config_dirs: list[Path] | None = None,
    *,
    jsonl_paths: list[Path] | None = None,
    session_ids: set[str] | None = None,
    agent_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if jsonl_paths:
        candidate_files = [p.expanduser() for p in jsonl_paths]
    elif config_dirs is None:
        home = Path.home()
        config_dirs = [home / ".claude"]
        candidate_files = []
    else:
        config_dirs = [p.expanduser() for p in config_dirs]
        candidate_files = []

    all_entries: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    if not candidate_files:
        for config_dir in config_dirs:
            projects_dir = config_dir / "projects"
            if not projects_dir.is_dir():
                continue
            candidate_files.extend(find_jsonl_files(projects_dir))

    for jsonl_path in candidate_files:
        if not jsonl_path.is_file():
            continue
        entries = parse_claude_code_jsonl(
            jsonl_path,
            start,
            end,
            session_ids=session_ids,
            agent_ids=agent_ids,
        )
        for e in entries:
            dk = e.get("dedup_key", "")
            if dk and dk in seen_keys:
                continue
            if dk:
                seen_keys.add(dk)
            all_entries.append(e)

    return all_entries


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _content_dedup_key(source: str, ts_str: str, model: str, usage: dict) -> str:
    h = hashlib.sha256()
    parts = [
        source, ts_str, model,
        str(json_int(usage, "input_tokens")),
        str(json_int(usage, "output_tokens")),
        str(json_int(usage, "cached_input_tokens") or json_int(usage, "cache_read_input_tokens")),
        str(json_int(usage, "reasoning_output_tokens")),
    ]
    h.update("|".join(parts).encode())
    return f"{source}:{h.hexdigest()[:32]}"


MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4": {"input": 15.0, "cached_read": 1.5, "cached_write": 18.75, "output": 75.0},
    "claude-sonnet-4": {"input": 3.0, "cached_read": 0.3, "cached_write": 3.75, "output": 15.0},
    "claude-haiku-4": {"input": 0.80, "cached_read": 0.08, "cached_write": 1.0, "output": 4.0},
}
_DEFAULT_PRICING = {"input": 3.0, "cached_read": 0.3, "cached_write": 3.75, "output": 15.0}


def _pricing_for_model(model: str) -> dict[str, float]:
    for key, pricing in MODEL_PRICING.items():
        if key in model:
            return pricing
    return _DEFAULT_PRICING


def _estimate_cost_usd(entries: list[dict[str, Any]]) -> float:
    cost = 0.0
    for e in entries:
        p = _pricing_for_model(e.get("model", ""))
        cost += e.get("input_tokens", 0) / 1_000_000 * p["input"]
        cost += e.get("cached_input_tokens", 0) / 1_000_000 * p["cached_read"]
        cost += e.get("cache_creation_input_tokens", 0) / 1_000_000 * p["cached_write"]
        out = e.get("output_tokens", 0) + e.get("reasoning_output_tokens", 0)
        cost += out / 1_000_000 * p["output"]
    return round(cost, 4)


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    total_in = total_out = total_cached_read = total_cached_write = total_reasoning = 0
    for e in entries:
        total_in += e.get("input_tokens", 0)
        total_out += e.get("output_tokens", 0)
        total_cached_read += e.get("cached_input_tokens", 0)
        total_cached_write += e.get("cache_creation_input_tokens", 0)
        total_reasoning += e.get("reasoning_output_tokens", 0)
    return {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cached_input_tokens": total_cached_read,
        "cache_creation_input_tokens": total_cached_write,
        "reasoning_output_tokens": total_reasoning,
        "total_tokens": total_in + total_out + total_reasoning,
        "estimated_cost_usd": _estimate_cost_usd(entries),
        "entry_count": len(entries),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect token usage from Claude Code local JSONL files",
    )
    parser.add_argument(
        "--start-time", required=True,
        help="ISO 8601 start of time window (inclusive), e.g. 2026-05-25T10:00:00Z",
    )
    parser.add_argument(
        "--end-time", required=True,
        help="ISO 8601 end of time window (inclusive), e.g. 2026-05-25T10:05:00Z",
    )
    parser.add_argument(
        "--claude-config-dir", type=Path, default=None,
        help="Override Claude Code config directory (default: ~/.claude).",
    )
    parser.add_argument(
        "--claude-jsonl",
        type=Path,
        action="append",
        default=[],
        help="Limit collection to a specific JSONL file. Repeatable. "
             "For subagents, pass the exact subagents/agent-*.jsonl path.",
    )
    parser.add_argument(
        "--claude-session-id",
        action="append",
        default=[],
        help="Filter events by sessionId or JSONL filename stem. "
             "Repeatable or comma-separated.",
    )
    parser.add_argument(
        "--claude-agent-id",
        action="append",
        default=[],
        help="Filter events by agentId or agent-*.jsonl filename. "
             "Repeatable or comma-separated.",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Write result JSON to this path instead of stdout.",
    )
    args = parser.parse_args()

    start = parse_ts(args.start_time)
    end = parse_ts(args.end_time)
    if start is None or end is None:
        print("Error: invalid --start-time or --end-time format", file=sys.stderr)
        sys.exit(1)

    claude_jsonl_paths = [p.expanduser() for p in args.claude_jsonl]
    claude_session_ids = _filter_set(args.claude_session_id)
    claude_agent_ids = _filter_set(args.claude_agent_id)

    config_dirs = [args.claude_config_dir] if args.claude_config_dir else None
    entries = collect_claude_code(
        start,
        end,
        config_dirs,
        jsonl_paths=claude_jsonl_paths,
        session_ids=claude_session_ids,
        agent_ids=claude_agent_ids,
    )

    result = {
        "source": "claude-code",
        "entries": entries,
        "summary": summarize(entries),
        "time_window": {
            "start": args.start_time,
            "end": args.end_time,
        },
        "collection_method": "claude_code_jsonl" if entries else "none",
    }

    output_json = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_json, encoding="utf-8")
        print(f"[collect_local_usage] wrote {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
