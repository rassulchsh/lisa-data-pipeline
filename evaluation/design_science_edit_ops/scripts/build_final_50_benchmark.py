#!/usr/bin/env python3
"""Build the frozen 50-task benchmark from held-out editing examples.

The finalized export intentionally contains message-only training rows, while
its adjacent statistics file retains split and source-deck provenance. This
builder pairs those files by their validated export order, reconstructs compact
deck states from the verified healed source decks, excludes pilot/train source
identifiers, and deterministically selects the requested operation mix.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_OPERATIONS = (
    "edit_content",
    "edit_slide",
    "set_layout",
    "move_slide",
    "insert_slide_after",
    "delete_slide",
    "set_image",
)
TARGET_OPERATION_COUNTS = {
    "edit_content": 12,
    "edit_slide": 8,
    "set_layout": 7,
    "move_slide": 7,
    "insert_slide_after": 6,
    "delete_slide": 5,
    "set_image": 5,
}
TARGET_DIFFICULTY_BY_OPERATION = {
    "edit_content": {"easy": 2, "medium": 6, "hard": 4},
    "edit_slide": {"easy": 2, "medium": 4, "hard": 2},
    "set_layout": {"easy": 2, "medium": 3, "hard": 2},
    "move_slide": {"easy": 1, "medium": 3, "hard": 3},
    "insert_slide_after": {"easy": 1, "medium": 3, "hard": 2},
    "delete_slide": {"easy": 1, "medium": 3, "hard": 1},
    "set_image": {"easy": 1, "medium": 3, "hard": 1},
}
TARGET_DIFFICULTY_COUNTS = {"easy": 10, "medium": 25, "hard": 15}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse repository-root-friendly builder options."""
    parser = argparse.ArgumentParser(
        description="Build the held-out final 50-task slide-edit benchmark."
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="Finalized dataset export directory; auto-detected by default.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="Root containing the export's batches/<batch>/healed source paths.",
    )
    parser.add_argument(
        "--pilot",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_pilot.jsonl",
        help="Frozen pilot task file whose source identifiers must be excluded.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_final_50.jsonl",
        help="Final benchmark JSONL output path.",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=BENCHMARK_ROOT / "report" / "final_50_benchmark_audit.md",
        help="Markdown audit report output path.",
    )
    parser.add_argument(
        "--distribution",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "final_50_task_distribution.csv",
        help="Operation/difficulty distribution CSV output path.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Selection seed.")
    parser.add_argument(
        "--allow-leakage",
        action="store_true",
        help="Allow final source identifiers also found in train (disabled by default).",
    )
    return parser.parse_args(argv)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL file and require object rows."""
    if not path.exists():
        raise FileNotFoundError(f"required JSONL file does not exist: {path}")
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            rows.append(row)
    if not rows:
        raise ValueError(f"JSONL file contains no rows: {path}")
    return rows


def find_export_dir(explicit: Optional[Path]) -> Path:
    """Locate the finalized message export without falling back to train data."""
    candidates = (
        [explicit]
        if explicit is not None
        else [
            REPO_ROOT / "dataset" / "exports" / "finlized_combined_training_v1",
            REPO_ROOT / "dataset" / "exports" / "finalized_combined_training_v1",
        ]
    )
    required = (
        "combined_dialogues_validation.jsonl",
        "combined_dialogues_api_call_statistics.jsonl",
    )
    for candidate in candidates:
        if candidate is not None and all((candidate / name).exists() for name in required):
            return candidate.resolve()
    checked = ", ".join(str(path) for path in candidates if path is not None)
    raise FileNotFoundError(
        "could not find a finalized export with validation data and statistics; "
        f"checked: {checked}. Training examples are never used as fallback."
    )


def find_source_root(explicit: Optional[Path]) -> Path:
    """Locate the finalized run root containing verified healed source decks."""
    candidates = (
        [explicit]
        if explicit is not None
        else [REPO_ROOT / "dataset" / "runs" / "v5" / "finalized_dataset_v1"]
    )
    for candidate in candidates:
        if candidate is not None and (candidate / "batches").is_dir():
            return candidate.resolve()
    checked = ", ".join(str(path) for path in candidates if path is not None)
    raise FileNotFoundError(f"could not locate healed source-deck root; checked: {checked}")


def tool_calls(example: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Flatten tool calls from a message-only exported dialogue."""
    calls: List[Dict[str, Any]] = []
    messages = example.get("messages")
    if not isinstance(messages, list):
        return calls
    for message in messages:
        if not isinstance(message, dict):
            continue
        message_calls = message.get("tool_calls")
        if not isinstance(message_calls, list):
            continue
        calls.extend(call for call in message_calls if isinstance(call, dict))
    return calls


