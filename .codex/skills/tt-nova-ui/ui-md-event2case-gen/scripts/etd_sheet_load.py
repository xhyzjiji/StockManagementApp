#!/usr/bin/env python3
"""Load Lark ETD sheets with cell styles; strip strikethrough (作废) text.

ETD authors often mark obsolete enum values with font_line=line-through.
Plain `sheets +csv-get` drops styles, so struck text looks live. This loader
uses `sheets +cells-get --include value,style` and removes struck segments
before agents lock events / enums.

Usage:
  python etd_sheet_load.py --url 'https://.../wiki/TOKEN?sheet=SHEET_ID' [--range A1:Z200]
  python etd_sheet_load.py --spreadsheet-token TOKEN --sheet-id SHEET [--range A1:Z200]
  python etd_sheet_load.py --self-check

Output (stdout): JSON
  {
    "spreadsheet_token": "...",
    "sheet_id": "...",
    "range": "...",
    "cells": [{"addr":"A1","raw":"...","text":"...","struck":true|false,"struck_segments":[...]}],
    "tsv": "cleaned TSV for human skim",
    "struck_summary": [{"addr":"B12","removed":"..."}]
  }
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse


STRIKE = "line-through"


def _is_struck_style(style: Any) -> bool:
    if not isinstance(style, dict):
        return False

    def _hit(val: Any) -> bool:
        if isinstance(val, str):
            norm = re.sub(r"[^a-z]", "", val.lower())
            return "linethrough" in norm or norm == "strike" or "strikethrough" in norm
        if isinstance(val, list):
            return any(_hit(x) for x in val)
        return False

    for key in ("font_line", "fontLine", "textDecoration", "text_decoration"):
        if _hit(style.get(key)):
            return True
    font = style.get("font")
    if isinstance(font, dict):
        return _is_struck_style(font)
    return False


def clean_cell_payload(cell: Any) -> dict[str, Any]:
    """Return cleaned text + strike metadata from a cells-get cell object / scalar."""
    if cell is None:
        return {"raw": "", "text": "", "struck": False, "struck_segments": []}
    if isinstance(cell, (str, int, float, bool)):
        return {"raw": str(cell), "text": str(cell), "struck": False, "struck_segments": []}
    if not isinstance(cell, dict):
        raw = str(cell)
        return {"raw": raw, "text": raw, "struck": False, "struck_segments": []}

    raw_value = cell.get("value")
    if raw_value is None:
        raw_value = cell.get("formatted_value") or cell.get("text") or ""
    if isinstance(raw_value, list):
        raw = "\n".join(str(x) for x in raw_value)
    else:
        raw = "" if raw_value is None else str(raw_value)

    struck_segments: list[str] = []
    rich = cell.get("rich_text") or cell.get("richText") or cell.get("segments")
    if isinstance(rich, list) and rich:
        kept: list[str] = []
        for seg in rich:
            if not isinstance(seg, dict):
                kept.append(str(seg))
                continue
            text = seg.get("text") or seg.get("content") or ""
            style = seg.get("style") or seg.get("segment_style") or {}
            if _is_struck_style(style):
                if text:
                    struck_segments.append(str(text))
                continue
            kept.append(str(text))
        text = "".join(kept)
        # rich_text may omit newlines between enum lines; fall back to raw line filter
        if not text.strip() and raw.strip() and struck_segments:
            text = ""
        return {
            "raw": raw,
            "text": text,
            "struck": bool(struck_segments) and not text.strip(),
            "struck_segments": struck_segments,
        }

    styles = (
        cell.get("cell_styles")
        or cell.get("cellStyles")
        or cell.get("style")
        or cell.get("styles")
        or {}
    )
    if isinstance(styles, list):
        struck = any(_is_struck_style(s) for s in styles if isinstance(s, dict))
    else:
        struck = _is_struck_style(styles)
    if struck:
        return {
            "raw": raw,
            "text": "",
            "struck": True,
            "struck_segments": [raw] if raw else [],
        }
    return {"raw": raw, "text": raw, "struck": False, "struck_segments": []}


def _run_lark(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        ["lark-cli", *args],
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if not out and err:
        raise RuntimeError(f"lark-cli failed: {' '.join(args)}\n{err}")
    try:
        payload = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"lark-cli non-JSON output: {' '.join(args)}\n{out[:500]}\n{err[:500]}"
        ) from exc
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(json.dumps(payload, ensure_ascii=False)[:2000])
    return payload if isinstance(payload, dict) else {"data": payload}


def _walk_find(obj: Any, keys: set[str]) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and v:
                return v
        for v in obj.values():
            found = _walk_find(v, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _walk_find(item, keys)
            if found:
                return found
    return None


def resolve_sheet_locator(
    url: str | None,
    spreadsheet_token: str | None,
    sheet_id: str | None,
    as_identity: str | None,
) -> tuple[str, str | None]:
    """Return (spreadsheet_token, sheet_id). sheet_id may come from ?sheet=."""
    sid = sheet_id
    if url:
        qs = parse_qs(urlparse(url).query)
        if not sid and "sheet" in qs and qs["sheet"]:
            sid = qs["sheet"][0]
        inspect_args = ["drive", "+inspect", "--url", url, "--format", "json"]
        if as_identity:
            inspect_args.extend(["--as", as_identity])
        try:
            info = _run_lark(inspect_args)
        except RuntimeError:
            if as_identity != "user":
                inspect_args = [
                    "drive",
                    "+inspect",
                    "--url",
                    url,
                    "--format",
                    "json",
                    "--as",
                    "user",
                ]
                info = _run_lark(inspect_args)
            else:
                raise
        token = _walk_find(
            info,
            {"spreadsheet_token", "spreadsheetToken", "obj_token", "objToken", "token"},
        )
        if not token or not isinstance(token, str):
            raise RuntimeError(
                f"drive +inspect 未解析到 spreadsheet token: {json.dumps(info, ensure_ascii=False)[:800]}"
            )
        obj_type = _walk_find(info, {"obj_type", "objType", "type", "doc_type"})
        if obj_type and str(obj_type).lower() not in {"sheet", "sheets", "spreadsheet", "wiki"}:
            # wiki unwrap often still yields sheet obj_token
            pass
        return token, sid

    if not spreadsheet_token:
        raise ValueError("need --url or --spreadsheet-token")
    return spreadsheet_token, sid


def _col_letters(n: int) -> str:
    """1-based column index → A, B, ..., Z, AA, ..."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _iter_cells_from_payload(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    """Normalize cells-get payloads into (A1, cell) pairs."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    cells_out: list[tuple[str, Any]] = []

    # Current lark-cli +cells-get shape:
    # {
    #   "data": {
    #     "ranges": [{
    #       "actual_range": "A1:V11",
    #       "row_indices": [1, 2, ...],
    #       "col_indices": ["A", "B", ...],
    #       "cells": [[{"value": "...", "cell_styles": {...}}, ...]]
    #     }]
    #   }
    # }
    ranges = data.get("ranges") if isinstance(data, dict) else None
    if isinstance(ranges, list):
        for rg in ranges:
            if not isinstance(rg, dict):
                continue
            grid = rg.get("cells")
            if not isinstance(grid, list):
                continue
            actual_range = (
                rg.get("actual_range")
                or rg.get("range")
                or rg.get("requested_range")
                or "A1"
            )
            start_row, start_col = 1, 1
            if isinstance(actual_range, str):
                m = re.search(r"([A-Z]+)(\d+)", actual_range.split("!")[-1])
                if m:
                    start_col = sum(
                        (ord(c) - 64) * (26**i)
                        for i, c in enumerate(reversed(m.group(1)))
                    )
                    start_row = int(m.group(2))
            row_indices = rg.get("row_indices") or rg.get("rowIndices") or []
            col_indices = rg.get("col_indices") or rg.get("colIndices") or []
            for ri, row in enumerate(grid):
                if not isinstance(row, list):
                    continue
                raw_row = row_indices[ri] if ri < len(row_indices) else start_row + ri
                try:
                    row_num = int(raw_row)
                except (TypeError, ValueError):
                    row_num = start_row + ri
                for ci, cell in enumerate(row):
                    raw_col = col_indices[ci] if ci < len(col_indices) else _col_letters(start_col + ci)
                    if isinstance(raw_col, int):
                        col_letters = _col_letters(raw_col)
                    else:
                        col_text = str(raw_col)
                        if col_text.isdigit():
                            col_letters = _col_letters(int(col_text))
                        else:
                            col_letters = col_text.upper()
                    if not re.fullmatch(r"[A-Z]+", col_letters):
                        col_letters = _col_letters(start_col + ci)
                    cells_out.append((f"{col_letters}{row_num}", cell))
        if cells_out:
            return cells_out

    # Shape A: flat list of {range/address, value, ...}
    for key in ("cells", "cell_list", "items"):
        items = data.get(key) if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                addr = (
                    item.get("address")
                    or item.get("addr")
                    or item.get("range")
                    or item.get("cell")
                    or ""
                )
                # strip sheet prefix SheetId!A1
                if "!" in str(addr):
                    addr = str(addr).split("!", 1)[1]
                cells_out.append((str(addr), item))
            if cells_out:
                return cells_out

    # Shape B: values 2D grid (+ optional styles / rich_text grids)
    values = None
    for key in ("values", "value_range", "valueRange"):
        cand = data.get(key) if isinstance(data, dict) else None
        if isinstance(cand, dict):
            values = cand.get("values")
            break
        if isinstance(cand, list):
            values = cand
            break
    if not isinstance(values, list):
        # nested valueRanges
        vrs = data.get("valueRanges") or data.get("value_ranges") if isinstance(data, dict) else None
        if isinstance(vrs, list) and vrs and isinstance(vrs[0], dict):
            values = vrs[0].get("values")

    if not isinstance(values, list):
        return cells_out

    styles = data.get("cell_styles") or data.get("styles") if isinstance(data, dict) else None
    rich = data.get("rich_texts") or data.get("rich_text") if isinstance(data, dict) else None
    start_row, start_col = 1, 1
    rng = data.get("range") if isinstance(data, dict) else None
    if isinstance(rng, str):
        m = re.search(r"([A-Z]+)(\d+)", rng.split("!")[-1])
        if m:
            start_col = sum(
                (ord(c) - 64) * (26**i) for i, c in enumerate(reversed(m.group(1)))
            )
            start_row = int(m.group(2))

    for ri, row in enumerate(values):
        if not isinstance(row, list):
            continue
        for ci, val in enumerate(row):
            addr = f"{_col_letters(start_col + ci)}{start_row + ri}"
            cell: dict[str, Any] = {"value": val}
            if isinstance(styles, list) and ri < len(styles) and isinstance(styles[ri], list):
                if ci < len(styles[ri]):
                    cell["cell_styles"] = styles[ri][ci]
            if isinstance(rich, list) and ri < len(rich) and isinstance(rich[ri], list):
                if ci < len(rich[ri]):
                    cell["rich_text"] = rich[ri][ci]
            # Sometimes each value is already a rich object
            if isinstance(val, dict):
                cell = val
            cells_out.append((addr, cell))
    return cells_out


