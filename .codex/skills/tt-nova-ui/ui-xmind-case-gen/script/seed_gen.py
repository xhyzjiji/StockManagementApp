"""
Seeds 生成辅助模块 — 三项上下文优化算法。

优化 4: 用例分类预处理（mechanical vs semantic）
    将原始用例分为"断言清晰可直接转化"的机械型，和"断言模糊需 LLM 润色"的语义型。
    典型场景下约 60~70% 为机械型，可绕过 LLM，大幅降低上下文压力。

优化 3: Coverage Bitmap 驱动的增量验证
    对比 spec 第 7 章的 seeds 数量与原始有效用例数，输出覆盖率报告。
    若存在缺口（seeds < cases），输出需要补充的 Feature 列表及缺口大小。

优化 2: Map-Reduce 分批处理超大 Feature
    将大 Feature（>BATCH_SIZE 条用例）按模块子树切分为若干批次，
    每批独立生成带「数量契约」的 LLM Prompt，最终 Reduce 合并重编号。

CLI 入口（在 script.py 中注册）：
    seed-classify   <cases.json>              分类报告（优化 4）
    seed-coverage   <spec.md> --cases F-XX=path ...   覆盖率报告（优化 3）
    seed-gen-prompts <cases.json> <feature_id>        分批 Prompt（优化 2+4）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RawCase:
    """原始有效用例（来自 xlsx/json，已过滤空行）。"""
    row_id: str
    module: str        # 功能模块路径，如 "语聊房迁移/主播端/直播间"
    title: str
    precond: str
    steps: str
    expected: str
    priority: str = ""
    case_type: Literal["mechanical", "semantic"] = "mechanical"


@dataclass
class CoverageResult:
    """单个 Feature 的 Coverage Bitmap 检查结果。"""
    feature_id: str
    total_seeds: int   # spec 第 7 章中该 Feature 的 seeds 行数
    total_cases: int   # 原始有效用例数
    coverage_rate: float
    gap: int           # max(0, total_cases - total_seeds)
    status: Literal["ok", "gap"] = "ok"

    def to_dict(self) -> dict:
        return {
            "feature_id":    self.feature_id,
            "total_seeds":   self.total_seeds,
            "total_cases":   self.total_cases,
            "coverage_rate": round(self.coverage_rate, 3),
            "gap":           self.gap,
            "status":        self.status,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 优化 4: 用例分类
# ─────────────────────────────────────────────────────────────────────────────

# 模糊断言模式（命中 → semantic）
_VAGUE_RE = re.compile(
    r"展示正常|正常展示|正常显示|正常运行|符合预期|正确展示"
    r"|应该正常|没有问题|样式正常|界面正常|功能正常|正常跳转"
    r"|加载正常|响应正常|运行正常",
    re.IGNORECASE,
)

# 预期结果以动词开头但无角色主语（命中 → semantic）
_MISSING_ROLE_RE = re.compile(
    r"^(?:展示|显示|弹出|跳转|触发|出现|消失|提示|更新|刷新|播放|加载)"
    r"(?![^\n]*(?:主播|嘉宾|观众|管理员|\[|\（|端))",
)


def classify_case(case: RawCase) -> Literal["mechanical", "semantic"]:
    """
    优化 4：判断用例类型。

    mechanical — 断言清晰可观测，规则引擎可直接转化为 seed 行。
    semantic   — 断言含模糊表达或缺失角色主语，需要 LLM 润色后生成 seed。
    """
    combined = f"{case.expected}\n{case.steps}"

    if _VAGUE_RE.search(combined):
        return "semantic"

    first_line = case.expected.strip().split("\n")[0].strip()
    if _MISSING_ROLE_RE.match(first_line):
        return "semantic"

    # 预期结果极短（< 5 字符），可能是空或无意义
    if len(case.expected.strip()) < 5:
        return "semantic"

    return "mechanical"


def classify_cases(cases: List[RawCase]) -> Tuple[List[RawCase], List[RawCase]]:
    """
    批量分类，同时更新 case.case_type 字段。
    返回 (mechanical_cases, semantic_cases)。
    """
    mechanical, semantic = [], []
    for case in cases:
        case.case_type = classify_case(case)
        (mechanical if case.case_type == "mechanical" else semantic).append(case)
    return mechanical, semantic


def classify_report(cases: List[RawCase]) -> dict:
    """生成分类统计报告 dict，可直接 JSON 序列化输出。"""
    mechanical, semantic = classify_cases(cases)
    return {
        "total": len(cases),
        "mechanical": len(mechanical),
        "semantic": len(semantic),
        "semantic_ratio": round(len(semantic) / max(len(cases), 1), 3),
        "llm_load_reduction": f"{round(len(mechanical) / max(len(cases), 1) * 100)}%",
        "sample_semantic": [
            {"title": c.title, "expected": c.expected[:100]}
            for c in semantic[:5]
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 优化 2: Map-Reduce 分批
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_BATCH_SIZE = 20  # 每批 ≤ 20 条；LLM 输入 < 3K tokens，输出质量稳定


def split_into_batches(
    cases: List[RawCase],
    batch_size: int = DEFAULT_BATCH_SIZE,
    group_by_module: bool = True,
) -> List[List[RawCase]]:
    """
    优化 2 — Map 阶段：将用例列表切分为若干批次。

    group_by_module=True（默认）：
        先按模块路径第 3 层分组，再切分。同场景用例聚合在同一批次，
        LLM 上下文更连贯，拆行更准确。

    group_by_module=False：
        简单顺序切分，适用于模块路径缺失的情况。
    """
    if not group_by_module or not cases:
        return [cases[i:i + batch_size] for i in range(0, len(cases), batch_size)]

    # 按模块路径前 3 层分组
    groups: Dict[str, List[RawCase]] = {}
    for case in cases:
        parts = case.module.split("/")
        key = "/".join(parts[:3]) if len(parts) >= 3 else (parts[0] if parts else "default")
        groups.setdefault(key, []).append(case)

    batches: List[List[RawCase]] = []
    current: List[RawCase] = []

    for group_cases in groups.values():
        # 单个组本身超限 → 强制拆分
        if len(group_cases) > batch_size:
            if current:
                batches.append(current)
                current = []
            for i in range(0, len(group_cases), batch_size):
                batches.append(group_cases[i:i + batch_size])
            continue

        # 加入当前组后会超限 → 先 flush
        if current and len(current) + len(group_cases) > batch_size:
            batches.append(current)
            current = []

        current.extend(group_cases)

    if current:
        batches.append(current)

    return batches


def build_batch_prompt(
    batch: List[RawCase],
    feature_id: str,
    feature_name: str,
    total_n: int,
    batch_idx: int,
    batch_total: int,
    start_seed_num: int,
) -> str:
    """
    优化 2+3：为一个批次构建带「数量契约」的 LLM Prompt。

    关键设计点：
    1. 告知 LLM 本批用例数 N，要求 seeds ≥ N（数量下界契约）
    2. 标注每条用例的类型 [M]/[S]，[S] 类型要求改写断言
    3. 要求 LLM 在表格后写自检行，防止静默遗漏
    4. Seed ID 从 start_seed_num 开始编号，便于 Reduce 阶段合并
    """
    fid_clean = feature_id.replace("-", "")   # "F01"
    seed_prefix = fid_clean.upper()            # "F01"

    cases_block_lines = []
    for i, c in enumerate(batch):
        type_tag = "[M]" if c.case_type == "mechanical" else "[S]"
        cases_block_lines.append(
            f"{i + 1}. {type_tag} 标题：{c.title}\n"
            f"   前置：{c.precond[:120] if c.precond else '（无）'}\n"
            f"   步骤：{c.steps[:180] if c.steps else '（无）'}\n"
            f"   预期：{c.expected[:250] if c.expected else '（无）'}"
        )
    cases_block = "\n\n".join(cases_block_lines)

    seed_id_example = f"{seed_prefix}-S{start_seed_num:03d}"

    return f"""你正在为功能 {feature_id}（{feature_name}）的第 7 章 Raw Case Seeds 生成表格。

