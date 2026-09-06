"""
导航链构建器 + 前置配方解析器。

导航链：从 spec 依赖图 + ui_routes.txt 规则化生成完整导航路径（无需 LLM）。
配方解析器：将 spec 中纯业务语言的前置实现配方拆分为"工具可替代"与"GUI 操作"两部分，
实现 spec（业务语言）与 case（工具+GUI）的职责边界。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

from script.seed_parser import ParsedSpec, SetupRecipe
from script.ui_enricher import ui_routes_prompt_context

if TYPE_CHECKING:
    from script.tool_skills import ToolSkill


@dataclass
class ResolvedRecipe:
    """A setup recipe split into tool-resolvable and GUI-only steps."""
    dependency_desc: str
    target_feature: str
    tool_preconditions: List[str] = field(default_factory=list)
    gui_steps: List[str] = field(default_factory=list)


_STEP_SEPARATOR_RE = None

def _split_recipe_steps(steps_text: str) -> List[str]:
    """Split '步骤1 → 步骤2 → ...' into individual steps."""
    import re
    parts = re.split(r'\s*→\s*', steps_text)
    return [p.strip() for p in parts if p.strip()]


def resolve_recipe(
    recipe: SetupRecipe,
    tools: Optional[List["ToolSkill"]] = None,
) -> ResolvedRecipe:
    """Match each step in a recipe against registered tools.

    Environment tools go to tool_preconditions; flow tools (step-only)
    and unmatched steps stay as gui_steps for LLM to expand.
    """
    if tools is None:
        from script.tool_skills import TOOL_SKILLS
        tools = TOOL_SKILLS
    from script.tool_skills import _STEP_ONLY_TOOLS

    resolved = ResolvedRecipe(
        dependency_desc=recipe.dependency_desc,
        target_feature=recipe.target_feature,
    )

    if not recipe.steps:
        return resolved

    steps = _split_recipe_steps(recipe.steps)
    for step in steps:
        matched_tool = _match_step_to_tool(step, tools)
        if matched_tool:
            if matched_tool.name_en in _STEP_ONLY_TOOLS:
                resolved.gui_steps.append(f"{matched_tool.name}（流程工具，写入 step_expected_pairs）")
            elif matched_tool.name not in resolved.tool_preconditions:
                resolved.tool_preconditions.append(matched_tool.name)
        else:
            resolved.gui_steps.append(step)

    return resolved


def _match_step_to_tool(step: str, tools: List["ToolSkill"]) -> Optional["ToolSkill"]:
    """Check if a business-language step can be replaced by a tool."""
    from script.tool_skills import _matches_tool_by_name, _matches_tool_by_keyword
    for tool in tools:
        if _matches_tool_by_name(step, tool):
            return tool
    for tool in tools:
        if _matches_tool_by_keyword(step, tool):
            return tool
    return None


def resolve_recipes_for_feature(
    feature_id: str,
    spec: ParsedSpec,
    tools: Optional[List["ToolSkill"]] = None,
) -> List[ResolvedRecipe]:
    """Resolve all setup recipes along the full dependency chain for a feature."""
    deps = _build_transitive_deps(feature_id, spec.dependency_graph)
    all_fids = deps + [feature_id]

    resolved: List[ResolvedRecipe] = []
    for fid in all_fids:
        fid_meta = spec.features.get(fid)
        if not fid_meta:
            continue
        for recipe in fid_meta.setup_recipes:
            resolved.append(resolve_recipe(recipe, tools))

    return resolved


def format_resolved_recipes(resolved_list: List[ResolvedRecipe]) -> str:
    """Format resolved recipes into a prompt context block with clear tool/GUI split."""
    if not resolved_list:
        return ""

    all_tools: List[str] = []
    all_gui: List[str] = []

    lines: List[str] = []
    for r in resolved_list:
        lines.append(f"- {r.dependency_desc}")
        if r.tool_preconditions:
            tools_str = ", ".join(r.tool_preconditions)
            lines.append(f"  ✅ 工具可替代：{tools_str}（放入 preconditions）")
            for t in r.tool_preconditions:
                if t not in all_tools:
                    all_tools.append(t)
        if r.gui_steps:
            gui_str = " → ".join(r.gui_steps)
            lines.append(f"  🔧 GUI 操作：{gui_str}（展开为 step_expected_pairs）")
            all_gui.extend(r.gui_steps)

    summary = []
    if all_tools:
        summary.append(f"工具前置条件（直接放入 preconditions）：{', '.join(all_tools)}")
    if all_gui:
        summary.append(f"GUI 步骤（必须写入 step_expected_pairs）：{' → '.join(all_gui)}")
    # 显式锁定：防止 LLM 自行引入列表之外的工具替代
    summary.append("⚠️ 工具替代范围锁定：preconditions 中只允许出现上方「工具前置条件」列出的工具名；"
                   "「GUI 步骤」中的任何步骤不得替换为工具，必须保留为 GUI 操作。"
                   "禁止在 preconditions 中自行添加可用工具列表之外的工具名。")

    return "\n".join(["【前置配方解析结果】", ""] + lines + ["", "【汇总】"] + summary)


def _build_transitive_deps(
    feature_id: str,
    dep_graph: Dict[str, List[str]],
) -> List[str]:
    """BFS 计算传递依赖链（按依赖深度排序，根节点在前）。"""
    visited = set()
    order = []
    queue = list(dep_graph.get(feature_id, []))
    while queue:
        fid = queue.pop(0)
        if fid in visited:
            continue
        visited.add(fid)
        order.append(fid)
        queue.extend(dep_graph.get(fid, []))
    order.reverse()
    return order


def build_nav_chains(spec: ParsedSpec) -> Dict[str, str]:
    """
    为每个 Feature 生成导航路径描述文本。

    返回 {feature_id: nav_description} 字典，
    每个 nav_description 包含从首页到该功能入口的完整步骤链。
    """
    ui_routes = ui_routes_prompt_context()

    chains: Dict[str, str] = {}
    for fid in spec.feature_ids:
        meta = spec.features.get(fid)
        if not meta:
            continue

        deps = _build_transitive_deps(fid, spec.dependency_graph)

        parts = ["TikTok 首页"]

        for dep_fid in deps:
            dep_meta = spec.features.get(dep_fid)
            if dep_meta:
                parts.append(f"[{dep_fid} {dep_meta.feature_name}] 完成前置")

        parts.append(f"进入 {meta.feature_name} 入口")

        chains[fid] = " → ".join(parts)

    return chains


def build_setup_recipe_chain(
    feature_id: str,
    spec: ParsedSpec,
) -> str:
    """
    为单个 Feature 构建完整的前置实现配方链。

    沿依赖链收集所有 setup recipes，按执行顺序拼接。
    如果 spec 中没有显式 recipe，则从依赖 Feature 的用户路径中提取关键步骤。
    """
    deps = _build_transitive_deps(feature_id, spec.dependency_graph)
    meta = spec.features.get(feature_id)
    if not meta:
        return ""

    recipe_lines: list[str] = []

    all_fids = deps + [feature_id]
    for fid in all_fids:
        fid_meta = spec.features.get(fid)
        if not fid_meta:
            continue
        for recipe in fid_meta.setup_recipes:
            if recipe.steps:
                recipe_lines.append(
                    f"- {recipe.dependency_desc}\n"
                    f"  前置实现：{recipe.steps}"
                )
            else:
                recipe_lines.append(
                    f"- {recipe.dependency_desc}（⚠️ 无显式配方，需从 {recipe.target_feature} 的场景描述中推导具体步骤）"
                )

    if not recipe_lines:
        if meta.depends_on:
            for dep_fid in meta.depends_on:
                dep_meta = spec.features.get(dep_fid)
                dep_name = dep_meta.feature_name if dep_meta else dep_fid
                recipe_lines.append(
                    f"- 依赖 {dep_fid}（{dep_name}）的完成状态（⚠️ 无显式配方，需从功能点描述中推导具体步骤）"
                )

    if not recipe_lines:
        return ""

    return "\n".join(recipe_lines)


def build_nav_context_for_feature(
    feature_id: str,
    spec: ParsedSpec,
    nav_chains: Optional[Dict[str, str]] = None,
) -> str:
    """为单个 Feature 生成导航链 + 已解析配方上下文块。

    配方已被拆分为 工具前置条件 + GUI 操作步骤，LLM 只需：
    - 将工具名放入 preconditions
    - 将 GUI 步骤展开为 step_expected_pairs
    """
    if nav_chains is None:
        nav_chains = build_nav_chains(spec)

    chain = nav_chains.get(feature_id, "TikTok 首页 → 功能入口")
    meta = spec.features.get(feature_id)

    lines = [f"【{feature_id} 导航路径】"]
    lines.append(f"完整路径：{chain}")

    if meta and meta.depends_on:
        lines.append(f"直接依赖：{', '.join(meta.depends_on)}")

    deps = _build_transitive_deps(feature_id, spec.dependency_graph)
    if deps:
        ancestor_parts = []
        for dep_fid in deps:
            dep_meta = spec.features.get(dep_fid)
            name = dep_meta.feature_name if dep_meta else dep_fid
            ancestor_parts.append(f"{dep_fid}（{name}）")
        lines.append(f"传递依赖链：{' → '.join(ancestor_parts)} → {feature_id}")

    resolved = resolve_recipes_for_feature(feature_id, spec)
    if resolved:
        lines.append("")
        resolved_text = format_resolved_recipes(resolved)
        lines.append(resolved_text)
        lines.append("")
        lines.append("⚠️ AutoGLM 每条用例从 App 冷启动独立执行：")
        lines.append("  - 「工具可替代」步骤 → 放入 preconditions（工具名称）")
        lines.append("  - 「GUI 操作」步骤 → 写入 step_expected_pairs 中的真实操作")
        lines.append("  - 不可用 hint 代替功能依赖！")
    else:
        recipe_chain = build_setup_recipe_chain(feature_id, spec)
        if recipe_chain:
            lines.append("")
            lines.append("【前置实现配方（Setup Recipes）— 必须展开为真实步骤】")
            lines.append(recipe_chain)

    lines.append("")
    lines.append("【已知 UI 导航路径（作为路径参考）】")
    lines.append(ui_routes_prompt_context())

    return "\n".join(lines)
