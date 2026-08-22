# JSON Schemas

This document defines the JSON schemas used by `kb-docs-benchmark`.

---

## evals.json

Defines the benchmark suite for doc-root usefulness measurement. The expected doc root shape is:

- `CLAUDE.md`
- `docs/interface.md`
- `docs/workflow.md`
- `docs/domain.md`
- `docs/rule.md`

Prefer storing `evals.json` at `<doc-root>/docs/evals/evals.json`. Use a `doc_root` path relative to the repository root when the docs live inside the repo. Absolute in-repo paths are accepted with a warning for compatibility with older evals.

Important: `evals[].doc_root` must be the module root containing `CLAUDE.md` and `docs/`, not the `docs/` directory itself.

This schema supports two eval modes:
- `mode: "docs"`: verify the markdown docs themselves.
- `mode: "qa"`: ask repeated Q&A with and without docs, then compare answer quality, time, and token usage.

```json
{
  "suite_name": "kb-docs-benchmark",
  "evals": [
    {
      "id": 1,
      "name": "module-foo-docs",
      "mode": "docs",
      "doc_root": "path/to/module-root",
      "doc_paths": [
        "CLAUDE.md",
        "docs/interface.md",
        "docs/workflow.md",
        "docs/domain.md",
        "docs/rule.md"
      ],
      "assertions": [
        {
          "id": "required_files",
          "type": "files_exist",
          "paths": [
            "CLAUDE.md",
            "docs/interface.md",
            "docs/workflow.md",
            "docs/domain.md",
            "docs/rule.md"
          ]
        }
      ],
      "rubric": {
        "template": "rubric.md"
      }
    },
    {
      "id": 2,
      "name": "module-foo-qa",
      "mode": "qa",
      "doc_root": "path/to/module-root",
      "doc_paths": [
        "CLAUDE.md",
        "docs/interface.md",
        "docs/workflow.md",
        "docs/domain.md",
        "docs/rule.md"
      ],
      "questions": [
        {
          "id": "q1",
          "question": "Where is the public entry point and what inputs does it require?",
          "topics": ["public_api"],
          "source_files": ["path/to/module-root/src/public_entry.py"],
          "provenance": {
            "type": "human",
            "author": "alice"
          },
          "assertions": [
            {
              "id": "mentions_public_entry",
              "type": "contains",
              "text": "PublicEntryPoint"
            }
          ]
        },
        {
          "id": "q2",
          "question": "Which workflow step handles retries?",
          "topics": ["workflow", "retry"],
          "source_files": ["path/to/module-root/src/retry_handler.py"],
          "provenance": {
            "type": "llm",
            "model": "claude-opus-4-6",
            "prompt_source": "question-synthesis-v1"
          },
          "assertions": [
            {
              "id": "mentions_retry_handler",
              "type": "contains",
              "text": "RetryHandler"
            }
          ]
        }
      ]
    }
  ]
}
```

**Fields:**
- `suite_name`: Benchmark suite name.
- `evals[].id`: Unique integer identifier.
- `evals[].name`: Human-readable eval name.
- `evals[].mode`: `"docs"` or `"qa"`.
- `evals[].doc_root`: Module root directory containing `CLAUDE.md` and `docs/`. Prefer repo-root-relative paths for in-repo docs.
- `evals[].doc_paths`: Relative paths included in doc bundling and missing-doc checks.
- `evals[].assertions`: Objective checks for docs mode.
- `evals[].questions`: QA questions for compare mode.
- `questions[].topics`: Optional topic labels such as `public_api`, `workflow`, `lifecycle`, `error_handling`, or module-specific labels.
- `questions[].source_files`: Optional repo-root-relative source files that motivated the question.
- `questions[].provenance`: Optional source metadata for the question.
  - `provenance.type`: Recommended values are `human` or `llm`.
  - Additional fields such as `author`, `model`, or `prompt_source` are allowed.

For QA questions, assertions should check answer content such as symbols, APIs, call-chain nodes, behavior, state, or business concepts. Do not assert that the answer contains docs paths such as `CLAUDE.md`, `docs/interface.md`, or `docs/evals/**`.

