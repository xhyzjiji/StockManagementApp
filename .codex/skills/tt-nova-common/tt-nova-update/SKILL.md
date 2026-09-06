---
name: tt-nova-update
description: "One-click update all TT Nova skills (API, UI, DataGen, Common) via AgentBuddy CLI. Use when the user wants to update tt-nova skills, refresh tt-nova collections, or mentions \"update tt-nova\", \"upgrade tt-nova\", \"tt-nova update\", \"tt-nova upgrade\""
---

# TT Nova Skills Update

One-click update for all TT Nova skill collections.

## Agent Detection

Auto-detect the current agent type from context:
- If running in **Cursor** (system prompt contains "You operate in Cursor") → `cursor`
- If running in **Claude Code** → `claude-code`
- If running in **Trae** → `trae`
- Other agents follow the same pattern, use the corresponding agent identifier

If the user explicitly specifies an agent name, use that instead.

## Execution

Run all four commands **sequentially** in a single shell. Each command uses:
- `npm_config_registry="https://bnpm.byted.org"` — ByteDance internal npm registry
- `-y` — auto-confirm prompts
- `-a <agent>` — auto-detected or user-specified agent

```bash
AGENT="<auto-detected-or-user-specified>"

echo "=== [1/4] Updating TT Nova API ==="
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-api -a "$AGENT" -y

echo "=== [2/4] Updating TT Nova UI ==="
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-ui -a "$AGENT" -y

echo "=== [3/4] Updating TT Nova DataGen ==="
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-datagen -a "$AGENT" -y

echo "=== [4/4] Updating TT Nova Common ==="
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-common -a "$AGENT" -y

echo "=== All TT Nova skills updated! ==="
```

The `AGENT` variable should be auto-detected from the current environment. Only ask the user if detection is ambiguous.

## Notes

- Requires Node.js / npm available in PATH.
- Commands need network access to `bnpm.byted.org` — request `full_network` permission when running via Shell tool.
- If any collection fails, continue with the remaining ones and report the failure at the end.
