#!/usr/bin/env python3
"""kb-docs-validator

Validate and reconcile kb-init-docs knowledge docs across one or multiple doc roots.

Outputs a Markdown report to stdout.

Design goals:
- Fast: do filesystem checks locally; avoid expensive repo-wide scans.
- Deterministic: prefer code-derived signals (via kb_tool.py) over doc content.
- Non-destructive: report by default; do not auto-edit files.

Usage:
  python3 validate_kb_docs.py <doc_root1> [doc_root2 ...]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


DEFAULT_KB_INIT_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "kb-init-docs" / "scripts"
DEFAULT_KB_TOOL = str(DEFAULT_KB_INIT_SCRIPTS_DIR / "kb_tool.py")
DEFAULT_TOP = 20

if str(DEFAULT_KB_INIT_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(DEFAULT_KB_INIT_SCRIPTS_DIR))

try:
    from kb_common import SOURCE_EXTS as KB_SOURCE_EXTS
except Exception:  # noqa: BLE001
    KB_SOURCE_EXTS = {
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".java",
        ".kt",
        ".kts",
        ".m",
        ".mm",
        ".swift",
    }


@dataclass
class Issue:
    severity: str  # INFO|WARN|ERROR
    title: str
    details: str


@dataclass
class RuleScope:
    name: str  # small|medium|large
    target_lines: int
    warn_lines: int
    strong_lines: int
    child_doc_roots: int
    code_files: int
    direct_subdirs: int
    reasons: List[str]


CODE_EXTENSIONS = set(KB_SOURCE_EXTS)

RULE_SCOPE_THRESHOLDS: Dict[str, Tuple[int, int, int]] = {
    # (target<=p90, warn>p90, strong>p95) — single 口径 with kb-doc-budget-contract.md and the
    # dashboard (kb-dochealth.py): measured p90 budget + p95 strong level. >500 is always a hard
    # error (checked separately). Re-derived monthly from the real distribution (p1-distribution.py).
    "small": (105, 105, 141),
    "medium": (200, 200, 255),
    "large": (200, 200, 239),
}

AGGREGATE_DOC_ROOT_NAMES = {
    "Component",
    "Components",
    "Foundation",
    "Foundations",
    "LiveRoom",
    "Service",
    "Services",
}

# CLAUDE.md in the current template is exactly three H2 sections:
# Module Overview / Key Classes / References. A heading is canonical when its normalized
# form contains one of these tokens (forgiving of bilingual headers like "References / 参考");
# any other H2 is an old-template section (Architecture, Directory Structure, Workflow,
# Dependencies, Testing, ...) and a migration signal.
CLAUDE_CANONICAL_H2_TOKENS = [
    "module overview",
    "overview",
    "module summary",
    "key classes",
    "key class",
    "key types",
    "references",
    "reference",
    "模块概述",
    "模块概览",
    "模块说明",
    "概述",
    "概览",
    "关键类",
    "核心类",
    "关键类型",
    "参考",
    "引用",
    "相关文档",
    "参考文档",
]

# domain.md must be pure business (entities, concepts, business rules, glossary). Architecture
# / layering / dependency / data-flow content belongs in a separate architecture.md under the
# current template.
#
# Detection is deliberately narrow to avoid word-collision false positives (each false flag
# triggers a needless migration). Two tiers, matched against a heading whose parenthetical
# content has been stripped first:
#   COMPOUND — unambiguous architecture phrases, matched ANYWHERE in the heading.
#   BARE — ambiguous single words, matched ONLY when they LEAD the heading. So a business
#     heading that merely contains the word in a product name / parenthetical — e.g.
#     "Repost Panel (Dual Panel Architecture)" or "双面板架构" — is NOT flagged.
DOMAIN_ARCH_COMPOUND_PATTERNS = [
    "架构约束", "架构设计", "架构总览", "架构图", "技术架构", "系统架构", "整体架构",
    "分层架构", "分层结构", "层次结构", "依赖关系", "依赖图", "模块依赖", "组件结构",
    "调用关系", "调用链", "数据流向", "数据流图", "时序图", "系统设计",
    r"layered\s+structure", r"\blayering\b", r"dependency\s+(?:graph|diagram)",
    r"component\s+structure", r"call\s+(?:graph|flow|chain)", r"data\s?flow",
    r"sequence\s+diagram", r"system\s+design",
    # "<arch-qualifier> architecture" (qualifier-first real arch sections like
    # "Technical / System / Module Architecture") — curated whitelist so a product name
    # like "Dual Panel Architecture" (qualifier "panel") is still NOT matched.
    r"(?:technical|system|software|application|overall|high[\s-]?level|module|service|layered|component|solution|reference|target)\s+architecture",
]
# Lead-only ambiguous words (lowercased; CJK compared verbatim, ASCII compared case-insensitively).
DOMAIN_ARCH_BARE_LEADS = [
    "架构", "分层", "层次", "依赖关系", "依赖",
    "architecture", "architectural", "dependencies", "dependency", "layers", "layer",
]


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _is_symlink_to(path: Path, target_name: str) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if not path.is_symlink():
        return False
    try:
        return Path(os.readlink(path)).name == target_name
    except OSError:
        return False


def _normalize_md(s: str) -> str:
    # normalize line endings + trim trailing spaces
    return "\n".join(line.rstrip() for line in s.replace("\r\n", "\n").split("\n")).strip()


def _extract_markdown_table_names(md: str) -> List[str]:
    # Extract names in markdown table cells like: | `Name` | ... |
    names: List[str] = []
    for line in md.splitlines():
        m = re.search(r"\|\s*`([^`]+)`\s*\|", line)
        if m:
            names.append(m.group(1).strip())
    return names


def _extract_claude_key_classes(md: str) -> List[str]:
    # Best-effort: try to locate the Key Classes section; fall back to table extraction.
    # Supports both the new 3-section format and older variants.
    section_pat = re.compile(r"^##\s+Key\s+Classes\s*$", re.MULTILINE)
    m = section_pat.search(md)
    if not m:
        return _extract_markdown_table_names(md)

    start = m.end()
    # Find next H2
    next_h2 = re.search(r"^##\s+", md[start:], re.MULTILINE)
    body = md[start : start + next_h2.start()] if next_h2 else md[start:]
    return _extract_markdown_table_names(body)


def _run_kb_tool_select_key_classes(doc_root: Path, top: int) -> Tuple[List[str], Optional[str]]:
    if not Path(DEFAULT_KB_TOOL).exists():
        return [], f"kb_tool.py not found at: {DEFAULT_KB_TOOL}"

    cmd = [sys.executable, DEFAULT_KB_TOOL, "select-key-classes", str(doc_root), "--top", str(top)]
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001
        return [], f"failed to run kb_tool.py: {e}"

    if p.returncode != 0:
        msg = p.stderr.strip() or p.stdout.strip() or f"exit={p.returncode}"
        return [], f"kb_tool.py failed: {msg}"

    # Parse lines like:
    # - `TTKFriendsRootViewController` (objc_class) — ...
    key_classes: List[str] = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line.startswith("- `"):
            continue
        m = re.match(r"-\s+`([^`]+)`\s+\(", line)
        if m:
            key_classes.append(m.group(1))

    return key_classes, None


def _find_entry_headers(doc_root: Path) -> List[Path]:
    # Code-as-truth heuristic: the module entry commonly includes *ModuleService.h
    # Keep it shallow by limiting to a couple expected locations.
    candidates: List[Path] = []
    for pat in [
        "**/ModuleInterface/Interface/*ModuleService.h",
        "**/ModuleInterface/Interface/*Service.h",
    ]:
        candidates.extend(doc_root.glob(pat))
    # Deduplicate by resolved path if possible
    uniq: List[Path] = []
    seen = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq[:20]


def _is_code_file(path: Path) -> bool:
    return path.suffix in CODE_EXTENSIONS


def _count_child_doc_roots(doc_root: Path) -> int:
    count = 0
    for claude in doc_root.rglob("CLAUDE.md"):
        if claude.parent == doc_root:
            continue
        count += 1
    return count


def _count_code_files(doc_root: Path) -> int:
    return sum(1 for path in doc_root.rglob("*") if path.is_file() and _is_code_file(path))


def _count_direct_subdirs(doc_root: Path) -> int:
    try:
        return sum(1 for path in doc_root.iterdir() if path.is_dir())
    except OSError:
        return 0


def _detect_rule_scope(doc_root: Path) -> RuleScope:
    child_doc_roots = _count_child_doc_roots(doc_root)
    code_files = _count_code_files(doc_root)
    direct_subdirs = _count_direct_subdirs(doc_root)
    direct_names = {path.name for path in doc_root.iterdir() if path.is_dir()}
    reasons: List[str] = []

    # Prefer explicit knowledge-doc hierarchy over raw code size: large feature
    # modules can have many files but should still keep feature-level rule docs concise.
    if child_doc_roots >= 3:
        name = "large"
        reasons.append(f"{child_doc_roots} child doc roots")
    elif doc_root.name in AGGREGATE_DOC_ROOT_NAMES:
        name = "large"
        reasons.append(f"aggregate doc-root name `{doc_root.name}`")
    elif child_doc_roots >= 1:
        name = "medium"
        reasons.append(f"{child_doc_roots} child doc root")
    elif {"Interface", "Module", "Fragments"} & direct_names:
        name = "medium"
        reasons.append("known local module-layer layout")
    elif code_files >= 80:
        name = "medium"
        reasons.append(f"{code_files} code files")
    elif direct_subdirs >= 8:
        name = "medium"
        reasons.append(f"{direct_subdirs} direct subdirectories")
    else:
        name = "small"
        reasons.append("leaf doc root")

    target, warn, strong = RULE_SCOPE_THRESHOLDS[name]
    return RuleScope(
        name=name,
        target_lines=target,
        warn_lines=warn,
        strong_lines=strong,
        child_doc_roots=child_doc_roots,
        code_files=code_files,
        direct_subdirs=direct_subdirs,
        reasons=reasons,
    )


def _normalize_rule_signature(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", " ", text)
    return " ".join(text.lower().split())


# Fixed meta sections from rule.template.md — NOT scenario blocks. Exclude them from the
# ancestor-duplication signature so a parent and child rule.md both carrying the template's
# standard headings do not falsely trip "duplicates ancestor rule scenarios".
META_RULE_HEADINGS = {"inherited rules", "context", "related docs", "related skills"}


def _extract_rule_signatures(txt: str) -> Dict[str, List[str]]:
    headings: List[str] = []
    whens: List[str] = []
    for line in txt.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            normalized = _normalize_rule_signature(heading.group(1))
            if normalized and normalized not in META_RULE_HEADINGS:
                headings.append(normalized)
            continue
        when = re.match(r"^WHEN\s+(.+?)[:：]\s*$", line)
        if when:
            normalized = _normalize_rule_signature(when.group(1))
            if normalized:
                whens.append(normalized)
    return {"headings": headings, "whens": whens}


def _find_ancestor_rule_docs(doc_root: Path) -> List[Path]:
    docs: List[Path] = []
    seen = set()
    for ancestor in doc_root.parents:
        for candidate in (ancestor / "docs" / "rule.md", ancestor / "rule.md"):
            if not candidate.exists() or not candidate.is_file():
                continue
            key = str(candidate.resolve())
            if key in seen:
                continue
            seen.add(key)
            docs.append(candidate)
    return docs


def _resolve_example_path(raw_path: str, doc_root: Path) -> Path:
    raw_path = raw_path.strip().strip("`").strip()
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate

    doc_root_candidate = (doc_root / candidate).resolve()
    if doc_root_candidate.exists():
        return doc_root_candidate

    for ancestor in (doc_root, *doc_root.parents):
        repo_candidate = (ancestor / candidate).resolve()
        if repo_candidate.exists():
            return repo_candidate
    return doc_root_candidate


def _check_code_example_sources(txt: str, doc_root: Path, label: str) -> List[Issue]:
    lines = txt.splitlines()
    issues: List[Issue] = []
    missing_sources = 0
    missing_paths: List[str] = []
    in_code_block = False

    for idx, line in enumerate(lines):
        if not line.strip().startswith("```"):
            continue
        if in_code_block:
            in_code_block = False
            continue
        in_code_block = True
        previous = lines[idx - 1].strip() if idx > 0 else ""
        previous2 = lines[idx - 2].strip() if idx > 1 else ""
        source_line = previous if previous else previous2
        match = re.match(r"(?i)^(?:bad\s+)?example\s+from\s+(.+?)[:：]\s*$", source_line)
        if not match:
            missing_sources += 1
            continue
        source_path = match.group(1).strip()
        if not _resolve_example_path(source_path, doc_root).exists():
            missing_paths.append(source_path)

    if missing_sources:
        issues.append(
            Issue(
                "WARN",
                f"{label} has code examples without source paths",
                f"Found {missing_sources} code fence(s) without `Example from <path>:` or `Bad example from <path>:` immediately before them.",
            )
        )
    if missing_paths:
        issues.append(
            Issue(
                "WARN",
                f"{label} has code examples with missing source paths",
                "Example source paths not found: "
                + ", ".join(f"`{path}`" for path in missing_paths[:5])
                + ". Use real repo files for examples.",
            )
        )

    return issues


def _check_rule_doc_quality(rule_path: Path, label: str, doc_root: Path) -> List[Issue]:
    issues: List[Issue] = []
    txt = _read_text(rule_path)
    if txt is None or not txt.strip():
        return issues

    lines = txt.splitlines()
    line_count = len(lines)
    scope = _detect_rule_scope(doc_root)
    when_count = sum(1 for line in lines if re.match(r"^WHEN\s+.+[:：]", line))
    must_count = sum(1 for line in lines if re.match(r"^\s*-\s+MUST\s+", line))
    must_not_count = sum(1 for line in lines if re.match(r"^\s*-\s+MUST\s+NOT\s+", line))
    table_lines = sum(1 for line in lines if line.strip().startswith("|"))
    code_fences = sum(1 for line in lines if line.strip().startswith("```"))

    has_when = re.search(r"(?m)^WHEN\s+.+[:：]", txt) is not None
    has_must = must_count > 0
    has_must_not = must_not_count > 0

    scope_details = (
        f"Detected scope={scope.name} ({', '.join(scope.reasons)}; "
        f"child_doc_roots={scope.child_doc_roots}, code_files={scope.code_files}, "
        f"direct_subdirs={scope.direct_subdirs}). "
        f"Thresholds: target<={scope.target_lines}, warn>{scope.warn_lines}, "
        f"strong>{scope.strong_lines}, hard_error>500."
    )

    if line_count > 500:
        issues.append(
            Issue(
                "ERROR",
                f"{label} exceeds hard length limit",
                f"Lines={line_count}. {scope_details}",
            )
        )
    elif line_count > scope.strong_lines:
        issues.append(
            Issue(
                "WARN",
                f"{label} is strongly oversized for {scope.name} doc root",
                f"Lines={line_count}. {scope_details}",
            )
        )
    elif line_count > scope.warn_lines:
        issues.append(
            Issue(
                "WARN",
                f"{label} is oversized for {scope.name} doc root",
                f"Lines={line_count}. {scope_details}",
            )
        )

    if not has_when:
        issues.append(
            Issue(
                "WARN",
                f"{label} has no scenario trigger",
                "Expected at least one `WHEN <specific local scenario>:` block.",
            )
        )
    if not has_must and not has_must_not:
        issues.append(
            Issue(
                "WARN",
                f"{label} has no MUST/MUST NOT actions",
                "Expected actionable bullets starting with `MUST` or `MUST NOT`.",
            )
        )

    own_signatures = _extract_rule_signatures(txt)
    parent_duplicates: List[str] = []
    for parent_rule in _find_ancestor_rule_docs(doc_root):
        parent_txt = _read_text(parent_rule) or ""
        parent_signatures = _extract_rule_signatures(parent_txt)
        for kind, label_name in (("headings", "heading"), ("whens", "WHEN")):
            overlap = sorted(set(own_signatures[kind]) & set(parent_signatures[kind]))
            for signature in overlap[:3]:
                parent_duplicates.append(f"{label_name} `{signature}` already exists in {parent_rule}")
    if parent_duplicates:
        issues.append(
            Issue(
                "WARN",
                f"{label} duplicates ancestor rule scenarios",
                "Child rule docs should not restate parent/global rules. "
                + "; ".join(parent_duplicates[:5]),
            )
        )

    misplaced_section_patterns = [
        r"(?mi)^#{2,3}\s*(模块结构|目录结构|代码组织|文件结构|命名约定|文档编写)\s*$",
        r"(?mi)^#{2,3}\s*(Module Structure|Directory Structure|Code Organization|File Structure|Naming Conventions|Documentation)\s*$",
        r"(?mi)^#{2,3}\s*(Testing Requirements|Dependencies)\s*$",
    ]
    found_misplaced = [
        pat
        for pat in misplaced_section_patterns
        if re.search(pat, txt)
    ]
    if found_misplaced:
        issues.append(
            Issue(
                "WARN",
                f"{label} contains misplaced structure or inventory sections",
                "Module structure belongs in `CLAUDE.md` summary; dependency/test/name inventories "
                "should not live in rule.md unless narrowed into enforceable local constraints.",
            )
        )

    pseudo_rule_table_patterns = [
        r"(?mi)^\|\s*Rule\s*\|\s*(Rationale|Implementation|Details)\s*\|",
        r"(?mi)^\|\s*Feature Area\s*\|\s*Test Focus\s*\|",
        r"(?mi)^\|\s*Dependency\s*\|\s*Used For\s*\|",
    ]
    found_pseudo_tables = [
        pat
        for pat in pseudo_rule_table_patterns
        if re.search(pat, txt)
    ]
    if found_pseudo_tables:
        issues.append(
            Issue(
                "WARN",
                f"{label} contains table-based pseudo rules",
                "Convert keep-worthy rows into `WHEN` scenario blocks with local evidence; "
                "remove product notes, test matrices, and dependency inventories.",
            )
        )

    generic_patterns = [
        r"write clean code",
        r"follow best practices",
        r"handle errors",
        r"pay attention to performance",
        r"ensure code quality",
        r"be careful",
        r"good UX",
        r"user guidance",
        r"user knows",
        r"memory management",
        r"complete coverage",
        r"smooth switching",
        r"show success feedback",
        r"\bperformance\b",
        r"\bstability\b",
        r"\brobustness\b",
        r"\breliability\b",
        r"性能",
        r"稳定性",
        r"健壮性",
        r"可靠性",
        r"最佳实践",
        r"代码质量",
        r"用户体验",
    ]
    found_generic = [
        pat
        for pat in generic_patterns
        if re.search(pat, txt, flags=re.IGNORECASE)
    ]
    if found_generic:
        issues.append(
            Issue(
                "INFO",
                f"{label} contains generic rule text",
                "Generic phrases found: "
                + ", ".join(f"`{p}`" for p in found_generic)
                + ". Prefer local, evidence-backed rules or remove them.",
            )
        )

    if code_fences:
        issues.extend(_check_code_example_sources(txt, doc_root, label))

    if line_count > scope.warn_lines and when_count == 0:
        issues.append(
            Issue(
                "WARN",
                f"{label} has low scenario-rule density",
                f"Lines={line_count}, WHEN blocks=0, code fences={code_fences}, table lines={table_lines}. "
                "Long rule docs need explicit scenario blocks; code examples are allowed only as compact "
                "evidence for nearby local constraints.",
            )
        )
    elif when_count > 0:
        lines_per_when = line_count / when_count
        if line_count > scope.warn_lines and lines_per_when > 60:
            issues.append(
                Issue(
                    "INFO",
                    f"{label} may have low scenario-rule density",
                    f"Lines={line_count}, WHEN blocks={when_count}, approx lines per scenario={lines_per_when:.1f}. "
                    "Consider pruning examples or splitting broad scenarios.",
                )
            )

    if code_fences > max(6, when_count * 2 + 2) and line_count > scope.warn_lines:
        issues.append(
            Issue(
                "WARN",
                f"{label} contains many code examples",
                f"Code fence count={code_fences}. Keep short positive/negative examples only when they support "
                "nearby local `MUST` / `MUST NOT` constraints.",
            )
        )

    return issues


def _extract_h2_headings(md: str) -> List[str]:
    return [m.group(1).strip() for m in re.finditer(r"(?m)^##\s+(.+?)\s*$", md)]


def _check_claude_three_section(claude_txt: str) -> List[Issue]:
    """Flag CLAUDE.md that carries H2 sections outside the canonical 3-section template
    (Module Overview / Key Classes / References) — an old-template migration signal."""
    headings = _extract_h2_headings(claude_txt)
    if not headings:
        return []
    non_canonical: List[str] = []
    for heading in headings:
        norm = _normalize_rule_signature(heading)
        if not norm:
            continue
        if not any(tok in norm for tok in CLAUDE_CANONICAL_H2_TOKENS):
            non_canonical.append(heading)
    if not non_canonical:
        return []
    return [
        Issue(
            "WARN",
            "CLAUDE.md is not the canonical 3-section format",
            "CLAUDE.md should hold only `Module Overview`, `Key Classes`, and `References` H2 "
            "sections. Old-template sections found: "
            + ", ".join(f"`{h}`" for h in non_canonical[:8])
            + ". Migrate them (architecture/structure → architecture.md, flows → workflow.md, "
            "etc.) per kb-update-docs Value-Aware Migration.",
        )
    ]


def _check_interface_sot_section(interface_txt: str, label: str) -> List[Issue]:
    """Flag interface.md missing the `Source of Truth` declaration section (digest-not-transcription
    template). Old-template interface docs — typically verbatim source
    transcriptions — lack it; flagging them structurally non-conformant makes any kb-update touch
    trigger Value-Aware Migration, which rewrites the doc to the new digest template (Mode A
    pointer / Mode B `Dispersed:` declaration) and squeezes the transcription out."""
    headings = _extract_h2_headings(interface_txt)
    has_sot = any("source of truth" in h.lower() for h in headings)
    # Mode B docs may carry the machine token even if a writer restructured headings — accept it.
    has_dispersed_token = bool(re.search(r"(?m)^\s*\**`?Dispersed:", interface_txt))
    if has_sot or has_dispersed_token:
        return []
    return [
        Issue(
            "WARN",
            f"{label} lacks the `Source of Truth` declaration section",
            "interface.md must open its contract with a `Source of Truth` section declaring either "
            "Mode A (pointer table to the authoritative interface source files) or Mode B (fixed "
            "`Dispersed:` token — no dedicated interface file, the table IS the aggregated surface). "
            "Docs predating the digest template lack it and are typically verbatim source "
            "transcriptions; migrate per kb-update-docs Value-Aware Migration (curated 5-10 entries "
            "+ pointers, no pasted signature blocks / doc comments).",
        )
    ]


def _check_interface_network_api_endpoints(interface_txt: str, label: str) -> List[Issue]:
    """Flag Network APIs table rows whose Endpoint cell is not a full route path (leading `/`).
    Audited failure: a generated doc listed agent-invented endpoint aliases (`ai_music_trending` for
    an IDL rpc actually named `get_trending_list`) and prefix-stripped short names — neither matches
    anything in source or IDL, so agents searching either way miss. The template's hard rule: copy
    the declared full path VERBATIM. Any `/`-bearing cell passes (route path, `https://`/`wss://`
    URL, method+path, gRPC full name); flagged only when the cell has no `/`
    at all. Sanctioned exception (not flagged): an RPC/service method name plus a pointer to the
    declaring file — detected as any `/` elsewhere in the row (a path pointer)."""
    m = re.search(r"(?im)^##\s+Network APIs[^\n]*$", interface_txt)
    if not m:
        return []
    section = interface_txt[m.end():]
    nxt = re.search(r"(?m)^##\s+", section)
    if nxt:
        section = section[: nxt.start()]
    bad: List[str] = []
    for line in section.splitlines():
        row = line.strip()
        if not row.startswith("|"):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        endpoint = cells[0].strip("`* ").strip()
        if not endpoint or set(endpoint) <= {"-", ":", " "}:
            continue  # separator row
        if endpoint.lower() in ("endpoint", "none", "n/a"):
            continue  # header row / explicit none
        if "/" in endpoint or endpoint.startswith("<"):
            continue  # any /-bearing verbatim form (route path, https://, wss://, method+path, gRPC full name) / placeholder
        rest = "|".join(cells[1:])
        if "/" in rest:
            continue  # name + declaring-file pointer form (sanctioned)
        bad.append(endpoint)
    if not bad:
        return []
    return [
        Issue(
            "WARN",
            f"{label} Network APIs endpoints are not verbatim full route paths",
            "Endpoint cells must be the full route path copied VERBATIM from the declaration "
            "(client request annotation/builder or IDL route option), starting with `/`. "
            "Never paraphrase, prefix-strip, or invent names — invented aliases match nothing in "
            "source or IDL and mislead recall. If client code only exposes an RPC/service method "
            "name (codegen indirection), keep that exact name and add a pointer to the file where "
            "the full path is declared. Offending endpoints: "
            + ", ".join(f"`{e}`" for e in bad[:8])
            + ("…" if len(bad) > 8 else ""),
        )
    ]


def _strip_paren_content(s: str) -> str:
    """Drop (...) / （...） parenthetical content so an architecture word appearing only inside
    a product name or aside (e.g. "Repost Panel (Dual Panel Architecture)") does not register."""
    return re.sub(r"[\(（][^\)）]*[\)）]", " ", s)


def _heading_is_architecture(heading: str) -> bool:
    h = _strip_paren_content(heading).strip()
    hl = h.lower()
    for pat in DOMAIN_ARCH_COMPOUND_PATTERNS:
        if re.search(pat, hl):
            return True
    lead = re.sub(r"^[\s\W_]+", "", h).lower()  # CJK chars are \w, so only punctuation/space is stripped
    return any(lead.startswith(term) for term in DOMAIN_ARCH_BARE_LEADS)


def _check_domain_architecture_mixing(domain_txt: str, label: str) -> List[Issue]:
    """Flag domain.md that mixes architecture/layering/dependency content — it should be
    pure-business; architecture content belongs in a separate architecture.md."""
    matched: List[str] = []
    seen = set()
    for m in re.finditer(r"(?m)^#{2,4}\s+(.+?)\s*$", domain_txt):
        heading = m.group(1).strip()
        if heading in seen:
            continue
        if _heading_is_architecture(heading):
            seen.add(heading)
            matched.append(heading)
    if not matched:
        return []
    return [
        Issue(
            "WARN",
            f"{label} mixes architecture content",
            "domain.md should stay pure-business; architecture / layering / dependency / "
            "data-flow content belongs in a separate architecture.md. Architecture-style "
            "headings found: "
            + ", ".join(f"`{h}`" for h in matched[:8])
            + ". Extract them into architecture.md per kb-update-docs Value-Aware Migration.",
        )
    ]


_STEP_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?\*{0,2}\d+[.)]\s+")
_STEP_SYMBOL_RE = re.compile(r"`([A-Za-z_][\w:]*(?:\.[A-Za-z_][\w:]*)?)`")
_HEADING_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$")
# 子 bullet（`- detail` / `* detail`，含缩进）：编号步骤下的细节行，属于同一序列、不该断块
# （真实 workflow L2 步骤常带空行/子项，一断就把序列拆碎、符号数虚低 → 漏判）。
_SUBBULLET_RE = re.compile(r"^\s*[-*+]\s")


def _extract_numbered_step_symbol_blocks(md: str) -> List[Tuple[str, List[str]]]:
    """Return (section heading, ordered backticked identifier symbols) for each maximal run of
    numbered-step lines (`1.` `2.` …) in a doc. Used to detect the same runtime call sequence
    restated across workflow.md and architecture.md (the sequence is the duplication signal, not
    the mere reuse of class names — a static architecture.md legitimately names the same classes)."""
    blocks: List[Tuple[str, List[str]]] = []
    current_heading = ""
    cur_syms: List[str] = []
    in_block = False
    for line in md.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            if in_block and cur_syms:
                blocks.append((current_heading, cur_syms))
            in_block = False
            cur_syms = []
            current_heading = heading.group(1).strip()
            continue
        if _STEP_LINE_RE.match(line):
            if not in_block:
                in_block = True
                cur_syms = []
            cur_syms.extend(_STEP_SYMBOL_RE.findall(line))
        elif in_block:
            # 续块：编号序列在步骤间常夹【空行 / 子 bullet】，这些不断块——
            # 空行跳过；子 bullet 是步骤的细节、其符号也算进本序列。只有【标题】断块（上面已处理），
            # 其余顶层散文行仍断块（两段独立叙述不该并成一个序列）。
            if line.strip() == "":
                continue
            if _SUBBULLET_RE.match(line):
                cur_syms.extend(_STEP_SYMBOL_RE.findall(line))
                continue
            if cur_syms:
                blocks.append((current_heading, cur_syms))
            in_block = False
            cur_syms = []
    if in_block and cur_syms:
        blocks.append((current_heading, cur_syms))
    return [(h, s) for h, s in blocks if s]


def _check_workflow_architecture_dup(
    workflow_txt: str,
    architecture_txt: str,
    arch_label: str = "docs/architecture.md",
    wf_label: str = "docs/workflow.md",
) -> List[Issue]:
    """Flag architecture.md numbered-step blocks that restate a workflow.md numbered-step block
    (same ordered class-call sequence). architecture.md is static structure only; the runtime
    step-by-step flow is owned by workflow.md (L2). Conservative: needs a real overlapping *step
    sequence*, not just shared class names — so a legit static architecture.md that only names the
    same classes in bullets/tables (no numbered steps) is not flagged."""
    min_shared = 3
    min_ratio = 0.6
    wf_blocks = _extract_numbered_step_symbol_blocks(workflow_txt)
    arch_blocks = _extract_numbered_step_symbol_blocks(architecture_txt)
    if not wf_blocks or not arch_blocks:
        return []
    wf_sets = [set(syms) for _, syms in wf_blocks]
    dup_headings: List[str] = []
    seen = set()
    for heading, syms in arch_blocks:
        arch_set = set(syms)
        if not arch_set:
            continue
        best = max((len(arch_set & wf_set) for wf_set in wf_sets), default=0)
        if best >= min_shared and best >= min_ratio * len(arch_set):
            key = heading or "(unlabeled step block)"
            if key not in seen:
                seen.add(key)
                dup_headings.append(key)
    if not dup_headings:
        return []
    return [
        Issue(
            "WARN",
            f"{arch_label} restates {wf_label}'s runtime step sequences",
            "architecture.md carries static structure only; a numbered call sequence that also "
            "appears in workflow.md is duplicated content (drift risk). Keep the sequence in "
            "workflow.md (L2) and reduce the architecture.md copy to a one-line pointer to "
            "workflow.md. Duplicated architecture sections: "
            + ", ".join(f"`{h}`" for h in dup_headings[:8])
            + ". Per templates/kb-doc-templates.md rule 11 (SSOT for content).",
        )
    ]


def _check_doc_root(doc_root: Path) -> List[Issue]:
    issues: List[Issue] = []

    claude = doc_root / "CLAUDE.md"
    agent = doc_root / "AGENTS.md"

    docs_dir = doc_root / "docs"
    docs_files = {
        "interface": docs_dir / "interface.md",
        "workflow": docs_dir / "workflow.md",
        "domain": docs_dir / "domain.md",
        "rule": docs_dir / "rule.md",
    }

    legacy_files = {
        "interface": doc_root / "interface.md",
        "workflow": doc_root / "workflow.md",
        "domain": doc_root / "domain.md",
        "rule": doc_root / "rule.md",
    }

    # Basic presence checks
    if not claude.exists():
        issues.append(Issue("ERROR", "Missing CLAUDE.md", "Expected CLAUDE.md at doc root."))
    if agent.exists() or agent.is_symlink():
        if not _is_symlink_to(agent, "CLAUDE.md"):
            issues.append(
                Issue(
                    "WARN",
                    "AGENTS.md is not a symlink to CLAUDE.md",
                    "Expected AGENTS.md -> CLAUDE.md for consistency.",
                )
            )
    else:
        issues.append(Issue("INFO", "AGENTS.md missing", "Optional but recommended: AGENTS.md -> CLAUDE.md"))

    has_docs_dir = docs_dir.exists() and docs_dir.is_dir()
    has_any_docs = any(p.exists() for p in docs_files.values())
    has_any_legacy = any(p.exists() for p in legacy_files.values())

    if has_any_docs and not has_docs_dir:
        issues.append(Issue("ERROR", "docs/* exists but docs/ is not a directory", "Check filesystem state."))

    if has_any_docs and has_any_legacy:
        # Compare each pair
        for k in ["interface", "workflow", "domain", "rule"]:
            d = docs_files[k]
            l = legacy_files[k]
            if not d.exists() or not l.exists():
                continue
            d_txt = _read_text(d)
            l_txt = _read_text(l)
            if d_txt is None or l_txt is None:
                continue
            if _normalize_md(d_txt) != _normalize_md(l_txt):
                issues.append(
                    Issue(
                        "WARN",
                        f"Conflict: docs/{k}.md differs from root {k}.md",
                        "Two versions exist. Prefer code as truth; ask human which doc should be canonical.",
                    )
                )
            else:
                issues.append(
                    Issue(
                        "INFO",
                        f"Duplication: docs/{k}.md identical to root {k}.md",
                        "Consider keeping a single canonical copy to avoid drift.",
                    )
                )

    # Reference checks in CLAUDE.md/README.md
    claude_txt = _read_text(claude) or ""
    readme_txt = _read_text(doc_root / "README.md") or ""

    def _check_link(md: str, label: str, rel: str, must_exist: bool = True) -> None:
        if rel not in md:
            return
        target = (doc_root / rel).resolve() if not rel.startswith("./") else (doc_root / rel[2:]).resolve()
        if must_exist and not target.exists():
            issues.append(Issue("WARN", f"Broken reference in {label}", f"Link target not found: {rel}"))

    for rel in [
        "./docs/interface.md",
        "./docs/workflow.md",
        "./docs/domain.md",
        "./docs/rule.md",
        "./interface.md",
        "./workflow.md",
        "./domain.md",
        "./rule.md",
    ]:
        _check_link(claude_txt, "CLAUDE.md", rel)
        _check_link(readme_txt, "README.md", rel)

    for label, rule_path in [
        ("docs/rule.md", docs_files["rule"]),
        ("root rule.md", legacy_files["rule"]),
    ]:
        if rule_path.exists():
            issues.extend(_check_rule_doc_quality(rule_path, label, doc_root))

    # Structural-conformance checks (old-template signals → kb-update-docs Value-Aware Migration)
    if claude_txt:
        issues.extend(_check_claude_three_section(claude_txt))
    for label, iface_path in [
        ("docs/interface.md", docs_files["interface"]),
        ("root interface.md", legacy_files["interface"]),
    ]:
        if iface_path.exists():
            iface_txt = _read_text(iface_path)
            if iface_txt and iface_txt.strip():
                issues.extend(_check_interface_sot_section(iface_txt, label))
                issues.extend(_check_interface_network_api_endpoints(iface_txt, label))
    for label, domain_path in [
        ("docs/domain.md", docs_files["domain"]),
        ("root domain.md", legacy_files["domain"]),
    ]:
        if domain_path.exists():
            domain_txt = _read_text(domain_path)
            if domain_txt and domain_txt.strip():
                issues.extend(_check_domain_architecture_mixing(domain_txt, label))

    # Cross-file dedup: architecture.md must not restate workflow.md's runtime step sequences
    workflow_txt = _read_text(docs_files["workflow"]) or _read_text(legacy_files["workflow"]) or ""
    architecture_txt = _read_text(docs_dir / "architecture.md") or _read_text(doc_root / "architecture.md") or ""
    if workflow_txt.strip() and architecture_txt.strip():
        issues.extend(_check_workflow_architecture_dup(workflow_txt, architecture_txt))

    # Code-as-truth validation: key classes overlap
    if claude_txt:
        claude_keys = set(_extract_claude_key_classes(claude_txt))
        kb_keys, kb_err = _run_kb_tool_select_key_classes(doc_root, DEFAULT_TOP)
        if kb_err:
            issues.append(Issue("WARN", "kb_tool.py key class extraction failed", kb_err))
        else:
            kb_set = set(kb_keys)
            overlap = len(claude_keys & kb_set)
            if claude_keys and overlap == 0:
                issues.append(
                    Issue(
                        "WARN",
                        "Key Classes mismatch vs code",
                        "No overlap between CLAUDE.md key-class table and code-derived key classes. "
                        "Docs may be stale or using a different module boundary.",
                    )
                )
            elif claude_keys and overlap < min(5, len(claude_keys)):
                issues.append(
                    Issue(
                        "INFO",
                        "Key Classes low overlap vs code",
                        f"Overlap={overlap}. Consider regenerating or updating the key-class list from code.",
                    )
                )

    # Code-as-truth heuristic: entry headers exist
    entry_headers = _find_entry_headers(doc_root)
    if not entry_headers:
        issues.append(
            Issue(
                "INFO",
                "No obvious ModuleService header found",
                "Could be Swift-only or different module layout; validate the entry point manually.",
            )
        )
    else:
        # If interface docs exist, check whether any entry header path is mentioned.
        interface_doc = _read_text(docs_files["interface"]) or _read_text(legacy_files["interface"]) or ""
        if interface_doc:
            mentioned = any(p.name in interface_doc or str(p).replace(str(doc_root) + "/", "") in interface_doc for p in entry_headers)
            if not mentioned:
                issues.append(
                    Issue(
                        "INFO",
                        "Interface doc may be missing the real entry header",
                        "Found candidate entry headers in code, but none appear to be referenced in interface docs.",
                    )
                )

    return issues


def _format_report(results: List[Tuple[Path, List[Issue]]]) -> str:
    out: List[str] = []
    out.append("# kb-docs-validator report")
    out.append("")

    for doc_root, issues in results:
        out.append(f"## {doc_root}")
        out.append("")
        if not issues:
            out.append("No issues found.")
            out.append("")
            continue

        for sev in ["ERROR", "WARN", "INFO"]:
            group = [i for i in issues if i.severity == sev]
            if not group:
                continue
            out.append(f"### {sev}")
            out.append("")
            for i in group:
                out.append(f"- **{i.title}** — {i.details}")
            out.append("")

    return "\n".join(out).rstrip() + "\n"


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(prog="validate_kb_docs.py")
    ap.add_argument("doc_roots", nargs="+", help="One or more doc root directories")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any ERROR issue is found, so callers can gate on the exit code "
        "(e.g. kb-init-docs treats '0 ERROR' as the completion bar). Default off for back-compat.",
    )
    args = ap.parse_args(argv)

    results: List[Tuple[Path, List[Issue]]] = []
    for p in args.doc_roots:
        doc_root = Path(p).expanduser().resolve()
        if not doc_root.exists() or not doc_root.is_dir():
            results.append((doc_root, [Issue("ERROR", "Invalid doc root", "Path does not exist or is not a directory")]))
            continue
        results.append((doc_root, _check_doc_root(doc_root)))

    sys.stdout.write(_format_report(results))
    if args.strict:
        error_count = sum(1 for _, issues in results for i in issues if i.severity == "ERROR")
        return 1 if error_count else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
