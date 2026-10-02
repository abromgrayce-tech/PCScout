"""自主主图以及三个拥有私有 State 的子图。"""

from functools import partial
from langgraph.graph import END, START, StateGraph

from .agents import (main_agent_node, normalize_products_node, plan_search_node,
                     recommendation_agent_node, run_search_node, scoring_agent_node)
from .llm import invoke_structured
from .search_backend import JsonlProductSearchBackend, ProductSearchBackend
from .state import (MainAgentState, RecommendationAgentState,
                    ScoringAgentState, ShoppingAgentState)


def _route(state: MainAgentState) -> str:
    return state["next_agent"]


def build_shopping_agent(*, invoker, backend: ProductSearchBackend):
    graph = StateGraph(ShoppingAgentState)
    graph.add_node("plan", partial(plan_search_node, invoker=invoker))
    graph.add_node("search", partial(run_search_node, backend=backend))
    graph.add_node("extract", partial(normalize_products_node, invoker=invoker))
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "extract")
    graph.add_edge("extract", END)
    return graph.compile()


def build_scoring_agent(*, invoker):
    graph = StateGraph(ScoringAgentState)
    graph.add_node("score", partial(scoring_agent_node, invoker=invoker))
    graph.add_edge(START, "score")
    graph.add_edge("score", END)
    return graph.compile()


def build_recommendation_agent(*, invoker):
    graph = StateGraph(RecommendationAgentState)
    graph.add_node("recommend", partial(recommendation_agent_node, invoker=invoker))
    graph.add_edge(START, "recommend")
    graph.add_edge("recommend", END)
    return graph.compile()


def build_graph(*, invoker=invoke_structured,
                search_backend: ProductSearchBackend | None = None,
                max_steps: int = 8):
    """以 LLM 主 Agent 循环替换原来的固定节点工作流。"""
    backend = search_backend or JsonlProductSearchBackend()
    graph = StateGraph(MainAgentState)
    graph.add_node("main_agent",
                   partial(main_agent_node, invoker=invoker, max_steps=max_steps))
    # 子图私有字段不会进入 MainAgentState，只有同名输入/输出跨越边界。
    graph.add_node("shopping_agent",
                   build_shopping_agent(invoker=invoker, backend=backend))
    graph.add_node("scoring_agent", build_scoring_agent(invoker=invoker))
    graph.add_node("recommendation_agent", build_recommendation_agent(invoker=invoker))
    graph.add_edge(START, "main_agent")
    graph.add_conditional_edges("main_agent", _route, {
        "shopping_agent": "shopping_agent",
        "scoring_agent": "scoring_agent",
        "recommendation_agent": "recommendation_agent",
        "finish": END,
    })
    graph.add_edge("shopping_agent", "main_agent")
    graph.add_edge("scoring_agent", "main_agent")
    graph.add_edge("recommendation_agent", "main_agent")
    return graph.compile()
