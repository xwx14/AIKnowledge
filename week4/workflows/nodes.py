"""LangGraph 工作流节点函数定义。

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。
节点间通过 KBState 的结构化摘要通信，遵循报告式原则。
"""

import hashlib
import json
import logging
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from security import sanitize_input, secure_output

from config import ARTICLES_DIR
from model_client import Usage, chat
from state import KBState

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_QUERY = "AI OR artificial intelligence OR machine learning language:en"

_ILLEGAL_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_filename(title: str) -> str:
    name = title.strip()
    name = _ILLEGAL_FILENAME_RE.sub("_", name)
    name = re.sub(r"[\s_]+", "_", name)
    name = name.strip("_")
    if not name:
        name = "untitled"
    if len(name) > 80:
        name = name[:80].rstrip("_")
    return name


def _parse_json_from_text(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"无法从 LLM 响应中解析 JSON: {text[:200]}")


def accumulate_usage(tracker: dict, usage: Usage) -> dict:
    """累加 token 统计到 cost_tracker 字典。

    Args:
        tracker: 当前 cost_tracker 状态字典。
        usage: 本次 LLM 调用的 Usage 对象。

    Returns:
        更新后的 cost_tracker 字典（新对象，不修改原字典）。
    """
    return {
        "total_tokens": tracker.get("total_tokens", 0) + usage.total_tokens,
        "prompt_tokens": tracker.get("prompt_tokens", 0) + usage.prompt_tokens,
        "completion_tokens": tracker.get("completion_tokens", 0) + usage.completion_tokens,
        "total_cost_rmb": tracker.get("total_cost_rmb", 0.0),
        "calls": tracker.get("calls", 0) + 1,
    }


def collect_node(state: KBState) -> dict:
    """采集节点：调用 GitHub Search API 采集 AI 相关仓库。

    使用 urllib.request 访问 GitHub Search API，
    查询 AI/ML 相关仓库并按更新时间倒序排列，
    结果写入 state.sources。
    """
    logger.info("[CollectNode] 开始采集 GitHub 数据")

    plan = state.get("plan", {}) or {}
    per_source_limit = int(plan.get("per_source_limit", 10))

    params = urlencode({
        "q": GITHUB_QUERY,
        "sort": "updated",
        "order": "desc",
        "per_page": per_source_limit,
    })
    url = f"{GITHUB_SEARCH_URL}?{params}"

    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Knowledge-Pipeline",
    })

    sources: list[dict] = []
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("items", []):
                raw_title = item.get("name", "")
                raw_desc = item.get("description", "") or ""
                clean_title, t_warn = sanitize_input(raw_title)
                clean_desc, d_warn = sanitize_input(raw_desc)
                if t_warn or d_warn:
                    logger.warning("[CollectNode] 采集条目注入检测: id=%s, warnings=%s", item.get("id"), t_warn + d_warn)
                sources.append({
                    "id": f"github_{item['id']}",
                    "source": "github",
                    "title": clean_title,
                    "description": clean_desc,
                    "url": item.get("html_url", ""),
                    "updated_at": item.get("updated_at", ""),
                    "stars": item.get("stargazers_count", 0),
                    "collected_at": datetime.utcnow().isoformat(),
                })
    except Exception as e:
        logger.error("[CollectNode] GitHub 采集失败: %s", e)

    logger.info("[CollectNode] 采集完成，共 %d 条", len(sources))
    return {"sources": sources}


def analyze_node(state: KBState) -> dict:
    """分析节点：用 LLM 对每条数据生成中文摘要、标签、评分。

    遍历 sources 中每条记录，调用 chat() 获取 LLM 分析结果，
    合并原始字段后写入 analyses，同时更新 cost_tracker。
    """
    logger.info("[AnalyzeNode] 开始分析 %d 条数据", len(state.get("sources", [])))

    cost = dict(state.get("cost_tracker", {}))
    analyses: list[dict] = []
    system_prompt = (
        "你是一位 AI 技术分析专家。请对以下内容生成：\n"
        "1. 中文摘要（至少 20 字，突出技术要点）\n"
        "2. 质量评分（1-10 整数，10 为最佳）\n"
        "3. 技术标签列表（3-5 个）\n"
        '严格以 JSON 格式返回：{"summary": str, "score": int, "tags": [str]}'
    )

    for item in state.get("sources", []):
        prompt = (
            f"标题：{item.get('title', '')}\n"
            f"描述：{item.get('description', '')}\n"
            f"来源：{item.get('url', '')}"
        )
        try:
            text, usage = chat(prompt, system_prompt, node_name="analyze")
            cost = accumulate_usage(cost, usage)
            result = _parse_json_from_text(text)
        except Exception as e:
            logger.warning("[AnalyzeNode] 分析失败 (%s): %s", item.get("id", "?"), e)
            result = {
                "summary": (item.get("description") or "")[:100] or "暂无摘要",
                "score": 5,
                "tags": ["ai"],
            }

        merged = {**item}
        merged["summary"] = result.get("summary", "")
        merged["score"] = result.get("score", 5)
        merged["tags"] = result.get("tags", [])
        merged["analyzed"] = True
        analyses.append(merged)

    logger.info("[AnalyzeNode] 分析完成，共 %d 条", len(analyses))
    return {"analyses": analyses, "cost_tracker": cost}


