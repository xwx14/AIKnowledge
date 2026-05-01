"""Save processed articles to individual JSON files."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from config import ARTICLES_DIR

logger = logging.getLogger(__name__)


class Saver:
    """Save processed articles to individual JSON files."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def save_articles(self, items: list[dict[str, Any]]) -> list[Path]:
        """Save each article as individual JSON file."""
        saved_paths = []
        for item in items:
            article_id = item.get("id", hashlib.md5(item.get("url", "").encode()).hexdigest()[:12])
            article_file = ARTICLES_DIR / f"{article_id}.json"

            if self.dry_run:
                logger.info("[DRY-RUN] Would save article to %s", article_file)
            else:
                with open(article_file, "w", encoding="utf-8") as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                saved_paths.append(article_file)

        if not self.dry_run:
            logger.info("Saved %d articles to %s", len(saved_paths), ARTICLES_DIR)
        return saved_paths