Supported QA assertion types:
- `contains`: requires non-empty `text`; best for exact symbols, APIs, class names, method names, protocols, AB keys, enum cases, and stable domain terms.
- `regex`: requires non-empty valid `pattern`; best for flexible wording, ordering, alternatives, and relationships that simple keyword checks cannot prove.

Avoid empty patterns, `.*`, or broad regexes that can match unrelated answers.

---

## isolation_manifest.json

Workspace-level metadata written at `<workspace>/isolation_manifest.json` by `scripts/prepare_code_only_worktree.py`.

```json
{
  "isolation": "git_worktree_pair",
  "code_only_root": "/tmp/kb-docs-benchmark-module/code_only_worktree",
  "with_docs_root": "/tmp/kb-docs-benchmark-module/with_docs_worktree",
  "repo_root": "/abs/path/to/repo-root",
  "doc_root": "path/to/module-root",
  "target_doc_root": "path/to/module-root",
  "resolved_doc_root": "/abs/path/to/repo-root/path/to/module-root",
  "doc_root_exists": true,
  "source_ref": "0123456789abcdef",
  "removed_paths": [
    "path/to/module-root/CLAUDE.md",
    "path/to/module-root/docs"
  ],
  "with_docs_removed_paths": [
    "path/to/module-root/docs/evals"
  ],
  "missing_paths": [],
  "with_docs_missing_paths": [],
  "reused": false,
  "recreated_reason": "",
  "created_at": "2026-04-01T00:00:00Z"
}
```

- Gives `without_docs` a root where repository search cannot accidentally read the docs bundle.
- Gives `with_docs` a root where repository search can read normal docs but cannot read `docs/evals/**` questions or assertions.
- Records the source revision used for code-only isolation.
- Documents exactly which docs files were removed.
- Records missing docs paths instead of failing when the docs root or docs files are absent.
- Records whether an existing isolation workspace was reused or recreated.

---

## run_manifest.json

Per-run execution metadata emitted at `<run-dir>/run_manifest.json`.

```json
{
  "suite_name": "kb-docs-benchmark",
  "eval_id": 2000,
  "base_eval_id": 2,
  "eval_name": "module-foo-qa::q1",
  "question_id": "q1",
  "question_index": 0,
  "question": "Where is the public entry point and what inputs does it require?",
  "question_provenance": {
    "type": "human",
    "author": "alice"
  },
  "configuration": "with_docs",
  "canonical_configuration": "with_docs",
  "include_docs": true,
  "run_number": 3,
  "granularity": "session_batch",
  "batch_id": "batch-1",
  "batch_index": 0,
  "batch_size": 5,
  "batch_question_count": 5,
  "allocation_strategy": "even",
  "allocation_count": 12,
  "doc_root": "path/to/module-root",
  "doc_paths": [
    "CLAUDE.md",
    "docs/interface.md",
    "docs/workflow.md",
    "docs/domain.md",
    "docs/rule.md"
  ],
  "missing_docs": [],
  "executor_model": "claude-opus-4-6",
  "duration_ms": 24321,
  "total_duration_seconds": 24.321,
  "total_tokens": 4120,
  "source_duration_ms": 291852,
  "source_total_tokens": 494400,
  "docs_bundle_hash": "b7c4...",
  "docs_bundle_chars": 80000,
  "estimated_docs_tokens": 20000,
  "docs_token_estimate_method": "chars_div_4_ceil",
  "assertion_ids": ["mentions_public_entry"],
  "generated_at": "2026-04-01T00:00:00Z"
}
```

**Purpose:**
- Preserves canonical vs legacy configuration naming.
- Records question provenance.
- Records subagent granularity. `session_batch` means one subagent answered all questions for a configuration and token/time are amortized per question. `cold_start_per_question` means a fresh subagent answered one `(question, configuration)` pair.
- Records internal batch metadata for debugging. Batch IDs are not part of the user-facing report.
- Carries per-run metadata needed for aggregation.

---

## grading.json

Output from the assertion grader at `<run-dir>/grading.json`.

