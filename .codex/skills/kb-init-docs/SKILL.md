---
name: kb-init-docs
description: Generate/refresh documentation (CLAUDE.md, interface.md, workflow.md, domain.md, rule.md) for given directory path or analyzed directory paths
allowed-tools: Bash(python3 scripts/kb_tool.py*), Read, AskUserQuestion, Edit
---

> Note: All `python3 scripts/...` commands below must be executed with the current skill directory as the working directory (the directory containing this SKILL.md). The scripts resolve their own dependencies relative to that location.

## Intention

Generate or refresh documentation for:

- The given directory path
- The analyzed doc-root paths when `--analysis` is used

## Inputs

- Directory path(s) (required): repo-relative or absolute path; accepts multiple paths separated by spaces and/or newlines
- Optional flag: `--analysis`
- Optional flag: `--lang <auto|en|zh>` (default: `auto`)

## Examples

```bash
/kb-init-docs --analysis path 
/kb-init-docs path --lang en
/kb-init-docs path --analysis --lang zh
/kb-init-docs pathA pathB --analysis
```

## Workflow

Before generating `docs/rule.md`, read and follow the shared rule contract:

- `../kb-docs-validator/references/kb-rule-quality-contract.md`

### 1 Resolve directory path(s) (stable roots)

Interpret the user’s input as:

- If the input contains `--analysis`, remove that flag.
- If the input contains `--lang <auto|en|zh>`, remove that flag pair and record the language preference.
- Split the remaining text by whitespace/newlines into one or more directory paths.
- Treat each directory path independently in the following steps.

### 2 Decide scope

2.1 - If `--analysis` is NOT set: use each given directory path as a doc root and proceed to Step 3 for each path

2.2 - If `--analysis` IS set:
   2.2.1 analyze all given directory paths first, and collect suggested doc roots from the following script:

   !python3 scripts/kb_tool.py suggest-doc-roots "<module_path1>" "<module_path2>" ...
   || (printf '\a' >&2; echo "kb-init-docs error: suggest-doc-roots failed" >&2; exit 1)

   2.2.2 Use AskUserQuestion to ask the user how to choose doc roots. 
     1) Paste newline-separated doc root paths copied from `suggested_doc_roots`
     2) Reply `ALL` (or `全部`) to select all `suggested_doc_roots`
     3) Reply `USE_ARGUMENT_PATHS` (or `使用参数路径`) to use doc root paths already included in the original input argument (newline-separated)

### 3 Generate docs (writes, after explicit user approval)

What to generate:
Generate ONLY the following files and content:

Language:

- If `--lang en`, write all generated content in English.
- If `--lang zh`, write all generated content in Chinese.
- If `--lang auto`, follow the user's language in the conversation.
- **CLAUDE.md** - Main documentation with EXACTLY these three sections:
  - **Module Overview**: Brief description of the directory's primary purpose, responsibilities, and compact module structure.
    - Include a short structure summary when useful (for example: public contracts, implementations, adapters, resources, or other local layers that actually exist in this doc root).
    - Keep structure guidance at summary level. Do not paste long directory trees or code templates in `CLAUDE.md`.
  - **Key Classes**:
    step 1: find important classes/interfaces with one-line concise and clear descriptions by
    !python3 scripts/kb_tool.py select-key-classes <path> --top 20
    || (printf '\a' >&2; echo "kb-init-docs error: select-key-classes failed" >&2; exit 1)
    step 2: display key classes in the following table format
    <example-output>
       | Type | Kind | Des |
       |------|------|-------|
       | `ClassA` | class | brief description |
       | `ClassB` | class | brief description  |
    </example-output>
  - **References**: Fixed references to the following docs
    ```
    - [docs/interface.md](./docs/interface.md) - External interfaces and public APIs exposed by this doc root
    - [docs/workflow.md](./docs/workflow.md) - Business process flows
    - [docs/domain.md](./docs/domain.md) - Business terminology and strategy documentation,
    - [docs/rule.md](./docs/rule.md) - module-specific rules and constraints for future changes in this doc root
    ```
    Add `- [docs/architecture.md](./docs/architecture.md) - technical architecture (layers / dependencies / data flow)` to this list **only when** `docs/architecture.md` was generated.
