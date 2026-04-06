"""LangGraph 그래프 빌더 — 노드 등록, 조건 분기, Checkpointer 설정"""

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from backend.src.config import get_settings
from backend.src.graph.action_agent import action_agent
from backend.src.graph.conversation import conversation_agent
from backend.src.graph.course_plan_node import course_plan_node
from backend.src.graph.event_search_node import event_search_node
from backend.src.graph.intent_router_logic import route_by_intent
from backend.src.graph.intent_router_node import intent_router
from backend.src.graph.place_recommend_node import place_recommend_node
from backend.src.graph.place_search_node import place_search_node
from backend.src.graph.response_composer import response_composer
from backend.src.graph.search_agent import search_agent
from backend.src.graph.state import AgentState

logger = logging.getLogger(__name__)
settings = get_settings()

_graph = None


async def build_graph():
    """LangGraph 컴파일 및 Checkpointer 설정 (Postgres -> Memory Fallback)"""
    global _graph

    if _graph is not None:
        return _graph

    # Checkpointer 설정
    checkpointer = MemorySaver()  # 포트그레스 문제로 PoC는 메모리 고정

    # StateGraph 정의
    workflow = StateGraph(AgentState)

    # 노드 등록
    workflow.add_node("intent_router", intent_router)
    workflow.add_node("conversation", conversation_agent)
    workflow.add_node("place_search", place_search_node)
    workflow.add_node("place_recommend", place_recommend_node)
    workflow.add_node("event_search", event_search_node)
    workflow.add_node("course_plan", course_plan_node)
    workflow.add_node("search_agent", search_agent)
    workflow.add_node("action_agent", action_agent)
    workflow.add_node("response_composer", response_composer)

    # 시작점
    workflow.set_entry_point("intent_router")

    # Intent Router → 조건 분기
    workflow.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "conversation": "conversation",
            "place_search": "place_search",
            "place_recommend": "place_recommend",
            "event_search": "event_search",
            "course_plan": "course_plan",
            "search_agent": "search_agent",
            "action_agent": "action_agent",
        },
    )

    # 각 에이전트 → Response Composer
    workflow.add_edge("conversation", "response_composer")
    workflow.add_edge("place_search", "response_composer")
    workflow.add_edge("place_recommend", "response_composer")
    workflow.add_edge("event_search", "response_composer")
    workflow.add_edge("course_plan", "response_composer")

    # search_agent에서 intent가 COURSE_PLAN이면 action_agent로
    def route_after_search(state: AgentState) -> str:
        if state.get("intent") == "COURSE_PLAN":
            return "action_agent"
        return "response_composer"

    workflow.add_conditional_edges(
        "search_agent",
        route_after_search,
        {
            "action_agent": "action_agent",
            "response_composer": "response_composer",
        },
    )

    workflow.add_edge("action_agent", "response_composer")
    workflow.add_edge("response_composer", END)

    _graph = workflow.compile(checkpointer=checkpointer)
    return _graph


async def get_graph():
    return await build_graph()