## 批次信息
- 当前批次：第 {batch_idx + 1} / {batch_total} 批
- 本批用例数：{len(batch)} 条（整个功能共 {total_n} 条有效用例）
- 用例类型标注：[M] = 机械型（断言清晰，直接转化）；[S] = 语义型（需润色断言）

## 数量契约（核心约束，不可违反）
本批 {len(batch)} 条用例 → 生成的 Seeds 行数必须 ≥ {len(batch)}。
经以下拆行规则处理后，实际行数通常 > 原始用例数。
**禁止**将多条用例合并为一行，**禁止**省略任何一条用例。

## 拆行规则（每条规则命中时均需拆行）
1. 预期结果含"；""且""并且""同时"→ 每个结论单独一行（保持相同入口状态）
2. 步骤或预期含"/"或"、"列举多个值 → 每个枚举值单独一行（保持相同入口状态）
3. 涉及多个角色（主播 / 嘉宾 / 观众 / 管理员）→ 每个角色单独一行，入口状态注明角色身份
4. [S] 类型：将"展示正常""符合预期"等模糊断言改写为可直接观察的具体 UI 描述

## 入口状态书写要求
- 必须精确到具体状态值（如"竞猜进行中，观众未作答"），不能写"在直播间"
- 不可依赖上一条 seed 的结果（每条 seed 从 App 冷启动独立执行）
- 多角色场景：在入口状态中明确写出角色身份

