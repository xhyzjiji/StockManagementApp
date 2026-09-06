"""
LLM 调用相关工具函数（JSON 提取、FeatureModel 解析等）。
"""
from __future__ import annotations

import json
from typing import Optional

from script.test_model import FeatureModel, CaseBlock, StepExpected


def extract_json_from_llm_response(raw: str) -> str:
    """从 LLM 回复中提取 JSON 文本（可能带 ```json ... ``` 包裹）。"""
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{") or p.startswith("["):
                return p
    return raw


def parse_feature_json(data: dict) -> Optional[FeatureModel]:
    """将 LLM 返回的简化 JSON dict 转为 FeatureModel。"""
    try:
        cases = []
        for c in data.get("cases", []):
            pairs = [
                StepExpected(step=p["step"], expected=p.get("expected", []))
                for p in c.get("step_expected_pairs", [])
            ]
            cases.append(CaseBlock(
                title=c.get("title", ""),
                preconditions=c.get("preconditions", []),
                step_expected_pairs=pairs,
            ))
        roles = data.get("primary_roles")
        if not isinstance(roles, list):
            roles = []
        roles = [str(x).strip() for x in roles if str(x).strip()]

        return FeatureModel(
            feature_id=data.get("feature_id", ""),
            feature_name=data.get("feature_name", ""),
            primary_roles=roles,
            cases=cases,
        )
    except Exception:
        return None


def try_repair_truncated_json(raw: str) -> Optional[dict]:
    """尝试修复被 max_tokens 截断的 JSON。"""
    last_case_end = raw.rfind('"expected"')
    if last_case_end == -1:
        return None

    last_complete_brace = raw.rfind('}', 0, len(raw))
    second_last = raw.rfind('}', 0, last_complete_brace)
    if second_last == -1:
        return None

    for cut_pos in [last_complete_brace, second_last]:
        candidate = raw[:cut_pos + 1]
        open_brackets = candidate.count('[') - candidate.count(']')
        open_braces = candidate.count('{') - candidate.count('}')
        suffix = ']' * open_brackets + '}' * open_braces
        try:
            data = json.loads(candidate + suffix)
            if isinstance(data, dict) and "cases" in data and len(data["cases"]) > 0:
                print(f"[llm_utils] JSON repair success: recovered {len(data['cases'])} cases")
                return data
        except json.JSONDecodeError:
            continue
    return None