def organize_node(state: KBState) -> dict:
    """整理节点：过滤低分、URL 去重，有审核反馈时调用 LLM 修正。

    - 过滤低于 plan.relevance_threshold 对应分数的低分条目
    - 按 URL 去重
    - iteration > 0 且有 review_feedback 时，调用 LLM 定向修改摘要/标签/评分
    """
    logger.info("[OrganizeNode] 开始整理数据")

    cost = dict(state.get("cost_tracker", {}))
    items = list(state.get("analyses", []))
    iteration = state.get("iteration", 0)
    feedback = state.get("review_feedback", "")

    plan = state.get("plan", {}) or {}
    relevance_threshold = float(plan.get("relevance_threshold", 0.5))
    score_threshold = int(relevance_threshold * 10)

    # 审核修正轮次：根据反馈用 LLM 定向修改
    if iteration > 0 and feedback:
        logger.info("[OrganizeNode] 审核修正轮次 (iteration=%d)", iteration)
        revised: list[dict] = []
        for item in items:
            prompt = (
                f"审核反馈：{feedback}\n\n"
                "请根据反馈改进以下内容的摘要和标签，"
                '返回改进后的 JSON：{"summary": str, "score": int, "tags": [str]}\n\n'
                f"标题：{item.get('title', '')}\n"
                f"当前摘要：{item.get('summary', '')}\n"
                f"当前标签：{item.get('tags', [])}\n"
                f"当前评分：{item.get('score', 0)}"
            )
            try:
                text, usage = chat(prompt, "你是一位严谨的内容审核修改专家。", node_name="organize")
                cost = accumulate_usage(cost, usage)
                result = _parse_json_from_text(text)
                item["summary"] = result.get("summary", item.get("summary", ""))
                item["score"] = result.get("score", item.get("score", 0))
                item["tags"] = result.get("tags", item.get("tags", []))
            except Exception as e:
                logger.warning("[OrganizeNode] 修正失败 (%s): %s", item.get("id", "?"), e)
            revised.append(item)
        items = revised

    # 过滤低分条目（score < relevance_threshold * 10）
    items = [it for it in items if it.get("score", 0) >= score_threshold]
    logger.info("[OrganizeNode] 低分过滤后剩余 %d 条 (threshold=%.1f, score>=%d)", len(items), relevance_threshold, score_threshold)

    # PII 过滤：对摘要脱敏
    for item in items:
        raw_summary = item.get("summary", "")
        if raw_summary:
            filtered_summary, pii_detections = secure_output(raw_summary, "organize")
            if pii_detections:
                logger.warning("[OrganizeNode] PII 检测: id=%s, detections=%d", item.get("id"), len(pii_detections))
            item["summary"] = filtered_summary

    # URL 去重
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for item in items:
        url = item.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        deduped.append(item)

    logger.info("[OrganizeNode] 整理完成，共 %d 条", len(deduped))
    return {"articles": deduped, "cost_tracker": cost}


def save_node(state: KBState) -> dict:
    """保存节点：将 articles 写入 knowledge/articles/ 目录，更新 index.json。

    每篇文章保存为独立 JSON 文件（标题清洗为文件名），
    同时维护 index.json 索引，记录 id/title/url/tags/score。
    """
    logger.info("[SaveNode] 开始保存 %d 篇文章", len(state.get("articles", [])))

    articles = state.get("articles", [])
    used_names: dict[str, str] = {}

    for item in articles:
        title = (item.get("title") or "").strip()
        base_name = _sanitize_filename(title) if title else ""
        url = item.get("url", "")

        # 标题为空时用 id 或 url 哈希兜底
        if not base_name or base_name == "untitled":
            article_id = item.get("id", "")
            if not article_id:
                article_id = hashlib.md5(url.encode()).hexdigest()[:12]
            base_name = article_id

        # 同名冲突处理：同名同 URL 覆盖，同名不同 URL 追加数字后缀
        if base_name in used_names:
            if used_names[base_name] != url:
                counter = 2
                final_name = base_name
                while final_name in used_names and used_names[final_name] != url:
                    final_name = f"{base_name}_{counter}"
                    counter += 1
                base_name = final_name

        used_names[base_name] = url

        # 写入单篇文章 JSON
        article_file = ARTICLES_DIR / f"{base_name}.json"
        if article_file.exists():
            article_file.unlink()
        with open(article_file, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)

    # 更新 index.json 索引
    index_path = ARTICLES_DIR / "index.json"
    index: list[dict] = []
    if index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        except (json.JSONDecodeError, OSError):
            index = []

    existing_ids = {entry.get("id") for entry in index}
    for item in articles:
        if item.get("id") not in existing_ids:
            index.append({
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "tags": item.get("tags", []),
                "score": item.get("score", 0),
            })

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    logger.info("[SaveNode] 保存完成，共 %d 篇，索引 %d 条", len(articles), len(index))
    return {"articles": articles}
