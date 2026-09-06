---
name: kb-docs-benchmark
description: Benchmark whether a docs root with CLAUDE.md and docs/{interface,workflow,domain,rule}.md improves multi-round Q&A quality, time, and token usage.
---

# KB Docs Benchmark

> Note: This skill runs the benchmark through agent workers — Claude Code subagents or `cursor-agent` CLI sessions depending on the environment. Python scripts are used only for grading, timing metadata helpers, and report/viewer generation; they must not call models for the benchmark.
>
> By default, launch one `without_docs` and one `with_docs` worker **in parallel**, each answering all questions in a single session. Both workers must be foreground (wait for result before proceeding). Auto-split into batches of 10 when question count exceeds 10.
>
> All `python3 scripts/grade_existing_answers.py`, `python3 scripts/write_timing.py`, and `python3 eval-viewer/...` commands below must be executed with the current skill directory as the working directory (the directory containing this SKILL.md). The scripts resolve their own dependencies relative to that location.

Use this skill to measure whether a documentation root is actually useful for question answering.

## Evaluation Protocol

The goal is to measure documentation usefulness, not to maximize answer pass rate.

Treat each `(question, configuration)` as an evaluation trial with strict information boundaries. Do not help a worker answer better by giving it information that the configuration is supposed to withhold. A lower score for `without_docs` is a valid and useful result; do not "fix" it by leaking docs context.

Configuration meanings:

- `without_docs`: code-only baseline. The worker may inspect repository source code, but must not read, quote, summarize, or cite the docs bundle (`CLAUDE.md`, `docs/interface.md`, `docs/workflow.md`, `docs/domain.md`, `docs/rule.md`, or `docs/evals/**`).
- `with_docs`: docs-assisted condition. The worker may inspect repository source code and may use the docs bundle listed in `doc_paths`.

For a given question, both configurations must have the same repository/code access. The only controlled difference is docs-bundle access. Do not restrict, expand, or otherwise change the source files one configuration may inspect unless the eval is explicitly designed to measure code-access differences rather than documentation usefulness.

Both configurations must use isolated workspaces by default. Prepare them from the same repository revision. Remove the docs bundle from `without_docs`; keep the docs bundle but remove `docs/evals/**` from `with_docs`. If this isolation cannot be prepared, stop and report the run as blocked rather than silently falling back to prompt-only isolation.

When orchestrating subagents:

- Use foreground subagents for benchmark answer runs. Do not set `run_in_background: true` for the `with_docs` / `without_docs` answer workers.
- Do not share answers, evidence, or docs excerpts from one configuration with another configuration.
- Do not tell the `without_docs` worker what the docs contain.
- Do not ask the `without_docs` worker to cite docs paths.
- If `without_docs` cannot answer part of a question from code inspection, that uncertainty should remain in the answer.
- Preserve failures and uncertainty; they are benchmark signal.

The canonical workflow is:
1. Prepare a docs root containing:
   - `CLAUDE.md`
   - `docs/interface.md`
   - `docs/workflow.md`
   - `docs/domain.md`
   - `docs/rule.md`
2. Define QA questions in `<doc-root>/docs/evals/evals.json`.
3. Run Claude Code subagent orchestration to generate answers.
4. Review `benchmark.json`, `benchmark.md`, per-question outputs, and `review.html`.
5. Preserve the configured information boundaries when interpreting results.
6. Report run telemetry with `scripts/report_telemetry.py` (default, non-blocking) so module
   benchmark quality — pass rates, token usage, executor model, agent type — lands in the
   shared KB metrics data and the KB dashboard can surface it per module.

## What this skill benchmarks

This skill is focused on docs usefulness, not generic skill creation.

It compares two configurations:
- `without_docs`: code-only baseline; answer from repository/source inspection without reading or citing the docs bundle.
- `with_docs`: docs-assisted condition; answer from repository/source inspection plus the docs bundle.

The benchmark captures:
- pass rate from answer assertions
- wall time
- token usage
- question provenance breakdowns such as human-authored vs LLM-authored questions
- per-question and per-configuration answer artifacts


## Inputs

### Docs root

Expected layout:

```text
<doc-root>/
├── CLAUDE.md
└── docs/
    ├── interface.md
    ├── workflow.md
    ├── domain.md
    └── rule.md
```

### Evals file

Prefer storing benchmark cases in `<doc-root>/docs/evals/evals.json`.

- The evals file should already exist before running this skill.
- If it is missing, ask the user whether to create it with `kb-evals-creator`.
- Use `mode: "qa"` for compare benchmarking.
- Use `mode: "docs"` for direct doc checks.
- For QA questions, add `provenance` when available.
- For generated QA questions, prefer `doc_root` relative to the repository root when the docs root lives in the repository.
- QA assertions must check answer content such as symbols, APIs, call-chain nodes, state transitions, error behavior, or business concepts. Do not assert that an answer contains docs paths such as `CLAUDE.md`, `docs/interface.md`, or `docs/evals/**`.

Example QA entry:

```json
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
    }
  ]
}
```

## Eval Generation

`kb-docs-benchmark` does not own eval generation. If `<doc-root>/docs/evals/evals.json` is missing, stop and ask the user whether to create it with `kb-evals-creator`. Do not run benchmark answer subagents until `evals.json` exists and passes validation.

The `kb-evals-creator` skill is the single source of truth for:
- docs-first question generation
- targeted codebase exploration with a 5 minute budget
- repo-root-relative `doc_root` for in-repo docs
- QA assertions that check answer content rather than docs path mentions

After `kb-evals-creator` creates or updates the file, validate it locally before running the benchmark:

```bash
cd .claude/skills/kb-docs-benchmark
python3 scripts/validate_evals.py \
  --evals /abs/path/to/repo-root/path/to/module-root/docs/evals/evals.json \
  --base-dir /abs/path/to/repo-root
```

## Canonical command

### Picking an answer-worker mechanism

Answer workers can run three ways. Pick by what the host actually provides — do not fall through to a mechanism whose prerequisite is missing, and do not silently substitute one for another:

| Host | Mechanism | Section |
|---|---|---|
| Claude Code session | Claude Code subagents (returns `<usage>`) | *Claude Code mode* below |
| Any host with a `cursor-agent` credential | `cursor-agent` CLI, one session per batch | *Token collection flow — Cursor* |
| Any other agent runtime (e.g. Codex), no CLI credential | the host agent's own subagent facility | *Agent-native subagent mode* below |

