---
name: kb-update-docs
description: Use when existing module docs (CLAUDE.md / workflow.md / domain.md / rule.md) have outdated or wrong info; apply minimal, evidence-based, format-preserving edits. Evidence is code structure plus mined agent conversations, with local SDD traces preferred by default. Default trace source is local Claude Code / Cursor history; pass `--trace-source find-sdd-trace` or `--use-find-sdd-trace` to mine a remote Fornax trace located from an MR through find-sdd-trace.
allowed-tools: Bash(python3 *kb_tool.py*), Bash(python3 *conversation_miner.py*), Bash(codebase mr diff*), Bash(codebase mr view*), Bash(git cat-file*), Bash(fornax-cli trace list*), Bash(python3 *pick_complete_trace.py*), Read, Edit, Agent, AskUserQuestion
---

> **Working directory (critical):** `kb_tool.py` detects the repository root from the **current working directory**. Run every `kb_tool.py` command from inside the **target repository checkout** (`cd` there first), or pass `--repo-root <repo_checkout>` explicitly — never rely on the skill directory as cwd: the repo root then resolves to the skill's own repo and every changed path is misreported as `uncovered` (false no-op). Both scripts are standalone (stdlib only); invoke them by absolute path. Below, `<skill_dir>` means the directory containing this SKILL.md.

## Mission
Update existing module documentation to match the latest code. Two categories, both mandatory
(they are the Value bar's (a) and (b) below): **fix what this change made stale**, AND
**register the durable knowledge this change introduced**. Do not add speculative content.

⚠ Both directions cost something, and neither reading is safe:
- "Only update outdated information" drops category (b) entirely — the run fixes a few stale
  names while the pitfall the change introduced goes unrecorded, because every operating
  instruction it read said "only update outdated".
- "Register everything this change touched" is the mirror failure — the trivial hunks that rode
  along (a copy tweak, a log string, a spacing bump) get entries nobody will ever need, and the
  doc rots faster than it helps. The Value bar's per-hunk worthiness test is what separates
  them; it is not optional in either direction.

Target: $ARGUMENTS

Before updating `docs/rule.md`, read and follow the shared rule contract:

- `../kb-docs-validator/references/kb-rule-quality-contract.md`

Before restructuring any doc, read the shared structure templates (also used by kb-init-docs):

- `../kb-init-docs/templates/kb-doc-templates.md` (global contract: length budgets are pure
  upper bounds — never pad to a floor; spell out code symbols in full, no `{A,B}` brace
  abbreviations; when removing/rewriting a diagram, preserve every class/method name from it
  in the text version; no empty "TBD" table rows. A plain outdated-fact fix does NOT by itself
  require migrating an old doc to the template structure; structural migration is a separate,
  triggered action — see "Value-Aware Migration" below.)

## Use Scenarios

`$ARGUMENTS` format:
- Optional mode flag: `--ci` (non-interactive; see Modes).
- **Evals are refreshed in the same run, by default.** When this run updates a doc root's
  docs, it also updates that root's `docs/evals/evals.json` — see the two evals gates below.
  Rationale: docs and evals describe the same knowledge; letting them drift apart is what
  produces a fake-green benchmark (the suite passes while testing questions the docs no
  longer answer, or missing the ones they now do). The cascade makes this acute — it
  benchmarks the updated docs minutes later — but the drift is not cascade-specific.
- **Kill switch: `--no-evals-write`** — degrade **all three** evals gates (freshness /
  coverage / bootstrap) to report-only (`candidates` / `propose`), exactly the
  pre-2026-08-24 behavior. Keep this reachable: the orchestration prompt is fetched at
  runtime, so stopping evals writes never needs a deploy or a revert. It **overrides**
  `--evals-bootstrap-write` — a kill switch a feature flag can defeat is not a kill switch.
- **`--evals-bootstrap-write`** — opt IN to the bootstrap gate's write (creating a suite
  where none existed). **Off by default**, unlike the other two gates: they edit a file
  somebody already chose to keep, this one creates one in a root that never had it, and
  those roots are the majority. The caller decides; the skill never infers it.
- Optional trace-source flags:
  - `--trace-source local` (default): mine local Claude Code / Cursor SDD traces.
  - `--trace-source find-sdd-trace` or `--use-find-sdd-trace`: mine a remote Fornax trace through the sibling `find-sdd-trace` workflow.
- The change set, given one of two ways:
  - **`--mr <mr_url_or_number>`** (preferred) plus, when the MR value is numeric, `--repo <repo_path>`: the skill reads the MR's changed files with `codebase mr diff`. This is the single entry point for both local debugging and cloud auto-update, so they run identically.
  - one or more **explicit paths** (the changed files / dirs / docs), for when there is no MR — accepted both positionally (`/kb-update-docs a b`) and after `--path` (`/kb-update-docs --path a b`); when invoking `kb_tool.py`, always pass them via `--path`.
- `--mr` does double duty: it supplies the changed-file set, and in `--trace-source find-sdd-trace` mode it also locates the Fornax trace.

The change set drives an automatic, bounded resolution of which docs to touch — you never point at doc roots by hand. `kb_tool.py plan-doc-update` (see below) groups the changes and returns, per group, `leaves` and an `umbrella`, plus a shared `review_higher` list and an `uncovered` list. Act on them as:
- **`leaves`** — doc roots that actually contain code changes → **update** them (they are the modules whose code changed).
- **`umbrella`** — the group's nearest common-ancestor doc root → **review**: edit only if the child changes made its overview/contract outdated (may be null, or equal to a leaf).
- **`review_higher`** — ancestor doc roots above the umbrellas, up to but excluding the repo root (this includes an iOS pod root such as `TikTokSocial`) → **review with a rising bar**: edit only if the change materially affects that level's architecture / public surface. Usually a no-op; never rewrite a high-level doc just because one leaf changed.
- **`uncovered`** — changed paths with no doc root below the repo root → do **not** update anything; report them (they are candidates for `kb-init`, not for update).
- Unchanged sibling modules under an umbrella are left untouched. The repo-root doc is never updated or reviewed.

Whatever the plan says, the **only** files you may ever create or write are the 7 allowed basenames (see Update Rules). This is enforced deterministically by the `enforce-writeset` gate, which reverts any out-of-domain edit this run made.

Boundaries are detected structurally: the repo root is the `.git` directory; an iOS pod root is a directory holding a `*.podspec` (sample-app / test / template podspecs under `Example` / `Tests` / `template` segments are ignored). Conversation mining runs **once** for the whole invocation.

