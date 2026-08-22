#!/usr/bin/env node
// ADK Mobile Agent-Hook Telemetry Forwarder
//
// 透明转发器：把 AI 工具（Claude Code / Cursor / Codex / Trae）agent hook 的完整 stdin
// payload 原样转发给 adk-mobile-mcp 的隐藏命令 `_track`，由 MCP 工具内部完成按工具/按事件
// 的兼容、归一化、写本地 service-log 文件并上报。本脚本不做任何业务判断。
//
// 用法（由各 hooks.json 调用，--tool / --event / --workflow-dir 由配置传入）：
//   node track.js --tool claude --event PostToolUse --workflow-dir .ttadk/.adk-mobile
//
// 多根工作区归因：hooks.json 只传相对 --workflow-dir，不带 hook 所属工程根。多根工作区里
// `_track` 会用 payload.cwd / workspace_roots（=宿主当前「焦点工程」）解析项目根，可能把
// .ttadk 写到焦点工程而非安装本 hook 的工程。为此从本脚本磁盘路径向上定位安装根
// （各 Agent 的 hooks 标记目录 .cursor/.claude/.codex/.coco/.trae 的上一级），作为 positional
// 追加到 `_track`——其项目根
// 解析里 positional 优先级最高（高于 CLAUDE_PROJECT_DIR / workspace_roots / cwd），于是遥测与
// .ttadk 稳定归属到安装 hook 的工程。识别不到则不追加，维持原有回退（fail-open）。
//
// 约束：
// - 完全 fail-open：任何异常都 exit 0，绝不阻塞或污染宿主工具。
// - stdout 必须保持干净。Cursor / Claude 仅在 KB-read 命中时走前台注入
//   （见 shouldForwardInjectionOutput）；Codex 虽支持部分事件的 JSON additionalContext，但本遥测
//   hook 不参与其控制流，且 Stop/SubagentStop 的非 JSON 输出无效，因此保持 detached 静默。
// - 转发进程 detached + unref，立即返回，不等子进程结束。
//
// 可执行文件解析优先级（高频事件下 npx 冷启动/@latest 版本解析有开销，尽量避免）：
//   1) 环境变量 ADK_MOBILE_MCP_BIN —— 显式指定，最高优先级。
//   2) ~/.adk-mobile-mcp/mcp-bin.json —— MCP server 启动后自登记的真实可执行文件，
//      用 `node <script> _track` 直连，跳过 npx。只要起过一次 server 就走这条。
//   3) npx @byted-tiktok/adk-mobile-mcp@latest —— 兜底（从没起过 server / 缓存被清）。
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function readSavedBin() {
  try {
    const file = path.join(os.homedir(), '.adk-mobile-mcp', 'mcp-bin.json');
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (data && data.script && fs.existsSync(data.script)) {
      const node = data.node && fs.existsSync(data.node) ? data.node : process.execPath;
      return { node, script: data.script };
    }
  } catch {
    // 文件不存在/损坏 → 回退
  }
  return null;
}

