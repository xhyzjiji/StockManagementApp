#!/usr/bin/env node
'use strict';

/**
 * Mobile SDT stage-event log + phase-gate helper.
 *
 * Local equivalent of the SDD server-side phase gate ("without persisted phase_approved
 * the server rejects the phase"): each SDT stage appends an event to
 * `FEATURE_DIR/test/events.jsonl`, bound to the sha256 of `test/case.md` at that moment.
 * Downstream stages gate on the prior stage's persisted event; editing `case.md` after
 * an approval changes its sha and invalidates the approval (stale) — matching SDD's
 * "changing the approved artifact invalidates the approval".
 *
 * Event chain (mirrors the SDD events.jsonl lastEvent semantics):
 *   ff_generated → clarify_approved → implement_completed → report_reviewed
 * 审核可选：从未 clarify（missing）放行；批准一旦存在即 sha 绑定，之后改了 case.md（stale）
 * 才拦 —— 判据在 check-prerequisites.js，这里只负责算状态。其余事件为审计/路由完整性存在。 `report_reviewed`
 * records the human's verdict on test/report.md (same dashboard approval surface as
 * case.md — see adk-sdt-implement Step 4).
 *
 * Division of labor vs sibling scripts:
 *   - sdt-track.js  = usage TELEMETRY (best-effort API reporting; failures never block)
 *   - sdt-events.js = local WORKFLOW STATE (gate source of truth; must be reliable)
 *
 * This is a guard against agents skipping stages, not a security boundary: with no
 * server involved, a hostile writer could forge events — SKILL.md forbids recording
 * approvals outside the clarify flow.
 *
 * CLI:
 *   node sdt-events.js record       --feature-dir <dir> --event <name> [--extra '<json>']
 *   node sdt-events.js gate-clarify --feature-dir <dir>
 *
 * Also exported for `require()` by check-prerequisites.js.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const KNOWN_EVENTS = ['ff_generated', 'clarify_approved', 'implement_completed', 'report_reviewed'];

function caseFilePath(featureDir) {
  return path.join(featureDir, 'test', 'case.md');
}

function eventsFilePath(featureDir) {
  return path.join(featureDir, 'test', 'events.jsonl');
}

/** sha256 of test/case.md, or null when it does not exist. */
function computeCaseSha(featureDir) {
  try {
    return crypto.createHash('sha256').update(fs.readFileSync(caseFilePath(featureDir))).digest('hex');
  } catch {
    return null;
  }
}

/** Parse test/events.jsonl into an array of event objects (skips blank/malformed lines). */
function readEvents(featureDir) {
  let raw;
  try {
    raw = fs.readFileSync(eventsFilePath(featureDir), 'utf-8');
  } catch {
    return [];
  }
  const events = [];
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      events.push(JSON.parse(trimmed));
    } catch {
      /* skip malformed line */
    }
  }
  return events;
}

/**
 * Append an event (bound to the current case.md sha) to test/events.jsonl.
 * Refuses to record when case.md does not exist — an event with a null sha could
 * never match a future gate check and would only mislead audits.
 */
function recordEvent(featureDir, eventName, extra) {
  if (!KNOWN_EVENTS.includes(eventName)) {
    throw new Error(`unknown event "${eventName}" (expected one of: ${KNOWN_EVENTS.join(', ')})`);
  }
  const caseSha = computeCaseSha(featureDir);
  if (!caseSha) {
    throw new Error(`cannot record "${eventName}": ${caseFilePath(featureDir)} does not exist`);
  }
  const file = eventsFilePath(featureDir);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  // Controlled fields land LAST so `--extra` cannot overwrite them. With the old
  // order, `--extra '{"case_sha":"<current sha>"}'` re-armed the clarify gate for a
  // case.md that had been edited after approval — the one thing checkClarifyGate
  // exists to catch, and the reason three SKILL.md sections forbid hand-writing
  // clarify_approved. `extra` keeps its extension role for everything else.
  const event = Object.assign(
    {},
    extra || {},
    {
      event: eventName,
      ts: new Date().toISOString(),
      case_sha: caseSha,
    }
  );
  fs.appendFileSync(file, JSON.stringify(event) + '\n');
  return event;
}

/**
 * Gate check for the `adk-sdt-implement` skill.
 * Returns { ok, reason, approvedSha?, currentSha }.
 *   reason: 'ok' | 'no_case' | 'missing' (never clarified) | 'stale' (case.md edited after clarify)
 */
function checkClarifyGate(featureDir) {
  const currentSha = computeCaseSha(featureDir);
  if (!currentSha) return { ok: false, reason: 'no_case', currentSha: null };

  let approved = null;
  for (const e of readEvents(featureDir)) {
    if (e && e.event === 'clarify_approved') approved = e; // latest wins
  }
  if (!approved) return { ok: false, reason: 'missing', currentSha };
  if (approved.case_sha !== currentSha) {
    return { ok: false, reason: 'stale', approvedSha: approved.case_sha, currentSha };
  }
  return { ok: true, reason: 'ok', currentSha };
}

module.exports = {
  caseFilePath,
  eventsFilePath,
  computeCaseSha,
  readEvents,
  recordEvent,
  checkClarifyGate,
};

if (require.main === module) {
  const args = process.argv.slice(2);
  const cmd = args[0];
  const getOpt = (name) => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : undefined;
  };
  try {
    const featureDir = getOpt('--feature-dir');
    if (!featureDir) throw new Error('--feature-dir is required');

    if (cmd === 'record') {
      const event = getOpt('--event');
      if (!event) throw new Error('--event is required');
      let extra;
      const rawExtra = getOpt('--extra');
      if (rawExtra) {
        try {
          extra = JSON.parse(rawExtra);
        } catch {
          throw new Error('--extra must be valid JSON');
        }
      }
      console.log(JSON.stringify(recordEvent(featureDir, event, extra)));
    } else if (cmd === 'gate-clarify') {
      const result = checkClarifyGate(featureDir);
      console.log(JSON.stringify(result));
      // 与 check-prerequisites 同一口径：`missing` 是正当状态，不是失败的调用。
      // 这里退非零会让「审核可选」在两个入口给出相反答案。
      if (result.reason === 'no_case' || result.reason === 'stale') process.exit(1);
    } else {
      throw new Error(`unknown command: ${cmd || '(none)'} (use: record | gate-clarify)`);
    }
  } catch (err) {
    console.error(JSON.stringify({ error: err instanceof Error ? err.message : String(err) }));
    process.exit(1);
  }
}
