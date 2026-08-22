---
name: adk-readiness
description: "Assess mobile repository AI Coding readiness and produce a maturity report. Use when the user asks for readiness scan, module evaluation, or AI-friendly assessment."
---

# ADK Readiness

Codex entrypoint for `/adk:readiness`. Follow this workflow when the user invokes the matching slash command or explicitly requests this mobile SDD action.

## User Input

```text
$ARGUMENTS
```
You **MUST** consider the user input before proceeding (if not empty).

Supported user input patterns:
- **No arguments**: Repo-level scan (infrastructure dimensions only; suggests module scan next)
- **Module path(s)**: e.g. `"Modules/Search"` or `"Modules/Search Modules/Feed"` → module-level scan
- **`--all-modules`**: Auto-discover and batch-evaluate all modules containing source code
- **Specific dimensions**: e.g. `"Modules/Search only context and testing"` → scan specific dimensions for a module
- **Output to file**: e.g. `"output to file"` → write report to `.ttadk/readiness-report.md`
- **Compare mode**: e.g. `"compare with last run"` → diff against previous report
- **Target level**: e.g. `"target L3"` → only report improvements needed to reach L3

## Context

**Read context before Executing**:

1. **Language Setting**: Read `preferred_language` from `.ttadk/config.json` (default: 'en' if missing).
   - **IMPORTANT**: Use the configured language for ALL outputs: 'en' → English, 'zh' → 中文. This applies to: report text, section headings, dimension names, improvement suggestions, status messages, and error descriptions.

## Operating Constraints

**STRICTLY READ-ONLY**: Do **not** create, modify, or delete any project files. The sole exception is writing the report file when the user explicitly requests `"output to file"`.

## Evidence Model

Mobile repos are typically **enterprise internal**. Some controls live on the **code platform** rather than in the repo clone.

1. **Equivalence bundles (OR logic)** — For CI, ownership, etc.: if **any** credible signal is present, treat as **PASS**.

| Capability | Accept if any of these exist |
|---|---|
| CI / pipeline | `.codebase/pipelines/*`, `Jenkinsfile`, `fastlane/`, `Makefile` with CI targets, CI doc in README / AI instructions, Gradle CI tasks, Xcode CI schemes |
| CODEOWNERS / ownership | `CODEOWNERS`, `OWNERS`, ownership doc linking to platform |
| Build scripts | `Makefile`, `fastlane/Fastfile`, `build.sh`, Gradle tasks, Xcode schemes |

2. **Repo vs platform** — If a control only lives on the platform (branch protection, required reviewers, org-level SCA), mark **SKIP (not verifiable from repo)** — **never FAIL** on absence of local files. Note in report: "请在代码平台确认".
3. **Monorepo** — CI/owners/configs may live at repo root or shared config path. Accept the **nearest applicable** config; if inherited from root, PASS with note `inherited from monorepo root`.
4. **SKIP scoring** — Exclude SKIP items from **both** pass count and total for level pass-rate calculation.

## Evaluation Scope

Mobile projects are typically **monorepos** with dozens or hundreds of modules. The readiness assessment operates at two levels:

### Repo-Level (infrastructure)
Evaluates cross-cutting concerns shared by all modules: build system, CI/CD, git practices, repo-root TTADK/MCP configuration. Run once per repo.

### Module-Level (per module)
Evaluates individual module quality: documentation, testing, code organization, AI context. Run per module — this is where most actionable improvements live.

```
MonoRepo/
├── .ttadk/                    ← repo-level: TTADK config
├── .mcp.json                  ← repo-level: MCP config
├── Podfile / build.gradle     ← repo-level: build system
├── Modules/
│   ├── Search/                ← module-level: evaluate independently
│   │   ├── CLAUDE.md
│   │   ├── docs/
│   │   ├── Sources/
│   │   └── Tests/
│   ├── Feed/                  ← module-level: evaluate independently
│   └── Account/               ← module-level: evaluate independently
└── ...
```

When `$ARGUMENTS` contains a module path, run **both** repo-level infrastructure checks and module-level checks scoped to that path. When `--all-modules`, auto-discover modules and produce a summary matrix.

## Tech Stack Adaptation Table

Adapt checks based on detected platform:

