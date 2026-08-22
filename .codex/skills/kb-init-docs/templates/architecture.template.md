# <Module> Architecture

> **Conditional standard piece**: create this file ONLY when the module has real architecture (multiple layers / complex dependencies / a clear data flow); thin modules (API shim / single layer) skip it — cover the structure in `CLAUDE.md`'s Module Overview / Directory Map instead.
> This file covers the **static technical architecture**: layers / dependencies / data ownership. Business terminology belongs in `domain.md`; the directory tree belongs in `CLAUDE.md`; **runtime step-by-step flows and call sequences belong in `workflow.md` — do NOT restate them here, link to `workflow.md` instead.**
> **Include a diagram by default**: architecture.md is THE doc where a diagram earns its keep — add at least one Mermaid diagram (a **layered-structure** flowchart and/or a **module-dependency** graph). **Text-mirror rule (mandatory)**: every node / class / method that appears in any diagram MUST also appear in the prose / table below it, so the information survives where Mermaid does not render (some KB consumers / plain-text agent reads). A diagram is the visual aid, the text is the source of truth.

## Layered Structure
- **<layer>**: <responsibility> (<key classes/dirs, relative path>)
- **<layer>**: <responsibility>
<Inter-layer dependency in one line: A → B → C, and who must not depend on whom (a reverse dependency is a pitfall).>

```mermaid
flowchart TD
  <LayerA entry> --> <LayerB domain> --> <LayerC data>
```
<Default for this doc. Every node above also appears in the layer bullets / Dependencies table (text-mirror rule).>

## Dependencies
<Inter-layer / inter-module dependency **direction** and reverse-dependency pitfalls (who must not depend on whom) — the architectural relationships between the layers named above. Use a table AND a Mermaid dependency graph (default for this doc); every node name in the diagram must also appear once in the text/table (text-mirror rule). **Do NOT re-inventory external libraries / pods / server SDKs here — the module's external-dependency list is owned solely by `interface.md` (Required zone); this section is layer relationships, not a dependency catalog.**>

| Direction | Target | Purpose |
|---|---|---|
| depends on | `<internal layer/module>` | <why — the architectural relationship> |
| depended on by | `<internal layer/module>` | <who uses it, for what> |

## Key Data Flow
<A **static** view only: which layer / component **owns** which data, and the overall direction data moves between layers (source → transform → sink). One or two sentences plus an optional ownership table. **Do NOT write numbered runtime step sequences here** — the step-by-step temporal flow (receive → fan-out → filter → build → render, comment send / re-entry, moderation, …) is owned by `workflow.md` (L2). For the runtime sequence, link instead: "运行时逐步时序见 `workflow.md`". The same numbered call sequence must not appear in both files.>

| Data / state | Owning layer | Flows from → to |
|---|---|---|
| `<data/state>` | `<layer/component>` | `<source>` → `<sink>` |
