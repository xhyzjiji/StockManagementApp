---
name: adk-fetch
description: >-
  Fetch Slardar crash stacks, BITS MR diffs, Codebase MR diffs, and Meego tickets.
  Slardar uses a bundled Python script that hits Avocado API directly (no SSO needed); BITS / Codebase go through bitscli; Meego goes through bytedcli.
  On any BITS / Codebase / Meego fetch failure, asks the user via the AskQuestion tool whether to invoke /adk-doctor for an environment + auth check before retrying; user can also skip and fall back to inline install / auth steps.
  After each fetch (success or failure), best-effort log a custom event via the user-adk-mobile MCP `log` tool (point=adk-fetch) reporting resource type and outcome.
  Triggers when the user pastes a slardar / sladar URL, a bits devops/code/detail link, a code.byted.org merge_requests URL, or a meego ticket URL.
---

# adk-fetch (Slardar / BITS / Codebase / Meego)

> **Language rule**: reply to the user in **Chinese by default** throughout this skill. Switch to English only when the user's triggering message (or the surrounding conversation) is in English. 

---

## CLI Responsibilities

| Resource | Tool |
|----------|------|
| Slardar crash stack | bundled Python script (no CLI needed) |
| BITS MR | `bitscli` |
| Codebase MR | `bitscli` |
| Meego ticket | `bytedcli` (only used for this) |

## Failure handling (global)

When **any** resource fetch fails, before any inline retry, ask the user via the `AskQuestion` tool (MCQ, single-select) whether to delegate to `/adk-doctor` for an environment & auth check. Pick the `/adk-doctor` prompt by resource type:

| Resource | `/adk-doctor` prompt |
|----------|----------------------|
| BITS MR / Codebase MR | `"帮我做 CLI 检查"` (covers bitscli + Codebase auth) |
| Meego | `"帮我做 Meego 环境检查"` |
| Slardar | N/A — Slardar uses no CLI / auth; skip this prompt and go straight to that section's own "Failure handling" table |

### AskQuestion template

```yaml
prompt: |
  Failed to fetch the {resource_type} resource (`{url}`).
  Error: {short_error}

  Run /adk-doctor to check the environment and auth for this resource?
options:
  - id: run_doctor
    label: Yes — invoke /adk-doctor with "{resource_doctor_prompt}", then retry this fetch
  - id: skip
    label: No — show me the raw error and the inline install/auth steps so I can fix it myself
```

- `run_doctor` → invoke `/adk-doctor` with the mapped prompt; after the user replies **done**, retry the original fetch once.
- `skip` → fall back to:
  - BITS / Codebase → the "bitscli install & auth (inline fallback)" section below
  - Meego → relay the raw `bytedcli` error to the user; they can fix manually or invoke `/adk-doctor` later themselves
  - Slardar → the section's own "Failure handling" table

### bitscli install & auth (inline fallback for `skip`)

```bash
npm install -g @byted/bits-cli --registry=https://bnpm.byted.org
bitscli update

# Codebase auth (required for mr diff)
bitscli codebase auth login
# Or: _jwt=$(npx --registry=https://bnpm.byted.org -y skills get-codebase-jwt 2>/dev/null) && bitscli codebase auth login --jwt "$_jwt"
```

---

## Telemetry (mandatory per call, best-effort)

For every resource fetch (success or failure), call the `log` tool of the `user-adk-mobile` MCP to report one `custom` event, using the fixed point name `adk-fetch`.

**How**: MCP server = `user-adk-mobile`, tool = `log`.

**Params**:

| Field | Value |
|-------|-------|
| `specName` | current active spec (e.g. `001-feature-name`); fall back to `001-adk-byted-cli-log` if no spec context |
| `event` | `"custom"` |
| `phase` | current phase (`requirements` / `design` / `tasks` / `implementation`); fall back to `"implementation"` if no context |
| `data.point` | `"adk-fetch"` (fixed) |
| `data.resourceType` | `"slardar"` / `"bits-mr"` / `"codebase-mr"` / `"meego"` / `"unknown"` |
| `data.url` | original user-provided URL |
| `data.success` | `true` / `false` |
| `data.error` | short error message on failure (omit on success) |

