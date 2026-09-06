"""
RAG Bug 召回与 TestModel 补充（可选模块，默认关闭）

从知识库召回 bug，LLM 分析后合并到 TestModel。
当前阶段数据较少、检索效果不稳定，默认不启用。
需要启用时在 SKILL.md 工作流中显式指定。
"""
import asyncio
import json
import re as _re
from typing import Dict, Any, List

from script.test_model import TestModel, FeatureModel, CaseBlock, StepExpected
from script.prompts import BUG_ANALYSIS_PROMPT
from script.llm_utils import extract_json_from_llm_response
from script.knowledge_service import knowledge_service_chat
from script.device_role_skills import roles_prompt_context_short


def build_rag_queries(feature_names: List[str], user_req: str, max_queries: int = 8) -> List[str]:
    """从功能点名称中提取域词+特征词，组合出知识库检索词。"""
    domain_word = ""
    if len(feature_names) >= 2:
        for length in range(2, 8):
            candidates: dict[str, int] = {}
            for fname in feature_names:
                if len(fname) >= length:
                    prefix = fname[:length]
                    candidates[prefix] = candidates.get(prefix, 0) + 1
            best = max(candidates.items(), key=lambda x: x[1]) if candidates else ("", 0)
            if best[1] >= max(len(feature_names) * 0.4, 2):
                domain_word = best[0]
            else:
                break

    _TRIM = _re.compile(r'^[\s与及、/\-]+')
    feature_short: list[str] = []
    for fname in feature_names:
        rest = fname[len(domain_word):] if fname.startswith(domain_word) else fname
        rest = _TRIM.sub("", rest)
        short = rest[:6].split("与")[0].split("及")[0].split("（")[0].strip()
        if short and len(short) >= 2:
            feature_short.append(short)

    queries: list[str] = []
    seen: set[str] = set()

    def _add(q: str):
        q = q.strip()
        if q and q not in seen and len(queries) < max_queries:
            seen.add(q)
            queries.append(q)

    if domain_word:
        _add(domain_word)
    for fs in feature_short:
        _add(f"{domain_word} {fs}" if domain_word else fs)
    if not queries:
        _add(user_req or "测试用例")

    return queries


def enrich_test_model_with_rag(
    test_model_data: dict,
    llm_analyze_fn=None,
    user_requirement: str = "",
) -> dict:
    """
    同步版 RAG 补充入口。

    Args:
        test_model_data: TestModel dict
        llm_analyze_fn: 可选的 LLM 分析函数（默认使用内置知识库）
        user_requirement: 用户需求
    Returns:
        enriched TestModel dict
    """
    print("[rag] RAG Bug Regression Enrichment (enabled)")

    feature_names = [
        f.get("feature_name", "")
        for f in test_model_data.get("features", [])
        if f.get("feature_name")
    ]
    queries = build_rag_queries(feature_names, user_requirement)
    print(f"[rag] queries({len(queries)}): {queries}")

    seen_ids: set = set()
    merged_chunks: list[str] = []
    for q in queries[:6]:
        try:
            result = knowledge_service_chat(q)
            content = result.get("content", "") if isinstance(result, dict) else ""
            if content and len(content.strip()) > 10:
                merged_chunks.append(content)
        except Exception as e:
            print(f"[rag] KB query failed ({q[:30]}): {e}")

    merged_content = "\n\n---\n".join(merged_chunks)
    if not merged_content.strip():
        print("[rag] No bugs retrieved")
        return test_model_data

    bug_entries = []
    for block in _re.split(r'\n---\n', merged_content):
        block = block.strip()
        if not block or len(block) < 50:
            continue
        bug_id_match = _re.match(r'\[(\d+)\]', block)
        bid = bug_id_match.group(1) if bug_id_match else block[:30]
        if bid not in seen_ids:
            seen_ids.add(bid)
            bug_entries.append(block)

    if not bug_entries:
        print("[rag] No valid bug entries parsed")
        return test_model_data

    print(f"[rag] Retrieved {len(bug_entries)} bugs (analysis requires LLM - returning raw for agent)")
    return test_model_data
