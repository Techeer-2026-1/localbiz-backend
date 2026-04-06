"""Action Agent — Gemini ReAct 패턴 (캘린더/즐겨찾기/예약)"""
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from backend.src.graph.state import AgentState
from backend.src.tools.add_to_calendar import add_to_calendar, get_free_slots
from backend.src.tools.favorites import add_favorite, remove_favorite, list_favorites
from backend.src.tools.create_booking import create_booking
from backend.src.config import get_settings

settings = get_settings()

ACTION_TOOLS = [
    add_to_calendar,
    get_free_slots,
    add_favorite,
    remove_favorite,
    list_favorites,
    create_booking,
]

ACTION_SYSTEM = """당신은 사용자의 일정 관리와 예약을 돕는 어시스턴트입니다.
- 일정 추가 → add_to_calendar (날짜, 시간, 장소명 확인 후 실행)
- 빈 시간 확인 → get_free_slots
- 즐겨찾기 추가/삭제 → add_favorite / remove_favorite
- 즐겨찾기 목록 → list_favorites
- 예약 링크 → create_booking
오늘 날짜: {today}. 한국어로 친절하게 안내하세요."""

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0.1,
)


async def action_agent(state: AgentState) -> dict:
    """Action Agent 노드"""
    from datetime import date
    system = ACTION_SYSTEM.format(today=date.today().isoformat())
    agent_app = create_react_agent(llm, ACTION_TOOLS, state_modifier=system)

    # 이전 검색 결과가 있으면 컨텍스트로 포함
    context = ""
    if state.get("places"):
        place_names = [p.get("name", "") for p in state["places"][:3]]
        context = f"\n[검색된 장소: {', '.join(place_names)}]"

    input_content = state["user_message"] + context
    input_msg = HumanMessage(content=input_content)

    # user_id를 tool에 전달하기 위해 configurable 사용
    result = await agent_app.ainvoke(
        {"messages": [input_msg]},
        config={"configurable": {"user_id": state.get("user_id", "anonymous")}},
    )

    final_msg = result["messages"][-1]
    response_blocks = []

    # 도구 결과 타입에 따라 블록 생성
    for msg in result.get("messages", []):
        if hasattr(msg, "name"):
            try:
                import json
                content = json.loads(msg.content)
                if isinstance(content, dict):
                    if content.get("status") == "created":  # 캘린더 추가 성공
                        response_blocks.append({"type": "calendar", "data": content})
            except Exception:
                continue

    response_blocks.append({"type": "text", "content": final_msg.content})

    return {
        "response_blocks": response_blocks,
        "messages": result["messages"],
    }
