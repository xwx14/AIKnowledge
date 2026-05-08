"""AI 知识条目格式化模块.

将 knowledge/articles/ 中的 JSON 知识条目转换为 Markdown、Telegram MarkdownV2
和飞书 Interactive Card 三种格式, 并支持按日期生成当日简报。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

_TELEGRAM_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"
_TELEGRAM_ESCAPE_TABLE = str.maketrans(
    {ch: f"\\{ch}" for ch in _TELEGRAM_ESCAPE_CHARS}
)


def _escape_telegram(text: str) -> str:
    """转义 Telegram MarkdownV2 特殊字符."""
    return text.translate(_TELEGRAM_ESCAPE_TABLE)


def _score_emoji(score: float) -> str:
    """根据相关性评分返回对应 emoji 指示灯."""
    if score >= 0.8:
        return "\U0001f7e2"
    if score >= 0.6:
        return "\U0001f7e1"
    return "\U0001f534"


def _score_color(score: float) -> str:
    """根据评分返回飞书卡片 header 颜色."""
    if score >= 0.8:
        return "green"
    if score >= 0.6:
        return "yellow"
    return "red"


def load_articles(knowledge_dir: str = "knowledge/articles") -> List[Dict[str, Any]]:
    """加载指定目录下所有 JSON 知识条目.

    Args:
        knowledge_dir: 包含 JSON 条目的目录路径.

    Returns:
        解析后的字典列表, 每个字典对应一篇知识条目.
    """
    dir_path = Path(knowledge_dir)
    if not dir_path.is_dir():
        return []
    articles: List[Dict[str, Any]] = []
    for json_file in sorted(dir_path.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                articles.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return articles


def json_to_markdown(article: Dict[str, Any]) -> str:
    """将单篇知识条目转换为 Markdown 格式.

    包含标题、来源、日期、相关性评分（带指示灯）、标签、摘要和原文链接.

    Args:
        article: 知识条目字典, 需包含 title/source/collected_at/score/tags/summary/url.

    Returns:
        Markdown 格式的字符串.
    """
    title = article.get("title", "无标题")
    source = article.get("source", "unknown")
    collected_at = article.get("collected_at", "")
    date_str = collected_at[:10] if collected_at else "未知日期"
    score = float(article.get("score", 0))
    tags = article.get("tags", [])
    summary = article.get("summary", "")
    url = article.get("url", "")
    emoji = _score_emoji(score)
    tags_str = ", ".join(f"`{tag}`" for tag in tags) if tags else "无标签"

    lines = [
        f"## {title}",
        f"**来源**: {source}  |  **日期**: {date_str}  |  **相关性**: {emoji} {score:.1f}",
        f"**标签**: {tags_str}",
        "",
        summary if summary else "*暂无摘要*",
        "",
        f"[原文链接]({url})" if url else "",
    ]
    return "\n".join(lines)


def json_to_telegram(article: Dict[str, Any]) -> str:
    """将单篇知识条目转换为 Telegram MarkdownV2 格式.

    自动转义特殊字符, 包含标题链接、摘要、相关性、来源和标签.

    Args:
        article: 知识条目字典.

    Returns:
        Telegram MarkdownV2 格式的字符串.
    """
    title = _escape_telegram(article.get("title", "无标题"))
    source = _escape_telegram(article.get("source", "unknown"))
    score = float(article.get("score", 0))
    emoji = _score_emoji(score)
    url = article.get("url", "")
    summary = _escape_telegram(article.get("summary", "")) or _escape_telegram("暂无摘要")
    tags = article.get("tags", [])
    tags_escaped = " ".join(f"#{_escape_telegram(t.replace(' ', '_'))}" for t in tags) if tags else ""

    lines: List[str] = []
    if url:
        lines.append(f"[{title}]({url})")
    else:
        lines.append(title)
    lines.append("")
    lines.append(summary)
    lines.append("")
    lines.append(f"{emoji} 相关性: {score:.1f}  \\| 来源: {source}")
    if tags_escaped:
        lines.append(tags_escaped)
    return "\n".join(lines)


def json_to_feishu(article: Dict[str, Any]) -> Dict[str, Any]:
    """将单篇知识条目转换为飞书 Interactive Card 字典.

    根据 score 设置 header 颜色 (green/yellow/red).

    Args:
        article: 知识条目字典.

    Returns:
        符合飞书 Interactive Card 协议的字典, 可直接序列化为 JSON 发送.
    """
    title = article.get("title", "无标题")
    source = article.get("source", "unknown")
    score = float(article.get("score", 0))
    tags = article.get("tags", [])
    summary = article.get("summary", "") or "暂无摘要"
    url = article.get("url", "")
    color = _score_color(score)

    elements: List[Dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**来源**: {source}  |  **相关性**: {score:.1f}",
            },
        }
    ]
    if tags:
        tag_str = ", ".join(f"`{t}`" for t in tags)
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**标签**: {tag_str}"},
            }
        )
    elements.append(
        {"tag": "div", "text": {"tag": "lark_md", "content": summary}}
    )
    if url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看原文"},
                        "type": "primary",
                        "url": url,
                    }
                ],
            }
        )

    card: Dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        },
    }
    return card


def generate_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    target_date: date | None = None,
    top_n: int = 5,
) -> Dict[str, str]:
    """生成当日知识简报, 包含 Markdown、Telegram、飞书三种格式.

    按文章的 collected_at 日期筛选, 再按 relevance_score 降序取 Top N.
    当日无文章时返回 "📭 {date} 暂无新增知识条目".

    Args:
        knowledge_dir: 知识条目目录路径.
        target_date: 目标日期, 默认今天.
        top_n: 返回的 Top N 篇文章数.

    Returns:
        包含 "markdown", "telegram", "feishu" 三个键的字典, 值为对应格式的字符串.
        飞书格式为 JSON 序列化后的字符串.
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()

    dir_path = Path(knowledge_dir)
    if not dir_path.is_dir():
        empty_msg = f"\U0001f4ed {date_str} 暂无新增知识条目"
        return {"markdown": empty_msg, "telegram": empty_msg, "feishu": empty_msg}

    matched: List[Dict[str, Any]] = []
    for json_file in dir_path.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        article = data
        collected_at = article.get("collected_at", "")
        if collected_at and collected_at[:10] == date_str:
            matched.append(article)

    matched.sort(key=lambda a: float(a.get("score", 0)), reverse=True)
    top_articles = matched[:top_n]

    if not top_articles:
        empty_msg = f"\U0001f4ed {date_str} 暂无新增知识条目"
        return {"markdown": empty_msg, "telegram": empty_msg, "feishu": empty_msg}

    md_header = f"# AI 知识简报 - {date_str}\n\n共 {len(matched)} 篇, 以下为 Top {len(top_articles)}:\n\n---\n\n"
    md_body = "\n\n---\n\n".join(json_to_markdown(a) for a in top_articles)
    markdown = md_header + md_body

    tg_header = f"\U0001f4f0 *AI 知识简报\\- {date_str}*\n\n共 _{len(matched)}_ 篇\\, 以下为 Top _{len(top_articles)}_:\n\n"
    tg_body = "\n\n".join(json_to_telegram(a) for a in top_articles)
    telegram = tg_header + tg_body

    import json as _json

    feishu_elements: List[Dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"共 {len(matched)} 篇, 以下为 Top {len(top_articles)}",
            },
        },
        {"tag": "hr"},
    ]
    for article in top_articles:
        title = article.get("title", "无标题")
        score = float(article.get("score", 0))
        source = article.get("source", "unknown")
        tags = article.get("tags", [])
        summary = article.get("summary", "") or "暂无摘要"
        url = article.get("url", "")
        emoji = _score_emoji(score)
        tag_str = ", ".join(f"`{t}`" for t in tags) if tags else ""

        feishu_elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**{title}**"}}
        )
        feishu_elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{emoji} 相关性: {score:.1f}  |  来源: {source}",
                },
            }
        )
        if tag_str:
            feishu_elements.append(
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"标签: {tag_str}"},
                }
            )
        feishu_elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": summary[:200]},
            }
        )
        if url:
            feishu_elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看原文"},
                            "type": "primary",
                            "url": url,
                        }
                    ],
                }
            )
        feishu_elements.append({"tag": "hr"})

    feishu_digest_card: Dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"AI 知识简报 - {date_str}",
                },
                "template": "blue",
            },
            "elements": feishu_elements,
        },
    }
    feishu = _json.dumps(feishu_digest_card, ensure_ascii=False, indent=2)

    return {"markdown": markdown, "telegram": telegram, "feishu": feishu}
