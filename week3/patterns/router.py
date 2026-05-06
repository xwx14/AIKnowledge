"""Router pattern: two-layer intent classification with dedicated handlers.

Layer 1 — keyword fast-match (zero cost, no LLM call)
Layer 2 — LLM classification fallback (handles ambiguous intents)

Three intents: github_search / knowledge_query / general_chat
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parent.parent / "workflows"))
from model_client import chat, chat_json

logger = logging.getLogger(__name__)

INTENTS = ("github_search", "knowledge_query", "general_chat")

KEYWORD_RULES: dict[str, list[str]] = {
    "github_search": [
        "github", "repo", "repository", "开源项目", "代码仓库",
        "搜索项目", "find repo", "search repo", "search github",
        "开源仓库", "框架", "工具库", "sdk", "库推荐",
        "找项目", "搜项目",
    ],
    "knowledge_query": [
        "知识库", "本地文章", "已有文章", "knowledge",
        "之前采集", "本地资料", "已收录", "已保存",
        "本地知识", "文章库",
    ],
}

CLASSIFY_PROMPT = """\
你是一个意图分类器。根据用户查询，将其分类为以下三种意图之一：

- github_search：用户想搜索 GitHub 上的开源项目/仓库
- knowledge_query：用户想查询本地知识库中已有的文章/资料
- general_chat：普通对话，不属于以上两类

只返回意图名称（github_search / knowledge_query / general_chat），不要返回其他内容。

