#!/usr/bin/env node
'use strict';
/**
 * Regression tests for the SDT runtime scripts (MR !1781 review).
 * Node built-ins only, no test runner — run: node sdt-scripts.test.js
 *
 * Covers the two Major findings, both of which were "the guard exists but a
 * side door bypasses it" bugs that no amount of reading the happy path reveals.
 */
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const HERE = __dirname;
const EVENTS = path.join(HERE, 'sdt-events.js');
let failures = 0;
const test = (name, fn) => {
  try { fn(); console.log(`  ok   — ${name}`); }
  catch (e) { failures++; console.log(`  FAIL — ${name}\n         ${e.message.split('\n')[0]}`); }
};
const mkFeature = (caseBody) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sdt-test-'));
  fs.mkdirSync(path.join(dir, 'test'));
  fs.writeFileSync(path.join(dir, 'test', 'case.md'), caseBody);
  return dir;
};
const record = (dir, args) =>
  JSON.parse(execFileSync('node', [EVENTS, 'record', '--feature-dir', dir, ...args], { encoding: 'utf-8' }));
const gate = (dir) => {
  try { return JSON.parse(execFileSync('node', [EVENTS, 'gate-clarify', '--feature-dir', dir], { encoding: 'utf-8' })); }
  catch (e) { return JSON.parse(e.stdout); }
};

console.log('sdt-events.js — clarify gate');

test('extra cannot overwrite case_sha (would re-arm the gate for an edited case.md)', () => {
  const dir = mkFeature('v1');
  const forged = 'deadbeef'.padEnd(64, '0');
  const ev = record(dir, ['--event', 'clarify_approved', '--extra', JSON.stringify({ case_sha: forged })]);
  assert.notStrictEqual(ev.case_sha, forged, 'case_sha was overwritten by --extra');
});

test('extra cannot overwrite event or ts', () => {
  const dir = mkFeature('v1');
  const ev = record(dir, ['--event', 'clarify_approved', '--extra', JSON.stringify({ event: 'forged', ts: 'x' })]);
  assert.strictEqual(ev.event, 'clarify_approved');
  assert.notStrictEqual(ev.ts, 'x');
});

test('extra still carries its own fields through', () => {
  const dir = mkFeature('v1');
  const ev = record(dir, ['--event', 'clarify_approved', '--extra', JSON.stringify({ channel: 'dashboard' })]);
  assert.strictEqual(ev.channel, 'dashboard');
});

test('editing case.md after approval goes stale', () => {
  const dir = mkFeature('v1');
  record(dir, ['--event', 'clarify_approved']);
  assert.strictEqual(gate(dir).ok, true);
  fs.writeFileSync(path.join(dir, 'test', 'case.md'), 'v2');
  assert.strictEqual(gate(dir).reason, 'stale');
});

console.log('check-prerequisites.js — clarify is optional, but binding once used');

// Minimal repo fixture: `.ttadk` marks the repo root, specs live at the
// ttadk-CLI layout. cwd inside it drives getRepoRoot()/getSpecsRoot().
const PREREQ = path.join(HERE, 'check-prerequisites.js');
const mkRepo = () => {
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'sdt-repo-'));
  const feature = path.join(repo, '.ttadk', '.adk-mobile', 'specs', '001-x');
  fs.mkdirSync(path.join(feature, 'test'), { recursive: true });
  fs.writeFileSync(path.join(feature, 'test', 'case.md'), 'v1');
  fs.writeFileSync(path.join(feature, 'test', 'task.md'), 't');
  return { repo, feature };
};
const prereq = (repo) => {
  try {
    return {
      code: 0,
      out: JSON.parse(execFileSync(
        'node', [PREREQ, '--json', '--require-sdt-tests', '--require-clarify'],
        { encoding: 'utf-8', cwd: repo }
      )),
    };
  } catch (e) {
    return { code: e.status, err: String(e.stderr) };
  }
};

test('never-clarified cases pass the gate (clarify is optional)', () => {
  const { repo } = mkRepo();
  const r = prereq(repo);
  assert.strictEqual(r.code, 0, r.err);
  assert.strictEqual(r.out.CLARIFY, 'not_run');
});

test('a current approval passes and is reported as approved', () => {
  const { repo, feature } = mkRepo();
  record(feature, ['--event', 'clarify_approved']);
  const r = prereq(repo);
  assert.strictEqual(r.code, 0, r.err);
  assert.strictEqual(r.out.CLARIFY, 'approved');
});

test('editing case.md after an approval still blocks (contract, not ceremony)', () => {
  const { repo, feature } = mkRepo();
  record(feature, ['--event', 'clarify_approved']);
  fs.writeFileSync(path.join(feature, 'test', 'case.md'), 'v2');
  const r = prereq(repo);
  assert.notStrictEqual(r.code, 0, 'stale approval must still exit non-zero');
  assert.ok(/edited after the last/.test(r.err), r.err);
});

test('missing case.md still blocks (ff remains the entry point)', () => {
  const { repo, feature } = mkRepo();
  fs.rmSync(path.join(feature, 'test', 'case.md'));
  const r = prereq(repo);
  assert.notStrictEqual(r.code, 0);
  assert.ok(/adk-sdt-ff/.test(r.err), r.err);
});

test('gate-clarify 的退出码与 check-prerequisites 同口径（missing 放行）', () => {
  const dir = mkFeature('v1');
  // helper 的 try/catch 会吞掉退出码，所以这里直接看它退没退非零
  assert.doesNotThrow(
    () => execFileSync('node', [EVENTS, 'gate-clarify', '--feature-dir', dir], { encoding: 'utf-8', stdio: 'pipe' }),
    'missing 是正当状态：两个入口给相反答案，"审核可选"就不成立了',
  );
  record(dir, ['--event', 'clarify_approved']);
  fs.writeFileSync(path.join(dir, 'test', 'case.md'), 'v2');
  assert.throws(
    () => execFileSync('node', [EVENTS, 'gate-clarify', '--feature-dir', dir], { encoding: 'utf-8', stdio: 'pipe' }),
    'stale 仍要退非零',
  );
});

console.log('sdt-track.js — reporting opt-out');

const resolveEndpoint = (env) => {
  const src = fs.readFileSync(path.join(HERE, 'sdt-track.js'), 'utf-8');
  const fn = src.match(/function resolveEndpoint[\s\S]*?\n}/)[0];
  return new Function('process', 'DEFAULT_TRACK_HOST', `${fn}; return resolveEndpoint({});`)(
    { env }, 'https://default.invalid',
  );
};

test('unset keeps the default host', () => {
  assert.ok(String(resolveEndpoint({})).startsWith('https://default.invalid'));
});

test('explicitly empty host disables reporting (the header\'s promised opt-out)', () => {
  assert.strictEqual(resolveEndpoint({ SDT_TRACK_HOST: '' }), null);
  assert.strictEqual(resolveEndpoint({ SDT_TRACK_ENDPOINT: '' }), null);
  assert.strictEqual(resolveEndpoint({ SDT_TRACK_RUNS_ENDPOINT: '' }), null);
});

test('a configured host is honored', () => {
  assert.ok(String(resolveEndpoint({ SDT_TRACK_HOST: 'https://example.test' })).startsWith('https://example.test'));
});

process.exit(failures === 0 ? (console.log('\nsdt-scripts: PASS'), 0) : (console.log(`\nsdt-scripts: ${failures} FAILED`), 1));
