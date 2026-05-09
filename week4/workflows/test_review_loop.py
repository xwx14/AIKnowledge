"""测试审核循环：验证 organize → review 循环逻辑。"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

from nodes import organize_node, save_node
from review import review_node_test

initial_state = {
    "sources": [
        {"id": "github_1", "source": "github", "title": "TestRepo1", "description": "A test AI repo", "url": "https://github.com/test1", "updated_at": "", "collected_at": "", "stars": 100},
        {"id": "github_2", "source": "github", "title": "TestRepo2", "description": "Another ML project", "url": "https://github.com/test2", "updated_at": "", "collected_at": "", "stars": 50},
        {"id": "github_3", "source": "github", "title": "LowScoreRepo", "description": "Not relevant", "url": "https://github.com/test3", "updated_at": "", "collected_at": "", "stars": 1},
    ],
    "analyses": [
        {"id": "github_1", "source": "github", "title": "TestRepo1", "description": "A test AI repo", "url": "https://github.com/test1", "summary": "这是一个测试用的AI仓库，包含深度学习模型实现。", "score": 8, "tags": ["深度学习", "AI"], "analyzed": True},
        {"id": "github_2", "source": "github", "title": "TestRepo2", "description": "Another ML project", "url": "https://github.com/test2", "summary": "一个机器学习项目，提供了完整的训练流水线。", "score": 7, "tags": ["机器学习", "训练"], "analyzed": True},
        {"id": "github_3", "source": "github", "title": "LowScoreRepo", "description": "Not relevant", "url": "https://github.com/test3", "summary": "不太相关的内容。", "score": 3, "tags": ["测试"], "analyzed": True},
    ],
    "articles": [],
    "review_feedback": "",
    "review_passed": False,
    "iteration": 0,
    "cost_tracker": {},
}

print("=" * 60)
print("测试审核循环：模拟 organize -> review 循环")
print("=" * 60)

state = dict(initial_state)

for round_num in range(4):
    print(f"\n--- 第 {round_num + 1} 轮 ---")
    print(f"  [输入] iteration={state['iteration']}, review_passed={state['review_passed']}")

    result = organize_node(state)
    state.update(result)
    print(f"  [organize] 文章数={len(state['articles'])}")

    result = review_node_test(state)
    state.update(result)
    fb = state["review_feedback"]
    print(f"  [review]  iteration={state['iteration']}, review_passed={state['review_passed']}, feedback={fb if fb else '(无)'}")

    if state["review_passed"]:
        print(f"\n  >>> 审核通过！进入保存环节")
        result = save_node(state)
        state.update(result)
        print(f"  [save] 保存文章数={len(state['articles'])}")
        break

print(f"\n{'=' * 60}")
print(f"最终状态: iteration={state['iteration']}, review_passed={state['review_passed']}")
print(f"文章数: {len(state['articles'])}")
print("审核循环测试完成")
