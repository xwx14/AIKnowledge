"""Supervisor pattern: Worker generates analysis, Supervisor reviews quality.

Review loop:
  - Worker Agent 接收任务，输出 JSON 格式分析报告
  - Supervisor Agent 审核准确性/深度/格式（各 1-10 分）
  - 平均分 >= 7 通过，否则带反馈重做（最多 max_retries 轮）
  - 超过上限则强制返回并附带 warning
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "workflows"))
from model_client import chat, chat_json

logger = logging.getLogger(__name__)

WORKER_SYSTEM = "你是一个专业分析助手。请用中文完成分析任务，输出纯 JSON 格式的分析报告，不要包含 markdown 代码块标记。"

WORKER_PROMPT = """\
请完成以下分析任务，输出 JSON 格式的分析报告。

任务：{task}

{feedback_section}

输出格式（严格遵守）：
{{
  "title": "报告标题",
  "summary": "简要概述",
  "analysis": "详细分析内容",
  "conclusion": "结论",
  "key_points": ["要点1", "要点2", "要点3"]
}}"""

SUPERVISOR_SYSTEM = "你是一个严格的质量审核员。请审核分析报告的质量，只输出 JSON 格式的审核结果，不要包含 markdown 代码块标记。"

SUPERVISOR_PROMPT = """\
请审核以下分析报告的质量。

原始任务：{task}

分析报告：
{output}

评分维度（各 1-10 分）：
1. 准确性：分析内容是否准确、切题
2. 深度：分析是否深入、有洞察力
3. 格式：JSON 格式是否完整、字段是否齐全

输出格式（严格遵守）：
{{
  "accuracy": <1-10>,
  "depth": <1-10>,
  "format": <1-10>,
  "passed": <true 或 false，平均分 >= 7 为 true>,
  "score": <三维度平均分，四舍五入取整>,
  "feedback": "<具体改进建议，若通过可写'质量合格'>"
}}"""

PASS_THRESHOLD = 7


def _worker(task: str, feedback: str | None = None) -> dict:
    feedback_section = ""
    if feedback:
        feedback_section = (
            f"上一轮审核未通过，审核员反馈如下，请据此改进：\n{feedback}"
        )
    prompt = WORKER_PROMPT.format(
        task=task, feedback_section=feedback_section
    )
    try:
        result = chat_json(prompt, system_prompt=WORKER_SYSTEM)
        if isinstance(result, dict) and ("analysis" in result or "summary" in result):
            return result
        return {"raw": result}
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("Worker 输出解析失败: %s", e)
        text, _ = chat(prompt, system_prompt=WORKER_SYSTEM)
        return {"raw_text": text}


def _supervisor(task: str, output: dict) -> dict:
    output_str = json.dumps(output, ensure_ascii=False, indent=2)
    prompt = SUPERVISOR_PROMPT.format(task=task, output=output_str)
    try:
        result = chat_json(prompt, system_prompt=SUPERVISOR_SYSTEM)
        required = {"accuracy", "depth", "format", "passed", "score", "feedback"}
        if isinstance(result, dict) and required.issubset(result.keys()):
            return result
        if isinstance(result, dict):
            accuracy = result.get("accuracy", 5)
            depth = result.get("depth", 5)
            fmt = result.get("format", 5)
            avg = round((accuracy + depth + fmt) / 3)
            result.setdefault("score", avg)
            result.setdefault("passed", avg >= PASS_THRESHOLD)
            result.setdefault("feedback", result.get("feedback", "格式不完整"))
            return result
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("Supervisor 输出解析失败: %s", e)
    return {"passed": False, "score": 0, "feedback": "审核输出解析失败，请重试"}


def supervisor(task: str, max_retries: int = 3) -> dict:
    """Supervisor 监督模式：Worker 生成分析，Supervisor 审核，循环直到通过或超限。

    Args:
        task: 分析任务描述。
        max_retries: 最大重试轮数。

    Returns:
        dict: {
            "output": Worker 最终输出,
            "attempts": 实际尝试轮数,
            "final_score": 最终审核分数,
            "warning": 超限时附带的警告字符串（可选）
        }
    """
    feedback = None
    worker_output = None
    review = None

    for attempt in range(1, max_retries + 1):
        logger.info("第 %d/%d 轮：Worker 执行任务...", attempt, max_retries)
        worker_output = _worker(task, feedback)

        logger.info("第 %d/%d 轮：Supervisor 审核中...", attempt, max_retries)
        review = _supervisor(task, worker_output)

        score = review.get("score", 0)
        passed = review.get("passed", score >= PASS_THRESHOLD)
        feedback = review.get("feedback", "")

        logger.info(
            "第 %d 轮审核结果：score=%s, passed=%s, feedback=%s",
            attempt, score, passed, feedback[:50],
        )

        if passed:
            return {
                "output": worker_output,
                "attempts": attempt,
                "final_score": score,
            }

    return {
        "output": worker_output,
        "attempts": max_retries,
        "final_score": review.get("score", 0) if review else 0,
        "warning": f"已达到最大重试次数({max_retries})，强制返回最后结果",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    test_tasks = [
        "分析 RAG（检索增强生成）技术的核心原理、优缺点和应用场景",
        "对比 Transformer 和 Mamba 架构在序列建模上的差异",
    ]

    for task in test_tasks:
        print("=" * 60)
        print(f"任务: {task}")
        print("=" * 60)
        result = supervisor(task, max_retries=3)
        print(f"尝试轮数: {result['attempts']}")
        print(f"最终分数: {result['final_score']}")
        if "warning" in result:
            print(f"警告: {result['warning']}")
        print(f"输出: {json.dumps(result['output'], ensure_ascii=False, indent=2)[:500]}")
        print()
