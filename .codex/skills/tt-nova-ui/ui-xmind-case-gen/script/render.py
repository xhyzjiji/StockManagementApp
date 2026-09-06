"""
渲染管线：TestModel JSON → (Markdown 测试文档, RichText 列表)

1. 校验 TestModel
2. 后处理：工具关键词替换为 richtext 占位
3. 渲染为 Markdown
4. 从 Markdown 提取 richtext 列表（按出现顺序去重）
"""

import json
import re
from typing import Any, Dict, List, Tuple

from script.test_model import TestModel, test_model_to_markdown
from script.tool_skills import (
    MissingRequiredToolParams,
    apply_tool_skills,
    enforce_region_and_tags,
    reset_dynamic_registry,
    richtext_registry,
)

_RICHTEXT_PLACEHOLDER_RE = re.compile(r"\$\{richText_([^:]+):\s*([^}]*)\}")


def _missing_required_params_prompt(exc: MissingRequiredToolParams) -> str:
    missing = ", ".join(f"`{name}`" for name in exc.missing_params)
    example = " ".join(f"{name}=..." for name in exc.missing_params)
    return (
        f"{exc.tool_name} 缺少必填参数：{missing}。"
        f"请补充后重试，例如：`{exc.tool_name} {example}`"
    )


def extract_richtext_from_markdown(markdown: str) -> List[Dict[str, Any]]:
    """从 markdown 解析 ${richText_<uuid>:<name>}，按出现顺序去重，用预置结构填充。"""
    if not markdown or not isinstance(markdown, str):
        return []
    seen = set()
    order = []
    for m in _RICHTEXT_PLACEHOLDER_RE.finditer(markdown):
        uid = (m.group(1) or "").strip()
        if uid and uid not in seen:
            seen.add(uid)
            order.append(uid)
    registry = richtext_registry()
    out = []
    for uid in order:
        item = registry.get(uid)
        if item is not None:
            out.append(item)
        else:
            out.append(
                {
                    "type": 2,
                    "text": f"Tool({uid})",
                    "id": uid,
                    "mentionType": 31,
                    "token": "32",
                    "uuid": uid,
                    "pluginData": None,
                }
            )
    return out


def render_test_model(test_model_data: dict) -> Tuple[str, List[Dict[str, Any]]]:
    """
    完整渲染管线。

    Args:
        test_model_data: TestModel.model_dump() 的 dict

    Returns:
        (markdown_str, richtext_list)

    Raises:
        MissingRequiredToolParams: 当工具缺少必填参数时抛出，由 skill 层处理交互
    """
    if not test_model_data:
        return "", []

    model = TestModel.model_validate(test_model_data)

    reset_dynamic_registry()
    # 不捕获 MissingRequiredToolParams，让 skill 层处理交互
    for feat in model.features:
        # 先做地区识别：涉及 US/EU 的用例补 ttmock_preset 地区 + 打 US/EU 标签，
        # 再交给 apply_tool_skills 把前置条件文本转换为 richtext 占位符。
        enforce_region_and_tags(feat.cases)
        apply_tool_skills(feat.cases)

    markdown = test_model_to_markdown(model)
    richtext_list = extract_richtext_from_markdown(markdown)

    print(
        f"[render] Markdown: {len(markdown)} chars, RichText: {len(richtext_list)} items"
    )
    return markdown, richtext_list


def render_from_json_file(json_path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """从 JSON 文件读取 TestModel 并渲染。"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return render_test_model(data)