def load_etd_sheet(
    *,
    url: str | None = None,
    spreadsheet_token: str | None = None,
    sheet_id: str | None = None,
    range_a1: str = "A1:Z200",
    as_identity: str | None = None,
) -> dict[str, Any]:
    token, sid = resolve_sheet_locator(url, spreadsheet_token, sheet_id, as_identity)
    args = [
        "sheets",
        "+cells-get",
        "--spreadsheet-token",
        token,
        "--range",
        range_a1,
        "--include",
        "value,style",
        "--format",
        "json",
    ]
    if sid:
        args.extend(["--sheet-id", sid])
    if as_identity:
        args.extend(["--as", as_identity])
    try:
        payload = _run_lark(args)
    except RuntimeError:
        if as_identity != "user":
            # drop previous --as pair if any
            cleaned: list[str] = []
            skip = False
            for a in args:
                if skip:
                    skip = False
                    continue
                if a == "--as":
                    skip = True
                    continue
                cleaned.append(a)
            cleaned.extend(["--as", "user"])
            payload = _run_lark(cleaned)
        else:
            raise

    pairs = _iter_cells_from_payload(payload)
    cells: list[dict[str, Any]] = []
    struck_summary: list[dict[str, str]] = []
    # build sparse map for TSV
    grid: dict[tuple[int, int], str] = {}
    max_r = max_c = 0
    for addr, cell in pairs:
        cleaned = clean_cell_payload(cell)
        entry = {"addr": addr, **cleaned}
        cells.append(entry)
        if cleaned["struck_segments"]:
            struck_summary.append(
                {"addr": addr, "removed": " | ".join(cleaned["struck_segments"])}
            )
        m = re.fullmatch(r"([A-Z]+)(\d+)", addr)
        if not m:
            continue
        col = sum((ord(c) - 64) * (26**i) for i, c in enumerate(reversed(m.group(1))))
        row = int(m.group(2))
        grid[(row, col)] = cleaned["text"]
        max_r = max(max_r, row)
        max_c = max(max_c, col)

    tsv_lines: list[str] = []
    if max_r and max_c:
        for r in range(1, max_r + 1):
            row_vals = [grid.get((r, c), "") for c in range(1, max_c + 1)]
            if any(v.strip() for v in row_vals):
                tsv_lines.append("\t".join(row_vals))

    return {
        "spreadsheet_token": token,
        "sheet_id": sid,
        "range": range_a1,
        "cells": cells,
        "tsv": "\n".join(tsv_lines),
        "struck_summary": struck_summary,
        "struck_count": len(struck_summary),
    }


