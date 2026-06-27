#!/usr/bin/env python3
"""Render model inputs for the Design Science edit-operation benchmark.

This Phase 5A script turns benchmark tasks plus the shared prompt template into
rendered prompts and chat-style message records. It prepares inputs only; it
does not run models, call APIs, or import inference libraries.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
DECK_STATE_PLACEHOLDER = "{deck_state}"
USER_REQUEST_PLACEHOLDER = "{user_request}"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments with repository-root friendly defaults."""
    parser = argparse.ArgumentParser(
        description="Render benchmark task prompts for model-input preparation."
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_pilot.jsonl",
        help="Benchmark task JSONL file.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=BENCHMARK_ROOT / "prompts" / "edit_operation_prompt.txt",
        help="Prompt template text file.",
    )
    parser.add_argument(
        "--out-jsonl",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "rendered_prompts_pilot.jsonl",
        help="Output rendered prompt JSONL path.",
    )
    parser.add_argument(
        "--out-preview",
        type=Path,
        default=BENCHMARK_ROOT / "report" / "prompt_preview_pilot.md",
        help="Output Markdown preview path.",
    )
    parser.add_argument(
        "--preview-count",
        type=int,
        default=3,
        help="Number of rendered prompts to include in the Markdown preview.",
    )
    return parser.parse_args()


def read_template(path: Path) -> str:
    """Read and sanity-check the shared prompt template."""
    if not path.exists():
        raise FileNotFoundError(f"template file does not exist: {path}")
    template = path.read_text(encoding="utf-8")
    missing = [
        placeholder
        for placeholder in (DECK_STATE_PLACEHOLDER, USER_REQUEST_PLACEHOLDER)
        if placeholder not in template
    ]
    if missing:
        raise ValueError(f"template is missing placeholder(s): {', '.join(missing)}")
    return template


def load_tasks(path: Path) -> List[Dict[str, Any]]:
    """Load benchmark tasks from JSONL and validate required task fields."""
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
            require_task_fields(task, path, line_no)
            tasks.append(task)
    return tasks


def require_task_fields(task: Dict[str, Any], path: Path, line_no: int) -> None:
    """Fail clearly if a task is missing fields needed for prompt rendering."""
    required = ("task_id", "deck_state", "user_request")
    missing = [field for field in required if field not in task]
    if missing:
        raise ValueError(f"{path}:{line_no}: missing required field(s): {', '.join(missing)}")
    if not isinstance(task["task_id"], str) or not task["task_id"].strip():
        raise ValueError(f"{path}:{line_no}: task_id must be a non-empty string")
    if not isinstance(task["deck_state"], dict):
        raise ValueError(f"{path}:{line_no}: deck_state must be an object")
    if not isinstance(task["user_request"], str) or not task["user_request"].strip():
        raise ValueError(f"{path}:{line_no}: user_request must be a non-empty string")


def render_prompt(template: str, task: Dict[str, Any]) -> str:
    """Render one task into the shared prompt template."""
    deck_state_json = json.dumps(task["deck_state"], indent=2, ensure_ascii=False)
    rendered = template.replace(DECK_STATE_PLACEHOLDER, deck_state_json)
    rendered = rendered.replace(USER_REQUEST_PLACEHOLDER, task["user_request"])

    unresolved = [
        placeholder
        for placeholder in (DECK_STATE_PLACEHOLDER, USER_REQUEST_PLACEHOLDER)
        if placeholder in rendered
    ]
    if unresolved:
        raise ValueError(
            f"{task['task_id']}: rendered prompt still contains unresolved placeholder(s): "
            f"{', '.join(unresolved)}"
        )
    return rendered


def build_rendered_record(task: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Build one JSONL record for model-input preparation."""
    return {
        "task_id": task["task_id"],
        "deck_id": task.get("deck_id"),
        "operation_group": task.get("operation_group"),
        "expected_api_call": task.get("expected_api_call"),
        "expected_slide_no": task.get("expected_slide_no"),
        "replay_applicable": task.get("replay_applicable"),
        "prompt": prompt,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }


def render_records(tasks: List[Dict[str, Any]], template: str) -> List[Dict[str, Any]]:
    """Render all benchmark tasks into model-input records."""
    records = [build_rendered_record(task, render_prompt(template, task)) for task in tasks]
    if len(records) != len(tasks):
        raise RuntimeError("rendered record count does not match task count")
    return records


def write_jsonl(records: List[Dict[str, Any]], path: Path) -> None:
    """Write rendered prompt records as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_preview(records: List[Dict[str, Any]], path: Path, preview_count: int) -> None:
    """Write a readable Markdown preview of the first rendered prompts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    selected = records[: max(0, preview_count)]
    lines = ["# Prompt Preview - Pilot Benchmark", ""]

    for record in selected:
        lines.extend(
            [
                f"## {record['task_id']}",
                "",
                f"Expected API call: {record.get('expected_api_call')}",
                f"Expected slide: {record.get('expected_slide_no')}",
                "",
                "```text",
                record["prompt"],
                "```",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    template = read_template(args.template)
    tasks = load_tasks(args.tasks)
    records = render_records(tasks, template)
    write_jsonl(records, args.out_jsonl)
    write_preview(records, args.out_preview, args.preview_count)

    print(f"tasks_loaded: {len(tasks)}")
    print(f"prompts_rendered: {len(records)}")
    print(f"jsonl_written: {args.out_jsonl}")
    print(f"preview_written: {args.out_preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