Modes:
- Default: interactive — may confirm mined knowledge or resolve ambiguity via AskUserQuestion.
- `--ci` (non-interactive / CI mode): no user interaction (no AskUserQuestion); emit a concise, machine-friendly summary (groups, edited roots, edited files, reviewed-but-unchanged files per doc root, uncovered, the `evals_gate:` line — see "Evals freshness gate" — the `evals_add:` line — see "Evals coverage gate" — and any files the `enforce-writeset` gate reverted). When the run is a no-op (no doc file was edited), the summary MUST also carry a machine-readable line `no_op_reason: covered_unchanged|uncovered`, taken verbatim from the planner's `no_op_reason_hint` (see "Resolve the Update Plan") so the distillation flow can carry it into the callback. Use for cloud / automated runs. The gate MUST run in `--ci` exactly as locally.
- Trace source default is always local. Do not call Fornax / `find-sdd-trace` unless the user explicitly passes `--trace-source find-sdd-trace` or `--use-find-sdd-trace`.
- In `find-sdd-trace` mode, if an MR link / number or repo cannot be determined: in interactive mode, ask for the missing input; in `--ci` mode, exit immediately with a machine-readable error (never ask). Neither mode falls back to local trace mining.

## Examples

```bash
# preferred: feed an MR; the skill reads its diff and auto-resolves the docs to touch
/kb-update-docs --mr https://code.byted.org/ugc/TikTok/merge_requests/279608
/kb-update-docs --mr 279608 --repo ugc/TikTok
/kb-update-docs --ci --mr 271226 --repo ugc-android/TikTok
# or pass the changed paths explicitly (no MR)
/kb-update-docs path_a/Foo.swift path_b/Bar.swift
/kb-update-docs --ci --path path_a path_b
# additionally mine the MR's SDD trace as extra evidence
/kb-update-docs --trace-source find-sdd-trace --mr 279639 --repo ugc/TikTok
```


## Resolve the Update Plan (no writes)

If `--mr` was given, first read the MR's changed files:

!codebase mr diff -N <mr_number> -R <repo> --name-only

From the JSON, take each `Files[].Path` whose `ChangeType` is not `"deleted"` (treat `"renamed"` / `"copied"` as the new `Path`). If explicit paths were given instead, use those as the change set.

Then resolve the grouped, bounded plan in one call, **run from inside the target repo checkout** (or with `--repo-root`):

!python3 "<skill_dir>/scripts/kb_tool.py" plan-doc-update --repo-root "<repo_checkout>" --path "<changed_1>" ["<changed_2>" ...]

It prints JSON:
`{"groups": [{"umbrella": <root|null>, "leaves": [<root>...], "changed": [<file>...]}], "evals_roots": [<root>...], "review_higher": [<root>...], "uncovered": [<path>...], "no_op_reason_hint": "covered_unchanged"|"uncovered"}`

`evals_roots` lists the plan roots (leaves, umbrellas and `review_higher` ancestors) that already ship an evals suite (`docs/evals/evals.json`) — informational scope for the evals freshness gate below; the gate itself does NOT depend on it.

`no_op_reason_hint` classifies a no-op outcome for the callback: `uncovered` when at least one changed path resolved to no doc root (the `uncovered` bucket is non-empty), else `covered_unchanged`. It applies to any no-op outcome — whether `groups` was empty, or the grouped roots were reviewed and left unchanged.

