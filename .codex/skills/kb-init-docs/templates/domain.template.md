# <Module> Domain Knowledge

<One line: what business problem this module solves, what scenarios it serves.>

> This file holds **business knowledge only** (terminology / core objects). Technical architecture (layers / dependencies / data flow / key sequences) goes in `architecture.md` (only for modules with real architecture); the structure overview (directory tree) lives in `CLAUDE.md`.

## Terminology
<First **enumerate ALL sub-feature-domains of this module** (entry / interstitial / result / growth / tracking / per-business-line / tools… every sub-domain that actually exists), then group by sub-domain, one table per group — **do not cover only the main path and drop the growth / tracking / entry side-domains** (the #1 cause of recall regressions). The Path column is mandatory — term→class→path triples are a shared trait of high-recall docs.>

### <Concept Area 1, e.g. "Conversation Types">
| Term | Meaning | Class | Path |
|---|---|---|---|
| <term> | <one line> | `<Class>` | `<relative path>` |

### <Concept Area 2>
| Term | Meaning | Class | Path |
|---|---|---|---|

## Core Objects & Relationships
<3-6 core business objects; relationships in one line / a small diagram. Use a table for state machines: state / meaning / transition condition.>

| Object | Responsibility | Key states/fields |
|---|---|---|

## Related Docs
- Public interfaces → `interface.md`; flows → `workflow.md`; rules & pitfalls → `rule.md`; architecture (if any) → `architecture.md`
