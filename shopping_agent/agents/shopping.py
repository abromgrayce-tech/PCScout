"""拥有私有检索状态的购物子 Agent。"""

import json
from typing import Callable
from pydantic import BaseModel

from ..schemas.autonomous import SearchPlan
from ..schemas.computer_products import ProductBatch
from ..search_backend import ProductSearchBackend
from ..state import ShoppingAgentState
from .common import append_error

StructuredInvoker = Callable[[str, str, type[BaseModel]], BaseModel]
PLAN_PROMPT = """你是购物检索 Agent。根据分类需求生成检索计划，只规划检索，
不评分、不推荐。category 必须与 request.category 一致。"""
EXTRACT_PROMPT = """把搜索后端的原始记录抽取成对应分类商品 Schema。
所有商品使用统一 Product 外壳和 MerchantOffer；attributes 必须使用 category 对应
的专属 Attributes Schema。只提取原始记录有证据支持的事实，未知值填 null 或空列表，
不得猜测；长尾商品使用 category=other、category_name 和受控 OtherAttributes。"""


def plan_search_node(state: ShoppingAgentState, *, invoker: StructuredInvoker) -> dict:
    payload = {"request": state["request"].model_dump(mode="json"),
               "query_hint": state.get("search_query")}
    try:
        plan = SearchPlan.model_validate(invoker(
            PLAN_PROMPT, json.dumps(payload, ensure_ascii=False), SearchPlan))
        if plan.category != state["request"].category:
            raise ValueError("检索类别与需求类别不一致")
        return {"search_plan": plan}
    except Exception as error:
        return {"errors": append_error(state.get("errors"), "shopping.plan", error)}


def run_search_node(state: ShoppingAgentState, *, backend: ProductSearchBackend) -> dict:
    if state.get("search_plan") is None:
        return {"raw_products": [], "search_summary": "未生成有效检索计划"}
    try:
        records = backend.search(state["search_plan"])
        return {"raw_products": records,
                "search_summary": f"搜索接口返回 {len(records)} 条原始记录"}
    except Exception as error:
        return {"raw_products": [], "search_summary": str(error),
                "errors": append_error(state.get("errors"), "shopping.search", error)}


def normalize_products_node(state: ShoppingAgentState, *, invoker: StructuredInvoker) -> dict:
    records = state.get("raw_products", [])
    if not records:
        return {"products": []}
    payload = {"category": state["request"].category,
               "records": [r.model_dump(mode="json") for r in records]}
    try:
        batch = ProductBatch.model_validate(invoker(
            EXTRACT_PROMPT, json.dumps(payload, ensure_ascii=False), ProductBatch))
        ids = [p.product_id for p in batch.products]
        if any(p.category != state["request"].category for p in batch.products):
            raise ValueError("抽取结果包含错误商品类别")
        if len(ids) != len(set(ids)):
            raise ValueError("抽取结果包含重复 product_id")
        return {"products": batch.products,
                "search_summary": f"已整理出 {len(batch.products)} 个候选商品"}
    except Exception as error:
        return {"products": [],
                "errors": append_error(state.get("errors"), "shopping.extract", error)}
