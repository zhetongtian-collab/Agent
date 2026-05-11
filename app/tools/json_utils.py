import json
from typing import Any


# 把字典或列表转换成 JSON 字符串。
# ensure_ascii=False 会保留中文字符，default=str 可以处理 datetime 等默认不能序列化的对象。
def to_json(data: dict[str, Any] | list[Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


# 生成统一的成功 JSON 响应。
# 会自动加上 ok=True，再把调用方传入的数据字段展开进去。
def ok(data: dict[str, Any]) -> str:
    return to_json({"ok": True, **data})


# 生成统一的失败 JSON 响应。
# message 会放到 error 字段里，extra 可以附带更多错误上下文，
# 例如 file_id、suffix 等，方便前端或 Agent 判断失败原因。
def fail(message: str, **extra: Any) -> str:
    return to_json({"ok": False, "error": message, **extra})
