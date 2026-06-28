#!/usr/bin/env python3
"""Build and audit the frozen HardSingleOp-50 held-out benchmark.

HardSingleOp-50 reuses the verified validation/provenance pairing and healed
deck reconstruction from the final-50 builder, but selects only unused source
dialogues and deterministically rewrites them into harder semantic-reference
requests.  It never falls back to training rows and never emits a dialogue
control operation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from build_final_50_benchmark import (
    BENCHMARK_ROOT,
    REPO_ROOT,
    SUPPORTED_OPERATIONS,
    compact_deck_state,
    display_path,
    find_export_dir,
    find_source_root,
    identifier_sets,
    load_jsonl,
    overlaps_identifiers,
    pair_validation_rows,
    pilot_identifiers,
    resolve_healed_path,
    slide_index,
    stable_digest,
    target_slide_no,
    tool_calls,
    write_jsonl,
)


BENCHMARK_VERSION = "hard_single_50_v1"
TARGET_OPERATION_COUNTS = {
    "edit_content": 10,
    "edit_slide": 8,
    "set_layout": 7,
    "move_slide": 7,
    "insert_slide_after": 7,
    "delete_slide": 5,
    "set_image": 6,
}
MAX_TASKS = 50
TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}

CANDIDATE_CSV_FIELDS = (
    "validation_row",
    "source_example_id",
    "source_split",
    "task_type",
    "operation_group",
    "scenario",
    "tool_call_count",
    "deck_id",
    "source_pack_id",
    "deck_identity",
    "original_user_request",
    "confirmation_gated",
    "deck_recovered",
    "deck_slide_count",
    "expected_slide_no",
    "expected_arguments",
    "rewrite_type",
    "rewritten_user_request",
    "hardness_score",
    "hardness_tags",
    "difficulty",
    "eligible",
    "selected",
    "selected_task_id",
    "exclusion_reason",
    "selection_status",
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse repository-root-friendly HardSingleOp builder options."""
    parser = argparse.ArgumentParser(
        description="Build the held-out HardSingleOp-50 slide-edit benchmark."
    )
    parser.add_argument("--export-dir", type=Path, default=None)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument(
        "--final",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_final_50.jsonl",
        help="Frozen final-50 file whose source examples must be excluded.",
    )
    parser.add_argument(
        "--pilot",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_pilot.jsonl",
        help="Pilot file; it is optional and excluded when present.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "benchmark_tasks_hard_single_50.jsonl",
    )
    parser.add_argument(
        "--candidate-pool",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "hard_single_50_candidate_pool.csv",
    )
    parser.add_argument(
        "--task-distribution",
        type=Path,
        default=BENCHMARK_ROOT / "results" / "hard_single_50_task_distribution.csv",
    )
    parser.add_argument(
        "--complexity-distribution",
        type=Path,
        default=BENCHMARK_ROOT
        / "results"
        / "hard_single_50_complexity_distribution.csv",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=BENCHMARK_ROOT / "report" / "hard_single_50_benchmark_audit.md",
    )
    parser.add_argument(
        "--gold-validation",
        type=Path,
        default=BENCHMARK_ROOT
        / "results"
        / "raw_results_hard_single_50_gold.csv",
        help="Gold validation CSV checked when --freeze is requested.",
    )
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="Mark the deterministic benchmark frozen only after all gold rows pass.",
    )
    parser.add_argument("--seed", type=int, default=73)
    return parser.parse_args(argv)


def empty_identifiers() -> Dict[str, Set[str]]:
    """Return an empty identifier namespace map."""
    return {"source_pack_id": set(), "deck_id": set(), "deck_identity": set()}


def optional_pilot_identifiers(
    path: Path, statistics: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, Set[str]]]:
    """Load pilot provenance when the optional pilot file exists."""
    if not path.exists():
        return [], empty_identifiers()
    rows = load_jsonl(path)
    return rows, pilot_identifiers(rows, statistics)


def first_user_request(example: Mapping[str, Any]) -> str:
    """Recover the initiating request, never a later confirmation message."""
    messages = example.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        value = message.get("text", message.get("content"))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def user_message_count(example: Mapping[str, Any]) -> int:
    """Count non-empty user messages for confirmation-gate auditing."""
    messages = example.get("messages")
    if not isinstance(messages, list):
        return 0
    return sum(
        1
        for message in messages
        if isinstance(message, dict)
        and message.get("role") == "user"
        and isinstance(message.get("text", message.get("content")), str)
        and bool(str(message.get("text", message.get("content"))).strip())
    )


def normalized_title(value: Any) -> str:
    """Normalize a title for exact uniqueness checks."""
    if not isinstance(value, str):
        return ""
    return " ".join(TITLE_TOKEN_RE.findall(value.casefold()))


def title_tokens(value: Any) -> Set[str]:
    """Return meaningful tokens for conservative distractor detection."""
    return {
        token
        for token in TITLE_TOKEN_RE.findall(str(value or "").casefold())
        if token not in TITLE_STOPWORDS and len(token) > 2
    }


def title_is_unique(slide_no: int, deck_state: List[Dict[str, Any]]) -> bool:
    """Return true only when the target has a non-empty unique title."""
    target = slide_index(deck_state).get(slide_no, {})
    normalized = normalized_title(target.get("title"))
    if not normalized:
        return False
    return sum(
        1 for slide in deck_state if normalized_title(slide.get("title")) == normalized
    ) == 1