The third row exists because the first two both have hard prerequisites that some hosts do not meet: `Claude Code mode` assumes you are inside Claude Code, and the CLI path fails closed with `Error: Authentication required` when no `CURSOR_API_KEY` is present. A run that hits either wall must not be reported as a benchmark failure of the docs — it is an environment failure, and the correct outcome is `blocked` with the reason, not a pass rate.

### Agent-native subagent mode (any runtime, no CLI credential)

Use the **host agent's own subagent facility** to run the answer workers. No CLI is invoked, so no CLI credential is needed. Everything else in this skill is unchanged: same worktrees, same grading scripts, same artifacts.

Three properties differ from the CLI path, and every one of them must be **reported rather than assumed**:

1. **Isolation is a different mechanism here, and it has been measured.** The CLI enforced it with `--workspace`. A subagent is *assumed* to share the parent's context — but on the runtime this skill actually runs on, it does not: each worker thread starts from the system prompt alone, the `without_docs` prompt carries the prohibition and no doc text, and that worker's worktree has the docs removed on disk. Report it as `isolation: subagent`, not `prompt-level`: the boundary is a worktree plus a fresh thread, not a request to please not look.

   **What the measurement does and does not show.** On a 10-question set chosen because the CLI path scored 90.0% / 26.7% on it, the subagent path scored **96.67% / 20.0%**.

   - **Supported**: no large leak *in that run*. The two arms are **76.7pp apart**, far outside the ±15–20pp single-run noise this document declares elsewhere. An arm that could read the docs does not score 20%.
   - 🔴 **NOT supported**: "the subagent boundary is no weaker than process isolation." That claim rests on comparing 26.7% (CLI) against 20.0% (subagent) — **6.7pp, comfortably inside the same noise band**. The comparison is noise, and an earlier version of this section asserted it anyway. A number that survives one reading and not the other is not a weaker result; it is a different claim.

   **To settle the boundary, measure it directly instead of inferring it from scores.** Put a unique token in the parent context before launching the workers, and have the `without_docs` worker report whether it can see that token. One run, a deterministic yes/no, immune to question difficulty and to run-to-run noise. Until that runs, describe this mode as "no leak observed at 76.7pp separation" — not as equivalence with process isolation.

   **Report telemetry from this mode.** The reason it was suppressed was never "these numbers are wrong" — it was "a dashboard row carries no marker, so a suspect row would sit next to trustworthy ones looking equally trustworthy." That is now a field: pass `--isolation subagent` and the row says what it is. Suppressing a whole class of runs is what you do when you *cannot* express the caveat; once you can express it, suppressing instead is just hiding data that someone will later need and not find.
2. **Token accounting depends on the host, and is a measurement — not an assumption.** Some hosts return a usage block from a finished subagent; some return nothing. **Read what the host actually returned**: if there is a usage figure, use it (`token_source: "subagent_usage"`); if there is not, record `token_source: "missing"`. Do **not** pre-declare either outcome, and do not substitute the parent session's cumulative usage — that is the whole session's cost, not this arm's.

3. **Elapsed time has no source unless you take one.** A subagent that returns no usage block also returns no `duration_ms`, so `write_timing.py` records `duration_source: "missing"` and the arm reports no time at all.

   **Prefer the runner event log — the same place the tokens come from.** `collect_runner_tokens.py` reports the answer worker's own elapsed time as `dur=` on its `LOGTOK` line, taken from the runtime's `turn/completed`. Pass it through:

   ```bash
   python3 scripts/write_timing.py … --fallback-duration-ms "<the dur= value from LOGTOK>"
   ```

   **A parent-held stopwatch is the fallback, not the default**, and must be labelled as such. Measured against the runtime's own figure on one pair, the parent clock came out **+14%** on one leg and **−20%** on the other — small enough to look right, and inconsistent in sign, so it cannot be corrected for. The damage is in the comparison, not the absolute: that pair rendered as "无KB 慢 6%" while the authoritative numbers say **51%**. A duration that is roughly right is still a delta that is entirely wrong.

   ```bash
   # fallback only — when the log yields no dur=
   start_ms=$(python3 -c 'import time; print(int(time.time()*1000))')
   # …launch the answer worker as a foreground subagent and WAIT for it…
   end_ms=$(python3 -c 'import time; print(int(time.time()*1000))')
   ```

   `write_timing.py` prefers a subagent's own figure over whatever is passed here, so passing something is always safe: it fills a gap and never overrides a real measurement. **Omitting it entirely is what produced `duration_source: "missing"` on every agent-native run before this** — the flag existed the whole time and nothing passed it.

   Report which source won, in the summary, from `write_timing.py`'s own field: `duration_source=subagent_usage` / `parent_wall_clock` / `missing`.

⚠ **When comparing pass rates from this mode against CLI-path runs, say which mode each came from** — that is what `--isolation` is for. The mechanism differs (thread + worktree vs. process + `--workspace`), and a difference in mechanism is worth stating whether or not it turns out to be a difference in result.

**Neither direction of the strength comparison is supported by the pass rates.** Across the two modes the no-docs arm differs by **6.7pp** (26.7% → 20.0%) — inside the ±15–20pp single-run noise, so it cannot say that one boundary is stronger OR weaker than the other. To compare the boundaries, run the unique-token probe above; it answers yes/no in one run instead of asking a noisy number to carry a claim it cannot.

If a no-docs arm scores *high*, suspect the questions before the boundary: an easy question set lets an arm answer from the code, which looks identical to a leak and is far more common.

🔴 **Never report this mode as unavailable while using it.** If the host's subagent facility genuinely cannot start anything, that is a real and reportable outcome — but "unavailable" is only true when **zero** subagents started this run. Count them before making the claim, and state the count alongside it. A run that started subagents, answered the questions, and then reported the facility as unavailable sends every later reader to inspect credentials and skill paths, neither of which is broken. Failing is cheap; **naming the wrong cause is what costs the next person their afternoon.**

### Claude Code mode (recommended inside Claude Code)

When this skill is invoked, orchestrate the answers from the current Claude Code session:

1. Resolve the docs root and evals file:
   - docs root: the user-provided path
   - evals: `<doc-root>/docs/evals/evals.json`
   - workspace: `/tmp/kb-docs-benchmark-<doc-root-name>`
2. If the workspace already exists, stop and ask the user for confirmation before deleting it. Do not delete previous benchmark results automatically.

```bash
if [ -d /tmp/kb-docs-benchmark-<doc-root-name> ]; then
  echo "Previous benchmark workspace exists: /tmp/kb-docs-benchmark-<doc-root-name>"
  echo "Ask the user before deleting it. Do not proceed until they confirm."
  exit 2
fi
mkdir -p /tmp/kb-docs-benchmark-<doc-root-name>
```

