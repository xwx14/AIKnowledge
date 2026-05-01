"""Collect AI-related content from GitHub and RSS sources."""

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from config import RAW_DIR

logger = logging.getLogger(__name__)


class Collector:
    """Collect AI-related content from GitHub and RSS sources."""

    def __init__(self, limit: int = 20, dry_run: bool = False) -> None:
        self.limit = limit
        self.dry_run = dry_run
        self.client = httpx.Client(timeout=30)

    def collect_github(self) -> list[dict[str, Any]]:
        """Collect AI content from GitHub Search API."""
        logger.info("Collecting from GitHub (limit=%d)", self.limit)
        results = []
        query = "AI OR artificial intelligence OR machine learning language:en"
        params = {"q": query, "sort": "updated", "order": "desc", "per_page": min(self.limit, 100)}
        url = f"https://api.github.com/search/repositories?{urlencode(params)}"

        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])[: self.limit]

            for item in items:
                result = {
                    "source": "github",
                    "id": f"github_{item['id']}",
                    "title": item.get("name", ""),
                    "description": item.get("description", ""),
                    "url": item.get("html_url", ""),
                    "updated_at": item.get("updated_at", ""),
                    "stars": item.get("stargazers_count", 0),
                    "collected_at": datetime.utcnow().isoformat(),
                }
                results.append(result)

            logger.info("Collected %d items from GitHub", len(results))
        except Exception as e:
            logger.error("GitHub collection failed: %s", e)

        return results

    def collect_rss(self) -> list[dict[str, Any]]:
        """Collect AI content from RSS feeds using regex parsing."""
        logger.info("Collecting from RSS (limit=%d)", self.limit)
        results = []
        feeds = [
            "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
            "https://feeds.feedburner.com/nvidiablog",
        ]

        for feed_url in feeds:
            try:
                resp = self.client.get(feed_url)
                resp.raise_for_status()
                content = resp.text

                titles = re.findall(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
                links = re.findall(r"<link>(.*?)</link>", content, re.IGNORECASE | re.DOTALL)
                descriptions = re.findall(r"<description>(.*?)</description>", content, re.IGNORECASE | re.DOTALL)

                count = min(len(titles) - 1, self.limit - len(results))
                for i in range(1, count + 1):
                    if len(results) >= self.limit:
                        break
                    result = {
                        "source": "rss",
                        "id": f"rss_{hashlib.md5((titles[i] + links[i]).encode()).hexdigest()[:12]}",
                        "title": titles[i].strip(),
                        "description": descriptions[i].strip() if i < len(descriptions) else "",
                        "url": links[i].strip() if i < len(links) else "",
                        "updated_at": "",
                        "collected_at": datetime.utcnow().isoformat(),
                    }
                    results.append(result)

                if len(results) >= self.limit:
                    break
            except Exception as e:
                logger.error("RSS collection failed for %s: %s", feed_url, e)

        logger.info("Collected %d items from RSS", len(results))
        return results

    def save_raw(self, items: list[dict[str, Any]], source: str) -> Path:
        """Save raw collected data to JSON file."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        raw_file = RAW_DIR / f"{source}_{timestamp}.json"
        if not self.dry_run:
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            logger.info("Saved raw data to %s", raw_file)
        else:
            logger.info("[DRY-RUN] Would save raw data to %s", raw_file)
        return raw_file
