"""节点更新 State 时使用的小型辅助函数。"""


def append_unique(values: list[str] | None, value: str) -> list[str]:
    result = list(values or [])
    if value not in result:
        result.append(value)
    return result


def append_event(values: list[str] | None, value: str) -> list[str]:
    result = list(values or [])
    result.append(value)
    return result


def append_error(values: list[str] | None, node: str, error: Exception | str) -> list[str]:
    result = list(values or [])
    result.append(f"{node}: {error}")
    return result