If the user confirms deletion, then run:

```bash
rm -rf /tmp/kb-docs-benchmark-<doc-root-name>
mkdir -p /tmp/kb-docs-benchmark-<doc-root-name>
```

If the user wants to preserve previous results, choose a new workspace path with a timestamp suffix and report that path.

3. Prepare isolated worktrees for both answer configurations:

```bash
cd .claude/skills/kb-docs-benchmark
python3 scripts/prepare_code_only_worktree.py \
  --repo-root /abs/path/to/repo-root \
  --doc-root path/to/module-root \
  --evals /abs/path/to/repo-root/path/to/module-root/docs/evals/evals.json \
  --workspace /tmp/kb-docs-benchmark-<doc-root-name>
```

This creates:

```text
<workspace>/code_only_worktree
<workspace>/with_docs_worktree
<workspace>/isolation_manifest.json
```

If valid isolated worktrees already exist for the same repo root, doc root, and source revision, the helper reuses them. If either worktree is stale or invalid, the helper recreates both and records `reused` / `recreated_reason` in `isolation_manifest.json`.

The `without_docs` worker must receive `<workspace>/code_only_worktree` as its repository root and must not be pointed at the original repo. This worktree removes `CLAUDE.md` and `docs/`.

The `with_docs` worker must receive `<workspace>/with_docs_worktree` as its repository root and must not be pointed at the original repo. This worktree keeps the docs bundle but removes `docs/evals/**`, so the worker cannot read questions or assertions from `evals.json`.

4. Materialize canonical docs bundles before launching any answer subagent:

```bash
python3 scripts/prepare_docs_bundles.py \
  --evals /abs/path/to/repo-root/path/to/module-root/docs/evals/evals.json \
  --workspace /tmp/kb-docs-benchmark-<doc-root-name> \
  --base-dir /abs/path/to/repo-root
```

This writes:

```text
<workspace>/docs_bundles/eval-<eval_id>.md
<workspace>/docs_bundles/manifest.json
```

The parent orchestrator must treat these files as the only canonical docs bundle source for the run. Do not ask subagents to reformat, translate, summarize, or reconstruct the bundle. For every `with_docs` batch from the same eval, provide the same `<workspace>/docs_bundles/eval-<eval_id>.md` content and copy that exact file to each `outputs/docs_bundle.md`.

#### Compare mode (`--compare-docs-ref`)

To measure the same docs at two versions instead of docs-vs-no-docs (for example, does a slimmed doc still answer the same questions as the pre-slim doc), pass `--compare-docs-ref <git-ref>`.

##### When to route here

Compare mode answers "did this docs change help?". The default `with_docs` / `without_docs` flow answers a different question — "are these docs worth anything at all?" — so a request about a *change* must not be served by the default flow.

Route to compare mode for requests like: benchmark my docs change; compare before and after; is this version better than the previous one; did the slim hurt the docs; A/B the two versions of this doc root. Keep the default flow for: are these docs useful; do these docs help answer questions.

##### Resolving the "before" ref

If the user names a ref ("compare against v1.2", "against origin/main", a sha), use it verbatim. Never override an explicit ref with an inferred one.

Otherwise derive it from the repository. `DOC_REL` is the doc root relative to the repo root:

```bash
# Trunk detection. origin/HEAD is unset in plenty of checkouts (shallow clones, CI
# checkouts, any clone that never ran `git remote set-head`), so falling back to a
# hardcoded name is not safe: origin/master often still EXISTS as a stale branch, so
# guard 1 below would happily verify it while merge-base walked back far past the real
# fork point — turning compare_delta into a large fake improvement that no guard
# catches. Take the first ref that actually resolves, and stop if none do.
TRUNK=""
for CAND in "$(git symbolic-ref -q --short refs/remotes/origin/HEAD)" origin/develop origin/main origin/master; do
  [ -n "$CAND" ] || continue
  if git rev-parse --verify -q "$CAND^{commit}" >/dev/null; then TRUNK="$CAND"; break; fi
done
[ -n "$TRUNK" ] || { echo "no trunk ref resolved (tried origin/HEAD, develop, main, master)"; exit 1; }

# merge-base can legitimately fail (unrelated histories, grafted/shallow clone). An
# empty BASE would make the next line `git log "..HEAD"`, which does NOT error — it
# quietly returns nothing, reads as "no committed docs changes", falls through to
# HEAD, and produces a run whose delta is structurally always 0.
BASE=$(git merge-base HEAD "$TRUNK") || BASE=""
[ -n "$BASE" ] || { echo "merge-base HEAD $TRUNK failed — cannot establish a baseline"; exit 1; }

AHEAD=$(git log --oneline "$BASE..HEAD" -- "$DOC_REL")   # docs changes committed on this branch
DIRTY=$(git status --porcelain -- "$DOC_REL")            # docs changes still in the worktree
```

| Repository state | ref to use | Why |
|---|---|---|
| `AHEAD` non-empty (branch carries committed docs changes — whether or not the worktree is also dirty) | `$BASE` | The "after" side is the worktree, which already contains the committed *and* the uncommitted edits, so the baseline has to step back to where this branch left the trunk. Using `HEAD` here would compare the change against itself. |
| `AHEAD` empty, `DIRTY` non-empty | `HEAD` | The last commit is exactly the pre-change state. |
| Both empty | Stop. Report "no docs change detected under `<doc_root>`" and do not run compare mode. | There is nothing to compare; any ref picked here yields a meaningless delta. |

This covers both shapes users arrive with — edits sitting uncommitted in the working tree, and edits already committed on a feature branch — including the mixed case where both are present.

##### Required guards

A wrong or unresolvable ref does **not** fail loudly. `git show` returns non-zero per file and those files are recorded as missing, so the "before" bundle silently comes out EMPTY and `compare_delta` reports a large, entirely fake improvement. Inferring the ref automatically makes this failure more likely, not less, so all three guards are mandatory:

1. **Verify before use**: `git rev-parse --verify "<ref>^{commit}"`. Stop on failure; never silently fall back to another ref.
2. **Echo the resolution before spending a run**: the chosen ref with its short sha and subject, **which trunk ref was detected**, which side is the worktree, and which rule above fired. Showing the trunk matters — a run that silently resolved `origin/master` in a repo whose trunk is `origin/develop` looks identical to a correct one in every other respect. An inferred baseline must be rejectable by the user before the benchmark burns tokens.
3. **Re-check after preparing bundles**: read `<workspace>/docs_bundles_compare/manifest.json`. If `missing_docs` equals the entire `doc_paths` list for an eval, report the run as blocked and do not emit `compare_delta`. A *partial* `missing_docs` is expected and correct — a file the change added does not exist at the baseline.