- **docs/interface.md** - External interfaces and public APIs exposed by this doc root (length budget tiered by module size — see `../kb-docs-validator/references/kb-doc-budget-contract.md`)
  - Structure: follow `templates/interface.template.md`.
  - When the module exposes deep-link / URL routes, document them in a route table (route → target/handler class → required + optional params) — a route IS a public interface and "how to open X / which route" is a top KB question; do not document only the programmatic factory. List the key methods of each key service/manager (including parameterized selectors), not just the class name.
- **docs/workflow.md** - Main business process flows with UML diagrams if needed
  - Structure: follow `templates/workflow.template.md` (L1 human-readable overview → L2 detail → L3 failure/degradation). workflow.md is the **sole owner** of runtime / temporal step-by-step flows and call sequences. Do NOT pad a diagram with a prose restatement (that duplicates the L2 steps); but every class/method appearing in a diagram MUST also appear in the body text (steps / tables; a class that only appears in a diagram is anchored in `CLAUDE.md`'s Key Classes).
- **docs/domain.md** - Business knowledge template for developers, terms and concepts used in the business
  - Structure: follow `templates/domain.template.md` (pure business — terminology and core objects; technical architecture lives in `docs/architecture.md`, not here).
- **docs/architecture.md** (CONDITIONAL — generate only when warranted) - **Static** technical architecture: layered structure / dependencies / data ownership.
  - Generate ONLY when the module has substantial architecture (multiple layers, non-trivial dependencies, or a real data flow worth documenting). For thin modules (API shim / single-layer / no real architecture), DO NOT create it — a one-line structure note in `CLAUDE.md`'s Module Overview is enough.
  - Structure: follow `templates/architecture.template.md`. Prefer structured text (tables + short prose); diagrams are optional, only where they render, never the sole representation, and every symbol in a diagram must also appear in the text. **Before writing, check what `workflow.md` already covers: architecture.md carries the static structure only — do NOT restate workflow.md's runtime step-by-step sequences (link to `workflow.md` instead), and do NOT re-inventory external dependencies (those are owned by `interface.md`'s Required zone).**
- **docs/rule.md** - Module-specific rules for this doc root only.
  - Follow `../kb-docs-validator/references/kb-rule-quality-contract.md`, plus the structure in `templates/rule.template.md` (each rule carries `Why(incident|design)`; rules with neither must not be written).
  - Before writing rules, inspect ancestor `docs/rule.md` / `rule.md` files and do not duplicate parent/global rules.
  - Generate rules only when they are specific to this doc root, evidence-backed, useful for future code changes, and shaped as `WHEN` + `MUST` / `MUST NOT` scenario blocks.
  - Put compact module structure summaries in `CLAUDE.md`; use `docs/rule.md` only for enforceable constraints derived from that structure.
  - Keep 1-3 high-value compact code examples when they materially improve future coding accuracy; attach each example to a nearby local rule.

> **Structure templates**: read `templates/kb-doc-templates.md` FIRST — it carries the global
> contract for all docs, the four-piece + CLAUDE.md plus the conditional `architecture.md` (length budgets are pure upper bounds, no padding to a floor;
> small API-shim modules may drop non-applicable sections with a one-line pointer to the impl
> KB; code symbols must be spelled out in full — no `{A,B}` brace abbreviations; when removing
> or rewriting a diagram, every class/method name appearing in it must be preserved in the text
> version; "TBD" only on items someone will actually fill, never as empty table rows).
> `CLAUDE.md` structure additionally follows `templates/CLAUDE.template.md` (consistent with the
> EXACT three-section rule above).

#### Document Generation Rules

- CLAUDE.md top-level sections MUST be exactly: `## Module Overview`, `## Key Classes`, `## References`
- If files already exist, no any changes to them
- Place `interface.md`, `workflow.md`, `domain.md`, `rule.md` (and `architecture.md` when generated) under a `docs/` folder next to `CLAUDE.md`
- Include README.md content in Module Overview if it exists
- Ensure `AGENTS.md` is a symbolic link pointing to `CLAUDE.md` in the same directory
- **Coverage completeness (do not document only the main pipeline)**: before writing, enumerate ALL
  sub-feature-domains that actually exist in the module (entry / growth / tracking / per-business-line /
  tools / ...), not just the obvious core flow — each gets its terms→class→path coverage in the
  relevant doc. After writing, run `!python3 scripts/kb_tool.py select-key-classes <abs_doc_root> --top 20`
  again and verify every important class it returns is anchored (class name + relative path) in at least
  one generated doc (`domain.md` / `interface.md` / `workflow.md` / `architecture.md`); add any that are
  missing. Restructuring or tightening the budget may reorganize content but MUST NOT drop important
  classes wholesale — that is the difference between a high-recall KB and a merely "clean" one.