| Check | iOS | Android |
|---|---|---|
| Build system | Xcode (`.xcodeproj` / `.xcworkspace`) | Gradle (`build.gradle` / `settings.gradle`) |
| Dependency manager | CocoaPods (`Podfile`) / SPM (`Package.swift`) | Gradle dependencies |
| Lock file | `Podfile.lock` / `Package.resolved` | `gradle.lockfile` (optional) |
| Linter | SwiftLint (`.swiftlint.yml`) | ktlint / detekt |
| Formatter | SwiftFormat | ktfmt / spotless |
| Test framework | XCTest / Quick+Nimble | JUnit / Espresso / Robolectric |
| UI test | XCUITest | Espresso / UIAutomator |
| Source extensions | `.swift`, `.m`, `.mm`, `.h` | `.kt`, `.java` |
| Build automation | `fastlane/`, Xcode schemes | Gradle tasks |
| Gitignore patterns | `DerivedData/`, `Pods/`, `*.xcuserdata` | `.gradle/`, `build/`, `local.properties` |

## Execution Steps

### Step 1 — Determine Scan Scope

**1a. Parse arguments** to decide:
- **Repo-only** (no path argument): scan only repo-level dimensions (D1–D5). Suggest running with module path next.
- **Module-level** (path provided): scan repo-level dimensions + module-level dimensions (D6–D8) scoped to the given module path(s).
- **Batch mode** (`--all-modules`): auto-discover module directories, then run module-level scan for each.

**1b. Module discovery** (for `--all-modules` or when user provides a parent directory):
- Walk the directory tree looking for directories that contain source files (`.swift`, `.m`, `.kt`, `.java`) and are a logical module boundary.
- Heuristic signals for module boundaries:
  - Contains its own `CLAUDE.md` or `README.md`
  - Is a direct child of a well-known container (`Modules/`, `Features/`, `Libraries/`, `Frameworks/`, `Components/`)
  - Has its own build target (`.xcodeproj`, `build.gradle`, `Package.swift`, `BUILD`)
  - Contains `Sources/` or `src/` subdirectory
- Cap at **20 modules** per batch. If more found, pick the 20 largest by file count and note the rest.

**1c. Platform & language detection** (same for all scopes):

| Signal Files | Platform |
|---|---|
| `*.xcodeproj` or `*.xcworkspace` | iOS (Xcode) |
| `Podfile` or `Package.swift` | iOS (CocoaPods / SPM) |
| `build.gradle` or `settings.gradle` | Android (Gradle) |
| Both iOS + Android signals | Cross-platform |

**1d. Load previous reports** from `.ttadk/readiness-history/` for delta comparison.

**1e. Required MCP servers** (determined by platform from 1c):

| Platform | Required MCP Servers |
|---|---|
| Android | `adk-mobile`, `build-ai`, `core-ai`, `d2c4a` |
| iOS | `adk-mobile`, `iOS_context`, `titkok_arch_mcp`, `tiktok_d2c_mcp`, `UI_Wiki` |

**Health-check procedure** (choose based on client):

**Claude Code:**
1. Call `ListMcpResourcesTool` with `server` = `"adk-mobile"`. Response contains `"Available servers: xxx, yyy, zzz"` — the full list of running MCP servers.
2. For each required server, check whether the Available servers list **contains** the server name. Use **substring matching** — actual server names may carry prefixes (e.g. `plugin:common-plugin:core-ai` matches `core-ai`).
3. Present in the list = healthy; absent = not running.

