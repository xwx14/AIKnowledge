"""审核节点：LLM 五维度加权评分（review_node）及测试用模拟节点（review_node_test）。"""

import logging

from model_client import chat_json
from nodes import accumulate_usage
from state import KBState

logger = logging.getLogger(__name__)

_REVIEW_WEIGHTS = {
    "summary_quality": 0.25,
    "technical_depth": 0.25,
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15,
}
_PASS_THRESHOLD = 7.0


def review_node(state: KBState) -> dict:
    """审核节点：LLM 五维度加权评分（1-10），iteration >= max_iterations 强制通过。

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
    plan = state.get("plan", {}) or {}
    max_iterations = int(plan.get("max_iterations", 3))

    if iteration >= max_iterations:
        logger.info("[ReviewNode] iteration=%d >= max_iterations=%d，强制通过", iteration, max_iterations)
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
        result, usage = chat_json(prompt, system_prompt, temperature=0.1, node_name="review")
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
