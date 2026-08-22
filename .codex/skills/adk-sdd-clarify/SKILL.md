---
name: adk-sdd-clarify
description: "Clarify ambiguities in spec artifacts via reverse scan and Q&A. Use when the user wants /adk:sdd:clarify."
---

# ADK SDD Clarify

Codex entrypoint for `/adk:sdd:clarify`. Follow this workflow when the user invokes the matching slash command or explicitly requests this mobile SDD action.

## Mission

Detect and resolve ambiguities, inconsistencies, or knowledge gaps across existing spec artifacts by reviewing them in reverse phase order, confirming issues with the user through up to 5 targeted Q&A rounds, and cascade-updating all affected intermediate products to maintain cross-document consistency.

## Implementation

**CRITICAL: This uses MCP tool call, NOT bash command**

When invoked:

### Step 1 — Resolve Target Spec

`spec name` is OPTIONAL. Resolution order:

1. **Argument provided** → use it directly.
2. **No argument** → infer from current conversation context (the spec being actively worked on in this session).
3. **Cannot infer** → ask the user which spec to clarify.

Optional trailing argument: a specific concern or question the user wants clarified (used to seed prioritization in Step 4).

### Step 2 — Determine Current Phase

1. **Find and call** the available MCP tool ending with `spec-status` to retrieve the current workflow state.
2. **If `data.mode === 'ff'`** (Fast-Flow spec): the artifact chain is simply `plan.md` + `spec.md` (if it exists). Skip the phase-order logic below and go directly to Step 3 with this two-file chain.
3. Identify which phase the spec is currently in or most recently completed:
   - **Phase order**: `requirement` → `design` → `task` → `implementation`
   - The "current phase" is the latest phase that has an existing artifact file, regardless of approval status.
4. Build the **artifact chain** — the ordered list of intermediate products that exist for this spec, from the current phase backward:
   - If in `tasks` phase: `tasks.md` → `design.md` → `requirements.md`
   - If in `design` phase: `design.md` → `requirements.md`
   - If in `requirements` phase: `requirements.md`
   - If in `implementation` phase: `tasks.md` → `design.md` → `requirements.md`
   - Additionally, if `spec.md` exists (from prd-to-spec flow), include it at the end of the chain.

### Step 3 — Reverse-Order Artifact Scan

Read artifacts in **reverse phase order** (latest phase first, earliest last). For each artifact:

1. **Load** the file content from `{workflow-dir}/specs/{spec-name}/` (check `.mcp.json` for the `--workflow-dir` argument to determine the actual workflow directory).
2. **Scan** for:
   - Internal ambiguities: vague language ("robust", "intuitive", "appropriate"), TODO markers, placeholder text, unresolved decisions.
   - Cross-document inconsistencies: terms, constraints, or decisions in a later artifact that contradict or are unsupported by an earlier one.
   - Missing coverage: requirements mentioned in `requirements.md` but not addressed in `design.md`; design decisions in `design.md` not reflected in `tasks.md`.
   - Stale references: outdated file paths, renamed entities, deprecated approaches.
3. **Confirm issue existence**: Before flagging an issue, verify it is genuine by cross-referencing related artifacts. Only flag issues that would materially impact implementation correctness, test design, or architectural integrity.

Build an internal **issue map** (do NOT output it directly) — categorized by:
- `inconsistency`: cross-document contradiction
- `ambiguity`: vague or underspecified within a single document
- `gap`: missing information that downstream phases depend on
- `stale`: outdated content that no longer reflects the current state

### Step 4 — Generate Clarification Questions (Top 5)

From the issue map, generate a prioritized queue of **at most 5** clarification questions. Apply these constraints:

- **Impact-first ordering**: Prioritize issues by `(Downstream Impact × Uncertainty)`. Issues that block implementation or cause cascading inconsistencies rank highest.
- If the user provided a specific concern in the argument, prioritize related issues first.
- Each question must be answerable with EITHER:
  - A short multiple-choice selection (2–5 distinct options), OR
  - A short free-form answer (≤ 1 sentence).
- Exclude questions whose answers would not change any artifact content.
- Ensure coverage balance: avoid clustering all questions on a single document when multiple documents have issues.

### Step 5 — Sequential Q&A Loop (Interactive)

Present **exactly ONE question at a time**. For each question:

