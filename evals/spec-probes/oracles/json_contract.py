import json
import math
from typing import Any


def strict_json_loads(text: str) -> Any:
    def object_from_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"duplicate object key: {key}")
            output[key] = value
        return output

    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite numeric constant: {value}")

    value = json.loads(
        text,
        object_pairs_hook=object_from_pairs,
        parse_constant=reject_nonfinite,
    )

    def validate(item: Any, *, depth: int = 0) -> None:
        if depth > 100:
            raise ValueError("JSON value exceeds the maximum nesting depth")
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError("JSON value contains a surrogate code point") from exc
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"non-finite numeric value: {item}")
        if isinstance(item, list):
            for child in item:
                validate(child, depth=depth + 1)
        if isinstance(item, dict):
            for key, child in item.items():
                validate(key, depth=depth)
                validate(child, depth=depth + 1)

    validate(value)
    return value
