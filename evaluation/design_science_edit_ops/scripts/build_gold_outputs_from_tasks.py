#!/usr/bin/env python3
"""Build deterministic validator smoke-test outputs from benchmark gold labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_OPERATIONS = {
    "edit_content",
    "edit_slide",
    "set_layout",
    "move_slide",
    "insert_slide_after",
    "delete_slide",
    "set_image",
}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse gold-output builder options."""
    parser = argparse.ArgumentParser(
        description="Create deterministic validator-compatible outputs from task labels."
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_final_50.jsonl",
        help="Benchmark task JSONL containing expected labels.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BENCHMARK_ROOT / "outputs" / "gold_final_50",
        help="Directory for one gold output JSON file per task.",
    )
    return parser.parse_args(argv)


def load_tasks(path: Path) -> List[Dict[str, Any]]:
    """Load task objects from JSONL."""
    if not path.exists():
        raise FileNotFoundError(f"task file does not exist: {path}")
    tasks: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                task = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(task, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            if not isinstance(task.get("task_id"), str) or not task["task_id"].strip():
                raise ValueError(f"{path}:{line_no}: missing task_id")
            tasks.append(task)
    if not tasks:
        raise ValueError(f"task file contains no tasks: {path}")
    return tasks


def gold_arguments(task: Mapping[str, Any]) -> Dict[str, Any]:
    """Build minimal operation-specific arguments accepted by the validator."""
    operation = task.get("expected_api_call")
    expected = task.get("expected_arguments")
    arguments = dict(expected) if isinstance(expected, dict) else {}

    if operation == "edit_content":
        arguments.setdefault("target", "bullets")
        arguments.setdefault(
            "instruction", "Apply only the requested bullet-content edit and preserve constraints."
        )
    elif operation == "edit_slide":
        arguments.setdefault(
            "instruction", "Apply only the requested title or slide-framing edit."
        )
    elif operation == "set_layout":
        arguments.setdefault("layout", "TitleBullets")
    elif operation == "move_slide":
        if not any(key in arguments for key in ("after_slide_no", "before_slide_no", "new_position")):
            raise ValueError(f"{task.get('task_id')}: move_slide lacks expected destination")
    elif operation == "insert_slide_after":
        arguments.setdefault("after_slide_no", task.get("expected_slide_no"))
        arguments.setdefault("title", "Transition")
        arguments.setdefault("instruction", "Connect the surrounding sections briefly.")
    elif operation == "delete_slide":
        arguments = {}
    elif operation == "set_image":
        arguments.setdefault("image_intent", "decorative")
        arguments.setdefault("instruction", "Add a relevant conceptual visual only.")
    else:
        raise ValueError(f"{task.get('task_id')}: unsupported expected operation: {operation}")
    return arguments


def build_gold_output(task: Mapping[str, Any]) -> Dict[str, Any]:
    """Build one minimal schema-shaped gold output."""
    operation = task.get("expected_api_call")
    if operation not in SUPPORTED_OPERATIONS:
        raise ValueError(f"{task.get('task_id')}: unsupported expected operation: {operation}")
    slide_no = task.get("expected_slide_no")
    if not isinstance(slide_no, int):
        raise ValueError(f"{task.get('task_id')}: expected_slide_no must be an integer")
    return {
        "api_call": operation,
        "slide_no": slide_no,
        "arguments": gold_arguments(task),
        "reason": "Deterministic gold output for validator compatibility testing.",
        "review_status": "pending",
    }


def write_output(path: Path, payload: Mapping[str, Any]) -> None:
    """Write one pretty-printed gold JSON output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Build all gold outputs."""
    args = parse_args(argv)
    tasks = load_tasks(args.tasks)
    for task in tasks:
        write_output(args.out_dir / f"{task['task_id']}.json", build_gold_output(task))
    print(f"tasks: {len(tasks)}")
    print(f"outputs_written: {len(tasks)}")
    print(f"output_directory: {args.out_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
