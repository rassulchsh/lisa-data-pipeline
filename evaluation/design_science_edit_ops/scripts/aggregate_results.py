#!/usr/bin/env python3
"""Aggregate Design Science benchmark validation results.

This Phase 4 script reads row-level validation CSV output from
``validate_outputs.py`` and produces compact summary tables by model and by
gold expected API call. It does not run models, call APIs, score free text, or
create charts.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]

MODEL_FIELDS = [
    "model",
    "total_tasks",
    "outputs_found",
    "missing_outputs",
    "json_valid_rate",
    "schema_valid_rate",
    "api_call_valid_rate",
    "api_call_accuracy",
    "slide_target_valid_rate",
    "slide_target_accuracy",
    "argument_complete_rate",
    "traceability_complete_rate",
    "replay_success_rate",
    "validation_pass_rate",
]

API_CALL_FIELDS = [
    "expected_api_call",
    "total_tasks",
    "outputs_found",
    "json_valid_rate",
    "schema_valid_rate",
    "api_call_accuracy",
    "slide_target_accuracy",
    "argument_complete_rate",
    "traceability_complete_rate",
    "replay_success_rate",
    "validation_pass_rate",
]

API_CALL_ORDER = [
    "edit_content",
    "edit_slide",
    "set_layout",
    "move_slide",
    "insert_slide_after",
    "delete_slide",
    "set_image",
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments with repository-root friendly defaults."""
    parser = argparse.ArgumentParser(
        description="Aggregate Design Science benchmark raw validation CSV files."
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "raw_results_pilot_fake.csv",
        help="Raw row-level validation CSV.",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_pilot.jsonl",
        help="Benchmark task JSONL file used to join expected API calls.",
    )
    parser.add_argument(
        "--out-model",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "summary_by_model_pilot_fake.csv",
        help="Output CSV path for model-level summary.",
    )
    parser.add_argument(
        "--out-api-call",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "summary_by_api_call_pilot_fake.csv",
        help="Output CSV path for expected-API-call summary.",
    )
    return parser.parse_args()


def parse_bool(value: Any) -> bool:
    """Parse CSV boolean-ish strings.

    ``NA`` and empty values parse as ``False`` for ordinary boolean counts. For
    replay metrics, not-applicability is handled by the replay_applicable field.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"true", "1", "yes", "y"}


def load_raw_rows(path: Path) -> List[Dict[str, str]]:
    """Load raw validation rows from CSV."""
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_expected_api_calls(path: Path) -> Dict[str, str]:
    """Load task_id -> expected_api_call from benchmark task JSONL."""
    mapping: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            task = json.loads(line)
            if not isinstance(task, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            task_id = task.get("task_id")
            expected = task.get("expected_api_call")
            if isinstance(task_id, str) and isinstance(expected, str):
                mapping[task_id] = expected
    return mapping


def rate(rows: Iterable[Mapping[str, Any]], field: str, denominator: int) -> str:
    """Return true-count / denominator as a formatted rate."""
    if denominator <= 0:
        return "NA"
    numerator = sum(1 for row in rows if parse_bool(row.get(field)))
    return format_rate(numerator, denominator)


def replay_success_rate(rows: List[Mapping[str, Any]]) -> str:
    """Calculate replay success only over replay-applicable rows."""
    replay_rows = [row for row in rows if parse_bool(row.get("replay_applicable"))]
    if not replay_rows:
        return "NA"
    success_count = sum(1 for row in replay_rows if parse_bool(row.get("replay_success")))
    return format_rate(success_count, len(replay_rows))


def format_rate(numerator: int, denominator: int) -> str:
    """Format a rate compactly but consistently for CSV output."""
    if denominator <= 0:
        return "NA"
    return f"{numerator / denominator:.4f}"


def summarize_model(model: str, rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """Build one model-level summary row."""
    total = len(rows)
    outputs_found = sum(1 for row in rows if parse_bool(row.get("output_file_exists")))
    return {
        "model": model,
        "total_tasks": total,
        "outputs_found": outputs_found,
        "missing_outputs": total - outputs_found,
        "json_valid_rate": rate(rows, "json_valid", total),
        "schema_valid_rate": rate(rows, "schema_valid", total),
        "api_call_valid_rate": rate(rows, "api_call_valid", total),
        "api_call_accuracy": rate(rows, "api_call_correct", total),
        "slide_target_valid_rate": rate(rows, "slide_target_valid", total),
        "slide_target_accuracy": rate(rows, "slide_target_correct", total),
        "argument_complete_rate": rate(rows, "argument_complete", total),
        "traceability_complete_rate": rate(rows, "traceability_complete", total),
        "replay_success_rate": replay_success_rate(rows),
        "validation_pass_rate": rate(rows, "validation_passed", total),
    }


def summarize_api_call(expected_api_call: str, rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """Build one expected-API-call summary row."""
    total = len(rows)
    outputs_found = sum(1 for row in rows if parse_bool(row.get("output_file_exists")))
    return {
        "expected_api_call": expected_api_call,
        "total_tasks": total,
        "outputs_found": outputs_found,
        "json_valid_rate": rate(rows, "json_valid", total),
        "schema_valid_rate": rate(rows, "schema_valid", total),
        "api_call_accuracy": rate(rows, "api_call_correct", total),
        "slide_target_accuracy": rate(rows, "slide_target_correct", total),
        "argument_complete_rate": rate(rows, "argument_complete", total),
        "traceability_complete_rate": rate(rows, "traceability_complete", total),
        "replay_success_rate": replay_success_rate(rows),
        "validation_pass_rate": rate(rows, "validation_passed", total),
    }


def group_by(rows: Iterable[Dict[str, str]], field: str) -> Dict[str, List[Dict[str, str]]]:
    """Group raw CSV rows by a field."""
    groups: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row.get(field, "")].append(row)
    return dict(groups)


def attach_expected_api_calls(
    rows: List[Dict[str, str]],
    expected_by_task: Mapping[str, str],
) -> List[Dict[str, str]]:
    """Return rows with expected_api_call joined from task metadata."""
    joined: List[Dict[str, str]] = []
    for row in rows:
        copy = dict(row)
        copy["expected_api_call"] = expected_by_task.get(copy.get("task_id", ""), "unknown")
        joined.append(copy)
    return joined


def sorted_api_keys(keys: Iterable[str]) -> List[str]:
    """Sort API-call keys in benchmark vocabulary order, then alphabetically."""
    order = {name: idx for idx, name in enumerate(API_CALL_ORDER)}
    return sorted(keys, key=lambda key: (order.get(key, len(order)), key))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    """Write summary rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    raw_rows = load_raw_rows(args.raw)
    expected_by_task = load_expected_api_calls(args.tasks)

    by_model = group_by(raw_rows, "model")
    model_rows = [
        summarize_model(model, rows)
        for model, rows in sorted(by_model.items())
    ]

    joined_rows = attach_expected_api_calls(raw_rows, expected_by_task)
    by_api_call = group_by(joined_rows, "expected_api_call")
    api_call_rows = [
        summarize_api_call(api_call, by_api_call[api_call])
        for api_call in sorted_api_keys(by_api_call)
    ]

    write_csv(args.out_model, model_rows, MODEL_FIELDS)
    write_csv(args.out_api_call, api_call_rows, API_CALL_FIELDS)

    print(f"raw_rows: {len(raw_rows)}")
    print(f"models: {len(by_model)}")
    print(f"api_call_groups: {len(by_api_call)}")
    print(f"summary_by_model_csv: {args.out_model}")
    print(f"summary_by_api_call_csv: {args.out_api_call}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
