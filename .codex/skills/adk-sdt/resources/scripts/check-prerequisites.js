#!/usr/bin/env node
'use strict';

/**
 * Mobile SDT Check Prerequisites Script
 *
 * Validates workspace state for TTADK Mobile SDT workflow skills.
 * Adapted from ttadk/core adk-sdt check-prerequisites for the mobile workflow layout:
 * mobile specs live under `.adk-mobile/specs/` (adk-mobile MCP) with `.ttadk/specs/`
 * and root-level `specs/` as fallbacks.
 *
 * Uses only Node.js built-in modules (no external dependencies).
 *
 * Usage:
 *   node check-prerequisites.js [--json] [--paths-only] [--require-sdt-tests]
 *                               [--require-clarify] [--include-sdt-tests]
 *                               [--feature-dir <path>]
 *
 *   --require-clarify  Enforce the clarify gate. Clarify itself is OPTIONAL —
 *                      ff-generated cases may execute directly, adk-sdt-clarify
 *                      is the on-demand review/repair loop for when the user is
 *                      not satisfied with case.md. But an approval, once given,
 *                      is a sha-bound contract. This is what adk-sdt-implement
 *                      runs before it starts. Outcomes (sdt-events checkClarifyGate):
 *                        ok      — approval present and current → pass (CLARIFY: approved)
 *                        missing — never clarified            → pass (CLARIFY: not_run)
 *                        no_case — test/case.md missing        → exit 1 (run adk-sdt-ff)
 *                        stale   — case.md edited after an approval → exit 1
 *                                  (the approved contract diverged; re-clarify)
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function existsSync(p) {
  try {
    fs.accessSync(p, fs.constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function isDirSync(p) {
  try {
    return fs.statSync(p).isDirectory();
  } catch {
    return false;
  }
}

/**
 * Project root discovery.
 * Priority: nearest ancestor containing `.adk-mobile` or `.ttadk` → git toplevel → nearest `.git`.
 */
function getRepoRoot() {
  let dir = process.cwd();
  while (dir !== path.parse(dir).root) {
    if (existsSync(path.join(dir, '.adk-mobile')) || existsSync(path.join(dir, '.ttadk'))) {
      return dir;
    }
    dir = path.dirname(dir);
  }
  try {
    return execSync('git rev-parse --show-toplevel', { encoding: 'utf-8' }).trim();
  } catch {
    dir = process.cwd();
    while (dir !== path.parse(dir).root) {
      if (existsSync(path.join(dir, '.git'))) {
        return dir;
      }
      dir = path.dirname(dir);
    }
    throw new Error('Could not determine repository root. Please run from within the repository.');
  }
}

/**
 * The adk-mobile MCP's workflow dir is configurable (`--workflow-dir`), so the specs
 * root is NOT a fixed path: a ttadk-CLI install uses `.ttadk/.adk-mobile`, a bare dev
 * server defaults to `.adk-mobile`. Read the project's own `.mcp.json` to learn which
 * one is authoritative here.
 */
function getConfiguredWorkflowDir(repoRoot) {
  try {
    const mcp = JSON.parse(fs.readFileSync(path.join(repoRoot, '.mcp.json'), 'utf8'));
    const args = mcp?.mcpServers?.['adk-mobile']?.args;
    if (!Array.isArray(args)) return null;
    const i = args.indexOf('--workflow-dir');
    if (i >= 0 && typeof args[i + 1] === 'string') return args[i + 1];
    const inline = args.find((a) => typeof a === 'string' && a.startsWith('--workflow-dir='));
    return inline ? inline.slice('--workflow-dir='.length) : null;
  } catch {
    return null;
  }
}

/** A specs root is "live" when it holds at least one feature dir — an empty one is a stale shell. */
function hasFeatureDirs(dir) {
  try {
    return listFeatureDirs(dir).length > 0;
  } catch {
    return false;
  }
}

/**
 * Specs root discovery. Candidates, in order: the workflow dir declared in `.mcp.json`
 * (authoritative), then `.ttadk/.adk-mobile/specs`, `.adk-mobile/specs`, `.ttadk/specs`,
 * `specs`. A candidate that EXISTS BUT IS EMPTY loses to a later one that actually holds
 * feature dirs — both layouts coexist in the same repo once either server has run, and
 * picking the empty shell silently strands SDT on the wrong root.
 */
