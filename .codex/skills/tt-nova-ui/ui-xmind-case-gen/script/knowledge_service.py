"""
知识库检索客户端 —— 从 volcengine 知识库召回 Bug 文档。
"""
import json
import requests


_KNOWLEDGE_BASE_DOMAIN = "api-knowledgebase.mlp.cn-beijing.volces.com"
_API_KEY = "a3bb4a57-0249-42d8-a3d3-37316f860e22"
_SERVICE_RESOURCE_ID = "kb-service-1b76ddaabd9ac0a8"


def knowledge_service_chat(query: str) -> dict:
    """
    查询知识库，返回 {content, references, result_count, raw}。
    content 是多条 Bug 内容用 --- 分隔的文本。
    """
    path = "/api/knowledge/service/chat"
    request_params = {
        "service_resource_id": _SERVICE_RESOURCE_ID,
        "messages": [
            {
                "role": "user",
                "content": query,
            }
        ],
        "stream": False,
        "query_param": {
            "doc_filter": {
                "op": "and",
                "conds": [
                    {
                        "op": "must",
                        "field": "biz_line",
                        "conds": ["MobileGaming"],
                    },
                    {
                        "op": "must",
                        "field": "domain",
                        "conds": ["Bug"],
                    },
                ],
            }
        },
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "Host": _KNOWLEDGE_BASE_DOMAIN,
        "Authorization": f"Bearer {_API_KEY}",
    }

    rsp = requests.request(
        method="POST",
        url=f"http://{_KNOWLEDGE_BASE_DOMAIN}{path}",
        headers=headers,
        data=json.dumps(request_params),
        timeout=20,
    )
    rsp.encoding = "utf-8"

    try:
        data = rsp.json()
        result_list = data.get("data", {}).get("result_list", [])
        chunks = [item.get("content", "") for item in result_list if item.get("content")]
        content = "\n\n---\n".join(chunks)
        references = data.get("data", {}).get("references", [])
        return {"content": content, "references": references, "result_count": len(result_list), "raw": data}
    except Exception:
        return {"content": rsp.text, "references": [], "result_count": 0, "raw": None}