def has_similar_title(slide_no: int, deck_state: List[Dict[str, Any]]) -> bool:
    """Detect a plausible title distractor without treating it as ambiguous."""
    slides = slide_index(deck_state)
    target_tokens = title_tokens(slides.get(slide_no, {}).get("title"))
    if len(target_tokens) < 3:
        return False
    for other_no, other in slides.items():
        if other_no == slide_no:
            continue
        other_tokens = title_tokens(other.get("title"))
        if len(other_tokens) < 3:
            continue
        union = target_tokens | other_tokens
        if union and len(target_tokens & other_tokens) / len(union) >= 0.45:
            return True
    return False


def semantic_reference(
    slide_no: int, deck_state: List[Dict[str, Any]]
) -> Tuple[str, bool]:
    """Build a deterministic title reference, falling back safely to a number."""
    slide = slide_index(deck_state).get(slide_no, {})
    title = slide.get("title")
    if title_is_unique(slide_no, deck_state) and isinstance(title, str):
        return f"the slide titled “{title.strip()}”", True
    if isinstance(title, str) and title.strip():
        return f"slide {slide_no}, titled “{title.strip()}”", False
    return f"slide {slide_no}", False


def content_instruction(scenario: str) -> str:
    """Map source scenarios to deterministic instruction-style content edits."""
    if scenario == "compress_slide":
        return "Shorten and tighten only the bullet text while preserving its meaning."
    if scenario == "expand_slide":
        return "Expand only the bullet text with a clearer explanation using the same sources."
    if scenario == "rewrite_slide_preserve_citation":
        return (
            "Rewrite only the bullet text so the main claim and supporting evidence "
            "are easier to distinguish."
        )
    return "Strengthen only the bullet wording so the slide's claim is more precise."


def objective_arguments(
    operation: str, args: Mapping[str, Any], scenario: str
) -> Dict[str, Any]:
    """Build executable prompt-schema arguments without leaking target slide numbers."""
    if operation == "edit_content":
        return {"target": "bullets", "instruction": content_instruction(scenario)}
    if operation == "edit_slide":
        title = args.get("title")
        if isinstance(title, str) and title.strip():
            return {"new_title": title.strip()}
        return {"instruction": "Improve only the slide title and framing."}
    if operation == "set_layout":
        return {"layout": args["layout"]} if isinstance(args.get("layout"), str) else {}
    if operation == "move_slide":
        for key in ("after_slide_no", "before_slide_no"):
            if isinstance(args.get(key), int):
                return {key: args[key]}
        return {}
    if operation == "insert_slide_after":
        result: Dict[str, Any] = {}
        if isinstance(args.get("after_slide_no"), int):
            result["after_slide_no"] = args["after_slide_no"]
        if isinstance(args.get("title"), str) and args["title"].strip():
            result["title"] = args["title"].strip()
        result["instruction"] = "Connect the surrounding sections briefly."
        return result
    if operation == "set_image":
        prompt = args.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            return {"image_prompt": prompt.strip()}
        return {
            "image_intent": "decorative",
            "instruction": "Add one relevant conceptual visual only.",
        }
    return {}


def expected_constraints(
    operation: str, target: Mapping[str, Any]
) -> List[str]:
    """Return operation-local preservation constraints for a hard task."""
    common = ["preserve_slide_scope", "do_not_modify_other_slides"]
    if operation == "edit_content":
        result = ["rewrite_bullet_text", "preserve_title", "preserve_layout", *common]
    elif operation == "edit_slide":
        result = ["change_title_only", "preserve_content", "preserve_layout", *common]
    elif operation == "set_layout":
        result = ["change_layout_only", "preserve_text", *common]
    elif operation == "move_slide":
        result = ["preserve_slide_content", "preserve_layout", "move_only_requested_slide", *common]
    elif operation == "insert_slide_after":
        result = ["insert_after_requested_slide", "do_not_modify_existing_slides"]
    elif operation == "delete_slide":
        result = ["delete_requested_slide_only", "do_not_delete_other_slides"]
    else:
        result = ["image_only_change", "preserve_text", "preserve_layout", *common]

    citation_can_be_preserved = operation != "delete_slide"
    if bool(target.get("has_citation")) and citation_can_be_preserved:
        result.append("preserve_citation")
    return result


def hardness(
    operation: str,
    args: Mapping[str, Any],
    deck_state: List[Dict[str, Any]],
) -> Tuple[int, List[str], str]:
    """Compute the documented HardSingleOp score, tags, and difficulty."""
    target_no = target_slide_no(operation, args)
    assert target_no is not None
    target = slide_index(deck_state)[target_no]
    score = 0
    tags: List[str] = []

    target_semantic = operation != "insert_slide_after" and title_is_unique(
        target_no, deck_state
    )
    if target_semantic:
        score += 3
        tags.append("semantic_title_target")

    destination_no: Optional[int] = None
    if operation == "move_slide":
        raw_destination = args.get("after_slide_no", args.get("before_slide_no"))
        destination_no = raw_destination if isinstance(raw_destination, int) else None
    elif operation == "insert_slide_after":
        destination_no = target_no
    if destination_no is not None and title_is_unique(destination_no, deck_state):
        score += 3
        tags.append("semantic_title_destination")

    if operation in {"move_slide", "insert_slide_after"}:
        score += 2
        tags.append("relative_position")

    if bool(target.get("has_citation")) and operation != "delete_slide":
        score += 2
        tags.append("citation_preservation")

    if operation == "edit_content":
        score += 2
        tags.append("content_transformation")

    if len(deck_state) >= 9:
        score += 1
        tags.append("long_deck")

    distractor_numbers = [target_no]
    if destination_no is not None and destination_no != target_no:
        distractor_numbers.append(destination_no)
    if any(has_similar_title(number, deck_state) for number in distractor_numbers):
        score += 1
        tags.append("similar_title_distractor")

    semantic_reference_available = (
        title_is_unique(target_no, deck_state)
        if operation != "insert_slide_after"
        else title_is_unique(target_no, deck_state)
    )
    if not semantic_reference_available:
        score -= 2
        tags.append("explicit_slide_number_fallback")

    if operation in {"delete_slide", "set_layout"}:
        score -= 1
        tags.append("trivial_operation_penalty")

    difficulty = "hard" if score >= 8 else "medium" if score >= 5 else "easy"
    return score, tags, difficulty


