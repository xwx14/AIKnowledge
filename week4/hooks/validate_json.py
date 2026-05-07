#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "id": str,
    "title": str,
    "url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUS_VALUES = {"draft", "review", "published", "archived"}
VALID_AUDIENCE_VALUES = {"beginner", "intermediate", "advanced"}

ID_PATTERN = re.compile(r"^[^-]+-(\d{8})-(\d{3})$")
URL_PATTERN = re.compile(r"^https?://.+")


def validate_id_format(value: str) -> list[str]:
    errors = []
    if not ID_PATTERN.match(value):
        errors.append(f"Invalid ID format: '{value}'. Expected format: {{source}}-{{YYYYMMDD}}-{{NNN}}")
    return errors


def validate_status(value: str) -> list[str]:
    errors = []
    if value not in VALID_STATUS_VALUES:
        errors.append(f"Invalid status: '{value}'. Must be one of: {', '.join(sorted(VALID_STATUS_VALUES))}")
    return errors


def validate_url(value: str) -> list[str]:
    errors = []
    if not URL_PATTERN.match(value):
        errors.append(f"Invalid URL format: '{value}'. Must start with http:// or https://")
    return errors


def validate_summary(value: str) -> list[str]:
    errors = []
    if len(value) < 20:
        errors.append(f"Summary too short: {len(value)} characters. Minimum: 20 characters")
    return errors


def validate_tags(value: list) -> list[str]:
    errors = []
    if len(value) < 1:
        errors.append(f"Tags list empty. At least 1 tag required")
    return errors


def validate_score(value: Any) -> list[str]:
    errors = []
    if not isinstance(value, (int, float)):
        errors.append(f"Score must be a number, got {type(value).__name__}")
    elif not 1 <= value <= 10:
        errors.append(f"Score out of range: {value}. Must be between 1 and 10")
    return errors


def validate_audience(value: Any) -> list[str]:
    errors = []
    if not isinstance(value, str):
        errors.append(f"Audience must be a string, got {type(value).__name__}")
    elif value not in VALID_AUDIENCE_VALUES:
        errors.append(f"Invalid audience: '{value}'. Must be one of: {', '.join(sorted(VALID_AUDIENCE_VALUES))}")
    return errors


def validate_json_file(file_path: Path) -> list[str]:
    errors = []

    if not file_path.exists():
        return [f"File not found: {file_path}"]

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON parse error in {file_path}: {e.msg} at line {e.lineno} column {e.colno}"]
    except Exception as e:
        return [f"Error reading file {file_path}: {e}"]

    for field_name, field_type in REQUIRED_FIELDS.items():
        if field_name not in data:
            errors.append(f"Missing required field: '{field_name}'")
        elif not isinstance(data[field_name], field_type):
            errors.append(
                f"Field '{field_name}' has incorrect type: expected {field_type.__name__}, got {type(data[field_name]).__name__}"
            )

    missing_required = any(f.startswith("Missing required field") for f in errors)
    if missing_required:
        return errors

    errors.extend(validate_id_format(data["id"]))
    errors.extend(validate_status(data["status"]))
    errors.extend(validate_url(data["url"]))
    errors.extend(validate_summary(data["summary"]))
    errors.extend(validate_tags(data["tags"]))

    if "score" in data:
        errors.extend(validate_score(data["score"]))

    if "audience" in data:
        errors.extend(validate_audience(data["audience"]))

    return errors


def expand_files(paths: list[Path]) -> list[Path]:
    expanded = []
    for path in paths:
        if "*" in str(path) or "?" in str(path) or "[" in str(path):
            expanded.extend(path.parent.glob(path.name))
        else:
            expanded.append(path)
    return expanded


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate knowledge entry JSON files")
    parser.add_argument("files", nargs="+", type=Path, help="JSON file(s) to validate (supports wildcards)")
    args = parser.parse_args()

    file_paths = expand_files(args.files)

    if not file_paths:
        print("Error: No files found matching the given patterns", file=sys.stderr)
        return 1

    all_errors = {}
    for file_path in file_paths:
        errors = validate_json_file(file_path)
        if errors:
            all_errors[str(file_path)] = errors

    if all_errors:
        for file_path, errors in all_errors.items():
            print(f"\n{file_path}:")
            for error in errors:
                print(f"  - {error}")

        total_errors = sum(len(errors) for errors in all_errors.values())
        total_files = len(file_paths)
        failed_files = len(all_errors)

        print(f"\nSummary: {total_errors} error(s) in {failed_files}/{total_files} file(s)")
        return 1
    else:
        print(f"All {len(file_paths)} file(s) valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