1. **State which artifact** the issue was found in (e.g., "In `design.md`, section Architecture Overview...").
2. **For multiple-choice questions**:
   - Analyze all options and determine the **most suitable option** based on project context and best practices.
   - Present recommendation prominently: `**Recommended:** Option [X] — <reasoning>`
   - Render all options as a Markdown table:

   | Option | Description |
   |--------|-------------|
   | A | ... |
   | B | ... |
   | C | ... |

   - After the table: `Reply with the option letter, accept the recommendation by saying "yes", or provide your own answer.`

3. **For free-form questions**:
   - Provide a **suggested answer**: `**Suggested:** <answer> — <brief reasoning>`
   - Then: `You can accept by saying "yes" or provide your own answer.`

4. **After the user answers**:
   - If "yes" or "recommended": use the previously stated recommendation.
   - Validate the answer resolves the identified issue.
   - If ambiguous, ask for a quick disambiguation (does not count as a new question).
   - Record the accepted answer and **immediately** proceed to cascade update (Step 6) before asking the next question.

5. **Stop** asking further questions when:
   - All critical issues resolved, OR
   - User signals completion ("done", "enough", "proceed"), OR
   - 5 questions have been asked and answered.

### Step 6 — Cascade Update (After EACH Accepted Answer)

After each accepted answer, update **all affected artifacts** to maintain consistency. The update cascades **upward** through the artifact chain:

1. **Identify affected scope**: Determine which artifact(s) contain the issue and which upstream/downstream artifacts reference the same concept.
2. **Update strategy by current phase**:
   - **Fast-Flow spec** (`data.mode === 'ff'`): fix `plan.md` first, then check and update `spec.md` if the fix implies a context change.
   - If issue is in `design.md`:
     - Fix `design.md` first.
     - Check if the fix implies changes to `requirements.md` (e.g., a new constraint, a changed requirement). If so, update `requirements.md` as well.
     - If `spec.md` exists, check and update it for consistency.
   - If issue is in `tasks.md`:
     - Fix `tasks.md` first.
     - Check if the fix implies design changes → update `design.md`.
     - Then check if those design changes imply requirement changes → update `requirements.md`.
     - If `spec.md` exists, check and update it for consistency.
   - If issue is in `requirements.md`:
     - Fix `requirements.md`.
     - Check if downstream artifacts (`design.md`, `tasks.md`) need alignment updates.
     - If `spec.md` exists, check and update it for consistency.
3. **Update rules**:
   - Replace contradictory statements rather than appending (no obsolete text should remain).
   - Preserve document structure, heading hierarchy, and formatting.
   - Keep changes minimal and targeted — do not rewrite unrelated sections.
   - Add a `<!-- clarify: YYYY-MM-DD — <brief change note> -->` comment near each substantive change for traceability.
4. **Save** each modified file immediately after updating.
5. Modify only artifacts in the current repository. Never edit another member's `specDir` or propagate files to another repository; later phase-guide calls detect changed member `spec.md` content automatically.

### Step 7 — Completion Report

After the Q&A loop ends:

1. **Summary**: Number of questions asked and answered.
2. **Artifacts updated**: List each modified file and the sections touched.
3. **Consistency status**: Confirm all artifacts are now mutually consistent, or list remaining known issues.
4. **Recommendation**:
   - If all issues resolved: suggest proceeding with the current phase workflow (e.g., `/adk:sdd:continue <spec-name>`).
   - If unresolved issues remain: recommend running `/adk:sdd:clarify <spec-name>` again after further progress, or escalating specific items.

### Behavior Rules

- If no meaningful issues found across all artifacts, respond: **"No critical ambiguities or inconsistencies detected across spec artifacts."** and suggest proceeding.
- If no spec artifacts exist for the given name (or no active specs detected during auto-resolution), instruct the user to run `/adk:sdd:new` first.
- Never exceed 5 total questions (disambiguation retries for a single question do not count as new questions).
- Respect user early termination signals ("stop", "done", "proceed", "enough").
- Do NOT modify artifact files unless the user has confirmed the change through the Q&A loop.
- When updating artifacts, always re-read the file before writing to avoid overwriting concurrent changes.

## Examples

- `/adk:sdd:clarify` — Auto-detect the active spec and scan all its artifacts for ambiguities
- `/adk:sdd:clarify user-auth` — Explicitly target the user-auth spec
- `/adk:sdd:clarify 001-payment-flow the retry logic seems unclear` — Clarify with a focus on retry logic in the payment-flow spec
- `/adk:sdd:clarify 002-dark-mode` — Check consistency across requirements, design, and tasks for dark-mode

