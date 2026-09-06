#!/usr/bin/env node
"use strict";

/**
 * SDT skill-level usage tracking CLI.
 *
 * Design notes from the SDT tracking discussion:
 * - The metric granularity is one Skill execution, not one LLM/model call. This keeps
 *   the data model small and avoids coupling the SDT workflow to host-specific model
 *   telemetry details.
 * - The table fields are intentionally minimal: skill name/family/stage, git user,
 *   agent runtime, start/end/duration, and explicitly supplied extra JSON.
 *   Token usage is deliberately excluded because an SDT prompt cannot reliably obtain
 *   the host's actual model usage.
 * - Standalone business events (for example, a fix confirmation) use the `event`
 *   command rather than a zero-duration Skill run. Events are immediately reported,
 *   do not create local run state, and carry event_name/event_time instead.
 * - skill_family and the default stage are derived from skill_name so SDT prompts do
 *   not need to repeat static metadata on every execution.
 * - stage can still be overridden with --stage for special cases such as fix_confirm,
 *   where the business event is more specific than the base skill name.
 * - extra is never auto-collected. It is null unless the caller explicitly passes
 *   --extra '{"fixed_issue_count":3,...}'. This avoids hidden environment collection
 *   and keeps the usage event predictable.
 * - user_name is read from git config user.name. If that is unavailable, it falls back
 *   to git config user.email. We do not cache identity because git config is already
 *   the chosen lightweight source of truth for this telemetry.
 * - Reporting must never block the SDT workflow. API failures are printed as warnings
 *   on stderr and the command still exits successfully unless the CLI input itself is
 *   invalid.
 *
 * Typical prompt usage:
 *   node "$SDT_ASSET_ROOT/scripts/sdt-track.js" start --skill-name qa-sdt-ff
 *   node "$SDT_ASSET_ROOT/scripts/sdt-track.js" finish --run-id <id>
 *
 * Placeholder API:
 * - The default reporting host is https://hp6ndm0q.sg-fn.tiktok-row.net. Run
 *   lifecycle requests are posted to /v1/sdt/runs and standalone events to
 *   /v1/sdt/events. Set SDT_TRACK_HOST to override the host, or use the
 *   endpoint-specific SDT_TRACK_RUNS_ENDPOINT / SDT_TRACK_EVENTS_ENDPOINT.
 * - Set SDT_TRACK_STATE_DIR to override the local run-state directory; otherwise
 *   state is stored in the user's cache area:
 *     macOS:   ~/Library/Caches/ttadk/sdt-track/runs
 *     Windows: %LOCALAPPDATA%/ttadk/sdt-track/runs
 *     Linux:   ${XDG_CACHE_HOME:-~/.cache}/ttadk/sdt-track/runs
 *   This avoids creating telemetry state files inside the user's project repo.
 * - Until the real endpoint contract is finalized, this script stores start state
 *   locally and no-ops the remote report when the endpoint/host is explicitly empty.
 *   Opt out with any of: SDT_TRACK_HOST="", SDT_TRACK_ENDPOINT="",
 *   SDT_TRACK_RUNS_ENDPOINT="" / SDT_TRACK_EVENTS_ENDPOINT="". Unset (as opposed to
 *   set-but-empty) keeps the default host — hence `??` rather than `||` in
 *   resolveEndpoint; `||` treated "" as absent and reported anyway.
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const https = require("https");
const { randomBytes } = require("crypto");
const { execFileSync } = require("child_process");

const STATE_DIR = process.env.SDT_TRACK_STATE_DIR || getDefaultStateDir();
const DEFAULT_TIMEOUT_MS = 3000;
const DEFAULT_TRACK_HOST = "https://hp6ndm0q.sg-fn.tiktok-row.net";

const SKILL_META = {
  "adk-sdt": { skill_family: "adk-sdt", stage: "entry" },
  "adk-sdt-ff": { skill_family: "adk-sdt", stage: "ff" },
  "adk-sdt-implement": { skill_family: "adk-sdt", stage: "implement" },
  "adk-sdt-clarify": { skill_family: "adk-sdt", stage: "clarify" },
  "adk-sdt-feedback-loop": { skill_family: "adk-sdt", stage: "feedback_loop" },
  "adk-sdt-learning": { skill_family: "adk-sdt", stage: "learning" },

  "qa-sdt": { skill_family: "qa-sdt", stage: "entry" },
  "qa-sdt-specify": { skill_family: "qa-sdt", stage: "specify" },
  "qa-sdt-ff": { skill_family: "qa-sdt", stage: "ff" },
  "qa-sdt-implement": { skill_family: "qa-sdt", stage: "implement" },
  "qa-sdt-clarify": { skill_family: "qa-sdt", stage: "clarify" },
  "qa-sdt-tasks": { skill_family: "qa-sdt", stage: "tasks" },
  "sdt-assets-collect": { skill_family: "qa-sdt", stage: "assets_collect" },
};

function parseArgs(argv) {
  const result = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) {
      result._.push(arg);
      continue;
    }

    const key = arg.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      result[key] = true;
      continue;
    }

    result[key] = next;
    i += 1;
  }
  return result;
}

function printUsage() {
  console.log(`Usage:
  sdt-track start --skill-name <skill> [--run-id <id>] [--stage <stage>] [--agent-runtime <runtime>] [--extra <json>]
  sdt-track finish --run-id <id> [--extra <json>]
  sdt-track event --skill-name <skill> --event-name <name> [--stage <stage>] [--agent-runtime <runtime>] [--extra <json>]

Examples:
  node sdt-track.js start --skill-name qa-sdt-ff --agent-runtime cursor
  node sdt-track.js start --skill-name qa-sdt-implement --stage fix_confirm --extra '{"fixed_issue_count":3,"remaining_issue_count":1,"issue_source":"case_review"}'
  node sdt-track.js finish --run-id sdt_abc
  node sdt-track.js event --skill-name qa-sdt-implement --event-name fix_confirm --extra '{"fixed_issue_count":3,"remaining_issue_count":1,"issue_source":"case_review"}'
`);
}

function fail(message) {
  console.error(`sdt-track: ${message}`);
  process.exitCode = 1;
}

function warn(message) {
  console.error(`sdt-track warning: ${message}`);
}

function nowIso() {
  return new Date().toISOString();
}

function getDefaultStateDir() {
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Caches", "ttadk", "sdt-track", "runs");
  }

  if (process.platform === "win32") {
    return path.join(
      process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"),
      "ttadk",
      "sdt-track",
      "runs",
    );
  }

  return path.join(
    process.env.XDG_CACHE_HOME || path.join(os.homedir(), ".cache"),
    "ttadk",
    "sdt-track",
    "runs",
  );
}

function generateRunId() {
  const time = Date.now().toString(36);
  const random = randomBytes(8).toString("hex");
  return `sdt_${time}_${random}`;
}

function generateEventId() {
  const time = Date.now().toString(36);
  const random = randomBytes(8).toString("hex");
  return `sdt_evt_${time}_${random}`;
}

function toNumber(value, defaultValue) {
  if (value === undefined || value === null || value === "") {
    return defaultValue;
  }
  const numberValue = Number(value);
  return Number.isFinite(numberValue) && numberValue >= 0 ? Math.floor(numberValue) : defaultValue;
}

function parseExtra(rawExtra) {
  if (rawExtra === undefined || rawExtra === null || rawExtra === "") {
    return null;
  }
  try {
    const parsed = JSON.parse(rawExtra);
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("extra must be a JSON object");
    }
    return parsed;
  } catch (error) {
    throw new Error(`invalid --extra JSON: ${error.message}`);
  }
}

function runGitConfig(key) {
  try {
    const value = execFileSync("git", ["config", key], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    return value || null;
  } catch (_error) {
    return null;
  }
}

function getUserName() {
  return runGitConfig("user.name") || runGitConfig("user.email");
}

function getAgentRuntime(value) {
  // Prompts should pass --agent-runtime explicitly (cursor, claude_code, codex,
  // etc.). SDT_AGENT_RUNTIME is provided as a host-level fallback for wrappers.
  return value || process.env.SDT_AGENT_RUNTIME || null;
}

function getSkillMeta(skillName, stageOverride) {
  const known = SKILL_META[skillName];
  if (known) {
    return {
      skill_family: known.skill_family,
      stage: stageOverride || known.stage,
    };
  }

  const inferredFamily = skillName && skillName.startsWith("qa-sdt") ? "qa-sdt"
    : skillName && skillName.startsWith("adk-sdt") ? "adk-sdt"
    : "unknown";

  return {
    skill_family: inferredFamily,
    stage: stageOverride || null,
  };
}

function ensureStateDir() {
  fs.mkdirSync(STATE_DIR, { recursive: true });
}

function statePath(runId) {
  return path.join(STATE_DIR, `${runId}.json`);
}

function writeState(event) {
  ensureStateDir();
  fs.writeFileSync(statePath(event.run_id), `${JSON.stringify(event, null, 2)}${os.EOL}`, "utf8");
}

function readState(runId) {
  const filePath = statePath(runId);
  if (!fs.existsSync(filePath)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function deleteState(runId) {
  try {
    fs.unlinkSync(statePath(runId));
  } catch (_error) {
    // Best-effort cleanup only. A stale local state file must not make the SDT
    // workflow fail after the final event has already been prepared.
  }
}

function mergeExtra(startExtra, finishExtra) {
  if (!startExtra && !finishExtra) {
    return null;
  }
  return Object.assign({}, startExtra || {}, finishExtra || {});
}

function postJson(urlString, payload, timeoutMs) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlString);
    const body = JSON.stringify(payload);
    const client = url.protocol === "https:" ? https : http;
    const request = client.request({
      method: "POST",
      protocol: url.protocol,
      hostname: url.hostname,
      port: url.port,
      path: `${url.pathname}${url.search}`,
      headers: {
        "content-type": "application/json",
        "content-length": Buffer.byteLength(body),
      },
      timeout: timeoutMs,
    }, (response) => {
      let responseBody = "";
      response.setEncoding("utf8");
      response.on("data", chunk => {
        responseBody += chunk;
      });
      response.on("end", () => {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve();
          return;
        }
        reject(new Error(`HTTP ${response.statusCode}: ${responseBody}`));
      });
    });

    request.on("timeout", () => {
      request.destroy(new Error(`request timed out after ${timeoutMs}ms`));
    });
    request.on("error", reject);
    request.write(body);
    request.end();
  });
}

/**
 * Explicitly emptying any of the endpoint/host variables DISABLES reporting.
 *
 * `||` treats "" as absent, so `SDT_TRACK_ENDPOINT=""` used to fall through to the
 * hard-coded default host and report anyway — the exact opposite of the opt-out this
 * file's header promises. `??` keeps "set but empty" distinguishable from "unset",
 * which is what makes the opt-out real. Returns null when reporting is disabled.
 */