# --- 结构化解析（按列头）：把 ETD 宽表变成机读事件表 -----------------------
# 让 agent 不必肉眼读 20 列宽表。列头对不上时返回 None，调用方回退人工抽取。

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "event": ("event_name", "event", "事件名称", "事件名", "埋点名称"),
    "report_side": ("用户类型", "上报端", "上报角色", "端类型"),
    "param": ("param名称", "参数名称", "参数名", "param_name"),
    "required": ("是否必传", "是否必填", "必传"),
    "values": ("param取值", "参数取值", "枚举取值", "枚举值", "取值"),
    "behavior": ("埋点行为类型", "行为类型"),
    "change": ("变更类型", "是否新增", "新增/修改", "变更说明", "变更", "埋点状态"),
    "timing": ("上报时机", "触发时机"),
    "param_desc": ("param描述", "参数描述"),
}

# 「主播侧」「用户侧/观众侧/看播侧」→ scope.roles。默认主播是问题 2 的根因，必须显式解析。
_ROLE_MAP: tuple[tuple[str, str], ...] = (
    ("主播", "anchor"),
    ("anchor", "anchor"),
    ("host", "anchor"),
    ("嘉宾", "guest"),
    ("guest", "guest"),
    ("用户", "viewer"),
    ("观众", "viewer"),
    ("看播", "viewer"),
    ("viewer", "viewer"),
    ("audience", "viewer"),
)