- Send telemetry after each resource fetch completes; **do not block** the main flow in parallel.
- Batch fetches → report one event per resource.
- `log` tool unavailable / throws → ignore silently, do not affect the resource return.

---

## 1. Slardar crash stack (bundled script, no SSO)

**URL pattern**: `slardar*.tiktok-row.net/...#/abnormal/detail/{type}/{hash}?aid=...&os=...&region=...`

The script `slardar_fetch.py` lives in the same directory as this SKILL.md. Run it directly:

```bash
python3 <skill_dir>/slardar_fetch.py "<SLARDAR_URL>" > slardar-log.json
```

`<skill_dir>` = this skill's root (the directory containing this SKILL.md).

**Key output fields**:

| Path | Meaning |
|------|---------|
| `data.title` | issue title |
| `data.reason` | crash reason |
| `data.app_version` | version |
| `data.backtrace_count` | number of frames |
| `data.backtrace_pretty[]` | human-readable stack (show first 30–40 lines) |

**Failure handling**:

| Symptom | Action |
|---------|--------|
| `HTTP 4xx/5xx` | check URL completeness (must include `aid`, `os`, `region`, and `#/abnormal/detail/...`) |
| `backtrace_count == 0` | the script auto-retries `--blame`; if still empty, ask the user whether the URL includes an `event_index` parameter |
| `Unsupported fragment` | ask the user for the full detail-page URL |

---

## 2. BITS MR — code/detail URL

**URL pattern**: `https://bits.bytedance.net/devops/{spaceId}/code/detail/{mrId}`

**Flow**: `space_detail` resolves the repo → `get_single_mr` gets the Codebase `iid` → `codebase mr diff` fetches the diff.

### Resolve variables (run once before each diff command)

```bash
URL="https://bits.bytedance.net/devops/1500037378/code/detail/7913735"
MR_ID=$(echo "$URL" | sed -n 's|.*/detail/\([0-9]*\).*|\1|p')
REPO=$(bitscli devops mobile space_detail --code-url "$URL" \
  | jq -r '.space.extra | fromjson | .gitUrl' | sed 's|https://code.byted.org/||')
IID=$(bitscli devops mobile get_single_mr --mr-id "$MR_ID" | jq -r '.mr.iid')
```

| Variable | Source | Example |
|----------|--------|---------|
| `MR_ID` | URL path `/detail/{id}` | `7913735` |
| `REPO` | `space_detail` → `extra.gitUrl` | `ugc/TikTok` |
| `IID` | `get_single_mr` → `mr.iid` | `254364` |

> Repo path varies by Bits space; always resolve dynamically via `space_detail` → `extra.gitUrl`.

### Diff summary (file list + line counts)

```bash
bitscli codebase mr diff -N "$IID" -R "$REPO" --stat
```

### Full diff (unified, with line numbers)

```bash
bitscli codebase mr diff -N "$IID" -R "$REPO" --unified
```

### Filter by directory (optional, matches Bits page cr_tab module paths)

```bash
bitscli codebase mr diff -N "$IID" -R "$REPO" \
  --file "Modules/TikTokFeed/AWEFeed/" --unified
```

### MR metadata (optional)

```bash
bitscli devops mobile get_single_mr --mr-id "$MR_ID"
bitscli codebase mr view -N "$IID" -R "$REPO"
```

---

## 3. Codebase MR — merge_requests URL

**URL pattern**: `https://code.byted.org/{group}/{repo}/merge_requests/{iid}`

Extract `REPO` and `IID` from the URL path and call `codebase mr` directly:

```bash
REPO="ugc/TikTok"   # extracted from URL path
IID=254364          # the number after merge_requests

# MR metadata
bitscli codebase mr view -N "$IID" -R "$REPO"

# Diff summary
bitscli codebase mr diff -N "$IID" -R "$REPO" --stat

# Full diff
bitscli codebase mr diff -N "$IID" -R "$REPO" --unified

# Filter by file / directory
bitscli codebase mr diff -N "$IID" -R "$REPO" --file "path/to/dir/" --unified
```

---

## 4. Meego ticket

```bash
bytedcli --json meego workitem get --url "<MEEGO_URL>"
```

**Failure handling**: see [Failure handling (global)](#failure-handling-global).
