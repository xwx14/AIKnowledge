#!/usr/bin/env python3
"""top-rated: 按关键字搜索知识库，返回评分最高的项目"""

import argparse
import json
import sys
from pathlib import Path

ARTICLES_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "articles"


def normalize_score(score):
    if score > 1.0:
        return score / 10.0
    return score


def load_articles():
    if not ARTICLES_DIR.exists():
        return []
    articles = []
    for fp in ARTICLES_DIR.glob("*.json"):
        if fp.name == "index.json":
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_normalized_score"] = normalize_score(data.get("score", 0.0))
                articles.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return articles


def match_keyword(article, keyword):
    if not keyword:
        return True
    kw = keyword.lower()
    fields = [
        article.get("title") or "",
        article.get("summary") or "",
        article.get("description") or "",
        " ".join(t for t in (article.get("tags") or []) if isinstance(t, str)),
    ]
    return any(kw in f.lower() for f in fields)


def search_top_rated(keyword, top_n=5):
    articles = load_articles()
    matched = [a for a in articles if match_keyword(a, keyword)]
    matched.sort(key=lambda a: a.get("_normalized_score", 0.0), reverse=True)
    results = []
    for a in matched[:top_n]:
        results.append({
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "score": a.get("score", 0.0),
            "summary": a.get("summary", ""),
            "tags": a.get("tags", []),
            "source": a.get("source", ""),
            "collected_at": a.get("collected_at", ""),
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="搜索知识库，返回评分最高的项目")
    parser.add_argument("keyword", nargs="?", default="", help="搜索关键字")
    parser.add_argument("--top", type=int, default=5, help="返回结果数量（默认 5）")
    args = parser.parse_args()

    results = search_top_rated(args.keyword, args.top)
    if not results:
        print(json.dumps([], ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