// 仅在必要时给 shell 参数加引号：命中安全字符集就原样返回（既有 --tool/--event/
// --workflow-dir/npx 等参数逐字节不变，零回归），否则按平台安全引用。仅用于 shell:true
// 分支——因为 Node 的 shell:true 不会转义参数，追加的工程根路径若含空格/shell 元字符会被
// 截断甚至造成注入；shell:false（直连 node）以数组传参，天然安全，无需引用。
const SHELL_SAFE_ARG = /^[A-Za-z0-9_@%+=:,./-]+$/;
function shellQuote(arg) {
  const s = String(arg);
  if (SHELL_SAFE_ARG.test(s)) return s; // 安全字符 → 原样，保持既有命令逐字节不变
  if (process.platform === 'win32') {
    return `"${s.replace(/"/g, '""')}"`; // cmd.exe：双引号包裹，内部双引号翻倍
  }
  return `'${s.replace(/'/g, `'\\''`)}'`; // POSIX sh：单引号包裹，内部单引号断开重接
}

function buildSpec(forwardArgs) {
  const trackArgs = ['_track', ...forwardArgs];

  // 1) 显式覆盖
  const bin = process.env.ADK_MOBILE_MCP_BIN && process.env.ADK_MOBILE_MCP_BIN.trim();
  if (bin) {
    return { cmd: bin, args: trackArgs.map(shellQuote), shell: true };
  }

  // 2) server 自登记的真实可执行文件 → 直连，跳过 npx
  const saved = readSavedBin();
  if (saved) {
    return { cmd: saved.node, args: [saved.script, ...trackArgs], shell: false };
  }

  // 3) 兜底：npx（与 .mcp.json 一致）
  const registry = process.env.ADK_MOBILE_MCP_REGISTRY || 'https://bnpm.byted.org';
  const pkg = process.env.ADK_MOBILE_MCP_PKG || '@byted-tiktok/adk-mobile-mcp@latest';
  return { cmd: 'npx', args: ['-y', `--registry=${registry}`, pkg, ...trackArgs].map(shellQuote), shell: true };
}

function forwardedEvent(forwardArgs) {
  const i = forwardArgs.indexOf('--event');
  return i >= 0 && i + 1 < forwardArgs.length ? String(forwardArgs[i + 1]).toLowerCase() : '';
}

function forwardedTool(forwardArgs) {
  const i = forwardArgs.indexOf('--tool');
  return i >= 0 && i + 1 < forwardArgs.length ? String(forwardArgs[i + 1]).toLowerCase() : '';
}

// 只有这两个宿主会消费 hook stdout 里的注入字段（Cursor 读 additional_context，Claude 读
// hookSpecificOutput.additionalContext）。Codex/Trae 的遥测 hook 均保持静默，故一律排除 —— 与 `_track` 端
// decideKbValuePrompt 只对 claude/cursor 置 decided 的口径一致。
const INJECTION_TOOLS = new Set(['claude', 'cursor']);

function hookPayload(input) {
  try {
    const parsed = JSON.parse(input);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function firstString(obj, keys) {
  if (!obj || typeof obj !== 'object') return '';
  for (const key of keys) {
    if (typeof obj[key] === 'string' && obj[key].trim()) return obj[key].trim();
  }
  return '';
}

function isKbReadPayload(input) {
  const payload = hookPayload(input);
  if (!payload) return false;
  const tool = firstString(payload, ['tool_name', 'toolName', 'name']).toLowerCase();
  if (!['read', 'glob', 'ls', 'notebookread'].includes(tool)) return false;

  const pathKeys = ['file_path', 'path', 'target_file', 'notebook_path', 'relative_workspace_path'];
  const filePath =
    firstString(payload, pathKeys) ||
    firstString(payload.tool_input, [...pathKeys, 'target_directory']);
  const normalized = filePath.replace(/\\/g, '/');
  // Mirror of ai-sde/src/core/agent-hooks/hook-track.ts::kbDocInfo.
  // Keep both lists in sync whenever a KB document type is added or renamed.
  return (
    /(?:^|\/)CLAUDE\.md$/i.test(normalized) ||
    /(?:^|\/)docs\/(?:domain|interface|workflow|rule|architecture)\.md$/i.test(normalized)
  );
}

function shouldForwardInjectionOutput(input, forwardArgs) {
  if (!INJECTION_TOOLS.has(forwardedTool(forwardArgs))) return false;
  const event = forwardedEvent(forwardArgs);
  // R1 only exists for KB-document reads. R2 is returned in-band by the spec_completed
  // log response and does not need hook stdout. Everything else stays detached.
  return event === 'posttooluse' && isKbReadPayload(input);
}

// 各 AI 工具在工程内安装 hook 脚本的「标记目录」= ttadk_cli 各 profile 的
// hooksConfig.scriptsDirectoryPath 的上一级（真相源：ttadk_cli/src/core/ai-tools/profiles/*）：
//   .cursor → cursor / cursor-cli    .claude → claude / relay    .codex → codex
//   .coco   → coco                   .trae   → trae / trae-cli
// 覆盖 ttadk_cli 目前所有支持 hooks 的 Agent；新增此类 Agent 时在此登记其标记目录即可。
//（adk-mobile-track 当前 compatible_tools 为 claude/cursor/codex/trae/trae-cli，即除 coco
// 外全部命中；coco 保留为前向兼容，识别到也安全。）
const HOOK_DIR_MARKERS = new Set(['.cursor', '.claude', '.codex', '.coco', '.trae']);

// 从本脚本磁盘路径向上定位安装该 hook 的「工程根」。安装布局（见 ttadk_cli hooks-loader）：
//   <projectRoot>/<marker>/hooks/<plugin>/adk-mobile-track/scripts/track.js
//   （<marker> ∈ HOOK_DIR_MARKERS，如 .cursor / .claude / .codex / .coco / .trae）
// 逐级向上找到「父目录名命中 HOOK_DIR_MARKERS 的 hooks 目录」，其标记目录的上一级即工程根。
// 命中返回该绝对路径；走到文件系统根仍未命中、或任何异常 → 返回 null（不追加，维持原逻辑，
// fail-open）。用 __dirname 字符串向上走、不 realpath：安装路径本身就含标记段，字符串定位最稳；
// _track 端会再做 normalize/realpath。
function detectHookProjectRoot() {
  try {
    let dir = __dirname;
    while (true) {
      if (path.basename(dir) === 'hooks') {
        const marker = path.basename(path.dirname(dir)); // 标记目录名，如 .cursor / .codex
        if (HOOK_DIR_MARKERS.has(marker)) {
          return path.dirname(path.dirname(dir)); // 工程根 = 含标记目录的目录
        }
      }
      const up = path.dirname(dir);
      if (up === dir) return null; // 已到文件系统根仍未命中
      dir = up;
    }
  } catch {
    return null; // 任何异常都不追加，维持原逻辑
  }
}

function main() {
  // 把本脚本收到的 --tool/--event/--workflow-dir 等参数原样转发给 `_track`
  const forwardArgs = process.argv.slice(2);

  // 追加安装本 hook 的工程根作为 positional：_track 项目根解析里 positional 优先级最高，
  // 覆盖多根工作区里指向「焦点工程」的 payload.cwd / workspace_roots，确保归属到本工程。
  // 识别不到（如源码仓直接跑、非标准安装）则不追加，维持原有回退。
  const projectRoot = detectHookProjectRoot();
  if (projectRoot) forwardArgs.push(projectRoot);

  let input = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => { input += chunk; });
  process.stdin.on('error', () => finish(input, forwardArgs));
  process.stdin.on('end', () => finish(input, forwardArgs));

  // 兜底：stdin 异常未触发 end 时也要退出，不能挂死。
  setTimeout(() => finish(input, forwardArgs), 2000).unref();
}

let finished = false;
function finish(input, forwardArgs) {
  if (finished) return;
  finished = true;

  // KB 价值追踪 · KB-read 专用注入模式：
  // 需要把 `_track` 的 stdout 回喂宿主（Cursor 把 postToolUse hook 的 stdout 当 JSON 控制字段、
  // 读 additional_context）。只有明确命中 KB 文档的 Read 才前台回传；其它事件始终走 detached。
  const inject = shouldForwardInjectionOutput(input, forwardArgs);

  // 兜底强制退出：默认 1s；注入模式放宽到 4s（<Cursor hook 5s 超时），给子进程 flush + 输出留足时间。
  setTimeout(() => process.exit(0), inject ? 4000 : 1000).unref();

  try {
    const { cmd, args, shell } = buildSpec(forwardArgs);

    if (inject) {
      // 前台捕获 stdout 并「即到即转发」给宿主（不 detached）。即到即写 → 即便兜底超时抢先退出也不丢注入。
      const child = spawn(cmd, args, {
        stdio: ['pipe', 'pipe', 'ignore'], // 捕获子进程 stdout，stderr 仍丢弃
        shell,
        windowsHide: true,
      });
      child.stdout.on('data', c => { try { process.stdout.write(c); } catch { /* ignore */ } });
      child.on('error', () => process.exit(0));
      child.stdin.on('error', () => { /* 忽略：子进程可能已读完即退 */ });
      child.on('close', () => process.exit(0));
      child.stdin.end(input);
      return;
    }

    // 默认路径（零回归）：detached fire-and-forget，丢弃 stdout。
    const child = spawn(cmd, args, {
      detached: true,
      stdio: ['pipe', 'ignore', 'ignore'], // stdout/stderr 全部丢弃，保持宿主干净
      shell,                                // npx/显式 bin 用 shell;直连 node 不用
      windowsHide: true,
    });
    child.on('error', () => process.exit(0));
    child.stdin.on('error', () => process.exit(0));
    child.unref();
    // 关键：等 payload 真正写入子进程 stdin（进内核 pipe buffer）后再退出。
    // 否则 process.exit 会抢在异步写入前终止，detached 子进程只会读到被截断的 payload。
    child.stdin.end(input, () => process.exit(0));
  } catch {
    process.exit(0); // spawn 同步失败也立即退出，绝不阻塞宿主
  }
}

try {
  main();
} catch {
  process.exit(0);
}