def preservation_clause(operation: str, target: Mapping[str, Any]) -> str:
    """Build a safe citation clause only for operations that can preserve it."""
    if bool(target.get("has_citation")) and operation != "delete_slide":
        return " Preserve all citation and source references exactly as they are."
    return ""


def rewrite_request(
    operation: str,
    args: Mapping[str, Any],
    scenario: str,
    deck_state: List[Dict[str, Any]],
) -> Tuple[str, str]:
    """Safely rewrite one request without changing its executable answer."""
    target_no = target_slide_no(operation, args)
    if target_no is None:
        raise ValueError(f"{operation}: missing integer target")
    slides = slide_index(deck_state)
    target = slides[target_no]
    target_ref, target_semantic = semantic_reference(target_no, deck_state)
    rewrite_types: List[str] = []
    if target_semantic:
        label = (
            "destination_number_to_unique_title"
            if operation == "insert_slide_after"
            else "target_number_to_unique_title"
        )
        rewrite_types.append(label)

    citation_clause = preservation_clause(operation, target)
    if citation_clause:
        rewrite_types.append("preservation_constraints_added")

    if operation == "edit_content":
        rewrite_types.append("content_edit_wording_strengthened")
        request = (
            f"On {target_ref}, {content_instruction(scenario)[0].lower()}"
            f"{content_instruction(scenario)[1:]} Keep the title and layout unchanged."
            f"{citation_clause} Do not modify any other slide."
        )
    elif operation == "edit_slide":
        new_title = args.get("title")
        if not isinstance(new_title, str) or not new_title.strip():
            raise ValueError("edit_slide source call lacks a deterministic title")
        request = (
            f"On {target_ref}, replace only the title with “{new_title.strip()}”. "
            f"Keep all bullet content and the layout unchanged.{citation_clause} "
            "Do not modify any other slide."
        )
    elif operation == "set_layout":
        layout = args.get("layout")
        if not isinstance(layout, str) or not layout.strip():
            raise ValueError("set_layout source call lacks a layout")
        request = (
            f"Change only {target_ref} to the {layout.strip()} layout. "
            f"Preserve every title and bullet exactly.{citation_clause} "
            "Do not modify any other slide."
        )
    elif operation == "move_slide":
        relation_key = (
            "after_slide_no"
            if isinstance(args.get("after_slide_no"), int)
            else "before_slide_no"
        )
        destination_no = args.get(relation_key)
        if not isinstance(destination_no, int) or destination_no not in slides:
            raise ValueError("move_slide source call lacks a valid destination")
        destination_ref, destination_semantic = semantic_reference(
            destination_no, deck_state
        )
        if destination_semantic:
            rewrite_types.append("destination_number_to_unique_title")
        relation = "directly after" if relation_key == "after_slide_no" else "directly before"
        request = (
            f"Move {target_ref} so it appears {relation} {destination_ref}. "
            f"Keep the moved slide's title, content, and layout unchanged.{citation_clause} "
            "Do not edit or move any other slide."
        )
    elif operation == "insert_slide_after":
        title = args.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("insert_slide_after source call lacks a deterministic title")
        request = (
            f"Insert exactly one short transition slide titled “{title.strip()}” directly "
            f"after {target_ref}. Use it only to connect that section to the following "
            f"section.{citation_clause} Do not modify any existing slide."
        )
    elif operation == "delete_slide":
        request = (
            f"Delete only {target_ref} because it is redundant. "
            "Do not delete, move, or edit any other slide."
        )
    elif operation == "set_image":
        prompt = args.get("prompt")
        visual = (
            prompt.strip()
            if isinstance(prompt, str) and prompt.strip()
            else "a simple decorative conceptual visual relevant to the slide"
        )
        request = (
            f"Add exactly one decorative image to {target_ref} with this visual intent: "
            f"“{visual}” Keep the title, bullet text, and layout unchanged.{citation_clause} "
            "Do not modify any other slide."
        )
    else:
        raise ValueError(f"unsupported operation: {operation}")

    if "similar_title_distractor" in hardness(operation, args, deck_state)[1]:
        role = str(target.get("role") or "content").replace("_", " ")
        if role not in {"title", "agenda"}:
            request += f" Use the {role} slide—not the agenda or title slide."
            rewrite_types.append("limited_title_agenda_distractor")

    if not rewrite_types:
        rewrite_types.append("preservation_constraints_added")
    return request, "+".join(dict.fromkeys(rewrite_types))


