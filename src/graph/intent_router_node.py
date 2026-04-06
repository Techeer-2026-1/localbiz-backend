"""Intent Router — Gemini로 12개 의도 분류"""
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from backend.src.graph.state import AgentState
from backend.src.config import get_settings

settings = get_settings()

INTENT_SYSTEM_PROMPT = """당신은 서울 로컬 생활 정보 AI 어시스턴트의 의도 분류기입니다.
사용자 메시지를 다음 12개 의도 중 하나로 분류하세요.

의도 목록:
- PLACE_SEARCH: 장소 검색 ("강남역 근처 카페", "마포구 헬스장 찾아줘")
- PLACE_RECOMMEND: 장소 추천 (조건 기반 맞춤 추천, "분위기 좋은", "주차 되는")
- EVENT_SEARCH: 행사/축제 검색 ("이번 주 서울 축제", "공연 있어?")
- COURSE_PLAN: 코스/일정 계획 ("하루 코스 짜줘", "데이트 코스")
- ANALYSIS: 분석/통계 ("강남 맛집 분포", "리뷰 비교")
- DETAIL_INQUIRY: 장소 상세 정보 ("영업시간", "메뉴", "주소")
- COST_ESTIMATE: 비용 견적 ("2명 저녁 예산", "얼마나 들어?")
- CROWDEDNESS: 혼잡도 ("지금 사람 많아?", "한산한 시간")
- BOOKING: 일정 추가/예약 ("캘린더에 추가", "예약해줘")
- REVIEW_WRITE: 리뷰 작성 ("리뷰 남길게", "후기 써줘")
- FAVORITE: 즐겨찾기 ("즐겨찾기 추가", "내 즐겨찾기 보여줘")
- GENERAL: 일반 대화 (위 카테고리에 해당하지 않는 모든 대화)

반드시 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{"intent": "INTENT_TYPE", "sub_intent": "세부 의도 (선택)", "reason": "분류 근거 한 줄"}"""

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0,
    response_mime_type="application/json",
)


async def intent_router(state: AgentState) -> dict:
    """의도 분류 노드 — Ollama로 intent 결정"""
    messages = [
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=state["user_message"]),
    ]

    VALID_INTENTS = {
        "PLACE_SEARCH", "PLACE_RECOMMEND", "EVENT_SEARCH", "COURSE_PLAN",
        "ANALYSIS", "DETAIL_INQUIRY", "COST_ESTIMATE", "CROWDEDNESS",
        "BOOKING", "REVIEW_WRITE", "FAVORITE", "GENERAL"
    }

    try:
        response = await llm.ainvoke(messages)
        import json
        result = json.loads(response.content)
        intent = result.get("intent", "GENERAL")
        if intent not in VALID_INTENTS:
            intent = "GENERAL"
        return {
            "intent": intent,
            "sub_intent": result.get("sub_intent"),
        }
    except Exception:
        return {"intent": "GENERAL", "sub_intent": None}
