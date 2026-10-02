"""自主主 Agent：理解需求并决定下一位子 Agent。"""

import json
from typing import Callable
from pydantic import BaseModel

from ..schemas.autonomous import MainAgentDecision
from ..state import MainAgentState
from .common import append_error, append_event

StructuredInvoker = Callable[[str, str, type[BaseModel]], BaseModel]

MAIN_PROMPT = """你是覆盖电脑硬件与外设的购物系统主 Agent。你自主决定下一步调用
shopping_agent、scoring_agent、recommendation_agent 或 finish。
首次决策必须生成 ProductRequirement。category 只能是 cpu、gpu、motherboard、
memory、ssd、hdd、psu、case、cooler、monitor、keyboard、mouse、laptop、desktop、
network_card、other；未列出的电脑商品使用 other 并保留 category_name。
硬性、偏好和排除条件分别写入对应 features；用户已有硬件写入结构化 compatibility。
每个可量化的硬性条件还必须写入 hard_constraints，field 使用商品 attributes 字段名，
operator 使用 eq/gte/lte/contains/not_contains，并保留 source_text。只提取用户明确表达
的信息，不得猜测。根据现有状态推进，不重复工作。
reason 说明依据，需要检索时生成简洁 search_query。"""


def main_agent_node(state: MainAgentState, *, invoker: StructuredInvoker, max_steps: int) -> dict:
    step = state.get("step_count", 0)
    errors = list(state.get("errors", []))
    if step >= max_steps:
        return {"next_agent": "finish", "route_reason": "达到最大步骤数",
                "step_count": step + 1,
                "route_history": append_event(state.get("route_history"), "main→finish")}
    snapshot = {
        "user_query": state.get("user_query", ""),
        "request": state["request"].model_dump(mode="json") if state.get("request") else None,
        "product_count": len(state.get("products", [])),
        "has_scores": state.get("scoring_result") is not None,
        "has_recommendation": state.get("recommendation") is not None,
        "search_summary": state.get("search_summary"),
        "errors": errors,
        "route_history": state.get("route_history", []),
    }
    try:
        decision = MainAgentDecision.model_validate(
            invoker(MAIN_PROMPT, json.dumps(snapshot, ensure_ascii=False), MainAgentDecision)
        )
        next_agent, reason = decision.next_agent, decision.reason
    except Exception as error:
        errors = append_error(errors, "main_agent", error)
        decision, next_agent, reason = None, "finish", "主 Agent 模型决策失败"

    request = state.get("request")
    updates = {}
    if request is None and decision and decision.request is not None:
        request = decision.request
        updates["request"] = request
    if decision and decision.search_query:
        updates["search_query"] = decision.search_query

    # 只保护数据前置条件；业务路线仍由大模型决定。
    if next_agent == "shopping_agent" and request is None:
        errors = append_error(errors, "main_agent", "模型未生成分类购物需求")
        next_agent, reason = "finish", "缺少通过 Schema 校验的购物需求"
    elif next_agent == "scoring_agent" and not state.get("products"):
        next_agent, reason = ("shopping_agent", "评分前必须先获得候选商品")
    elif next_agent == "recommendation_agent" and state.get("scoring_result") is None:
        next_agent = "scoring_agent" if state.get("products") else "shopping_agent"
        reason = "推荐前必须先完成检索和评分"

    updates.update({"next_agent": next_agent, "route_reason": reason, "errors": errors,
                    "step_count": step + 1,
                    "route_history": append_event(state.get("route_history"), f"main→{next_agent}")})
    return updates
