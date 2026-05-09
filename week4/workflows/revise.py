"""修订节点：根据审核反馈中弱项维度，逐条调用 LLM 改写摘要/标签。"""

import asyncio
import json
import logging
import re

from model_client import chat_with_retry
from nodes import _parse_json_from_text, accumulate_usage
from state import KBState

logger = logging.getLogger(__name__)

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
                m = re.search(r"(\d+)", line)
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
            response = asyncio.run(chat_with_retry(messages, temperature=0.4, node_name="revise"))
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
