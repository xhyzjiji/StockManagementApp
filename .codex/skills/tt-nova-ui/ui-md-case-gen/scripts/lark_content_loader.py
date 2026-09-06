import json
import os
import re
import subprocess


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


def lark_content_loader(document_url: str, user_name: str = None) -> str:
    payload = {"url": document_url}
    if user_name:
        payload["user_name"] = user_name

    result = subprocess.run(
        [
            "gdpa-cli",
            "run",
            "lark-docs",
            "--session-id",
            _ensure_gdpa_session_id(),
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
    return _extract_doc_text(_extract_json_payload(result.stdout))


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python lark_content_loader.py <document_url> [user_name]")
        sys.exit(1)

    document_url = sys.argv[1]
    user_name = sys.argv[2] if len(sys.argv) > 2 else None

    print(lark_content_loader(document_url, user_name))