##### Command

```bash
python3 scripts/prepare_docs_bundles.py \
  --evals /abs/path/to/repo-root/path/to/module-root/docs/evals/evals.json \
  --workspace /tmp/kb-docs-benchmark-<doc-root-name> \
  --base-dir /abs/path/to/repo-root \
  --compare-docs-ref <resolved-ref>
```

The "after" side is always the working tree as it stands — `prepare_docs_bundles.py` reads the docs straight off the filesystem, so uncommitted edits are included and the user does not need to commit first.

This additionally writes `<workspace>/docs_bundles_compare/eval-<eval_id>.md` — the same docs materialized as they existed at `<git-ref>`.

##### Run TWO configurations, not three

A compare run answers "did this docs change help", so it needs exactly two answer batches:

- `with_docs` — the current docs (working tree)
- `with_docs_compare` — identical to `with_docs` in every way (same questions, same `with_docs_worktree` code access, same isolation, same `docs/evals/**` removal) except that its docs bundle is the compare bundle

**Do not run `without_docs` in a compare run.** It answers a different question ("are these docs worth anything at all"), contributes nothing to the current-vs-ref comparison, and costs a full extra answer batch — a third of the run's tokens for a number nobody asked for. Run it only if the user separately asks whether the docs are useful at all.

##### Report and suggestions follow the same two configurations

- `aggregate_benchmark.py` emits `compare_delta.pass_rate = passRate(with_docs) − passRate(with_docs_compare)`. In a compare-only run there is no `without_docs`, so no docs-vs-no-docs `delta` is produced at all — the report's delta column shows `compare_delta`, and the two columns are labelled "With Docs (current)" and "With Docs (compare ref)".
- The docs-quality analyzer must judge on the current-vs-ref axis and use the compare categories (`regression` / `improvement` / `unchanged_gap` / `navigation_regression`); see `agents/docs_quality_analyzer.md`. Suggestions must never reason about a `without_docs` baseline that did not run.

This is a coarse signal (single-run noise is ±15–20pp); treat it as directional, not a gate.

5. Read `evals.json`. For a first smoke pass, use only the questions currently present in that file.
6. Answer workers write prose in English (their output is graded against assertions written in English). **Analysis subagents write prose in Chinese** — their output is read by people, not by a grader. Both preserve code symbols and API names verbatim.
7. Use `session_batch` granularity by default:
   - **Default: 1 batch per configuration.** Launch one `without_docs` agent and one `with_docs` agent in parallel, each answering all questions in a single session. Token usage is reported per-batch and amortized per-question.
   - **Auto-split when > 10 questions:** Split into batches of at most 10 questions each. Run batches within each configuration sequentially; the two configurations can still run in parallel.
   - Do not expose batch IDs in the final report; batching is only an execution-stability strategy.
   - This measures session-level docs usefulness: the docs bundle is paid once and its cost is amortized across the questions in that batch.
   - If the user explicitly asks for cold-start isolation, use `cold_start_per_question`: one fresh agent for each `(question, configuration)` pair.
8. Each batch subagent must return one answer per question:

```json
{
  "granularity": "session_batch",
  "configuration": "with_docs",
  "answers": [
    {
      "question_id": "q1",
      "answer": "Final answer text.",
      "evidence": ["Concise evidence or source symbols."]
    }
  ]
}
```

9. For each question, produce two answers:
   - `without_docs`: answer from `<workspace>/code_only_worktree` only. The docs bundle has been removed from that worktree; do not search/read the original repo or cite the docs bundle.
   - `with_docs`: answer from `<workspace>/with_docs_worktree` plus the docs bundle listed in `doc_paths`. The `docs/evals/**` files have been removed from that worktree; do not search/read the original repo.
10. Save each answer to the existing workspace layout:

```text
<workspace>/eval-<eval_id>-<question_id>/<configuration>/run-1/outputs/answer.md
<workspace>/eval-<eval_id>-<question_id>/<configuration>/run-1/outputs/question.md
<workspace>/eval-<eval_id>-<question_id>/<configuration>/run-1/outputs/prompt.md
```

The orchestrating parent agent must write timing metadata after each subagent completes.

```text
<workspace>/eval-<eval_id>-<question_id>/<configuration>/run-1/timing.json
```

### Token source priority

`write_timing.py` resolves `total_tokens` using this priority:

1. **`--total-tokens`** (from the usage block a finished answer-worker subagent returns) → `token_source: "subagent_usage"` — natively scoped to the subagent, no attribution risk. Claude Code returns one; other runtimes may or may not, so **check what came back instead of assuming either way**.
2. **The runner's own event log** → `token_source: "runner_event_log"` — see *Token collection flow — runner event log* below. Works on any runtime that logs usage, needs no cooperation from the subagent, and is written by the runner rather than composed by the agent. Prefer this over 3 whenever the log is reachable.
3. **`--local-usage-json`** (from `collect_local_usage.py`) → `token_source: "local_collection"` — fallback when no usage block is returned (e.g. Cursor). Requires precise ID-based attribution.
4. **None available** → `token_source: "missing"`, `total_tokens: 0`. Do not guess or publish polluted data.

`total_tokens: 0` and `token_source: "missing"` together mean **not measured**. They never mean "this arm cost nothing". Anything downstream that renders a cost must keep those two cases distinguishable.

### Token collection flow — agent-native subagent

The host decides whether a finished subagent hands back a usage figure. Treat that as the thing under test:

1. Launch the answer worker as a foreground subagent and wait for it.
2. **Inspect the returned result for a usage figure.** Found → pass it as `--total-tokens`.
3. **Not found → do not stop at `missing`.** Fall through to *Token collection flow — runner event log* below; a host that returns no usage to its subagents may still be logging it. `missing` is the verdict only after that path has also been probed and reported.
4. Report which happened, in the run summary, in these exact words: `token_source=subagent_usage`, `token_source=runner_event_log`, or `token_source=missing`. A reader cannot otherwise tell "this host does not expose usage" apart from "we forgot to collect it".
4. **Emit the fact through a channel that survives a dead run.** Some runtimes do not export the agent session at all — tool-call arguments, tool output, and the agent's own final message never reach the runner log, which leaves only one content-bearing channel: the first line of a subagent's returned result. So after the answer workers finish, launch one short subagent named `usage-receipt` and have it return, verbatim as its first line:

