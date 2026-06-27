"""Shared JSON-object extraction for benchmark model responses."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Optional


class JsonExtractionError(ValueError):
    """Raised when model response text contains no valid JSON object."""


def _fenced_json_candidate(raw_text: str) -> Optional[str]:
    """Return content when the entire response is one Markdown code fence."""
    stripped = raw_text.strip()
    match = re.fullmatch(
        r"```(?:json)?[ \t]*\r?\n(?P<body>.*)\r?\n```",
        stripped,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return match.group("body").strip()


def _balanced_object_candidates(text: str) -> Iterable[str]:
    """Yield balanced brace-delimited candidates while respecting JSON strings."""
    for start, character in enumerate(text):
        if character != "{":
            continue

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue

            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : index + 1]
                    break


def _parse_json_object(candidate: str) -> Optional[Dict[str, Any]]:
    """Parse a candidate only when it is a JSON object."""
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_first_json_object(text: str) -> Dict[str, Any]:
    """Return the first valid JSON object found in model response text.

    Plain JSON, a response consisting of one JSON Markdown fence, and JSON
    surrounded by explanatory text are supported. ``JsonExtractionError`` is
    raised when the response is empty or contains no valid JSON object.
    """
    if not isinstance(text, str) or not text.strip():
        raise JsonExtractionError("model response text is empty")

    parsed = _parse_json_object(text)
    if parsed is not None:
        return parsed

    fenced = _fenced_json_candidate(text)
    if fenced is not None:
        parsed = _parse_json_object(fenced)
        if parsed is not None:
            return parsed

    for candidate in _balanced_object_candidates(text):
        parsed = _parse_json_object(candidate)
        if parsed is not None:
            return parsed

    raise JsonExtractionError("no valid JSON object found in model response text")
