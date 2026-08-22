# KB Doc Length-Budget Contract (single source of truth)

> Same mechanism as `kb-rule-quality-contract.md`: every length judgment on the generation /
> validation / dashboard side references THIS file — change a budget in one place only. Consumers:
> `kb-init-docs` (generation), `kb-update-docs` (update), and the KB dashboard health view's
> over-budget list (the data side judges by this table).

## Tiers: by module size (source files in the doc-root subtree)

Source file = `.swift/.m/.mm/.h/.c/.cpp/.kt/.java` (same definition as the dashboard's "qualifying dir >= 30 source files").

| Tier | Module size | Typical shape |
|---|---|---|
| **S** | < 30 source files | API shim / adapter layer / small utility module |
| **M** | 30 – 149 source files | Regular business module (baseline tier) |
| **L** | >= 150 source files | Large module — **prefer splitting into sub-module KBs**; the L cap is a transitional allowance, not a normal state |

## Budget table (line count, pure upper bound)

| Doc | S | M | L |
|---|---|---|---|
| `CLAUDE.md` | 50 | 70 | 95 |
| `docs/domain.md` | 80 | 130 | 140 |
| `docs/interface.md` | 90 | 170 | 170 |
| `docs/workflow.md` | 135 | 190 | 225 |
| `docs/rule.md` | 105 | 200 | 200 |

> **Single 口径 = measured p90 (rounded up to 5).** Every cell is the p90 of real KB-doc line counts for
> that (doc type × tier), computed by the calibration script `p1-distribution.py`
> (maintainers' calibration archive). These numbers are **identical to the
> dashboard's oversize thresholds** (`kb-crawler/kb-dochealth.py` `TIER_BUDGET`) — same source, no drift.
> `docs/rule.md` is on the SAME p90 basis as the other four (it is **no longer** the separate 80/120/180 —
> that was measured too tight at S/M). The validator's `rule.md` length gate (`kb-rule-quality-contract.md`
> "Scoped Length Budgets" + `validate_kb_docs.py`) uses the same p90 for target/warn and p95 for the strong
> level. **Refresh:** the crawler recomputes p90 monthly and proposes adjustments for review (no hand-picking).
> Tier: S<->Small/leaf, M<->Medium/module, L<->Large/aggregate; module size by source-file count
> (S < 30, M 30–149, L >= 150) as a machine-judgeable proxy.

## Rules

1. **Pure upper bound, no floor**: content that says everything needed is complete; "padding lines to hit the budget" is a smell.
2. **Over budget = a split signal**: when over the M/L cap, first consider splitting into sub-module KBs (each sub-module carries its own four-piece set), rather than deleting facts.
3. **S tier may drop whole sections**: for an inapplicable section, write one line — "N/A: logic lives in the impl layer, see <impl> KB".
4. **L-tier precondition**: a module with >= 150 source files should first be evaluated for splitting; use the L cap only when it genuinely should not be split (a strongly-cohesive monolith), and prefer adding the conditional `docs/architecture.md` (which does not count against the four-piece budget).
5. Budget changes: edit this table and it takes effect globally; the generation-side templates (`kb-init-docs/templates/`) and the dashboard data side (over-budget judgment) both follow this table — neither may invent its own numbers.