```text
USAGE with_docs=<total|none> without_docs=<total|none> source=<subagent_usage|runner_event_log|missing>
```

Without this line, "the host returns no usage" and "the run died before it got there" are indistinguishable from outside — and on a host that does not export sessions, there is no second place to look.

#### When the host returns no usage: probe the sandbox's local LLM proxy

> **Status: reachable, but not the path.** The probe resolved: the proxy answers, auth is accepted, and the `400` was `{"error":"unknown_model","model":"gpt-5"}` — a wrong model name in the probe, nothing about the route. Prefer *Token collection flow — runner event log* below and treat this section as reference. The reason is structural, not incidental: this proxy reports usage for **a call you make yourself**, whereas the number the benchmark needs is what the *answer worker* consumed. Getting those to be the same thing would mean reimplementing the answer worker as a direct HTTP client, which costs it the file-reading tool use it exists to do. Keep the section for the day a component genuinely needs to bill its own calls.

Some runners start a **local LLM proxy inside the sandbox** and route the agent's own model traffic through it (observed: listening on `http://127.0.0.1:18766`, forwarding to an internal GPT **Responses** endpoint, with auth injected by the platform as a query parameter). If a script can call that proxy directly, **token usage comes straight out of the HTTP response's `usage` field** — per-arm by construction, and independent of whether the host's subagents report anything.

Probe it before writing any code against it. One round, in this order:

1. **Base url**: check env for a `127.0.0.1` LLM/OpenAI-style base url; else use the observed `http://127.0.0.1:18766`.
2. **Auth parameter**: it is a *pattern*, not a secret to hunt for — the observed form is `ak=<runtime>:<username>`, e.g. `codex:<the username field from the run's input JSON>`. Build it from those two values you already have; only fall back to searching the host CLI's config if that form is rejected. **Record only "found"/"none" — never print the value.**
   A probe that reports `auth=none` has *not* established anything about the route: it means the request went out unauthenticated, and the `4xx` that follows says nothing about shape. Two runs of this probe disagreed on `auth` (one `found`, one `none`) precisely because the instruction said "go find it" instead of "build it from these two fields".
3. **Copy the URL shape from what the runner actually logged; do not invent one.** The observed shape is:

   ```text
   POST <base>/responses?api-version=2024-03-01-preview&ak=<the value found in step 2>
   ```

   The `api-version` query parameter is required — omitting it is a `400` on its own.
4. **Send both body shapes, once each, and report both codes.** The upstream is the Responses endpoint, whose schema differs from chat/completions; settling which shape is accepted costs nothing extra here and saves a whole run later:

   ```bash
   A='{"model":"<the model the host is configured with>","input":"ping","max_output_tokens":16}'
   B='{"model":"<same>","messages":[{"role":"user","content":"ping"}],"max_tokens":16}'
   ```
5. **On any non-2xx, carry back the error body's `message` (first 100 chars).** Without it, "the request was malformed" and "this route yields nothing" are indistinguishable — a probe that reports only a status code throws away the one field that says which.
   `err=` has three distinct values and they must not be collapsed: the message text when there is one; **`empty` when the response body is empty**; `none` **only** when no request was sent at all. Reporting `none` for an empty body destroys the distinction between "the server said nothing" and "we never asked".

Report the outcome as the first line of a `proxy-receipt` subagent result:

```text
PROXY base=<found|none> auth=<found|none> shapeA=<code|none> shapeB=<code|none> usage=<yes|no> total_tokens=<n|none> err=<first 100 chars|none>
```

**How to read that line** — do not collapse these three cases:

- `000` / connection refused → the route genuinely does not exist here.
- `4xx` → **reachable and authenticated**; only the shape or a parameter is wrong. This is a fixable result, not a dead end.
- `2xx` with no `usage` in the body → *this* is the evidence that the route does not carry usage.

🔴 **Never let an auth string reach output, summary, or receipt — not one character.** Report `found`/`none` and, if a length is genuinely needed, the length. A probe that fails can be retried; a leaked credential cannot be recalled.

And do not invent a number to make the line look complete: a guessed token count is worse than a missing one, because it reads as a measurement.

### Token collection flow — runner event log

The runtime writes token usage into its own run log as the session proceeds. That number is emitted by the runner, not composed by the agent, so it is the instrument reading rather than the subject self-reporting — and it survives a host whose subagents hand back nothing at all.

🔴 **The file name AND the event name change with the runtime. Never carry one runtime's pair over to another.** This exact mistake has now produced three separate confident conclusions of "there is no token data here", each from a grep that was looking for the other runtime's string:

| runtime | file | event | field case | granularity |
|---|---|---|---|---|
| cursor | `logs/agent.log` | `{"event":{"name":"token:usage","from":"MAIN_AGENT",…}}` | `input_tokens` / `output_tokens` / `total_tokens` | one session total |
| codex | `logs/runner-out.log` | `{"method":"thread/tokenUsage/updated","params":{"threadId":…,"tokenUsage":{"total":{…}}}}` | `inputTokens` / `outputTokens` / `totalTokens` | **per thread**, cumulative |
| claude-code | — | none observed in either file | — | — |

Observed, not assumed: a cursor run log carries exactly one `token:usage` (total 895,454); a codex run carries 177–273 `thread/tokenUsage/updated` spread over 6–7 threads. On codex the values are **cumulative per thread**, which is what licenses "take the last event per `threadId`, then sum" — established by checking monotonicity across 150 events / 13 threads (zero violations), not by reading the word "updated" in the method name.

Two consequences of the per-thread shape:

- **Do not filter to a "main agent" thread.** Under codex the answer worker is a *child* thread, so a main-thread-only total omits precisely the part the benchmark is measuring.
- **Attribution is free.** Label each thread by the first `userMessage` sent to it and the answer worker's cost separates cleanly from the orchestrator's and from the receipt subagents'. Match on the prompt's role sentence in **whichever language the prompt is written in** — an English-only substring silently drops a Chinese-prompted worker into "other", where it reads as zero rather than as unmatched.

**Do not hand-roll the extraction. Run the script.**