```json
{
  "expectations": [
    {
      "text": "[mentions_public_entry] Answer contains: PublicEntryPoint",
      "passed": true,
      "evidence": "Found"
    }
  ],
  "summary": {
    "passed": 1,
    "failed": 0,
    "total": 1,
    "pass_rate": 1.0
  },
  "execution_metrics": {
    "tool_calls": {},
    "total_tool_calls": 0,
    "total_steps": 1,
    "errors_encountered": 0,
    "output_chars": 512,
    "transcript_chars": 0
  },
  "timing": {
    "total_duration_seconds": 24.321,
    "total_tokens": 4120
  },
  "notes": []
}
```

---

## timing.json

Wall clock timing for a run. Located at `<run-dir>/timing.json`.

```json
{
  "total_tokens": 4120,
  "duration_ms": 24321,
  "total_duration_seconds": 24.321,
  "duration_source": "subagent_usage",
  "batch_id": "batch-1",
  "batch_index": 0,
  "batch_size": 5,
  "batch_question_count": 5,
  "usage_duration_ms": 24321,
  "fallback_duration_ms": 0,
  "source_total_tokens": 494400,
  "source_duration_ms": 291852,
  "docs_bundle_hash": "b7c4...",
  "docs_bundle_chars": 80000,
  "estimated_docs_tokens": 20000,
  "docs_token_estimate_method": "chars_div_4_ceil"
}
```

`duration_source` is `subagent_usage` when the subagent usage block provides duration, `parent_wall_clock` when the parent orchestrator supplied a fallback duration, and `missing` when neither source is available. Token counts should not be estimated; missing token usage remains `0` until a reliable source is available. `estimated_docs_tokens` is a separate docs-bundle-only estimate used for normalized reporting, not a replacement for model usage.

---

## benchmark.json

Aggregated compare output at `<workspace>/benchmark.json`.

```json
{
  "metadata": {
    "skill_name": "kb-docs-benchmark",
    "skill_path": "/path/to/workspace",
    "executor_model": "claude-opus-4-6",
    "execution_mode": "foreground_subagent",
    "granularity": "session_batch",
    "analyzer_model": null,
    "timestamp": "2026-04-01T00:20:00Z",
    "evals_run": [2000, 2001, 2002],
    "runs_per_configuration": 3,
    "configurations": ["with_docs", "without_docs"]
  },
  "runs": [
    {
      "eval_id": 2000,
      "eval_name": "module-foo-qa::q1",
      "configuration": "with_docs",
      "run_number": 1,
      "result": {
        "pass_rate": 1.0,
        "passed": 1,
        "failed": 0,
        "total": 1,
        "time_seconds": 24.321,
        "tokens": 4120,
        "tool_calls": 0,
        "source_time_seconds": 291.852,
        "source_tokens": 494400,
        "source_tool_calls": 12,
        "errors": 0
      },
      "expectations": [
        {
          "text": "[mentions_public_entry] Answer contains: PublicEntryPoint",
          "passed": true,
          "evidence": "Found"
        }
      ],
      "notes": []
    }
  ],
  "run_summary": {
    "with_docs": {
      "pass_rate": {"mean": 0.85, "stddev": 0.05, "min": 0.8, "max": 0.9},
      "time_seconds": {"mean": 45.0, "stddev": 12.0, "min": 32.0, "max": 58.0},
      "tokens": {"mean": 3800.0, "stddev": 400.0, "min": 3200.0, "max": 4100.0}
    },
    "without_docs": {
      "pass_rate": {"mean": 0.35, "stddev": 0.08, "min": 0.28, "max": 0.45},
      "time_seconds": {"mean": 32.0, "stddev": 8.0, "min": 24.0, "max": 42.0},
      "tokens": {"mean": 2100.0, "stddev": 300.0, "min": 1800.0, "max": 2500.0}
    },
    "delta": {
      "pass_rate": "+0.50",
      "time_seconds": "+13.0",
      "tokens": "+1700"
    }
  },
  "usage_summary": {
    "with_docs": {
      "total_time_seconds": {"mean": 291.852, "stddev": 0.0, "min": 291.852, "max": 291.852},
      "total_tokens": {"mean": 494400.0, "stddev": 0.0, "min": 494400.0, "max": 494400.0},
      "normalized_total_tokens": {"mean": 454400.0, "stddev": 0.0, "min": 454400.0, "max": 454400.0},
      "duplicate_docs_tokens": {"mean": 40000.0, "stddev": 0.0, "min": 40000.0, "max": 40000.0},
      "docs_token_estimate_method": "chars_div_4_ceil",
      "total_tool_calls": {"mean": 12.0, "stddev": 0.0, "min": 12.0, "max": 12.0}
    },
    "without_docs": {
      "total_time_seconds": {"mean": 180.0, "stddev": 0.0, "min": 180.0, "max": 180.0},
      "total_tokens": {"mean": 252000.0, "stddev": 0.0, "min": 252000.0, "max": 252000.0},
      "total_tool_calls": {"mean": 8.0, "stddev": 0.0, "min": 8.0, "max": 8.0}
    },
    "delta": {
      "total_time_seconds": "+111.9",
      "total_tokens": "+242400",
      "normalized_total_tokens": "+202400",
      "duplicate_docs_tokens": "+40000",
      "total_tool_calls": "+4"
    }
  },
  "provenance_summary": {
    "human": {
      "runs": 6,
      "configurations": {
        "with_docs": {
          "pass_rate": {"mean": 1.0, "stddev": 0.0, "min": 1.0, "max": 1.0},
          "time_seconds": {"mean": 22.0, "stddev": 1.5, "min": 20.0, "max": 24.0},
          "tokens": {"mean": 3500.0, "stddev": 200.0, "min": 3300.0, "max": 3800.0}
        }
      }
    }
  },
  "notes": [
    "with_docs minus without_docs: pass_rate +0.50, time_seconds +13.0, tokens +1700"
  ],
  "docs_quality_suggestions": {
    "summary": "Docs improve public entry questions but do not cover retry behavior clearly.",
    "suggestions": [
      {
        "priority": "high",
        "category": "coverage_gap",
        "question_id": "q2",
        "doc_paths": ["docs/workflow.md"],
        "problem": "Retry behavior is missing from the workflow docs.",
        "evidence": "with_docs failed mentions_retry_handler.",
        "recommendation": "Document the retry handler and its caller path in docs/workflow.md.",
        "expected_impact": "Should improve docs-assisted correctness on retry questions."
      }
    ]
  }
}
```

