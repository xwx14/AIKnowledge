#!/usr/bin/env python3
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STANDARD_TAGS = {
    "python", "javascript", "java", "go", "rust", "typescript",
    "frontend", "backend", "fullstack", "devops", "testing",
    "algorithm", "data-structure", "database", "cache", "queue",
    "http", "rest", "graphql", "api", "web", "mobile",
    "react", "vue", "angular", "nodejs", "spring", "django",
    "security", "performance", "optimization", "architecture",
    "design-pattern", "refactoring", "testing", "ci-cd",
    "docker", "kubernetes", "cloud", "aws", "azure", "gcp",
    "machine-learning", "ai", "deep-learning", "nlp",
    "monitoring", "logging", "tracing", "observability",
}

TECH_KEYWORDS = {
    "api", "http", "rest", "graphql", "database", "cache",
    "algorithm", "data-structure", "concurrency", "async",
    "performance", "optimization", "security", "authentication",
    "authorization", "encryption", "deployment", "monitoring",
    "logging", "testing", "unit-test", "integration-test",
    "docker", "kubernetes", "microservices", "architecture",
    "design-pattern", "refactoring", "code-review",
    "ci-cd", "version-control", "git", "agile", "scrum",
}

EMPTY_WORDS_CN = {
    "赋能", "抓手", "闭环", "打通", "全链路",
    "底层逻辑", "颗粒度", "对齐", "拉通", "沉淀",
    "强大的", "革命性的",
}

EMPTY_WORDS_EN = {
    "groundbreaking", "revolutionary", "game-changing",
    "cutting-edge", "disruptive", "innovative",
    "next-generation", "state-of-the-art",
}


@dataclass
class DimensionScore:
    name: str
    score: int
    max_score: int


@dataclass
class QualityReport:
    file_path: str
    id: str
    summary_quality: int
    technical_depth: int
    format_compliance: int
    tag_precision: int
    empty_words_check: int

    def total_score(self) -> int:
        return (
            self.summary_quality +
            self.technical_depth +
            self.format_compliance +
            self.tag_precision +
            self.empty_words_check
        )

    def grade(self) -> str:
        score = self.total_score()
        if score >= 80:
            return "A"
        elif score >= 60:
            return "B"
        else:
            return "C"

    def dimensions(self) -> list[DimensionScore]:
        return [
            DimensionScore("Summary Quality", self.summary_quality, 25),
            DimensionScore("Technical Depth", self.technical_depth, 25),
            DimensionScore("Format Compliance", self.format_compliance, 20),
            DimensionScore("Tag Precision", self.tag_precision, 15),
            DimensionScore("Empty Words Check", self.empty_words_check, 15),
        ]


def check_summary_quality(summary: str) -> int:
    if not summary:
        return 0

    score = 0
    length = len(summary)

    if length >= 20:
        score = int((length / 50) * 25)
        if score > 25:
            score = 25

    summary_lower = summary.lower()
    keyword_count = sum(1 for kw in TECH_KEYWORDS if kw in summary_lower)
    bonus = min(keyword_count, 3)
    score = min(score + bonus, 25)

    return score


def check_technical_depth(data: dict[str, Any]) -> int:
    score_value = data.get("score", 1)
    if isinstance(score_value, (int, float)):
        score_value = max(1, min(10, score_value))
        return int((score_value / 10) * 25)
    return 0


def check_format(data: dict[str, Any]) -> int:
    score = 0
    required_fields = [
        ("id", str),
        ("title", str),
        ("url", str),
        ("status", str),
        ("timestamp", str),
    ]

    for field, expected_type in required_fields:
        if field in data and isinstance(data[field], expected_type) and data[field]:
            score += 4

    return score