```bash
# Known path first; search only as a fallback — and NEVER with -xdev.
LOG_PATH=/root/sdma/out_files/logs/runner-out.log
[ -s "$LOG_PATH" ] || LOG_PATH=$(find / -maxdepth 6 -name 'runner-out.log' -size +1k 2>/dev/null |
                                 xargs -r ls -S 2>/dev/null | head -1)
printf 'LOG_PATH=%s\n' "${LOG_PATH:-<none>}"
cd "$BENCH_SKILL_DIR" && python3 scripts/collect_runner_tokens.py --log "${LOG_PATH:-/nonexistent}"
# 🔴 这个脚本【永远 exit 0】——成败全在 err= 里，退出码不携带任何判断。
# 所以不要给它接 `|| echo failed` 之类：那个分支永远不会触发，写了只会让人以为有兜底。
# 唯一的读法是读它那一行的 err=。
```

🔴 **Never put `-xdev` on that find.** It stops at filesystem boundaries, and the log lives under a path that is a separate mount on some hosts — so the search returns nothing while the file sits right there. The failure is intermittent *by construction*: it depends on the box's mount layout, not on anything about this run, which makes it read as flakiness rather than as a wrong flag. It has already cost one collection — `err=log_not_found` on a run whose log was present the whole time.

Two more details in that snippet, both load-bearing:

