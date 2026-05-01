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
import yaml

from config import RAW_DIR

logger = logging.getLogger(__name__)


class Collector:
    """Collect AI-related content from GitHub and RSS sources."""

    def __init__(self, limit: int = 20, dry_run: bool = False) -> None:
        self.limit = limit
        self.dry_run = dry_run
        self.client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)
        self.rss_sources = self._load_rss_sources()

    def _load_rss_sources(self) -> list[dict[str, Any]]:
        """Load RSS sources from YAML config file."""
        config_path = Path(__file__).parent / "rss_sources.yaml"
        if not config_path.exists():
            logger.warning("RSS config not found: %s", config_path)
            return []

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        sources = config.get("sources", [])
        enabled_sources = [s for s in sources if s.get("enabled", False)]
        logger.info("Loaded %d enabled RSS sources from config", len(enabled_sources))
        return enabled_sources

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

        for source in self.rss_sources:
            if len(results) >= self.limit:
                break

            feed_url = source.get("url", "")
            source_name = source.get("name", "Unknown")

            try:
                resp = self.client.get(feed_url)
                resp.raise_for_status()
                content = resp.text

                if not content or len(content) < 100:
                    logger.warning("RSS content too short for %s, skipping", source_name)
                    continue

                titles = re.findall(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
                links = re.findall(r"<link>(.*?)</link>", content, re.IGNORECASE | re.DOTALL)
                descriptions = re.findall(r"<description>(.*?)</description>", content, re.IGNORECASE | re.DOTALL)

                if len(titles) <= 1:
                    logger.warning("No valid items found in RSS feed: %s", source_name)
                    continue

                count = min(len(titles) - 1, self.limit - len(results))
                for i in range(1, count + 1):
                    if len(results) >= self.limit:
                        break
                    title = titles[i].strip()
                    link = links[i].strip() if i < len(links) else ""
                    if not title or not link:
                        continue
                    result = {
                        "source": "rss",
                        "source_name": source_name,
                        "category": source.get("category", ""),
                        "id": f"rss_{hashlib.md5((title + link).encode()).hexdigest()[:12]}",
                        "title": title,
                        "description": descriptions[i].strip() if i < len(descriptions) else "",
                        "url": link,
                        "updated_at": "",
                        "collected_at": datetime.utcnow().isoformat(),
                    }
                    results.append(result)

            except Exception as e:
                logger.error("RSS collection failed for %s: %s", source_name, e)

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