_TRUTHY = {"true", "t", "yes", "y", "1", "是", "必传", "√", "✓"}

_ENUM_ITEM_RE = re.compile(
    r"(?:^|[；;、,，/|\n])\s*[「『\"'`]?([A-Za-z0-9_.\-]+)[」』\"'`]?\s*[：:=]"
)


def _norm_header(text: str) -> str:
    """列头归一：去空白、去括号补充说明、转小写。"""
    cleaned = re.sub(r"[（(].*?[)）]", "", str(text or ""))
    return re.sub(r"\s+", "", cleaned).lower()


def parse_enum_values(text: str) -> list[str]:
    """从 `param取值` 单元格抽离散取值。抽不到 → 空列表（= opaque，不拆行）。"""
    raw = str(text or "").strip()
    if not raw:
        return []
    # 「值：说明」列表，分隔符各 ETD 不一（；、,\n 都见过）→ 在分隔边界上扫，不预先切分。
    # 宁可多抽（门禁报缺失，人一眼能发现）也不少抽（静默漏枚举 = 少生成用例）。
    values = _ENUM_ITEM_RE.findall(raw)
    if values:
        return list(dict.fromkeys(values))
    # 无「值：说明」形态时，只认纯枚举串（`up/down`、`a、b`），自然语言描述一律判 opaque
    if re.fullmatch(r"[A-Za-z0-9_.\-]+(\s*[/、,，|]\s*[A-Za-z0-9_.\-]+)+", raw):
        return list(dict.fromkeys(re.split(r"\s*[/、,，|]\s*", raw)))
    return []


def parse_report_sides(text: str) -> list[str]:
    hit = [role for token, role in _ROLE_MAP if token in str(text or "").lower()]
    return list(dict.fromkeys(hit))


