#!/usr/bin/env python3
"""Tika 自定义 Agent OpenAPI 知识检索客户端。

实现自《Tika 自定义 Agent 接入：飞书机器人 / OpenAPI / ByteOncall》：
https://bytedance.larkoffice.com/wiki/VEX4wwxF4iDV24ktekacclT3ndf

- create conversation : POST /tiktok/efficiency/api/v2/space/conversation/create
- chat (SSE 流式)      : POST /tiktok/efficiency/api/v2/space/chat/chat
- get conversation     : POST /tiktok/efficiency/api/v2/space/conversation/detail

对外主要暴露 `retrieve_knowledge(query, ...)`：内部串起「建会话 → 发起对话(检索)」，
解析 SSE 事件流，返回 {answer, references[...], chat_id}。检索源由 Agent 配置决定，
不再通过 search_scope 传参。

鉴权：Header `X-Jwt-Token`（服务账号 JWT）；可选用户身份：
X-User-Jwt / X-Lark-Union-ID / X-Lark-User-Access-Token（chat 检索飞书文档时推荐）。

凭证来源优先级：CLI 参数 > 环境变量 > --config JSON 文件。仅依赖标准库。
"""
import argparse
import json
import os
import re
import ssl
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

# 文档「BaseURL」一节（不再带 /openapi/v1 前缀）
BASE_URLS = {
    "prod": "https://tiksearch.byteintl.net",
    "notebook": "https://tika-notebook-sg.tiktok-row.org",
    "office": "https://tiksearch.tiktok-row.net",
    "cn": "https://tiksearch.byted.org",
}

API_PREFIX = "/tiktok/efficiency/api/v2/space"

ERROR_HINTS = {
    40000: "请求参数错误（必填缺失或类型错误），对照文档检查 body。",
    40100: "JWT 缺失：请求未携带 Header X-Jwt-Token。",
    40101: "JWT 解码错误：一般是过期或区域错配。",
    40102: "JWT 类型错误：误用了个人 JWT，请换成服务账号 JWT。",
    40300: "JWT 类型错误或租户权限错误，检查服务账号与 space/agent 配置。",
    40400: "资源不存在：检查 space_id / agent_id。",
    42900: "被限流，稍后重试。",
    50000: "Tika 服务端错误，稍后重试或联系 Tika 接口人。",
}

_DEFAULT_TIMEOUT = 90
_CITATION_RE = re.compile(r"\[\^\d+\]")


class TikaError(RuntimeError):
    """Tika OpenAPI 调用失败。"""


@dataclass
class TikaConfig:
    base_url: str
    space_id: str
    agent_id: str
    jwt_token: str
    user_jwt: str = ""
    lark_union_id: str = ""
    lark_user_access_token: str = ""
    user_name: str = ""
    timeout: int = _DEFAULT_TIMEOUT

    def validate(self) -> None:
        missing = [
            k
            for k in ("base_url", "space_id", "agent_id", "jwt_token")
            if not getattr(self, k)
        ]
        if missing:
            raise TikaError(
                "Tika 凭证不完整，缺少：" + ", ".join(missing) + "。\n"
                "请通过以下任一方式提供（优先级 CLI > 环境变量 > --config 文件）：\n"
                "  - 环境变量：TIKA_SPACE_ID、TIKA_AGENT_ID、TIKA_JWT_TOKEN，"
                "可选 TIKA_ENV / TIKA_BASE_URL\n"
                "  - 兼容旧变量：TIKA_TENANT_ID 会当作 space_id\n"
                "  - CLI 参数：--space-id、--agent-id、--jwt-token、--env\n"
                "  - JSON 文件：--config <path>\n"
                "X-Jwt-Token 为服务账号 JWT，获取方式见文档 JWT 接入部分。"
            )

    def base_headers(self) -> Dict[str, str]:
        return {
            "X-Jwt-Token": self.jwt_token,
            "Content-Type": "application/json",
        }

    def user_identity_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.user_jwt:
            headers["X-User-Jwt"] = self.user_jwt
        if self.lark_union_id:
            headers["X-Lark-Union-ID"] = self.lark_union_id
        if self.lark_user_access_token:
            headers["X-Lark-User-Access-Token"] = self.lark_user_access_token
        return headers

    def agent_body(self) -> Dict[str, str]:
        return {"space_id": self.space_id, "agent_id": self.agent_id}


