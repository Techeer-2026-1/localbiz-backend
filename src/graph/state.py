"""LangGraph AgentState 정의"""

import operator
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # 세션 식별
    chat_id: str  # thread_id (LangGraph Checkpointer)
    user_id: str | None

    # 사용자 입력
    user_message: str
    user_location: dict[str, Any] | None  # {"lat": 37.5, "lng": 127.0}

    # 의도 분류 결과
    intent: str  # 12개 intent 중 하나
    sub_intent: str | None

    # 검색/추천 결과
    places: list[dict[str, Any]]  # photo_url 포함
    events: list[dict[str, Any]]  # poster_url 포함
    route: dict[str, Any] | None
    calendar: dict[str, Any] | None
    favorites: dict[str, Any] | None
    booking: dict[str, Any] | None
    statistics: dict[str, Any] | None

    # WebSocket 응답 블록 누적 (operator.add → append)
    response_blocks: Annotated[list[dict[str, Any]], operator.add]

    # LangGraph 메시지 이력
    messages: Annotated[list[BaseMessage], add_messages]