**Cursor:**
1. For each required server, call `CallMcpTool(server="<name>", toolName="_ping")`.
2. Server is running if the response is a normal result **or** "tool not found" error (server alive, tool doesn't exist).
3. Server is not running if the response is "server not found" or connection/timeout error.

### Step 2 — Determine Skip Items

Based on detected platform, mark inapplicable checks as **SKIP**:

| Condition | Auto-SKIP |
|---|---|
| iOS project | Android-specific checks |
| Android project | iOS-specific checks |
| Framework / SDK module | E2E tests, app launch checks |
| Branch protection | **Always SKIP** (platform-side only; see Evidence Model) |
| CI only on platform side | CI-related checks → **SKIP** with note, not FAIL |
| Repo-only scan | Module-level dimensions (D6–D8) |

### Step 3 — Repo-Level Dimensions (D1–D5)

These are evaluated once per repo regardless of module scope.

If `$ARGUMENTS` requests **only specific dimensions**, run checks **only** for those; state clearly in Section A that the run is **partial** and overall Level/Score are **not** comparable to a full scan. Omit headline Level/Score and show per-dimension results only.

#### D1: Context Engineering (Repo Weight 30%, Max 10 pts)

| Check | Type | Level | Points | How to Verify |
|---|---|---|---|---|
| AI instruction files exist | PASS/FAIL | L2 | 3 | Repo-root: `CLAUDE.md`, `.cursorrules`, `.cursor/rules/`, `AGENTS.md`. 1 file = 1pt, 2 = 2pt, 3+ = 3pt |
| AI instruction file quality | Gradient | L3 | 2 | >50 lines = 1pt; contains architecture/conventions/mobile-specific patterns = 2pt |
| TTADK configuration | PASS/FAIL | L2 | 2 | `.ttadk/` exists = 1pt; has `config.json` with mobile preset = 2pt |
| MCP servers running | Gradient | L3 | 2 | Run MCP health-check procedure (see Step 1e). All present = 2pt; ≥50% present = 1pt. Report missing server names |
| Knowledge base coverage | Gradient | L4 | 1 | Module-level `CLAUDE.md` in ≥1 module = 0.5pt; ≥3 modules = 1pt |

#### D2: Build & Dependencies (Repo Weight 20%, Max 10 pts)

| Check | Type | Level | Points | How to Verify |
|---|---|---|---|---|
| Build system configured | PASS/FAIL | L1 | 2 | Xcode project / Gradle build exists and appears functional (see Tech Stack table) |
| Dependency manager | PASS/FAIL | L1 | 2 | CocoaPods/SPM/Gradle configured = 1pt; lock file committed = 2pt (see Tech Stack table) |
| Build commands documented | PASS/FAIL | L2 | 2 | Build/test commands documented in README or AI instructions |
| CI/CD config | PASS/FAIL | L2 | 2 | Use **equivalence bundle** from Evidence Model. Pipeline config exists or documented; **SKIP** if platform-side only (not FAIL) |
| Dependency version pinning | PASS/FAIL | L3 | 2 | No wildcard/latest versions |

#### D3: Style & Validation (Repo Weight 15%, Max 10 pts)

| Check | Type | Level | Points | How to Verify |
|---|---|---|---|---|
| Lint config | PASS/FAIL | L1 | 3 | SwiftLint/ktlint/detekt config exists = 2pt; rules customized = 3pt (see Tech Stack table) |
| Formatter config | PASS/FAIL | L2 | 2 | SwiftFormat/ktfmt or equivalent (see Tech Stack table) |
| Pre-commit hooks | PASS/FAIL | L3 | 2 | Pre-commit or Husky/lint-staged config |
| Interface definitions | PASS/FAIL | L3 | 2 | Protobuf/Thrift/OpenAPI schemas for network APIs |
| Standard patterns | Gradient | L3 | 1 | Documented standard paradigms (MVVM, networking, DI, data flow) in AI instructions or module docs; same problem uses same solution pattern across the codebase |

#### D4: Security & Governance (Repo Weight 15%, Max 10 pts)

| Check | Type | Level | Points | How to Verify |
|---|---|---|---|---|
| .gitignore completeness | PASS/FAIL | L1 | 2 | Covers platform patterns (see Tech Stack table) |
| No hardcoded secrets | PASS/FAIL | L2 | 3 | No API keys/tokens in source = 2pt; uses config/env management = 3pt |
| CODEOWNERS | PASS/FAIL | L3 | 2 | Use **equivalence bundle**: any ownership file or documented alternative |
| Branch protection | SKIP | L3 | 2 | Always SKIP (platform-side); note in report: "请在代码平台确认" |
| Sensitive data protection | PASS/FAIL | L3 | 1 | .cursorignore or AI access controls |

#### D5: SDD Readiness (Repo Weight 20%, Max 10 pts)

| Check | Type | Level | Points | How to Verify |
|---|---|---|---|---|
| TTADK initialized | PASS/FAIL | L3 | 2 | `.ttadk/` with config.json containing mobile preset |
| Required MCPs healthy | Gradient | L3 | 2 | Run MCP health-check (see Step 1e). All present = 2pt; ≥50% = 1pt. Report missing server names |
| Lark CLI available | PASS/FAIL | L2 | 1 | `lark-cli --version` runs successfully. If missing, link to [install doc](https://bytedance.larkoffice.com/docx/WnHkdJQM6oGpQFxm9i7ckVdenSh) |
| Workflow directory ready | PASS/FAIL | L3 | 1 | `.ttadk/.adk-mobile/` exists |
| Specs history | Gradient | L4 | 2 | Saved specs in codebase = 1pt; multiple features or well-organized = 2pt |
| Knowledge base initialized | PASS/FAIL | L4 | 2 | ≥1 module has kb-init-docs output (CLAUDE.md + docs/) |

### Step 4 — Module-Level Dimensions (D6–D8)

These are evaluated **per module**. When multiple modules are specified, run each independently.

The **module root** is the path provided by the user. All checks below are scoped to files within that directory tree.

#### D6: Module Documentation (Module Weight 35%, Max 10 pts)

| Check | Type | Level | Points | How to Verify |
|---|---|---|---|---|
| CLAUDE.md exists | PASS/FAIL | L2 | 2 | `<module>/CLAUDE.md` exists |
| CLAUDE.md quality | Gradient | L3 | 2 | Has Module Overview + Key Classes + References = 2pt; has 2 of 3 = 1pt |
| docs/ folder exists | PASS/FAIL | L3 | 2 | `<module>/docs/` with at least `interface.md` or `workflow.md` |
| docs/ completeness | Gradient | L4 | 2 | All 4 docs (interface, workflow, domain glossary/business terms, rule/standard patterns) = 2pt; 2–3 = 1pt |
| AGENTS.md symlink | PASS/FAIL | L3 | 1 | `<module>/AGENTS.md` exists and points to CLAUDE.md |
| Doc freshness | PASS/FAIL | L4 | 1 | Module docs updated within 180 days (git log) |

#### D7: Module Testing (Module Weight 35%, Max 10 pts)

| Check | Type | Level | Points | How to Verify |
|---|---|---|---|---|
| Test files exist | PASS/FAIL | L1 | 2 | Test files found within or alongside the module |
| Test coverage ratio | Gradient | L2 | 2 | Test file count / source file count: >10% = 1pt; >20% = 2pt |
| Test quality | Gradient | L3 | 2 | Tests have meaningful assertions (not just compilation checks) = 1pt; cover key entry points = 2pt |
| Code testability | Gradient | L3 | 1 | DI framework or protocol-based injection used; key dependencies mockable without modifying production code |
| UI / Integration tests | PASS/FAIL | L3 | 1 | UI test targets exist for this module (XCUITest / Espresso) |
| Evals defined | PASS/FAIL | L4 | 2 | `<module>/docs/evals/evals.json` exists with questions = 2pt; exists = 1pt |

#### D8: Module Code Organization (Module Weight 30%, Max 10 pts)

AI-Friendly design principle: code should be **findable in one read** and **writable with minimal context**. Checks below evaluate semantic clarity, structure navigability, and generation-friendliness.

| Check | Type | Level | Points | How to Verify |
|---|---|---|---|---|
| Clear module interface | PASS/FAIL | L1 | 2 | Public interface / API boundary clearly defined = 1pt; documented in docs/interface.md = 2pt |
| Feature-based organization | Gradient | L2 | 2 | Code organized by feature vertically (related UI/state/data in same package, not split by technical layer) = 1pt; module describable in one sentence (high cohesion) = 2pt |
| Naming semantics | Gradient | L2 | 1 | Names express `[Object][Action][Scope]` (e.g. `HomeViewModel`, `loadCommentList()`); no vague names (`handle`, `process`, `common`, `helper`, `manager` without qualifier) |
| File granularity | Gradient | L2 | 1 | Avg file <400 lines = 0.5pt; no files >2000 lines and files >600 lines <10% = 1pt |
| Comment coverage | Gradient | L3 | 2 | Public API doc comments ≥50% = 1pt; ≥80% = 2pt |
| Complexity | Gradient | L3 | 2 | No files >1000 lines = 1pt; control flow nesting depth ≤ 3 (use early return) = 2pt |

### Step 5 — Calculate Dual-Track Scores

**5a. Maturity Level (L1–L5)**

For each level L1 through L5, collect all check items tagged with that level:
- Let **applicable** = all items at that level that are **not** SKIP
- Pass rate = (count of **PASS** among applicable) / (count of **applicable**)
- Level N is unlocked if **all levels ≤ N** have pass rate ≥ **80%**
- Current Level = highest unlocked level

**5b. Weighted Percentage Score (0–100)**

Repo-level and module-level scores are calculated independently, then blended:

```
Repo Score   = Σ (dimension_points / dimension_max_points × repo_weight × 100)
Module Score = Σ (dimension_points / dimension_max_points × module_weight × 100)
```

For each dimension, `dimension_points` = sum of points from **non-SKIP** checks; `dimension_max_points` = sum of max points for those **same non-SKIP** checks (SKIP rows excluded from both).

Repo dimension weights (sum to 100%):

| Dimension | Weight |
|---|---|
| D1 Context Engineering | 30% |
| D2 Build & Dependencies | 20% |
| D3 Style & Validation | 15% |
| D4 Security & Governance | 15% |
| D5 SDD Readiness | 20% |

Module dimension weights (sum to 100%):

| Dimension | Weight |
|---|---|
| D6 Module Documentation | 35% |
| D7 Module Testing | 35% |
| D8 Module Code Organization | 30% |

**5c. Combined Score** (for module scans):

```
Combined Score = Repo Score × 0.4 + Module Score × 0.6
```

- **Repo-only scan**: report Repo Score only.
- **Batch mode** (`--all-modules`): calculate per-module Combined Scores and a summary matrix.

### Step 6 — Generate Report

Use the language from `preferred_language`.

If `$ARGUMENTS` includes **target L*N***: prioritize Section D/G/H on gaps that block reaching L*N*; you may shorten lower-priority sections.

---

**Section A: Overview**

For **repo-only scan** (no module path):

```
# Mobile AI Development Readiness Report (Repo Infrastructure)

| Field       | Value                        |
|-------------|------------------------------|
| Project     | <project-name>               |
| Platform    | <iOS/Android/Cross-platform> |
| Date        | <today>                      |
| Level       | **L<N>**                     |
| Infra Score | **<score>/100**              |

⚠️ This is a repo-level infrastructure scan only.
Run `/adk:readiness <ModulePath>` to evaluate specific modules.
Run `/adk:readiness --all-modules` to batch-evaluate all discovered modules.
```

For **single module scan**:

```
# Mobile AI Development Readiness Report

| Field        | Value                        |
|--------------|------------------------------|
| Project      | <project-name>               |
| Module       | <module-path>                |
| Platform     | <iOS/Android>                |
| Date         | <today>                      |
| Level        | **L<N>**                     |
| Repo Score   | **<repo-score>/100**         |
| Module Score | **<module-score>/100**       |
| Combined     | **<combined>/100**           |
```

For **partial scan** (specific dimensions only): omit Level/Score and add:

```
⚠️ Partial scan (dimensions: <list>). Overall Level/Score not comparable to a full scan.
```

**Section B: Maturity Level Progress**

Show a progress bar for each level (L1–L5) with percentage and pass/fail indicator:

```
L1 Functional     ████████████ 100%  ✅
L2 Documented     █████████░░░  82%  ✅  ← Current
L3 Standardized   ██████░░░░░░  55%     ← Target (need N more)
L4 Optimized      ███░░░░░░░░░  28%
L5 Autonomous     █░░░░░░░░░░░   8%
```

**Section C: Strengths**

List top 3 highest-scoring dimensions with percentage and key findings.

**Section D: Opportunities**

List the specific checks needed to unlock the next level.

**Section E: Score Summary Table**

| # | Dimension | Score | Pass Rate | Key Finding |
|---|-----------|-------|-----------|-------------|
| D1 | Context Engineering | X/10 | X/X | ... |
| ... | ... | ... | ... | ... |

**Section F: All Criteria (Detailed)**

For each dimension, list every check item with:
- ✓ / ✗ / — (pass / fail / skip) prefix
- Check name
- Points earned / max
- Brief explanation

Include **Quick Wins** under dimensions with easy improvements.

Example:
```
### D1: Context Engineering 3/10 (2/5 pass)

✓ ttadk_configuration    1/2  .ttadk/ directory with config.json present
✗ ai_instruction_files   0/3  No CLAUDE.md, .cursorrules, or AGENTS.md found
✓ mcp_servers_running    1/2  adk-mobile running; missing: build-ai, core-ai, d2c4a
✗ ai_file_quality        0/2  No AI instruction files to evaluate
✗ knowledge_base         0/1  No module-level CLAUDE.md found

**Quick Wins:**
- Create `CLAUDE.md` with project overview (+3 pts)
- Start missing MCP servers (+1 pt)
```

**Section G: Top Recommendations**

Provide a prioritized table:

| # | Priority | Action | Impact | Effort | Level |
|---|----------|--------|--------|--------|-------|
| 1 | CRITICAL | ... | +X pts | time | → LN |

Priority levels:
- **CRITICAL**: Blocks current level unlock, highest ROI (> 10 pts impact)
- **HIGH**: Required for next level (5–10 pts)
- **MEDIUM**: Score improvement (2–5 pts)
- **LOW**: Future-facing, low urgency (< 2 pts)

Link improvement suggestions to ADK commands where applicable.

**Section H: Roadmap to Next Level**

```
Current: **LN** → Target: **L(N+1)** (<level-name>)

### Must-fix (X items to unlock L(N+1)):
1. ✗ check_name — concrete remediation command or action
...

### Estimated effort: ~X hours
### Expected result: L(N+1) unlocked, score X → Y+
```

**Batch Module Report (--all-modules)**

After per-module details, append a **Module Comparison Matrix**:

```
## Module Comparison Matrix

| Module | Doc | Test | Code Org | Module Score | Level |
|--------|-----|------|----------|-------------|-------|
| Modules/Search | 8/10 | 6/10 | 7/10 | 72 | L3 |
| Modules/Feed | 3/10 | 4/10 | 5/10 | 41 | L1 |
| Modules/Account | 6/10 | 7/10 | 8/10 | 68 | L2 |
| ... | | | | | |

### Summary
- Modules evaluated: N
- Average module score: X/100
- Highest: <module> (X/100)
- Lowest: <module> (X/100)
- Modules below L2: N (need attention)
```

### Step 7 — Output

- **Default**: Print report to console. Do NOT write files automatically.
- **Compare mode**: Append a **Change Since Last Report** section showing score deltas and criteria status changes.

### Step 8 — Ask Whether to Save Report

After printing, **ask the user** whether to save:

1. **File path**: `.ttadk/readiness-report.md` (latest) + `.ttadk/readiness-history/readiness-<YYYY-MM-DD>.md` (timestamped)
2. **Purpose**: Enables future `"compare with last run"`, historical tracking, sharing with team

**Do NOT write any file unless the user explicitly confirms.** If `$ARGUMENTS` already contained `"output to file"`, treat as confirmation.

## Next Step Guidance

### If Level < L2:
- **Priority**: Create `CLAUDE.md` at repo root with project overview and conventions
- Ensure basic build/test infrastructure is in place
- Run `ttadk init -p ttadk/ios` or `ttadk/android` to initialize TTADK config

### If Level = L2, targeting L3:
- Focus on the **Must-fix** items in the Roadmap section
- Typical gaps: pre-commit hooks, MCP servers not all running, module-level docs missing
- Start knowledge base: `/kb-init-docs --analysis <path>` on key modules

### If Level = L3, targeting L4:
- Expand module-level documentation coverage
- Add evals: `kb-evals-creator` for evaluation questions
- Build up specs history with `/adk:sdd:new`
- Validate existing docs: `kb-docs-validator`

### If Level ≥ L4:
- Focus on autonomous operation: high test coverage, comprehensive docs
- Periodically re-run readiness to track trends
- Iterate: init docs → validate → benchmark → improve → re-assess

### Module-level improvements:
- No CLAUDE.md → `/kb-init-docs <module-path>`
- Outdated docs → `/kb-update-docs <module-path>`
- No evals → `kb-evals-creator`
- Validate docs → `kb-docs-validator`

### MCP not running:
- Refer to troubleshooting knowledge base ("MCP 连接问题" section) for per-server troubleshooting steps

### Batch improvement strategy:
1. Start with the **lowest-scoring modules** that are **most actively developed**
2. Run `kb-init-docs --analysis <top-level-path>` to auto-suggest doc roots
3. Iterate: init docs → validate → benchmark → improve → re-assess

### Re-assessment:
- After improvements, re-run `/adk:readiness <module-path>` to verify
- Use `"compare with last run"` for delta tracking

## Token Efficiency Strategy

1. **Batch file-existence checks**: list directories first
2. **Progressive depth**: existence → quality reads
3. **Sample, don't exhaust**: 10–20 representative files per module for quality checks
4. **Early termination**: skip deep inspection if dimension is clearly 0 or max
5. **Module scan cap**: max 20 modules per batch to control cost
6. **Avoid reading large files entirely**: for file size checks, use line counts; for quality checks, read only the first 50–100 lines