def new_audit_row(
    index: int, example: Mapping[str, Any], metadata: Mapping[str, Any]
) -> Dict[str, Any]:
    """Create a complete candidate-audit row with conservative defaults."""
    calls = tool_calls(example)
    return {
        "validation_row": index,
        "source_example_id": metadata.get("example_id", ""),
        "source_split": metadata.get("split", ""),
        "task_type": metadata.get("task_type", ""),
        "operation_group": metadata.get("api_call", ""),
        "scenario": metadata.get("scenario", ""),
        "tool_call_count": len(calls),
        "deck_id": metadata.get("source_deck_id", ""),
        "source_pack_id": metadata.get("source_pack_id", ""),
        "deck_identity": metadata.get("source_deck_identity", ""),
        "original_user_request": first_user_request(example),
        "confirmation_gated": user_message_count(example) > 1,
        "deck_recovered": False,
        "deck_slide_count": 0,
        "expected_slide_no": "",
        "expected_arguments": "",
        "rewrite_type": "",
        "rewritten_user_request": "",
        "hardness_score": "",
        "hardness_tags": "",
        "difficulty": "",
        "eligible": False,
        "selected": False,
        "selected_task_id": "",
        "exclusion_reason": "",
        "selection_status": "excluded",
    }


def exclude(row: Dict[str, Any], reason: str) -> None:
    """Mark one candidate audit row excluded."""
    row["exclusion_reason"] = reason
    row["selection_status"] = f"excluded:{reason}"


