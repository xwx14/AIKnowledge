#!/usr/bin/env python3
"""MCP Knowledge Server - 让 AI 工具可以搜索本地知识库。

协议：JSON-RPC 2.0 over stdio
方法：initialize / tools/list / tools/call
无第三方依赖，仅使用 Python 标准库。
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ARTICLES_DIR = Path(__file__).parent.parent / "knowledge" / "articles"

TOOLS = [
    {
        "name": "search_articles",
        "description": "按关键词搜索知识库文章（搜索标题、摘要、描述）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认5",
                    "default": 5,
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_article",
        "description": "按文章 ID 获取完整内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章 ID，如 github_1226519344 或 rss_233589e8b85d",
                },
            },
            "required": ["article_id"],
        },
    },
    {
        "name": "knowledge_stats",
        "description": "获取知识库统计信息（文章总数、来源分布、热门标签）",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def load_all_articles() -> list[dict[str, Any]]:
    """加载 knowledge/articles/ 目录下所有 JSON 文件。"""
    articles: list[dict[str, Any]] = []
    if not ARTICLES_DIR.exists():
        return articles
    for path in sorted(ARTICLES_DIR.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                articles.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] skip {path.name}: {e}", file=sys.stderr)
    return articles


def tool_search_articles(arguments: dict[str, Any]) -> dict[str, Any]:
    """按关键词搜索文章标题、摘要、描述。"""
    keyword = arguments.get("keyword", "").lower()
    limit = arguments.get("limit", 5)
    articles = load_all_articles()

    results: list[dict[str, Any]] = []
    for a in articles:
        title = (a.get("title") or "").lower()
        summary = (a.get("summary") or "").lower()
        description = (a.get("description") or "").lower()
        if keyword in title or keyword in summary or keyword in description:
            results.append(a)
            if len(results) >= limit:
                break

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(results, ensure_ascii=False, indent=2),
            }
        ]
    }


def tool_get_article(arguments: dict[str, Any]) -> dict[str, Any]:
    """按 ID 获取文章完整内容。"""
    article_id = arguments.get("article_id", "")
    for path in ARTICLES_DIR.glob("*.json"):
        if path.stem == article_id:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    article = json.load(f)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(article, ensure_ascii=False, indent=2),
                        }
                    ]
                }
            except (json.JSONDecodeError, OSError) as e:
                return {
                    "content": [{"type": "text", "text": f"读取文件失败: {e}"}],
                    "isError": True,
                }

    return {
        "content": [{"type": "text", "text": f"未找到文章: {article_id}"}],
        "isError": True,
    }


def tool_knowledge_stats(arguments: dict[str, Any]) -> dict[str, Any]:
    """返回知识库统计信息。"""
    articles = load_all_articles()

    source_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    analyzed_count = 0

    for a in articles:
        source = a.get("source") or "unknown"
        source_counter[source] += 1
        if a.get("analyzed"):
            analyzed_count += 1
        for tag in a.get("tags") or []:
            tag_counter[tag] += 1

    top_tags = [
        {"tag": t, "count": c}
        for t, c in tag_counter.most_common(20)
    ]

    stats = {
        "total_articles": len(articles),
        "analyzed_articles": analyzed_count,
        "source_distribution": dict(source_counter),
        "top_tags": top_tags,
    }

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(stats, ensure_ascii=False, indent=2),
            }
        ]
    }


TOOL_HANDLERS = {
    "search_articles": tool_search_articles,
    "get_article": tool_get_article,
    "knowledge_stats": tool_knowledge_stats,
}


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """处理单个 JSON-RPC 请求，返回响应（通知类返回 None）。"""
    method = request.get("method", "")
    params = request.get("params") or {}
    req_id = request.get("id")

    # 通知类消息，无需响应
    if method == "notifications/initialized":
        return None

    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "knowledge-server",
                "version": "1.0.0",
            },
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        tool_name = params.get("name", "")
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            result = {
                "content": [{"type": "text", "text": f"未知工具: {tool_name}"}],
                "isError": True,
            }
        else:
            result = handler(params.get("arguments") or {})
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }

    if req_id is not None:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    return None


def main() -> None:
    """主循环：从 stdin 逐行读取 JSON-RPC 请求。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        try:
            response = handle_request(request)
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": f"Internal error: {e}"},
            }

        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
