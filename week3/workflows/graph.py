"""LangGraph 工作流图组装。

构建知识库采集工作流 DAG：
  collect → analyze → organize → review ─┬→ save → END
                                          ├→ revise → review (修正循环, iteration < 3)
                                          └→ human_flag → END (iteration >= 3)

条件分支：review_passed=True 走 save，
未通过且 iteration < 3 走 revise 再回 review，
未通过且 iteration >= 3 走 human_flag 终止。
"""

import logging

from langgraph.graph import END, StateGraph

from human_flag import human_flag_node
from nodes import (
    analyze_node,
    collect_node,
    organize_node,
    review_node,
    revise_node,
    save_node,
)
from state import KBState

logger = logging.getLogger(__name__)


def route_after_review(state: KBState) -> str:
    """3 路条件路由：根据审核结果和迭代次数决定下一步。

    Returns:
        "save" — 审核通过，进入保存节点。
        "revise" — 审核未通过且 iteration < 3，进入修订节点。
        "human_flag" — 审核未通过且 iteration >= 3，标记人工审核。
    """
    if state.get("review_passed", False):
        return "save"
    if state.get("iteration", 0) >= 3:
        return "human_flag"
    return "revise"


def build_graph() -> StateGraph:
    """组装并编译 LangGraph 工作流。

    Returns:
        编译后的可执行 CompiledGraph 实例。
    """
    graph = StateGraph(KBState)

    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_node)
    graph.add_node("revise", revise_node)
    graph.add_node("human_flag", human_flag_node)
    graph.add_node("save", save_node)

    graph.set_entry_point("collect")

    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "review")

    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"save": "save", "revise": "revise", "human_flag": "human_flag"},
    )

    graph.add_edge("revise", "review")
    graph.add_edge("save", END)
    graph.add_edge("human_flag", END)

    return graph.compile()


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    app = build_graph()
    logger.info("工作流图编译完成，开始执行")

    initial_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "needs_human_review": False,
        "iteration": 0,
        "cost_tracker": {},
    }

    for event in app.stream(initial_state):
        node_name = list(event.keys())[0]
        node_output = event[node_name]

        print(f"\n{'=' * 50}")
        print(f"[{node_name}] 输出摘要:")

        if node_name == "collect":
            sources = node_output.get("sources", [])
            print(f"  采集条目数: {len(sources)}")
            for s in sources[:3]:
                print(f"  - {s.get('title', '?')} ({s.get('id', '?')})")
            if len(sources) > 3:
                print(f"  ... 及其他 {len(sources) - 3} 条")

        elif node_name == "analyze":
            analyses = node_output.get("analyses", [])
            print(f"  分析条目数: {len(analyses)}")
            for a in analyses[:3]:
                print(f"  - [{a.get('score', '?')}] {a.get('title', '?')} | {a.get('tags', [])}")
            if len(analyses) > 3:
                print(f"  ... 及其他 {len(analyses) - 3} 条")

        elif node_name == "organize":
            articles = node_output.get("articles", [])
            print(f"  整理后条目数: {len(articles)}")
            for a in articles[:3]:
                print(f"  - [{a.get('score', '?')}] {a.get('title', '?')}")
            if len(articles) > 3:
                print(f"  ... 及其他 {len(articles) - 3} 条")

        elif node_name == "review":
            passed = node_output.get("review_passed", False)
            iteration = node_output.get("iteration", 0)
            feedback = node_output.get("review_feedback", "")
            print(f"  审核通过: {passed}")
            print(f"  当前轮次: {iteration}")
            if feedback:
                print(f"  反馈: {feedback}")

        elif node_name == "revise":
            articles = node_output.get("articles", [])
            print(f"  修订条目数: {len(articles)}")

        elif node_name == "human_flag":
            print(f"  需要人工审核: {node_output.get('needs_human_review', False)}")

        elif node_name == "save":
            articles = node_output.get("articles", [])
            print(f"  保存文章数: {len(articles)}")

        cost = node_output.get("cost_tracker", {})
        if cost:
            print(f"  Token 累计: {cost.get('total_tokens', 0)} | 调用次数: {cost.get('calls', 0)}")

    print(f"\n{'=' * 50}")
    print("工作流执行完毕")
