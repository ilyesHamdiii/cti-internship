import hashlib
import json
from typing import Any


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k).lower(): canonicalize(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return sorted((canonicalize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, str):
        return " ".join(value.lower().split())
    return value


def fingerprint_behavior(payload: dict[str, Any]) -> str:
    canonical = canonicalize(payload)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def similarity_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_tokens = set(json.dumps(canonicalize(left), sort_keys=True).split())
    right_tokens = set(json.dumps(canonicalize(right), sort_keys=True).split())
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