def build_candidate_pool(
    pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    *,
    final_source_examples: Set[str],
    pilot_ids: Mapping[str, Set[str]],
    train_ids: Mapping[str, Set[str]],
    source_root: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Audit every validation row and return eligible single-op candidates."""
    candidates: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []
    deck_cache: Dict[Path, List[Dict[str, Any]]] = {}

    for index, (example, metadata) in enumerate(pairs, start=1):
        row = new_audit_row(index, example, metadata)
        audit_rows.append(row)

        if metadata.get("split") != "validation":
            exclude(row, "not_validation_split")
            continue
        if metadata.get("task_type") != "deck_editing":
            exclude(row, "not_deck_editing")
            continue
        if metadata.get("validation_verdict") not in {None, "accept"}:
            exclude(row, "source_not_verified")
            continue

        source_example = metadata.get("example_id")
        if isinstance(source_example, str) and source_example in final_source_examples:
            exclude(row, "final_50_source_example_overlap")
            continue
        if overlaps_identifiers(metadata, pilot_ids):
            exclude(row, "pilot_source_identifier_overlap")
            continue
        if overlaps_identifiers(metadata, train_ids):
            exclude(row, "train_source_identifier_overlap")
            continue

        operation = metadata.get("api_call")
        calls = tool_calls(example)
        if operation not in SUPPORTED_OPERATIONS:
            exclude(row, "unsupported_or_multi_operation_signature")
            continue
        if len(calls) != 1:
            exclude(row, "expected_tool_call_count_not_one")
            continue
        if calls[0].get("name") != operation:
            exclude(row, "tool_metadata_operation_mismatch")
            continue
        args = calls[0].get("args")
        if not isinstance(args, dict):
            exclude(row, "tool_arguments_not_object")
            continue

        try:
            path = resolve_healed_path(source_root, metadata)
            if path not in deck_cache:
                deck_cache[path] = compact_deck_state(path)
            deck_state = deck_cache[path]
            slides = slide_index(deck_state)
            target_no = target_slide_no(str(operation), args)
            if target_no is None or target_no not in slides:
                raise ValueError("target slide is absent from recovered deck")
            if operation == "move_slide":
                destination = args.get("after_slide_no", args.get("before_slide_no"))
                if not isinstance(destination, int) or destination not in slides:
                    raise ValueError("move destination is absent from recovered deck")
            rewritten, rewrite_type = rewrite_request(
                str(operation), args, str(metadata.get("scenario", "")), deck_state
            )
            score, tags, difficulty = hardness(str(operation), args, deck_state)
            expected = objective_arguments(
                str(operation), args, str(metadata.get("scenario", ""))
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            exclude(row, "deck_or_rewrite_not_recoverable")
            row["selection_status"] += f":{str(exc).replace(chr(10), ' ')[:160]}"
            continue

        row.update(
            {
                "deck_recovered": True,
                "deck_slide_count": len(deck_state),
                "expected_slide_no": target_no,
                "expected_arguments": json.dumps(expected, ensure_ascii=False, sort_keys=True),
                "rewrite_type": rewrite_type,
                "rewritten_user_request": rewritten,
                "hardness_score": score,
                "hardness_tags": "|".join(tags),
                "difficulty": difficulty,
                "eligible": True,
                "exclusion_reason": "",
                "selection_status": "eligible_not_selected",
            }
        )
        candidates.append(
            {
                "example": example,
                "metadata": metadata,
                "operation": str(operation),
                "args": args,
                "deck_state": deck_state,
                "original_user_request": row["original_user_request"],
                "user_request": rewritten,
                "rewrite_type": rewrite_type,
                "hardness_score": score,
                "hardness_tags": tags,
                "difficulty": difficulty,
                "expected_arguments": expected,
                "audit_row": row,
            }
        )
    return candidates, audit_rows


def operation_ranked(
    candidates: List[Dict[str, Any]], operation: str, seed: int
) -> List[Dict[str, Any]]:
    """Rank by hardness while round-robining source decks for diversity."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if candidate["operation"] == operation:
            groups[candidate["metadata"]["source_deck_identity"]].append(candidate)
    for deck, rows in groups.items():
        groups[deck] = sorted(
            rows,
            key=lambda row: (
                -row["hardness_score"],
                stable_digest(f"{seed}:{operation}:{row['metadata']['example_id']}"),
            ),
        )
    deck_order = sorted(
        groups,
        key=lambda deck: (
            -groups[deck][0]["hardness_score"],
            stable_digest(f"{seed}:{operation}:deck:{deck}"),
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


def select_candidates(
    candidates: List[Dict[str, Any]], seed: int
) -> List[Dict[str, Any]]:
    """Select up to 50 hard tasks with documented target fallback behavior."""
    selected: List[Dict[str, Any]] = []
    selected_examples: Set[str] = set()
    operation_counts: Counter[str] = Counter()
    deck_counts: Counter[str] = Counter()

    for operation in SUPPORTED_OPERATIONS:
        ranked = operation_ranked(candidates, operation, seed)
        count = min(TARGET_OPERATION_COUNTS[operation], len(ranked))
        for candidate in ranked[:count]:
            selected.append(candidate)
            example_id = candidate["metadata"]["example_id"]
            selected_examples.add(example_id)
            operation_counts[operation] += 1
            deck_counts[candidate["metadata"]["source_deck_identity"]] += 1

    target_total = min(MAX_TASKS, len(candidates))
    while len(selected) < target_total:
        remaining = [
            candidate
            for candidate in candidates
            if candidate["metadata"]["example_id"] not in selected_examples
            and operation_counts[candidate["operation"]]
            < TARGET_OPERATION_COUNTS[candidate["operation"]] + 1
        ]
        if not remaining:
            remaining = [
                candidate
                for candidate in candidates
                if candidate["metadata"]["example_id"] not in selected_examples
            ]
        if not remaining:
            break
        chosen = min(
            remaining,
            key=lambda candidate: (
                -candidate["hardness_score"],
                deck_counts[candidate["metadata"]["source_deck_identity"]],
                operation_counts[candidate["operation"]]
                - TARGET_OPERATION_COUNTS[candidate["operation"]],
                stable_digest(
                    f"{seed}:fallback:{candidate['metadata']['example_id']}"
                ),
            ),
        )
        selected.append(chosen)
        selected_examples.add(chosen["metadata"]["example_id"])
        operation_counts[chosen["operation"]] += 1
        deck_counts[chosen["metadata"]["source_deck_identity"]] += 1

    queues = {
        operation: [row for row in selected if row["operation"] == operation]
        for operation in SUPPORTED_OPERATIONS
    }
    interleaved: List[Dict[str, Any]] = []
    while any(queues.values()):
        for operation in SUPPORTED_OPERATIONS:
            if queues[operation]:
                interleaved.append(queues[operation].pop(0))
    return interleaved


def task_from_candidate(candidate: Dict[str, Any], number: int) -> Dict[str, Any]:
    """Convert one selected source dialogue into a HardSingleOp task."""
    metadata = candidate["metadata"]
    operation = candidate["operation"]
    args = candidate["args"]
    deck_state = candidate["deck_state"]
    target_no = target_slide_no(operation, args)
    assert target_no is not None
    target = slide_index(deck_state)[target_no]
    task_id = f"hard_single_{number:03d}"
    candidate["audit_row"].update(
        {
            "selected": True,
            "selected_task_id": task_id,
            "selection_status": "selected",
        }
    )
    return {
        "task_id": task_id,
        "benchmark_version": BENCHMARK_VERSION,
        "deck_id": metadata["source_deck_id"],
        "source_pack_id": metadata["source_pack_id"],
        "deck_identity": metadata["source_deck_identity"],
        "source_example_id": metadata["example_id"],
        "source_split": "validation",
        "operation_group": operation,
        "user_request": candidate["user_request"],
        "original_user_request": candidate["original_user_request"],
        "rewrite_type": candidate["rewrite_type"],
        "hardness_score": candidate["hardness_score"],
        "hardness_tags": candidate["hardness_tags"],
        "deck_state": deck_state,
        "expected_api_call": operation,
        "expected_slide_no": target_no,
        "expected_arguments": candidate["expected_arguments"],
        "expected_constraints": expected_constraints(operation, target),
        "replay_applicable": True,
        "difficulty": candidate["difficulty"],
        "selection_notes": (
            "Unused held-out validation source example with exactly one verified "
            f"backend call; source scenario={metadata.get('scenario')}; selected by "
            "deterministic hardness-first, deck-diverse balancing."
        ),
    }


def identifier_overlap(
    left: Mapping[str, Set[str]], right: Mapping[str, Set[str]]
) -> Dict[str, Set[str]]:
    """Intersect identifier namespaces."""
    return {name: set(left[name]) & set(right[name]) for name in left}


def validate_tasks(
    tasks: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    final_rows: List[Dict[str, Any]],
    pilot_rows: List[Dict[str, Any]],
    pilot_ids: Mapping[str, Set[str]],
    train_ids: Mapping[str, Set[str]],
) -> Dict[str, Any]:
    """Enforce all construction-time HardSingleOp quality gates."""
    if len(candidates) >= MAX_TASKS and len(tasks) != MAX_TASKS:
        raise ValueError(f"expected {MAX_TASKS} tasks from viable pool, found {len(tasks)}")
    if len(tasks) > MAX_TASKS:
        raise ValueError(f"HardSingleOp cannot exceed {MAX_TASKS} tasks")
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("task IDs are not unique")
    if len({task["source_example_id"] for task in tasks}) != len(tasks):
        raise ValueError("selected source examples are not unique")

    final_task_ids = {str(row.get("task_id")) for row in final_rows}
    final_source_examples = {
        str(row.get("source_example_id"))
        for row in final_rows
        if row.get("source_example_id")
    }
    pilot_task_ids = {str(row.get("task_id")) for row in pilot_rows}
    pilot_source_examples = {
        str(row.get("source_example_id"))
        for row in pilot_rows
        if row.get("source_example_id")
    }
    task_ids = {task["task_id"] for task in tasks}
    source_examples = {task["source_example_id"] for task in tasks}
    if task_ids & final_task_ids or source_examples & final_source_examples:
        raise ValueError("HardSingleOp overlaps final-50 task/source-example IDs")
    if task_ids & pilot_task_ids or source_examples & pilot_source_examples:
        raise ValueError("HardSingleOp overlaps pilot task/source-example IDs")

    hard_ids = identifier_sets(tasks)
    pilot_overlap = identifier_overlap(hard_ids, pilot_ids)
    if any(pilot_overlap.values()):
        raise ValueError(f"HardSingleOp overlaps pilot source identifiers: {pilot_overlap}")
    train_overlap = identifier_overlap(hard_ids, train_ids)
    if any(train_overlap.values()):
        raise ValueError(f"HardSingleOp overlaps training source identifiers: {train_overlap}")

    for task in tasks:
        operation = task.get("expected_api_call")
        if operation not in SUPPORTED_OPERATIONS or operation == "ask_clarification":
            raise ValueError(f"{task.get('task_id')}: unsupported operation {operation}")
        if task.get("source_split") != "validation":
            raise ValueError(f"{task.get('task_id')}: source split is not validation")
        if task.get("replay_applicable") is not True:
            raise ValueError(f"{task.get('task_id')}: replay_applicable must be true")
        deck_state = task.get("deck_state")
        if not isinstance(deck_state, list) or not deck_state:
            raise ValueError(f"{task.get('task_id')}: deck state is not a slide list")
        if task.get("expected_slide_no") not in slide_index(deck_state):
            raise ValueError(f"{task.get('task_id')}: target absent from deck")
        if not isinstance(task.get("expected_arguments"), dict):
            raise ValueError(f"{task.get('task_id')}: expected arguments are not an object")
        if not isinstance(task.get("original_user_request"), str) or not task[
            "original_user_request"
        ].strip():
            raise ValueError(f"{task.get('task_id')}: original request not recovered")

    final_ids = identifier_sets(final_rows)
    return {
        "final_task_id_overlap": len(task_ids & final_task_ids),
        "final_source_example_overlap": len(source_examples & final_source_examples),
        "pilot_task_id_overlap": len(task_ids & pilot_task_ids),
        "pilot_source_example_overlap": len(source_examples & pilot_source_examples),
        "pilot_identifier_overlap": sum(len(values) for values in pilot_overlap.values()),
        "train_identifier_overlap": sum(len(values) for values in train_overlap.values()),
        "final_deck_overlap": len(hard_ids["deck_identity"] & final_ids["deck_identity"]),
        "final_pack_overlap": len(hard_ids["source_pack_id"] & final_ids["source_pack_id"]),
    }


def csv_scalar(value: Any) -> Any:
    """Serialize audit values consistently."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def write_candidate_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write the full validation-row candidate and exclusion audit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANDIDATE_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: csv_scalar(row.get(field, "")) for field in CANDIDATE_CSV_FIELDS}
            )


def write_task_distribution(path: Path, tasks: List[Dict[str, Any]]) -> None:
    """Write requested versus selected operation counts."""
    counts = Counter(task["expected_api_call"] for task in tasks)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=("operation", "target_count", "selected_count", "deviation"),
        )
        writer.writeheader()
        for operation in SUPPORTED_OPERATIONS:
            writer.writerow(
                {
                    "operation": operation,
                    "target_count": TARGET_OPERATION_COUNTS[operation],
                    "selected_count": counts[operation],
                    "deviation": counts[operation] - TARGET_OPERATION_COUNTS[operation],
                }
            )


def write_complexity_distribution(path: Path, tasks: List[Dict[str, Any]]) -> None:
    """Write difficulty, score, hardness-tag, rewrite, and deck-length distributions."""
    rows: List[Dict[str, Any]] = []

    def add_counter(dimension: str, counter: Mapping[Any, int]) -> None:
        for value, count in sorted(counter.items(), key=lambda item: str(item[0])):
            rows.append({"dimension": dimension, "value": value, "count": count})

    add_counter("difficulty", Counter(task["difficulty"] for task in tasks))
    add_counter("hardness_score", Counter(task["hardness_score"] for task in tasks))
    add_counter(
        "hardness_tag",
        Counter(tag for task in tasks for tag in task["hardness_tags"]),
    )
    add_counter(
        "rewrite_type",
        Counter(
            rewrite
            for task in tasks
            for rewrite in str(task["rewrite_type"]).split("+")
            if rewrite
        ),
    )
    add_counter("deck_slide_count", Counter(len(task["deck_state"]) for task in tasks))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=("dimension", "value", "count"))
        writer.writeheader()
        writer.writerows(rows)


def markdown_counter(
    counter: Mapping[Any, int], first_label: str = "Value"
) -> List[str]:
    """Format one compact counter as a Markdown table."""
    return [
        f"| {first_label} | Count |",
        "|---|---:|",
        *[
            f"| {value} | {count} |"
            for value, count in sorted(counter.items(), key=lambda item: str(item[0]))
        ],
    ]


def file_sha256(path: Path) -> str:
    """Hash a benchmark artifact for the freeze statement."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_passing_gold_validation(path: Path, tasks: List[Dict[str, Any]]) -> None:
    """Refuse --freeze unless every selected task has one passing gold row."""
    if not path.exists():
        raise ValueError(f"cannot freeze: gold validation CSV does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    expected_ids = {task["task_id"] for task in tasks}
    observed_ids = {str(row.get("task_id", "")) for row in rows}
    failures = [
        str(row.get("task_id", ""))
        for row in rows
        if str(row.get("validation_passed", "")).casefold() != "true"
    ]
    if observed_ids != expected_ids or len(rows) != len(tasks):
        raise ValueError(
            "cannot freeze: gold validation task IDs/count do not match benchmark"
        )
    if failures:
        raise ValueError(f"cannot freeze: gold validation failures: {failures}")


def write_audit(
    path: Path,
    *,
    export_dir: Path,
    source_root: Path,
    final_path: Path,
    pilot_path: Path,
    candidate_rows: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
    overlaps: Mapping[str, int],
    task_path: Path,
    gold_validation: Path,
    frozen: bool,
) -> None:
    """Write the complete provenance, selection, overlap, and freeze audit."""
    exclusions = Counter(
        str(row["exclusion_reason"])
        for row in candidate_rows
        if row.get("exclusion_reason")
    )
    operations = Counter(task["expected_api_call"] for task in tasks)
    difficulties = Counter(task["difficulty"] for task in tasks)
    hardness_tags = Counter(tag for task in tasks for tag in task["hardness_tags"])
    rewrite_types = Counter(
        rewrite
        for task in tasks
        for rewrite in str(task["rewrite_type"]).split("+")
        if rewrite
    )
    hard_ids = identifier_sets(tasks)
    confirmation_count = sum(
        1
        for task in tasks
        if next(
            (
                row.get("confirmation_gated")
                for row in candidate_rows
                if row.get("selected_task_id") == task["task_id"]
            ),
            False,
        )
    )
    operation_rows = [
        f"| {operation} | {TARGET_OPERATION_COUNTS[operation]} | "
        f"{operations[operation]} | {operations[operation] - TARGET_OPERATION_COUNTS[operation]} |"
        for operation in SUPPORTED_OPERATIONS
    ]
    example_lines: List[str] = []
    for task in sorted(tasks, key=lambda row: (-row["hardness_score"], row["task_id"]))[:5]:
        example_lines.extend(
            [
                f"### {task['task_id']} — `{task['expected_api_call']}`",
                "",
                f"- Hardness: {task['hardness_score']} ({', '.join(task['hardness_tags'])})",
                f"- Request: {task['user_request']}",
                f"- Expected target: slide {task['expected_slide_no']}",
                "",
            ]
        )

    freeze_lines = (
        [
            "- Status: **FROZEN — PASS**",
            f"- Gold validation: all {len(tasks)} selected tasks passed.",
            f"- Gold validation file: `{display_path(gold_validation)}`",
            f"- Frozen task SHA-256: `{file_sha256(task_path)}`",
            "- Any future task-content change requires a new benchmark version and fresh gold validation.",
        ]
        if frozen
        else [
            "- Status: **NOT YET FROZEN**",
            "- Run gold generation and validation, then rerun this builder with `--freeze`.",
        ]
    )

    lines = [
        "# HardSingleOp-50 Benchmark Audit",
        "",
        "## Source files used",
        "",
        f"- Benchmark version: `{BENCHMARK_VERSION}`",
        f"- Validation dialogues: `{display_path(export_dir / 'combined_dialogues_validation.jsonl')}`",
        f"- Split/provenance statistics: `{display_path(export_dir / 'combined_dialogues_api_call_statistics.jsonl')}`",
        f"- Verified healed deck root: `{display_path(source_root)}`",
        f"- Frozen final-50 exclusions: `{display_path(final_path)}`",
        (
            f"- Pilot exclusions: `{display_path(pilot_path)}`"
            if pilot_path.exists()
            else f"- Pilot exclusions: optional file absent at `{display_path(pilot_path)}`"
        ),
        "- Training data was used only as an identifier exclusion set; no training dialogue was a candidate.",
        "",
        "## Candidate loading and exclusions",
        "",
        f"- Validation rows loaded: {len(candidate_rows)}",
        f"- Eligible clean single-operation candidates: {len(candidates)}",
        f"- Selected tasks: {len(tasks)}",
        f"- Confirmation-gated selected dialogues using the initiating request: {confirmation_count}",
        "",
        *markdown_counter(exclusions, "Exclusion reason"),
        "",
        "## Operation distribution",
        "",
        "| Operation | Requested target | Selected | Deviation |",
        "|---|---:|---:|---:|",
        *operation_rows,
        "",
        "The unused clean pool contains only 7 `edit_content` examples after final-50 and pilot exclusions. The three-task deficit is redistributed deterministically to the highest-hardness operations, with at most one extra task per operation before any broader fallback.",
        "",
        "## Difficulty distribution",
        "",
        *markdown_counter(difficulties, "Difficulty"),
        "",
        "## Hardness tag distribution",
        "",
        *markdown_counter(hardness_tags, "Hardness tag"),
        "",
        "## Rewrite type distribution",
        "",
        *markdown_counter(rewrite_types, "Rewrite type"),
        "",
        "## Deck and source-pack diversity",
        "",
        f"- Unique source packs: {len(hard_ids['source_pack_id'])}",
        f"- Unique decks: {len(hard_ids['deck_id'])}",
        f"- Unique deck identities: {len(hard_ids['deck_identity'])}",
        f"- Deck lengths: {min(len(task['deck_state']) for task in tasks)}–{max(len(task['deck_state']) for task in tasks)} slides",
        "",
        "## Overlap and quality-gate checks",
        "",
        f"- Final-50 task-ID overlap: {overlaps['final_task_id_overlap']} — PASS",
        f"- Final-50 source-example overlap: {overlaps['final_source_example_overlap']} — PASS",
        f"- Pilot task-ID overlap: {overlaps['pilot_task_id_overlap']} — PASS",
        f"- Pilot source-example overlap: {overlaps['pilot_source_example_overlap']} — PASS",
        f"- Pilot source-identifier overlap: {overlaps['pilot_identifier_overlap']} — PASS",
        f"- Train source-identifier overlap: {overlaps['train_identifier_overlap']} — PASS",
        "- Unsupported operation count: 0 — PASS",
        "- `ask_clarification` count: 0 — PASS",
        "- Selected examples with expected backend tool-call count other than one: 0 — PASS",
        f"- Final-50 deck-identity reuse: {overlaps['final_deck_overlap']}",
        f"- Final-50 source-pack reuse: {overlaps['final_pack_overlap']}",
        "",
        "Deck/source-pack reuse is expected and is not source-example leakage: final-50 already occupies eight validation decks and the pilot occupies the ninth. HardSingleOp therefore isolates unused validation dialogues/source examples while conservatively excluding the entire pilot deck. A deck-level exclusion against both prior suites would leave no candidates.",
        "",
        "## Examples of selected hard tasks",
        "",
        *example_lines,
        "## Limitations",
        "",
        "- Validation provenance contains only nine source decks, so task-level diversity is stronger than deck-level diversity.",
        "- The requested `edit_content` quota cannot be met without reusing final-50 examples or the pilot deck; the benchmark records the three-task redistribution instead.",
        "- Semantic title targeting is deterministic only when the compact recovered deck contains a unique title; otherwise the builder retains an explicit numbered fallback and applies the score penalty.",
        "- Gold validation checks schema, operation, target, minimum argument completeness, and replay proxy compatibility; it is not a live PowerPoint execution test.",
        "",
        "## Freeze statement",
        "",
        *freeze_lines,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(
    *,
    candidate_rows: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
    overlaps: Mapping[str, int],
    args: argparse.Namespace,
) -> None:
    """Print a concise construction summary."""
    operations = Counter(task["expected_api_call"] for task in tasks)
    difficulties = Counter(task["difficulty"] for task in tasks)
    print(f"validation_rows_audited: {len(candidate_rows)}")
    print(f"eligible_candidates: {len(candidates)}")
    print(f"tasks_written: {len(tasks)}")
    print(
        "operation_distribution: "
        + ", ".join(f"{operation}={operations[operation]}" for operation in SUPPORTED_OPERATIONS)
    )
    print(
        "difficulty_distribution: "
        + ", ".join(f"{level}={difficulties[level]}" for level in ("easy", "medium", "hard"))
    )
    print(f"final_source_example_overlap: {overlaps['final_source_example_overlap']}")
    print(f"pilot_identifier_overlap: {overlaps['pilot_identifier_overlap']}")
    print(f"train_identifier_overlap: {overlaps['train_identifier_overlap']}")
    print("ask_clarification: 0")
    print(f"freeze_status: {'FROZEN' if args.freeze else 'NOT_YET_FROZEN'}")
    print(f"task_file: {args.out}")
    print(f"candidate_pool: {args.candidate_pool}")
    print(f"audit_report: {args.audit}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Build, validate structurally, audit, and optionally freeze HardSingleOp."""
    args = parse_args(argv)
    export_dir = find_export_dir(args.export_dir)
    source_root = find_source_root(args.source_root)
    validation_path = export_dir / "combined_dialogues_validation.jsonl"
    statistics_path = export_dir / "combined_dialogues_api_call_statistics.jsonl"

    examples = load_jsonl(validation_path)
    statistics = load_jsonl(statistics_path)
    pairs = pair_validation_rows(examples, statistics)
    final_rows = load_jsonl(args.final)
    pilot_rows, pilot_ids = optional_pilot_identifiers(args.pilot, statistics)
    train_ids = identifier_sets(
        row for row in statistics if row.get("split") == "train"
    )
    final_source_examples = {
        str(row["source_example_id"])
        for row in final_rows
        if isinstance(row.get("source_example_id"), str)
    }

    candidates, candidate_rows = build_candidate_pool(
        pairs,
        final_source_examples=final_source_examples,
        pilot_ids=pilot_ids,
        train_ids=train_ids,
        source_root=source_root,
    )
    selected = select_candidates(candidates, args.seed)
    tasks = [
        task_from_candidate(candidate, number)
        for number, candidate in enumerate(selected, start=1)
    ]
    overlaps = validate_tasks(
        tasks, candidates, final_rows, pilot_rows, pilot_ids, train_ids
    )

    write_jsonl(args.out, tasks)
    if args.freeze:
        require_passing_gold_validation(args.gold_validation, tasks)
    write_candidate_csv(args.candidate_pool, candidate_rows)
    write_task_distribution(args.task_distribution, tasks)
    write_complexity_distribution(args.complexity_distribution, tasks)
    write_audit(
        args.audit,
        export_dir=export_dir,
        source_root=source_root,
        final_path=args.final,
        pilot_path=args.pilot,
        candidate_rows=candidate_rows,
        candidates=candidates,
        tasks=tasks,
        overlaps=overlaps,
        task_path=args.out,
        gold_validation=args.gold_validation,
        frozen=args.freeze,
    )
    print_summary(
        candidate_rows=candidate_rows,
        candidates=candidates,
        tasks=tasks,
        overlaps=overlaps,
        args=args,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
