#!/usr/bin/env python3
"""G2 转换后门禁：验证 *_richtext.md 里前置环境工具节点按正确工具落地。

正确选型（与 ui-xmind-case-gen / tool_skills 一致）：
  - PPE / 泳道 env     → 工具 `环境名称`（inputData key=`envName`）
  - Libra 加实验       → 工具 `libra实验`（inputData key=`libraExperiment`，含 libra_id）
  - 地区/语言/AB KV    → 工具 `ttmock_preset`（region/language/ab_settings*）
  - 禁止把 env / libra 塞进 ttmock_preset.params

Usage:
  python check_xmind_precondition.py --richtext path/to/*_richtext.md [--expect-env ENV] [--expect-flights IDS]
  python check_xmind_precondition.py --self-check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ENV_TOOL_TEXTS = ("环境名称", "env_name")
LIBRA_TOOL_TEXTS = ("libra实验", "libra experiment")
TTMOCK_TOOL_TEXT = "ttmock_preset"


def _extract_json_array(md_text: str) -> list[Any]:
    """从 ```json ... ``` 块中抽出 JSON 数组。"""
    m = re.search(r"```json\s*(\[[\s\S]*?\])\s*```", md_text)
    if not m:
        raise ValueError("richtext markdown 中没找到 ```json ... ``` 代码块")
    return json.loads(m.group(1))


def _parse_inputdata(raw: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"inputData 不是合法 JSON: {e}")
    if not isinstance(data, list):
        raise ValueError(f"inputData 必须是 list，实际是 {type(data).__name__}")
    entries: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            entries.append(item)
        elif isinstance(item, str):
            try:
                inner = json.loads(item)
            except json.JSONDecodeError as e:
                raise ValueError(f"inputData 元素不是合法 JSON 字符串: {e}")
            if not isinstance(inner, dict):
                raise ValueError(
                    f"inputData 元素必须是 object 字符串，实际是 {type(inner).__name__}"
                )
            entries.append(inner)
        else:
            raise ValueError(
                f"inputData 元素必须是 dict 或 JSON 字符串，实际是 {type(item).__name__}"
            )
    return entries


def _tool_kv(tool: dict[str, Any]) -> dict[str, list[str]]:
    raw = tool.get("inputData")
    entries = _parse_inputdata(raw) if isinstance(raw, str) else raw
    result: dict[str, list[str]] = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "")
        if not key:
            continue
        val = entry.get("value")
        vals: list[str] = []
        if isinstance(val, list):
            for v in val:
                if isinstance(v, str):
                    vals.append(v)
                elif v is not None:
                    vals.append(str(v))
        elif isinstance(val, str):
            vals.append(val)
        elif val is not None:
            vals.append(str(val))
        result[key] = vals
    return result


def _find_tools(nodes: list[Any], texts: tuple[str, ...] | str) -> list[dict[str, Any]]:
    wanted = {texts} if isinstance(texts, str) else set(texts)
    found: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("text") not in wanted:
            continue
        pd = node.get("pluginData")
        if not isinstance(pd, dict):
            continue
        atsb = pd.get("autoxToolSaveBindItem")
        if not isinstance(atsb, dict):
            continue
        found.append(atsb)
    return found


def _collect_env_values(nodes: list[Any]) -> list[str]:
    values: list[str] = []
    for tool in _find_tools(nodes, ENV_TOOL_TEXTS):
        try:
            kv = _tool_kv(tool)
        except ValueError:
            continue
        for v in kv.get("envName", []) + kv.get("env", []):
            raw = str(v).strip()
            if not raw:
                continue
            # builder stores envName value as {"env":"ppe_xxx"} JSON string
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and obj.get("env"):
                    values.append(str(obj["env"]).strip())
                    continue
            except json.JSONDecodeError:
                pass
            values.append(raw)
    return values


def _collect_libra_ids(nodes: list[Any]) -> set[str]:
    ids: set[str] = set()
    for tool in _find_tools(nodes, LIBRA_TOOL_TEXTS):
        try:
            kv = _tool_kv(tool)
        except ValueError:
            continue
        for blob in kv.get("libraExperiment", []):
            text = str(blob)
            ids.update(re.findall(r'"libra_id"\s*:\s*(\d+)', text))
            ids.update(re.findall(r'"fids"\s*:\s*\[\s*"?(\d+)"?', text))
            try:
                obj = json.loads(blob) if isinstance(blob, str) else blob
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(obj, dict):
                for fid in obj.get("fids") or []:
                    ids.add(str(fid))
                for item in obj.get("libra") or []:
                    if isinstance(item, dict) and item.get("libra_id") is not None:
                        ids.add(str(item["libra_id"]))
    return ids


def _collect_ab_settings_keys(nodes: list[Any]) -> set[str]:
    keys: set[str] = set()
    for tool in _find_tools(nodes, TTMOCK_TOOL_TEXT):
        try:
            kv = _tool_kv(tool)
        except ValueError:
            continue
        for param in ("ab_settings", "ab_settings_live"):
            for blob in kv.get(param, []):
                if not blob:
                    continue
                try:
                    obj = json.loads(blob) if isinstance(blob, str) else blob
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(obj, dict):
                    keys.update(str(k) for k in obj.keys())
    return keys


def _ttmock_has_forbidden_params(nodes: list[Any]) -> list[str]:
    """Detect legacy mistakes: stuffing env=/libra= into ttmock tool text is already lost
    at render time; here we only flag if inputData somehow still has those keys."""
    bad: list[str] = []
    for tool in _find_tools(nodes, TTMOCK_TOOL_TEXT):
        try:
            kv = _tool_kv(tool)
        except ValueError as e:
            bad.append(str(e))
            continue
        for forbidden in ("env", "server_env", "environment", "env_name", "libra"):
            if any(str(v).strip() for v in kv.get(forbidden, [])):
                bad.append(
                    f"G2 ttmock_preset 误带 `{forbidden}`：env 应用 `环境名称`，"
                    "Libra 应用 `libra实验`，不要塞进 ttmock_preset"
                )
    return bad


def check_richtext(
    richtext_path: Path,
    expect_env: str | None = None,
    expect_flights: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    text = richtext_path.read_text(encoding="utf-8")
    try:
        nodes = _extract_json_array(text)
    except (ValueError, json.JSONDecodeError) as e:
        errors.append(f"richtext 解析失败 `{richtext_path.name}`: {e}")
        return errors

    errors.extend(_ttmock_has_forbidden_params(nodes))

    # ab_settings 若出现，必须是 JSON 对象（非数组 / 非 flight: 文本）
    for tool in _find_tools(nodes, TTMOCK_TOOL_TEXT):
        try:
            kv = _tool_kv(tool)
        except ValueError as e:
            errors.append(f"ttmock_preset inputData 解析失败: {e}")
            continue
        for param in ("ab_settings", "ab_settings_live"):
            for blob in kv.get(param, []):
                if blob is None or blob == "":
                    continue
                raw = blob if isinstance(blob, str) else json.dumps(blob, ensure_ascii=False)
                try:
                    obj = json.loads(raw) if isinstance(blob, str) else blob
                except json.JSONDecodeError:
                    errors.append(
                        f"G2 ttmock_preset `{param}` 不是合法 JSON 对象 string（实际={raw!r}）。"
                        '标准形态：{"72192329":"1"}'
                    )
                    continue
                if not isinstance(obj, dict):
                    errors.append(
                        f"G2 ttmock_preset `{param}` 必须是 JSON 对象，禁止数组/标量"
                        f"（实际 type={type(obj).__name__}）"
                    )

    if expect_env:
        envs = _collect_env_values(nodes)
        if not envs:
            errors.append(
                "G2 缺少 `环境名称` 工具或 envName 为空：PPE/泳道必须用 "
                '`--precondition-tools-json` 传 `{"tool":"环境名称","params":{"env":"..."}}`，'
                "禁止塞进 ttmock_preset"
            )
        elif expect_env not in envs:
            errors.append(
                f"G2 环境名称不匹配：期望 `{expect_env}` 实际 `{envs}`"
            )

    if expect_flights:
        libra_ids = _collect_libra_ids(nodes)
        missing = [f for f in expect_flights if f not in libra_ids]
        if missing:
            errors.append(
                f"G2 缺少 `libra实验` 覆盖 flight {missing}（已解析 libra_id={sorted(libra_ids) or '[]'}）。"
                "每个 flight 需要 `libra实验 region= libra_id= group_id=`；"
                "仅当有 Libra 链接且缺 group_id 时分别问实验组与对照组，正向挂实验组、对照/反向挂对照组"
                "（见 references/libra-group-assignment.md）。禁止把 libra/flight 塞进 ttmock_preset。"
            )

    return errors


def _make_tool_md(text: str, input_data_entries: list[dict[str, Any]]) -> str:
    input_data_str = json.dumps(input_data_entries, ensure_ascii=False)
    node = {
        "type": 2,
        "text": text,
        "id": "x",
        "pluginData": {
            "autoxToolSaveBindItem": {
                "mentionId": "x",
                "biz": 1,
                "saitamaTemplateId": "tpl",
                "inputData": input_data_str,
                "appId": 1233,
            }
        },
    }
    arr_str = json.dumps([node], ensure_ascii=False, indent=2)
    return f"# RichText List\n\n```json\n{arr_str}\n```\n"


def _make_multi_tool_md(tools: list[tuple[str, list[dict[str, Any]]]]) -> str:
    nodes = []
    for i, (text, entries) in enumerate(tools):
        nodes.append(
            {
                "type": 2,
                "text": text,
                "id": f"x{i}",
                "pluginData": {
                    "autoxToolSaveBindItem": {
                        "mentionId": f"x{i}",
                        "biz": 1,
                        "saitamaTemplateId": "tpl",
                        "inputData": json.dumps(entries, ensure_ascii=False),
                        "appId": 1233,
                    }
                },
            }
        )
    return "# RichText List\n\n```json\n" + json.dumps(nodes, ensure_ascii=False, indent=2) + "\n```\n"


@contextmanager
def _tmp_richtext(md: str):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x_richtext.md"
        p.write_text(md, encoding="utf-8")
        yield p


def self_check() -> int:
    # 坏：只有空 ttmock，期望 env+flight 都应失败
    bad = _make_tool_md(
        TTMOCK_TOOL_TEXT,
        [
            {"key": "language", "value": ["zh"]},
            {"key": "region", "value": ["US"]},
            {"key": "ab_settings", "value": []},
            {"key": "ab_settings_live", "value": []},
        ],
    )
    with _tmp_richtext(bad) as p:
        errs = check_richtext(p, expect_env="ppe_x", expect_flights=["123"])
        if not any("环境名称" in e for e in errs):
            print("self-check FAIL: missing 环境名称 must fail, got", errs)
            return 1
        if not any("libra实验" in e for e in errs):
            print("self-check FAIL: missing libra实验 must fail, got", errs)
            return 1

    # 坏：ab_settings 用数组
    bad_ab = _make_tool_md(
        TTMOCK_TOOL_TEXT,
        [{"key": "ab_settings", "value": [json.dumps([{"key": "1", "value": "1"}])]}],
    )
    with _tmp_richtext(bad_ab) as p:
        errs = check_richtext(p)
        if not any("必须是 JSON 对象" in e for e in errs):
            print("self-check FAIL: array ab_settings must fail, got", errs)
            return 1

    # 好：环境名称 + libra实验
    good = _make_multi_tool_md(
        [
            (
                "环境名称",
                [{"key": "envName", "value": ['{"env":"ppe_x"}']}],
            ),
            (
                "libra实验",
                [
                    {
                        "key": "libraExperiment",
                        "value": [
                            json.dumps(
                                {
                                    "region": "sg",
                                    "fids": ["123"],
                                    "libra": [
                                        {
                                            "libra_title": "t",
                                            "libra_id": 123,
                                            "group_id": 1,
                                            "region": "sg",
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        ],
                    }
                ],
            ),
            (
                TTMOCK_TOOL_TEXT,
                [
                    {"key": "language", "value": ["zh"]},
                    {"key": "region", "value": ["US"]},
                    {"key": "ab_settings", "value": [json.dumps({"72192329": "1"})]},
                    {"key": "ab_settings_live", "value": []},
                ],
            ),
        ]
    )
    with _tmp_richtext(good) as p:
        errs = check_richtext(p, expect_env="ppe_x", expect_flights=["123"])
        if errs:
            print("self-check FAIL: good case should pass, got", errs)
            return 1

    # 没节点但 expect 有值
    empty = "# RichText List\n\n```json\n[]\n```\n"
    with _tmp_richtext(empty) as p:
        errs = check_richtext(p, expect_env="ppe_x")
        if not any("环境名称" in e for e in errs):
            print("self-check FAIL: empty richtext must fail env, got", errs)
            return 1

    print("self-check OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--richtext", help="path to *_richtext.md")
    ap.add_argument("--expect-env", help="expected env value (e.g. ppe_unified_im)")
    ap.add_argument(
        "--expect-flights",
        help="comma-separated libra flight IDs that must appear in libra实验",
    )
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    if not args.richtext:
        ap.error("--richtext is required unless --self-check")
    p = Path(args.richtext)
    if not p.exists():
        print(f"ERROR: richtext not found: {p}", file=sys.stderr)
        return 2

    flights = (
        [x.strip() for x in args.expect_flights.split(",") if x.strip()]
        if args.expect_flights
        else None
    )
    errors = check_richtext(p, expect_env=args.expect_env, expect_flights=flights)
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