def _grid_from_cells(cells: list[dict[str, Any]]) -> dict[int, dict[int, str]]:
    grid: dict[int, dict[int, str]] = {}
    for cell in cells:
        m = re.fullmatch(r"([A-Z]+)(\d+)", str(cell.get("addr", "")))
        if not m:
            continue
        col = sum((ord(c) - 64) * (26**i) for i, c in enumerate(reversed(m.group(1))))
        grid.setdefault(int(m.group(2)), {})[col] = str(cell.get("text") or "")
    return grid


def parse_etd_table(payload: dict[str, Any]) -> dict[str, Any] | None:
    """把 load_etd_sheet 的输出解析成结构化事件表；列头认不出返回 None。"""
    grid = _grid_from_cells(payload.get("cells") or [])
    if not grid:
        return None

    header_row = columns = None
    for row in sorted(grid)[:10]:
        found: dict[str, int] = {}
        for col, text in grid[row].items():
            norm = _norm_header(text)
            if not norm:
                continue
            for field, aliases in _HEADER_ALIASES.items():
                if field in found:
                    continue
                if norm in aliases or any(norm.startswith(a) for a in aliases):
                    found[field] = col
        if "event" in found and "param" in found:
            header_row, columns = row, found
            break
    if header_row is None or columns is None:
        return None

    def cell(row: int, field: str) -> str:
        col = columns.get(field)
        return grid.get(row, {}).get(col, "").strip() if col else ""

    events: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    current = ""
    for row in sorted(r for r in grid if r > header_row):
        # 合并单元格：event 列只在首行有值，后续 param 行为空 → 向下填充
        row_event_cell = cell(row, "event")
        current = row_event_cell or current
        if not current:
            continue
        event = by_name.get(current)
        if event is None:
            event = {
                "event_name": current,
                "roles": [],
                "behaviors": [],
                "timing": cell(row, "timing"),
                "change_raw": cell(row, "change"),
                "params": [],
            }
            by_name[current] = event
            events.append(event)
        for role in parse_report_sides(cell(row, "report_side")):
            if role not in event["roles"]:
                event["roles"].append(role)
        behavior = cell(row, "behavior")
        if behavior and behavior not in event["behaviors"]:
            event["behaviors"].append(behavior)
        event["timing"] = event["timing"] or cell(row, "timing")
        event["change_raw"] = event["change_raw"] or cell(row, "change")

        key = cell(row, "param")
        if not key or any(p["key"] == key for p in event["params"]):
            continue
        raw_values = cell(row, "values")
        event["params"].append(
            {
                "key": key,
                "required": cell(row, "required").strip().lower() in _TRUTHY,
                "values": parse_enum_values(raw_values),
                "raw_values": raw_values,
                "desc": cell(row, "param_desc"),
                # 事件首行的变更说明属于事件级，不能当成该参数「新增」的证据
                "change_raw": "" if row_event_cell else cell(row, "change"),
            }
        )

    if not events:
        return None
    return {
        "header_row": header_row,
        "columns": {k: _col_letters(v) for k, v in sorted(columns.items())},
        "unmapped_fields": sorted(set(_HEADER_ALIASES) - set(columns)),
        "events": events,
    }


