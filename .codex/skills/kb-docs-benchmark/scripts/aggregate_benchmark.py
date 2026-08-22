#!/usr/bin/env python3
"""
Aggregate individual QA benchmark run results into viewer-compatible benchmark statistics.
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.eval_helpers import canonical_configuration_name, docs_bundle_stats, utc_now


# with_docs_compare: optional third config for --compare-docs-ref runs (current docs vs a
# ref version of the docs, e.g. slim before/after). Absent in the default two-config flow.
CANONICAL_CONFIG_ORDER = ["with_docs", "without_docs", "with_docs_compare"]


def calculate_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}

    count = len(values)
    mean = sum(values) / count
    if count > 1:
        variance = sum((value - mean) ** 2 for value in values) / (count - 1)
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0

    return {
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _int_metric(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_eval_metadata(eval_dir: Path) -> Dict[str, Any]:
    metadata_path = eval_dir / "eval_metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        return _read_json(metadata_path)
    except (json.JSONDecodeError, OSError):
        return {}


def _load_docs_quality_suggestions(benchmark_dir: Path) -> Optional[Dict[str, Any]]:
    path = benchmark_dir / "docs_quality_suggestions.json"
    if not path.exists():
        return None
    try:
        data = _read_json(path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: failed to read {path}: {exc}")
        return None
    if not isinstance(data, dict):
        print(f"Warning: ignoring {path}: root must be a JSON object")
        return None
    suggestions = data.get("suggestions")
    if suggestions is not None and not isinstance(suggestions, list):
        print(f"Warning: ignoring {path}: suggestions must be a list")
        return None
    return data


def _load_docs_bundle_stats(run_dir: Path) -> Dict[str, Any]:
    docs_bundle = run_dir / "outputs" / "docs_bundle.md"
    if not docs_bundle.is_file():
        return {}
    try:
        content = docs_bundle.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return docs_bundle_stats(content)


def _search_dir(benchmark_dir: Path) -> Optional[Path]:
    runs_dir = benchmark_dir / "runs"
    if runs_dir.exists():
        return runs_dir
    if list(benchmark_dir.glob("eval-*")):
        return benchmark_dir
    return None


def load_run_results(benchmark_dir: Path) -> Dict[str, Any]:
    search_dir = _search_dir(benchmark_dir)
    if search_dir is None:
        print(f"No eval directories found in {benchmark_dir} or {benchmark_dir / 'runs'}")
        return {
            "results": {},
            "metadata": {"eval_ids": [], "eval_names": [], "executor_models": [], "granularities": [], "runs_per_configuration": 0},
            "provenance_summary": {},
        }

    results: Dict[str, List[Dict[str, Any]]] = {}
    eval_ids: set[int] = set()
    eval_names: set[str] = set()
    executor_models: set[str] = set()
    granularities: set[str] = set()
    run_numbers_by_config: dict[str, set[int]] = defaultdict(set)
    provenance_summary: dict[str, dict[str, Any]] = {}

    for eval_dir in sorted(search_dir.glob("eval-*")):
        eval_metadata = _load_eval_metadata(eval_dir)
        fallback_eval_id = eval_metadata.get("eval_id")
        fallback_eval_name = eval_metadata.get("eval_name")

        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir():
                continue
            run_dirs = sorted(config_dir.glob("run-*"))
            if not run_dirs:
                continue

            canonical_configuration = canonical_configuration_name(config_dir.name)
            results.setdefault(canonical_configuration, [])

            for run_dir in run_dirs:
                try:
                    run_number = int(run_dir.name.split("-", 1)[1])
                except (IndexError, ValueError):
                    continue

                grading_path = run_dir / "grading.json"
                if not grading_path.exists():
                    print(f"Warning: grading.json not found in {run_dir}")
                    continue

                try:
                    grading = _read_json(grading_path)
                except (json.JSONDecodeError, OSError) as exc:
                    print(f"Warning: failed to read {grading_path}: {exc}")
                    continue

                run_manifest_path = run_dir / "run_manifest.json"
                run_manifest = {}
                if run_manifest_path.exists():
                    try:
                        run_manifest = _read_json(run_manifest_path)
                    except (json.JSONDecodeError, OSError) as exc:
                        print(f"Warning: failed to read {run_manifest_path}: {exc}")

                timing = grading.get("timing", {})
                timing_path = run_dir / "timing.json"
                if timing_path.exists():
                    try:
                        timing = {**timing, **_read_json(timing_path)}
                    except (json.JSONDecodeError, OSError):
                        pass

                execution_metrics = grading.get("execution_metrics", {})
                summary = grading.get("summary", {})
                docs_stats = _load_docs_bundle_stats(run_dir)
                if not docs_stats:
                    docs_bundle_hash = str(timing.get("docs_bundle_hash") or run_manifest.get("docs_bundle_hash") or "")
                    estimated_docs_tokens = _int_metric(
                        timing.get("estimated_docs_tokens"),
                        _int_metric(run_manifest.get("estimated_docs_tokens"), 0),
                    )
                    docs_bundle_chars = _int_metric(
                        timing.get("docs_bundle_chars"),
                        _int_metric(run_manifest.get("docs_bundle_chars"), 0),
                    )
                    if docs_bundle_hash or estimated_docs_tokens or docs_bundle_chars:
                        docs_stats = {
                            "docs_bundle_hash": docs_bundle_hash,
                            "docs_bundle_chars": docs_bundle_chars,
                            "estimated_docs_tokens": estimated_docs_tokens,
                            "docs_token_estimate_method": str(
                                timing.get("docs_token_estimate_method")
                                or run_manifest.get("docs_token_estimate_method")
                                or "chars_div_4_ceil"
                            ),
                        }
                provenance = run_manifest.get("question_provenance")
                if not isinstance(provenance, dict):
                    provenance = eval_metadata.get("provenance") if isinstance(eval_metadata.get("provenance"), dict) else {"type": "unknown"}
                provenance_type = str(provenance.get("type") or "unknown")

                eval_id = run_manifest.get("eval_id", fallback_eval_id)
                eval_name = run_manifest.get("eval_name", fallback_eval_name)
                executor_model = run_manifest.get("executor_model")
                if executor_model:
                    executor_models.add(str(executor_model))
                granularity = run_manifest.get("granularity")
                if granularity:
                    granularities.add(str(granularity))

                if isinstance(eval_id, int):
                    eval_ids.add(eval_id)
                if eval_name:
                    eval_names.add(str(eval_name))

                run_numbers_by_config[canonical_configuration].add(run_number)
                source_duration_ms = _int_metric(timing.get("source_duration_ms"), _int_metric(timing.get("duration_ms")))
                source_total_tokens = _int_metric(
                    timing.get("source_total_tokens"),
                    _int_metric(timing.get("total_tokens"), _int_metric(execution_metrics.get("output_chars"))),
                )
                source_tool_uses = _int_metric(timing.get("source_tool_uses"), _int_metric(timing.get("tool_uses")))

                result = {
                    "eval_id": eval_id,
                    "eval_name": eval_name,
                    "configuration": canonical_configuration,
                    "run_number": run_number,
                    "pass_rate": summary.get("pass_rate", 0.0),
                    "passed": summary.get("passed", 0),
                    "failed": summary.get("failed", 0),
                    "total": summary.get("total", 0),
                    "time_seconds": timing.get("total_duration_seconds", 0.0),
                    "tokens": timing.get("total_tokens", execution_metrics.get("output_chars", 0)),
                    "tool_calls": execution_metrics.get("total_tool_calls", 0),
                    "source_time_seconds": round(source_duration_ms / 1000.0, 3) if source_duration_ms else 0.0,
                    "source_duration_ms": source_duration_ms,
                    "source_tokens": source_total_tokens,
                    "source_tool_calls": source_tool_uses,
                    "estimated_docs_tokens": _int_metric(docs_stats.get("estimated_docs_tokens"), 0),
                    "docs_bundle_chars": _int_metric(docs_stats.get("docs_bundle_chars"), 0),
                    "docs_bundle_hash": str(docs_stats.get("docs_bundle_hash") or ""),
                    "docs_token_estimate_method": str(docs_stats.get("docs_token_estimate_method") or ""),
                    # write_timing 已经判定过用量是哪来的（subagent_usage / cursor_agent_cli /
                    # local_collection / missing），但这个判定一直没被往下带：聚合层不收、上报层
                    # 不发，于是 "missing" 这三个字从没离开过本机，看板只看得到 total_tokens=0，
                    # 与「真的没花 token」不可分辨。带上它，0 才能被解释。
                    "token_source": str(timing.get("token_source") or ""),
                    "allocation_count": _int_metric(timing.get("allocation_count"), 1),
                    "allocation_strategy": str(timing.get("allocation_strategy") or ""),
                    "batch_id": str(timing.get("batch_id") or run_manifest.get("batch_id") or ""),
                    "batch_index": _int_metric(timing.get("batch_index"), _int_metric(run_manifest.get("batch_index"), 0)),
                    "batch_size": _int_metric(timing.get("batch_size"), _int_metric(run_manifest.get("batch_size"), 0)),
                    "batch_question_count": _int_metric(
                        timing.get("batch_question_count"),
                        _int_metric(run_manifest.get("batch_question_count"), 0),
                    ),
                    "errors": execution_metrics.get("errors_encountered", 0),
                    "expectations": grading.get("expectations", []),
                    "notes": [],
                    "question_id": run_manifest.get("question_id"),
                    "question": run_manifest.get("question"),
                    "question_provenance": provenance,
                    "doc_root": run_manifest.get("doc_root"),
                    "missing_docs": run_manifest.get("missing_docs", []),
                    "executor_model": executor_model,
                    "granularity": granularity,
                }

                notes_summary = grading.get("user_notes_summary", {})
                if isinstance(notes_summary, dict):
                    result["notes"].extend(notes_summary.get("uncertainties", []))
                    result["notes"].extend(notes_summary.get("needs_review", []))
                    result["notes"].extend(notes_summary.get("workarounds", []))
                result["notes"].extend(grading.get("notes", []))
                if result["missing_docs"]:
                    result["notes"].append(f"Missing docs: {', '.join(result['missing_docs'])}")

                bucket = provenance_summary.setdefault(
                    provenance_type,
                    {
                        "runs": 0,
                        "configurations": defaultdict(list),
                    },
                )
                bucket["runs"] += 1
                bucket["configurations"][canonical_configuration].append(
                    {
                        "pass_rate": result["pass_rate"],
                        "time_seconds": result["time_seconds"],
                        "tokens": result["tokens"],
                    }
                )

                results[canonical_configuration].append(result)

    normalized_provenance_summary: dict[str, dict[str, Any]] = {}
    for provenance_type, payload in provenance_summary.items():
        configurations: dict[str, Any] = {}
        for configuration, metrics_list in payload["configurations"].items():
            configurations[configuration] = {
                "pass_rate": calculate_stats([item["pass_rate"] for item in metrics_list]),
                "time_seconds": calculate_stats([item["time_seconds"] for item in metrics_list]),
                "tokens": calculate_stats([item["tokens"] for item in metrics_list]),
            }
        normalized_provenance_summary[provenance_type] = {
            "runs": payload["runs"],
            "configurations": configurations,
        }

    runs_per_configuration = 0
    if run_numbers_by_config:
        runs_per_configuration = max(len(run_numbers) for run_numbers in run_numbers_by_config.values())

    return {
        "results": results,
        "metadata": {
            "eval_ids": sorted(eval_ids),
            "eval_names": sorted(eval_names),
            "executor_models": sorted(executor_models),
            "granularities": sorted(granularities),
            "runs_per_configuration": runs_per_configuration,
        },
        "provenance_summary": normalized_provenance_summary,
    }


def aggregate_results(results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    run_summary: Dict[str, Any] = {}
    ordered_configs = [config for config in CANONICAL_CONFIG_ORDER if config in results]
    ordered_configs.extend(config for config in sorted(results) if config not in ordered_configs)

    for config in ordered_configs:
        runs = results.get(config, [])
        run_summary[config] = {
            "pass_rate": calculate_stats([run["pass_rate"] for run in runs]),
            "time_seconds": calculate_stats([run["time_seconds"] for run in runs]),
            "tokens": calculate_stats([run["tokens"] for run in runs]),
        }

    with_docs = run_summary.get("with_docs", {})
    without_docs = run_summary.get("without_docs", {})
    # Only emit the docs-vs-no-docs delta when that baseline actually ran. A
    # compare-only run (with_docs + with_docs_compare, the shape used when the
    # question is "did this docs change help?") has no without_docs, and
    # subtracting the missing config's implicit 0.0 would publish with_docs' own
    # pass rate as a "delta" — a number that reads like a docs benefit and is
    # nothing of the kind. Absent is honest; a zero baseline is not.
    if with_docs and without_docs:
        delta_pass_rate = with_docs.get("pass_rate", {}).get("mean", 0.0) - without_docs.get("pass_rate", {}).get("mean", 0.0)
        delta_time = with_docs.get("time_seconds", {}).get("mean", 0.0) - without_docs.get("time_seconds", {}).get("mean", 0.0)
        delta_tokens = with_docs.get("tokens", {}).get("mean", 0.0) - without_docs.get("tokens", {}).get("mean", 0.0)
        run_summary["delta"] = {
            "pass_rate": f"{delta_pass_rate:+.2f}",
            "time_seconds": f"{delta_time:+.1f}",
            "tokens": f"{delta_tokens:+.0f}",
        }

    # Compare delta: current docs vs the --compare-docs-ref version (e.g. slim before/after).
    # Only present when a with_docs_compare run exists. Positive = current docs score higher.
    with_docs_compare = run_summary.get("with_docs_compare", {})
    if with_docs_compare:
        cmp_delta_pass_rate = (
            with_docs.get("pass_rate", {}).get("mean", 0.0)
            - with_docs_compare.get("pass_rate", {}).get("mean", 0.0)
        )
        run_summary["compare_delta"] = {
            "pass_rate": f"{cmp_delta_pass_rate:+.2f}",
            "note": "with_docs (current) minus with_docs_compare (--compare-docs-ref version)",
        }
    return run_summary


def aggregate_usage(results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    usage_summary: Dict[str, Any] = {}
    ordered_configs = [config for config in CANONICAL_CONFIG_ORDER if config in results]
    ordered_configs.extend(config for config in sorted(results) if config not in ordered_configs)

    for config in ordered_configs:
        per_run_sources: dict[int, dict[tuple[Any, ...], dict[str, float]]] = defaultdict(dict)
        # 用量是哪来的：把每个 run 的 token_source 收起来往上带。
        # 没有它，一个 total_tokens=0 无法区分「真的没花」和「两个采集源都没拿到」——
        # write_timing 早就判定过了，只是以前没人往下传。
        token_sources: list[str] = []
        for run in results.get(config, []):
            src = str(run.get("token_source") or "").strip()
            if src and src not in token_sources:
                token_sources.append(src)
            run_number = _int_metric(run.get("run_number"), 0)
            source_time_seconds = float(run.get("source_time_seconds") or run.get("time_seconds") or 0.0)
            source_tokens = _int_metric(run.get("source_tokens"), _int_metric(run.get("tokens")))
            source_tool_calls = _int_metric(run.get("source_tool_calls"), _int_metric(run.get("tool_calls")))
            docs_bundle_hash = str(run.get("docs_bundle_hash") or "")
            estimated_docs_tokens = _int_metric(run.get("estimated_docs_tokens"), 0)

            if run.get("allocation_strategy") == "even" and _int_metric(run.get("allocation_count"), 1) > 1:
                # session_batch repeats the same source usage on each question. Deduplicate
                # identical batch usage within the same configuration/run before summing.
                usage_key = (
                    "batch",
                    run_number,
                    run.get("batch_id") or run.get("batch_index"),
                    run.get("source_duration_ms"),
                    source_tokens,
                    source_tool_calls,
                    run.get("allocation_count"),
                )
            else:
                usage_key = (
                    "single",
                    run_number,
                    run.get("eval_id"),
                    run.get("question_id"),
                    source_time_seconds,
                    source_tokens,
                    source_tool_calls,
                )

            per_run_sources[run_number][usage_key] = {
                "time_seconds": source_time_seconds,
                "tokens": float(source_tokens),
                "tool_calls": float(source_tool_calls),
                "docs_bundle_hash": docs_bundle_hash,
                "estimated_docs_tokens": float(estimated_docs_tokens),
            }

        total_time_by_run: list[float] = []
        total_tokens_by_run: list[float] = []
        normalized_total_tokens_by_run: list[float] = []
        duplicate_docs_tokens_by_run: list[float] = []
        total_tool_calls_by_run: list[float] = []
        for sources in per_run_sources.values():
            raw_tokens = sum(source["tokens"] for source in sources.values())
            duplicate_docs_tokens = 0.0
            seen_docs: set[str] = set()
            for source in sources.values():
                docs_hash = str(source.get("docs_bundle_hash") or "")
                docs_tokens = float(source.get("estimated_docs_tokens") or 0.0)
                if not docs_hash or docs_tokens <= 0:
                    continue
                docs_tokens = min(docs_tokens, float(source.get("tokens") or 0.0))
                if docs_hash in seen_docs:
                    duplicate_docs_tokens += docs_tokens
                else:
                    seen_docs.add(docs_hash)
            total_time_by_run.append(sum(source["time_seconds"] for source in sources.values()))
            total_tokens_by_run.append(raw_tokens)
            duplicate_docs_tokens_by_run.append(duplicate_docs_tokens)
            normalized_total_tokens_by_run.append(max(0.0, raw_tokens - duplicate_docs_tokens))
            total_tool_calls_by_run.append(sum(source["tool_calls"] for source in sources.values()))

        usage_summary[config] = {
            "total_time_seconds": calculate_stats(total_time_by_run),
            "total_tokens": calculate_stats(total_tokens_by_run),
            "normalized_total_tokens": calculate_stats(normalized_total_tokens_by_run),
            "duplicate_docs_tokens": calculate_stats(duplicate_docs_tokens_by_run),
            "docs_token_estimate_method": "chars_div_4_ceil",
            "total_tool_calls": calculate_stats(total_tool_calls_by_run),
            "token_sources": token_sources,
        }

    with_docs = usage_summary.get("with_docs", {})
    without_docs = usage_summary.get("without_docs", {})
    if not (with_docs and without_docs):
        # Same reasoning as run_summary["delta"]: no baseline ran, so no delta.
        return usage_summary
    delta_total_time = with_docs.get("total_time_seconds", {}).get("mean", 0.0) - without_docs.get("total_time_seconds", {}).get("mean", 0.0)
    delta_total_tokens = with_docs.get("total_tokens", {}).get("mean", 0.0) - without_docs.get("total_tokens", {}).get("mean", 0.0)
    delta_normalized_total_tokens = with_docs.get("normalized_total_tokens", {}).get("mean", 0.0) - without_docs.get("normalized_total_tokens", {}).get("mean", 0.0)
    delta_duplicate_docs_tokens = with_docs.get("duplicate_docs_tokens", {}).get("mean", 0.0) - without_docs.get("duplicate_docs_tokens", {}).get("mean", 0.0)
    delta_total_tool_calls = with_docs.get("total_tool_calls", {}).get("mean", 0.0) - without_docs.get("total_tool_calls", {}).get("mean", 0.0)
    usage_summary["delta"] = {
        "total_time_seconds": f"{delta_total_time:+.1f}",
        "total_tokens": f"{delta_total_tokens:+.0f}",
        "normalized_total_tokens": f"{delta_normalized_total_tokens:+.0f}",
        "duplicate_docs_tokens": f"{delta_duplicate_docs_tokens:+.0f}",
        "total_tool_calls": f"{delta_total_tool_calls:+.0f}",
    }
    return usage_summary


def _derive_notes(run_summary: Dict[str, Any], provenance_summary: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    if "with_docs" in run_summary and "without_docs" in run_summary:
        delta = run_summary.get("delta", {})
        notes.append(
            "with_docs minus without_docs: "
            f"pass_rate {delta.get('pass_rate', '0.00')}, "
            f"amortized_time_seconds {delta.get('time_seconds', '0.0')}, "
            f"amortized_tokens {delta.get('tokens', '0')}"
        )

    for provenance_type in sorted(provenance_summary):
        configs = provenance_summary[provenance_type].get("configurations", {})
        with_docs = configs.get("with_docs", {})
        without_docs = configs.get("without_docs", {})
        if with_docs and without_docs:
            with_pass = with_docs.get("pass_rate", {}).get("mean", 0.0)
            without_pass = without_docs.get("pass_rate", {}).get("mean", 0.0)
            notes.append(
                f"Provenance {provenance_type}: pass rate delta {with_pass - without_pass:+.2f} "
                f"({with_pass:.2f} vs {without_pass:.2f})"
            )
    return notes


def generate_benchmark(benchmark_dir: Path, skill_name: str = "", skill_path: str = "") -> Dict[str, Any]:
    loaded = load_run_results(benchmark_dir)
    results = loaded["results"]
    metadata_info = loaded["metadata"]
    provenance_summary = loaded["provenance_summary"]
    run_summary = aggregate_results(results)
    usage_summary = aggregate_usage(results)

    ordered_configs = [config for config in CANONICAL_CONFIG_ORDER if config in results]
    ordered_configs.extend(config for config in sorted(results) if config not in ordered_configs)

    runs: List[Dict[str, Any]] = []
    for config in ordered_configs:
        for result in sorted(results.get(config, []), key=lambda item: (item.get("eval_id") or 0, item["run_number"])):
            runs.append(
                {
                    "eval_id": result["eval_id"],
                    "eval_name": result.get("eval_name"),
                    "configuration": config,
                    "run_number": result["run_number"],
                    "result": {
                        "pass_rate": result["pass_rate"],
                        "passed": result["passed"],
                        "failed": result["failed"],
                        "total": result["total"],
                        "time_seconds": result["time_seconds"],
                        "tokens": result["tokens"],
                        "tool_calls": result["tool_calls"],
                        "source_time_seconds": result["source_time_seconds"],
                        "source_tokens": result["source_tokens"],
                        "source_tool_calls": result["source_tool_calls"],
                        "estimated_docs_tokens": result["estimated_docs_tokens"],
                        "docs_bundle_chars": result["docs_bundle_chars"],
                        "docs_bundle_hash": result["docs_bundle_hash"],
                        "docs_token_estimate_method": result["docs_token_estimate_method"],
                        "errors": result["errors"],
                    },
                    "expectations": result["expectations"],
                    "notes": result["notes"],
                }
            )

    executor_model = metadata_info["executor_models"][0] if len(metadata_info["executor_models"]) == 1 else (", ".join(metadata_info["executor_models"]) if metadata_info["executor_models"] else None)
    granularity = metadata_info["granularities"][0] if len(metadata_info["granularities"]) == 1 else (", ".join(metadata_info["granularities"]) if metadata_info["granularities"] else None)
    benchmark = {
        "metadata": {
            "skill_name": skill_name or "kb-docs-benchmark",
            "skill_path": skill_path or str(benchmark_dir),
            "executor_model": executor_model,
            "execution_mode": "foreground_subagent",
            "granularity": granularity,
            "analyzer_model": None,
            "timestamp": utc_now(),
            "evals_run": metadata_info["eval_ids"],
            "runs_per_configuration": metadata_info["runs_per_configuration"],
            "configurations": ordered_configs,
        },
        "runs": runs,
        "run_summary": run_summary,
        "usage_summary": usage_summary,
        "provenance_summary": provenance_summary,
        "notes": _derive_notes(run_summary, provenance_summary),
    }
    docs_quality_suggestions = _load_docs_quality_suggestions(benchmark_dir)
    if docs_quality_suggestions:
        benchmark["docs_quality_suggestions"] = docs_quality_suggestions
    return benchmark


def generate_markdown(benchmark: Dict[str, Any]) -> str:
    metadata = benchmark["metadata"]
    run_summary = benchmark["run_summary"]
    usage_summary = benchmark.get("usage_summary", {})
    provenance_summary = benchmark.get("provenance_summary", {})

    # "delta"/"compare_delta" are summary keys, not configurations — never let the
    # fallback below pick one of them as a column.
    non_config_keys = {"delta", "compare_delta"}
    config_a = "with_docs" if "with_docs" in run_summary else next((key for key in run_summary if key not in non_config_keys), "with_docs")
    config_b = (
        "without_docs"
        if "without_docs" in run_summary
        else next((key for key in run_summary if key not in non_config_keys and key != config_a), "without_docs")
    )
    compare_run = config_b == "with_docs_compare"
    label_a = "With Docs (current)" if compare_run and config_a == "with_docs" else config_a.replace("_", " ").title()
    label_b = "With Docs (compare ref)" if compare_run else config_b.replace("_", " ").title()

    lines = [
        f"# Docs Benchmark: {metadata['skill_name']}",
        "",
        f"**Model**: {metadata.get('executor_model') or 'unknown'}",
        f"**Execution Mode**: {metadata.get('execution_mode') or 'foreground_subagent'}",
        f"**Granularity**: {metadata.get('granularity') or 'unknown'}",
        f"**Date**: {metadata['timestamp']}",
        f"**Evals**: {', '.join(map(str, metadata.get('evals_run', [])))} ({metadata.get('runs_per_configuration', 0)} runs each per configuration)",
        "",
        "## Summary",
        "",
        f"| Metric | {label_a} | {label_b} | Delta |",
        "|--------|------------|---------------|-------|",
    ]
    pass_rate_label = "Pass Rate"
    total_time_label = "Total Time"
    total_tokens_label = "Total Tokens"
    normalized_total_tokens_label = "Normalized Tokens (est.)"
    duplicate_docs_tokens_label = "Duplicate Docs Tokens (est.)"
    time_label = "Amortized Time"
    tokens_label = "Amortized Tokens"

    a_summary = run_summary.get(config_a, {})
    b_summary = run_summary.get(config_b, {})
    # In a compare-only run the meaningful delta is current docs vs ref docs, which
    # lives under compare_delta; run_summary["delta"] is absent there by design.
    delta = run_summary.get("delta") or (run_summary.get("compare_delta", {}) if compare_run else {})

    a_pr = a_summary.get("pass_rate", {})
    b_pr = b_summary.get("pass_rate", {})
    lines.append(f"| {pass_rate_label} | {a_pr.get('mean', 0) * 100:.0f}% ± {a_pr.get('stddev', 0) * 100:.0f}% | {b_pr.get('mean', 0) * 100:.0f}% ± {b_pr.get('stddev', 0) * 100:.0f}% | {delta.get('pass_rate', '—')} |")

    usage_delta = usage_summary.get("delta", {}) if isinstance(usage_summary, dict) else {}
    a_usage = usage_summary.get(config_a, {}) if isinstance(usage_summary, dict) else {}
    b_usage = usage_summary.get(config_b, {}) if isinstance(usage_summary, dict) else {}

    a_total_time = a_usage.get("total_time_seconds", {})
    b_total_time = b_usage.get("total_time_seconds", {})
    if a_total_time or b_total_time:
        lines.append(f"| {total_time_label} | {a_total_time.get('mean', 0):.1f}s ± {a_total_time.get('stddev', 0):.1f}s | {b_total_time.get('mean', 0):.1f}s ± {b_total_time.get('stddev', 0):.1f}s | {usage_delta.get('total_time_seconds', '—')}s |")

    a_duplicate_docs_tokens = a_usage.get("duplicate_docs_tokens", {})
    b_duplicate_docs_tokens = b_usage.get("duplicate_docs_tokens", {})
    duplicate_docs_mean = float(a_duplicate_docs_tokens.get("mean", 0) or 0) + float(b_duplicate_docs_tokens.get("mean", 0) or 0)
    if duplicate_docs_mean > 0:
        a_normalized_total_tokens = a_usage.get("normalized_total_tokens", {})
        b_normalized_total_tokens = b_usage.get("normalized_total_tokens", {})
        lines.append(f"| {normalized_total_tokens_label} | {a_normalized_total_tokens.get('mean', 0):.0f} ± {a_normalized_total_tokens.get('stddev', 0):.0f} | {b_normalized_total_tokens.get('mean', 0):.0f} ± {b_normalized_total_tokens.get('stddev', 0):.0f} | {usage_delta.get('normalized_total_tokens', '—')} |")
        lines.append(f"| {duplicate_docs_tokens_label} | {a_duplicate_docs_tokens.get('mean', 0):.0f} ± {a_duplicate_docs_tokens.get('stddev', 0):.0f} | {b_duplicate_docs_tokens.get('mean', 0):.0f} ± {b_duplicate_docs_tokens.get('stddev', 0):.0f} | {usage_delta.get('duplicate_docs_tokens', '—')} |")
    else:
        a_total_tokens = a_usage.get("total_tokens", {})
        b_total_tokens = b_usage.get("total_tokens", {})
        if a_total_tokens or b_total_tokens:
            lines.append(f"| {total_tokens_label} | {a_total_tokens.get('mean', 0):.0f} ± {a_total_tokens.get('stddev', 0):.0f} | {b_total_tokens.get('mean', 0):.0f} ± {b_total_tokens.get('stddev', 0):.0f} | {usage_delta.get('total_tokens', '—')} |")

    a_time = a_summary.get("time_seconds", {})
    b_time = b_summary.get("time_seconds", {})
    lines.append(f"| {time_label} | {a_time.get('mean', 0):.1f}s ± {a_time.get('stddev', 0):.1f}s | {b_time.get('mean', 0):.1f}s ± {b_time.get('stddev', 0):.1f}s | {delta.get('time_seconds', '—')}s |")

    a_tokens = a_summary.get("tokens", {})
    b_tokens = b_summary.get("tokens", {})
    lines.append(f"| {tokens_label} | {a_tokens.get('mean', 0):.0f} ± {a_tokens.get('stddev', 0):.0f} | {b_tokens.get('mean', 0):.0f} ± {b_tokens.get('stddev', 0):.0f} | {delta.get('tokens', '—')} |")

    if duplicate_docs_mean > 0:
        lines.extend([
            "",
            "_Normalized Tokens (est.) is the primary token metric for multi-batch docs runs. Raw Total Tokens are preserved in benchmark.json as `usage_summary.total_tokens` and include repeated docs reads._",
        ])

    if provenance_summary:
        lines.extend(["", "## Provenance Breakdown", ""])
        lines.append("| Provenance | Configuration | Pass Rate | Amortized Time | Amortized Tokens |")
        lines.append("|------------|---------------|-----------|------|--------|")
        for provenance_type in sorted(provenance_summary):
            configurations = provenance_summary[provenance_type].get("configurations", {})
            ordered_configs = [config for config in CANONICAL_CONFIG_ORDER if config in configurations]
            ordered_configs.extend(config for config in sorted(configurations) if config not in ordered_configs)
            for config in ordered_configs:
                stats = configurations[config]
                lines.append(
                    f"| {provenance_type} | {config} | {stats['pass_rate']['mean'] * 100:.0f}% | {stats['time_seconds']['mean']:.1f}s | {stats['tokens']['mean']:.0f} |"
                )

    if benchmark.get("notes"):
        lines.extend(["", "## Notes", ""])
        for note in benchmark["notes"]:
            lines.append(f"- {note}")

    docs_quality_suggestions = benchmark.get("docs_quality_suggestions")
    if isinstance(docs_quality_suggestions, dict):
        suggestions = docs_quality_suggestions.get("suggestions") or []
        lines.extend(["", "## Docs Quality Suggestions", ""])
        summary = docs_quality_suggestions.get("summary")
        if summary:
            lines.extend([str(summary), ""])
        if suggestions:
            for item in suggestions[:10]:
                if not isinstance(item, dict):
                    continue
                priority = item.get("priority", "unknown")
                category = item.get("category", "unknown")
                question_id = item.get("question_id", "unknown")
                recommendation = item.get("recommendation") or item.get("problem") or ""
                lines.append(f"- **{priority}** `{category}` `{question_id}`: {recommendation}")
        else:
            lines.append("- No suggestions provided.")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate benchmark run results into summary statistics")
    parser.add_argument("benchmark_dir", type=Path, help="Path to the benchmark directory")
    parser.add_argument("--skill-name", default="", help="Name of the skill being benchmarked")
    parser.add_argument("--skill-path", default="", help="Path to the skill being benchmarked")
    parser.add_argument("--output", "-o", type=Path, help="Output path for benchmark.json (default: <benchmark_dir>/benchmark.json)")
    args = parser.parse_args()

    if not args.benchmark_dir.exists():
        print(f"Directory not found: {args.benchmark_dir}")
        sys.exit(1)

    benchmark = generate_benchmark(args.benchmark_dir, args.skill_name, args.skill_path)

    output_json = args.output or (args.benchmark_dir / "benchmark.json")
    output_md = output_json.with_suffix(".md")

    output_json.write_text(json.dumps(benchmark, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated: {output_json}")

    output_md.write_text(generate_markdown(benchmark), encoding="utf-8")
    print(f"Generated: {output_md}")

    print("\nSummary:")
    for config in [config for config in CANONICAL_CONFIG_ORDER if config in benchmark["run_summary"]]:
        pass_rate = benchmark["run_summary"][config]["pass_rate"]["mean"]
        print(f"  {config.replace('_', ' ').title()}: {pass_rate * 100:.1f}% pass rate")
    print(f"  Delta: {benchmark['run_summary'].get('delta', {}).get('pass_rate', '—')}")


if __name__ == "__main__":
    main()
