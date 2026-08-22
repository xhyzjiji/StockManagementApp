# <Module>

## Module Overview
<3-6 lines: what this module is, its core responsibilities, which business line it belongs to. A newcomer / AI must grasp "what is this for" at a glance.>

### Directory Map (optional; include when the module has several submodules)
> CLAUDE.md top-level `##` sections may ONLY be Module Overview / Key Classes / References (hard rule); a directory tree is a structure overview, so nest it under Module Overview using `###`.
```
<module-root>/
├── <subdir>/   # <responsibility>
└── <subdir>/   # <responsibility>
```

## Key Classes
| Type | Kind | Description |
|---|---|---|
| `<Class>` | <class/protocol/enum> | <one-line responsibility> |
<The 5-15 most important ones; do not paste the full list here (use the directory tree / IDE).>

## References
- `docs/domain.md` — business terminology / core objects
- `docs/interface.md` — public protocols / events / network
- `docs/workflow.md` — core flows (the L1 summary reads in 5 min)
- `docs/rule.md` — module rules and pitfalls (each with a Why)
<Add `- docs/architecture.md — technical architecture (layers / dependencies / data flow)` ONLY when architecture.md was generated. List docs/evals/ too if present.>