def check_tags(tags: list[Any]) -> int:
    if not tags or not isinstance(tags, list):
        return 0

    count = len(tags)
    valid_count = sum(1 for tag in tags if isinstance(tag, str) and tag.lower() in STANDARD_TAGS)

    if count == 0:
        return 0
    elif 1 <= count <= 3:
        ratio = valid_count / count
        return int(ratio * 15)
    else:
        ratio = valid_count / count
        return int(ratio * 10)


def check_empty_words(summary: str) -> int:
    if not summary:
        return 0

    summary_lower = summary.lower()

    for word in EMPTY_WORDS_CN:
        if word in summary_lower:
            return 0

    for word in EMPTY_WORDS_EN:
        if word in summary_lower:
            return 0

    return 15


def load_json_file(file_path: Path) -> dict[str, Any] | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return None


def calculate_quality_report(file_path: Path, data: dict[str, Any]) -> QualityReport:
    summary = data.get("summary", "")
    tags = data.get("tags", [])

    return QualityReport(
        file_path=str(file_path),
        id=data.get("id", ""),
        summary_quality=check_summary_quality(summary),
        technical_depth=check_technical_depth(data),
        format_compliance=check_format(data),
        tag_precision=check_tags(tags),
        empty_words_check=check_empty_words(summary),
    )


def expand_files(paths: list[Path]) -> list[Path]:
    expanded = []
    for path in paths:
        if "*" in str(path) or "?" in str(path) or "[" in str(path):
            expanded.extend(path.parent.glob(path.name))
        else:
            expanded.append(path)
    return expanded


def show_progress_bar(current: int, total: int, width: int = 40) -> None:
    if total <= 1:
        return

    progress = current / total
    filled = int(width * progress)
    bar = "#" * filled + "-" * (width - filled)
    percent = int(progress * 100)
    sys.stdout.write(f"\r[{bar}] {percent}% ({current}/{total})")
    sys.stdout.flush()


def display_report(report: QualityReport) -> None:
    total = report.total_score()
    grade = report.grade()

    print(f"\n{'='*70}")
    print(f"File: {report.file_path}")
    print(f"ID: {report.id}")
    print(f"{'─'*70}")

    for dim in report.dimensions():
        status = "[+]" if dim.score > 0 else "[ ]"
        bar_width = 20
        filled = int((dim.score / dim.max_score) * bar_width)
        bar = "#" * filled + "-" * (bar_width - filled)
        print(f"{status} {dim.name:20s}: [{bar}] {dim.score:2d}/{dim.max_score}")

    print(f"{'-'*70}")
    print(f"Total Score: {total}/100  Grade: [{grade}]")
    print(f"{'='*70}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check quality of knowledge entry JSON files")
    parser.add_argument("files", nargs="+", type=Path, help="JSON file(s) to check (supports wildcards)")
    args = parser.parse_args()

    file_paths = expand_files(args.files)

    if not file_paths:
        print("Error: No files found matching the given patterns", file=sys.stderr)
        return 1

    reports = []

    print(f"Checking {len(file_paths)} file(s)...")

    for i, file_path in enumerate(file_paths):
        show_progress_bar(i + 1, len(file_paths))

        data = load_json_file(file_path)
        if data is None:
            continue

        report = calculate_quality_report(file_path, data)
        reports.append(report)

    print()

    has_c_grade = False
    for report in reports:
        display_report(report)
        if report.grade() == "C":
            has_c_grade = True

    if not reports:
        print("No valid files to process")
        return 1

    total_score = sum(r.total_score() for r in reports)
    avg_score = total_score / len(reports)
    grade_count = {"A": 0, "B": 0, "C": 0}
    for r in reports:
        grade_count[r.grade()] += 1

    print(f"{'='*70}")
    print(f"Summary: {len(reports)} file(s) processed")
    print(f"Average Score: {avg_score:.1f}/100")
    print(f"Grade Distribution: A={grade_count['A']}  B={grade_count['B']}  C={grade_count['C']}")
    print(f"{'='*70}")

    if has_c_grade:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
