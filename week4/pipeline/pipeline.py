"""
pipeline/pipeline.py — V4 知识库采集分析流水线

【V4 关键演进：继承 V3 LangGraph 工作流 + V4 分发层】

V1 (week1) → 手动 Agent + OpenCode
V2 (week2) → 自动化四步流水线 (关键词匹配)
V3 (week3) → LangGraph + Planner/Reviewer + 审核循环 (真 LLM)
V4 (week4) → V3 LangGraph 工作流 + 分发层 (formatter/publisher) + 容器化

本文件是 V3 LangGraph workflows.graph.app 的薄封装——
在流水线跑完后追加分发步骤 (publish)。

调用关系:
    workflows.graph.app.invoke(state)  ← 核心审核循环
            │
            ▼
    distribution.publisher.publish_daily_digest()  ← V4 新增
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "workflows"))

load_dotenv()

logger = logging.getLogger(__name__)


async def run_pipeline(publish: bool = True) -> list[dict]:
    """运行完整的 V4 流水线。

    阶段:
    1. V3 LangGraph 工作流 (planner → collect → analyze → organize → review → save)
    2. V4 新增：发布每日简报到各渠道 (Telegram / Feishu)

    Args:
        publish: 是否在流水线完成后发布每日简报

    Returns:
        本次运行生成的知识条目列表
    """
    logger.info("=" * 60)
    logger.info(f"[V4 Pipeline] 开始执行 — {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # ------ Stage A: 运行 V3 LangGraph 工作流 ------
    logger.info("[V4 Pipeline] Stage A: V3 LangGraph 工作流")
    from workflows.graph import build_graph
    from workflows.state import KBState

    app = build_graph().compile()

    initial_state: KBState = {
        "plan": {},
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "needs_human_review": False,
        "iteration": 0,
        "cost_tracker": {},
    }

    final_state: dict = {}
    current_plan: dict = {}
    for event in app.stream(initial_state):
        node_name = list(event.keys())[0]
        node_output = event[node_name]
        final_state.update(node_output)
        if "plan" in node_output:
            current_plan = node_output["plan"] or {}
            logger.info(f"[Pipeline] plan 策略: {current_plan.get('tier', '?')}")
        if "sources" in node_output:
            logger.info(f"[Pipeline] collect: {len(node_output['sources'])} 条")
        if "articles" in node_output:
            logger.info(f"[Pipeline] organize: {len(node_output['articles'])} 条")
        if "review_passed" in node_output:
            max_iter = current_plan.get("max_iterations", 3)
            passed = "通过" if node_output["review_passed"] else "未通过"
            logger.info(f"[Pipeline] review: {passed} ({node_output.get('iteration', '?')}/{max_iter})")

    articles = final_state.get("articles", [])
    cost = final_state.get("cost_tracker", {}).get("total_cost_rmb", 0)
    logger.info(f"[V4 Pipeline] Stage A 完成：{len(articles)} 条文章，成本 ¥{cost:.6f}")

    # ------ Stage B: V4 新增 — 分发每日简报 ------
    if publish and articles:
        logger.info("[V4 Pipeline] Stage B: 发布每日简报")
        try:
            from distribution.publisher import publish_daily_digest

            results = await publish_daily_digest()
            for r in results:
                status = "成功" if r.success else f"失败({r.error})"
                logger.info(f"[V4 Pipeline] {r.channel}: {status}")
        except ImportError as e:
            logger.warning(f"[V4 Pipeline] distribution 模块未装，跳过发布: {e}")
        except Exception as e:
            logger.error(f"[V4 Pipeline] 发布失败: {e}")
    elif not publish:
        logger.info("[V4 Pipeline] 跳过发布（--no-publish）")
    else:
        logger.info("[V4 Pipeline] 无新文章，跳过发布")

    logger.info("=" * 60)
    logger.info(f"[V4 Pipeline] 完成 — 总成本 ¥{cost:.6f}")
    logger.info("=" * 60)

    return articles


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    publish = "--no-publish" not in sys.argv
    asyncio.run(run_pipeline(publish=publish))