def scope_draft(table: dict[str, Any], etd_url: str = "") -> dict[str, Any]:
    """结构化事件表 → etd_scope.json 草稿。故意留空 entrances，逼 agent 补全后才过门禁。"""
    events = []
    for ev in table["events"]:
        params = []
        for p in ev["params"]:
            kind = "enum" if p["values"] else "opaque"
            if re.search(r"_(u?cnt|num|count|rate)$", p["key"]):
                kind = "semantic"
            param: dict[str, Any] = {"key": p["key"], "kind": kind, "required": p["required"]}
            if p["values"]:
                param["values"] = p["values"]
            if p["desc"]:
                param["desc"] = p["desc"]
            # 参数级「新增」：只认参数行自己写的新增，「新增埋点」是事件级说明
            p_change = str(p.get("change_raw") or "")
            if "新增" in p_change and not re.search(r"埋点|事件", p_change):
                param["added"] = True
            params.append(param)
        # ponytail: 按「变更类型」列关键字起草反例形态，列缺失/写法认不出就留空 ""，
        # 门禁报错逼人工确认；不默认 new_event（默认就是错反例「直接不上报」的来路）。
        ev_change = str(ev.get("change_raw") or "")
        if "新增" in ev_change and re.search(r"参数|字段|param", ev_change):
            change_type = "param_added"
        elif "新增" in ev_change:
            change_type = "new_event"
        else:
            change_type = ""
        events.append(
            {
                "event_name": ev["event_name"],
                "entrances": [],
                "roles": ev["roles"],
                "roles_evidence": f"ETD 用户类型/上报端列（{'、'.join(ev['roles']) or '未填'}）",
                "change_type": change_type,
                "change_evidence": f"ETD 变更类型列（{ev.get('change_raw') or '未填'}）",
                "params": params,
                "note": f"埋点行为类型={'/'.join(ev['behaviors']) or '?'}；上报时机={ev['timing']}",
            }
        )
    return {
        "etd_url": etd_url,
        "authority": "user_etd_body",
        "_draft": "由 etd_sheet_load.py --emit-scope-draft 生成；agent 必须补 entrances / "
        "expected_combinations / policies / test_kit 并复核 kind 后才能过门禁",
        "events": events,
        "out_of_scope": [],
        "conflicts": [],
        "test_kit": {"source_doc": "", "packages": {}, "env": "", "libra_flights": [], "accounts": [], "missing": []},
    }


