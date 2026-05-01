"""Organize, deduplicate, and validate collected content."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Organizer:
    """Organize, deduplicate, and validate collected content."""

    def __init__(self) -> None:
        pass

    def deduplicate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicate items based on URL or ID."""
        seen_urls = set()
        seen_ids = set()
        unique_items = []

        for item in items:
            url = item.get("url", "")
            item_id = item.get("id", "")

            if url and url in seen_urls:
                continue
            if item_id and item_id in seen_ids:
                continue

            if url:
                seen_urls.add(url)
            if item_id:
                seen_ids.add(item_id)
            unique_items.append(item)

        logger.info("Deduplicated: %d -> %d items", len(items), len(unique_items))
        return unique_items

    def standardize(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Standardize item format."""
        standardized = []
        for item in items:
            std_item = {
                "id": item.get("id", ""),
                "source": item.get("source", ""),
                "title": item.get("title", "").strip(),
                "description": item.get("description", "").strip(),
                "url": item.get("url", ""),
                "summary": item.get("summary", ""),
                "score": item.get("score", 0.0),
                "tags": item.get("tags", []),
                "updated_at": item.get("updated_at", ""),
                "collected_at": item.get("collected_at", ""),
                "analyzed": item.get("analyzed", False),
            }
            standardized.append(std_item)
        return standardized

    def validate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate items and filter out invalid ones."""
        valid_items = []
        for item in items:
            if not item.get("title") or not item.get("id"):
                logger.warning("Skipping invalid item: %s", item.get("id"))
                continue
            valid_items.append(item)
        return valid_items
