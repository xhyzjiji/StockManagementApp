"""
Knowledge Loader — 按业务线从飞书文档远程加载 accounts / ui_routes 知识。

核心流程：
  1. 读取 data/knowledge_index.json 获取业务线 → 飞书文档映射
  2. resolve_biz() 根据用户指定或 spec 文本关键词自动匹配业务线
  3. load_accounts() / load_routes() 通过 gdpa-cli 的 lark-docs 能力拉取文档内容，带 TTL 缓存

降级策略：
  - gdpa 文档读取失败时自动回退到本地 data/accounts.txt 和 data/ui_routes.txt
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_INDEX_PATH = os.path.join(_DATA_DIR, "knowledge_index.json")

CACHE_DIR = os.path.join("/tmp", "knowledge_cache")
CACHE_TTL_SECONDS = 3600


@dataclass
class BizLine:
    id: str
    name: str
    keywords: List[str]
    accounts_doc: str
    routes_doc: str


_index: Optional[Dict] = None
_biz_lines: List[BizLine] = []
_default_biz: str = ""


def _load_index() -> None:
    global _index, _biz_lines, _default_biz
    if _index is not None:
        return
    if not os.path.isfile(_INDEX_PATH):
        _index = {}
        return
    with open(_INDEX_PATH, "r", encoding="utf-8") as f:
        _index = json.load(f)
    _default_biz = _index.get("default", "")
    _biz_lines.clear()
    for entry in _index.get("business_lines", []):
        _biz_lines.append(BizLine(
            id=entry["id"],
            name=entry["name"],
            keywords=entry.get("keywords", []),
            accounts_doc=entry.get("accounts_doc", ""),
            routes_doc=entry.get("routes_doc", ""),
        ))


def list_biz_lines() -> List[BizLine]:
    _load_index()
    return list(_biz_lines)


def resolve_biz(spec_text: str = "", user_biz: str = None) -> str:
    """
    确定业务线 ID。

    优先级：
      1. user_biz 显式指定（精确 id 或名称模糊匹配）
      2. 扫描 spec_text 匹配 keywords，取命中数最多的业务线
      3. fallback 到 default
    """
    _load_index()

    if user_biz:
        user_biz_lower = user_biz.strip().lower()
        for bl in _biz_lines:
            if bl.id.lower() == user_biz_lower or bl.name == user_biz.strip():
                return bl.id
        for bl in _biz_lines:
            if user_biz_lower in bl.id.lower() or user_biz_lower in bl.name.lower():
                return bl.id

    if spec_text:
        text_lower = spec_text.lower()
        best_id = ""
        best_hits = 0
        for bl in _biz_lines:
            hits = sum(1 for kw in bl.keywords if kw.lower() in text_lower)
            if hits > best_hits:
                best_hits = hits
                best_id = bl.id
        if best_id:
            return best_id

    return _default_biz


def _get_biz(biz_id: str) -> Optional[BizLine]:
    _load_index()
    for bl in _biz_lines:
        if bl.id == biz_id:
            return bl
    return None


def _cache_path(biz_id: str, doc_type: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{biz_id}_{doc_type}.txt")


def _read_cache(biz_id: str, doc_type: str) -> Optional[str]:
    path = _cache_path(biz_id, doc_type)
    if not os.path.isfile(path):
        return None
    age = time.time() - os.path.getmtime(path)
    if age > CACHE_TTL_SECONDS:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_cache(biz_id: str, doc_type: str, content: str) -> None:
    path = _cache_path(biz_id, doc_type)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _extract_session_id(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("gdpa-cli create-session 返回为空")

    try:
        payload = _extract_json_payload(text)
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        candidates = [
            payload,
            payload.get("data"),
            payload.get("session"),
            payload.get("result"),
        ]
        for candidate in candidates:
            if isinstance(candidate, dict):
                for key in ("session_id", "sessionId", "id"):
                    value = candidate.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            elif isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

    for pattern in (
        r"session[_-]?id['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9._:-]+)",
        r"\b(sess_[A-Za-z0-9._:-]+)\b",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        last_line = lines[-1]
        if re.fullmatch(r"[A-Za-z0-9._:-]+", last_line):
            return last_line
        tokens = re.findall(r"[A-Za-z0-9._:-]{8,}", last_line)
        if len(tokens) == 1:
            return tokens[0]

    raise RuntimeError(f"无法从 gdpa-cli create-session 输出中解析 session_id: {text}")


def _ensure_gdpa_session_id() -> str:
    for env_name in ("GDPA_SESSION_ID", "SESSION_ID"):
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value

    result = subprocess.run(
        ["gdpa-cli", "create-session"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "gdpa-cli create-session 失败: "
            f"code={result.returncode}, stderr={result.stderr.strip() or result.stdout.strip()}"
        )
    return _extract_session_id(result.stdout)


def _extract_json_payload(raw: str):
    text = (raw or "").strip()
    if not text:
        raise ValueError("gdpa-cli 返回为空")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"无法解析 gdpa-cli 输出为 JSON: {text[:300]}")


def _extract_doc_text(payload) -> str:
    candidates = []
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        candidates.extend(
            [
                data,
                data.get("document") if isinstance(data, dict) else None,
                data.get("doc") if isinstance(data, dict) else None,
                data.get("prd") if isinstance(data, dict) else None,
                data.get("content") if isinstance(data, dict) else None,
            ]
        )

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if not isinstance(candidate, dict):
            continue

        for key in ("markdown", "content", "text", "body", "design"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                title = candidate.get("title")
                if key == "design" and isinstance(title, str) and title.strip():
                    return f"{title.strip()}\n{value.strip()}"
                return value.strip()

        title = candidate.get("title")
        if isinstance(title, str) and title.strip():
            for key in ("design", "markdown", "content", "text", "body"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return f"{title.strip()}\n{value.strip()}"

    raise ValueError(f"无法从 lark-docs 返回中提取文档正文: {json.dumps(payload, ensure_ascii=False)[:500]}")


def _fetch_lark_doc(doc_url: str, user_name: str = None) -> str:
    """Fetch document content from Lark through gdpa-cli lark-docs."""
    session_id = _ensure_gdpa_session_id()
    payload = {"url": doc_url}
    if user_name:
        payload["user_name"] = user_name

    result = subprocess.run(
        [
            "gdpa-cli",
            "run",
            "lark-docs",
            "--session-id",
            session_id,
            "--input",
            json.dumps(payload, ensure_ascii=False),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "gdpa-cli run lark-docs 失败: "
            f"code={result.returncode}, stderr={result.stderr.strip() or result.stdout.strip()}"
        )
    response = _extract_json_payload(result.stdout)
    return _extract_doc_text(response)


def _local_fallback(doc_type: str) -> str:
    filename = "accounts.txt" if doc_type == "accounts" else "ui_routes.txt"
    path = os.path.join(_DATA_DIR, filename)
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_accounts(biz: str, user_name: str = None) -> str:
    """
    Load accounts knowledge for the given business line.

    Returns content in accounts.txt format (plain text).
    Falls back to local data/accounts.txt on failure.
    """
    cached = _read_cache(biz, "accounts")
    if cached:
        return cached

    bl = _get_biz(biz)
    if not bl or not bl.accounts_doc:
        return _local_fallback("accounts")

    try:
        content = _fetch_lark_doc(bl.accounts_doc, user_name)
        _write_cache(biz, "accounts", content)
        return content
    except Exception as e:
        print(f"[knowledge_loader] 飞书文档加载失败 (accounts, biz={biz}): {e}", file=sys.stderr)
        print("[knowledge_loader] 降级使用本地 accounts.txt", file=sys.stderr)
        return _local_fallback("accounts")


def load_routes(biz: str, user_name: str = None) -> str:
    """
    Load UI routes knowledge for the given business line.

    Returns content in ui_routes.txt format (plain text).
    Falls back to local data/ui_routes.txt on failure.
    """
    cached = _read_cache(biz, "routes")
    if cached:
        return cached

    bl = _get_biz(biz)
    if not bl or not bl.routes_doc:
        return _local_fallback("routes")

    try:
        content = _fetch_lark_doc(bl.routes_doc, user_name)
        _write_cache(biz, "routes", content)
        return content
    except Exception as e:
        print(f"[knowledge_loader] 飞书文档加载失败 (routes, biz={biz}): {e}", file=sys.stderr)
        print("[knowledge_loader] 降级使用本地 ui_routes.txt", file=sys.stderr)
        return _local_fallback("routes")


def load_all(biz: str, user_name: str = None) -> dict:
    """
    Load both accounts and routes for the given business line.

    Returns {"accounts": str, "routes": str, "biz": str}.
    """
    return {
        "biz": biz,
        "accounts": load_accounts(biz, user_name),
        "routes": load_routes(biz, user_name),
    }
