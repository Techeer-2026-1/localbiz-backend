"""LangGraph AgentState 정의"""
import operator
from typing import Annotated, Any, List, Dict, Optional, Union
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # 세션 식별
    chat_id: str                            # thread_id (LangGraph Checkpointer)
    user_id: Optional[str]

    # 사용자 입력
    user_message: str
    user_location: Optional[Dict[str, Any]] # {"lat": 37.5, "lng": 127.0}

    # 의도 분류 결과
    intent: str                             # 12개 intent 중 하나
    sub_intent: Optional[str]

    # 검색/추천 결과
    places: List[Dict[str, Any]]            # photo_url 포함
    events: List[Dict[str, Any]]            # poster_url 포함
    route: Optional[Dict[str, Any]]
    calendar: Optional[Dict[str, Any]]
    favorites: Optional[Dict[str, Any]]
    booking: Optional[Dict[str, Any]]
    statistics: Optional[Dict[str, Any]]

    # WebSocket 응답 블록 누적 (operator.add → append)
    response_blocks: Annotated[List[Dict[str, Any]], operator.add]

    # LangGraph 메시지 이력
    messages: Annotated[List[BaseMessage], add_messages]