function resolveEndpoint(event) {
  const isStandaloneEvent = Boolean(event.event_id);
  const configuredEndpoint = isStandaloneEvent
    ? process.env.SDT_TRACK_EVENTS_ENDPOINT
    : process.env.SDT_TRACK_RUNS_ENDPOINT;
  if (configuredEndpoint !== undefined) {
    return configuredEndpoint.trim() ? configuredEndpoint : null;
  }

  // SDT_TRACK_ENDPOINT remains a host-level backwards-compatible alias for
  // older wrapper scripts. New integrations should use SDT_TRACK_HOST.
  const rawHost = process.env.SDT_TRACK_HOST ?? process.env.SDT_TRACK_ENDPOINT ?? DEFAULT_TRACK_HOST;
  if (!rawHost.trim()) return null;
  const host = rawHost.replace(/\/+$/, "");
  return `${host}${isStandaloneEvent ? "/v1/sdt/events" : "/v1/sdt/runs"}`;
}

async function reportUsageEvent(event) {
  const endpoint = resolveEndpoint(event);
  if (!endpoint) {
    return { skipped: true, reason: "reporting disabled (endpoint/host explicitly empty)" };
  }
  await postJson(endpoint, event, toNumber(process.env.SDT_TRACK_TIMEOUT_MS, DEFAULT_TIMEOUT_MS));
  return { skipped: false };
}

