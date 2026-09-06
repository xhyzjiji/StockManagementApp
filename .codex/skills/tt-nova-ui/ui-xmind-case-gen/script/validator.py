"""
Pass 3 — Rule-based Validator

检查 Pass 2 生成的 cases JSON 相对于 spec 第 7 章 seeds 的覆盖缺口。
不调用 LLM，纯代码检测。

Violation 类型：
  seed_gap   : 某条 seed 找不到匹配的 generated case
  role_gap   : seeds 中明确提到的角色在 generated cases 中缺少对应用例
  time_gap   : seeds 中出现的时间节点标签在 generated cases 中缺少对应用例

输出格式（violations.json）：
{
  "feature_id": "F-05",
  "seed_total": 36,
  "case_total": 27,
  "covered": 22,
  "violations": [
    {
      "type": "seed_gap",
      "seed": "结算完成5min内/主播提交答案为Invalid/主播侧-中触展示竞猜结果",
      "reason": "无匹配 case（关键词命中 0/3）",
      "suggestion": "新增覆盖该场景的独立用例"
    },
    ...
  ]
}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


# ── 停用词 ─────────────────────────────────────────────────────────────────────
_STOP = {
    "的", "与", "和", "或", "在", "中", "后", "前", "及", "等",
    "下", "上", "是", "不", "有", "到", "了", "为", "以", "已",
    "-", "—", "/", "、", "（", "）", "(", ")", "+",
}

# ── 角色关键词 ─────────────────────────────────────────────────────────────────
_ROLE_PATTERNS: Dict[str, List[str]] = {
    "主播":   ["主播", "streamer", "broadcaster", "主播侧"],
    "管理员": ["管理员", "moderator", "mod", "管理员侧"],
    "观众":   ["观众", "viewer", "看播", "用户侧", "投注"],
}

# ── 时间节点 ──────────────────────────────────────────────────────────────────
_TIME_PAT = re.compile(
    r'(\d+\s*(?:min|分钟?|s|秒)\s*(?:内|后|前)?'
    r'|\d+min(?:内|后)'
    r'|30s|5min|10min|5分钟|10分钟)',
    re.IGNORECASE,
)


# ── 数据结构 ──────────────────────────────────────────────────────────────────
@dataclass
class Violation:
    type: str          # seed_gap | role_gap | time_gap
    seed: str          # 对应的 seed 文本
    reason: str
    suggestion: str
    matched_case: Optional[str] = None   # 最接近的 case 标题（若有部分匹配）


@dataclass
class ValidationResult:
    feature_id: str
    seed_total: int
    case_total: int
    covered: int
    violations: List[Violation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feature_id": self.feature_id,
            "seed_total": self.seed_total,
            "case_total": self.case_total,
            "covered": self.covered,
            "coverage_rate": round(self.covered / self.seed_total, 3) if self.seed_total else 1.0,
            "violations": [
                {
                    "type": v.type,
                    "seed": v.seed,
                    "reason": v.reason,
                    "suggestion": v.suggestion,
                    **({"matched_case": v.matched_case} if v.matched_case else {}),
                }
                for v in self.violations
            ],
        }


# ── 关键词提取 ────────────────────────────────────────────────────────────────
def _keywords(text: str, min_len: int = 2) -> List[str]:
    """从文本中提取有效关键词（过滤停用词和短词）。"""
    tokens = re.split(r'[\s\-/、，。；：\+（）\(\)]+', text)
    return [t for t in tokens if t and t not in _STOP and len(t) >= min_len]


def _cjk_chars(text: str) -> set:
    """提取文本中所有 CJK 汉字的集合（去除标点、空白、ASCII）。"""
    return {ch for ch in text if '\u4e00' <= ch <= '\u9fff'}


def _match_score(seed: str, case_title: str) -> Tuple[int, int]:
    """
    返回 (命中关键词数, seed 关键词总数)。

    匹配策略（双轨）：
    1. Token 命中：seed token 是 case_title 的子串，或与 case token 精确相等
    2. CJK 字符覆盖：case_title CJK 字符集 ⊆ seed CJK 字符集的覆盖率 ≥ 70%
       （处理 case 是 seed 的缩写版本的情况）

    只要两轨之一通过阈值，就返回足以触发"已覆盖"判断的分数。
    """
    sk = list(_keywords(seed))
    if not sk:
        return 0, 0
    ct_lower = case_title.lower()
    ck_set = set(t.lower() for t in _keywords(case_title))
    hit = 0
    for token in sk:
        token_l = token.lower()
        if token_l in ct_lower or token_l in ck_set:
            hit += 1

    # 字符级覆盖兜底：case 中每个 CJK 汉字都能在 seed 中找到 → 说明 case 是 seed 的高度缩写
    seed_cjk = _cjk_chars(seed)
    case_cjk = _cjk_chars(case_title)
    if seed_cjk and case_cjk:
        case_in_seed_rate = len(case_cjk & seed_cjk) / len(case_cjk)
        if case_in_seed_rate >= 0.70:
            # 强制命中：case 中 70%+ 的字在 seed 里 → 视为充分覆盖
            return max(hit, len(sk)), len(sk)

    return hit, len(sk)


def _find_best_match(seed: str, case_titles: List[str]) -> Tuple[Optional[str], int, int]:
    """找到与 seed 最匹配的 case_title，返回 (title, hit, total)。"""
    best_title, best_hit, best_total = None, 0, 0
    for title in case_titles:
        hit, total = _match_score(seed, title)
        if hit > best_hit:
            best_hit, best_total, best_title = hit, total, title
    return best_title, best_hit, best_total


# ── Seeds 解析（兼容 bullet 列表 + 新表格格式）────────────────────────────────
def _extract_seeds_from_table(block: str) -> List[str]:
    """从表格行提取 seed 描述（兼容 | Seed ID | 入口状态 | 核心操作 | 预期结果 | 格式）。"""
    seeds = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---") or "Seed" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) >= 4:
            # F01-S01 | 入口状态 | 核心操作 | 预期结果
            entry_state = cols[1]
            operation   = cols[2]
            expected    = cols[3]
            combined = f"{entry_state}-{operation}-{expected}".strip("-")
            if combined:
                seeds.append(combined)
    return seeds


def parse_seeds(spec_text: str, feature_id: str) -> List[str]:
    """
    从 spec.md 第 7 章提取指定 feature_id 的 seeds。
    同时支持 bullet 列表和新表格格式。
    """
    # 找到第 7 章
    sec7_m = re.search(
        r'(?:^#{1,3}\s*7[.、．].*?Raw Case Seeds.*?$)(.*?)(?:^---|\Z)',
        spec_text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not sec7_m:
        return []
    sec7 = sec7_m.group(1)

    # 找到对应 feature_id 的子节
    fid_escaped = re.escape(feature_id)
    fid_pat = r'(?:^#{1,6}\s*' + fid_escaped + r'(?:\s|$))(.*?)(?:^#{1,6}\s*F-\d+|\Z)'
    fid_m = re.search(fid_pat, sec7, re.MULTILINE | re.DOTALL)
    if not fid_m:
        return []
    block = fid_m.group(1)

    # 优先尝试表格格式
    table_seeds = _extract_seeds_from_table(block)
    if table_seeds:
        return table_seeds

    # 回退到 bullet 列表
    return [
        m.group(1).strip()
        for m in re.finditer(r'^[-*•]\s+(.+)$', block, re.MULTILINE)
        if m.group(1).strip()
    ]


# ── Case titles 提取 ──────────────────────────────────────────────────────────
def extract_case_titles(cases_json: list) -> List[str]:
    """从 Pass 2 输出的 cases JSON 数组中提取 title 列表。"""
    titles = []
    for c in cases_json:
        t = c.get("title", "").strip()
        if t:
            titles.append(t)
    return titles


# ── 角色覆盖检查 ──────────────────────────────────────────────────────────────
def _detect_roles_in_seeds(seeds: List[str]) -> Dict[str, List[str]]:
    """返回 {角色名: [含该角色的 seed 列表]}。"""
    role_seeds: Dict[str, List[str]] = {}
    for seed in seeds:
        for role, kws in _ROLE_PATTERNS.items():
            if any(kw in seed for kw in kws):
                role_seeds.setdefault(role, []).append(seed)
    return role_seeds


def _role_covered(role: str, seed: str, case_titles: List[str]) -> bool:
    """检查含特定角色的 seed 是否被 case_titles 中某条用例覆盖（语义 + 角色）。"""
    kws = _ROLE_PATTERNS.get(role, [role])
    for title in case_titles:
        if any(kw in title for kw in kws):
            hit, total = _match_score(seed, title)
            if total > 0 and hit / total >= 0.3:
                return True
    return False


# ── 时间节点覆盖检查 ──────────────────────────────────────────────────────────
def _extract_time_nodes(texts: List[str]) -> Dict[str, List[str]]:
    """返回 {时间标签: [含该标签的文本列表]}。"""
    node_map: Dict[str, List[str]] = {}
    for text in texts:
        for m in _TIME_PAT.finditer(text):
            node = m.group(0).strip()
            node_map.setdefault(node, []).append(text)
    return node_map


def _time_node_covered(node: str, seed: str, case_titles: List[str]) -> bool:
    for title in case_titles:
        if node in title:
            hit, total = _match_score(seed, title)
            if total > 0 and hit / total >= 0.25:
                return True
    return False


# ── 主入口 ────────────────────────────────────────────────────────────────────
_MATCH_THRESHOLD = 0.4   # 命中率 ≥ 40% 视为"已覆盖"
_MATCH_MIN_HIT   = 2     # 至少命中 2 个关键词


def validate(
    feature_id: str,
    cases_json: list,
    spec_text: str,
    *,
    match_threshold: float = _MATCH_THRESHOLD,
    match_min_hit: int = _MATCH_MIN_HIT,
) -> ValidationResult:
    seeds = parse_seeds(spec_text, feature_id)
    titles = extract_case_titles(cases_json)

    result = ValidationResult(
        feature_id=feature_id,
        seed_total=len(seeds),
        case_total=len(titles),
        covered=0,
    )

    if not seeds:
        return result

    # ── 1. Seed 覆盖 diff ──────────────────────────────────────────────────────
    uncovered_seeds: List[str] = []
    for seed in seeds:
        best_title, hit, total = _find_best_match(seed, titles)
        if total > 0 and hit >= match_min_hit and hit / total >= match_threshold:
            result.covered += 1
        else:
            uncovered_seeds.append(seed)
            result.violations.append(Violation(
                type="seed_gap",
                seed=seed,
                reason=f"无匹配 case（关键词命中 {hit}/{total}）",
                suggestion="新增覆盖该场景的独立用例",
                matched_case=best_title,
            ))

    # ── 2. 角色覆盖检查 ────────────────────────────────────────────────────────
    role_seeds = _detect_roles_in_seeds(uncovered_seeds)
    for role, r_seeds in role_seeds.items():
        for seed in r_seeds:
            if not _role_covered(role, seed, titles):
                # 避免与 seed_gap 重复
                if not any(v.type == "role_gap" and v.seed == seed for v in result.violations):
                    result.violations.append(Violation(
                        type="role_gap",
                        seed=seed,
                        reason=f"角色「{role}」在已生成用例中无对应覆盖",
                        suggestion=f"为「{role}」角色单独生成该场景的用例",
                    ))

    # ── 3. 时间节点覆盖检查 ────────────────────────────────────────────────────
    all_time_nodes = _extract_time_nodes(seeds)
    case_time_nodes = set()
    for t in titles:
        for m in _TIME_PAT.finditer(t):
            case_time_nodes.add(m.group(0).strip())

    for node, node_seeds in all_time_nodes.items():
        if node not in case_time_nodes:
            for seed in node_seeds:
                if not any(v.seed == seed and v.type == "time_gap" for v in result.violations):
                    result.violations.append(Violation(
                        type="time_gap",
                        seed=seed,
                        reason=f"时间节点「{node}」在已生成用例标题中未出现",
                        suggestion=f"新增入口状态含「{node}」的独立用例",
                    ))

    return result