If `groups` is empty: stop and report no edits. **In `--ci` mode, whenever the overall run is a no-op — no doc file was edited, whether because `groups` was empty OR because the grouped roots were reviewed and left unchanged — the summary MUST include the machine-readable line `no_op_reason: <no_op_reason_hint>`** (use the planner's `no_op_reason_hint` value verbatim). `uncovered` paths are `kb-init` candidates (no docs cover them) — do not edit files; report them.

If the tool exits with a `none of the target path(s) exist under the resolved repo root` error, the repo root is wrong (wrong cwd / wrong `--repo-root`) — fix it and retry. Never report that error as `uncovered` or as a no-op.

### Evals freshness gate — evals-update v1 (read-only, zero-model)

A code change can silently stale a module's evals suite (`docs/evals/evals.json`) — docs get updated, evals keep asserting symbols the code no longer has (a fake-green benchmark). The static gate detects this. It makes NO writes, is cheap (zero-model, a few git calls), and runs in BOTH default and `--ci` mode **whenever a real git range exists — unconditionally, NOT gated on the plan's `evals_roots`** (the gate walks ancestors itself and can find suites the plan list does not carry, e.g. above a pod ceiling). Its outcome is always reported as a machine-readable `evals_gate:` line in the run summary — exactly one of the values defined below, never silently omitted, never an improvised value.

The gate needs a real git range, so it only runs when the change set came from `--mr` and the MR is merged:

1. Resolve the MR's merge commit: `codebase mr view -N <mr> -R <repo> -v` → `MergeCommitId` (call it `M`) and `MergeMethod`.
   - Explicit-paths invocation (no MR) → report `evals_gate: skipped_no_range`.
   - `MergeCommitId` empty (MR not merged yet) → report `evals_gate: skipped_not_merged`.
   - Range not resolvable in the local checkout — check BOTH ends: `git cat-file -t "<M>"` AND `git cat-file -t "<M>^1"` (a depth-1 shallow clone resolves `M` but not `M^1`) → on either failing, report `evals_gate: skipped_unresolvable_range`.
   - `MergeMethod` is `merge_commit` or squash → the MR's diff is `M^1..M`. A fast-forward merge method (no merge/squash commit; `M` = the source branch tip) would make `M^1..M` cover only the MR's LAST commit — in that case use `--base "<M>~<CommitsCount>"` (both fields come from the same `mr view` output).
2. Run (same cwd / `--repo-root` discipline as every other `kb_tool.py` call):

!python3 "<skill_dir>/scripts/kb_tool.py" eval-gate --repo-root "<repo_checkout>" --base "<M>^1" --head "<M>"

It prints JSON: `{"base", "head", "changed_file_count", "checked_roots": [...], "unreadable_evals": [...], "candidates": [{"root", "hit_symbols", "changed_files"}...]}`. A candidate is a root whose evals assert a code symbol (symbol-shaped `contains` assertions only — natural-language phrases are filtered) that this MR's diff touched on an added or removed line (word-boundary match). Evals suites are probed and read **at the `head` ref, not from the worktree**, so a stale checkout cannot skew the result. The gate fails loudly on a bad ref / non-git checkout — treat that like the wrong-repo-root error above (fix and retry), never as "no candidates". A non-empty `unreadable_evals` (a suite exists at head but failed to parse) must be surfaced in the summary — a broken suite is invisible to the gate on every future MR until fixed.

3. Act on the outcome (v1 = keep-fresh only; never create evals where absent):
   - `candidates` empty → report `evals_gate: no_candidates`. No evals action.
   - `candidates` non-empty → report `evals_gate: candidates <JSON array of {"root","hit_symbols"} objects, verbatim from the tool output>` (JSON, not space-joined — root paths may contain spaces). This is a **proposal for a separate evals-refresh flow, not an instruction to edit evals in this run**:
     - **Never touch `evals.json` in this run.** Evals are not in the 7 allowed basenames; the write-domain gate reverts any such edit. Evals changes ship in a SEPARATE branch/MR — never auto-merged, mandatory human review (evals are benchmark ground truth; a wrong "fix" is worse than a stale entry).
     - The follow-up evals MR must **patch, not regenerate**: touch only the eval entries whose asserted symbols hit; leave every other entry byte-identical. Per edited entry it must state which hit symbol and which MR change motivated the edit, and it must pass the discrimination gate for that root — the refreshed evals pass against the post-MR code, and the stale entries it replaced fail — before human review.
   - The gate is a recall-oriented pre-filter: an over-flag costs one human review, a miss ships a fake-green eval. Do not second-guess a candidate away without running the discrimination evidence.

4. **Refresh the stale entries in THIS run** (default; `--no-evals-write` degrades to step 3's report-only outcome). Everything above still holds; only the destination of the edit changes. Report `evals_gate: candidates_refreshed <same JSON array>` instead of `candidates`.
   - **Patch, never regenerate.** Touch only the entries whose asserted symbols hit; every other entry stays **byte-identical**. Regenerating a suite silently rewrites questions nobody asked you to change — and evals are benchmark ground truth, so a rewrite launders a fabricated question into the baseline.
   - **Delegate authoring to `kb-evals-creator`** (same single-source-of-truth discipline as the coverage gate below), then validate with `kb-docs-benchmark/scripts/validate_evals.py`.
   - **Discrimination is still mandatory, per edited entry**: the refreshed entry passes against the post-MR code AND the entry it replaced fails. An entry that passes both ways tests nothing — drop the edit and report it rather than ship a question that cannot fail.
   - 🔴 **If any part of this fails — creator unavailable, validator red, discrimination not demonstrated — revert your evals edits and fall back to `evals_gate: candidates`** (the report-only outcome). A half-refreshed suite is worse than a stale one: stale is uniformly old, half-refreshed is *inconsistently* old and no one can tell which entries to trust.

### Evals coverage gate — evals-update v1.5 (add: a question for genuinely new knowledge)

The freshness gate above catches evals that went STALE. Its mirror blind spot: a change adds genuinely NEW behavior to an already-covered root and the distillation updates the docs, but no eval ever tests it — the new knowledge ships untested (`docs updated, evals didn't` is a fake-green just like staleness). The coverage gate decides whether to ADD a question. It writes NOTHING here, the signal step is zero-model, and it reports exactly one machine-readable `evals_add:` line — never silently omitted, never an improvised value. It **reuses the exact `--base`/`--head` the freshness gate already resolved** — `M^1` for a merge/squash merge, `M~<CommitsCount>` for a fast-forward merge (the command below shows the merge-commit form; carry over the base you resolved above, do NOT hardcode `M^1` on an FF-merged MR). If that range was skipped, report the same value on `evals_add:` (`skipped_no_range` / `skipped_not_merged` / `skipped_unresolvable_range`) and stop.

1. Deterministic signal (zero-model) — the new code symbols this MR introduced into an evals-bearing root that no existing eval covers:

!python3 "<skill_dir>/scripts/kb_tool.py" eval-add-signal --repo-root "<repo_checkout>" --base "<M>^1" --head "<M>"

It prints JSON: `{"base","head","checked_roots","unreadable_evals","capped_roots","add_candidates":[{"root","new_symbols","changed_files"}...]}`. `new_symbols` are symbol-shaped tokens on the MR's ADDED lines that are absent from the root's code at base and not already asserted — read at the `head` ref, same hardening as the freshness gate. Surface a non-empty `capped_roots` (umbrella roots on large MRs whose candidate tokens hit the per-root cap; leaf roots carry the precise signal) and `unreadable_evals` in the summary.

2. Docs-updated gate (the REAL trigger — not the raw signal): an add-candidate only matters if THIS distillation run actually updated that root's docs. A new symbol whose knowledge the distillation judged not doc-worthy (it edited no doc for that root) does not deserve an eval either. Intersect `add_candidates[].root` with **every doc root you edited this run** — a `leaf`, an `umbrella`, OR a `review_higher` ancestor (e.g. a pod / aggregate root whose evals suite sits above the leaf). eval-add-signal walks all evals-bearing ancestors and the plan's `evals_roots` is drawn from all three, so restricting the intersection to leaves/umbrella would silently drop a pod-level add-candidate — the exact recall miss this gate exists to prevent.
   - Empty intersection → report `evals_add: signal_only` (new symbols exist but no doc was updated for them) and stop.

3. Agent judgment (is a surviving new symbol worth a question?) — for each root in the intersection, using the UPDATED docs + the MR diff, decide PER symbol whether it is a new public entry / flow node / constraint / registration point worth testing, and NOT a private implementation detail, a refactor rename, a test/telemetry symbol, or a duplicate of an existing question. Record every decision (add / skip + one-line reason) for the evals MR description.
   - Nothing worth a question → report `evals_add: no_new_questions` and stop.
   - At least one → report `evals_add: propose <JSON array of {"root","new_symbols"} objects>` and author.

4. Authoring — **DELEGATE to `kb-evals-creator`** (its SKILL declares itself the single source of truth for evals generation and has `kb-docs-benchmark` delegate to it; follow the same discipline here — do NOT hand-write questions or grow a parallel generator). Follow its "Adding Questions" flow: read the current `evals.json` first, preserve existing questions, continue the ID sequence, honor its quantity budget (add at most 3 per root; keep a suite ≤ 8 active questions), assert the new symbol via its `contains`/`regex` rules (no docs-path leakage), and stamp `provenance {"type":"llm","prompt_source":"kb-evals-creator-mr-add-v1"}` so machine-added questions stay separable from human-authored ones. Validate with `kb-docs-benchmark/scripts/validate_evals.py` (the single validator — kb-evals-creator's SKILL points there too).

5. Guardrails:
   - **Default**: write the questions into the root's `docs/evals/evals.json` in THIS run and report `evals_add: added <same JSON array>`. Same fallback rule as the freshness gate — **anything goes wrong, revert the evals edits and degrade to `propose`**, never ship a partially-authored suite.
   - **`--no-evals-write`**: never write `evals.json` in this run — the write-domain gate reverts it. New questions ship in a SEPARATE evals MR, never auto-merged, mandatory human review. Report `evals_add: propose ...`.
   - **Either way, each new question must pass the discrimination gate for its root**: it passes WITH the updated docs and FAILS code-only (`without_docs`). A question the docs don't help answer is not discriminating — drop it, don't ship it. This one never relaxes — not for the cascade, not for a rushed run; it is the only thing separating "an eval" from "a sentence that happens to be true".

Recall-first, like the freshness gate: the agent judgment and the docs-updated gate are the precision layers, not the signal. Known **over-flag** classes (extra candidates the agent filters — all visible in the tool output, none silent): service-locator-macro symbols; comment-derived Title-case words the base-existence check missed on a small root. Known **under-flag** signal — a non-empty `capped_roots`: that root had more candidate tokens than the base-check cap, so some genuinely-new symbols were dropped from `new_symbols`. Do NOT dismiss it as noise (it is the opposite — a recall gap): treat it as "investigate this root's new symbols manually", and note that the leaf roots below it carry the un-truncated signal.

### Evals bootstrap gate — evals-update v2 (create: a root that has NO suite at all)

The two gates above both find their roots by **evals presence** — the freshness gate walks ancestors that ship a suite, and the coverage gate adds to a suite that exists. So a root with **no** `docs/evals/evals.json` is not rejected, it is **never visited**. That leaves the single most common production shape completely untested: **the docs exist, the evals never did.** The chain then reports `no_evals` and scores nothing, which on a dashboard is indistinguishable from "the benchmark is broken".

🔴 **This is the case, not an edge case.** Most modules have docs and no evals; `kb-init` is the only thing that ever creates a suite, and its MRs are not always merged — so a root can stay evals-less forever while every distillation dutifully updates its docs.

This gate reuses **the exact `--base`/`--head` the freshness gate already resolved**. If that range was skipped, report the same value on `evals_bootstrap:` (`skipped_no_range` / `skipped_not_merged` / `skipped_unresolvable_range`) and stop. It reports exactly one machine-readable `evals_bootstrap:` line — never silently omitted, never an improvised value.

1. Deterministic signal (zero-model). **You pass the roots in** — the tool does not infer them:

!python3 "<skill_dir>/scripts/kb_tool.py" eval-bootstrap-signal --repo-root "<repo_checkout>" --base "<M>^1" --head "<M>" --roots "<comma-separated doc roots you edited THIS run>"

`--roots` is required and must be **every doc root you edited this run** (leaf, umbrella, or `review_higher` ancestor — same set the coverage gate intersects against). The tool deliberately does **not** re-derive "what counts as a doc root": the ancestor walk the other two gates use finds its way by asking "is there an evals suite here?", which is false by construction here. Re-deriving it would put a **second definition of "doc root" in a second place**, and two definitions of the same thing drift — silently, and only on the paths nobody tests.

It prints JSON: `{"base","head","checked_roots","skipped_have_suite","no_new_symbols","unknown_roots","capped_roots","bootstrap_candidates":[{"root","new_symbols","changed_files"}...]}`.
- `skipped_have_suite` — that root already has a suite; it belongs to the two gates above. **Surface it**: "absent from the output" and "deliberately not ours" read the same to a human, and only one of them is a bug.
- `unknown_roots` — a root you named does not exist at `head`. That is a **wrong ref / stale plan**, not "nothing to do". Fix it and retry; never report it as a clean result.
- `capped_roots` / `no_new_symbols` — same meaning as the coverage gate.

2. Docs-updated gate (the REAL trigger): a bootstrap candidate only matters if THIS run actually updated that root's docs. Since you pass `--roots` yourself, this is already true by construction — **do not widen `--roots` to "roots that looked interesting"**, that is how this gate turns into a suite generator for modules nobody distilled.
   - No candidates → report `evals_bootstrap: no_candidates` and stop.

3. Agent judgment — for each candidate root, using the UPDATED docs + the MR diff, decide whether this root's newly-documented knowledge is worth a **starter suite** at all. A root whose entire doc update was a one-line typo fix does not need one. Record every decision (bootstrap / skip + one-line reason) for the MR description.
   - Nothing worth a suite → report `evals_bootstrap: no_new_questions` and stop.
   - At least one → report `evals_bootstrap: propose <JSON array of {"root","new_symbols"} objects>` and author.

4. Authoring — **DELEGATE to `kb-evals-creator`** (the declared single source of truth for evals generation; the same discipline as the other two gates — do NOT hand-write questions or grow a parallel generator). Follow its "New Suite" flow: honor its quantity budget (**start small — 3 questions, never a full 8**; a starter suite is a seed, not a finished benchmark), assert the new symbols via its `contains`/`regex` rules (no docs-path leakage), and stamp `provenance {"type":"llm","prompt_source":"kb-evals-creator-mr-bootstrap-v1"}` so machine-created suites stay separable from human-authored ones. Validate with `kb-docs-benchmark/scripts/validate_evals.py`.

5. Guardrails:
   - 🔴 **Default is REPORT-ONLY — this gate writes nothing unless it is explicitly turned on.** Report `evals_bootstrap: propose <JSON array>` and stop. This is the opposite default from the freshness and coverage gates above, and the asymmetry is deliberate: **those two edit a file that already exists, in a root somebody already chose to cover; this one creates a file that never existed, in a root that never had one** — and roots with no suite are the *majority*, so the blast radius is not comparable. A first suite lands in an author's follow-up MR as a file they have never seen before.
   - **`--evals-bootstrap-write`**: opt in to writing `<root>/docs/evals/evals.json` in THIS run; report `evals_bootstrap: created <same JSON array>`. The write-domain gate admits it via the same `--allow-evals` path-shape rule as the other two gates.
   - **`--no-evals-write`** still wins over it: if both are passed, nothing is written. A kill switch that can be overridden by a feature flag is not a kill switch.
   - **Discrimination is mandatory, per question, and never relaxes**: it passes WITH the updated docs and FAILS code-only (`without_docs`). A question the docs don't help answer is not discriminating — drop it. **This one does not bend for the cascade**: a bootstrapped suite that cannot fail turns every future benchmark on that root permanently, falsely green — strictly worse than the `no_evals` it replaced, because `no_evals` at least announces itself.
   - **Anything goes wrong — creator unavailable, validator red, discrimination not demonstrated — revert the evals file and degrade to `propose`.** Never ship a partial starter suite: with no prior suite to compare against, nobody can tell which questions were vetted.

### Write-domain gate — snapshot BEFORE you edit (mandatory)

Before making the FIRST doc edit, record a git baseline of the target checkout so the post-edit gate only ever judges THIS run's changes (a dirty checkout / pre-existing user edits are recorded as baseline and never touched):

!python3 "<skill_dir>/scripts/kb_tool.py" enforce-writeset --snapshot --repo-root "<repo_checkout>"

**Add `--allow-evals` to BOTH the snapshot and the apply call** (omit it only under `--no-evals-write`). It
admits each touched doc root's own `docs/evals/evals.json` — matched by **path shape**
(`<root>/docs/evals/evals.json`), not by basename, so a stray `evals.json` anywhere else,
or a sibling file in the same directory, is still reverted. Without the flag the gate
reverts your evals edits and the run ends up reporting a refresh it did not keep.

This is mandatory in BOTH default and `--ci` mode. Then make your edits, then run the `--apply` gate at the end (see "Finalize"). Mirror the existing `kb-docs-validator` gate discipline: a guard that did not run is a guard that did not protect anything.

Otherwise:
- For each group, **update** every `leaf` doc root (these have real code changes), then **review** its `umbrella` and edit only if the child changes made it outdated.
- **For every doc root you touch, also run `kb-docs-validator` once** (see "Value-Aware Migration" below). If it reports structural non-conformance, migrate that doc root's docs to the template structure in this same update — in place, any size, language-preserved. This is the one sanctioned structural rewrite; for conforming doc roots, stay with minimal fact-fixes.
- **Within each doc root you touch, review EVERY existing doc file — not just one.** Read and re-check ALL of `CLAUDE.md` and `docs/{workflow,domain,interface,rule,architecture}.md` against the latest code. Registering a new symbol in `interface.md` is **not** a complete update: also fix every now-inaccurate statement elsewhere, in particular —
  - `CLAUDE.md` **Scope / Module Overview / Key Classes** — any description of a type's role, shape, or responsibility that the change has obsoleted;
  - `docs/rule.md` per the rule-quality contract — a rule that constrains behavior the module no longer has (e.g. a rule about a code path that was removed or replaced) is outdated and must be corrected;
  - `docs/domain.md` / `docs/workflow.md` — flows or concepts the change invalidated.
  Do not finish a doc root after editing a single file when other files under it are still stale.
- **Value bar — reviewing every file is mandatory; editing one is not.** Edit a doc file ONLY when at least one of:
  - (a) this MR made a statement in it wrong or stale — must fix; or
  - (b) this MR introduced knowledge a future developer/agent would misuse or fail to find without it — must register.
  Before each edit ask: *would this edit change what a future developer/agent does?* If not, skip it. **Leaving a reviewed file unchanged is the normal, correct outcome for most files.** In the final summary, report per doc root which files were reviewed but left unchanged.
- **A triggered MR means at least one change is worth registering — NOT that every change is; judge worthiness per changed hunk, never per MR.** The distill trigger only guarantees *some* durable knowledge exists in this diff; it never licenses documenting the trivial parts that rode along with it. When an MR mixes a worthy change (a new contract, a behavior change, a renamed public symbol) with trivial ones (a copy tweak, a spacing bump, a log-string edit), register ONLY the worthy hunks and leave the rest undocumented — a worthy hunk elsewhere in the same MR NEVER justifies an entry for a trivial one. This is the additions bar applied change-by-change; it does not weaken the fix mandate below.
- **The value bar limits additions — it never excuses fixes.** Correcting or deleting a statement the MR made wrong or obsolete is category (a) and stays MANDATORY: a stale overview sentence, an obsolete rule, a description of removed behavior MUST be rewritten or removed. Skipping a known-stale statement is NOT a valid "no-edit" outcome. When in doubt between "add a new fact" and "fix a wrong one", the fix always wins.
- **Transient experiment behavior is not durable knowledge — do NOT write a `rule` whose truth depends on which branch of a still-being-decided experiment is currently live.** The hinge is TRANSIENCE, not mere flag presence: only skip a rule that documents the per-branch variant of an experiment still being decided (e.g. "maintain both branches" of an `if (SomeABFlag) { … } else { … }` visual/layout/tuning split, or its per-branch constants like colors, paddings, asset names) — that rule rots the moment the experiment concludes. A **permanent** feature flag / kill-switch / region or config gate is durable operational behavior, and a **concluded** experiment (flag removed, OR default permanently flipped / one branch now dead) is settled knowledge — both MAY be recorded — but recording a concluded experiment means its DURABLE behavior, never the per-branch pixels / paddings / colors it used (those stay excluded by the granular-UI rule below). This is an **additions** limit only — it does not weaken the fix mandate above: if the change made an EXISTING doc statement wrong, still correct it.
- **Granular UI / visual / layout specifics are implementation detail, not durable knowledge — do NOT register them, even outside an experiment.** Icon and image dimensions, color / hex values, corner radii, spacing / padding / inset constants, font sizes, per-widget layout numbers, animation durations, and style-catalog enum inventories (e.g. a `*_style` case list) are read straight off the code when needed and churn on their own cadence; a `rule` / `domain` entry that pins them rots fast and answers a question no future developer/agent brings to the KB. Register the *durable* fact instead — the contract, the state a value gates, the reason it is load-bearing — never the pixel value itself. **Carve-out — a consumed enum is a contract, not a catalog:** a `*_style` / variant enum that OTHER modules `switch` on is a public API surface, not a self-rotting visual catalog — the "churns on its own cadence" test does NOT apply to it; register the contract it exposes (which variants exist as a consumed surface, and who consumes them) without enumerating each case's pixels. The exclusion targets enums whose cases exist only for local rendering. (The transient-experiment rule above is the per-branch case of this; this covers the permanent case too.) Additions limit only: if the change made an EXISTING doc statement about such a value wrong, still correct or delete it. **A constraint that mentions such a value is not itself such a value — see the next bullet.**
- **A constraint is not a pixel — write out the X and the Y.** The exclusion above targets *values*. It does NOT reach a **constraint on future changes**, which is category-(b) knowledge and MUST be registered. **The test is a deliverable, not a possibility:** state, concretely, the X and the Y in "if you do X, Y breaks". **If you cannot write both out, it is not a contract — do not register it.** ("Can it be phrased that way?" is not a test: a possibility bar is always satisfiable by anything.)
  - **X must be a future change someone would really make** — refactoring this view, reusing this component elsewhere, adding another entry point, swapping the base class, turning on the other experiment branch. **X is NOT "revert this MR's hunk".** Every hunk breaks something if you delete it; allowing that X makes this test *wider* than the "is it behavior?" test it replaces.
  - **Y must be a failure a person can see and describe** — "tapping the follow chip sends no new message", "the list jumps back to the top after insert". **NOT** "behavior changes", "renders wrong", "does not match expectations".
  - Passing: "must mirror under RTL", "must keep following the scroll position after insertion", "must be reset before the cell is reused" — each pairs with a real X and a visible Y. Failing: "the icon is 24pt", "the accent color is #FE2C55".
  - **Do NOT use "is it behavior?" as the test** — "the color must be red" is behavior too, and that phrasing is wide enough to swallow the whole exclusion.
  - The X/Y you just wrote out **is** the `WHEN` / `MUST` content of the entry — this test costs nothing extra, its by-product is the entry itself.
  - **A constraint containing a value still excludes the value.** "scroll to the bottom with a 12pt offset after insertion" registers as "must scroll to the bottom after insertion" — the carve-out covers the constraint clause, never the number inside it.
  - **"In the author's own terms" means do not re-interpret** — do not soften, generalize, or invent the reason. It does NOT mean pasting the comment verbatim: the entry still takes the `WHEN` / `MUST` shape the rule-quality contract requires.
- **No pure-format edits.** Never restructure, re-section, or restyle content whose meaning is unchanged. Rewriting an existing, still-accurate bullet list into `WHEN/MUST` sections with equivalent sentences IS a pure-format edit — do not do it. Apply contract formatting only to the specific entries you are already editing for content reasons — this follows from the formatting-stability rules below. **One sanctioned exception:** a touched doc root that meets the "Value-Aware Migration" trigger below is migrated wholesale to the template structure — that is the only place a structural rewrite of unchanged-meaning content is allowed, and only because the validator flagged the doc root as non-conformant.
- **Traceability — every fact you write MUST trace to a changed hunk in THIS MR's diff.** Before adding or expanding an entry, point to the specific added/removed line(s) in this MR that make it true or newly relevant. Do NOT add a standalone block of background about a class, flow, or module this MR did not touch — a debugging guide for an untouched subsystem is the failure mode to kill. A *minimal* orienting clause that makes the changed fact locatable and usable — naming the flow a new gate sits in, the caller a new method serves — stays in scope and is often necessary; what's out of scope is background beyond placing this change, or documenting an untouched area as if this MR introduced it. If the only support for a statement is your own model of the codebase rather than a hunk in this diff, it is out of scope for this run — skip it. The one sanctioned non-diff evidence source is user-confirmed conversation mining (see that section); `scan-types` proves a symbol *exists*, not that this MR *changed* it, so it does not by itself satisfy this bar. This does not weaken the fix mandate — a hunk that invalidates an existing statement still obligates the fix.
- **Review** each `review_higher` root once, with a rising bar — edit only if the change materially affects that level's overview / architecture / public surface; otherwise leave it unchanged.
- For every doc root you do edit, first run the evidence commands (e.g. `scan-types`) and proceed doc-root-by-doc-root, finishing each root before the next.
- Treat groups as independent; never touch unchanged sibling modules, and never touch the repo-root doc.

## Update Rules (strict)
- **Write domain is exactly 7 basenames (CASE-SENSITIVE):** `workflow.md`, `domain.md`, `interface.md`, `rule.md`, `architecture.md`, `CLAUDE.md`, `AGENTS.md`. NEVER create or write ANY other file — not `implementation_map.md` / `key_logic.md` / `danger_zones.md`, not `*.yaml` / `*.json` / `classes.json`, not `CHANGELOG` / `schema_version`, not `README.md` — **even if the target KB already ships such files**. `README.md` is deliberately out of domain. The `enforce-writeset --apply` gate reverts any out-of-domain file this run created or modified; do not rely on it as a safety net — stay in domain by construction.
- Only update directories that already contain `CLAUDE.md` or `docs/{workflow,domain,interface,rule,architecture}.md`.
- Only update existing doc roots — do not create a doc root for a module that has none. **One in-root exception:** Value-Aware Migration (below) may create `docs/architecture.md` when extracting architecture content out of `domain.md` / `CLAUDE.md` (`architecture.md` is one of the 7 write-domain basenames, so the `enforce-writeset` gate allows it) — this is part of an in-place migration of an already-documented doc root, never a brand-new doc root.
- Do not edit any content wrapped by `<nay-ai>...</nay-ai>`; treat it as human-authored and immutable.
- Only edit statements that are outdated according to the latest code structure.
- Do not introduce new "architecture patterns", "principles", or "best practices" unless they already exist in the codebase/docs under this module, or are backed by user-confirmed conversation-mined evidence.
- Keep `CLAUDE.md` structure stable:
  - Keep existing H2 sections; remove H2 section only when the whole section is outdated.
- Keep formatting stable across all docs:
  - Do not reflow paragraphs, rewrap lines, or "clean up" punctuation/whitespace.
  - Do not reorder lists, headings, sections, or files.
  - Do not change code fences, diagram blocks, tables, or indentation unless fixing incorrect content inside them.
  - Preserve the file's trailing final newline: an edit or append at end-of-file must not drop it. Before committing, check the diff for `\ No newline at end of file` on any doc you touched and restore the newline if it appears.
  - Prefer the smallest possible edit that makes the statement accurate.

## Value-Aware Migration (structural non-conformance)

The strict rules above keep ordinary fact-updates minimal. They make ONE controlled
exception: when this change set touches a doc root whose docs do not conform to the current
templates, migrate that doc root's docs to the template structure in the same update — even
though those edits are structural, not fact corrections.

**Trigger — both must hold:**
1. The doc root is one you are already updating or reviewing for this change set — a `leaf`
   (its code changed), or an `umbrella` / `review_higher` you are touching. **Never migrate a
   doc root no code change reached** (don't sweep the whole repo). Migration only ever writes
   the **7 write-domain basenames** (above) and the `enforce-writeset` gate reverts anything
   else — so a migration can restructure the four-piece + `CLAUDE.md` (+ extract
   `architecture.md`) but **never touches a KB's bespoke / extra files** (`implementation_map.md`,
   `*.yaml`, …); a hand-curated KB's non-standard content is therefore safe by construction.
   Whole-root owner-KB protection (skip a maintained KB entirely) is the cloud blacklist's job,
   out of this skill's scope.
2. `kb-docs-validator` reports structural non-conformance for that doc root.

For a `review_higher` root the bar is **higher**: migrate it only when the change *materially
affects that level's architecture / public surface* AND it is non-conformant — otherwise just
report it as a migration candidate. Do not rewrite a high-traffic top-level doc because one
descendant leaf changed.

**Detection = the validator, not surface guesses.** Run the validator on the touched doc
roots and treat its structural findings as the old-template signal:

!python3 "<skill_dir>/../kb-docs-validator/scripts/validate_kb_docs.py" "<doc_root_1>" ["<doc_root_2>" ...]

Findings that mean "migrate": `rule.md` with no `WHEN`/`MUST` scenario blocks, table-based
pseudo rules, rules duplicating an ancestor, misplaced structure/inventory sections,
`domain.md` mixing architecture content, or `CLAUDE.md` not in the canonical
**Module Overview / Key Classes / References** shape. Do **NOT** use the doc's *language* or
the mere *absence of `architecture.md`* as a migration signal — a Chinese doc stays Chinese,
and a thin module legitimately has no `architecture.md`.

**Migration = restructure in place, regardless of size — via update, not regeneration.**
Migrate the touched doc root with `kb-update-docs` itself, because update **transforms the
existing docs**: every human-curated gotcha, rationale, and pitfall is preserved and re-homed
into the new structure. `kb-init` would regenerate from code and **lose** everything the code
can't reproduce.
- **Any size — but large migrations get a hard gate, not just a flag.** A large doc is not a
  reason to defer; a KB update is its own follow-up MR (not mixed into the code MR), so a large
  migration is a large, separately-reviewable doc MR. BUT a full rewrite of a big hand-maintained
  doc is the easiest place to silently drop a gotcha, so "zero info loss" must be *enforced*, not
  just hoped for:
  - **Size gate:** above a meaningful size (roughly the doc's tier budget, e.g. a `rule.md`
    already over its `kb-rule-quality-contract.md` budget, or any doc >~200 lines), in `--ci`
    do **NOT** silently auto-rewrite — downgrade to **report-only** (emit it as a migration
    candidate for human review) instead of applying. Interactive mode may still migrate, but
    flag it **"needs careful human review."**
  - **Symbol-superset check (always, every migration):** the set of class/method/symbol names
    in the migrated doc MUST be a **superset** of the pre-migration set. If any symbol was
    dropped, **revert the migration and report it** rather than ship a lossy rewrite.
- **Structure-only and language-preserving.** Lift the existing content into rule
  `WHEN/MUST` blocks, References-first SSOT, the 3-section `CLAUDE.md`, and **extract
  `architecture.md`** when `domain.md` / `CLAUDE.md` carry architecture / layering /
  dependency content. **Keep the doc's existing language** (never translate zh→en). **Zero
  information loss** — every class/method name, gotcha, and rationale from the old docs must
  survive the migration.

**kb-init regeneration is the narrow fallback, not the default.** Mark a doc root as a
`kb-init` candidate — report it, do **not** regenerate here — only when the existing docs are
not worth preserving (junk / near-empty / wildly wrong) or absent (the `uncovered` case).
Whenever the existing docs hold real curated knowledge, prefer in-place migration.

**Migration is ADDITIVE — never a substitute for the normal update.** A migrated doc root
STILL gets, in the same pass: (a) its stale facts fixed, and (b) the new knowledge this
change introduced registered (the value bar above). Do not let the structural migration crowd
out the fact/knowledge update — the migration restructures, the normal update keeps the
content current. A doc root can be *migrated* AND have *new knowledge registered* AND have
*facts fixed* all at once, and the knowledge from the change usually lands in more than the
one doc you migrated (e.g. a new rule scenario in `rule.md` plus a flow line in `workflow.md`).

**Summary.** Per touched doc root, report the outcome(s) — any combination of: *facts fixed* /
*new knowledge registered* (which docs) / *migrated to template* (with/without `architecture.md`
extraction) / *kb-init candidate*. Mark large migrations **"needs careful human review"**.

## Evidence Requirement

**Comment lines in THIS MR's diff are first-class evidence — read them before concluding a doc
root has nothing to register.** Scope is exactly the added/modified comment lines of this diff
(not "comments in the changed files"): those are as new as the code in the same hunk, they
already satisfy Traceability, and they are usually the highest-confidence knowledge the MR
carries — the author telling a future reader what they must not get wrong. Scan them as a
distinct pass; a `// must mirror under RTL` / `// keep following scroll after insert` note is
exactly the category-(b) knowledge the Value bar mandates, and it needs no conversation trace.

**Register the constraint, not the compliance claim.** A comment states *intent*, and intent is
often something code can neither confirm nor refute — so "trust the code over the comment" does
not resolve it. The usable rule is about **shape**:
- ✅ "X MUST mirror under RTL" — a constraint on future changes. This is what `rule.md` is for,
  and it is exactly the `WHEN` / `MUST` block shape the rule-quality contract already requires.
- ❌ "X is mirrored under RTL" — a statement about current state. That needs code backing, and if
  the comment is the only support, do not write it as fact.

**When a comment and the code in its own hunk plainly contradict each other, register neither —
skip it and flag it for human review.** Silently picking a side ships a confident wrong fact.

**A comment that explains a mechanism is not a third category — route it.** "AWERTL flips the
whole window layer" asserts neither a constraint nor compliance; it explains *why* a constraint
holds. It **never becomes an entry of its own** — as a standalone block it is precisely what
Traceability kills ("background about a class, flow, or module this MR did not touch"). It rides
along **inside** the constraint's entry, as the orienting clause the Traceability rule calls
"often necessary". **Test: delete the mechanism sentence — can the constraint still be acted on?**
Yes ⇒ drop it (background). No ⇒ keep it, in the same entry ("MUST route RTL through AWERTL and
MUST NOT stack a UIKit semantic layer on top — AWERTL already mirrors at the window layer").

⚠ Note the asymmetry with the evals coverage gate below, which filters comment-derived tokens as
over-flag noise: there they are weak evidence that a **symbol** is new; here they are strong
evidence about **behavior**. Do not carry that gate's "comments are noise" heuristic into this step.

Before changing any "Key Classes" line or API description:
1. Run the type scan for that doc root (one doc root per call):
   !python3 "<skill_dir>/scripts/kb_tool.py" scan-types --repo-root "<repo_checkout>" --path "<doc_root_relpath>"
2. Only add/remove/update class names if they appear in the scan output (or are clearly present in files under the same doc root).

`scan-types` also accepts multiple `--path` values, but unlike the target
resolvers it returns a per-file-deduped aggregation across the given roots
(types are counted once per source file even when roots overlap), then truncated
to `--max-items` globally — it is NOT a "union of single-path runs". Run it once
per doc root (as above) for evidence; reserve multi-path scan-types for ad-hoc
whole-area inventories.

## Conversation Mining (additional evidence source)

Mine agent conversation history for knowledge that code scanning cannot capture: architecture decisions, implicit constraints, clarifications, gotchas.

Trace source selection:
- Default / `--trace-source local`: mine local agent conversation history (Claude Code + Cursor).
- `--trace-source find-sdd-trace` / `--use-find-sdd-trace`: mine a remote Fornax trace located by the sibling `find-sdd-trace` workflow.

Spawn **one** subagent (Agent tool) to handle the entire mining workflow. The subagent resolves the selected trace source, exports and analyzes the conversation, and presents findings to the user for review via AskUserQuestion. The main agent receives confirmed knowledge items as the subagent's return value.

Subagent prompt template:

```
You are a conversation knowledge miner. Your job is to discover local agent conversation
history or fetch a requested remote MR-linked trace, extract knowledge worth preserving in
project documentation, and let the user review your findings.

## Inputs
- trace_source: "<local|find-sdd-trace>"
- repo_root: "<repo_root>"
- mr: "<mr_url_or_number_or_empty>"
- repo: "<repo_path_or_empty>"

## Tools available
- Bash: to run python3 scripts
- Bash: codebase / fornax-cli / ../find-sdd-trace helpers only when trace_source is `find-sdd-trace`
- AskUserQuestion: to present findings to the user for review

## Step 1: Resolve trace source

If trace_source is `local`:

  python3 "<skill_dir>/scripts/conversation_miner.py" discover --project-path "<repo_root>" --format json

This positively identifies SDD sessions by fingerprint (the session invoked adk-mobile
spec MCP tools and/or touched `.adk-mobile/specs/<NUM>-<name>`) and returns them
most-recent-first — matching the usual flow of summarizing the SDD session the user just
finished locally. Add `--within-hours N` for a soft recency window. SDD-tagged results
carry a `spec_name`. If no SDD session is found it falls back to a progressive time
window (24h → 3d → 7d) over substantive sessions; if nothing is found, return empty
result immediately.

If trace_source is `find-sdd-trace`, use the MR input to locate the remote trace:
1. Require an MR URL, or an MR number plus repo path. If either is missing and cannot
   be inferred from the current git remote: in interactive mode, ask the user for the
   missing input and stop; in `--ci` mode, emit a machine-readable error and stop
   (never ask, never fall back to local mining).
2. Run:
     codebase mr view -N <mr_number> -R <repo>
   Extract the MR author and CreatedAt timestamp. The relevant agent run usually
   happened before the MR was opened.
3. List candidate Fornax traces into a temp directory:
     # Query BOTH Fornax spaces by --workspace-id — a MR could be from either agent,
     # and omitting the flag silently searches only the config-default space (the root
     # cause of cursor-produced MRs showing up as "not found"):
     #   default (llmgw) space — codex / claude-cli : 7590053277580641284
     #   cursor space                               : 7590053680642274820
     for WS in 7590053277580641284 7590053680642274820; do
       fornax-cli trace list \
         --workspace-id "$WS" \
         --since <MR_created_minus_a_few_hours_ISO8601> \
         --until <MR_created_ISO8601> \
         --trace-filter-expr "user_id LIKE '<developer>%'" \
         --page-size 200 \
         --custom-region <region> \
         -o /tmp/kb_update_sdd_traces_<mr_number>
     done
   `--workspace-id` is required — without it only one space is searched. Both spaces write
   into the same dir (trace-id filenames don't collide) so Step 4 picks across all of them.
   The cursor space keys `user_id` by the developer's full email; the llmgw space may use a
   different handle. Match case-INSENSITIVELY (`LIKE '<handle>%'`, not `=` on a lower-cased
   email) — real cursor ids vary in case (e.g. an upper-case domain) and an exact match
   silently misses them. Pick `--custom-region` for the MR's environment (e.g. `SG`); do not
   assume one — a wrong region returns an empty list rather than an error, which looks like
   "no candidate trace".
   Widen the window only when the first result set is too small to identify a complete
   candidate run. If Fornax auth fails or no candidate trace exists, report the error and do
   not silently fall back to local mining.
4. Pick the complete trace:
     python3 "<skill_dir>/../find-sdd-trace/scripts/pick_complete_trace.py" /tmp/kb_update_sdd_traces_<mr_number> --json
   Use the winner path returned by the helper. For cursor candidates the helper regroups
   spans by `conversation_id` across trace files (one cursor conversation is scattered over
   many trace_ids) and returns a materialized `_conversation_<cid>.jsonl` as the winner.

## Step 2: Export and analyze

For each local discovered session, export it:
  python3 "<skill_dir>/scripts/conversation_miner.py" export --jsonl-path "<path>" --source "<source>" --format json

`--source` is `claude-code` or `cursor` for the local sessions found in Step 1.

For the `find-sdd-trace` winner path, export it:
  python3 "<skill_dir>/scripts/conversation_miner.py" export --jsonl-path "<winner_trace_json_path>" --source fornax --format json

The export preserves human text plus the high-signal structured parts of an SDD trace —
AskUserQuestion interactions (question + options + the user's actual selection, tagged
`[AskUserQuestion]` / `[User selected]`) and the generated `[SDD artifact: ...]` content
(spec / requirements / design / tasks / explore) — and drops noise tool calls
(Read / Grep / Bash / Glob).

Read the exported conversations and extract knowledge in these categories:
1. CORRECTION — user corrected the agent's misunderstanding (reveals implicit knowledge)
2. WHY — user explained why something is designed a certain way (architecture rationale)
3. CONSTRAINT — user stated something must/must not be done (implicit rules)
4. GOTCHA — user mentioned a past incident, pitfall, or non-obvious behavior
5. DEPENDENCY — user described runtime relationships not visible in code structure
6. DECISION — an AskUserQuestion the user answered: the chosen option is a deliberate
   decision; capture it and the rationale implied by the options not chosen

Do not invent knowledge — every item must have direct evidence from the conversation.
Deduplicate across sessions.

## Step 3: User review

Present extracted items to the user in batches of 3-4 via AskUserQuestion (multiSelect: true).
Each option: the knowledge statement + a short evidence quote.
Items not selected are discarded.

## Output

Return confirmed items as a JSON array, each item:
{
  "category": "CORRECTION|WHY|CONSTRAINT|GOTCHA|DEPENDENCY",
  "knowledge": "One-line statement in WHEN/MUST format if applicable",
  "evidence": "Exact quote from the conversation that supports this",
  "target_doc": "rule.md|domain.md|workflow.md|interface.md|CLAUDE.md",
  "confidence": "high|medium|low",
  "related_files": ["paths mentioned in context"]
}
```

### Integration with doc updates

Confirmed conversation-mined knowledge returned by the subagent feeds into the "What to Update Per Doc Root" phase:
- Items targeting `rule.md` → add as new WHEN/MUST rules
- Items targeting `domain.md` → update domain descriptions or add gotcha notes
- Items targeting `workflow.md` → update flow descriptions
- Items targeting `CLAUDE.md` → update module overview or key classes
- All updates still follow the Update Rules (strict) — minimal edits, no speculation

## What to Update Per Doc Root
For each doc root:
1. `CLAUDE.md`:
   - Update **Module Overview** only when ownership/integration changed.
   - Keep compact module structure summaries here when they help agents navigate the module (for example: public contracts, implementations, adapters, resources, or other local layers that actually exist in this doc root).
   - Do not paste long directory trees or code templates; keep `CLAUDE.md` as the entry summary and index.
   - Update **Key Classes** by removing missing symbols and adding only obvious entry points.
   - Keep **References** exactly as-is.
2. `interface.md`:
   - Update public-facing protocols/routers/services that changed.
   - Keep it < 100 lines; prefer pruning over adding.
3. `workflow.md`, `domain.md`, `rule.md`:
   - Fix outdated named entities, flows, and in-repo examples (Value bar category (a)).
   - **AND register the durable knowledge this change introduced** (category (b)). These three
     files are the ONLY place (b) knowledge can land — a narrower reading here silently cancels
     the (b) mandate for the whole run, since this is the last instruction read before writing.
     Both categories, same pass.
   - **The bar for (b), restated here because this is the last thing you read before writing:**
     register ONLY what a future developer/agent would **get wrong** without it, and only when
     you can point to the **hunk in THIS MR's diff** that makes it true. Judge it **per hunk**,
     never per MR — a worthy hunk elsewhere never licenses an entry for a trivial one. If an
     entry would not change what a future developer does, skip it. (Naming the additions limits
     is not the same as applying them: transient-experiment, granular-UI and Traceability all
     still bind, unchanged.)
4. `rule.md` quality upgrades for existing docs:
   - Treat low-quality existing rules as update targets when they violate `../kb-docs-validator/references/kb-rule-quality-contract.md`.
   - Compare against ancestor `docs/rule.md` / `rule.md` files and remove child rules that only restate parent/global rules.
   - Move or summarize module structure into `CLAUDE.md`; keep `rule.md` focused on enforceable future-change constraints.
   - Rewrite keep-worthy rules into `WHEN` + `MUST` / `MUST NOT` scenario blocks.
   - Keep only local, evidence-backed rules; preserve 1-3 high-value compact examples when they improve future coding accuracy, but remove standalone tutorials, full templates, generic style guides, product notes, test matrices, and inventories.
   - Apply the scoped length budgets from the shared contract.
   - After updating, run `kb-docs-validator` and continue fixing deterministic `rule.md` quality findings unless the remaining issue needs human judgment.
   - Preserve human-authored `<nay-ai>...</nay-ai>` blocks and ask before removing a large rule section.

## Finalize — enforce the write domain (mandatory gate)
After ALL edits are done (and after `kb-docs-validator`), run the apply phase of the write-domain gate against the same checkout you snapshotted at the start:

!python3 "<skill_dir>/scripts/kb_tool.py" enforce-writeset --apply --repo-root "<repo_checkout>"

It prints JSON `{"reverted": [...], "violations_basename": [...], "allowed_touched": [...], "scope_warnings": [...], "baseline_used": "..."}` and exits non-zero if it reverted anything. This is mandatory in BOTH default and `--ci` mode, exactly like the `kb-docs-validator` gate above.
- **Non-zero exit (something was reverted):** enumerate the reverted files in the run summary — `violations_basename` are out-of-domain files you must not have written — and self-correct: an out-of-domain write means you strayed from the 7 allowed basenames. Do not re-create reverted files.
- **`scope_warnings` (non-blocking):** kept files that do not sit at a recognized doc root — eyeball them; they are not reverted, just flagged.
- The gate is baseline-anchored, so it never touches files that were already dirty before you started.