async function safeReport(event) {
  try {
    return await reportUsageEvent(event);
  } catch (error) {
    warn(`failed to report usage event: ${error.message}`);
    return { skipped: true, reason: error.message };
  }
}

async function start(args) {
  const skillName = args["skill-name"];
  if (!skillName) {
    fail("start requires --skill-name");
    return;
  }

  let extra;
  try {
    extra = parseExtra(args.extra);
  } catch (error) {
    fail(error.message);
    return;
  }

  const runId = args["run-id"] || generateRunId();
  const startTime = nowIso();
  const meta = getSkillMeta(skillName, args.stage);
  const event = {
    run_id: runId,
    skill_name: skillName,
    skill_family: meta.skill_family,
    stage: meta.stage,
    user_name: getUserName(),
    agent_runtime: getAgentRuntime(args["agent-runtime"]),
    start_time: startTime,
    end_time: null,
    duration_ms: null,
    extra,
  };

  writeState(event);
  await safeReport(event);
  console.log(JSON.stringify({ run_id: runId, event }, null, 2));
}

async function finish(args) {
  const runId = args["run-id"];
  if (!runId) {
    fail("finish requires --run-id");
    return;
  }

  let finishExtra;
  try {
    finishExtra = parseExtra(args.extra);
  } catch (error) {
    fail(error.message);
    return;
  }

  const previous = readState(runId);
  if (!previous) {
    fail(`run state not found for ${runId}`);
    return;
  }

  const endTime = nowIso();
  const event = Object.assign({}, previous, {
    end_time: endTime,
    duration_ms: Math.max(0, new Date(endTime).getTime() - new Date(previous.start_time).getTime()),
    extra: mergeExtra(previous.extra, finishExtra),
  });

  await safeReport(event);
  deleteState(runId);
  console.log(JSON.stringify({ run_id: runId, event }, null, 2));
}

