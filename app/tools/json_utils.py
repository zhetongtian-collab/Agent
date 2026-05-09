import json
from typing import Any


def to_json(data: dict[str, Any] | list[Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def ok(data: dict[str, Any]) -> str:
    return to_json({"ok": True, **data})


def fail(message: str, **extra: Any) -> str:
    return to_json({"ok": False, "error": message, **extra})
