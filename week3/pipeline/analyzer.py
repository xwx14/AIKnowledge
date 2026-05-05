"""Analyze content using LLM for summarization, scoring, and tagging."""

import json
import logging
import os
import re
from typing import Any

from model_client import get_provider, chat_with_retry

logger = logging.getLogger(__name__)


class Analyzer:
    """Analyze content using LLM for summarization, scoring, and tagging."""

    def __init__(self, dry_run: bool = False, provider_name: str = "deepseek") -> None:
        self.dry_run = dry_run
        self.provider = None
        if not dry_run:
            try:
                os.environ["LLM_PROVIDER"] = provider_name
                self.provider = get_provider()
            except Exception as e:
                logger.warning("LLM provider not available: %s", e)

    async def analyze_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Analyze a single item using LLM."""
        if self.dry_run or not self.provider:
            return {
                "summary": "干跑模式摘要",
                "score": 5,
                "tags": ["人工智能", "测试"],
                "analyzed": False,
            }

        prompt = f"""请分析以下AI相关内容，并提供：
1. 简洁的中文摘要（2-3句话）
2. 对AI知识库的相关性评分（1到10）
3. 最多5个相关的中文标签

标题：{item.get('title', '')}
描述：{item.get('description', '')}

请用中文回复，JSON格式示例：{{"summary": "这里是中文摘要...", "score": 8, "tags": ["人工智能", "机器学习"]}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = await chat_with_retry(messages)
            content = response.content.strip()

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                analysis["analyzed"] = True
                return analysis
        except Exception as e:
            logger.error("Analysis failed for %s: %s", item.get("id"), e)

        return {
            "summary": "",
            "score": 0,
            "tags": [],
            "analyzed": False,
        }

    async def analyze_all(self, items: list[dict[str, Any]]) -> None:
        """Analyze all items in-place."""
        for item in items:
            analysis = await self.analyze_item(item)
            item.update(analysis)
