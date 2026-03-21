"""Consolidated LLM response parsing utilities.

Replaces duplicate JSON extraction logic across agent.py and ai_grid.py.
"""

import json
import re
from typing import Optional


def parse_llm_json(text: str) -> Optional[dict]:
    """Extract a JSON object from an LLM response.

    Strategy (preserves agent.py's full-text-first approach):
    1. Strip markdown code fences (```json ... ```)
    2. Try json.loads on the full cleaned text
    3. Fall back to brace-matching extraction

    Args:
        text: Raw LLM response string.

    Returns:
        Parsed dict, or None if no valid JSON found.
    """
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```", "", cleaned)

    # 1. Try full-text parse
    try:
        return json.loads(cleaned.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Brace-matching extraction
    return _extract_json_object(cleaned)


def _extract_json_object(text: str) -> Optional[dict]:
    """Extract first balanced JSON object from text."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    break
    return None


def parse_price_value(raw: object) -> Optional[float]:
    """Parse a price value that may contain $ or commas.

    Args:
        raw: Value from parsed JSON (str, int, float, or None).

    Returns:
        Float value, or None on failure.
    """
    if raw is None:
        return None
    try:
        return float(str(raw).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def extract_field(parsed: dict, keys: tuple[str, ...], converter=None, default=None):
    """Extract a value from parsed JSON, trying multiple key names.

    Args:
        parsed: Parsed JSON dict.
        keys: Tuple of key names to try in order.
        converter: Optional callable to convert the value.
        default: Default if no key matches or conversion fails.

    Returns:
        Extracted and converted value, or default.
    """
    for key in keys:
        if key in parsed and parsed[key] is not None:
            val = parsed[key]
            if converter is not None:
                try:
                    return converter(val)
                except (ValueError, TypeError):
                    continue
            return val
    return default
