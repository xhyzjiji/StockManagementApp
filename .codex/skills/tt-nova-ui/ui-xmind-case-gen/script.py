"""
ui-xmind-case-gen skill CLI 入口。

子命令：

── Seed-based pipeline（推荐）──────────────────────────────────────────────
    seed-info       <spec.md>                 显示 seed 统计（Feature 列表、seed 数、依赖关系）
    seed-prompt     <spec.md> <feature-id>    为单个 Feature 生成 Seed → Case 展开 Prompt
    seed-assemble   <spec.md>                 合并各 Feature 的 cases → TestModel JSON
                    --cases <F-01=f1.json> …
                    [-o <output.json>]
    check-json-object <text>                  判断字符串是否为 JSON 对象 string（供 LLM 自检 ab_settings）
                    [--param ab_settings]

── 上下文优化算法命令（Opt 2/3/4）──────────────────────────────────────────
    seed-classify   <cases.json>              [优化4] 用例分类：机械型 vs 语义型
                    [-o <report.json>]
    seed-coverage   <spec.md>                 [优化3] Coverage Bitmap：对比 seeds 数 vs 有效用例数
                    --cases <F-01=path.json>…  输出各 Feature 的覆盖率与缺口
                    [-o <coverage.json>]
    seed-gen-prompts <cases.json> <feature-id> [优化2+4] 分批生成带数量契约的 LLM Prompt 文件
                    [--feature-name <str>]
                    [--batch-size <int>]       每批最大用例数（默认 20）
                    [-o <output-dir>]

── Legacy pipeline（保留兼容）──────────────────────────────────────────────
    plan            <md>                      分析文档，输出生成策略（SINGLE_PASS / TWO_PASS）
    prompt          [md] [-req]               输出单次全量 Prompt（SINGLE_PASS 路径调试用）
    outline         <md>                      输出 Pass 1 Prompt（TWO_PASS 路径）
    feature-prompt  <md> <feature-id>         输出 Pass 2 Prompt（TWO_PASS 路径，逐 Feature）
                    [--outline-json <file>]   Pass 1 输出 JSON，用于注入导航链
                    [-req <str>]
    assemble        <skeleton.json>           将 Pass 1 骨架 + 多个 Pass 2 cases 合并为 TestModel JSON
                    --cases <F-01=f1.json> …
                    [-o <output.json>]
    render          <test_model.json>         将 TestModel JSON 渲染为 Markdown + RichText
                    [-o <cases.md>] [-r <richtext.md>]
    validate        <cases.json> <spec.md> <feature-id>
                                              Pass 3a：规则检测覆盖缺口，输出 violations JSON
                    [-o <violations.json>]
    repair          <cases.json> <spec.md> <feature-id>
                                              Pass 3b：根据 validate 结果生成 Repair Prompt
                    [--violations <file>]     预计算的 violations JSON（省略则自动运行 validate）
                    [--outline-json <file>]   Pass 1 骨架 JSON，用于注入导航链
                    [-o <repair_prompt.txt>]
"""

import argparse
import json
import os
import re
import sys

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)


def _read_file(path: str) -> str:
    with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
        return f.read()