def pair_validation_rows(
    examples: List[Dict[str, Any]], statistics: List[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Pair validation exports with provenance rows and verify editing signatures."""
    validation_stats = [row for row in statistics if row.get("split") == "validation"]
    if len(examples) != len(validation_stats):
        raise ValueError(
            "validation export/statistics row count mismatch: "
            f"{len(examples)} != {len(validation_stats)}"
        )

    pairs = list(zip(examples, validation_stats))
    for index, (example, metadata) in enumerate(pairs):
        if metadata.get("task_type") != "deck_editing":
            continue
        signature = "|".join(str(call.get("name", "")) for call in tool_calls(example))
        if signature != metadata.get("api_call"):
            raise ValueError(
                "editing export/statistics order mismatch at validation row "
                f"{index + 1}: observed={signature!r}, metadata={metadata.get('api_call')!r}"
            )
    return pairs


def identifier_sets(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Set[str]]:
    """Collect non-empty source identifiers from provenance/task rows."""
    aliases = {
        "source_pack_id": ("source_pack_id",),
        "deck_id": ("deck_id", "source_deck_id"),
        "deck_identity": ("deck_identity", "source_deck_identity"),
    }
    result: Dict[str, Set[str]] = {name: set() for name in aliases}
    for row in rows:
        for canonical, keys in aliases.items():
            for key in keys:
                value = row.get(key)
                if isinstance(value, str) and value.strip():
                    result[canonical].add(value.strip())
                    break
    return result


def pilot_identifiers(
    pilot_rows: List[Dict[str, Any]], statistics: List[Dict[str, Any]]
) -> Dict[str, Set[str]]:
    """Collect explicit pilot IDs and infer missing provenance from matching deck IDs."""
    identifiers = identifier_sets(pilot_rows)
    pilot_decks = set(identifiers["deck_id"])
    inferred_rows = [row for row in statistics if row.get("source_deck_id") in pilot_decks]
    inferred = identifier_sets(inferred_rows)
    for name in identifiers:
        identifiers[name].update(inferred[name])
    return identifiers


def overlaps_identifiers(
    row: Mapping[str, Any], identifiers: Mapping[str, Set[str]]
) -> bool:
    """Return whether a provenance row intersects any identifier set."""
    values = {
        "source_pack_id": row.get("source_pack_id"),
        "deck_id": row.get("source_deck_id", row.get("deck_id")),
        "deck_identity": row.get("source_deck_identity", row.get("deck_identity")),
    }
    return any(
        isinstance(value, str) and value in identifiers.get(name, set())
        for name, value in values.items()
    )


def resolve_healed_path(source_root: Path, metadata: Mapping[str, Any]) -> Path:
    """Resolve the statistics file's repository-relative healed deck path."""
    relative = metadata.get("source_healed_deck_file")
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError(f"{metadata.get('example_id')}: missing source_healed_deck_file")
    path = Path(relative)
    candidates = [path] if path.is_absolute() else [source_root / path, REPO_ROOT / path]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        f"{metadata.get('example_id')}: healed deck file not found: {relative}"
    )


def compact_deck_state(path: Path) -> List[Dict[str, Any]]:
    """Reconstruct a compact full deck state from a verified healed source deck."""
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid healed deck JSON: {path}: {exc}") from exc
    if not isinstance(source, dict):
        raise ValueError(f"healed deck is not a JSON object: {path}")

    metadata_rows = source.get("slide_metadata")
    if not isinstance(metadata_rows, list) or not metadata_rows:
        fields = ", ".join(sorted(source.keys()))
        raise ValueError(
            f"cannot recover deck state from {path}; slide_metadata missing; fields: {fields}"
        )

    bullets_by_slide: Dict[int, List[str]] = {}
    messages = source.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            calls = message.get("tool_calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                if not isinstance(call, dict) or call.get("name") != "edit_content":
                    continue
                args = call.get("args")
                if not isinstance(args, dict):
                    continue
                slide_no = args.get("slide_no")
                items = args.get("items")
                if isinstance(slide_no, int) and isinstance(items, list):
                    bullets_by_slide[slide_no] = [
                        str(item) for item in items if isinstance(item, (str, int, float))
                    ]

    compact: List[Dict[str, Any]] = []
    seen_numbers: Set[int] = set()
    for raw_slide in metadata_rows:
        if not isinstance(raw_slide, dict):
            continue
        slide_no = raw_slide.get("slide_no")
        if not isinstance(slide_no, int) or slide_no in seen_numbers:
            continue
        seen_numbers.add(slide_no)

        source_refs = raw_slide.get("source_refs")
        bibliography_refs = raw_slide.get("bibliography_refs")
        image_refs = raw_slide.get("image_source_refs")
        citation_footer = raw_slide.get("citation_footer")
        visual_type = str(raw_slide.get("visual_type") or "").strip().lower()
        fulfillment = str(raw_slide.get("image_fulfillment_status") or "").strip().lower()
        has_citation = bool(
            citation_footer
            or (isinstance(source_refs, list) and source_refs)
            or (isinstance(bibliography_refs, list) and bibliography_refs)
        )
        has_image = bool(
            (isinstance(image_refs, list) and image_refs)
            or visual_type not in {"", "none", "text_only"}
            or fulfillment not in {"", "none", "not_required", "unfulfilled"}
        )
        compact.append(
            {
                "slide_no": slide_no,
                "role": raw_slide.get("slide_role", raw_slide.get("role")),
                "title": raw_slide.get("title"),
                "layout": raw_slide.get("layout"),
                "bullets": bullets_by_slide.get(slide_no, []),
                "has_citation": has_citation,
                "has_image": has_image,
            }
        )

    compact.sort(key=lambda slide: slide["slide_no"])
    if not compact:
        fields = ", ".join(sorted(source.keys()))
        raise ValueError(f"no compact slides recovered from {path}; fields: {fields}")
    return compact


def target_slide_no(operation: str, args: Mapping[str, Any]) -> Optional[int]:
    """Return the benchmark's expected top-level slide target."""
    key = "after_slide_no" if operation == "insert_slide_after" else "slide_no"
    value = args.get(key)
    return value if isinstance(value, int) else None


def expected_arguments(operation: str, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep only objective arguments suitable for later strict validation."""
    if operation == "edit_content":
        return {"target": "bullets"}
    if operation == "set_layout" and isinstance(args.get("layout"), str):
        return {"layout": args["layout"]}
    if operation == "move_slide":
        for key in ("after_slide_no", "before_slide_no"):
            if isinstance(args.get(key), int):
                return {key: args[key]}
    if operation == "insert_slide_after" and isinstance(args.get("after_slide_no"), int):
        return {"after_slide_no": args["after_slide_no"]}
    if operation == "set_image":
        return {"image_intent": "decorative"}
    return {}


def slide_index(deck_state: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Index compact slides by slide number."""
    return {
        slide["slide_no"]: slide
        for slide in deck_state
        if isinstance(slide.get("slide_no"), int)
    }


def slide_reference(
    slide_no: int, deck_state: List[Dict[str, Any]], difficulty: str
) -> str:
    """Use title/role references for hard tasks and explicit numbers otherwise."""
    slide = slide_index(deck_state).get(slide_no, {})
    title = slide.get("title")
    if difficulty != "hard" or not isinstance(title, str) or not title.strip():
        return f"slide {slide_no}"
    duplicate_count = sum(1 for item in deck_state if item.get("title") == title)
    if duplicate_count == 1:
        return f"the slide titled “{title}”"
    role = slide.get("role")
    if isinstance(role, str) and role.strip():
        return f"the {role} slide titled “{title}”"
    return f"slide {slide_no}, titled “{title}”"


def constraints_for(operation: str, target: Mapping[str, Any]) -> List[str]:
    """Return deterministic operation-specific safety constraints."""
    common = ["preserve_slide_scope", "do_not_modify_other_slides"]
    if operation == "edit_content":
        result = ["rewrite_bullet_text", "preserve_title", "preserve_layout", *common]
    elif operation == "edit_slide":
        result = ["change_title_or_framing_only", "preserve_content", "preserve_layout", *common]
    elif operation == "set_layout":
        result = ["change_layout_only", "preserve_text", *common]
    elif operation == "move_slide":
        result = ["preserve_slide_content", "move_only_requested_slide", *common]
    elif operation == "insert_slide_after":
        result = ["insert_after_requested_slide", "do_not_modify_existing_slides"]
    elif operation == "delete_slide":
        result = ["delete_requested_slide_only", "do_not_delete_other_slides"]
    else:
        result = ["image_only_change", "preserve_text", "preserve_layout", *common]
    if bool(target.get("has_citation")) and operation in {
        "edit_content",
        "edit_slide",
        "set_layout",
    }:
        result.append("preserve_citation")
    return result


def content_action(scenario: str) -> str:
    """Map source editing scenarios to clear content-only instructions."""
    if scenario == "compress_slide":
        return "shorten and tighten only the bullet text"
    if scenario == "expand_slide":
        return "expand only the bullet text with a clearer explanation"
    if scenario == "rewrite_slide_preserve_citation":
        return "rewrite only the bullet text for clarity"
    return "strengthen only the wording of the bullet text"


def build_user_request(
    operation: str,
    args: Mapping[str, Any],
    scenario: str,
    deck_state: List[Dict[str, Any]],
    difficulty: str,
) -> str:
    """Create hard-but-unambiguous, single-operation benchmark wording."""
    target_no = target_slide_no(operation, args)
    if target_no is None:
        raise ValueError(f"{operation}: source tool call has no valid target slide")
    slides = slide_index(deck_state)
    target = slides.get(target_no)
    if target is None:
        raise ValueError(f"{operation}: target slide {target_no} is absent from source deck")
    target_ref = slide_reference(target_no, deck_state, difficulty)
    citation_clause = (
        " Preserve all citation and source references on that slide."
        if target.get("has_citation")
        else ""
    )

    if operation == "edit_content":
        action = content_action(scenario)
        if difficulty == "hard":
            if scenario == "rewrite_slide_preserve_citation":
                action = (
                    "rewrite only the bullet text so its main claim and supporting "
                    "evidence are easier to distinguish"
                )
            elif scenario == "improve_slide":
                action = (
                    "strengthen only the bullet wording so its main claim and evidence "
                    "are more precise"
                )
        request = (
            f"Please {action} on {target_ref}. "
            "Keep its title and layout unchanged."
            f"{citation_clause} Do not modify any other slide."
        )
        return request

    if operation == "edit_slide":
        return (
            f"Give {target_ref} a more precise title that reflects its main argument. "
            f"Keep the bullet content and layout unchanged.{citation_clause} "
            "Do not alter any other slide."
        )

    if operation == "set_layout":
        layout = args.get("layout")
        if not isinstance(layout, str) or not layout.strip():
            raise ValueError("set_layout source call is missing layout")
        return (
            f"Change only {target_ref} to the {layout} layout. "
            f"Preserve all text and wording.{citation_clause} Do not change any other slide."
        )

    if operation == "move_slide":
        relation_key = "after_slide_no" if isinstance(args.get("after_slide_no"), int) else "before_slide_no"
        destination_no = args.get(relation_key)
        if not isinstance(destination_no, int) or destination_no not in slides:
            raise ValueError("move_slide source call has no valid destination")
        destination_ref = slide_reference(destination_no, deck_state, difficulty)
        relation = "directly after" if relation_key == "after_slide_no" else "directly before"
        return (
            f"Move {target_ref} so it appears {relation} {destination_ref}. "
            "Keep the moved slide’s content and layout unchanged, and do not move or edit any other slide."
        )

    if operation == "insert_slide_after":
        title = args.get("title")
        title_clause = f" titled “{title}”" if isinstance(title, str) and title.strip() else ""
        return (
            f"Insert one short transition slide{title_clause} directly after {target_ref}. "
            "Use it to connect that section to the following section, and do not modify any existing slide."
        )

    if operation == "delete_slide":
        return (
            f"Delete only {target_ref} because it is redundant. "
            "Do not delete, move, or edit any other slide."
        )

    return (
        f"Add a simple conceptual decorative visual only to {target_ref}. "
        "Keep its title, bullet text, layout, and all other slides unchanged."
    )


def stable_digest(value: str) -> str:
    """Return a stable hexadecimal sort key."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def round_robin_by_deck(
    candidates: List[Dict[str, Any]], operation: str, seed: int
) -> List[Dict[str, Any]]:
    """Spread selection across held-out decks before reusing a deck."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        groups[candidate["metadata"]["source_deck_identity"]].append(candidate)
    deck_order = sorted(
        groups,
        key=lambda deck: stable_digest(f"{seed}:{operation}:deck:{deck}"),
    )
    for deck, rows in groups.items():
        groups[deck] = sorted(
            rows,
            key=lambda row: stable_digest(
                f"{seed}:{operation}:example:{row['metadata']['example_id']}"
            ),
        )

    ordered: List[Dict[str, Any]] = []
    index = 0
    while True:
        added = False
        for deck in deck_order:
            if index < len(groups[deck]):
                ordered.append(groups[deck][index])
                added = True
        if not added:
            return ordered
        index += 1


def assign_difficulties(
    rows: List[Dict[str, Any]], operation: str, seed: int
) -> List[Dict[str, Any]]:
    """Assign the exact per-operation difficulty mix deterministically."""
    counts = TARGET_DIFFICULTY_BY_OPERATION[operation]
    labels = [level for level in ("easy", "medium", "hard") for _ in range(counts[level])]
    if len(rows) != len(labels):
        raise ValueError(f"{operation}: selected row/difficulty target mismatch")
    random.Random(seed + SUPPORTED_OPERATIONS.index(operation) * 1009).shuffle(labels)
    for row, difficulty in zip(rows, labels):
        row["difficulty"] = difficulty
    return rows


def build_candidates(
    pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    pilot_ids: Mapping[str, Set[str]],
    source_root: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Filter supported held-out examples and attach recovered compact decks."""
    metrics = {
        "validation_examples_loaded": len(pairs),
        "editing_examples": 0,
        "supported_single_operation_examples": 0,
        "pilot_overlap_candidates_excluded": 0,
        "deck_recoverable_candidates": 0,
    }
    candidates: List[Dict[str, Any]] = []
    deck_cache: Dict[Path, List[Dict[str, Any]]] = {}

    for example, metadata in pairs:
        if metadata.get("task_type") != "deck_editing":
            continue
        metrics["editing_examples"] += 1
        operation = metadata.get("api_call")
        calls = tool_calls(example)
        if operation not in SUPPORTED_OPERATIONS or len(calls) != 1:
            continue
        if calls[0].get("name") != operation:
            raise ValueError(f"{metadata.get('example_id')}: tool/metadata operation mismatch")
        metrics["supported_single_operation_examples"] += 1
        if overlaps_identifiers(metadata, pilot_ids):
            metrics["pilot_overlap_candidates_excluded"] += 1
            continue

        args = calls[0].get("args")
        if not isinstance(args, dict):
            continue
        path = resolve_healed_path(source_root, metadata)
        if path not in deck_cache:
            deck_cache[path] = compact_deck_state(path)
        deck_state = deck_cache[path]
        target_no = target_slide_no(str(operation), args)
        if target_no is None or target_no not in slide_index(deck_state):
            continue
        if operation == "move_slide":
            destination = args.get("after_slide_no", args.get("before_slide_no"))
            if not isinstance(destination, int) or destination not in slide_index(deck_state):
                continue
        candidates.append(
            {
                "example": example,
                "metadata": metadata,
                "operation": operation,
                "args": args,
                "deck_state": deck_state,
            }
        )
        metrics["deck_recoverable_candidates"] += 1
    return candidates, metrics


def select_final_candidates(
    candidates: List[Dict[str, Any]], seed: int
) -> List[Dict[str, Any]]:
    """Enforce exact operation and difficulty targets, then interleave operations."""
    queues: Dict[str, List[Dict[str, Any]]] = {}
    for operation in SUPPORTED_OPERATIONS:
        available = [row for row in candidates if row["operation"] == operation]
        needed = TARGET_OPERATION_COUNTS[operation]
        if len(available) < needed:
            raise ValueError(
                f"not enough eligible {operation} examples: need {needed}, found {len(available)}"
            )
        chosen = round_robin_by_deck(available, operation, seed)[:needed]
        queues[operation] = assign_difficulties(chosen, operation, seed)

    interleaved: List[Dict[str, Any]] = []
    while any(queues.values()):
        for operation in SUPPORTED_OPERATIONS:
            if queues[operation]:
                interleaved.append(queues[operation].pop(0))
    return interleaved


def task_from_candidate(candidate: Dict[str, Any], number: int) -> Dict[str, Any]:
    """Convert one selected source example into a compact benchmark task."""
    metadata = candidate["metadata"]
    operation = candidate["operation"]
    args = candidate["args"]
    deck_state = candidate["deck_state"]
    difficulty = candidate["difficulty"]
    target_no = target_slide_no(operation, args)
    assert target_no is not None
    target = slide_index(deck_state)[target_no]
    return {
        "task_id": f"final_{number:03d}",
        "benchmark_version": "final_50_v1",
        "deck_id": metadata["source_deck_id"],
        "source_pack_id": metadata["source_pack_id"],
        "deck_identity": metadata["source_deck_identity"],
        "source_example_id": metadata["example_id"],
        "source_split": "validation",
        "operation_group": operation,
        "user_request": build_user_request(
            operation,
            args,
            str(metadata.get("scenario", "")),
            deck_state,
            difficulty,
        ),
        "deck_state": deck_state,
        "expected_api_call": operation,
        "expected_slide_no": target_no,
        "expected_arguments": expected_arguments(operation, args),
        "expected_constraints": constraints_for(operation, target),
        "replay_applicable": True,
        "difficulty": difficulty,
        "selection_notes": (
            "Held-out validation editing example with verified source-deck pairing; "
            f"source scenario={metadata.get('scenario')}; wording deterministically rewritten "
            "to require exactly one executable operation."
        ),
    }


def identifier_overlap(
    left: Mapping[str, Set[str]], right: Mapping[str, Set[str]]
) -> Dict[str, Set[str]]:
    """Intersect source identifiers by namespace."""
    return {name: set(left[name]) & set(right[name]) for name in left}


def validate_tasks(
    tasks: List[Dict[str, Any]],
    pilot_ids: Mapping[str, Set[str]],
    train_ids: Mapping[str, Set[str]],
    allow_leakage: bool,
) -> Dict[str, Set[str]]:
    """Validate exact distributions, schema essentials, and leakage constraints."""
    operation_counts = Counter(task["expected_api_call"] for task in tasks)
    difficulty_counts = Counter(task["difficulty"] for task in tasks)
    if len(tasks) != 50:
        raise ValueError(f"final benchmark must contain 50 tasks, found {len(tasks)}")
    if dict(operation_counts) != TARGET_OPERATION_COUNTS:
        raise ValueError(f"operation distribution mismatch: {dict(operation_counts)}")
    if dict(difficulty_counts) != TARGET_DIFFICULTY_COUNTS:
        raise ValueError(f"difficulty distribution mismatch: {dict(difficulty_counts)}")
    if len({task["source_example_id"] for task in tasks}) != len(tasks):
        raise ValueError("selected source examples are not unique")

    for task in tasks:
        if not task["task_id"].startswith("final_"):
            raise ValueError(f"invalid final task ID: {task['task_id']}")
        if task["expected_api_call"] not in SUPPORTED_OPERATIONS:
            raise ValueError(f"unsupported operation: {task['expected_api_call']}")
        if task["replay_applicable"] is not True:
            raise ValueError(f"{task['task_id']}: replay_applicable must be true")
        if not isinstance(task["deck_state"], list) or not task["deck_state"]:
            raise ValueError(f"{task['task_id']}: deck_state must be a non-empty slide list")
        if task["expected_slide_no"] not in slide_index(task["deck_state"]):
            raise ValueError(f"{task['task_id']}: expected target is absent from deck_state")

    final_ids = identifier_sets(tasks)
    pilot_overlap = identifier_overlap(final_ids, pilot_ids)
    if any(pilot_overlap.values()):
        raise ValueError(f"final benchmark overlaps pilot identifiers: {pilot_overlap}")
    train_overlap = identifier_overlap(final_ids, train_ids)
    if any(train_overlap.values()) and not allow_leakage:
        raise ValueError(
            "final benchmark source identifiers overlap train split; rerun only with "
            f"--allow-leakage to override: {train_overlap}"
        )
    return train_overlap


def write_jsonl(path: Path, rows: List[Mapping[str, Any]]) -> None:
    """Write deterministic UTF-8 JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


def write_distribution(path: Path, tasks: List[Dict[str, Any]]) -> None:
    """Write operation and difficulty distributions in one audit-friendly CSV."""
    operation_counts = Counter(task["expected_api_call"] for task in tasks)
    difficulty_counts = Counter(task["difficulty"] for task in tasks)
    rows = [
        {
            "dimension": "operation",
            "value": operation,
            "count": operation_counts[operation],
            "target_count": TARGET_OPERATION_COUNTS[operation],
        }
        for operation in SUPPORTED_OPERATIONS
    ]
    rows.extend(
        {
            "dimension": "difficulty",
            "value": difficulty,
            "count": difficulty_counts[difficulty],
            "target_count": TARGET_DIFFICULTY_COUNTS[difficulty],
        }
        for difficulty in ("easy", "medium", "hard")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=("dimension", "value", "count", "target_count")
        )
        writer.writeheader()
        writer.writerows(rows)


def display_path(path: Path) -> str:
    """Prefer a repository-relative audit path."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def format_counter(counter: Mapping[str, int], order: Iterable[str]) -> List[str]:
    """Format a Markdown table body for a known key order."""
    return [f"| {key} | {counter.get(key, 0)} |" for key in order]


def write_audit(
    path: Path,
    *,
    export_dir: Path,
    source_root: Path,
    metrics: Mapping[str, int],
    tasks: List[Dict[str, Any]],
    pilot_ids: Mapping[str, Set[str]],
    train_overlap: Mapping[str, Set[str]],
) -> None:
    """Write provenance, distribution, leakage, and selection audit details."""
    operation_counts = Counter(task["expected_api_call"] for task in tasks)
    difficulty_counts = Counter(task["difficulty"] for task in tasks)
    scenario_counts = Counter(
        task["selection_notes"].split("source scenario=", 1)[1].split(";", 1)[0]
        for task in tasks
    )
    final_ids = identifier_sets(tasks)
    lines = [
        "# Final 50 Benchmark Audit",
        "",
        "## Provenance",
        "",
        "- Benchmark version: `final_50_v1`",
        f"- Finalized export: `{display_path(export_dir)}`",
        f"- Validation rows: `{display_path(export_dir / 'combined_dialogues_validation.jsonl')}`",
        f"- Provenance statistics: `{display_path(export_dir / 'combined_dialogues_api_call_statistics.jsonl')}`",
        f"- Verified healed deck root: `{display_path(source_root)}`",
        "- Selection split: validation only; training rows are never a fallback.",
        "- Deck states are reconstructed from verified healed source decks, not invented.",
        "",
        "## Candidate filtering",
        "",
        f"- Validation examples loaded: {metrics['validation_examples_loaded']}",
        f"- Validation editing examples: {metrics['editing_examples']}",
        f"- Supported single-operation examples: {metrics['supported_single_operation_examples']}",
        f"- Candidates excluded for pilot identifier overlap: {metrics['pilot_overlap_candidates_excluded']}",
        f"- Eligible candidates with recoverable compact deck states: {metrics['deck_recoverable_candidates']}",
        f"- Final tasks selected: {len(tasks)}",
        "",
        "## Operation distribution",
        "",
        "| Operation | Count |",
        "|---|---:|",
        *format_counter(operation_counts, SUPPORTED_OPERATIONS),
        "",
        "## Difficulty distribution",
        "",
        "| Difficulty | Count |",
        "|---|---:|",
        *format_counter(difficulty_counts, ("easy", "medium", "hard")),
        "",
        "## Source coverage and leakage",
        "",
        f"- Unique source_pack_id values used: {len(final_ids['source_pack_id'])}",
        f"- Unique deck_id values used: {len(final_ids['deck_id'])}",
        f"- Unique deck_identity values used: {len(final_ids['deck_identity'])}",
        f"- Pilot source_pack_id values excluded: {len(pilot_ids['source_pack_id'])}",
        f"- Pilot deck_id values excluded: {len(pilot_ids['deck_id'])}",
        f"- Pilot deck_identity values excluded: {len(pilot_ids['deck_identity'])}",
        f"- Final/train source_pack_id overlap: {len(train_overlap['source_pack_id'])}",
        f"- Final/train deck_id overlap: {len(train_overlap['deck_id'])}",
        f"- Final/train deck_identity overlap: {len(train_overlap['deck_identity'])}",
        "- Leakage status: PASS" if not any(train_overlap.values()) else "- Leakage status: OVERRIDDEN",
        "",
        "## Selected source scenarios",
        "",
        "| Scenario | Count |",
        "|---|---:|",
        *[f"| {name} | {count} |" for name, count in sorted(scenario_counts.items())],
        "",
        "## Construction notes",
        "",
        "- The pilot deck and its inferred source pack/deck identity are excluded.",
        "- Multi-operation examples and one-shot deck generation examples are excluded.",
        "- Source requests are deterministically rewritten to be single-operation and unambiguous.",
        "- Hard tasks refer to unique slide titles/roles where possible and retain explicit safety constraints.",
        "- `ask_clarification` is not part of the operation vocabulary.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(
    *,
    export_dir: Path,
    metrics: Mapping[str, int],
    tasks: List[Dict[str, Any]],
    out: Path,
    audit: Path,
    distribution: Path,
    train_overlap: Mapping[str, Set[str]],
) -> None:
    """Print the stable build summary used in the audit handoff."""
    final_ids = identifier_sets(tasks)
    operations = Counter(task["expected_api_call"] for task in tasks)
    difficulties = Counter(task["difficulty"] for task in tasks)
    print(f"export_dir: {export_dir}")
    for name, value in metrics.items():
        print(f"{name}: {value}")
    print(f"tasks_written: {len(tasks)}")
    print("operation_distribution: " + ", ".join(f"{op}={operations[op]}" for op in SUPPORTED_OPERATIONS))
    print("difficulty_distribution: " + ", ".join(f"{key}={difficulties[key]}" for key in ("easy", "medium", "hard")))
    print(f"unique_source_pack_ids: {len(final_ids['source_pack_id'])}")
    print(f"unique_deck_ids: {len(final_ids['deck_id'])}")
    print(f"unique_deck_identities: {len(final_ids['deck_identity'])}")
    print(f"train_identifier_overlap: {sum(len(values) for values in train_overlap.values())}")
    print("ask_clarification: 0")
    print(f"task_file: {out}")
    print(f"audit_report: {audit}")
    print(f"distribution_csv: {distribution}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Build and audit the deterministic final benchmark."""
    args = parse_args(argv)
    export_dir = find_export_dir(args.export_dir)
    source_root = find_source_root(args.source_root)
    validation_path = export_dir / "combined_dialogues_validation.jsonl"
    statistics_path = export_dir / "combined_dialogues_api_call_statistics.jsonl"

    examples = load_jsonl(validation_path)
    statistics = load_jsonl(statistics_path)
    pairs = pair_validation_rows(examples, statistics)
    pilot_rows = load_jsonl(args.pilot)
    pilot_ids = pilot_identifiers(pilot_rows, statistics)
    train_ids = identifier_sets(row for row in statistics if row.get("split") == "train")

    candidates, metrics = build_candidates(pairs, pilot_ids, source_root)
    selected = select_final_candidates(candidates, args.seed)
    tasks = [task_from_candidate(candidate, index) for index, candidate in enumerate(selected, 1)]
    train_overlap = validate_tasks(tasks, pilot_ids, train_ids, args.allow_leakage)

    write_jsonl(args.out, tasks)
    write_distribution(args.distribution, tasks)
    write_audit(
        args.audit,
        export_dir=export_dir,
        source_root=source_root,
        metrics=metrics,
        tasks=tasks,
        pilot_ids=pilot_ids,
        train_overlap=train_overlap,
    )
    print_summary(
        export_dir=export_dir,
        metrics=metrics,
        tasks=tasks,
        out=args.out,
        audit=args.audit,
        distribution=args.distribution,
        train_overlap=train_overlap,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
