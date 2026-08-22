#!/usr/bin/env python3
"""
generate_report.py — 读取 final_comments.json，填充 report-template.html 占位符，输出完整 HTML 报告。

用法:
    python generate_report.py <final_comments.json> [--output report.html] [--repo <name>] [--mode <mode>] [--range <range>]

示例:
    python generate_report.py /tmp/myrepo_1234/final_comments.json --repo myrepo --range "HEAD~1..HEAD"
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

CATEGORY_ZH = {
    "LOGIC": "逻辑错误",
    "BUSINESS_SEMANTICS": "业务语义问题",
    "SECURITY": "安全漏洞",
    "CONCURRENCY": "并发问题",
    "ROBUSTNESS": "健壮性问题",
    "PERFORMANCE": "性能问题",
    "QUALITY": "代码质量问题",
}

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SCRIPT_DIR.parent / "assets" / "report-template.html"


def load_template() -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def required_title(defect: dict, index: int) -> str:
    title = defect.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"defect #{index} missing required non-empty field: title")
    return title.strip()


def normalize_defects(defects: list) -> list:
    if not isinstance(defects, list):
        raise ValueError("final_comments.json must be a JSON array")

    normalized = []
    for index, defect in enumerate(defects, start=1):
        if not isinstance(defect, dict):
            raise ValueError(f"defect #{index} must be a JSON object")
        current = dict(defect)
        current["title"] = required_title(current, index)
        normalized.append(current)
    return normalized


def build_defect_card(defect: dict, index: int) -> str:
    severity = defect.get("severity", "P2")
    category = defect.get("category", "")
    category_zh = CATEGORY_ZH.get(category, category)
    confidence = defect.get("confidence", 0)
    file_path = defect.get("file", "")
    start_line = defect.get("start_line", 0)
    end_line = defect.get("end_line", 0)
    rationale = defect.get("rationale", "")
    suggestion = defect.get("suggestion", "")
    title = required_title(defect, index + 1)

    suggestion_section = ""
    if suggestion:
        suggestion_section = f"""
        <div class="defect-section">
          <div class="defect-section-title">修复建议</div>
          <p>{_escape(suggestion)}</p>
        </div>"""

    return f"""
    <div class="defect-card severity-{severity}">
      <div class="defect-header">
        <span class="severity-badge {severity}">{severity}</span>
        <span class="category-badge">{category_zh}</span>
        <span class="defect-title">{_escape(title)}</span>
        <span class="confidence-tag">置信度 {confidence}/10</span>
      </div>
      <div class="defect-body">
        <div class="defect-location">{_escape(file_path)}:{start_line}-{end_line}</div>
        <div class="defect-section">
          <div class="defect-section-title">问题描述</div>
          <p>{_escape(rationale)}</p>
        </div>{suggestion_section}
      </div>
    </div>"""


def build_p0_alert_items(defects: list) -> str:
    items = []
    for index, d in enumerate(defects, start=1):
        if d.get("severity") == "P0":
            cat_zh = CATEGORY_ZH.get(d.get("category", ""), d.get("category", ""))
            file_path = d.get("file", "")
            start_line = d.get("start_line", 0)
            title = required_title(d, index)
            items.append(
                f'        <li>[P0][{cat_zh}] {_escape(file_path)}:{start_line} | {_escape(title)}</li>'
            )
    return "\n".join(items)


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _count_severities(defects: list) -> tuple:
    count_p0 = sum(1 for d in defects if d.get("severity") == "P0")
    count_p1 = sum(1 for d in defects if d.get("severity") == "P1")
    count_p2 = sum(1 for d in defects if d.get("severity") == "P2")
    return count_p0, count_p1, count_p2, len(defects)


def generate_markdown(
    defects: list,
    repo_name: str,
    review_mode: str,
    diff_range: str,
    file_count: int,
    line_count: int,
    generated_at: str,
) -> str:
    count_p0, count_p1, count_p2, count_total = _count_severities(defects)

    lines = [
        "# 代码评审报告",
        "",
        f"- 仓库：{repo_name or '-'}",
        f"- 检测模式：{review_mode or '-'}",
        f"- 检测范围：{diff_range or '-'}",
        f"- 生成时间：{generated_at}",
        f"- 检查文件：{file_count}",
        f"- 变更行数：{line_count}",
        "",
    ]

    if count_total == 0:
        lines += [
            "## 评审结论",
            "",
            "本次评审未发现 P0-P2 级别的缺陷。",
            "",
            f"评审覆盖：共检查 {file_count} 个文件，约 {line_count} 行变更。",
            "",
        ]
        return "\n".join(lines)

    lines += [
        "## 缺陷统计",
        "",
        f"- P0：{count_p0}",
        f"- P1：{count_p1}",
        f"- P2：{count_p2}",
        f"- 合计：{count_total}",
        "",
    ]

    if count_p0 > 0:
        lines += ["## P0 告警", ""]
        for index, d in enumerate(defects, start=1):
            if d.get("severity") != "P0":
                continue
            cat_zh = CATEGORY_ZH.get(d.get("category", ""), d.get("category", ""))
            file_path = d.get("file", "")
            start_line = d.get("start_line", 0)
            title = required_title(d, index)
            lines.append(f"- [P0][{cat_zh}] {file_path}:{start_line} | {title}")
        lines.append("")

    lines += ["## 缺陷详情", ""]
    for index, defect in enumerate(defects, start=1):
        severity = defect.get("severity", "P2")
        category = defect.get("category", "")
        cat_zh = CATEGORY_ZH.get(category, category)
        confidence = defect.get("confidence", 0)
        file_path = defect.get("file", "")
        start_line = defect.get("start_line", 0)
        end_line = defect.get("end_line", 0)
        title = required_title(defect, index)
        rationale = defect.get("rationale", "")
        suggestion = defect.get("suggestion", "")

        lines += [
            f"### {index}. [{severity}][{cat_zh}] {title}",
            "",
            f"- 位置：`{file_path}:{start_line}-{end_line}`",
            f"- 置信度：{confidence}/10",
            "",
            "**问题描述**",
            "",
            rationale or "-",
            "",
        ]
        if suggestion:
            lines += ["**修复建议**", "", suggestion, ""]
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def generate(
    defects: list,
    repo_name: str = "",
    review_mode: str = "通用检测",
    diff_range: str = "",
    file_count: int = 0,
    line_count: int = 0,
    generated_at: str = "",
) -> str:
    defects = normalize_defects(defects)
    html = load_template()
    now = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")

    count_p0, count_p1, count_p2, count_total = _count_severities(defects)

    # Build defect cards
    cards = "\n".join(build_defect_card(d, i) for i, d in enumerate(defects))

    # P0 alert
    p0_display = "block" if count_p0 > 0 else "none"
    p0_items = build_p0_alert_items(defects)

    # Replace placeholders
    replacements = {
        "__REPO_NAME__": _escape(repo_name),
        "__REVIEW_MODE__": _escape(review_mode),
        "__DIFF_RANGE__": _escape(diff_range),
        "__GENERATED_AT__": now,
        "__COUNT_P0__": str(count_p0),
        "__COUNT_P1__": str(count_p1),
        "__COUNT_P2__": str(count_p2),
        "__COUNT_TOTAL__": str(count_total),
        "__P0_ALERT_DISPLAY__": p0_display,
        "__P0_ALERT_ITEMS__": p0_items,
        "__DEFECT_CARDS__": cards,
        "__FILE_COUNT__": str(file_count),
        "__LINE_COUNT__": str(line_count),
    }

    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)

    # Handle empty state: uncomment if no defects, remove defect-list
    if count_total == 0:
        html = html.replace("<!-- __EMPTY_STATE_START__", "")
        html = html.replace("__EMPTY_STATE_END__ -->", "")

    return html


def main() -> int:
    parser = argparse.ArgumentParser(description="生成代码评审 HTML 报告")
    parser.add_argument("input", help="final_comments.json 路径")
    parser.add_argument("--output", "-o", default="report.html", help="输出文件路径")
    parser.add_argument("--repo", default="", help="仓库名称")
    parser.add_argument("--mode", default="通用检测", help="检测模式")
    parser.add_argument("--range", default="", help="检测范围描述")
    parser.add_argument("--files", type=int, default=0, help="检查的文件数")
    parser.add_argument("--lines", type=int, default=0, help="变更行数")
    args = parser.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            defects = json.load(f)

        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        html = generate(
            defects=defects,
            repo_name=args.repo,
            review_mode=args.mode,
            diff_range=args.range,
            file_count=args.files,
            line_count=args.lines,
            generated_at=generated_at,
        )

        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"生成报告失败: {exc}", file=sys.stderr)
        return 1

    print(f"HTML 报告已生成: {os.path.abspath(args.output)}")

    md_path = _derive_markdown_path(args.output)
    try:
        normalized = normalize_defects(defects)
        markdown = generate_markdown(
            defects=normalized,
            repo_name=args.repo,
            review_mode=args.mode,
            diff_range=args.range,
            file_count=args.files,
            line_count=args.lines,
            generated_at=generated_at,
        )
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Markdown 报告已生成: {os.path.abspath(md_path)}")
    except Exception as exc:
        print(f"Markdown 报告生成失败（不影响 HTML）: {exc}", file=sys.stderr)

    return 0


def _derive_markdown_path(html_output: str) -> str:
    p = Path(html_output)
    if p.suffix.lower() == ".html":
        return str(p.with_suffix(".md"))
    return str(p) + ".md"


if __name__ == "__main__":
    sys.exit(main())
