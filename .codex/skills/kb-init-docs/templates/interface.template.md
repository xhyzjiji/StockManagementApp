# <Module> Interfaces

> **Boundary map** of the module, in two explicit directions: **Provided（对外提供）** — the public contract
> consumers use (services / routes / events / integration recipe); **Required（依赖与消费）** — what the module
> consumes at its boundary (server network APIs, external dependencies). The Provided zone is the primary reason
> this doc exists; the Required zone records cross-file / cross-repo wiring that agentic search finds poorly.
> Document **boundary** things only; internal implementation details belong in domain/rule.
>
> **Digest, not transcription（压缩优先）**: this doc is a *curated digest* of the module's public
> surface — NOT a mirror of it. The authoritative, always-fresh definition of every signature lives in the source files
> (agents can and should read them directly via the pointers below). Audited failure mode to avoid: interface.md that
> verbatim-copies whole headers incl. `///` doc comments (real case: a 646-line doc duplicating 853 lines of source —
> compression ≈ 1:1, zero reading-cost saved, guaranteed to rot). Rules:
> - **Pick, don't enumerate**: list the 5–10 highest-traffic entry points per capability area with a one-line purpose
>   each — not every method of every protocol. For the full surface, point to the source file.
> - **Never paste source doc comments (`///` / KDoc / Javadoc) or full signature blocks.** A method is referenced by
>   its name — Swift `save(forKey:)`, Kotlin/Java `save(key)`, ObjC `setObject:forKey:` — plus one line of purpose in
>   your own words. If your sentence is identical to the source comment, you are transcribing — delete or compress.
> - **What earns lines here is what source can't say**: threading/ordering constraints, stability contracts, pitfalls,
>   cross-file wiring. Signature inventory earns almost none.

## Source of Truth（接口权威声明，REQUIRED — 二选一）
<First DETECT which case this module is (probe before writing: does a dedicated interface surface exist — an
`Interface`/`API`-named file or subspec on iOS, a sibling `*_api` module on Android, a public-headers set?),
then declare ONE of the two modes explicitly. The declaration is machine-read by the recall-miss caliber
(covered-by-pointer), so never skip or blur it.>

**Mode A — Centralized（接口集中型）**: a dedicated file/module IS the authoritative surface. Point to it; the body
below stays a curated digest (5–10 entries). Agents needing the full, current signature list read these files.
| Interface source file | Declares |
|---|---|
| `<path/to/PublicInterface.swift>` | <e.g. the service protocol + factory> |

**Mode B — Dispersed（接口分散型）**: no single authoritative file — the public surface is scattered across
implementation files. Declare it in one line that MUST start with the fixed machine token **`Dispersed:`** (the
recall-miss caliber parses this exact prefix to branch A/B — never reword or translate the prefix; the text after
it is free-form): `Dispersed: no dedicated interface file; the table below IS the aggregated public surface.`
In this mode a fuller enumeration is LEGITIMATE (aggregating scattered entry points into
one map is cross-file knowledge that agentic search does poorly — it earns its lines), but each entry is still ONE
line (name + purpose in your own words); pasted signature blocks / doc comments remain forbidden, and the length
budget still applies. A Dispersed declaration is also a refactor signal (interface worth consolidating) — the
dashboard may surface it.

## Provided（对外提供）
<Zone divider — keep this heading verbatim. Everything from here to the Required zone describes the OUTWARD
direction: what consumers (other modules / the host app) can call, observe, or navigate to.>

## Services & Protocols
<Group by capability area. Mode A: list ONLY the highest-traffic entry points (5–10 across the group, judged by
call-site frequency / integration order) — full membership of a protocol = see the Source of Truth pointer, do not
inline it. Mode B: enumerating more entries is fine (the table is the aggregation), one line each. In both modes,
each entry = a one-line purpose in your own words; method names remain good recall anchors — anchor by name
(per-language form above), never with pasted declarations.>

### <Capability Area 1>
| Protocol / Service | Key entry points (curated) | Description |
|---|---|---|
| `<Protocol>` (`<path>`) | `<method(a:b:)>`, `<method2()>` | <one line> |

## Routes / Deep Links (REQUIRED when the module exposes URL routes / deep links)
<Consumers most often ask "how do I open / navigate to X" — list ALL public URL routes: route string + target
page/handler class + required/optional params. **Don't document only the programmatic factory and drop the URL route**
(document both). Routes are cross-file wiring that agentic search finds poorly — they earn their lines. Write "None"
if there are no public routes.>
| Route (URL) | Target / handler class | Required params | Optional params |
|---|---|---|---|
| `<aweme://...>` | `<Class>` | `<param>` | <...> |

## Outbound Events / Data Channels
<Notifications, callbacks, EventBus, data subscriptions — how consumers observe this module. Write "None" if none.>
| Event/channel | When it fires | Payload |
|---|---|---|

## Integration Example (optional; recommended for init / most-used APIs)
<A complete, copyable code block of how the host integrates (e.g. a setup() call + callback implementation). Tables
aren't copyable; init-style APIs must include this. Pure query-style small interfaces may omit this section. This is
YOUR composed example — an integration recipe the source doesn't contain — not a pasted source excerpt.>
```<lang>
<complete call example>
```

## Stability Constraints
<Which interfaces are stable contracts (who to notify before changing) and which are free to change; the blast radius
of a breaking change. 3-5 lines.>

## Required（依赖与消费）
<Zone divider — keep this heading verbatim. Everything below describes the INWARD direction: what this module
consumes at its boundary. This is NOT part of the provided surface — consumers never touch these — but the
endpoint↔feature / dependency↔module mapping is cross-file (often cross-repo: IDL, codegen) wiring that agentic
search reconstructs poorly, so it earns its lines here.>

## Network APIs (REQUIRED — write "None" if the module makes no network calls)
<Server endpoints this module CALLS — its contract with the backend.
**Endpoint format (hard rule)**: copy the full route path VERBATIM from where it is declared — the client request
annotation/builder (e.g. Retrofit/Mota `@GET("/tiktok/v1/<feature>/<action>/")`, iOS request path constant) or the
IDL route option (`option (api.get/post) = "..."`). NEVER paraphrase, shorten, or invent a name — an audited failure:
a doc listed `ai_music_trending` for an endpoint whose declared name is `get_trending_list`; the alias matches nothing
in source or IDL, so agents searching either name miss. If client code only shows an RPC/service method name (codegen
indirection), write that exact name PLUS a pointer to the file where the full path is declared.>
| Endpoint | Method | Purpose |
|---|---|---|
| `/tiktok/v1/<feature>/<action>/` | POST | <one line, your own words> |

## External Dependencies (REQUIRED — write "None" if the module has none)
<External services / modules this module depends on, one per line + purpose. An absent section reads as
"not audited", not "no dependencies" — always write the section, with "None" when empty.>