---

## docs_quality_suggestions.json

Optional structured suggestions written at `<workspace>/docs_quality_suggestions.json` by Docs Quality Analysis Mode.
The prose fields should be written in English; category IDs, priorities, file paths, assertion IDs, and code symbols remain unchanged.

```json
{
  "summary": "Docs improve public entry questions but do not cover retry behavior clearly.",
  "suggestions": [
    {
      "priority": "high",
      "category": "coverage_gap",
      "question_id": "q2",
      "doc_paths": ["docs/workflow.md"],
      "problem": "Retry behavior is missing from the workflow docs.",
      "evidence": "with_docs failed mentions_retry_handler.",
      "recommendation": "Document the retry handler and its caller path in docs/workflow.md.",
      "expected_impact": "Should improve docs-assisted correctness on retry questions."
    }
  ]
}
```

Allowed categories:
- `coverage_gap`
- `redundant_docs`
- `misleading_docs`
- `navigation_gap`
- `stale_or_inconsistent`
- `eval_issue`

**Compatibility requirements:**
- `runs[].configuration` must be `with_docs` or `without_docs` for the viewer.
- `runs[].eval_name` should be present so the viewer labels sections cleanly.
- `metadata.execution_mode` should be `foreground_subagent` for benchmark runs orchestrated by the parent agent waiting on Subagent results.
- `run_summary.delta` should represent `with_docs - without_docs`.
- `run_summary.time_seconds` and `run_summary.tokens` are amortized per question.
- `usage_summary.total_*` represents total source usage per configuration/run. For `session_batch`, repeated per-question `source_*` values are deduplicated before aggregation.
- `usage_summary.normalized_total_tokens` subtracts repeated `with_docs` docs bundle token estimates across session batches using `docs_bundle_hash`. It is explicitly estimated and is the primary displayed token metric when available; `usage_summary.total_tokens` remains the raw observed source usage in JSON.
- Extra fields such as `provenance_summary` are allowed and should not break the viewer.
