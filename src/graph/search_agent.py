"""Search Agent — Gemini ReAct 패턴"""

import json
import os

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from backend.src.config import get_settings
from backend.src.graph.state import AgentState
from backend.src.tools.compare_reviews import compare_reviews
from backend.src.tools.get_place_detail import get_place_detail
from backend.src.tools.get_place_reviews import get_place_reviews
from backend.src.tools.recommend_places import recommend_places
from backend.src.tools.search_events import search_events
from backend.src.tools.search_places import search_places

settings = get_settings()

SEARCH_TOOLS = [
    search_places,
    search_events,
    recommend_places,
    get_place_detail,
    get_place_reviews,
    compare_reviews,
]

SEARCH_SYSTEM = """당신은 서울 로컬 생활 정보 검색 전문가입니다.
사용자 요청에 따라 적절한 도구를 사용하여 장소와 행사를 검색하세요.

[중요 지침]
1. 장소를 검색(search_places)한 후, 결과에 google_place_id가 있다면 반드시 get_place_detail을 호출하여 실시간 정보(평점, 영업여부, 이미지)를 가져오세요.
2. 최종 응답에는 검색된 장소의 상세 정보를 포함하여 한국어로 친절하게 답변하세요.
3. 도구의 출력 결과(리스트 또는 딕셔너리)를 기반으로 답변하세요.
4. 장소 비교/리뷰 비교 요청 시 compare_reviews 도구를 사용하세요. 비교 결과에 chart 데이터가 포함되며, 각 장소의 점수와 요약을 자연스럽게 설명해주세요."""

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0,
)
_agent = create_react_agent(llm, SEARCH_TOOLS, state_modifier=SEARCH_SYSTEM)


async def search_agent(state: AgentState) -> dict:
    """Search Agent 노드 — 도구 실행 및 결과 추출"""
    messages = state.get("messages", [])
    if not messages or not isinstance(messages[-1], HumanMessage):
        messages.append(HumanMessage(content=state["user_message"]))

    result = await _agent.ainvoke({"messages": messages})

    places = []
    events = []
    charts = []

    for msg in result.get("messages", []):
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            if "place_id" in item:
                                places.append(item)
                            elif "event_id" in item:
                                events.append(item)
                elif isinstance(data, dict):
                    if "place_id" in data:
                        places.append(data)
                    elif "event_id" in data:
                        events.append(data)
                    elif "chart" in data:
                        charts.append(data["chart"])
                        if "analysis_sources" in data:
                            charts.append(data["analysis_sources"])
            except Exception:
                continue

    unique_places = {p["place_id"]: p for p in places if "place_id" in p}.values()
    unique_places = list(unique_places)

    final_msg = result["messages"][-1]
    response_blocks = []

    if unique_places:
        response_blocks.append({"type": "places", "data": unique_places})
        markers = [
            {
                "place_id": p.get("place_id", ""),
                "name": p.get("name", ""),
                "lat": p.get("lat", 0),
                "lng": p.get("lng", 0),
                "category": p.get("category", ""),
            }
            for p in unique_places
            if p.get("lat") and p.get("lng")
        ]
        if markers:
            response_blocks.append(
                {
                    "type": "map_markers",
                    "center": {"lat": markers[0]["lat"], "lng": markers[0]["lng"]},
                    "zoom": 14,
                    "markers": markers,
                }
            )

    if events:
        response_blocks.append({"type": "events", "data": events})

    for chart in charts:
        response_blocks.append(chart)

    response_blocks.append({"type": "text", "content": final_msg.content})

    return {
        "places": unique_places,
        "events": events,
        "response_blocks": response_blocks,
        "messages": result["messages"],
    }
