"""Main pipeline entry point that orchestrates the four-step process."""

import argparse
import logging
from pathlib import Path
from typing import Any

from collector import Collector
from analyzer import Analyzer
from organizer import Organizer
from saver import Saver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Main pipeline entry point."""
    parser = argparse.ArgumentParser(description="AI Knowledge Base Pipeline")
    parser.add_argument(
        "--sources",
        default="github,rss",
        help="Comma-separated list of sources (github,rss)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of items to collect per source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making actual changes",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    sources = [s.strip() for s in args.sources.split(",")]
    logger.info("Starting pipeline with sources=%s, limit=%d", sources, args.limit)

    collector = Collector(limit=args.limit, dry_run=args.dry_run)
    analyzer = Analyzer(dry_run=args.dry_run)
    organizer = Organizer()
    saver = Saver(dry_run=args.dry_run)

    all_items: list[dict[str, Any]] = []

    # Step 1: Collect
    for source in sources:
        if source == "github":
            items = collector.collect_github()
        elif source == "rss":
            items = collector.collect_rss()
        else:
            logger.warning("Unknown source: %s", source)
            continue

        collector.save_raw(items, source)
        all_items.extend(items)

    logger.info("Step 1 completed: Collected %d items total", len(all_items))

    # Step 2: Analyze
    for item in all_items:
        analysis = analyzer.analyze_item(item)
        item.update(analysis)

    logger.info("Step 2 completed: Analyzed %d items", len(all_items))

    # Step 3: Organize
    all_items = organizer.deduplicate(all_items)
    all_items = organizer.standardize(all_items)
    all_items = organizer.validate(all_items)

    logger.info("Step 3 completed: Organized %d items", len(all_items))

    # Step 4: Save
    saved_paths = saver.save_articles(all_items)

    logger.info("Step 4 completed: Saved %d articles", len(saved_paths))
    logger.info("Pipeline completed successfully!")


if __name__ == "__main__":
    main()
