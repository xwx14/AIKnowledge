"""LangGraph 工作流共享状态定义。

遵循"报告式通信"原则：每个字段存储结构化摘要，
而非原始数据流，使节点间通信清晰可审计。
"""

from typing import TypedDict


class KBState(TypedDict):
    """知识库采集工作流的共享状态。

    各节点通过读写此状态进行协作，字段值为结构化摘要，
    不是未经处理的原始数据，确保状态可追溯、可调试。
    """

    sources: list[dict]
    """采集到的原始数据。

    每个元素为一条采集记录，格式：
    {
        "id": str,          # 条目唯一标识，如 "github_12345"
        "source": str,      # 来源类型，"github" 或 "rss"
        "title": str,       # 标题
        "url": str,         # 原文链接
        "description": str, # 原始描述
        "updated_at": str,  # 更新时间
        "collected_at": str # 采集时间
    }
    由 Collector 节点写入。
    """

    analyses: list[dict]
    """LLM 分析后的结构化结果。

    每个元素在 sources 条目基础上追加 LLM 产出字段：
    {
        "summary": str,     # 中文摘要（≥20 字符）
        "score": int,       # 质量评分 1-10
        "tags": list[str],  # 技术标签列表
        "analyzed": bool    # 是否已完成分析（True）
    }
    由 Analyzer 节点写入。
    """

    articles: list[dict]
    """格式化、去重后的知识条目。

    经过 Organizer 节点的去重（URL + ID 双键）、
    标准化（统一字段名和类型）、校验（过滤无标题/无 ID）
    后的最终条目，格式与 analyses 一致但仅保留合法记录。
    由 Organizer 节点写入。
    """

    review_feedback: str
    """审核反馈意见。

    Reviewer 节点写入，描述本轮审核发现的问题，
    如"摘要过于笼统，缺少技术细节"或空字符串表示无异议。
    Analyzer 节点读取后据此重新分析。
    """

    review_passed: bool
    """审核是否通过。

    True 表示当前 articles 质量达标，可进入保存环节；
    False 表示需要根据 review_feedback 重新分析。
    由 Reviewer 节点写入。
    """

    iteration: int
    """当前审核循环次数。

    从 0 开始计数，每次 Reviewer 判定不通过后递增，
    最多循环 3 次（即 iteration <= 3），超过则强制通过。
    用于防止无限循环。
    """

    cost_tracker: dict
    """Token 用量与成本追踪。

    格式：
    {
        "total_tokens": int,       # 累计 token 数
        "prompt_tokens": int,      # 累计输入 token 数
        "completion_tokens": int,  # 累计输出 token 数
        "total_cost_rmb": float,   # 累计成本（人民币）
        "calls": int               # 累计 API 调用次数
    }
    由 Analyzer 节点每次调用 LLM 后更新。
    """