def _resolve_base_url(env: str = "", base_url: str = "") -> str:
    if base_url:
        return base_url.rstrip("/")
    key = (env or "").strip().lower()
    if key and key in BASE_URLS:
        return BASE_URLS[key]
    if key:
        raise TikaError(f"未知 env: {env}，可选 {list(BASE_URLS)} 或显式传 base_url。")
    return BASE_URLS["office"]


JWT_HOSTS = {
    "prod": "cloud-i18n.byted.org",
    "notebook": "cloud-i18n.byted.org",
    "office": "cloud-i18n.bytedance.net",
    "cn": "cloud.bytedance.net",
}


def _default_jwt_host(env: str = "") -> str:
    return JWT_HOSTS.get((env or "").strip().lower() or "office", "cloud-i18n.bytedance.net")


def mint_jwt(sa_secret: str, jwt_host: str = "", env: str = "", timeout: int = 30) -> str:
    """用 ByteCloud IAM 服务账号 Secret 换取 X-Jwt-Token。"""
    host = (jwt_host or _default_jwt_host(env)).rstrip("/")
    url = f"https://{host}/auth/api/v1/jwt"
    req = urllib_request.Request(url, headers={"Authorization": f"Bearer {sa_secret}"}, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            token = resp.headers.get("X-Jwt-Token") or resp.headers.get("x-jwt-token")
    except urllib_error.HTTPError as exc:
        body = _decode_error_body(exc.read())
        raise TikaError(
            f"换取 X-Jwt-Token 失败：HTTP {exc.code} {body.get('error') or body.get('message') or ''}"
            f"（jwt_host={host}）。"
        ) from exc
    except urllib_error.URLError as exc:
        raise TikaError(f"换取 X-Jwt-Token 网络错误：{exc}（jwt_host={host}）") from exc
    if not token:
        raise TikaError(f"换取 X-Jwt-Token 失败：响应头无 X-Jwt-Token（jwt_host={host}）。")
    return token


def load_config(args: Optional[argparse.Namespace] = None) -> TikaConfig:
    """按 CLI 参数 > 环境变量 > --config 文件 解析凭证。"""
    file_cfg: Dict[str, object] = {}
    cfg_path = getattr(args, "config", "") if args else ""
    cfg_path = cfg_path or os.environ.get("TIKA_CONFIG", "")
    if cfg_path and os.path.isfile(os.path.expanduser(cfg_path)):
        with open(os.path.expanduser(cfg_path), "r", encoding="utf-8") as fh:
            file_cfg = json.load(fh) or {}

    def pick(arg_name: str, env_name: str, file_key: str, default: str = "") -> str:
        if args is not None:
            val = getattr(args, arg_name, "") or ""
            if val:
                return str(val)
        env_val = os.environ.get(env_name, "")
        if env_val:
            return env_val
        file_val = file_cfg.get(file_key)
        if file_val:
            return str(file_val)
        return default

    env_name = pick("env", "TIKA_ENV", "env")
    base_url = pick("base_url", "TIKA_BASE_URL", "base_url")
    resolved_base = _resolve_base_url(env_name, base_url)
    timeout = int(getattr(args, "timeout", 0) or os.environ.get("TIKA_TIMEOUT") or _DEFAULT_TIMEOUT)

    jwt_token = pick("jwt_token", "TIKA_JWT_TOKEN", "jwt_token")
    sa_secret = pick("sa_secret", "TIKA_SA_SECRET", "sa_secret")
    jwt_host = pick("jwt_host", "TIKA_JWT_HOST", "jwt_host")
    if not jwt_token and sa_secret:
        jwt_token = mint_jwt(sa_secret, jwt_host=jwt_host, env=env_name, timeout=timeout)

    space_id = pick("space_id", "TIKA_SPACE_ID", "space_id")
    if not space_id:
        space_id = pick("tenant_id", "TIKA_TENANT_ID", "tenant_id")

    user_name = pick("user_name", "TIKA_USER_NAME", "user_name")
    if not user_name:
        user_name = pick("user_email_prefix", "TIKA_USER_EMAIL_PREFIX", "user_email_prefix")

    return TikaConfig(
        base_url=resolved_base,
        space_id=space_id,
        agent_id=pick("agent_id", "TIKA_AGENT_ID", "agent_id"),
        jwt_token=jwt_token,
        user_jwt=pick("user_jwt", "TIKA_USER_JWT", "user_jwt"),
        lark_union_id=pick("lark_union_id", "TIKA_LARK_UNION_ID", "lark_union_id"),
        lark_user_access_token=pick(
            "lark_user_access_token", "TIKA_LARK_USER_ACCESS_TOKEN", "lark_user_access_token"
        ),
        user_name=user_name,
        timeout=timeout,
    )


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if os.environ.get("TIKA_INSECURE_SSL", "").lower() in ("1", "true", "yes"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _decode_error_body(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return {"message": raw.decode("utf-8", "replace")[:500]}


def _explain_error(status: int, body: dict) -> str:
    code = body.get("code")
    hint = ERROR_HINTS.get(code) or ERROR_HINTS.get(status)
    parts = [f"HTTP {status}"]
    if code is not None:
        parts.append(f"code={code}")
    msg = body.get("message")
    if msg:
        parts.append(str(msg))
    if hint:
        parts.append(f"建议：{hint}")
    return " | ".join(parts)


def _api_url(config: TikaConfig, path: str) -> str:
    return f"{config.base_url}{API_PREFIX}{path}"


def _post_json(config: TikaConfig, url: str, payload: dict, extra_headers: Optional[Dict[str, str]] = None) -> dict:
    headers = config.base_headers()
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=config.timeout, context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = _decode_error_body(exc.read())
        raise TikaError(_explain_error(exc.code, body)) from exc
    except urllib_error.URLError as exc:
        raise TikaError(f"网络错误：{exc}（base_url={config.base_url}）") from exc


def _ensure_ok(result: dict, status: int = 200) -> dict:
    if result.get("code") not in (0, None):
        raise TikaError(_explain_error(status, result))
    return result.get("data") or {}


def create_conversation(
    config: TikaConfig,
    conversation_name: str,
    user_email: str = "",
) -> str:
    config.validate()
    payload = {
        **config.agent_body(),
        "conversation_name": conversation_name or "ui-case-knowledge",
    }
    if user_email:
        payload["user_email"] = user_email
    result = _post_json(config, _api_url(config, "/conversation/create"), payload)
    data = _ensure_ok(result)
    conv_id = data.get("conversation_id")
    if conv_id is None:
        raise TikaError(f"create conversation 未返回 conversation_id: {result}")
    return str(conv_id)


def _append_references(references: List[dict], payload: object) -> None:
    if isinstance(payload, list):
        references.extend(item for item in payload if isinstance(item, dict))
    elif isinstance(payload, dict):
        references.append(payload)


def _append_text(parts: List[str], data: dict, *keys: str) -> None:
    for key in keys:
        val = data.get(key)
        if val:
            parts.append(str(val))
            return


def parse_sse_stream(lines: Iterable, strip_citations: bool = True) -> dict:
    """解析 chat 接口 SSE 事件流。

    v2 格式：data: {"event": "...", "data": {...}}
    兼容旧格式：event: xxx / data: {...}
    """
    answer_parts: List[str] = []
    thought_parts: List[str] = []
    references: List[dict] = []
    chat_id = None
    error: Optional[dict] = None
    finished = False
    interrupted = False
    current_event: Optional[str] = None

    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw
        line = line.rstrip("\n").rstrip("\r")
        if line == "":
            current_event = None
            continue
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
            continue
        if not line.startswith("data:"):
            continue

        data_str = line[len("data:") :].strip()
        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict) and "event" not in payload and "code" in payload and len(payload) <= 2:
            if payload.get("code") not in (0, None):
                error = payload
            continue

        event = payload.get("event") if isinstance(payload, dict) else None
        data = payload.get("data") if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = {}

        if not event and current_event:
            event = current_event
            data = payload if isinstance(payload, dict) else {}

        if event in ("start", "chat_start"):
            chat_id = data.get("chat_id", chat_id)
        elif event in ("references", "reference"):
            _append_references(references, data.get("references", data.get("reference", data)))
        elif event in ("llm_answer", "answer", "answer_delta", "content", "message"):
            _append_text(answer_parts, data, "content", "answer", "text", "delta", "message")
        elif event in ("llm_thought", "thought"):
            _append_text(thought_parts, data, "content", "thought")
        elif event in ("finish", "done", "end"):
            finished = True
            interrupted = bool(data.get("interrupted", False))
        elif event == "error":
            error = data or payload
        elif event == "tool_call":
            args = data.get("args")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if isinstance(args, dict):
                _append_references(references, args.get("references"))

    answer = "".join(answer_parts)
    if strip_citations and answer:
        answer = _CITATION_RE.sub("", answer)
    return {
        "chat_id": chat_id,
        "answer": answer.strip(),
        "thought": "".join(thought_parts).strip(),
        "references": references,
        "finished": finished,
        "interrupted": interrupted,
        "error": error,
    }


def chat(
    config: TikaConfig,
    conversation_id: str,
    query: str,
    strip_citations: bool = True,
) -> dict:
    config.validate()
    payload = {
        **config.agent_body(),
        "conversation_id": str(conversation_id),
        "query": query,
    }
    if config.user_name:
        payload["user_name"] = config.user_name

    headers = config.base_headers()
    headers["Accept"] = "text/event-stream"
    headers.update(config.user_identity_headers())
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        _api_url(config, "/chat/chat"),
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=config.timeout, context=_ssl_context()) as resp:
            parsed = parse_sse_stream(resp, strip_citations=strip_citations)
    except urllib_error.HTTPError as exc:
        body = _decode_error_body(exc.read())
        raise TikaError(_explain_error(exc.code, body)) from exc
    except urllib_error.URLError as exc:
        raise TikaError(f"网络错误：{exc}（base_url={config.base_url}）") from exc

    if parsed.get("error"):
        raise TikaError(_explain_error(200, parsed["error"]))
    return parsed


def get_conversation(config: TikaConfig, conversation_id: str) -> dict:
    config.validate()
    payload = {**config.agent_body(), "conversation_id": str(conversation_id)}
    return _post_json(config, _api_url(config, "/conversation/detail"), payload)


def _latest_chat_turn(detail: dict) -> dict:
    data = detail.get("data") if isinstance(detail.get("data"), dict) else detail
    history = data.get("chat_history") or []
    if not history:
        return {}
    return history[-1] if isinstance(history[-1], dict) else {}


def _enrich_from_conversation(
    config: TikaConfig,
    conversation_id: str,
    parsed: dict,
    strip_citations: bool,
) -> dict:
    """SSE 未完整返回 answer/references 时，从会话详情兜底。"""
    need_answer = not parsed.get("answer")
    need_refs = not parsed.get("references")
    if not need_answer and not need_refs:
        return parsed

    detail = get_conversation(config, conversation_id)
    turn = _latest_chat_turn(detail)
    if need_answer:
        answer = turn.get("answer", "") or ""
        if strip_citations and answer:
            answer = _CITATION_RE.sub("", answer)
        parsed["answer"] = answer.strip()
    if need_refs and turn.get("references"):
        parsed["references"] = turn.get("references", [])
    if not parsed.get("chat_id"):
        parsed["chat_id"] = turn.get("chat_id")
    return parsed


def _trim_references(references: List[dict], max_references: Optional[int], max_chars: int) -> List[dict]:
    trimmed = []
    for ref in references[: max_references or len(references)]:
        content = ref.get("content", "") or ""
        if max_chars and len(content) > max_chars:
            content = content[:max_chars] + " …(truncated)"
        trimmed.append(
            {
                "title": ref.get("title", ""),
                "url": ref.get("url", ""),
                "source": ref.get("source", ""),
                "doc_path": ref.get("doc_path", ""),
                "doc_type": ref.get("doc_type", ""),
                "refined_score": ref.get("refined_score"),
                "content": content,
            }
        )
    return trimmed


def retrieve_knowledge(
    query: str,
    config: Optional[TikaConfig] = None,
    conversation_name: str = "",
    user_email: str = "",
    max_references: Optional[int] = 8,
    max_ref_chars: int = 1500,
    strip_citations: bool = True,
) -> dict:
    """高层封装：建会话 → 发起对话(检索) → 返回结构化知识。"""
    if config is None:
        config = load_config()
    config.validate()
    conv_id = create_conversation(config, conversation_name or query[:120], user_email=user_email)
    result = chat(config, conv_id, query, strip_citations=strip_citations)
    result = _enrich_from_conversation(config, conv_id, result, strip_citations)
    refs = _trim_references(result.get("references", []), max_references, max_ref_chars)
    return {
        "query": query,
        "space_id": config.space_id,
        "agent_id": config.agent_id,
        "conversation_id": conv_id,
        "chat_id": result.get("chat_id"),
        "answer": result.get("answer", ""),
        "thought": result.get("thought", ""),
        "reference_count": len(refs),
        "references": refs,
        "interrupted": result.get("interrupted", False),
    }


def _self_check() -> None:
    sample = [
        'data: {"code": 0}',
        "",
        'data: {"event": "references", "data": {"references": [{"title": "t", "url": "u", "content": "c"}]}}',
        'data: {"event": "llm_answer", "data": {"content": "hello[^1]"}}',
        'data: {"event": "finish", "data": {"interrupted": false}}',
    ]
    parsed = parse_sse_stream(sample)
    assert parsed["answer"] == "hello", parsed
    assert parsed["references"][0]["title"] == "t", parsed
    assert parsed["finished"] is True, parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tika 自定义 Agent OpenAPI 知识检索")
    parser.add_argument("query", nargs="?", help="检索/提问内容（retrieve / chat 用）")
    parser.add_argument(
        "--command",
        choices=["retrieve", "create-conversation", "chat", "get-conversation", "self-check"],
        default="retrieve",
        help="子命令，默认 retrieve",
    )
    parser.add_argument("--conversation-id", default="", help="chat / get-conversation 用")
    parser.add_argument("--conversation-name", default="", help="会话名称，默认取 query 前 120 字")
    parser.add_argument("--user-email", default="", help="创建会话时记录的用户邮箱")
    parser.add_argument("--max-references", type=int, default=8, help="返回引用片段上限，默认 8")
    parser.add_argument("--max-ref-chars", type=int, default=1500, help="单条引用正文截断长度")
    parser.add_argument("--keep-citations", action="store_true", help="保留答案中的 [^id] 引用标记")
    # 凭证
    parser.add_argument("--env", default="", help="prod / notebook / office / cn")
    parser.add_argument("--base-url", dest="base_url", default="", help="显式 base url，覆盖 --env")
    parser.add_argument("--space-id", dest="space_id", default="", help="Tika 空间 id（即 tenant id）")
    parser.add_argument(
        "--tenant-id",
        dest="tenant_id",
        default="",
        help="已废弃，等同 --space-id",
    )
    parser.add_argument("--agent-id", dest="agent_id", default="", help="Tika Agent id")
    parser.add_argument("--jwt-token", dest="jwt_token", default="", help="服务账号 JWT（X-Jwt-Token）")
    parser.add_argument(
        "--sa-secret",
        dest="sa_secret",
        default="",
        help="ByteCloud IAM 服务账号 Secret；未传 --jwt-token 时自动换取 JWT",
    )
    parser.add_argument("--jwt-host", dest="jwt_host", default="", help="JWT 签发域名")
    parser.add_argument("--user-jwt", dest="user_jwt", default="", help="用户字节云 JWT（X-User-Jwt）")
    parser.add_argument(
        "--lark-union-id",
        dest="lark_union_id",
        default="",
        help="用户飞书 Union ID（X-Lark-Union-ID）",
    )
    parser.add_argument(
        "--lark-user-access-token",
        dest="lark_user_access_token",
        default="",
        help="飞书用户 access token（X-Lark-User-Access-Token）",
    )
    parser.add_argument(
        "--user-name",
        dest="user_name",
        default="",
        help="请求人邮箱前缀（chat body user_name）",
    )
    parser.add_argument(
        "--user-email-prefix",
        dest="user_email_prefix",
        default="",
        help="已废弃，等同 --user-name",
    )
    parser.add_argument("--config", default="", help="凭证 JSON 文件路径")
    parser.add_argument("--timeout", type=int, default=0, help="单请求超时秒数")
    parser.add_argument("--pretty", action="store_true", help="JSON 缩进输出")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "self-check":
            _self_check()
            print(json.dumps({"ok": True}, ensure_ascii=False))
            return 0

        config = load_config(args)
        if args.command == "create-conversation":
            conv_id = create_conversation(
                config, args.conversation_name or (args.query or ""), args.user_email
            )
            out = {"conversation_id": conv_id}
        elif args.command == "get-conversation":
            if not args.conversation_id:
                raise TikaError("get-conversation 需要 --conversation-id")
            out = get_conversation(config, args.conversation_id)
        elif args.command == "chat":
            if not args.conversation_id:
                raise TikaError("chat 需要 --conversation-id（或用默认的 retrieve 自动建会话）")
            if not args.query:
                raise TikaError("chat 需要 query")
            out = chat(config, args.conversation_id, args.query, strip_citations=not args.keep_citations)
        else:
            if not args.query:
                raise TikaError('retrieve 需要 query，例如：tika_knowledge.py "主播开播流程"')
            out = retrieve_knowledge(
                args.query,
                config=config,
                conversation_name=args.conversation_name,
                user_email=args.user_email,
                max_references=args.max_references,
                max_ref_chars=args.max_ref_chars,
                strip_citations=not args.keep_citations,
            )
    except TikaError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
