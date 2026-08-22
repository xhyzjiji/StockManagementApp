#!/usr/bin/env python3
"""Report a completed kb-docs-benchmark run to the ai-sde telemetry channel.

Reads <workspace>/benchmark.json and POSTs ONE summary entry to the same
service-logs ingestion endpoint used by the ai-sde MCP/agent-hook, so benchmark
quality data lands in `ai_sde_service_logs` (service='kb-benchmark') and can be
joined with KB coverage/recall on the `kb_module` column.

Non-blocking by design: any failure (missing benchmark.json, network error,
non-2xx response) prints a warning and exits 0 so it never fails a benchmark
run. Use --strict to get a non-zero exit code for debugging.

Stdlib only. No model calls.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Same ingestion channel as ai-sde MetricsReporter (src/core/metrics-reporter.ts).
DEFAULT_API_BASE = "https://v45b0i5r.fn.bytedance.net/api/v1/aisde"
# Shared default metrics ingest token — same convention as tmb-cli (cli/telemetry.py)
# and ai-sde MetricsReporter, which both ship this default in distributed clients
# Follow the tmb precedent. Override order:
# --token > AISDE_METRICS_TOKEN env > ~/.adk-mobile-mcp/metrics-token file > default.
DEFAULT_BEARER_TOKEN = "aisde_default_metrics_token_0x9f3b2c1a8e7d6c5b4a3"
TOKEN_FILE = Path.home() / ".adk-mobile-mcp" / "metrics-token"

CLIENT_NAME = "kb-docs-benchmark"
CLIENT_VERSION = "1.0.0"
SERVICE = "kb-benchmark"
EVENT = "benchmark:completed"
# Traffic-source tag (口径台账 2026-07-13): source ∈ benchmark|skill|human(缺省).
# The recall crawler's benchmark-exclusion predicate matches data_json source ==
# "benchmark" ONLY; rows without the field fall back to the v3 time-window
# heuristic (retires after a 30-day window). Field names are the cross-emitter
# contract (this script / TMB harness / ai-sde emitter) — change via the ledger,
# not locally.
SOURCE = "benchmark"
SOURCE_DETAIL = "kb-docs-benchmark"


def normalize_project_path(project_path: str) -> str:
    """Mirror ai-sde normalizeProjectPath: absolute, no trailing slash, realpath."""
    absolute = os.path.abspath(project_path)
    if len(absolute) > 1 and absolute.endswith(os.sep):
        absolute = absolute.rstrip(os.sep)
    try:
        return os.path.realpath(absolute)
    except OSError:
        return absolute


def generate_project_id(project_path: str) -> str:
    """Mirror ai-sde generateProjectId: sha1 -> base64url (no padding) -> first 16."""
    normalized = normalize_project_path(project_path)
    digest = hashlib.sha1(normalized.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:16]


def resolve_user(repo_root: str, explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    try:
        email = subprocess.run(
            ["git", "-C", repo_root, "config", "user.email"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if email and "@" in email:
            return email.split("@", 1)[0]
    except Exception:
        pass
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def infer_platform(repo_root: str, explicit: Optional[str]) -> str:
    if explicit:
        p = explicit.strip().lower()
        if p == "android":
            return "Android"
        if p == "ios":
            return "iOS"
        return ""
    base = os.path.basename(normalize_project_path(repo_root)).lower()
    if "android" in base:
        return "Android"
    if "ios" in base:
        return "iOS"
    return ""


def _mean(stats: Any) -> Optional[float]:
    """→ float，或 None 表示【这一项没有采集到】。

    None 和 0.0 是两件必须分开的事：0.0 的意思是「测出来就是零」，None 的意思是
    「没测到」。旧实现把两者都折成 0.0，于是一次拿不到用量的运行，在看板上
    渲染成「这次跑没花 token、没调用工具」——与真实的零消耗不可分辨。
    """
    if isinstance(stats, dict):
        if "mean" not in stats:
            return None
        try:
            return float(stats["mean"])
        except (TypeError, ValueError):
            return None
    if stats is None:
        return None
    try:
        return float(stats)
    except (TypeError, ValueError):
        return None


# 用量字段：(输出键, benchmark.json 里的键, 小数位)。
# 采集不到就【整个键省略】，不写 0——省略在看板上是空的、会被追问；0 不会。
_USAGE_FIELDS = (
    ("totalTokens", "total_tokens", 0),
    ("normalizedTokens", "normalized_total_tokens", 0),
    ("totalTimeSeconds", "total_time_seconds", 1),
    ("totalToolCalls", "total_tool_calls", 0),
)


def config_summary(benchmark: Dict[str, Any], config: str) -> Optional[Dict[str, Any]]:
    """→ 该配置的汇总；通过率缺失时返回 None（调用方据此拒绝上报整份报告）。

    通过率是这份报告的全部意义所在。缺了它还照发，等于往看板上放一条
    「这个模块得 0 分」的记录，而真相是「这次没测出来」——同一个坑在回调模板上
    已经中过一次（agent 照抄占位的 0.0，让一次根本没跑的评测在库里留下 0 分）。
    """
    run = benchmark.get("run_summary", {}).get(config, {})
    usage = benchmark.get("usage_summary", {}).get(config, {})
    pass_rate = _mean(run.get("pass_rate"))
    if pass_rate is None:
        return None
    summary: Dict[str, Any] = {"passRate": round(pass_rate, 4)}
    for out_key, src_key, digits in _USAGE_FIELDS:
        value = _mean(usage.get(src_key))
        if value is None:
            continue
        summary[out_key] = round(value, digits) if digits else round(value)
    # 用量的来源判定（write_timing 早就算好了：subagent_usage / cursor_agent_cli /
    # local_collection / missing）。发出来，`totalTokens: 0` 才能被解释成
    # 「真的没花」还是「两个采集源都没拿到」——这正是 0 曾经骗人的地方。
    sources = [str(s) for s in (usage.get("token_sources") or []) if str(s).strip()]
    if sources:
        summary["tokenSource"] = ",".join(sources)
    return summary


def count_questions(benchmark: Dict[str, Any]) -> int:
    """Distinct questions = sum of grading totals across runs of one configuration."""
    per_config: Dict[str, int] = {}
    for run in benchmark.get("runs", []):
        config = run.get("configuration", "")
        total = run.get("result", {}).get("total", 0)
        if isinstance(total, (int, float)):
            per_config[config] = per_config.get(config, 0) + int(total)
    if not per_config:
        return 0
    return max(per_config.values())


def normalize_kb_module(doc_root: str) -> str:
    # 注意不能用 lstrip("./")——那是字符集剥离，会把 ".x/…"、绝对路径开头误剥，
    # kbModule join 键静默失联。只剥真正的 "./" 前缀。
    cleaned = doc_root.strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.rstrip("/")


class MissingPassRate(ValueError):
    """两臂之一没有通过率——这份报告不可解读，拒绝上报。"""


# 隔离等级：这一行的数字是在什么边界下测出来的。
#
# 为什么必须进 payload：在此之前看板上【没有任何字段】能区分「CLI 起独立进程跑的」和
# 「宿主 agent 用自己的 subagent 跑的」，于是后者被整步禁发——理由不是它不可信，
# 而是**万一不可信也看不出来**，会挨着可信的行、看起来一样可信。有了这个字段，
# 「可疑」就变成一个可过滤的属性，而不是一个必须靠禁发来执行的判断。
ISOLATION_LEVELS = ("process", "subagent", "unknown")
ISOLATION_DEFAULT = "unknown"


def build_payload(args: argparse.Namespace, benchmark: Dict[str, Any]) -> Dict[str, Any]:
    metadata = benchmark.get("metadata", {})
    with_docs = config_summary(benchmark, "with_docs")
    without_docs = config_summary(benchmark, "without_docs")
    # 缺一边就整份不发：delta 是这份报告的结论，而「跟一个没测出来的基线做减法」
    # 得到的不是 0，是一个假的 0。
    missing = [n for n, v in (("with_docs", with_docs), ("without_docs", without_docs)) if v is None]
    if missing:
        raise MissingPassRate(
            "缺少通过率的配置: " + "、".join(missing) + "；不上报（宁可看板上没有这次，也不放一条假的 0 分）"
        )
    delta_pass_rate = round(with_docs["passRate"] - without_docs["passRate"], 4)
    question_count = count_questions(benchmark)
    model = args.model or metadata.get("executor_model") or "unknown"
    kb_module = normalize_kb_module(args.doc_root)

    entry_data: Dict[str, Any] = {
        # `kbModule` feeds the kb_module VIRTUAL column in ai_sde_service_logs —
        # same repo-relative path convention as agent-hook recall tagging.
        "kbModule": kb_module,
        "source": SOURCE,
        "source_detail": SOURCE_DETAIL,
        "agent": args.agent,
        # 这一行的数字是在什么隔离边界下测出来的。看板要能把它当条件过滤，
        # 而不是只能靠「某类运行整批不上报」来保证可信度。
        "isolation": args.isolation,
        "model": model,
        "granularity": metadata.get("granularity") or "unknown",
        "evalIds": metadata.get("evals_run", []),
        "withDocs": with_docs,
        "withoutDocs": without_docs,
        "deltaPassRate": delta_pass_rate,
    }
    # 题数为 0 与「有通过率」是自相矛盾的——0 道题算不出通过率。所以这里的 0 只可能是
    # 「`runs` 这块没读到」，而不是「这次考了 0 题」。省略键，别让看板显示 n=0：
    # 那和其他用量字段是同一族的错——一个占位的零，长得像一次测量。
    if question_count > 0:
        entry_data["questionCount"] = question_count
    else:
        print(
            "Warning: benchmark.json 的 runs 里读不出题数，questionCount 键省略"
            "（不是 0——0 道题算不出通过率，这里的 0 只会是没读到）。",
            file=sys.stderr,
        )

    # isolation 进 message 而不只进 data：message 是唯一一个不 join、不解 JSON 就能
    # 一眼看到的字段。把可信度写在人第一眼看的地方，别只写在要展开才看得见的地方。
    message = (
        f"kb-docs-benchmark {kb_module}: with_docs {with_docs['passRate']:.0%} "
        f"vs without_docs {without_docs['passRate']:.0%} "
        f"(n={question_count if question_count > 0 else '?'}, delta={delta_pass_rate:+.0%}, model={model}, "
        f"agent={args.agent}, isolation={args.isolation})"
    )

    return {
        "projectId": generate_project_id(args.repo_root),
        "projectPath": normalize_project_path(args.repo_root),
        "platform": infer_platform(args.repo_root, args.platform),
        "sessionId": str(uuid.uuid4()),
        "user": resolve_user(args.repo_root, args.user),
        "department": args.department or "",
        "clientName": CLIENT_NAME,
        "clientVersion": CLIENT_VERSION,
        "mcpVersion": "",
        "entries": [
            {
                # No fractional seconds: the aisde /service-logs ingest validates ts against
                # ^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?$ and 400-rejects
                # millisecond timestamps (e.g. "...T12:51:04.581Z"), which silently dropped
                # every benchmark report (event=benchmark:completed was 0 all-time). 2026-06-16.
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "level": "info",
                "service": SERVICE,
                "event": EVENT,
                "message": message,
                "data": entry_data,
            }
        ],
    }


def post_with_retry(url: str, token: str, payload: Dict[str, Any], max_retries: int = 3) -> bool:
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(max_retries + 1):
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if 200 <= response.status < 300:
                    return True
                print(f"Warning: telemetry POST got HTTP {response.status}", file=sys.stderr)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            print(f"Warning: telemetry POST attempt {attempt + 1} failed: {exc}", file=sys.stderr)
        if attempt < max_retries:
            time.sleep(2 ** attempt)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Benchmark workspace containing benchmark.json")
    parser.add_argument("--repo-root", required=True, help="Absolute path to the benchmarked repository root")
    parser.add_argument("--doc-root", required=True, help="Repo-relative docs root (same path convention as recall kb_module)")
    parser.add_argument(
        "--agent",
        required=True,
        help=(
            "The runtime that ACTUALLY ran the answer workers this time "
            "(claude-code / cursor-agent / codex / …) — read it off the run, do not copy the example. "
            "A stale value here mislabels every row it produces, and nothing downstream can detect it."
        ),
    )
    parser.add_argument(
        "--isolation",
        required=True,
        choices=ISOLATION_LEVELS,
        help=(
            "REQUIRED. Isolation boundary the two arms were run under: "
            "'process' = each arm in its own CLI process/workspace; "
            "'subagent' = the host agent's own subagent facility, one thread per arm. "
            "'unknown' exists only for rows written before this flag was required — do not pass it. "
            "Required rather than defaulted because the answer is known before the run starts, "
            "and a defaulted value has no place in the receipt lines anyone actually reads: "
            "forgetting the flag would land a row that quietly says nothing."
        ),
    )
    parser.add_argument("--model", default="", help="Executor model override (default: benchmark.json metadata.executor_model)")
    parser.add_argument("--platform", default="", help="Android or iOS (default: inferred from repo root name, else empty)")
    parser.add_argument("--user", default="", help="Reporting user (default: git user.email prefix, else OS user)")
    parser.add_argument("--department", default="", help="Reporting department (optional)")
    parser.add_argument("--endpoint", default=os.environ.get("AISDE_METRICS_URL", DEFAULT_API_BASE), help="Telemetry API base URL")
    parser.add_argument("--token", default="", help="Bearer token (default: AISDE_METRICS_TOKEN env, then ~/.adk-mobile-mcp/metrics-token)")
    parser.add_argument("--dry-run", action="store_true", help="Print the payload without sending")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on failure (default: always exit 0)")
    args = parser.parse_args()

    failure_exit = 1 if args.strict else 0

    benchmark_path = Path(args.workspace) / "benchmark.json"
    if not benchmark_path.exists():
        print(f"Warning: {benchmark_path} not found; skipping telemetry.", file=sys.stderr)
        return failure_exit
    try:
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: failed to read benchmark.json: {exc}; skipping telemetry.", file=sys.stderr)
        return failure_exit

    run_summary = benchmark.get("run_summary", {})
    if "with_docs" not in run_summary and "without_docs" not in run_summary:
        print("Warning: benchmark.json has no with_docs/without_docs run_summary; skipping telemetry.", file=sys.stderr)
        return failure_exit

    try:
        payload = build_payload(args, benchmark)
    except MissingPassRate as exc:
        print(f"Warning: {exc}", file=sys.stderr)
        return failure_exit

    # 传了 'unknown' 是显式选择，不是遗忘——遗忘现在被 argparse 挡在门外了。
    # 仍然吵一声，因为一行说不清自己可不可信的数据，在看板上只能被过滤掉。
    if args.isolation == ISOLATION_DEFAULT:
        print(
            "Warning: --isolation 显式传了 'unknown'。它只为「这个 flag 成为必填之前写下的行」"
            "保留；一次真的运行是知道自己怎么跑的。这一行落到看板上只能被过滤掉。",
            file=sys.stderr,
        )

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    token = args.token or os.environ.get("AISDE_METRICS_TOKEN", "")
    if not token and TOKEN_FILE.exists():
        try:
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
    if not token:
        token = DEFAULT_BEARER_TOKEN

    url = f"{args.endpoint.rstrip('/')}/service-logs"
    if post_with_retry(url, token, payload):
        entry = payload["entries"][0]
        print(f"Telemetry reported: {entry['message']}")
        return 0
    print("Warning: telemetry reporting failed after retries; benchmark results are unaffected.", file=sys.stderr)
    return failure_exit


if __name__ == "__main__":
    sys.exit(main())
