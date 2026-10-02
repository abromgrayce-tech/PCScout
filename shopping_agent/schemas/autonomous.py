"""Structured decisions used by the autonomous main and child agents."""

from typing import Literal

from pydantic import Field

from ..models import StrictModel
from .computer_products import ComputerShoppingRequest, ProductCategory


AgentName = Literal["shopping_agent", "scoring_agent", "recommendation_agent", "finish"]


class MainAgentDecision(StrictModel):
    next_agent: AgentName
    reason: str = Field(min_length=1)
    request: ComputerShoppingRequest | None = None
    search_query: str | None = None


class SearchPlan(StrictModel):
    category: ProductCategory
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    required_terms: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)

