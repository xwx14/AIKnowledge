"""LangGraph 工作流节点函数定义。

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。
节点间通过 KBState 的结构化摘要通信，遵循报告式原则。
"""

import hashlib
import json
import logging
import re
import urllib.request
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from config import ARTICLES_DIR
from model_client import Usage, chat, chat_json
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

    params = urlencode({
        "q": GITHUB_QUERY,
        "sort": "updated",
        "order": "desc",
        "per_page": 20,
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
                sources.append({
                    "id": f"github_{item['id']}",
                    "source": "github",
                    "title": item.get("name", ""),
                    "description": item.get("description", ""),
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
            text, usage = chat(prompt, system_prompt)
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

    - 过滤 score < 6 的低分条目
    - 按 URL 去重
    - iteration > 0 且有 review_feedback 时，调用 LLM 定向修改摘要/标签/评分
    """
    logger.info("[OrganizeNode] 开始整理数据")

    cost = dict(state.get("cost_tracker", {}))
    items = list(state.get("analyses", []))
    iteration = state.get("iteration", 0)
    feedback = state.get("review_feedback", "")

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
                text, usage = chat(prompt, "你是一位严谨的内容审核修改专家。")
                cost = accumulate_usage(cost, usage)
                result = _parse_json_from_text(text)
                item["summary"] = result.get("summary", item.get("summary", ""))
                item["score"] = result.get("score", item.get("score", 0))
                item["tags"] = result.get("tags", item.get("tags", []))
            except Exception as e:
                logger.warning("[OrganizeNode] 修正失败 (%s): %s", item.get("id", "?"), e)
            revised.append(item)
        items = revised

    # 过滤低分条目（score < 6）
    items = [it for it in items if it.get("score", 0) >= 6]
    logger.info("[OrganizeNode] 低分过滤后剩余 %d 条", len(items))

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


def review_node(state: KBState) -> dict:
    """审核节点：LLM 四维度评分，iteration >= 2 强制通过。

    四维度：摘要质量 / 标签准确性 / 分类合理性 / 一致性。
    LLM 返回 JSON:
    {"passed": bool, "overall_score": float, "feedback": str,
     "scores": {"summary_quality": f, "tag_accuracy": f,
                "classification": f, "consistency": f}}
    overall_score >= 0.6 时 passed=True；iteration >= 2 强制通过。
    """
    logger.info("[ReviewNode] 开始审核")

    iteration = state.get("iteration", 0)

    # 防止无限循环：iteration >= 2 强制通过
    if iteration >= 2:
        logger.info("[ReviewNode] iteration=%d >= 2，强制通过", iteration)
        return {"review_passed": True, "review_feedback": "", "iteration": iteration}

    cost = dict(state.get("cost_tracker", {}))
    articles = state.get("articles", [])

    system_prompt = "你是一位严格的知识库内容审核专家，请从四个维度评分。"
    articles_summary = "\n".join(
        f"- [{a.get('id', '?')}] {a.get('title', '')} | "
        f"摘要: {a.get('summary', '')[:60]}… | 标签: {a.get('tags', [])}"
        for a in articles[:20]
    )
    prompt = (
        f"请审核以下 {len(articles)} 篇知识条目：\n{articles_summary}\n\n"
        "四维度评分（每项 0-1 分）：\n"
        "1. summary_quality — 摘要质量（是否准确、有技术深度）\n"
        "2. tag_accuracy — 标签准确性（是否贴切、无遗漏）\n"
        "3. classification — 分类合理性（标签是否覆盖主要领域）\n"
        "4. consistency — 一致性（摘要、标签、标题是否相互印证）\n\n"
        "返回 JSON：\n"
        '{"passed": bool, "overall_score": float, "feedback": str, '
        '"scores": {"summary_quality": float, "tag_accuracy": float, '
        '"classification": float, "consistency": float}}\n'
        "passed 为 true 当且仅当 overall_score >= 0.6；"
        "feedback 为改进建议，通过时留空。"
    )

    try:
        result = chat_json(prompt, system_prompt)
        passed = result.get("passed", False)
        feedback = result.get("feedback", "")
    except Exception as e:
        logger.warning("[ReviewNode] 审核失败，默认通过: %s", e)
        passed = True
        feedback = ""

    new_iteration = iteration + 1 if not passed else iteration

    logger.info(
        "[ReviewNode] 审核结果: passed=%s, iteration=%d->%d",
        passed, iteration, new_iteration,
    )
    return {
        "review_passed": passed,
        "review_feedback": feedback,
        "iteration": new_iteration,
        "cost_tracker": cost,
    }


def review_node_test(state: KBState) -> dict:
    """测试审核节点：模拟审核循环，前 2 次不通过，第 3 次通过。

    iteration=0 → passed=False, feedback="摘要过于笼统，缺少技术细节"
    iteration=1 → passed=False, feedback="标签不够精确，分类需调整"
    iteration>=2 → passed=True（模拟强制通过）
    """
    iteration = state.get("iteration", 0)

    if iteration >= 2:
        logger.info("[ReviewNodeTest] iteration=%d, review_passed=True (第3次，强制通过)", iteration)
        return {"review_passed": True, "review_feedback": "", "iteration": iteration}

    feedbacks = [
        "摘要过于笼统，缺少技术细节，请补充具体方法或数据",
        "标签不够精确，分类需调整，请使用更细粒度的技术标签",
    ]
    feedback = feedbacks[iteration] if iteration < len(feedbacks) else "质量仍需改进"
    new_iteration = iteration + 1

    logger.info("[ReviewNodeTest] iteration=%d->%d, review_passed=False", iteration, new_iteration)
    print(f"[ReviewNodeTest] iteration={iteration}, review_passed=False, feedback={feedback}")

    return {
        "review_passed": False,
        "review_feedback": feedback,
        "iteration": new_iteration,
    }


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