- **`-size +1k` and `ls -S`** — a search can match more than one `runner-out.log` (a stale copy, another run's). `head -1` over unsorted output takes an arbitrary one; taking the largest takes the live one.
- **`${LOG_PATH:-/nonexistent}`** — never pass an empty `--log`. An empty path and a missing file must both surface as `log_not_found`, not as some other silent failure.

Its stdout is exactly one line — **return it verbatim** as the first line of a `logtoken-receipt` subagent result:

```text
LOGTOK file=… bytes=… events=N threads=N total=N answer=N in=N out=N dur=N with=T/D without=T/D rt=… err=…
```

🔴 **Why a script and not a grep you compose yourself:** the agent-authored one-liner version of this failed in production. A quoting error made the extraction return nothing, and the receipt had no field for "my command broke" — so it reported `events=0`, which the reading rule below then interpreted as "this runtime logs no usage." The log at that moment provably held 158 events. **An error and a legitimate zero rendered identically**, which is the single failure mode this whole receipt exists to prevent. The script gives every failure its own `err=` value; a hand-written pipeline cannot.

`with=` / `without=` are **per-arm** `total_tokens/duration_ms`, read off each answer worker's own thread and attributed by the configuration named in its prompt. They are what makes **both arms in one session** workable: the two-run split existed only because a Cursor subagent reported no usage, so pricing an arm required giving it a session of its own. Per-thread accounting removes that constraint — one session, two workers, two priced arms, **one report**. An arm with no matching thread is `none`, never `0`.

`in=` / `out=` / `dur=` are the **same thread's** components as whatever `answer=` reports — `dur=` is that thread's elapsed ms from the runtime's own `turn/completed`, which is the authoritative answer time and should be preferred over any stopwatch the agent holds. Carry all three, because the completion callback has fields for all three and **filling a field with `0` when you did not measure it is worse than leaving it empty** — `0` reads as "ran and cost nothing". Where a value is genuinely absent the script emits `none`; let that become null downstream, never zero.

**How to read it — `err=` first, always.** Every other field is meaningless until `err=none`:

| `err=` | means | do |
|---|---|---|
| `none` | collected | use the numbers |
| `log_not_found` | no such path in the sandbox | **not self-reportable here** — a real finding, say it plainly and let the number be collected outside |
| `read_failed:…` | the file exists but could not be read | retry once, then report as unmeasured |
| `no_known_event_shape` | file read, no runtime's event name present | **check the table above before believing it** — a wrong event name looks exactly like this |
| `shape_matched_but_no_parsable_events` | right runtime, nothing parsed | read again after the answer worker finishes; the log is written as the run proceeds |
| `no_answer_worker_thread_matched` | session total collected, per-arm not attributable | report the **session total** and say so in `summary` — do not pass it off as the answer cost, they differ several-fold |

**`events=0` is never a verdict on its own.** It is produced by a broken command, a wrong event name, a read taken too early, and a runtime that genuinely logs nothing — four different facts that used to render identically. That is why `err=` exists; read it first.

With `err=none`, route each number to the thing it actually measures:

| goes to | value | why that one |
|---|---|---|
| `write_timing.py --total-tokens` for the **with_docs** run-dir | the `T` of `with=T/D` | that run-dir prices **one arm** |
| `write_timing.py --total-tokens` for the **without_docs** run-dir | the `T` of `without=T/D` | same, the other arm |
| callback `input_tokens` / `output_tokens` / `total_tokens` | `in` / `out` / `answer` | the callback prices the **run**, both arms together |

🔴 **Never pass `answer` to a run-dir.** `answer` is `with` + `without` — the two arms summed. Give it to one arm and that arm is inflated; give it to both and **both arms report the same number, so the cost delta becomes exactly zero** — the single most load-bearing output of this benchmark, silently flattened. It renders as "docs made no difference to cost", which is a sentence somebody will repeat in a meeting. Check the arithmetic on any real receipt and it is plain: `247820 + 578426 = 826246`.

Set `token_source=runner_event_log`. Where an arm has no matching thread the collector emits `none`; let that stay null — never 0.

And as everywhere else here: never invent a number to make the line look complete. A guessed token count is worse than a missing one, because it reads as a measurement.

### Token collection flow — Claude Code

Claude Code subagents return a `<usage>` block with `total_tokens`, `duration_ms`, `tool_uses`. This is the primary source. Local JSONL is the fallback.

```bash
# 1. Record start time
start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# 2. Launch subagent and wait for result (captures <usage> block)...

# 3. Record end time
end_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# 4. (Fallback) Collect from local JSONL if <usage> is missing.
#    Use --claude-jsonl for exact subagent file, or --claude-agent-id.
python3 scripts/collect_local_usage.py \
  --start-time "$start_time" --end-time "$end_time" \
  --claude-jsonl <path/to/subagents/agent-xxx.jsonl> \
  --output <run-dir>/local_usage.json

# 5. Write timing.json (<usage> takes priority; local collection as fallback)
python3 scripts/write_timing.py \
  --run-dir <run-dir> \
  --total-tokens <usage.total_tokens> \
  --duration-ms <usage.duration_ms> \
  --fallback-duration-ms <parent_wall_clock_ms> \
  --tool-uses <usage.tool_uses> \
  --local-usage-json <run-dir>/local_usage.json \
  --docs-bundle <workspace>/docs_bundles/eval-<eval_id>.md \
  --granularity session_batch \
  --allocation-count <questions_in_batch>
```

### Token collection flow — Cursor

Do NOT use Cursor UI Subagent tool for benchmark token tracking — it does not return usage data and Cursor does not write hooks events for subagent runs.

Instead, use `cursor-agent` CLI to run each batch as an independent CLI session. Each invocation returns structured JSON with `usage` (inputTokens, outputTokens, cacheReadTokens) and a `session_id`, natively scoped to that run.

```bash
# 1. Run one batch via cursor-agent CLI (e.g. without_docs)
cursor-agent --print --output-format json --mode ask --trust \
  --workspace "<code_only_worktree>" \
  "<prompt with questions for this batch>" \
  > <workspace>/cursor_agent_output_<configuration>_<batch>.json

# 2. The JSON output contains usage:
#    {
#      "session_id": "...",
#      "usage": {
#        "inputTokens": 14677,
#        "outputTokens": 92,
#        "cacheReadTokens": 5928,
#        "cacheWriteTokens": 0
#      }
#    }

# 3. Write timing.json using the cursor-agent output
python3 scripts/write_timing.py \
  --run-dir <run-dir> \
  --total-tokens 0 \
  --fallback-duration-ms <parent_wall_clock_ms> \
  --cursor-agent-json <workspace>/cursor_agent_output_<configuration>_<batch>.json \
  --docs-bundle <workspace>/docs_bundles/eval-<eval_id>.md \
  --granularity session_batch \
  --allocation-count <questions_in_batch>
```

Key constraints for Cursor:
- Use `cursor-agent --print --output-format json` for each batch, not Cursor UI Subagent.
- `without_docs` → `--workspace` points to code-only worktree.
- `with_docs` → `--workspace` points to worktree with docs, and prompt includes canonical docs bundle path.
- Run batches sequentially. Each `cursor-agent` invocation is an isolated session.
- Parse the answer from the JSON output and write it to `<run-dir>/outputs/answer.md` as usual.

### Supported ID-based filters in `collect_local_usage.py`

`collect_local_usage.py` parses Claude Code JSONL files only. For Cursor, use `cursor-agent --print --output-format json` instead.

| Flag | Matches on |
|------|------------|
| `--claude-jsonl <path>` | Exact JSONL file (subagent or session) |
| `--claude-session-id <id>` | `sessionId` field or JSONL filename stem |
| `--claude-agent-id <id>` | `agentId` field or `agent-*.jsonl` filename |

All ID flags are repeatable and comma-separated.

### timing.json schema

```json
{
  "total_tokens": 39728,
  "duration_ms": 37301,
  "total_duration_seconds": 37.301,
  "tool_uses": 7,
  "granularity": "session_batch",
  "batch_id": "batch-1",
  "batch_index": 0,
  "batch_size": 5,
  "batch_question_count": 2,
  "allocation_strategy": "even",
  "allocation_count": 2,
  "source_total_tokens": 79455,
  "source_duration_ms": 74602,
  "usage_duration_ms": 74602,
  "fallback_duration_ms": 0,
  "duration_source": "subagent_usage",
  "source_tool_uses": 14,
  "token_source": "subagent_usage",
  "docs_bundle_hash": "",
  "docs_bundle_chars": 0,
  "estimated_docs_tokens": 0,
  "docs_token_estimate_method": "",
  "local_usage": {
    "input_tokens": 30000,
    "output_tokens": 5000,
    "cached_input_tokens": 40000,
    "cache_creation_input_tokens": 1200,
    "reasoning_output_tokens": 4455,
    "estimated_cost_usd": 0.0842,
    "entry_count": 8,
    "collection_method": "claude_code_jsonl",
    "source_file": "local_usage.json"
  }
}
```

Rules:
- `total_tokens` comes from `<usage>.total_tokens` when available; otherwise from local collection; otherwise 0.
- `duration_ms` comes from `<usage>.duration_ms` when available. If missing or 0, use `--fallback-duration-ms` (parent wall-clock); set `duration_source` accordingly.
- `token_source` indicates provenance: `subagent_usage`, `local_collection`, or `missing`.
- `local_usage` provides a detailed breakdown when local collection succeeded. `estimated_cost_usd` uses Anthropic per-model pricing (input 1x, cached_read 0.1x, cached_write 1.25x, output 5x).
- If token/tool fields are unavailable, write 0 — do not guess. Duration should use parent wall-clock fallback when available.
- The worker/subagent itself cannot write these values; the parent orchestrator must write them after receiving the Agent result.
- For `session_batch`, amortize per-question and preserve source batch totals in `source_*` fields.
- For multi-batch `with_docs` runs, deduplicate repeated docs bundles by SHA-256 hash. Show deduped value as `Normalized Tokens (est.)`.
- Batch metadata is for debugging only. Do not expose in user-facing summaries.
- Do not compare `session_batch` and `cold_start_per_question` metrics in the same run summary.

For `with_docs`, also write the canonical docs bundle that was given to the worker:

```text
<workspace>/eval-<eval_id>-<question_id>/with_docs/run-1/outputs/docs_bundle.md
```

11. After all answers are written, run grading only:

```bash
cd .claude/skills/kb-docs-benchmark
python3 scripts/grade_existing_answers.py \
  --evals /abs/path/to/repo-root/path/to/module-root/docs/evals/evals.json \
  --workspace /tmp/kb-docs-benchmark-<doc-root-name> \
  --base-dir /abs/path/to/repo-root \
  --configurations without_docs,with_docs \
  --run-number 1 \
  --granularity session_batch
```

If any expected `answer.md` is missing, grading fails by default and does not publish a partial `benchmark.json`. Use `--allow-partial` only when the user explicitly wants an incomplete diagnostic report.

12. Generate and open the HTML review page:

```bash
python3 eval-viewer/generate_review.py \
  /tmp/kb-docs-benchmark-<doc-root-name> \
  --skill-name kb-docs-benchmark \
  --benchmark /tmp/kb-docs-benchmark-<doc-root-name>/benchmark.json \
  --static /tmp/kb-docs-benchmark-<doc-root-name>/review.html
open /tmp/kb-docs-benchmark-<doc-root-name>/review.html
```

13. Run Docs Quality Analysis Mode (below) to generate documentation improvement suggestions. This is a default step, not optional.
14. Report `benchmark.md`, `review.html`, `isolation_manifest.json`, and the workspace path. Summarize the highest-priority docs quality suggestions and ask the user whether they want to apply the improvements. Do not modify docs automatically.
15. Report run telemetry (default step, never blocks the run):

```bash
cd .claude/skills/kb-docs-benchmark
python3 scripts/report_telemetry.py \
  --workspace /tmp/kb-docs-benchmark-<doc-root-name> \
  --repo-root /abs/path/to/repo-root \
  --doc-root path/to/module-root \
  --agent <the runtime that actually ran the workers> \
  --isolation <process|subagent>
```

- `--doc-root` is the repo-relative docs root — the same path convention as KB recall tagging, so the row joins with coverage/recall data on `kb_module`.
- `--agent` is **the runtime that actually executed the answer workers this run** — `claude-code`, `cursor-agent`, `codex`, whatever it was. 🔴 Do not copy the example: this field is free text, nothing validates it, and a stale value mislabels every row it produces with no way for a reader to notice.
- `--isolation` is the boundary the two arms ran under: `process` for the CLI path (each arm its own process and `--workspace`), `subagent` for *Agent-native subagent mode* (one thread and one worktree per arm). Omitting it reports `unknown` and prints a warning — the row still lands, but nobody can tell from it whether the numbers are comparable to the rest.
- The executor model is read from `benchmark.json` (`metadata.executor_model`); pass `--model` only to override.
- Pass `--platform Android` or `--platform iOS` when the repo root name does not make it obvious.
- The script reads `<workspace>/benchmark.json`, sends ONE summary entry (question count, with/without pass rates, token usage, duration, model, agent, isolation), and always exits 0 — failures print a warning and never invalidate benchmark results. Use `--dry-run` to inspect the payload.
- **A metric it could not read is omitted, never sent as `0`.** Missing token/duration/question counts leave their keys out entirely, so the dashboard shows a gap rather than a plausible-looking zero. Two arms whose pass rates are missing refuse the whole report — a delta against a baseline that was never measured is not `0`, it is a fabricated `0`.
- Auth: the script ships the shared default metrics ingest token (same convention as tmb-cli and ai-sde MetricsReporter). Override order: `--token` > `AISDE_METRICS_TOKEN` env var > `~/.adk-mobile-mcp/metrics-token` file > built-in default.

This mode preserves question/config isolation through subagents. Do not run model-calling Python scripts as part of this skill; only run grading, timing, and viewer scripts after subagent answers have been written.

## Docs Quality Analysis Mode

Use this mode after `benchmark.json` has been generated. It explains why the docs helped or failed to help and suggests concrete improvements to the docs root.

1. Launch one analysis subagent. Provide:
   - `benchmark.json`
   - `evals.json`
   - docs bundle paths
   - all available `answer.md`, `grading.json`, and `run_manifest.json` files for `with_docs` and `without_docs`
   - the output contract in `agents/docs_quality_analyzer.md`
2. The analysis worker may inspect the same repository/code access used by answer workers and may read the docs bundle. It should not rerun the benchmark. It must write summary/problem/evidence/recommendation prose in **Chinese** while preserving category IDs and code symbols **verbatim** — the suggestions surface on a result card read by the docs' owners, and a translation step at decision time is a step that does not happen.
3. The worker must write or return this JSON shape:

```json
{
  "summary": "Short explanation of current docs quality.",
  "overall_recommendation": "先补 workflow.md 的 adapter 交接（q1 就栽在这），其余是同一处措辞问题，可以一起改掉。",
  "suggestions": [
    {
      "priority": "high",
      "category": "coverage_gap",
      "question_id": "q1",
      "doc_paths": ["docs/workflow.md"],
      "problem": "The docs do not describe the adapter handoff.",
      "evidence": "with_docs failed assertion mentions_manager_adapter.",
      "recommendation": "Add the manager adapter handoff and owning class to docs/workflow.md.",
      "expected_impact": "Should improve q1 with_docs correctness."
    }
  ]
}
```

Allowed categories:
- `coverage_gap`: `with_docs` still fails because the docs do not cover the behavior.
- `redundant_docs`: `without_docs` already passes consistently, so docs add little signal for this question.
- `misleading_docs`: `with_docs` performs worse than `without_docs`, suggesting stale or confusing docs.
- `navigation_gap`: `with_docs` is correct but materially slower or more token-heavy, suggesting poor docs navigation.
- `stale_or_inconsistent`: docs conflict with code evidence.
- `eval_issue`: the eval assertion is low quality or measures the wrong thing.

4. Save the outputs:

```text
<workspace>/docs_quality_suggestions.json
<workspace>/docs_quality_suggestions.md
```

5. Re-run local aggregation and viewer generation so the suggestions are embedded in `benchmark.json`, `benchmark.md`, and `review.html`.
6. After presenting the report, ask the user whether to apply the suggested docs improvements. Treat docs optimization as a separate user-approved step, not part of the benchmark run.

## Output artifacts

Per question and configuration:

```text
<workspace>/
└── eval-<id>-<question_id>/
    ├── eval_metadata.json
    ├── without_docs/
    │   └── run-<n>/
    │       ├── outputs/
    │       │   ├── question.md
    │       │   ├── prompt.md
    │       │   ├── answer.md
    │       │   └── missing_docs.json
    │       ├── grading.json
    │       ├── timing.json
    │       └── run_manifest.json
    └── with_docs/
        └── run-<n>/
            ├── outputs/
            │   ├── question.md
            │   ├── prompt.md
            │   ├── answer.md
            │   ├── docs_bundle.md
            │   └── missing_docs.json
            ├── grading.json
            ├── timing.json
            └── run_manifest.json
```

Workspace-level outputs:
- `benchmark.json`: viewer-compatible aggregated benchmark
- `benchmark.md`: human-readable summary
- `isolation_manifest.json`: code-only workspace preparation details for `without_docs`
- `docs_quality_suggestions.json`: structured doc-quality suggestions when Docs Quality Analysis Mode is run
- `docs_quality_suggestions.md`: human-readable doc-quality suggestions when Docs Quality Analysis Mode is run
- `review.html`: static review UI

## Viewer review

Render the benchmark with the existing viewer:

```bash
python3 eval-viewer/generate_review.py \
  /tmp/kb-docs-benchmark-real \
  --skill-name "kb-docs-benchmark" \
  --benchmark /tmp/kb-docs-benchmark-real/benchmark.json \
  --static /tmp/kb-docs-benchmark-real/review.html
```

In the viewer, confirm:
- outputs load by question, configuration, and run
- benchmark data groups under `with_docs` and `without_docs`
- pass rate, time, and tokens render correctly
- eval labels come from `eval_name`

## Notes for editing or extending the benchmark

- Prefer additive updates to the subagent orchestration, grading, aggregation, and viewer flow.
- Do not redesign the system when a naming normalization or metadata addition is enough.
- Keep `benchmark.json` viewer-compatible.
- If you need schema details, use `references/schemas.md`.