## 输出格式
只输出 Markdown 表格，不要输出其他内容。Seed ID 从 {seed_id_example} 开始：

| Seed ID | 入口状态（前置） | 核心操作 | 预期结果 |
|---------|----------------|---------|---------|
| {seed_id_example} | ... | ... | ... |

## 本批次用例（共 {len(batch)} 条）

{cases_block}

---
**自检（表格后必须写这一行）**：本批次生成 X 行，覆盖用例 {len(batch)}/{len(batch)} 条。"""


# ─────────────────────────────────────────────────────────────────────────────
# 优化 3: Coverage Bitmap
# ─────────────────────────────────────────────────────────────────────────────

def build_coverage_map(
    spec_seeds_count: Dict[str, int],
    valid_cases: Dict[str, List[RawCase]],
) -> Dict[str, CoverageResult]:
    """
    优化 3：构建 Coverage Bitmap。

    由于 LLM 生成的 seeds 无显式 source_case_id，使用「seeds 数量 ≥ cases 数量」
    作为覆盖率的代理指标（保守估计，实际覆盖率可能更高）。

    Args:
        spec_seeds_count: {feature_id: seeds_row_count}，来自 spec 第 7 章解析
        valid_cases:      {feature_id: [RawCase, ...]}，来自预过滤后的有效用例

    Returns:
        {feature_id: CoverageResult}
    """
    all_fids = set(spec_seeds_count) | set(valid_cases)
    results: Dict[str, CoverageResult] = {}

    for fid in sorted(all_fids):
        seeds_n = spec_seeds_count.get(fid, 0)
        cases_n = len(valid_cases.get(fid, []))
        gap = max(0, cases_n - seeds_n)
        rate = seeds_n / max(cases_n, 1)

        results[fid] = CoverageResult(
            feature_id=fid,
            total_seeds=seeds_n,
            total_cases=cases_n,
            coverage_rate=rate,
            gap=gap,
            status="ok" if gap == 0 else "gap",
        )

    return results


def coverage_report(coverage: Dict[str, CoverageResult]) -> dict:
    """将 Coverage Bitmap 转为可序列化的报告 dict。"""
    gap_features = sorted(
        [(fid, r.gap) for fid, r in coverage.items() if r.status == "gap"],
        key=lambda x: -x[1],
    )
    total_seeds = sum(r.total_seeds for r in coverage.values())
    total_cases = sum(r.total_cases for r in coverage.values())

    return {
        "overall": {
            "total_seeds": total_seeds,
            "total_cases": total_cases,
            "coverage_rate": round(total_seeds / max(total_cases, 1), 3),
            "status": "ok" if not gap_features else "gap",
            "gap_features": [
                {"feature_id": fid, "gap": gap} for fid, gap in gap_features
            ],
        },
        "features": {fid: r.to_dict() for fid, r in coverage.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# I/O 工具
# ─────────────────────────────────────────────────────────────────────────────

def load_raw_cases_from_json(path: str) -> List[RawCase]:
    """
    从 valid_*.json 加载 RawCase 列表。

    JSON 格式（与 ui-xmind-case-specify 流程对齐）：
    [{"id": "...", "module": "...", "title": "...",
      "precond": "...", "steps": "...", "expected": "...", "priority": "..."}]
    """
    import json
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    cases = []
    for item in data:
        cases.append(RawCase(
            row_id=str(item.get("id", "")),
            module=item.get("module", ""),
            title=item.get("title", ""),
            precond=item.get("precond", ""),
            steps=item.get("steps", ""),
            expected=item.get("expected", ""),
            priority=item.get("priority", ""),
        ))
    return cases
