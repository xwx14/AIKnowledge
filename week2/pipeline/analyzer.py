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

    def analyze_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Analyze a single item using LLM."""
        if self.dry_run or not self.provider:
            return {
                "summary": "Dry-run summary",
                "score": 0.5,
                "tags": ["ai", "test"],
                "analyzed": False,
            }

        prompt = f"""Analyze the following AI-related content and provide:
1. A concise summary (2-3 sentences)
2. A relevance score (0.0 to 1.0) for AI knowledge base
3. Up to 5 relevant tags

Title: {item.get('title', '')}
Description: {item.get('description', '')}

Respond in JSON format: {{"summary": "...", "score": 0.8, "tags": ["tag1", "tag2"]}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = chat_with_retry(self.provider, messages)
            content = response.content.strip()

            # Extract JSON from response
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                analysis["analyzed"] = True
                return analysis
        except Exception as e:
            logger.error("Analysis failed for %s: %s", item.get("id"), e)

        return {
            "summary": "",
            "score": 0.0,
            "tags": [],
            "analyzed": False,
        }