用户查询：{query}"""


def _keyword_classify(query: str) -> str | None:
    q = query.lower()
    for intent, keywords in KEYWORD_RULES.items():
        for kw in keywords:
            if kw in q:
                return intent
    return None


def _llm_classify(query: str) -> str:
    prompt = CLASSIFY_PROMPT.format(query=query)
    text, _ = chat(prompt, system_prompt="你是一个意图分类器，只返回意图名称。")
    text = text.strip().lower()
    for intent in INTENTS:
        if intent in text:
            return intent
    return "general_chat"


CN_TO_EN = {
    "框架": "framework",
    "工具库": "toolkit library",
    "开源仓库": "open source",
    "开源项目": "open source",
    "代码仓库": "open source",
    "机器学习": "machine learning",
    "深度学习": "deep learning",
    "人工智能": "artificial intelligence AI",
    "自然语言处理": "NLP natural language processing",
    "计算机视觉": "computer vision CV",
    "大模型": "LLM large language model",
    "大语言模型": "LLM large language model",
}


def _extract_github_query(query: str) -> str:
    chinese_stops = {"搜索", "帮我", "找", "搜", "一下", "最近", "最新", "一些", "关于", "有没有", "的"}
    text = query
    for cn, en in CN_TO_EN.items():
        text = text.replace(cn, f" {en} ")
    tokens = text.split()
    keep: list[str] = []
    for t in tokens:
        if t in chinese_stops:
            continue
        stripped = t
        for s in chinese_stops:
            stripped = stripped.replace(s, "")
        if stripped:
            keep.append(stripped)
    return " ".join(keep) if keep else query


def handle_github_search(query: str) -> str:
    search_query = _extract_github_query(query)
    params = urlencode({
        "q": search_query,
        "sort": "updated",
        "order": "desc",
        "per_page": 5,
    })
    url = f"https://api.github.com/search/repositories?{params}"

    req = Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "AI-Knowledge-Router")

    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        req.add_header("Authorization", f"token {github_token}")

    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error("GitHub Search API failed: %s", e)
        return f"GitHub 搜索失败：{e}"

    items = data.get("items", [])[:5]
    if not items:
        return "未找到相关 GitHub 项目。"

    lines = [f"GitHub 搜索结果（共 {data.get('total_count', 0)} 个）："]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item.get('full_name', '')}")
        lines.append(f"   {item.get('description') or '无描述'}")
        lines.append(f"   Stars: {item.get('stargazers_count', 0)} | {item.get('html_url', '')}")
        lines.append("")

    return "\n".join(lines)


_articles_cache: list[dict[str, Any]] | None = None

ARTICLES_DIR = Path(__file__).parent.parent / "knowledge" / "articles"


def _load_articles_index() -> list[dict[str, Any]]:
    global _articles_cache
    if _articles_cache is not None:
        return _articles_cache

    index_path = ARTICLES_DIR / "index.json"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            _articles_cache = json.load(f)
            return _articles_cache

    articles: list[dict[str, Any]] = []
    for fp in ARTICLES_DIR.glob("*.json"):
        if fp.name == "index.json":
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                articles.append(json.load(f))
        except Exception:
            continue

    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        logger.info("Built articles index: %d entries -> %s", len(articles), index_path)
    except Exception as e:
        logger.warning("Failed to save index.json: %s", e)

    _articles_cache = articles
    return _articles_cache


def handle_knowledge_query(query: str) -> str:
    articles = _load_articles_index()
    if not articles:
        return "知识库中暂无文章。"

    q_lower = query.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for art in articles:
        text = " ".join([
            art.get("title", ""),
            art.get("summary", ""),
            art.get("description", ""),
            " ".join(art.get("tags", [])),
        ]).lower()
        score = sum(1 for word in q_lower.split() if word in text)
        if score > 0:
            scored.append((score, art))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:5]

    if not top:
        return "未在知识库中找到相关文章。"

    lines = [f"知识库搜索结果（共命中 {len(scored)} 篇）："]
    for i, (score, art) in enumerate(top, 1):
        lines.append(f"{i}. [{art.get('id', '')}] {art.get('title', '无标题')}")
        summary = art.get("summary", "")
        if summary:
            lines.append(f"   摘要：{summary[:100]}")
        tags = art.get("tags", [])
        if tags:
            lines.append(f"   标签：{', '.join(tags)}")
        lines.append(f"   链接：{art.get('url', '')}")
        lines.append("")

    return "\n".join(lines)


def handle_general_chat(query: str) -> str:
    text, _ = chat(query, system_prompt="你是一个AI助手，请用中文简洁回答。")
    return text


HANDLERS: dict[str, object] = {
    "github_search": handle_github_search,
    "knowledge_query": handle_knowledge_query,
    "general_chat": handle_general_chat,
}


def route(query: str) -> str:
    intent = _keyword_classify(query)
    if intent:
        logger.info("关键词匹配意图：%s", intent)
    else:
        logger.info("关键词未匹配，调用 LLM 分类...")
        intent = _llm_classify(query)
        logger.info("LLM 分类意图：%s", intent)

    handler = HANDLERS[intent]
    return handler(query)


def classify(query: str) -> str:
    intent = _keyword_classify(query)
    if intent:
        return intent
    return _llm_classify(query)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Router 意图分类测试")
    parser.add_argument("query", nargs="*", help="要分类的查询文本")
    parser.add_argument("--demo", action="store_true", help="运行内置示例")
    parser.add_argument("--classify-only", action="store_true", help="仅输出意图分类，不执行处理")
    args = parser.parse_args()

    if args.demo or not args.query:
        test_queries = [
            "帮我搜一下 GitHub 上关于 LLM 的项目",
            "知识库里有没有关于 RAG 的文章",
            "今天天气怎么样",
            "找一些机器学习的开源仓库",
            "本地已收录的 Transformer 文章有哪些",
            "Python 和 Go 哪个更适合后端开发",
            "搜索最近的 AI Agent 框架",
        ]
        for q in test_queries:
            intent = classify(q)
            layer = "keyword" if _keyword_classify(q) else "LLM"
            print(f"[{layer:>7}] {q} -> {intent}")
    else:
        query = " ".join(args.query)
        intent = classify(query)
        layer = "keyword" if _keyword_classify(query) else "LLM"
        if args.classify_only:
            print(f"[{layer:>7}] {query} -> {intent}")
        else:
            print(f"[{layer:>7}] 意图：{intent}")
            print("-" * 60)
            print(route(query))
