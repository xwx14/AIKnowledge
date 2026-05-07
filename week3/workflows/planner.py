"""采集策略规划器。

根据目标采集量自动选择 lite / standard / full 三档策略，
控制每个源的采集上限、相关性阈值和最大迭代次数。
"""

import logging
import os

from state import KBState

logger = logging.getLogger(__name__)

_DEFAULT_TARGET = 10

_STRATEGIES = {
    "lite": {
        "per_source_limit": 5,
        "relevance_threshold": 0.7,
        "max_iterations": 1,
        "rationale": "目标采集量较小（<10），采用精简策略：少量采集、高阈值筛选、单次通过，节省 API 调用成本",
    },
    "standard": {
        "per_source_limit": 10,
        "relevance_threshold": 0.5,
        "max_iterations": 2,
        "rationale": "目标采集量适中（10-19），采用标准策略：中等采集量、常规阈值、允许一轮修正，平衡质量与效率",
    },
    "full": {
        "per_source_limit": 20,
        "relevance_threshold": 0.4,
        "max_iterations": 3,
        "rationale": "目标采集量较大（≥20），采用完整策略：大量采集、低阈值宽进、多次迭代修正，确保充分覆盖",
    },
}


def plan_strategy(target_count: int | None = None) -> dict:
    """根据目标采集量返回策略 dict。

    Args:
        target_count: 目标采集条目数。为 None 时从环境变量
            PLANNER_TARGET_COUNT 读取，默认 10。

    Returns:
        策略 dict，包含 per_source_limit / relevance_threshold /
        max_iterations / rationale / tier / target_count 字段。
    """
    if target_count is None:
        env_val = os.environ.get("PLANNER_TARGET_COUNT", "")
        try:
            target_count = int(env_val)
        except (ValueError, TypeError):
            target_count = _DEFAULT_TARGET

    if target_count < 10:
        tier = "lite"
    elif target_count < 20:
        tier = "standard"
    else:
        tier = "full"

    plan = {**_STRATEGIES[tier], "tier": tier, "target_count": target_count}
    logger.info(
        "[Planner] 目标 %d 条 → %s 策略 (per_source=%d, threshold=%.1f, max_iter=%d)",
        target_count, tier,
        plan["per_source_limit"], plan["relevance_threshold"], plan["max_iterations"],
    )
    return plan


def planner_node(state: KBState) -> dict:
    """LangGraph 规划节点：调用 plan_strategy 并返回 plan 更新。

    Args:
        state: 当前工作流状态，本节点不读取其字段，
            仅作为 LangGraph 节点签名占位。

    Returns:
        {"plan": plan} 部分状态更新。
    """
    plan = plan_strategy()
    return {"plan": plan}