- **Cross-file dedup self-check (workflow ↔ architecture ↔ interface)**: after writing, diff `workflow.md`'s L2
  numbered step sequences against `architecture.md`. If the same class-call sequence appears in both, keep it in
  `workflow.md` and reduce the `architecture.md` copy to a one-line pointer ("运行时逐步时序见 workflow.md").
  Likewise the external-dependency inventory belongs only in `interface.md` (Required zone) — remove any duplicate
  list from `architecture.md`. (The validator emits a WARN when a numbered call sequence is duplicated across
  `workflow.md` and `architecture.md`.)
- Focus on conceptual understanding, not implementation details
- DO NOT add generic development practices or tips

### 4 Validate the generated docs (gate, after Step 3)

Generation is NOT complete until the docs pass the validator. The validator is a separate skill;
run it automatically here rather than leaving it to the user.

For every doc root you generated in Step 3, run with `--strict` and **absolute paths** for each
doc root (the call is routed through `kb_tool.py` so it stays within this skill's `allowed-tools`;
arguments pass straight through to the validator, which resolves relative inputs against its own
skill directory — so absolute doc roots are required; `--strict` makes the exit code the gate —
non-zero means at least one `ERROR`):

!python3 scripts/kb_tool.py validate-kb-docs --strict "<abs_doc_root1>" "<abs_doc_root2>" ...

Then act on the report:

- **Exit code 0 (zero `ERROR`) is the completion bar.** A non-zero exit means the report lists at
  least one `ERROR` (broken references, AGENTS.md not linking to CLAUDE.md, doc claims that don't
  match code, malformed `rule.md` scenario blocks). Fix the generated docs minimally and re-run on
  the same roots. Repeat until the command exits 0.
- `WARN` / `INFO` are advisory and do NOT affect the exit code or block completion; address them
  only when the fix is clear and local. Do not pad docs to silence boilerplate INFO.
- Only report generation as done once the validator exits 0 for all generated roots.

After the validator passes, run the doc-coverage self-check — it catches important code symbols
the docs forgot to anchor, which the validator does not check (it exists because
`select-key-classes` is top-N bounded and silently drops contract protocols / secondary
collaborators that rank below the cut):

!python3 scripts/kb_tool.py check-doc-coverage "<abs_doc_root>"

- **Prong 1** lists public-interface-dir protocols (under `.../ModuleInterface/Interface/`,
  `.../Public/`, `.../API/`) not mentioned in the docs, ranked by fan-in. **Prong 2** lists
  same-header siblings of a documented type that are themselves undocumented (e.g. a documented
  manager's paired chunk / result / options type declared in the same header).
- This is **advisory, not a hard gate**: a large module legitimately leaves many interface
  protocols out of the KB. Scan the TOP hits and anchor the genuinely-important ones — the base
  protocol you must implement to extend the module, or a collaborator of a documented flow. Tune
  the threshold with `--min-fanin` / `--max-header-decls`; `--strict` turns Prong 1 into a gate
  (note: on a large module Prong 1 can be 100+ entries — a ranked hint list, not a clean gate;
  do NOT wire `--strict` into CI for big modules).
- **Ceiling (do not over-rely):** this only catches *whole types* that are dropped. It does NOT
  catch a documented class that is missing key *methods* (e.g. an inbox manager listed with no
  methods), nor missing *rule content* (e.g. a dropped dispatch-safety rule). Those still require
  human review of the diff.

### 5 Optional: generate evals (recommended)

After the docs bundle is generated and approved, offer to benchmark-proof it:

```
Use the kb-evals-creator skill on <doc-root> to create docs/evals/evals.json
```

Evals make the docs measurable (`kb-docs-benchmark` runs Q&A against them) and the KB
dashboard surfaces per-module evals coverage. Skip silently if the user declines.
