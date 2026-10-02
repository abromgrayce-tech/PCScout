"""Main graph state and the three private sub-agent states."""

from typing import TypedDict

from .schemas.autonomous import SearchPlan
from .schemas.computer_products import (
    ComputerProduct,
    ComputerShoppingRequest,
    RecommendationResult,
    ScoringResult,
)
from .search_backend import RawProductRecord


class MainAgentState(TypedDict, total=False):
    """主 Agent 只保存需要跨子 Agent 传递的事实。"""

    user_query: str
    request: ComputerShoppingRequest
    search_query: str
    products: list[ComputerProduct]
    search_summary: str
    scoring_result: ScoringResult
    recommendation: RecommendationResult
    next_agent: str
    route_reason: str
    route_history: list[str]
    errors: list[str]
    step_count: int


class ShoppingAgentState(TypedDict, total=False):
    """Private working memory of the shopping/search sub-agent."""

    request: ComputerShoppingRequest
    search_query: str
    search_plan: SearchPlan
    raw_products: list[RawProductRecord]
    products: list[ComputerProduct]
    search_summary: str
    errors: list[str]


class ScoringAgentState(TypedDict, total=False):
    """Private working memory of the scoring sub-agent."""

    request: ComputerShoppingRequest
    products: list[ComputerProduct]
    scoring_result: ScoringResult
    errors: list[str]


class RecommendationAgentState(TypedDict, total=False):
    """Private working memory of the recommendation sub-agent."""

    request: ComputerShoppingRequest
    products: list[ComputerProduct]
    scoring_result: ScoringResult
    recommendation: RecommendationResult
    errors: list[str]
