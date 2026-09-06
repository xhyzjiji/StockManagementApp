"""
UI 路径知识 — 加载 UI 路由表，供生成 prompt 注入。

支持两种来源：
  - 本地 data/ui_routes.txt（默认 / fallback）
  - 远程飞书文档（通过 knowledge_loader 加载后调用 reload_routes 注入）
"""
import os


def _load_ui_routes_text(path: str = None) -> str:
    if path is None:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data", "ui_routes.txt",
        )
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


_cached_routes: str = ""


def reload_routes(text: str) -> None:
    """
    Replace cached routes with new content from a remote source.

    Called by the knowledge_loader pipeline when Lark doc content
    is fetched for a specific business line.
    """
    global _cached_routes
    _cached_routes = text.strip() if text else ""


def ui_routes_prompt_context() -> str:
    """返回 UI 路由表文本，注入到生成 prompt 中。"""
    global _cached_routes
    if not _cached_routes:
        _cached_routes = _load_ui_routes_text()
    if not _cached_routes:
        return "（暂无 UI 导航路径定义）"
    return _cached_routes
