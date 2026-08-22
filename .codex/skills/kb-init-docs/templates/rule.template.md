# <Module> Rules

Module-specific, enforceable constraints for **this** doc root only. Repo-wide rules and nearest-ancestor rules apply by default — list them under **Inherited Rules** below and write only LOCAL differences / overrides here. Follows the KB rule quality contract (`kb-docs-validator/references/kb-rule-quality-contract.md`).

Owner: <owner>

## Inherited Rules

> Upper-level rules (global + the nearest ancestor `docs/rule.md`) apply by default — this file records only local
> **differences and overrides**; do NOT restate an inherited scenario (the validator WARNs on `WHEN` / heading overlap
> with an ancestor). This is the SSOT discipline: a shared rule lives in exactly one place — the nearest common ancestor.

- `<../../docs/rule.md>` — <nearest ancestor / business-root rule index: naming / DI / AB / layout / general>
- `<repo global rules path, e.g. .claude/rules/>` — <repo-wide conventions>
- If there is NO ancestor rule doc, write: `None — this is the top rule doc for this area.`

> **Rule shape** (required by the quality contract, the validator, and global-rule-creator): every rule is a local
> **scenario block** — a `## <Scenario>` heading + a `WHEN <specific local trigger>:` line + `- MUST` / `- MUST NOT`
> bullets. The validator requires at least one `WHEN ...:` block plus `MUST` / `MUST NOT` actions; prose/`Rule:`-style
> bullets without them fail.
> **Why discipline**: each scenario carries one `Why(incident)` (real incident/MR, with link) OR `Why(design)` (design
> reason in plain words). A rule that can give neither MUST NOT be written; don't dress generic advice up as having an
> incident behind it, and don't park "TBD" in the Why slot.
> **Examples**: keep 1-3 compact, copy-correct examples from the repo (5-12 lines, including protocol required members /
> boilerplate) attached to the scenario they clarify — an over-trimmed example that "won't compile when copied" is worse
> than none. Introduce with `Example from <path>:` / `Bad example from <path>:`.
> **SSOT — don't duplicate ancestors**: a shared rule lives in exactly ONE place (the nearest common ancestor). List
> ancestors in the **Inherited Rules** section above; here keep only local constraints, local exceptions, or local
> examples — never a restated parent scenario / `WHEN` / generic `MUST`.

## Context

Optional — include only when facts are needed to apply the rules below (source of truth, protected files, ownership boundary, lifecycle/state). Plain language, short. Delete this section if unused.

<facts the agent must know before applying these rules>

## <Scenario Name>

WHEN <specific local trigger condition>:
- MUST <required behavior, with a local boundary or exception>.
- MUST <required behavior; e.g. read `<doc>.md` before editing code covered by this scenario>.
- MUST NOT <forbidden behavior, with a local boundary or exception>.

Why(incident|design): <real incident/MR link, or the design reason in plain words. If neither — delete this rule.>

Example from `<repo-relative-path>`:
```<lang>
<5-12 lines of real code from the repo (keep protocol required members / boilerplate)>
```
Bad example from `<path>`:
```<lang>
<what the wrong version looks like + a one-line consequence>
```

## <Another Scenario Name>

WHEN <specific local trigger condition>:
- MUST <required behavior>.
- MUST NOT <forbidden behavior>.

Why(incident|design): <...>

## Related Docs

Optional — include only when a `MUST read` bullet above references a focused doc. Delete if unused.

- `<doc>.md`: <when to read it>

## Related Skills

Optional — include only when a Skill provides the detailed workflow behind a short rule trigger. Delete if unused.

- `<skill-name>`: <when to invoke it>