async function event(args) {
  const skillName = args["skill-name"];
  const eventName = args["event-name"];
  if (!skillName) {
    fail("event requires --skill-name");
    return;
  }
  if (!eventName) {
    fail("event requires --event-name");
    return;
  }

  let extra;
  try {
    extra = parseExtra(args.extra);
  } catch (error) {
    fail(error.message);
    return;
  }

  const eventId = args["event-id"] || generateEventId();
  const meta = getSkillMeta(skillName, args.stage || eventName);
  const eventPayload = {
    event_id: eventId,
    event_name: eventName,
    skill_name: skillName,
    skill_family: meta.skill_family,
    stage: meta.stage,
    user_name: getUserName(),
    agent_runtime: getAgentRuntime(args["agent-runtime"]),
    event_time: nowIso(),
    extra,
  };

  // A standalone event deliberately skips writeState/readState: it has no lifecycle
  // or duration and must be sent immediately, even when emitted mid-Skill.
  await safeReport(eventPayload);
  console.log(JSON.stringify({ event_id: eventId, event: eventPayload }, null, 2));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];
  if (args.help || !command) {
    printUsage();
    return;
  }

  if (command === "start") {
    await start(args);
    return;
  }

  if (command === "finish") {
    await finish(args);
    return;
  }

  if (command === "event") {
    await event(args);
    return;
  }

  fail(`unknown command: ${command}`);
  printUsage();
}

main().catch(error => {
  fail(error && error.message ? error.message : String(error));
});
