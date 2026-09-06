"""
文档预解析器：按 template.md 结构将需求文档切分为三层 Context。

三层结构：
  - global_shared   : 模块概述、风险等级、术语表（影响所有 Feature）
  - cross_feature   : 功能关系、Feature 索引、导航链（连接 Feature 之间）
  - feature_sections: 每个 Feature 的私有段落（Section 3.F-XX）

设计原则：
  - 容错优先：缺失章节时静默降级（置空字符串），不抛出异常
  - 导航链由 Pass 1 LLM 输出填充，parse_doc 本身只做文本切分
  - 父节点段落最多追溯 1 层，避免 Context 随链深度膨胀
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── 阈值 ──────────────────────────────────────────────────────
# 文档正文字符数超过此值时，推荐采用两阶段生成；否则单次全量。
# 依据：固定约束块 ~2000 tokens + 文档 2000 字符 ~2000 tokens = ~4000 tokens 输入，
#       在此范围内主流模型的指令跟随质量稳定；超出后截断风险与约束遗忘风险上升。
DOC_SPLIT_THRESHOLD = 2000


# ── 数据结构 ──────────────────────────────────────────────────
@dataclass
class FeatureSection:
    feature_id: str
    feature_name: str
    raw_text: str


@dataclass
class ParsedDoc:
    raw_text: str
    module_overview: str = ""        # Section 1：模块概述
    feature_index: str = ""          # Section 2：功能点总览
    feature_sections: Dict[str, FeatureSection] = field(default_factory=dict)  # Section 3.F-XX
    feature_relationships: str = ""  # Section 4：功能点关系
    risk_levels: str = ""            # Section 5：风险等级
    change_sensitivity: str = ""     # Section 6：变更敏感点
    glossary: str = ""               # 附录 A：术语表
    raw_case_seeds: Dict[str, List[str]] = field(default_factory=dict)  # Section 7：原始用例分组

    @property
    def char_count(self) -> int:
        return len(self.raw_text.strip())

    @property
    def feature_ids(self) -> List[str]:
        return list(self.feature_sections.keys())

    def should_split(self) -> bool:
        return self.char_count >= DOC_SPLIT_THRESHOLD


# ── 内部工具 ──────────────────────────────────────────────────
def _between(text: str, start_pat: str, end_pat: str) -> str:
    """提取两个 pattern 之间的文本；找不到 end_pat 时取到末尾。"""
    sm = re.search(start_pat, text, re.DOTALL | re.MULTILINE)
    if not sm:
        return ""
    snippet = text[sm.start():]
    em = re.search(end_pat, snippet, re.DOTALL | re.MULTILINE)
    return (snippet[: em.start()] if em else snippet).strip()


def _filter_glossary(glossary_text: str, target_text: str) -> str:
    """只保留在 target_text 中出现过的术语条目，减少无关注入。"""
    result = []
    for line in glossary_text.splitlines():
        for sep in ("：", ":"):
            if sep in line:
                term = re.split(sep, line, 1)[0].strip("- •*").strip()
                if term and term in target_text:
                    result.append(line)
                break
    return "\n".join(result)


# ── 解析入口 ──────────────────────────────────────────────────

def _parse_raw_case_seeds(seeds_block: str) -> Dict[str, List[str]]:
    """
    解析第 7 章「原始用例分组」块，返回 {feature_id: [seed_title, ...]} 字典。

    支持两种格式：
    1. Bullet list: ``- 用例标题``
    2. Markdown table: ``| Seed ID | 入口状态 | 核心操作 | 预期结果 |``
    """
    result: Dict[str, List[str]] = {}
    bullet_pat = re.compile(r"^[-*•]\s+(.+)$", re.MULTILINE)
    table_row_pat = re.compile(
        r"^\|\s*(F\d+-S\d+)\s*\|(.+)$", re.MULTILINE
    )

    sections = re.split(
        r"(?m)^(?:#{1,6}\s+)(F-\d+)\s+[^\n]*$", seeds_block
    )
    # re.split with a capturing group: [pre, fid1, content1, fid2, content2, ...]
    it = iter(sections)
    next(it, None)  # skip preamble
    for fid, content in zip(it, it):
        items: List[str] = []
        # Try bullet format first
        items = [m.group(1).strip() for m in bullet_pat.finditer(content) if m.group(1).strip()]
        # If no bullets, try table format
        if not items:
            for m in table_row_pat.finditer(content):
                seed_id = m.group(1).strip()
                rest = m.group(2).strip().rstrip("|")
                cells = [c.strip() for c in rest.split("|")]
                if len(cells) >= 3:
                    items.append(f"[{seed_id}] {cells[0]} → {cells[1]} → {cells[2]}")
                elif cells:
                    items.append(f"[{seed_id}] {' | '.join(cells)}")
        if items:
            result[fid.strip()] = items
    return result

# Markdown 标题前缀：兼容无前缀（sample 文档）和 ##/### 前缀（真实文档）
# 例：`1. 模块概述` 或 `## 1. 模块概述`
_H = r"(?:#{1,6}\s+)?"

def parse_doc(text: str) -> ParsedDoc:
    """
    解析需求文档，兼容两种格式：

    格式 A（sample / template.md）：章节标题为纯文本，如 `3.F-01 功能名称`
    格式 B（真实 spec 文档）：章节标题为 Markdown heading，如 `### 3.F-01 功能名称`

    段落分隔符为 `---`，各章节以阿拉伯数字开头。
    容错：缺失章节时对应字段为空字符串，不影响其余字段解析。
    """
    doc = ParsedDoc(raw_text=text)

    doc.module_overview = _between(
        text,
        rf"(?m)^{_H}1[.、．]\s*模块概述",
        rf"(?m)^---\s*$\s*{_H}2[.、．]",
    )
    doc.feature_index = _between(
        text,
        rf"(?m)^{_H}2[.、．]\s*功能点总览",
        rf"(?m)^---\s*$\s*{_H}3[.、．]",
    )
    doc.feature_relationships = _between(
        text,
        rf"(?m)^{_H}4[.、．]\s*功能点之间的关系",
        rf"(?m)^---\s*$\s*{_H}5[.、．]",
    )
    doc.risk_levels = _between(
        text,
        rf"(?m)^{_H}5[.、．]\s*风险等级",
        rf"(?m)^---\s*$\s*{_H}6[.、．]",
    )
    doc.change_sensitivity = _between(
        text,
        rf"(?m)^{_H}6[.、．]\s*变更敏感点",
        rf"(?m)^---\s*$\s*{_H}附录",
    )
    doc.glossary = _between(
        text,
        r"(?m)^(?:#{1,6}\s+)?附录\s*A[：:]\s*术语表",
        r"\Z",
    )

    # 提取第 7 章原始用例分组（Raw Case Seeds），格式：
    #   ## 7. 原始用例分组（Raw Case Seeds）
    #   ### F-01
    #   - 原始用例标题1
    #   - 原始用例标题2
    seeds_block = _between(
        text,
        rf"(?m)^{_H}7[.、．]\s*原始用例分组",
        rf"(?m)^{_H}(?:附录|8[.、．]|\Z)",
    )
    if seeds_block:
        doc.raw_case_seeds = _parse_raw_case_seeds(seeds_block)

    # 提取各 Feature 段落：3.F-XX（可带 ### 前缀）到下一个 3.F-XX 或 Section 4
    # 兼容：
    #   格式 A: `3.F-01 功能名称`
    #   格式 B: `### 3.F-01 功能名称`
    feature_pat = re.compile(
        r"(?m)^(?:#{1,6}\s+)?3\.(F-\d+)\s+([^\n]+)\n"
        r"(.*?)"
        r"(?=^(?:#{1,6}\s+)?3\.F-\d+(?!\.)\s|\n(?:#{1,6}\s+)?4[.、．]\s*功能点之间|\Z)",
        re.DOTALL,
    )
    for m in feature_pat.finditer(text):
        fid = m.group(1)
        fname = m.group(2).strip()
        raw = m.group(0).strip()
        doc.feature_sections[fid] = FeatureSection(
            feature_id=fid,
            feature_name=fname,
            raw_text=raw,
        )

    return doc


# ── Context 构建 ──────────────────────────────────────────────
def build_global_context(doc: ParsedDoc, feature_id: Optional[str] = None) -> str:
    """
    构建全局共享块：模块概述 + 风险等级 + 相关术语。

    feature_id: 若提供，则只注入与该 feature 段落相关的术语（过滤）。
    """
    parts: list[str] = []
    if doc.module_overview:
        parts.append("【模块概述】\n" + doc.module_overview)
    if doc.risk_levels:
        parts.append("【风险等级】\n" + doc.risk_levels)
    if doc.glossary:
        if feature_id and feature_id in doc.feature_sections:
            feature_text = doc.feature_sections[feature_id].raw_text
            filtered = _filter_glossary(doc.glossary, feature_text)
            if filtered:
                parts.append("【相关术语】\n" + filtered)
        else:
            parts.append("【术语表】\n" + doc.glossary)
    return "\n\n".join(parts)


def build_cross_feature_context(
    doc: ParsedDoc,
    feature_id: str,
    nav_chains: Optional[dict] = None,
) -> str:
    """
    构建跨 Feature 块：功能总览 + 功能关系 + 完整导航链。

    nav_chains: Pass 1 LLM 输出的 navigation_chains dict（key=feature_id）。
                为 None 时跳过导航链（单次全量路径不使用此函数）。
    """
    parts: list[str] = []
    if doc.feature_index:
        parts.append("【功能点总览】\n" + doc.feature_index)
    if doc.feature_relationships:
        parts.append("【功能关系】\n" + doc.feature_relationships)

    if nav_chains and feature_id in nav_chains:
        chain = nav_chains[feature_id]
        lines = [f"【{feature_id} 完整导航路径（Pass 1 提炼）】"]
        lines.append(f"完整路径：{chain.get('full_path', '')}")
        lines.append(f"进入状态：{chain.get('entry_state', '')}")
        anc = chain.get("ancestor_states", {})
        if anc:
            lines.append("祖先进入状态（含所有传递依赖）：")
            for aid, state in anc.items():
                lines.append(f"  - {aid}：{state}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def build_parent_section(
    doc: ParsedDoc,
    feature_id: str,
    nav_chains: Optional[dict] = None,
) -> str:
    """
    获取直接父节点的原文段落（最多追溯 1 层）。

    包含父节点原文而非摘要，是为了传递父节点的隐式业务规则
    （如时间限制、状态约束等，不会在 feature_index 或摘要中重复）。
    超过 1 层的祖先已通过 navigation_chains.ancestor_states 以结构化形式传递。
    """
    if not nav_chains or feature_id not in nav_chains:
        return ""
    depends_on: list = nav_chains[feature_id].get("depends_on", [])
    if not depends_on:
        return ""
    parent_id = depends_on[0]  # 只取直接父节点
    parent_sec = doc.feature_sections.get(parent_id)
    if not parent_sec:
        return ""
    return (
        f"【父功能点 {parent_id} 原文（用于理解隐式业务约束）】\n"
        f"{parent_sec.raw_text}"
    )


def plan_info(doc: ParsedDoc) -> dict:
    """
    输出文档分析与生成策略，供 Agent / CLI 决策。

    返回：
      strategy    : "SINGLE_PASS" | "TWO_PASS"
      char_count  : 文档字符总数
      threshold   : 分割阈值
      feature_ids : 检测到的 Feature ID 列表
      reason      : 决策原因说明
    """
    strategy = "TWO_PASS" if doc.should_split() else "SINGLE_PASS"
    if strategy == "SINGLE_PASS":
        reason = (
            f"文档长度 {doc.char_count} 字符 < 阈值 {DOC_SPLIT_THRESHOLD}，"
            "单次全量生成，指令跟随风险低。"
        )
    else:
        reason = (
            f"文档长度 {doc.char_count} 字符 ≥ 阈值 {DOC_SPLIT_THRESHOLD}，"
            f"检测到 {len(doc.feature_ids)} 个 Feature，"
            "采用两阶段生成：Pass 1 提炼全局上下文，Pass 2 逐 Feature 生成用例。"
        )
    return {
        "strategy": strategy,
        "char_count": doc.char_count,
        "threshold": DOC_SPLIT_THRESHOLD,
        "feature_ids": doc.feature_ids,
        "reason": reason,
    }
