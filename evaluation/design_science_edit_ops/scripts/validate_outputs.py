#!/usr/bin/env python3
"""Validate raw benchmark model outputs.

This Phase 3 validator compares one model output directory against a benchmark
task JSONL file and writes row-level validation results to CSV. It performs only
lightweight checks: JSON parsing, schema/field checks, expected API call,
target-slide checks, minimum argument completeness, traceability, and a simple
replay-success proxy. It does not call any LLM, API, or LISA pipeline code.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_API_CALLS = {
    "edit_content",
    "edit_slide",
    "set_layout",
    "move_slide",
    "insert_slide_after",
    "delete_slide",
    "set_image",
}

CSV_FIELDS = [
    "model",
    "task_id",
    "output_file_exists",
    "json_valid",
    "schema_valid",
    "api_call_valid",
    "api_call_correct",
    "slide_target_valid",
    "slide_target_correct",
    "argument_complete",
    "traceability_complete",
    "replay_applicable",
    "replay_check_skipped",
    "replay_success",
    "validation_passed",
    "error_message",
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments with repo-root friendly defaults."""
    parser = argparse.ArgumentParser(
        description="Validate Design Science slide-edit benchmark outputs."
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_pilot.jsonl",
        help="Benchmark task JSONL file.",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=BENCHMARK_ROOT / "outputs" / "fake_model",
        help="Directory containing one JSON output file per task.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=BENCHMARK_ROOT / "schemas" / "edit_operation_schema.json",
        help="JSON schema file for expected model output.",
    )
    parser.add_argument(
        "--model",
        default="fake_model",
        help="Model name to write in the CSV output.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "raw_results_pilot_fake.csv",
        help="Output CSV path.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    """Load a JSON file."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_tasks(path: Path) -> List[Dict[str, Any]]:
    """Load benchmark tasks from JSONL."""
    tasks: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                task = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid task JSONL: {exc}") from exc
            if not isinstance(task, dict):
                raise ValueError(f"{path}:{line_no}: expected task object")
            tasks.append(task)
    return tasks


def parse_model_output(path: Path) -> Tuple[Optional[Dict[str, Any]], bool, str]:
    """Parse one model output file as a JSON object.

    Returns ``(parsed_object, json_valid, error_message)``.
    """
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        return None, False, f"not valid JSON: {exc.msg}"
    except OSError as exc:
        return None, False, str(exc)
    if not isinstance(data, dict):
        return None, False, "JSON output is not an object"
    return data, True, ""


def validate_with_jsonschema(data: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate with jsonschema if installed."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return fallback_schema_check(data, schema)

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        prefix = f"{path}: " if path else ""
        return False, f"schema validation failed: {prefix}{exc.message}"
    except jsonschema.SchemaError as exc:
        return False, f"schema file is invalid: {exc.message}"
    return True, ""


def fallback_schema_check(data: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, str]:
    """Minimal schema validation used when jsonschema is unavailable."""
    required = schema.get("required") or []
    missing = [field for field in required if field not in data]
    if missing:
        return False, f"missing required field(s): {', '.join(missing)}"

    api_call = data.get("api_call")
    if not isinstance(api_call, str) or api_call not in ALLOWED_API_CALLS:
        return False, "api_call is missing or not allowed"

    if "slide_no" in data and data.get("slide_no") is not None and not isinstance(data.get("slide_no"), int):
        return False, "slide_no must be an integer or null"

    if not isinstance(data.get("arguments"), dict):
        return False, "arguments must be an object"

    if not isinstance(data.get("reason"), str) or not data.get("reason").strip():
        return False, "reason must be a non-empty string"

    if data.get("review_status") != "pending":
        return False, "review_status must be pending"

    allowed_properties = set((schema.get("properties") or {}).keys())
    extra = sorted(set(data.keys()) - allowed_properties)
    if schema.get("additionalProperties") is False and extra:
        return False, f"unexpected field(s): {', '.join(extra)}"

    return True, ""


def existing_slide_numbers(task: Dict[str, Any]) -> set[int]:
    """Return slide numbers present in a benchmark task deck_state."""
    slides = ((task.get("deck_state") or {}).get("slides") or [])
    return {
        slide.get("slide_no")
        for slide in slides
        if isinstance(slide, dict) and isinstance(slide.get("slide_no"), int)
    }


def is_slide_target_valid(task: Dict[str, Any], output: Optional[Dict[str, Any]]) -> bool:
    """Check whether the output slide_no is valid for this task."""
    if not output:
        return False

    slide_no = output.get("slide_no")
    existing = existing_slide_numbers(task)
    return isinstance(slide_no, int) and slide_no in existing


def is_slide_target_correct(task: Dict[str, Any], output: Optional[Dict[str, Any]]) -> bool:
    """Check whether the output slide_no matches the expected target."""
    if not output:
        return False

    expected = task.get("expected_slide_no")
    actual = output.get("slide_no")
    return actual == expected


def has_any_key(arguments: Dict[str, Any], keys: Iterable[str]) -> bool:
    """True when arguments contains at least one present key."""
    return any(key in arguments and arguments[key] not in (None, "", []) for key in keys)


def has_complete_replace_slide(arguments: Dict[str, Any]) -> bool:
    """Check for a non-empty concrete slide replacement payload."""
    replace_slide = arguments.get("replace_slide")
    if not isinstance(replace_slide, dict) or not replace_slide:
        return False
    replacement_fields = ("title", "bullets", "body", "content")
    return any(
        field in replace_slide and replace_slide[field] not in (None, "", [], {})
        for field in replacement_fields
    )


def is_argument_complete(output: Optional[Dict[str, Any]], slide_target_valid: bool) -> bool:
    """Check operation-specific minimum argument completeness."""
    if not output:
        return False

    arguments = output.get("arguments")
    if not isinstance(arguments, dict):
        return False

    api_call = output.get("api_call")
    if api_call == "edit_content":
        return has_any_key(
            arguments, ("instruction", "new_content", "target")
        ) or has_complete_replace_slide(arguments)
    if api_call == "edit_slide":
        return has_any_key(
            arguments, ("instruction", "title", "new_title")
        ) or has_complete_replace_slide(arguments)
    if api_call == "set_layout":
        return has_any_key(arguments, ("layout",))
    if api_call == "move_slide":
        return has_any_key(
            arguments,
            (
                "new_position",
                "after_slide_no",
                "before_slide_no",
                "relation",
                "reference_slide_no",
                "reference_slide_role",
            ),
        )
    if api_call == "insert_slide_after":
        return has_any_key(arguments, ("after_slide_no", "new_slide", "title", "instruction"))
    if api_call == "delete_slide":
        return slide_target_valid
    if api_call == "set_image":
        return has_any_key(arguments, ("image_prompt", "image_intent", "description", "instruction"))
    return False


def is_traceability_complete(output: Optional[Dict[str, Any]]) -> bool:
    """Check minimum traceability fields."""
    if not output:
        return False
    reason = output.get("reason")
    return isinstance(reason, str) and bool(reason.strip()) and output.get("review_status") == "pending"


def validate_task_output(
    task: Dict[str, Any],
    outputs_dir: Path,
    schema: Dict[str, Any],
    model_name: str,
) -> Dict[str, Any]:
    """Validate the output file for one benchmark task."""
    task_id = str(task.get("task_id", ""))
    output_path = outputs_dir / f"{task_id}.json"
    output_exists = output_path.exists()
    replay_applicable = bool(task.get("replay_applicable"))
    replay_check_skipped = not replay_applicable

    row: Dict[str, Any] = {
        "model": model_name,
        "task_id": task_id,
        "output_file_exists": output_exists,
        "json_valid": False,
        "schema_valid": False,
        "api_call_valid": False,
        "api_call_correct": False,
        "slide_target_valid": False,
        "slide_target_correct": False,
        "argument_complete": False,
        "traceability_complete": False,
        "replay_applicable": replay_applicable,
        "replay_check_skipped": replay_check_skipped,
        "replay_success": "NA" if replay_check_skipped else False,
        "validation_passed": False,
        "error_message": "",
    }

    if not output_exists:
        row["error_message"] = f"missing output file: {output_path}"
        return row

    output, json_valid, parse_error = parse_model_output(output_path)
    row["json_valid"] = json_valid
    if not json_valid:
        row["error_message"] = parse_error or "not valid JSON"
        return row

    assert output is not None
    schema_valid, schema_error = validate_with_jsonschema(output, schema)
    row["schema_valid"] = schema_valid
    row["api_call_valid"] = output.get("api_call") in ALLOWED_API_CALLS
    row["api_call_correct"] = output.get("api_call") == task.get("expected_api_call")
    row["slide_target_valid"] = is_slide_target_valid(task, output)
    row["slide_target_correct"] = is_slide_target_correct(task, output)
    row["argument_complete"] = is_argument_complete(output, bool(row["slide_target_valid"]))
    row["traceability_complete"] = is_traceability_complete(output)

    if not replay_check_skipped:
        row["replay_success"] = bool(
            row["json_valid"]
            and row["schema_valid"]
            and row["api_call_valid"]
            and row["slide_target_valid"]
            and row["argument_complete"]
        )

    if replay_applicable:
        row["validation_passed"] = bool(
            row["json_valid"]
            and row["schema_valid"]
            and row["api_call_valid"]
            and row["api_call_correct"]
            and row["slide_target_valid"]
            and row["slide_target_correct"]
            and row["argument_complete"]
            and row["traceability_complete"]
            and row["replay_success"] is True
        )
    else:
        row["validation_passed"] = bool(
            row["json_valid"]
            and row["schema_valid"]
            and row["api_call_valid"]
            and row["api_call_correct"]
            and row["slide_target_correct"]
            and row["argument_complete"]
            and row["traceability_complete"]
        )

    errors = []
    if schema_error:
        errors.append(schema_error)
    if not row["api_call_valid"]:
        errors.append("api_call is not allowed")
    elif not row["api_call_correct"]:
        errors.append(
            f"api_call mismatch: expected {task.get('expected_api_call')}, got {output.get('api_call')}"
        )
    if not row["slide_target_valid"]:
        errors.append("slide target is invalid")
    elif not row["slide_target_correct"]:
        errors.append(
            f"slide_no mismatch: expected {task.get('expected_slide_no')}, got {output.get('slide_no')}"
        )
    if not row["argument_complete"]:
        errors.append("minimum arguments are incomplete")
    if not row["traceability_complete"]:
        errors.append("reason/review_status traceability is incomplete")
    row["error_message"] = "; ".join(errors)

    return row


def csv_value(value: Any) -> Any:
    """Normalize Python values for a simple CSV report."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    """Write validation rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in CSV_FIELDS})


def print_summary(rows: List[Dict[str, Any]], out_path: Path) -> None:
    """Print a short run summary."""
    print(f"tasks: {len(rows)}")
    print(f"output_files_found: {sum(1 for row in rows if row['output_file_exists'])}")
    print(f"json_valid: {sum(1 for row in rows if row['json_valid'])}")
    print(f"validation_passed: {sum(1 for row in rows if row['validation_passed'])}")
    print(f"output_csv: {out_path}")


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    tasks = load_tasks(args.tasks)
    schema = load_json(args.schema)
    rows = [
        validate_task_output(task, args.outputs, schema, args.model)
        for task in tasks
    ]
    write_csv(rows, args.out)
    print_summary(rows, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