def _apply_biz_knowledge(biz: str = None, user_name: str = None, spec_text: str = "") -> str:
    """
    Resolve business line and reload accounts / routes from gdpa lark-docs.

    Returns the resolved biz ID. If --biz is not specified, auto-detects
    from spec_text keywords. On remote-fetch failure, silently falls back
    to local files (already loaded at import time).
    """
    from script.knowledge_loader import load_all, resolve_biz
    from script.tool_skills import reload_accounts
    from script.ui_enricher import reload_routes

    resolved = resolve_biz(spec_text=spec_text, user_biz=biz)
    if not resolved:
        return ""

    data = load_all(resolved, user_name)

    cache_dir = os.path.join("/tmp", "knowledge_cache")
    if not data.get("accounts"):
        cache_path = os.path.join(cache_dir, f"{resolved}_accounts.txt")
        if os.path.isfile(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                data["accounts"] = f.read()
    if not data.get("routes"):
        cache_path = os.path.join(cache_dir, f"{resolved}_routes.txt")
        if os.path.isfile(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                data["routes"] = f.read()

    if data["accounts"]:
        reload_accounts(data["accounts"])
    if data["routes"]:
        reload_routes(data["routes"])

    print(f"[knowledge] biz={resolved}, accounts={len(data['accounts'])} chars, "
          f"routes={len(data['routes'])} chars", file=sys.stderr)
    return resolved


def cmd_plan(args):
    """分析文档长度，输出生成策略 JSON。"""
    from script.doc_parser import parse_doc, plan_info

    text = _read_file(args.md_file)
    doc = parse_doc(text)
    info = plan_info(doc)
    print(json.dumps(info, ensure_ascii=False, indent=2))


def cmd_outline(args):
    """输出 Pass 1 Prompt（OUTLINE_PROMPT），供 Agent 调用 LLM 生成导航链骨架。"""
    from script.doc_parser import parse_doc
    from script.prompts import OUTLINE_PROMPT
    from script.ui_enricher import ui_routes_prompt_context

    text = _read_file(args.md_file)
    doc = parse_doc(text)
    if not doc.should_split():
        print(
            f"[outline] 文档长度 {doc.char_count} 字符 < 阈值，"
            "建议使用 `prompt` 命令（单次全量）。继续输出 outline prompt...",
            file=sys.stderr,
        )
    prompt = OUTLINE_PROMPT.format(
        doc_content=text,
        ui_routes_context=ui_routes_prompt_context(),
    )
    print(prompt)


def cmd_feature_prompt(args):
    """
    输出 Pass 2 Prompt（CASES_GEN_PROMPT）for 单个 Feature。

    --outline-json: Pass 1 LLM 输出的 JSON 文件路径，用于注入导航链上下文。
                    若未提供，则跳过导航链（降级输出，约束仍完整）。
    --spec-file:    包含「第 7 章 原始用例分组」的 spec.md 路径（可与 md_file 相同）。
                    若提供，将提取对应 feature_id 的原始用例作为覆盖率锚点注入 Prompt。
    """
    from script.device_role_skills import roles_prompt_context
    from script.doc_parser import (
        build_cross_feature_context,
        build_global_context,
        build_parent_section,
        parse_doc,
    )
    from script.prompts import CASES_GEN_PROMPT
    from script.tool_skills import tools_prompt_context
    from script.ui_enricher import ui_routes_prompt_context

    text = _read_file(args.md_file)

    biz = getattr(args, "biz", None)
    user = getattr(args, "user", None)
    _apply_biz_knowledge(biz=biz, user_name=user, spec_text=text)

    doc = parse_doc(text)
    feature_id = args.feature_id

    if feature_id not in doc.feature_sections:
        print(
            f"[feature-prompt] 未找到 feature_id={feature_id}，"
            f"文档中检测到的 Feature：{doc.feature_ids}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 加载 Pass 1 输出（可选）
    nav_chains = None
    outline_data: dict = {}
    if args.outline_json:
        with open(os.path.expanduser(args.outline_json), "r", encoding="utf-8") as f:
            outline_data = json.load(f)
        nav_chains = outline_data.get("cross_feature", {}).get("navigation_chains")

    feature_sec = doc.feature_sections[feature_id]

    # 确定风险等级
    risk_map = outline_data.get("global_shared", {}).get("risk_map", {})
    risk_level = risk_map.get(feature_id, "medium")

    global_ctx = build_global_context(doc, feature_id)
    cross_ctx = build_cross_feature_context(doc, feature_id, nav_chains)
    parent_block = build_parent_section(doc, feature_id, nav_chains)
    parent_section_block = parent_block if parent_block else "（无直接父功能点依赖）"

    # 构建原始用例锚点块（来自 spec 第 7 章，或外部 --spec-file）
    raw_cases_block = _build_raw_cases_block(args, feature_id, doc)

    prompt = CASES_GEN_PROMPT.format(
        tools_context=tools_prompt_context(),
        roles_context=roles_prompt_context(),
        ui_routes_context=ui_routes_prompt_context(),
        global_context=global_ctx,
        cross_feature_context=cross_ctx,
        parent_section_block=parent_section_block,
        feature_id=feature_id,
        feature_name=feature_sec.feature_name,
        risk_level=risk_level,
        feature_section=feature_sec.raw_text,
        raw_cases_block=raw_cases_block,
        req=args.requirement or "",
    )
    print(prompt)


def _build_raw_cases_block(args, feature_id: str, doc) -> str:
    """
    构建「原始用例锚点」Prompt 块。

    优先级：
    1. 若 --spec-file 指向与 md_file 不同的文件，解析该文件的第 7 章
    2. 否则，使用 doc（md_file 解析结果）中已包含的 raw_case_seeds
    3. 若两者均无对应 feature_id 的 seeds，返回空字符串（不注入）
    """
    from script.doc_parser import parse_doc as _parse_doc

    seeds: list = []

    spec_file = getattr(args, "spec_file", None)
    if spec_file and os.path.abspath(os.path.expanduser(spec_file)) != os.path.abspath(
        os.path.expanduser(args.md_file)
    ):
        spec_text = _read_file(spec_file)
        spec_doc = _parse_doc(spec_text)
        seeds = spec_doc.raw_case_seeds.get(feature_id, [])
    else:
        seeds = doc.raw_case_seeds.get(feature_id, [])

    if not seeds:
        return ""

    lines = [
        f"【原始用例锚点（Coverage Anchors for {feature_id}）】",
        "以下是来自原始测试规格中针对本功能点的原始用例标题/断言。",
        "生成的测试用例**必须覆盖以下每一条**（用例标题可以不完全一致，但不能遗漏对应场景）：",
        "",
    ]
    for seed in seeds:
        lines.append(f"- {seed}")
    lines.append("")
    lines.append(
        "⚠️ 如果上方某条锚点已被「原子可验证断言列表」中的行覆盖，以断言列表为准生成独立用例；两者均须覆盖，不允许只覆盖其中一个。"
    )
    return "\n".join(lines)


def cmd_assemble(args):
    """
    将 Pass 1 骨架 JSON + 多个 Pass 2 cases JSON 合并为完整 TestModel JSON。

    --cases 格式：F-01=path/to/f01_cases.json F-02=path/to/f02_cases.json
    """
    with open(os.path.expanduser(args.skeleton_json), "r", encoding="utf-8") as f:
        skeleton = json.load(f)

    # 解析 --cases 参数
    cases_map: dict = {}
    for item in args.cases or []:
        if "=" not in item:
            print(
                f"[assemble] 格式错误，应为 FEATURE_ID=path，收到：{item}",
                file=sys.stderr,
            )
            sys.exit(1)
        fid, path = item.split("=", 1)
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            raw = f.read().strip()
        from script.llm_utils import extract_json_from_llm_response

        cleaned = extract_json_from_llm_response(raw)
        cases_map[fid.strip()] = json.loads(cleaned)

    # 合并 cases 到 skeleton
    for feat in skeleton.get("features", []):
        fid = feat.get("feature_id", "")
        if fid in cases_map:
            feat["cases"] = cases_map[fid]
        else:
            print(
                f"[assemble] 未找到 {fid} 的 cases，该功能点 cases 置为空",
                file=sys.stderr,
            )
            feat.setdefault("cases", [])

    # 补全 feature_relationships（从 cross_feature 搬运）
    if "feature_relationships" not in skeleton:
        rels = skeleton.get("cross_feature", {}).get("feature_relationships", [])
        skeleton["feature_relationships"] = rels

    # 移除 Pass 1 专属字段，保持 TestModel 干净
    skeleton.pop("global_shared", None)
    skeleton.pop("cross_feature", None)

    result = json.dumps(skeleton, ensure_ascii=False, indent=2)
    if args.output:
        out = os.path.expanduser(args.output)
        with open(out, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"[assemble] TestModel written to: {out}")
    else:
        print(result)


def cmd_check_json_object(args):
    """供 skill / LLM 自检：判断字符串是否为 JSON 对象 string。

    exit 0 → ok=true；exit 1 → ok=false。stdout 始终输出一行 JSON：
      {"ok": true|false, "reason": "...", "param": "ab_settings"}
    """
    from script.tool_skills import parse_json_object_string

    text = args.text
    if getattr(args, "file", None):
        text = _read_file(args.file)
    ok, _obj, reason = parse_json_object_string(text)
    payload = {
        "ok": ok,
        "reason": reason,
        "param": getattr(args, "param", None) or "",
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0 if ok else 1)


def cmd_validate(args):
    """
    Pass 3a — 规则检测覆盖缺口。

    输入：
      cases_json   : Pass 2 LLM 输出的 cases JSON 文件（纯 JSON 数组或含 feature 包装的对象）
      spec_md      : spec.md 文件（含第 7 章 Raw Case Seeds）
      feature_id   : 要检测的 Feature ID，如 F-05
    输出：
      violations.json  打印到 stdout 或通过 --output/-o 写文件
    """
    from script.llm_utils import extract_json_from_llm_response
    from script.validator import validate

    # 读取 cases JSON
    raw = _read_file(args.cases_json)
    try:
        cleaned = extract_json_from_llm_response(raw)
        parsed = json.loads(cleaned)
    except Exception as e:
        print(f"[validate] cases JSON 解析失败：{e}", file=sys.stderr)
        sys.exit(1)

    # 支持两种格式：纯数组 or {"cases": [...]}
    if isinstance(parsed, list):
        cases_list = parsed
    elif isinstance(parsed, dict):
        cases_list = parsed.get("cases", [])
    else:
        print(
            "[validate] cases JSON 格式不支持，应为数组或含 cases 键的对象",
            file=sys.stderr,
        )
        sys.exit(1)

    spec_text = _read_file(args.spec_md)
    result = validate(args.feature_id, cases_list, spec_text)

    output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        out = os.path.expanduser(args.output)
        with open(out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[validate] violations written to: {out}", file=sys.stderr)
    else:
        print(output)


def cmd_repair(args):
    """
    Pass 3b — 生成 Repair Prompt，供 Agent 调用 LLM 修复覆盖缺口。

    输入：
      cases_json   : Pass 2 LLM 输出的 cases JSON 文件
      spec_md      : spec.md 文件（含第 7 章 Raw Case Seeds）
      feature_id   : 要修复的 Feature ID，如 F-05
    可选：
      --violations : 预计算的 violations JSON 文件（省略则自动运行 validate）
      --outline-json: Pass 1 骨架 JSON，用于注入导航链
    输出：
      repair prompt，打印到 stdout 或通过 --output/-o 写文件
    """
    from script.device_role_skills import roles_prompt_context
    from script.doc_parser import (
        build_cross_feature_context,
        parse_doc,
    )
    from script.llm_utils import extract_json_from_llm_response
    from script.prompts import REPAIR_PROMPT
    from script.tool_skills import tools_prompt_context
    from script.ui_enricher import ui_routes_prompt_context
    from script.validator import extract_case_titles, validate

    biz = getattr(args, "biz", None)
    user = getattr(args, "user", None)
    spec_text_for_biz = _read_file(args.spec_md)
    _apply_biz_knowledge(biz=biz, user_name=user, spec_text=spec_text_for_biz)

    # ── 读取 cases JSON ─────────────────────────────────────────────────────
    raw = _read_file(args.cases_json)
    try:
        cleaned = extract_json_from_llm_response(raw)
        parsed = json.loads(cleaned)
    except Exception as e:
        print(f"[repair] cases JSON 解析失败：{e}", file=sys.stderr)
        sys.exit(1)

    if isinstance(parsed, list):
        cases_list = parsed
    elif isinstance(parsed, dict):
        cases_list = parsed.get("cases", [])
    else:
        print(
            "[repair] cases JSON 格式不支持，应为数组或含 cases 键的对象",
            file=sys.stderr,
        )
        sys.exit(1)

    spec_text = _read_file(args.spec_md)
    feature_id = args.feature_id

    # ── 加载或计算 violations ───────────────────────────────────────────────
    if args.violations:
        with open(os.path.expanduser(args.violations), "r", encoding="utf-8") as f:
            vdata = json.load(f)
        violations = vdata.get("violations", [])
    else:
        result = validate(feature_id, cases_list, spec_text)
        violations = [
            v.__dict__ if hasattr(v, "__dict__") else v for v in result.violations
        ]
        # result.violations are Violation dataclasses; convert to dicts
        violations = result.to_dict().get("violations", [])

    if not violations:
        print("[repair] 未检测到覆盖缺口，无需 repair。", file=sys.stderr)
        sys.exit(0)

    # ── 构建 prompt 上下文 ──────────────────────────────────────────────────
    doc = parse_doc(spec_text)

    nav_chains = None
    outline_data: dict = {}
    if args.outline_json:
        with open(os.path.expanduser(args.outline_json), "r", encoding="utf-8") as f:
            outline_data = json.load(f)
        nav_chains = outline_data.get("cross_feature", {}).get("navigation_chains")

    if feature_id not in doc.feature_sections:
        print(
            f"[repair] 未找到 feature_id={feature_id}，"
            f"文档中检测到的 Feature：{doc.feature_ids}",
            file=sys.stderr,
        )
        sys.exit(1)

    feature_sec = doc.feature_sections[feature_id]
    cross_ctx = build_cross_feature_context(doc, feature_id, nav_chains)

    # 已有用例标题
    titles = extract_case_titles(cases_list)
    existing_titles_block = "\n".join(f"  - {t}" for t in titles) or "（无）"

    # violations 格式化
    vlines = []
    for i, v in enumerate(violations, 1):
        vtype = v.get("type", "?")
        seed = v.get("seed", "?")
        reason = v.get("reason", "")
        suggestion = v.get("suggestion", "")
        vlines.append(
            f"{i}. [{vtype}] {seed}\n   原因：{reason}\n   建议：{suggestion}"
        )
    violations_block = "\n\n".join(vlines)

    prompt = REPAIR_PROMPT.format(
        feature_id=feature_id,
        feature_name=feature_sec.feature_name,
        violation_count=len(violations),
        existing_titles_block=existing_titles_block,
        violations_block=violations_block,
        feature_section=feature_sec.raw_text,
        tools_context=tools_prompt_context(),
        roles_context=roles_prompt_context(),
        ui_routes_context=ui_routes_prompt_context(),
        cross_feature_context=cross_ctx,
    )

    if args.output:
        out = os.path.expanduser(args.output)
        with open(out, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"[repair] repair prompt written to: {out}", file=sys.stderr)
    else:
        print(prompt)


def cmd_seed_prompt(args):
    """
    Seed-based pipeline: 解析 spec.md 的第 7 章 seeds，为单个 Feature 生成展开 Prompt。

    新管线核心命令，替代原来的 plan + outline + feature-prompt 三步。
    """
    from script.device_role_skills import roles_prompt_context, set_active_space
    from script.nav_builder import build_nav_chains, build_nav_context_for_feature
    from script.prompts import SEED_EXPAND_PROMPT
    from script.seed_parser import parse_seeds_from_spec
    from script.tool_skills import tools_prompt_context

    space_id = getattr(args, "space_id", None)
    if space_id:
        resolved = set_active_space(space_id)
        print(f"[seed-prompt] 设备空间分区：{resolved}", file=sys.stderr)

    spec_text = _read_file(args.spec_file)

    biz = getattr(args, "biz", None)
    user = getattr(args, "user", None)
    _apply_biz_knowledge(biz=biz, user_name=user, spec_text=spec_text)

    spec = parse_seeds_from_spec(spec_text)
    feature_id = args.feature_id

    if feature_id not in spec.seeds:
        print(
            f"[seed-prompt] 未找到 {feature_id} 的 seeds。"
            f"已检测到的 Feature：{spec.feature_ids}",
            file=sys.stderr,
        )
        sys.exit(1)

    seeds = spec.seeds[feature_id]
    meta = spec.features.get(feature_id)
    feature_name = meta.feature_name if meta else feature_id

    nav_chains = build_nav_chains(spec)
    nav_context = build_nav_context_for_feature(feature_id, spec, nav_chains)

    has_byteio = any(getattr(s, "byteio_cases", None) for s in seeds)
    if has_byteio:
        seeds_lines = [
            "| Seed ID | 入口状态 | 核心操作 | 预期结果 | 埋点需求 |",
            "|---------|---------|---------|---------|---------|",
        ]
        for s in seeds:
            flag = "是（埋点断言由系统自动注入 et_checker_G20，勿自行编写）" if getattr(s, "byteio_cases", None) else "否"
            seeds_lines.append(
                f"| {s.seed_id} | {s.entry_state} | {s.core_action} | {s.expected_result} | {flag} |"
            )
    else:
        seeds_lines = [
            "| Seed ID | 入口状态 | 核心操作 | 预期结果 |",
            "|---------|---------|---------|---------|",
        ]
        for s in seeds:
            seeds_lines.append(
                f"| {s.seed_id} | {s.entry_state} | {s.core_action} | {s.expected_result} |"
            )
    seeds_table = "\n".join(seeds_lines)

    feature_context = spec.feature_sections.get(feature_id, "（无对应的测试场景分析）")

    prompt = SEED_EXPAND_PROMPT.format(
        tools_context=tools_prompt_context(),
        roles_context=roles_prompt_context(),
        nav_context=nav_context,
        feature_id=feature_id,
        feature_name=feature_name,
        feature_context=feature_context,
        seeds_table=seeds_table,
        req=args.requirement or "",
    )

    if args.output:
        out = os.path.expanduser(args.output)
        with open(out, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"[seed-prompt] Prompt written to: {out}", file=sys.stderr)
    else:
        print(prompt)


def _inject_byteio_assertions(spec, cases_map: dict) -> None:
    """确定性注入埋点断言：对带 byteio_cases 的 seed，把
    `et_checker_G20 byteio_case_list=[...]` 追加到该用例**断言步骤的预期结果**上
    （对应原始脑图 nodeType=13 的预期节点带 ByteIO resource——埋点校验属于预期结果，
    不是独立操作步骤）。byteio 参数直接取自 spec 第 7 章，绝不依赖 LLM 复述用例 ID。

    匹配依据：LLM 生成的 case 里的 `seed_id` 与 spec seed 的 seed_id 对应。
    渲染阶段 apply_tool_skills 会把该工具 token 转成预期结果里的 richtext 占位符。
    """
    seed_byteio: dict = {}
    for fid, seeds in (spec.seeds or {}).items():
        for s in seeds:
            if getattr(s, "byteio_cases", None):
                seed_byteio[s.seed_id] = s.byteio_cases

    if not seed_byteio:
        return

    injected = 0
    for fid, cases in cases_map.items():
        if not isinstance(cases, list):
            continue
        for case in cases:
            if not isinstance(case, dict):
                continue
            sid = str(case.get("seed_id") or "").strip()
            byteio = seed_byteio.get(sid)
            if not byteio:
                continue
            pairs = case.get("step_expected_pairs")
            if not isinstance(pairs, list) or not pairs:
                continue
            # 幂等：已注入过则跳过
            already = any(
                "et_checker_G20" in str(e)
                for p in pairs if isinstance(p, dict)
                for e in (p.get("expected") or [])
            )
            if already:
                continue
            # 断言步骤 = 最后一步（其预期结果承载埋点事件）
            target = None
            for p in reversed(pairs):
                if isinstance(p, dict):
                    target = p
                    break
            if target is None:
                continue
            case_list_json = json.dumps(byteio, ensure_ascii=False, separators=(",", ":"))
            tool_inv = f"et_checker_G20 byteio_case_list={case_list_json}"
            exp = target.get("expected")
            if not isinstance(exp, list) or not exp:
                exp = [tool_inv]
            else:
                # 把埋点工具追加到该预期结果节点文本末尾（保留原断言事件文本在前）
                exp = list(exp)
                exp[-1] = f"{str(exp[-1]).rstrip()} {tool_inv}".strip()
            target["expected"] = exp
            injected += 1

    if injected:
        print(f"[seed-assemble] 埋点断言注入：{injected} 条用例的预期结果已挂 et_checker_G20", file=sys.stderr)


def cmd_seed_assemble(args):
    """
    Seed-based pipeline: 从 spec.md 提取元数据，合并各 Feature 的 cases 为 TestModel JSON。

    替代原来的 outline + assemble 两步。
    """
    from script.llm_utils import extract_json_from_llm_response
    from script.seed_parser import parse_seeds_from_spec

    spec_text = _read_file(args.spec_file)
    spec = parse_seeds_from_spec(spec_text)

    cases_map: dict = {}
    for item in args.cases or []:
        if "=" not in item:
            print(
                f"[seed-assemble] 格式错误，应为 FEATURE_ID=path，收到：{item}",
                file=sys.stderr,
            )
            sys.exit(1)
        fid, path = item.split("=", 1)
        raw = _read_file(path)
        cleaned = extract_json_from_llm_response(raw)
        cases_map[fid.strip()] = json.loads(cleaned)

    # 埋点需求：确定性注入 et_checker_G20 埋点断言步骤。
    # byteio 参数取自 spec 第 7 章 seed 的第 5 列（不依赖 LLM 复述 ID）。
    _inject_byteio_assertions(spec, cases_map)

    features = []
    for fid in spec.feature_ids:
        meta = spec.features.get(fid)
        feature_name = meta.feature_name if meta else fid
        primary_roles = meta.primary_roles if meta else ["主播"]

        feature_data = {
            "feature_id": fid,
            "feature_name": feature_name,
            "primary_roles": primary_roles,
            "cases": cases_map.get(fid, []),
        }
        features.append(feature_data)

    relationships = []
    for fid, deps in spec.dependency_graph.items():
        for dep in deps:
            relationships.append(
                {
                    "source_id": dep,
                    "target_id": fid,
                    "relation_type": "depends_on",
                    "description": f"{fid} 依赖 {dep}",
                }
            )

    test_model = {
        "module": _extract_module_name(spec_text),
        "requirement_summary": "",
        "features": features,
        "feature_relationships": relationships,
    }

    result = json.dumps(test_model, ensure_ascii=False, indent=2)
    if args.output:
        out = os.path.expanduser(args.output)
        with open(out, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"[seed-assemble] TestModel written to: {out}")
    else:
        print(result)


def cmd_seed_info(args):
    """显示 spec.md 的 seed 统计信息，帮助 Agent 决定执行计划。"""
    from script.seed_parser import parse_seeds_from_spec

    spec_text = _read_file(args.spec_file)
    spec = parse_seeds_from_spec(spec_text)

    info = {
        "total_seeds": spec.total_seed_count(),
        "features": [],
    }
    for fid in spec.feature_ids:
        meta = spec.features.get(fid)
        seeds = spec.seeds.get(fid, [])
        info["features"].append(
            {
                "feature_id": fid,
                "feature_name": meta.feature_name if meta else fid,
                "seed_count": len(seeds),
                "primary_roles": meta.primary_roles if meta else [],
                "depends_on": meta.depends_on if meta else [],
            }
        )

    print(json.dumps(info, ensure_ascii=False, indent=2))


def cmd_seed_classify(args):
    """
    优化 4：对 valid_cases.json 中的用例做机械型/语义型分类，输出统计报告。

    机械型（mechanical）：断言清晰可观测，可直接转化为 seed 行，无需 LLM 介入。
    语义型（semantic）  ：断言含模糊表达（"正常展示"等）或缺少角色主语，需 LLM 润色。

    用法：
        python3 script.py seed-classify valid_F01.json
        python3 script.py seed-classify valid_F01.json -o classify_report.json
    """
    from script.seed_gen import classify_report, load_raw_cases_from_json

    cases = load_raw_cases_from_json(args.cases_json)
    report = classify_report(cases)

    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        out = os.path.expanduser(args.output)
        with open(out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[seed-classify] Report written to: {out}", file=sys.stderr)
    else:
        print(output)


def cmd_seed_coverage(args):
    """
    优化 3：对比 spec.md 第 7 章 seeds 行数与原始有效用例数，输出 Coverage Bitmap 报告。

    若存在缺口（seeds < cases），报告中列出各 Feature 的缺口大小，
    可用于决定哪些 Feature 需要补充生成 seeds。

    用法：
        python3 script.py seed-coverage spec.md \\
            --cases F-01=/abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-gen/valid_F01.json F-02=/abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-gen/valid_F02.json
        python3 script.py seed-coverage spec.md --cases F-01=valid.json -o coverage.json
    """
    from script.seed_gen import (
        build_coverage_map,
        coverage_report,
        load_raw_cases_from_json,
    )
    from script.seed_parser import parse_seeds_from_spec

    spec_text = _read_file(args.spec_file)
    spec = parse_seeds_from_spec(spec_text)

    # spec 第 7 章中各 Feature 的 seeds 行数
    seeds_count = {fid: len(seeds) for fid, seeds in spec.seeds.items()}

    # 加载各 Feature 的原始有效用例
    valid_cases = {}
    for item in args.cases or []:
        if "=" not in item:
            print(
                f"[seed-coverage] 格式错误，应为 FEATURE_ID=path，收到：{item}",
                file=sys.stderr,
            )
            sys.exit(1)
        fid, path = item.split("=", 1)
        valid_cases[fid.strip()] = load_raw_cases_from_json(path)

    cov_map = build_coverage_map(seeds_count, valid_cases)
    report = coverage_report(cov_map)

    # 输出摘要到 stderr，便于快速查看
    overall = report["overall"]
    print(
        f"[seed-coverage] seeds={overall['total_seeds']}, "
        f"cases={overall['total_cases']}, "
        f"rate={overall['coverage_rate']}, "
        f"status={overall['status']}",
        file=sys.stderr,
    )
    if overall["gap_features"]:
        for gf in overall["gap_features"]:
            print(
                f"  ⚠️  {gf['feature_id']}: gap={gf['gap']} "
                f"（需补充 {gf['gap']} 条 seeds）",
                file=sys.stderr,
            )

    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        out = os.path.expanduser(args.output)
        with open(out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[seed-coverage] Report written to: {out}", file=sys.stderr)
    else:
        print(output)


def cmd_seed_gen_prompts(args):
    """
    优化 2+4：将大型 Feature 的有效用例分批，为每批生成带「数量契约」的 LLM Prompt。

    流程：
      1. 加载 valid_cases.json（已过滤空行的有效用例）
      2. 优化 4：对每条用例分类（mechanical/semantic），标注在 prompt 中
      3. 优化 2：按模块路径第 3 层分组后切分为若干批次（每批 ≤ batch_size 条）
      4. 为每批生成独立 Prompt 文件，内嵌数量契约（seeds ≥ cases）和自检要求

    每个 Prompt 文件可独立调用 LLM，生成的批次表格在 Reduce 阶段合并重编号。

    用法：
        python3 script.py seed-gen-prompts valid_F01.json F-01 \\
            --feature-name "语聊房迁移到triones" --batch-size 20 -o ./prompts/
        # 生成：./prompts/F-01_batch_01_prompt.txt, _batch_02_prompt.txt, ...
    """
    from script.seed_gen import (
        DEFAULT_BATCH_SIZE,
        build_batch_prompt,
        classify_cases,
        load_raw_cases_from_json,
        split_into_batches,
    )

    cases = load_raw_cases_from_json(args.cases_json)

    # 优化 4：分类（修改 case.case_type in-place）
    mechanical, semantic = classify_cases(cases)
    print(
        f"[seed-gen-prompts] {args.feature_id}: {len(cases)} cases "
        f"(mechanical={len(mechanical)}, semantic={len(semantic)}, "
        f"llm_reduction={round(len(mechanical) / max(len(cases), 1) * 100)}%)",
        file=sys.stderr,
    )

    batch_size = args.batch_size or DEFAULT_BATCH_SIZE

    # 优化 2：分批（按模块子树聚合，再切分）
    batches = split_into_batches(cases, batch_size=batch_size, group_by_module=True)
    print(
        f"[seed-gen-prompts] → {len(batches)} batches (batch_size={batch_size})",
        file=sys.stderr,
    )

    feature_name = args.feature_name or args.feature_id
    output_dir = os.path.expanduser(args.output_dir or ".")
    os.makedirs(output_dir, exist_ok=True)

    # 计算各批次的起始 Seed 编号（便于 Reduce 阶段直接拼接）
    start_num = 1
    for i, batch in enumerate(batches):
        m_count = sum(1 for c in batch if c.case_type == "mechanical")
        s_count = len(batch) - m_count
        print(
            f"  Batch {i + 1:02d}/{len(batches)}: {len(batch)} cases "
            f"(M={m_count}, S={s_count}), seed_start={start_num:03d}",
            file=sys.stderr,
        )

        prompt = build_batch_prompt(
            batch=batch,
            feature_id=args.feature_id,
            feature_name=feature_name,
            total_n=len(cases),
            batch_idx=i,
            batch_total=len(batches),
            start_seed_num=start_num,
        )

        out_path = os.path.join(
            output_dir,
            f"{args.feature_id}_batch_{i + 1:02d}_prompt.txt",
        )
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(prompt)

        start_num += len(
            batch
        )  # 保守估算起始编号（实际拆行后可能更多，Reduce 阶段重编号）

    print(
        f"[seed-gen-prompts] Done. {len(batches)} prompt files → {output_dir}",
        file=sys.stderr,
    )


def _extract_module_name(spec_text: str) -> str:
    """从 spec 文本中提取模块名称。"""
    m = re.search(
        r"[*\*]*模块定位[*\*]*[：:]\s*(.+?)(?:[。.，,；;]|\s*$|\s{2})", spec_text, re.MULTILINE
    )
    if m:
        return m.group(1).strip()

    m = re.search(
        r"[*\*]*模块[*\*]*[：:]\s*(.+?)(?:\s*$|\s{2})", spec_text, re.MULTILINE
    )
    if m:
        return m.group(1).strip()

    _SKIP_TITLES = {"Feature 测试规格文档（Spec）", "Feature 测试规格文档", "Spec"}
    for h1 in re.finditer(r"^#\s+(.+)", spec_text, re.MULTILINE):
        title = h1.group(1).strip()
        if title not in _SKIP_TITLES:
            return title

    return "未知模块"


def cmd_render(args):
    from script.device_role_skills import set_active_space
    from script.render import render_from_json_file
    from script.tool_skills import (
        MissingRequiredToolParams,
        AccountPoolTagSuggestionNeeded,
        InvalidJsonObjectParam,
    )

    space_id = getattr(args, "space_id", None)
    if space_id:
        resolved = set_active_space(space_id)
        print(f"[render] 设备空间分区：{resolved}", file=sys.stderr)

    test_model_text = _read_file(args.test_model_json)
    biz = getattr(args, "biz", None)
    user = getattr(args, "user", None)
    _apply_biz_knowledge(biz=biz, user_name=user, spec_text=test_model_text)

    try:
        markdown, richtext_list = render_from_json_file(args.test_model_json)
    except MissingRequiredToolParams as exc:
        # 输出结构化错误信息，供 skill 层解析
        missing = ",".join(exc.missing_params)
        print(f"[MISSING_PARAMS] tool={exc.tool_name} missing={missing} hint={exc.params_hint}", file=sys.stderr)
        sys.exit(2)
    except InvalidJsonObjectParam as exc:
        print(
            f"[INVALID_JSON_OBJECT] tool={exc.tool_name} param={exc.param_name} "
            f"reason={exc.reason} hint={exc.params_hint} raw={exc.raw[:200]}",
            file=sys.stderr,
        )
        sys.exit(2)
    except AccountPoolTagSuggestionNeeded as exc:
        print(
            f"[SUGGEST_TAG] tool={exc.tool_name} pool_name={exc.pool_name} "
            f"suggested_tag={exc.suggested_tag} hint={exc.params_hint}",
            file=sys.stderr,
        )
        sys.exit(2)
    except ValueError as exc:
        print(f"[render] {exc}", file=sys.stderr)
        sys.exit(1)

    if args.cases_output:
        out = os.path.expanduser(args.cases_output)
        with open(out, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"[render] Cases written to: {out}")
    else:
        print(markdown)

    if args.richtext_output:
        out = os.path.expanduser(args.richtext_output)
        content = json.dumps(richtext_list, ensure_ascii=False, indent=2)
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"# RichText List\n\n```json\n{content}\n```\n")
        print(f"[render] RichText written to: {out}")


def cmd_prompt(args):
    """输出单次全量 Prompt（SINGLE_PASS），供调试查看。"""
    from script.device_role_skills import roles_prompt_context
    from script.doc_parser import parse_doc
    from script.prompts import FULL_DOC_GEN_PROMPT
    from script.tool_skills import tools_prompt_context
    from script.device_role_skills import roles_prompt_context
    from script.ui_enricher import ui_routes_prompt_context
    from script.doc_parser import parse_doc

    doc_content = ""
    if args.md_file:
        doc_content = _read_file(args.md_file)
        doc = parse_doc(doc_content)
        if doc.should_split():
            print(
                f"[prompt] 文档长度 {doc.char_count} 字符 ≥ 阈值，"
                "建议使用 TWO_PASS（outline + feature-prompt）。继续输出全量 prompt...",
                file=sys.stderr,
            )

    prompt = FULL_DOC_GEN_PROMPT.format(
        req=args.requirement or "",
        doc_content=doc_content,
        tools_context=tools_prompt_context(),
        roles_context=roles_prompt_context(),
        ui_routes_context=ui_routes_prompt_context(),
    )
    print(prompt)


def main():
    parser = argparse.ArgumentParser(
        prog="ui-xmind-case-gen",
        description="UI 自动化测试用例生成 Skill CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ── Seed-based pipeline（推荐） ──────────────────────────────

    p_si = subparsers.add_parser(
        "seed-info",
        help="显示 spec 的 seed 统计信息（Feature 列表、seed 数、依赖关系）",
    )
    p_si.add_argument("spec_file", help="spec.md 文件路径")
    p_si.set_defaults(func=cmd_seed_info)

    p_sp = subparsers.add_parser(
        "seed-prompt", help="为单个 Feature 生成 Seed → Case 展开 Prompt"
    )
    p_sp.add_argument("spec_file", help="spec.md 文件路径")
    p_sp.add_argument("feature_id", help="Feature ID，如 F-01")
    p_sp.add_argument("--requirement", "-req", default="", help="用户补充需求")
    p_sp.add_argument("--biz", default=None, help="业务线 ID（如 revenue / game），不指定则自动推断")
    p_sp.add_argument("--user", default=None, help="飞书用户名（如 huangyiran.dd），用于拉取远程文档权限")
    p_sp.add_argument("--space-id", default=None, help="设备角色映射空间分区（bits space_id 或其 project/dir id）；涉及设备时必须指定")
    p_sp.add_argument("--output", "-o", help="Prompt 输出路径（不指定则打印到 stdout）")
    p_sp.set_defaults(func=cmd_seed_prompt)

    p_sa = subparsers.add_parser(
        "seed-assemble", help="合并各 Feature 的 cases → TestModel JSON（无需 outline）"
    )
    p_sa.add_argument("spec_file", help="spec.md 文件路径（用于提取元数据）")
    p_sa.add_argument(
        "--cases",
        nargs="+",
        metavar="F-XX=path.json",
        help="各 Feature 的 cases JSON，格式：F-01=f01.json",
    )
    p_sa.add_argument("--output", "-o", help="输出 TestModel JSON 路径")
    p_sa.set_defaults(func=cmd_seed_assemble)

    # ── 优化算法命令（Opt 2/3/4） ────────────────────────────────

    p_sc = subparsers.add_parser(
        "seed-classify",
        help="[优化4] 将 valid_cases.json 中的用例分类为机械型/语义型，输出统计报告",
    )
    p_sc.add_argument("cases_json", help="有效用例 JSON 文件路径（已过滤空行）")
    p_sc.add_argument("--output", "-o", help="报告输出路径（不指定则打印到 stdout）")
    p_sc.set_defaults(func=cmd_seed_classify)

    p_scov = subparsers.add_parser(
        "seed-coverage",
        help="[优化3] 对比 spec.md seeds 行数与原始有效用例数，输出 Coverage Bitmap 报告",
    )
    p_scov.add_argument("spec_file", help="spec.md 文件路径（含第 7 章 Raw Case Seeds）")
    p_scov.add_argument(
        "--cases", nargs="+", metavar="F-XX=path.json",
        help="各 Feature 的有效用例 JSON，格式：F-01=/abs/path/to/repo/tt-nova/ui/tmp/{vc}/{module}/ui-xmind-case-gen/valid_f01.json",
    )
    p_scov.add_argument("--output", "-o", help="报告输出路径（不指定则打印到 stdout）")
    p_scov.set_defaults(func=cmd_seed_coverage)

    p_sgp = subparsers.add_parser(
        "seed-gen-prompts",
        help="[优化2+4] 将大型 Feature 用例分批，为每批生成带数量契约的 LLM Prompt 文件",
    )
    p_sgp.add_argument("cases_json", help="有效用例 JSON 文件路径（已过滤空行）")
    p_sgp.add_argument("feature_id", help="Feature ID，如 F-01")
    p_sgp.add_argument("--feature-name", help="Feature 名称（用于 Prompt 标题）")
    p_sgp.add_argument(
        "--batch-size", type=int, default=20,
        help="每批最大用例数（默认 20）",
    )
    p_sgp.add_argument(
        "--output-dir", "-o",
        help="Prompt 文件输出目录（默认为当前目录）",
    )
    p_sgp.set_defaults(func=cmd_seed_gen_prompts)

    # ── Legacy pipeline（保留兼容） ──────────────────────────────

    # plan
    p_plan = subparsers.add_parser("plan", help="[legacy] 分析文档，输出生成策略（SINGLE_PASS / TWO_PASS）")
    p_plan.add_argument("md_file", help=".md 需求文档路径")
    p_plan.set_defaults(func=cmd_plan)

    # outline（TWO_PASS Pass 1）
    p_outline = subparsers.add_parser("outline", help="输出 Pass 1 Prompt（TWO_PASS 路径，生成导航链骨架）")
    p_outline.add_argument("md_file", help=".md 需求文档路径")
    p_outline.set_defaults(func=cmd_outline)

    # feature-prompt（TWO_PASS Pass 2）
    p_fp = subparsers.add_parser("feature-prompt", help="输出 Pass 2 Prompt（TWO_PASS 路径，逐 Feature 生成用例）")
    p_fp.add_argument("md_file", help=".md 需求文档路径")
    p_fp.add_argument("feature_id", help="Feature ID，如 F-01")
    p_fp.add_argument("--outline-json", help="Pass 1 LLM 输出的 JSON 文件（含导航链），可选")
    p_fp.add_argument("--spec-file", help="含第 7 章「原始用例分组」的 spec.md 路径，用于注入覆盖率锚点（可与 md_file 相同）")
    p_fp.add_argument("--requirement", "-req", default="", help="用户补充需求")
    p_fp.add_argument("--biz", default=None, help="业务线 ID（如 revenue / game），不指定则自动推断")
    p_fp.add_argument("--user", default=None, help="飞书用户名，用于拉取远程文档权限")
    p_fp.set_defaults(func=cmd_feature_prompt)

    # assemble（TWO_PASS 最终合并）
    p_asm = subparsers.add_parser("assemble", help="合并 Pass 1 骨架 + Pass 2 cases → TestModel JSON")
    p_asm.add_argument("skeleton_json", help="Pass 1 LLM 输出的骨架 JSON 文件")
    p_asm.add_argument("--cases", nargs="+", metavar="F-XX=path.json", help="各 Feature 的 cases JSON，格式：F-01=f01.json")
    p_asm.add_argument("--output", "-o", help="输出 TestModel JSON 路径（不指定则打印到 stdout）")
    p_asm.set_defaults(func=cmd_assemble)

    # render
    p_render = subparsers.add_parser("render", help="将 TestModel JSON 渲染为 Markdown + RichText")
    p_render.add_argument("test_model_json", help="TestModel JSON 文件路径")
    p_render.add_argument("--cases-output", "-o", help="测试用例 Markdown 输出路径")
    p_render.add_argument("--richtext-output", "-r", help="RichText 列表输出路径 (.md)")
    p_render.add_argument("--biz", default=None, help="业务线 ID（如 revenue / game），不指定则自动推断")
    p_render.add_argument("--user", default=None, help="飞书用户名，用于拉取远程文档权限")
    p_render.add_argument("--space-id", default=None, help="设备角色映射空间分区（bits space_id 或其 project/dir id）；涉及设备时必须指定，决定 richtext 的 pluginData.id")
    p_render.set_defaults(func=cmd_render)

    # prompt（SINGLE_PASS 调试）
    p_prompt = subparsers.add_parser("prompt", help="输出单次全量 Prompt（SINGLE_PASS 路径调试用）")
    p_prompt.add_argument("md_file", nargs="?", help=".md 需求文档路径")
    p_prompt.add_argument("--requirement", "-req", default="", help="用户需求")
    p_prompt.set_defaults(func=cmd_prompt)

    # check-json-object（LLM 自检 ab_settings 等 JSON 对象参数）
    p_cjo = subparsers.add_parser(
        "check-json-object",
        help="判断字符串是否为 JSON 对象 string（供 LLM 自检 ab_settings / ab_settings_live）",
    )
    p_cjo.add_argument(
        "text",
        nargs="?",
        default="",
        help="待检测字符串；也可用 --file 从文件读取",
    )
    p_cjo.add_argument("--file", "-f", help="从文件读取待检测字符串")
    p_cjo.add_argument(
        "--param",
        default="ab_settings",
        help="参数名（写入输出 JSON，默认 ab_settings）",
    )
    p_cjo.set_defaults(func=cmd_check_json_object)

    # validate（Pass 3a）
    p_val = subparsers.add_parser("validate", help="Pass 3a：规则检测 cases 覆盖缺口，输出 violations JSON")
    p_val.add_argument("cases_json", help="Pass 2 LLM 输出的 cases JSON 文件路径")
    p_val.add_argument("spec_md", help="spec.md 文件路径（含第 7 章 Raw Case Seeds）")
    p_val.add_argument("feature_id", help="要检测的 Feature ID，如 F-05")
    p_val.add_argument("--output", "-o", help="violations JSON 输出路径（不指定则打印到 stdout）")
    p_val.set_defaults(func=cmd_validate)

    # repair（Pass 3b）
    p_rep = subparsers.add_parser("repair", help="Pass 3b：生成 Repair Prompt，供 LLM 修复覆盖缺口")
    p_rep.add_argument("cases_json", help="Pass 2 LLM 输出的 cases JSON 文件路径")
    p_rep.add_argument("spec_md", help="spec.md 文件路径（含第 7 章 Raw Case Seeds）")
    p_rep.add_argument("feature_id", help="要修复的 Feature ID，如 F-05")
    p_rep.add_argument("--violations", help="预计算的 violations JSON 文件（省略则自动运行 validate）")
    p_rep.add_argument("--outline-json", help="Pass 1 骨架 JSON，用于注入导航链（可选）")
    p_rep.add_argument("--biz", default=None, help="业务线 ID（如 revenue / game），不指定则自动推断")
    p_rep.add_argument("--user", default=None, help="飞书用户名，用于拉取远程文档权限")
    p_rep.add_argument("--output", "-o", help="repair prompt 输出路径（不指定则打印到 stdout）")
    p_rep.set_defaults(func=cmd_repair)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
