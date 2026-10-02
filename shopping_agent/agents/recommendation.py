"""拥有私有推荐状态的推荐子 Agent。"""

import json
from typing import Callable
from pydantic import BaseModel

from ..schemas.computer_products import RecommendationResult
from ..state import RecommendationAgentState
from .common import append_error

StructuredInvoker = Callable[[str, str, type[BaseModel]], BaseModel]
RECOMMENDATION_PROMPT = """你是最终推荐 Agent。只能推荐 hard_constraints_met=true 的商品，
按评分、置信度和取舍形成最终顺序，不得引入不存在的商品或参数。
没有合格商品返回 no_match；rank 必须从 1 开始连续。"""


def recommendation_agent_node(state: RecommendationAgentState, *, invoker: StructuredInvoker) -> dict:
    payload = {"request": state["request"].model_dump(mode="json"),
               "products": [p.model_dump(mode="json") for p in state.get("products", [])],
               "scores": state["scoring_result"].model_dump(mode="json")}
    try:
        result = RecommendationResult.model_validate(invoker(
            RECOMMENDATION_PROMPT, json.dumps(payload, ensure_ascii=False), RecommendationResult))
        allowed = {s.product_id for s in state["scoring_result"].scores
                   if s.hard_constraints_met}
        ids = [item.product_id for item in result.items]
        if any(i not in allowed for i in ids):
            raise ValueError("推荐包含未通过硬条件或不存在的商品")
        if len(ids) != len(set(ids)):
            raise ValueError("推荐包含重复商品")
        if [item.rank for item in result.items] != list(range(1, len(ids) + 1)):
            raise ValueError("推荐排名必须从 1 开始连续")
        return {"recommendation": result}
    except Exception as error:
        return {"errors": append_error(state.get("errors"), "recommendation_agent", error)}
