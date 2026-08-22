#!/usr/bin/env python3
"""Write timing metadata for a benchmark run.

Supports two token-tracking modes, used in priority order:

1. **Local usage collection** (``--local-usage-json``): reads token data
   collected by ``collect_local_usage.py`` from local AI-tool state files
   (Claude Code JSONL / Cursor hooks logs).  This is the most accurate source
   because it captures the raw Anthropic/OpenAI API ``usage`` fields directly,
   bypassing the potentially unstable ``<usage>`` block returned by subagents.

2. **Subagent ``<usage>`` block** (``--total-tokens`` / ``--duration-ms``):
   the original path where the parent agent extracts values from the Agent
   tool result.  Still supported as a fallback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.eval_helpers import docs_bundle_stats, read_text


def _load_local_usage(path: Path) -> dict | None:
    """Load and validate a local-usage JSON file produced by collect_local_usage.py."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data.get("summary")
        if not isinstance(summary, dict):
            return None
        if summary.get("entry_count", 0) == 0:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _load_cursor_agent_json(path: Path) -> dict | None:
    """Load usage from cursor-agent --print --output-format json output.

    Expected shape: {"usage": {"inputTokens": N, "outputTokens": N,
    "cacheReadTokens": N, "cacheWriteTokens": N}, "session_id": "..."}
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return None
        input_tok = int(usage.get("inputTokens", 0))
        output_tok = int(usage.get("outputTokens", 0))
        cached_read = int(usage.get("cacheReadTokens", 0))
        cached_write = int(usage.get("cacheWriteTokens", 0))
        total = input_tok + output_tok
        if total == 0:
            return None
        return {
            "summary": {
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cached_input_tokens": cached_read,
                "cache_creation_input_tokens": cached_write,
                "reasoning_output_tokens": 0,
                "total_tokens": total,
                "entry_count": 1,
            },
            "session_id": data.get("session_id", ""),
            "collection_method": "cursor_agent_cli",
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Write timing.json for one benchmark run")
    parser.add_argument("--run-dir", required=True, type=Path, help="Path like <workspace>/eval-1-q1/with_docs/run-1")
    parser.add_argument("--total-tokens", type=int, default=0)
    parser.add_argument("--duration-ms", type=int, default=0)
    parser.add_argument(
        "--fallback-duration-ms",
        type=int,
        default=0,
        help="Parent-measured wall-clock duration to use when subagent usage.duration_ms is unavailable or zero.",
    )
    parser.add_argument("--tool-uses", type=int, default=0)
    parser.add_argument("--granularity", choices=["session_batch", "cold_start_per_question"], default="session_batch")
    parser.add_argument("--batch-id", default="", help="Internal batch identifier for debugging, not shown in reports.")
    parser.add_argument("--batch-index", type=int, default=0, help="Zero-based internal batch index.")
    parser.add_argument("--batch-size", type=int, default=0, help="Configured max batch size for this run.")
    parser.add_argument("--batch-question-count", type=int, default=0, help="Actual number of questions answered by this batch.")
    parser.add_argument("--docs-bundle-hash", default="", help="SHA-256 hash for the docs bundle used by this run.")
    parser.add_argument("--docs-bundle-chars", type=int, default=0, help="Character count for the docs bundle used by this run.")
    parser.add_argument("--estimated-docs-tokens", type=int, default=0, help="Estimated token count for the docs bundle used by this run.")
    parser.add_argument("--docs-token-estimate-method", default="", help="Method used for estimated docs tokens.")
    parser.add_argument(
        "--docs-bundle",
        type=Path,
        default=None,
        help="Optional docs bundle path. Defaults to <run-dir>/outputs/docs_bundle.md when present.",
    )
    parser.add_argument(
        "--allocation-count",
        type=int,
        default=1,
        help="For session_batch, number of answers sharing this subagent usage. Values are evenly amortized.",
    )
    parser.add_argument(
        "--local-usage-json",
        type=Path,
        default=None,
        help="Path to JSON produced by collect_local_usage.py. Fallback when <usage> block is missing.",
    )
    parser.add_argument(
        "--cursor-agent-json",
        type=Path,
        default=None,
        help="Path to JSON output from cursor-agent --print --output-format json. "
             "Contains usage.inputTokens/outputTokens/cacheReadTokens. "
             "Same priority as <usage> block (direct tool output, natively scoped).",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser()
    run_dir.mkdir(parents=True, exist_ok=True)

    # --- Resolve token source ---
    # Priority (highest first):
    #   1. --total-tokens from Claude Code <usage> block (natively scoped)
    #   2. --cursor-agent-json from cursor-agent CLI (natively scoped)
    #   3. --local-usage-json from collect_local_usage.py (fallback)
    #   4. zero (missing)
    local_usage: dict | None = None
    local_usage_path = ""
    source_total_tokens = max(0, int(args.total_tokens))

    if source_total_tokens > 0:
        token_source = "subagent_usage"
    else:
        token_source = "missing"

    # Tier 2: cursor-agent CLI output (same trust level as <usage> block)
    if source_total_tokens == 0 and args.cursor_agent_json:
        cursor_data = _load_cursor_agent_json(args.cursor_agent_json.expanduser())
        if cursor_data is not None:
            local_usage = cursor_data
            local_usage_path = str(args.cursor_agent_json)
            source_total_tokens = cursor_data["summary"]["total_tokens"]
            token_source = "cursor_agent_cli"

    # Tier 3: local log collection (fallback)
    if source_total_tokens == 0 and args.local_usage_json:
        local_usage = _load_local_usage(args.local_usage_json.expanduser())
        if local_usage is not None:
            local_usage_path = str(args.local_usage_json)
            summary = local_usage["summary"]
            local_total = max(0, summary.get("total_tokens", 0))
            if local_total == 0:
                local_total = max(0,
                    summary.get("input_tokens", 0)
                    + summary.get("output_tokens", 0)
                    + summary.get("reasoning_output_tokens", 0))
            if local_total > 0:
                source_total_tokens = local_total
                token_source = "local_collection"

    usage_duration_ms = max(0, int(args.duration_ms))
    fallback_duration_ms = max(0, int(args.fallback_duration_ms))
    if usage_duration_ms > 0:
        source_duration_ms = usage_duration_ms
        duration_source = "subagent_usage"
    elif fallback_duration_ms > 0:
        source_duration_ms = fallback_duration_ms
        duration_source = "parent_wall_clock"
    else:
        source_duration_ms = 0
        duration_source = "missing"
    source_tool_uses = max(0, int(args.tool_uses))
    allocation_count = max(1, int(args.allocation_count))
    batch_index = max(0, int(args.batch_index))
    batch_size = max(0, int(args.batch_size))
    batch_question_count = max(0, int(args.batch_question_count))

    docs_bundle_path = args.docs_bundle.expanduser() if args.docs_bundle else run_dir / "outputs" / "docs_bundle.md"
    if docs_bundle_path.is_file():
        inferred_docs_stats = docs_bundle_stats(read_text(docs_bundle_path))
    else:
        inferred_docs_stats = docs_bundle_stats("")
    docs_bundle_hash = str(args.docs_bundle_hash or inferred_docs_stats["docs_bundle_hash"])
    docs_bundle_chars = max(0, int(args.docs_bundle_chars or inferred_docs_stats["docs_bundle_chars"]))
    estimated_docs_tokens = max(0, int(args.estimated_docs_tokens or inferred_docs_stats["estimated_docs_tokens"]))
    docs_token_estimate_method = str(args.docs_token_estimate_method or inferred_docs_stats["docs_token_estimate_method"])

    if args.granularity == "session_batch":
        total_tokens = round(source_total_tokens / allocation_count)
        duration_ms = round(source_duration_ms / allocation_count)
        tool_uses = round(source_tool_uses / allocation_count)
        allocation_strategy = "even"
    else:
        total_tokens = source_total_tokens
        duration_ms = source_duration_ms
        tool_uses = source_tool_uses
        allocation_strategy = "none"

    payload = {
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
        "total_duration_seconds": round(duration_ms / 1000.0, 3) if duration_ms else 0.0,
        "tool_uses": tool_uses,
        "granularity": args.granularity,
        "batch_id": str(args.batch_id or ""),
        "batch_index": batch_index,
        "batch_size": batch_size,
        "batch_question_count": batch_question_count or allocation_count,
        "allocation_strategy": allocation_strategy,
        "allocation_count": allocation_count,
        "source_total_tokens": source_total_tokens,
        "source_duration_ms": source_duration_ms,
        "usage_duration_ms": usage_duration_ms,
        "fallback_duration_ms": fallback_duration_ms,
        "duration_source": duration_source,
        "source_tool_uses": source_tool_uses,
        "token_source": token_source,
        "docs_bundle_hash": docs_bundle_hash,
        "docs_bundle_chars": docs_bundle_chars,
        "estimated_docs_tokens": estimated_docs_tokens,
        "docs_token_estimate_method": docs_token_estimate_method,
    }

    if local_usage is not None:
        summary = local_usage["summary"]
        payload["local_usage"] = {
            "input_tokens": summary.get("input_tokens", 0),
            "output_tokens": summary.get("output_tokens", 0),
            "cached_input_tokens": summary.get("cached_input_tokens", 0),
            "cache_creation_input_tokens": summary.get("cache_creation_input_tokens", 0),
            "reasoning_output_tokens": summary.get("reasoning_output_tokens", 0),
            "estimated_cost_usd": summary.get("estimated_cost_usd", 0.0),
            "entry_count": summary.get("entry_count", 0),
            "collection_method": local_usage.get("collection_method", ""),
            "source_file": local_usage_path,
        }

    timing_path = run_dir / "timing.json"
    timing_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[kb-docs-benchmark] wrote {timing_path} (token_source={token_source})")


if __name__ == "__main__":
    main()
