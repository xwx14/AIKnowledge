"""LangGraph 工作流节点函数定义。

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。
节点间通过 KBState 的结构化摘要通信，遵循报告式原则。
"""

import asyncio
import hashlib
import json
import logging
import re
import urllib.request
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from config import ARTICLES_DIR
from model_client import Usage, chat, chat_json, chat_with_retry
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


_REVIEW_WEIGHTS = {
    "summary_quality": 0.25,
    "technical_depth": 0.25,
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15,
}
_PASS_THRESHOLD = 7.0


def review_node(state: KBState) -> dict:
    """审核节点：LLM 五维度加权评分（1-10），iteration >= 2 强制通过。

    审核对象为 state["analyses"]，仅前 5 条（控 token）。
    五维度与权重：
      - summary_quality (25%): 摘要质量（准确性、简洁性、洞察深度）
      - technical_depth (25%): 技术深度（方法/数据/实验是否充实）
      - relevance (20%): 相关性（与 AI 知识库主题的契合度）
      - originality (15%): 原创性（是否有独到见解或新颖角度）
      - formatting (15%): 格式规范（字段完整、标签合规、摘要长度）
    加权总分由代码重算，不信任模型算术，>= 7.0 为通过。
    temperature=0.1 保证评分一致性。
    """
    logger.info("[ReviewNode] 开始审核")

    iteration = state.get("iteration", 0)

    if iteration >= 2:
        logger.info("[ReviewNode] iteration=%d >= 2，强制通过", iteration)
        return {"review_passed": True, "review_feedback": "", "iteration": iteration}

    cost = dict(state.get("cost_tracker", {}))
    analyses = state.get("analyses", [])
    batch = analyses[:5]

    if not batch:
        logger.info("[ReviewNode] analyses 为空，直接通过")
        return {"review_passed": True, "review_feedback": "", "iteration": iteration}

    system_prompt = "你是一位严格的知识库内容审核专家，请对每条内容逐维度评分（1-10 整数）。"

    items_summary = "\n".join(
        f"- [{a.get('id', '?')}] {a.get('title', '')} | "
        f"摘要: {a.get('summary', '')[:80]}… | 标签: {a.get('tags', [])}"
        for a in batch
    )
    prompt = (
        f"请审核以下 {len(batch)} 条知识条目：\n{items_summary}\n\n"
        "五维度评分（每项 1-10 整数分）：\n"
        "1. summary_quality — 摘要质量（准确性、简洁性、洞察深度）\n"
        "2. technical_depth — 技术深度（方法/数据/实验是否充实）\n"
        "3. relevance — 相关性（与 AI 知识库主题的契合度）\n"
        "4. originality — 原创性（是否有独到见解或新颖角度）\n"
        "5. formatting — 格式规范（字段完整、标签合规、摘要长度）\n\n"
        "严格返回 JSON：\n"
        '{"scores": {"summary_quality": int, "technical_depth": int, '
        '"relevance": int, "originality": int, "formatting": int}, '
        '"feedback": str}\n'
        "feedback 为改进建议，全部达标时留空字符串。"
    )

    try:
        result, usage = chat_json(prompt, system_prompt, temperature=0.1)
        cost = accumulate_usage(cost, usage)

        scores = result.get("scores", {})
        weighted_total = sum(
            scores.get(dim, 0) * weight
            for dim, weight in _REVIEW_WEIGHTS.items()
        )
        passed = weighted_total >= _PASS_THRESHOLD
        feedback = result.get("feedback", "")

        logger.info(
            "[ReviewNode] 评分: summary=%s, depth=%s, relevance=%s, "
            "originality=%s, formatting=%s, weighted=%.2f",
            scores.get("summary_quality"), scores.get("technical_depth"),
            scores.get("relevance"), scores.get("originality"),
            scores.get("formatting"), weighted_total,
        )
    except Exception as e:
        logger.warning("[ReviewNode] 审核失败，默认通过: %s", e)
        passed = True
        feedback = ""
        weighted_total = -1.0

    new_iteration = iteration + 1 if not passed else iteration

    logger.info(
        "[ReviewNode] 审核结果: passed=%s, weighted=%.2f, iteration=%d->%d",
        passed, weighted_total, iteration, new_iteration,
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


_DIMENSION_KEYWORDS = {
    "summary_quality": ["摘要", "摘要质量", "准确性", "简洁性", "洞察"],
    "tag_accuracy": ["标签", "标签准确", "贴切", "遗漏"],
    "category_correctness": ["分类", "分类合理", "类别", "领域覆盖"],
    "consistency": ["一致性", "印证", "矛盾", "不匹配"],
}

_DIMENSION_LABELS = {
    "summary_quality": "摘要质量（准确性、简洁性、洞察深度）",
    "tag_accuracy": "标签准确性（是否贴切、无遗漏）",
    "category_correctness": "分类合理性（标签是否覆盖主要领域）",
    "consistency": "整体一致性（摘要、标签、标题是否相互印证）",
}

_WEAK_THRESHOLD = 3


def _extract_weak_dimensions(feedback: str, scores: dict) -> list[str]:
    """从审核反馈和评分中提取弱项维度。

    优先从 scores 中筛选 < WEAK_THRESHOLD 的维度，
    再从 feedback 文本中匹配维度关键词，合并去重返回。
    """
    weak: list[str] = []

    for dim, score in scores.items():
        if isinstance(score, (int, float)) and score < _WEAK_THRESHOLD:
            weak.append(dim)

    for dim, label in _DIMENSION_LABELS.items():
        if dim not in weak:
            for keyword in label.split("（")[0].split("、"):
                if keyword in feedback:
                    weak.append(dim)
                    break

    for dim, keywords in _DIMENSION_KEYWORDS.items():
        if dim not in weak:
            for kw in keywords:
                if kw in feedback:
                    weak.append(dim)
                    break

    return weak


def revise_node(state: KBState) -> dict:
    """修订节点：根据审核反馈中弱项维度，逐条调用 LLM 改写摘要/标签。

    读取 state['review_feedback'] 和 review_node 写入的评分，
    提取弱项维度注入修改 prompt，temperature=0.4 允许创造性改写。
    返回修订后的 articles 和更新后的 cost_tracker。
    """
    logger.info("[ReviseNode] 开始修订")

    cost = dict(state.get("cost_tracker", {}))
    feedback = state.get("review_feedback", "")

    if not feedback:
        logger.info("[ReviseNode] 无审核反馈，跳过修订")
        return {"articles": state.get("articles", []), "cost_tracker": cost}

    articles = list(state.get("articles", []))

    scores = {}
    for line in feedback.split("\n"):
        for dim in _DIMENSION_LABELS:
            if dim in line:
                import re as _re
                m = _re.search(r"(\d+)", line)
                if m:
                    scores[dim] = int(m.group(1))

    weak_dims = _extract_weak_dimensions(feedback, scores)
    if not weak_dims:
        weak_dims = list(_DIMENSION_LABELS.keys())

    weak_desc = "\n".join(
        f"- {dim}：{_DIMENSION_LABELS.get(dim, dim)}"
        for dim in weak_dims
    )

    logger.info("[ReviseNode] 弱项维度: %s", weak_dims)

    revised: list[dict] = []
    for item in articles:
        prompt = (
            f"审核反馈：{feedback}\n\n"
            f"需要重点改进的维度：\n{weak_desc}\n\n"
            "请针对以上弱项改写以下内容，"
            '返回改进后的 JSON：{"summary": str, "score": int, "tags": [str]}\n\n'
            f"标题：{item.get('title', '')}\n"
            f"当前摘要：{item.get('summary', '')}\n"
            f"当前标签：{item.get('tags', [])}\n"
            f"当前评分：{item.get('score', 0)}"
        )
        try:
            messages = [
                {"role": "system", "content": "你是一位严谨的内容修订专家，擅长针对审核弱项定向改进。"},
                {"role": "user", "content": prompt},
            ]
            response = asyncio.run(chat_with_retry(messages, temperature=0.4))
            cost = accumulate_usage(cost, response.usage)
            result = _parse_json_from_text(response.content)
            item["summary"] = result.get("summary", item.get("summary", ""))
            item["score"] = result.get("score", item.get("score", 0))
            item["tags"] = result.get("tags", item.get("tags", []))
        except Exception as e:
            logger.warning("[ReviseNode] 修订失败 (%s): %s", item.get("id", "?"), e)

        revised.append(item)

    logger.info("[ReviseNode] 修订完成，共 %d 条", len(revised))
    return {"articles": revised, "cost_tracker": cost}


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
