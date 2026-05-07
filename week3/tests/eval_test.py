"""AI 知识库评估测试：覆盖正面/负面/边界场景 + LLM-as-Judge。"""

import json
import os
import re
import sys
import warnings

# ── 环境准备 ──────────────────────────────────────────────────────
# 加载 .env 使 pytest 能读取 LLM 相关环境变量
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 屏蔽自定义标记（slow）产生的未知标记警告
warnings.filterwarnings("ignore", category=pytest.PytestUnknownMarkWarning)

# 确保能导入 workflows 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "workflows"))

from model_client import chat


# ── 评估用例定义 ──────────────────────────────────────────────────
def _check_positive(result: dict) -> bool:
    """正面案例检查：有摘要、有标签、分数合理。"""
    return (
        len(result.get("summary", "")) >= 10
        and len(result.get("tags", [])) >= 1
        and 1 <= result.get("score", 0) <= 10
    )


def _check_negative(result: dict) -> bool:
    """负面案例检查：低相关性分数或被过滤。"""
    return result.get("score", 5) <= 4 or result.get("filtered", False)


def _check_boundary(result: dict) -> bool:
    """边界案例检查：不崩溃，返回可识别结构。"""
    return isinstance(result, dict) and "summary" in result


EVAL_CASES = [
    {
        "name": "正面案例 - 技术文章",
        "input": {
            "title": "Transformer Architecture for Large Language Models",
            "description": (
                "A comprehensive guide to transformer-based architectures used in "
                "modern large language models including attention mechanisms, "
                "positional encoding, and multi-head self-attention. Covers "
                "implementation details for PyTorch-based training pipelines."
            ),
        },
        "expected": {
            "check": _check_positive,
            "summary_min_len": 10,
            "tags_min": 1,
            "score_range": (1, 10),
        },
    },
    {
        "name": "负面案例 - 无关内容",
        "input": {
            "title": "How to Bake the Perfect Chocolate Cake",
            "description": (
                "This recipe shows you how to make a delicious chocolate cake "
                "with frosting. Ingredients include flour, sugar, cocoa powder, "
                "eggs, and butter. Bake at 350°F for 30 minutes."
            ),
        },
        "expected": {
            "check": _check_negative,
            "score_max": 4,
        },
    },
    {
        "name": "边界案例 - 极短输入",
        "input": {
            "title": "AI",
            "description": "AI",
        },
        "expected": {
            "check": _check_boundary,
        },
    },
]


# ── 辅助函数 ──────────────────────────────────────────────────────
def _run_analyzer(item: dict) -> dict:
    """调用 LLM 分析单条内容，返回 {summary, score, tags, analyzed}。"""
    prompt = f"""请分析以下AI相关内容，并提供：
1. 简洁的中文摘要（2-3句话）
2. 对AI知识库的相关性评分（1到10，10为最相关）
3. 最多5个相关的中文标签

标题：{item.get('title', '')}
描述：{item.get('description', '')}

请用中文回复，仅返回JSON格式：{{"summary": "摘要...", "score": 8, "tags": ["标签1", "标签2"]}}"""

    text, _usage = chat(prompt, system_prompt="你是一个AI知识库分析助手。")

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {"summary": text[:100], "score": 5, "tags": [], "analyzed": False}


# ── 本地验证测试（不调用 LLM）─────────────────────────────────────
class TestEvalCasesStructure:
    """验证 EVAL_CASES 结构完整，无需外部依赖。"""

    def test_eval_cases_not_empty(self):
        assert len(EVAL_CASES) >= 3, "至少需要 3 个评估用例"

    @pytest.mark.parametrize("case", EVAL_CASES, ids=lambda c: c["name"])
    def test_case_has_required_keys(self, case):
        assert "name" in case, f"{case} 缺少 name 字段"
        assert "input" in case, f"{case} 缺少 input 字段"
        assert "expected" in case, f"{case} 缺少 expected 字段"
        assert "check" in case["expected"], f"{case['name']} 的 expected 缺少 check 函数"

    def test_case_names_unique(self):
        names = [c["name"] for c in EVAL_CASES]
        assert len(names) == len(set(names)), f"存在重复的用例名: {names}"

    def test_case_inputs_have_title_and_description(self):
        for case in EVAL_CASES:
            inp = case["input"]
            assert "title" in inp, f"{case['name']} 的 input 缺少 title"
            assert "description" in inp, f"{case['name']} 的 input 缺少 description"


# ── LLM 分析测试（调用真实 API）───────────────────────────────────
class TestLLMAnalysis:
    """验证 LLM 能正确分析不同类型的内容。"""

    @pytest.mark.slow
    @pytest.mark.parametrize("case", EVAL_CASES, ids=lambda c: c["name"])
    def test_eval_case_analysis(self, case):
        """对每个 EVAL_CASE 调用 LLM 分析，验证结果符合预期。"""
        result = _run_analyzer(case["input"])
        assert isinstance(result, dict), "分析结果应为 dict"
        assert case["expected"]["check"](result), (
            f"[{case['name']}] 结果未达预期: {result}"
        )

    @pytest.mark.slow
    def test_positive_case_has_summary_and_tags(self):
        """正面案例：摘要长度 >= 10 字符，至少 1 个标签。"""
        case = EVAL_CASES[0]
        result = _run_analyzer(case["input"])
        assert len(result.get("summary", "")) >= 10, f"摘要太短: {result.get('summary')}"
        assert len(result.get("tags", [])) >= 1, f"缺少标签: {result.get('tags')}"
        assert isinstance(result.get("score", 0), (int, float)), "score 应为数字"
        assert 1 <= result["score"] <= 10, f"score 超出范围: {result['score']}"

    @pytest.mark.slow
    def test_negative_case_low_score(self):
        """负面案例：相关性评分应 <= 4。"""
        case = EVAL_CASES[1]
        result = _run_analyzer(case["input"])
        assert result.get("score", 5) <= 4, (
            f"无关内容评分过高: score={result.get('score')}"
        )

    @pytest.mark.slow
    def test_boundary_case_no_crash(self):
        """边界案例：极短输入不应崩溃。"""
        case = EVAL_CASES[2]
        result = _run_analyzer(case["input"])
        assert isinstance(result, dict), "极短输入导致返回非 dict"
        assert "summary" in result, "结果缺少 summary 字段"


# ── LLM-as-Judge 测试 ─────────────────────────────────────────────
class TestLLMAsJudge:
    """让 LLM 充当评判者，对分析结果打分（1-10），断言 >= 5。"""

    @pytest.mark.slow
    def test_llm_judge_scores_positive_case(self):
        """LLM 评判：技术文章的分析结果质量分应 >= 5。"""
        case = EVAL_CASES[0]
        analysis = _run_analyzer(case["input"])

        judge_prompt = f"""请对以下AI知识库分析结果进行质量评估（1-10分）：
- 标题：{case['input']['title']}
- 摘要：{analysis.get('summary', '')}
- 标签：{', '.join(analysis.get('tags', []))}

评分标准：
- 摘要是否准确概括内容
- 标签是否与主题相关
- 整体分析质量

仅返回一个数字（1-10），不要其他内容。"""

        text, _usage = chat(judge_prompt, system_prompt="你是一个严格的AI知识库质量评判员。")
        match = re.search(r"(\d+)", text)
        assert match, f"LLM 未返回有效分数: {text}"
        score = int(match.group(1))
        assert 1 <= score <= 10, f"分数超出范围: {score}"
        assert score >= 5, f"LLM 评判分数过低: {score}（期望 >= 5）"
