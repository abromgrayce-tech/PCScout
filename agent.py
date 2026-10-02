"""自主式电脑商品购物 Agent 命令行入口。"""

import argparse
import json
import sys
from pydantic import BaseModel

from shopping_agent.graph import build_graph

DEFAULT_MESSAGE = "预算 2500 元，想买一台 27 英寸 4K 非曲面显示器，用于办公。"


def _json_default(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"无法序列化 {type(value)!r}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="自主式电脑商品购物 Agent")
    parser.add_argument("message", nargs="?", default=DEFAULT_MESSAGE)
    args = parser.parse_args()
    initial_state = {"user_query": args.message, "route_history": [],
                     "errors": [], "step_count": 0}
    try:
        result = build_graph().invoke(initial_state, config={"recursion_limit": 30})
    except Exception as error:
        print(f"Agent 执行失败：{error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    return 0 if result.get("recommendation") is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