def self_check() -> None:
    # whole cell struck
    c1 = clean_cell_payload(
        {"value": "stage_reaction_click: 点击", "cell_styles": {"font_line": "line-through"}}
    )
    assert c1["text"] == "" and c1["struck"] and "stage_reaction_click" in c1["struck_segments"][0]

    # mixed rich text: keep live, drop struck
    c2 = clean_cell_payload(
        {
            "value": "mic: x\nstage_reaction_click: y\nlive_setting: z",
            "rich_text": [
                {"text": "mic: x\n", "style": {}},
                {
                    "text": "stage_reaction_click: y\n",
                    "style": {"font_line": "line-through"},
                },
                {"text": "live_setting: z", "style": {}},
            ],
        }
    )
    assert "mic: x" in c2["text"]
    assert "live_setting: z" in c2["text"]
    assert "stage_reaction_click" not in c2["text"]
    assert any("stage_reaction_click" in s for s in c2["struck_segments"])

    # plain live cell
    c3 = clean_cell_payload({"value": "show", "cell_styles": {"font_line": "none"}})
    assert c3["text"] == "show" and not c3["struck"]

    # textDecoration variant
    c4 = clean_cell_payload({"value": "dead", "style": {"textDecoration": "lineThrough"}})
    assert c4["text"] == "" and c4["struck"]

    assert parse_enum_values("0：不含；1：含有button") == ["0", "1"]
    assert parse_enum_values("click_cta：点击cta；\nfold：点击收起 ；\nslide_up：上滑关闭；") == [
        "click_cta",
        "fold",
        "slide_up",
    ]
    assert parse_enum_values("up/down") == ["up", "down"]
    # 顿号分隔（真实 ETD 里 position_before 就是这个写法，曾漏掉 down）
    assert parse_enum_values("up：会挡住二三排的位置、down：靠下不挡住二三排的位置") == ["up", "down"]
    assert parse_enum_values("直播间 id，必传") == []
    assert parse_report_sides("主播侧") == ["anchor"]
    assert parse_report_sides("用户侧") == ["viewer"]
    assert parse_report_sides("主播侧、用户侧") == ["anchor", "viewer"]

    # 真实 ETD 版式：合并的 event 列 + 每行一个 param + 单元格内换行
    header = [
        "序号", "event", "埋点描述", "埋点类型", "用户类型", "上报时机",
        "param名称", "param类型", "param级别（需求核心关注参数）", "是否必传",
        "param取值", "埋点行为类型",
    ]
    rows = [
        ["1", "livesdk_cues_msg_click", "点击时上报", "行为埋点", "用户侧", "点击时",
         "action_type", "string", "string", "TRUE",
         "click_cta：点击cta；\nfold：收起；\nslide_up：上滑关闭；", "click"],
        ["", "", "", "", "", "", "is_button", "string", "string", "TRUE", "0：不含；1：含有", ""],
        ["2", "livesdk_cues_msg_show", "曝光上报", "行为埋点", "主播侧", "展现时",
         "msg_id", "string", "string", "TRUE", "提词器消息 id", "show"],
    ]
    cells = [
        {"addr": f"{_col_letters(c + 1)}{r + 1}", "text": val}
        for r, row in enumerate([header, *rows])
        for c, val in enumerate(row)
    ]
    table = parse_etd_table({"cells": cells})
    assert table and len(table["events"]) == 2, table
    click = table["events"][0]
    assert click["roles"] == ["viewer"], click  # 不能默认主播侧
    assert [p["key"] for p in click["params"]] == ["action_type", "is_button"]  # 合并行未丢
    assert click["params"][0]["values"] == ["click_cta", "fold", "slide_up"]
    assert click["params"][1]["values"] == ["0", "1"]
    show = table["events"][1]
    assert show["roles"] == ["anchor"] and show["params"][0]["values"] == []

    draft = scope_draft(table, "https://example.com/etd")
    assert draft["events"][0]["params"][0]["kind"] == "enum"
    assert draft["events"][1]["params"][0]["kind"] == "opaque"
    assert draft["events"][0]["entrances"] == []  # 草稿必须过不了 validate_scope
    # 无「变更类型」列 → change_type 留空，逼人工确认反例形态（不默认 new_event）
    assert draft["events"][0]["change_type"] == ""

    # 有「变更类型」列：整事件新增 → new_event；老事件只有部分参数新增 → param_added
    change_header = [*header, "变更类型"]
    change_rows = [
        [*rows[0], "新增埋点"],
        [*rows[1], "新增埋点"],
        [*rows[2], "已有埋点，新增参数"],
        ["", "", "", "", "", "", "guide_type", "string", "string", "TRUE", "ai/human", "", "新增参数"],
    ]
    change_cells = [
        {"addr": f"{_col_letters(c + 1)}{r + 1}", "text": val}
        for r, row in enumerate([change_header, *change_rows])
        for c, val in enumerate(row)
    ]
    change_draft = scope_draft(parse_etd_table({"cells": change_cells}) or {"events": []})
    assert change_draft["events"][0]["change_type"] == "new_event", change_draft["events"][0]
    existing = change_draft["events"][1]
    assert existing["change_type"] == "param_added", existing
    assert [p["key"] for p in existing["params"] if p.get("added")] == ["guide_type"], existing

    # 列头认不出 → None（回退人工抽取，不能假装解析成功）
    assert parse_etd_table({"cells": [{"addr": "A1", "text": "随便写的标题"}]}) is None

    print("etd_sheet_load self-check OK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url")
    ap.add_argument("--spreadsheet-token")
    ap.add_argument("--sheet-id")
    ap.add_argument("--range", default="A1:Z200", dest="range_a1")
    ap.add_argument("--as", dest="as_identity", choices=["user", "bot"])
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--tsv-only", action="store_true", help="print cleaned TSV only")
    ap.add_argument(
        "--emit-scope-draft",
        action="store_true",
        help="按列头解析成 etd_scope.json 草稿（事件/上报端/必传参/枚举取值全量），agent 只需补 entrances 等",
    )
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return 0

    if not args.url and not args.spreadsheet_token:
        ap.error("need --url or --spreadsheet-token (or --self-check)")

    result = load_etd_sheet(
        url=args.url,
        spreadsheet_token=args.spreadsheet_token,
        sheet_id=args.sheet_id,
        range_a1=args.range_a1,
        as_identity=args.as_identity,
    )
    if args.emit_scope_draft:
        table = parse_etd_table(result)
        if table is None:
            print(
                "[etd_sheet_load] 列头未识别（没找到 event / param名称 列），"
                "无法生成 scope 草稿 —— 回退 SKILL.md Step 1.5 人工抽取 + --etd-text 反查",
                file=sys.stderr,
            )
            return 3
        print(json.dumps(scope_draft(table, args.url or ""), ensure_ascii=False, indent=2))
        if table["unmapped_fields"]:
            print(
                f"[etd_sheet_load] 这些列没认出来，需人工核对: {table['unmapped_fields']}",
                file=sys.stderr,
            )
    elif args.tsv_only:
        print(result["tsv"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["struck_count"]:
        print(
            f"[etd_sheet_load] stripped {result['struck_count']} struck cell(s)/segment group(s)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
