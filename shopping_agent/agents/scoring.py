"""Hybrid scoring: deterministic hardware (70) plus LLM preferences (30)."""

import json
from typing import Callable
from pydantic import BaseModel

from ..hardware_scoring import score_hardware_requirements
from ..schemas.computer_products import (
    ProductScore, ScoringResult, SoftPreferenceScore, SoftScoringResult,
)
from ..state import ScoringAgentState
from .common import append_error

StructuredInvoker = Callable[[str, str, type[BaseModel]], BaseModel]
SOFT_SCORING_PROMPT = """你只负责软偏好语义评分，不能修改 Python 已计算的硬件分或
淘汰结论。对每个合格商品分别评分：用途匹配 0–15、用户偏好 0–10、其他主观需求
0–5，总分必须为三项之和且不超过 30。只依据输入事实给出简短 evidence；信息不足时
降低得分和 confidence。必须为每个输入 product_id 返回且只返回一个结果。"""


def _zero_soft_score(product_id: str) -> SoftPreferenceScore:
    return SoftPreferenceScore(
        product_id=product_id, use_case_score=0, preference_score=0,
        subjective_score=0, total_score=0,
        evidence=["硬件条件未通过，不进行软偏好评分"], confidence=1,
    )


def scoring_agent_node(state: ScoringAgentState, *, invoker: StructuredInvoker) -> dict:
    products = state.get("products", [])
    request = state["request"]
    try:
        hardware_scores = {
            product.product_id: score_hardware_requirements(request, product)
            for product in products
        }
        eligible = [p for p in products if hardware_scores[p.product_id].passed]
        soft_by_id: dict[str, SoftPreferenceScore] = {}
        if eligible:
            payload = {
                "use_cases": request.use_cases,
                "preferred_features": request.preferred_features,
                "products": [p.model_dump(mode="json") for p in eligible],
                "hardware_scores": {
                    p.product_id: hardware_scores[p.product_id].model_dump(mode="json")
                    for p in eligible
                },
            }
            soft_result = SoftScoringResult.model_validate(invoker(
                SOFT_SCORING_PROMPT,
                json.dumps(payload, ensure_ascii=False),
                SoftScoringResult,
            ))
            expected = {p.product_id for p in eligible}
            actual = [score.product_id for score in soft_result.scores]
            if set(actual) != expected or len(actual) != len(set(actual)):
                raise ValueError("软评分必须与通过硬件条件的商品 ID 一一对应")
            soft_by_id = {score.product_id: score for score in soft_result.scores}

        combined = []
        for product in products:
            hardware = hardware_scores[product.product_id]
            soft = soft_by_id.get(product.product_id) or _zero_soft_score(product.product_id)
            combined.append(ProductScore(
                product_id=product.product_id,
                hard_constraints_met=hardware.passed,
                rejection_reasons=hardware.rejection_reasons,
                hardware_score=hardware,
                soft_score=soft,
                total_score=hardware.total_score + soft.total_score,
                confidence=soft.confidence if hardware.passed else 1,
            ))
        return {"scoring_result": ScoringResult(
            scores=combined,
            scoring_summary="最终得分 = Python 硬件条件分（70）+ LLM 软偏好分（30）",
        )}
    except Exception as error:
        return {"errors": append_error(state.get("errors"), "scoring_agent", error)}
