"""Shared configuration and constants for pipeline modules."""

from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "knowledge" / "raw"
ARTICLES_DIR = Path(__file__).parent.parent / "knowledge" / "articles"
RAW_DIR.mkdir(parents=True, exist_ok=True)
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