function getSpecsRoot(repoRoot) {
  const configured = getConfiguredWorkflowDir(repoRoot);
  const candidates = [
    ...(configured ? [path.join(repoRoot, configured, 'specs')] : []),
    path.join(repoRoot, '.ttadk', '.adk-mobile', 'specs'),
    path.join(repoRoot, '.adk-mobile', 'specs'),
    path.join(repoRoot, '.ttadk', 'specs'),
    path.join(repoRoot, 'specs'),
  ];
  const existing = candidates.filter((c) => existsSync(c) && isDirSync(c));
  const populated = existing.find(hasFeatureDirs);
  if (populated) return populated;
  if (existing.length > 0) return existing[0];
  throw new Error(
    `No specs directory found under ${repoRoot} (looked for ${candidates
      .map((c) => path.relative(repoRoot, c))
      .join(', ')}).\n` +
      'Run the SDD workflow first (e.g. /adk:sdd:ff or /adk:sdd:spec) to create a feature spec.'
  );
}

/** List feature dirs: NNN-* (mobile) or YYYYMMDD-* (server) naming, excluding archive dirs. */
function listFeatureDirs(specsRoot) {
  return fs
    .readdirSync(specsRoot)
    .filter((name) => {
      const full = path.join(specsRoot, name);
      return (
        isDirSync(full) &&
        (/^\d{3}-/.test(name) || /^\d{8}-/.test(name)) &&
        !['archived', 'doc_export'].includes(name)
      );
    })
    .map((name) => {
      const full = path.join(specsRoot, name);
      const stat = fs.statSync(full);
      const time = stat.birthtime ? stat.birthtime.getTime() : stat.mtime.getTime();
      return { name, time };
    })
    .sort((a, b) => b.time - a.time)
    .map((d) => d.name);
}

function buildPaths(repoRoot, specsRoot, featureDir) {
  const resolved = path.isAbsolute(featureDir) ? featureDir : path.resolve(repoRoot, featureDir);
  return {
    REPO_ROOT: repoRoot,
    SPECS_ROOT: specsRoot,
    FEATURE_NAME: path.basename(resolved),
    FEATURE_DIR: resolved,
    FEATURE_SPEC: path.join(resolved, 'spec.md'),
    REQUIREMENTS: path.join(resolved, 'requirements.md'),
    IMPL_PLAN: path.join(resolved, 'plan.md'),
    DESIGN: path.join(resolved, 'design.md'),
    TASKS: path.join(resolved, 'tasks.md'),
    SDT_CASE: path.join(resolved, 'test', 'case.md'),
    SDT_TASK: path.join(resolved, 'test', 'task.md'),
    SDT_REPORT: path.join(resolved, 'test', 'report.md'),
  };
}

function checkPrerequisites(options) {
  const repoRoot = getRepoRoot();
  const specsRoot = getSpecsRoot(repoRoot);
  const allFeatures = listFeatureDirs(specsRoot);

  let featureDir = options.featureDir;
  if (!featureDir) {
    if (process.env.TTADK_FEATURE) {
      featureDir = path.join(specsRoot, process.env.TTADK_FEATURE);
    } else if (allFeatures.length > 0) {
      featureDir = path.join(specsRoot, allFeatures[0]);
    } else {
      throw new Error(
        `No feature directories found under ${specsRoot}.\nRun the SDD workflow first to create a feature spec.`
      );
    }
  } else if (!path.isAbsolute(featureDir) && !existsSync(path.resolve(repoRoot, featureDir))) {
    // Allow passing a bare feature name.
    const asName = path.join(specsRoot, featureDir);
    if (existsSync(asName)) {
      featureDir = asName;
    }
  }

  const paths = buildPaths(repoRoot, specsRoot, featureDir);
  const result = {
    ...paths,
    ALL_FEATURES: allFeatures,
  };

  if (options.pathsOnly) {
    return result;
  }

  if (!existsSync(paths.FEATURE_DIR)) {
    throw new Error(
      `Feature directory not found: ${paths.FEATURE_DIR}\nRun the SDD workflow first to create the feature structure.`
    );
  }
  if (options.requireSdtTests) {
    if (!existsSync(paths.SDT_CASE)) {
      throw new Error(
        `test/case.md not found in ${paths.FEATURE_DIR}\nRun the adk-sdt-ff skill first to generate SDT test cases.`
      );
    }
    if (!existsSync(paths.SDT_TASK)) {
      throw new Error(
        `test/task.md not found in ${paths.FEATURE_DIR}\nRun the adk-sdt-ff skill first to generate SDT test tasks.`
      );
    }
  }
  // Clarify gate — opt-in but binding. Clarify is NOT a mandatory stage:
  // freshly generated cases execute directly, and adk-sdt-clarify exists for
  // when the user is unsatisfied with case.md. What the gate still enforces:
  //   - no_case: nothing to execute — ff must run first.
  //   - stale:   an approval IS on record and case.md diverged from the approved
  //     sha. The approval is a contract; silently running edited cases under an
  //     old approval is the tamper case the sha binding exists to catch.
  if (options.requireClarify) {
    const { checkClarifyGate } = require('./sdt-events.js');
    const gate = checkClarifyGate(paths.FEATURE_DIR);
    if (gate.ok) {
      result.CLARIFY = 'approved';
    } else if (gate.reason === 'no_case') {
      throw new Error(
        `test/case.md not found in ${paths.FEATURE_DIR}\nRun the adk-sdt-ff skill first to generate SDT test cases.`
      );
    } else if (gate.reason === 'stale') {
      throw new Error(
        `test/case.md was edited after the last adk-sdt-clarify approval ` +
          `(approved ${String(gate.approvedSha).slice(0, 12)} != current ${String(gate.currentSha).slice(0, 12)}).\n` +
          'Re-run the adk-sdt-clarify skill to review and re-approve the current cases before adk-sdt-implement.'
      );
    } else {
      // Never clarified — allowed. Surface it so the caller can mention the
      // review loop without blocking on it.
      result.CLARIFY = 'not_run';
    }
  }

  const docs = [];
  for (const [key, label] of [
    ['FEATURE_SPEC', 'spec.md'],
    ['REQUIREMENTS', 'requirements.md'],
    ['IMPL_PLAN', 'plan.md'],
    ['DESIGN', 'design.md'],
    ['TASKS', 'tasks.md'],
  ]) {
    if (existsSync(paths[key])) docs.push(label);
  }
  if (options.includeSdtTests) {
    if (existsSync(paths.SDT_CASE)) docs.push('test/case.md');
    if (existsSync(paths.SDT_TASK)) docs.push('test/task.md');
    if (existsSync(paths.SDT_REPORT)) docs.push('test/report.md');
  }
  result.AVAILABLE_DOCS = docs;
  return result;
}

function parseCliOptions(args) {
  const options = {
    json: false,
    pathsOnly: false,
    requireSdtTests: false,
    requireClarify: false,
    includeSdtTests: false,
    featureDir: '',
  };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--json') options.json = true;
    else if (arg === '--paths-only') options.pathsOnly = true;
    else if (arg === '--require-sdt-tests') options.requireSdtTests = true;
    else if (arg === '--require-clarify') options.requireClarify = true;
    else if (arg === '--include-sdt-tests') options.includeSdtTests = true;
    else if (arg === '--feature-dir') {
      options.featureDir = args[i + 1] || '';
      i++;
    } else if (arg.startsWith('--feature-dir=')) {
      options.featureDir = arg.slice('--feature-dir='.length);
    }
  }
  return options;
}

function main() {
  const options = parseCliOptions(process.argv.slice(2));
  try {
    const result = checkPrerequisites(options);
    if (options.json) {
      console.log(JSON.stringify(result, null, 2));
    } else {
      for (const [k, v] of Object.entries(result)) {
        console.log(`${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
      }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (options.json) {
      console.error(JSON.stringify({ error: message }));
    } else {
      console.error(`ERROR: ${message}`);
    }
    process.exit(1);
  }
}

main();
