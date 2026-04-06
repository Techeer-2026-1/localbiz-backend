"""Place Search Node — Google Places Text Search 기반 웹 검색 노드"""
import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from backend.src.graph.state import AgentState
from backend.src.external.google_places import text_search

PARAM_EXTRACT_SYSTEM = """사용자의 장소 검색 요청에서 검색 파라미터를 추출하세요.

JSON으로만 응답하세요:
{
  "query": "Google Places 검색에 쓸 핵심 검색어 (예: 강남역 카페, 홍대 맛집)",
  "location": "지역 한정자 (서울 특정 동네/역이 명시되면 그대로, 없으면 '서울')",
  "limit": 사용자가 개수를 명시하면 그 숫자, 아니면 3
}"""

PLACE_DESC_SYSTEM = """당신은 서울 로컬 생활 정보 전문 어시스턴트입니다.
아래 장소 정보를 바탕으로 2~3문장으로 친근하게 한국어로 소개해주세요.
평점, 분위기, 추천 포인트를 간결하게 언급하세요."""

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0,
    response_mime_type="application/json",
    streaming=False,
)


async def place_search_node(state: AgentState) -> dict:
    """장소 검색 노드 — Google Places Text Search → 장소별 개별 블록 생성"""
    user_message = state["user_message"]

    # 1) 검색 파라미터 추출 (limit 포함)
    try:
        param_response = await llm.ainvoke([
            SystemMessage(content=PARAM_EXTRACT_SYSTEM),
            HumanMessage(content=user_message),
        ])
        params = json.loads(param_response.content)
    except Exception:
        params = {"query": user_message, "location": "서울", "limit": 3}

    query = params.get("query", user_message)
    location = params.get("location", "서울")
    limit = int(params.get("limit", 3))

    # 2) Google Places Text Search
    try:
        places = await text_search(query=query, location=location, limit=limit)
    except Exception:
        places = []

    # 3) 장소별 개별 블록 생성 (place 카드 + 텍스트 스트림)
    response_blocks = []

    if places:
        for p in places:
            # 장소 카드 (이미지 포함)
            response_blocks.append({"type": "place", "data": p})

            # 해당 장소 개별 텍스트 설명
            place_info = (
                f"장소명: {p['name']}\n"
                f"주소: {p.get('address', '정보 없음')}\n"
                f"평점: {p.get('rating', '정보 없음')}"
                f" ({p.get('user_ratings_total', 0)}개 리뷰)\n"
                f"영업 여부: {'영업중' if p.get('is_open') else '영업종료' if p.get('is_open') is False else '정보 없음'}"
            )
            response_blocks.append({
                "type": "text_stream",
                "system": PLACE_DESC_SYSTEM,
                "prompt": place_info,
            })
    else:
        response_blocks.append({
            "type": "text_stream",
            "system": None,
            "prompt": f"'{query}' 검색 결과가 없어. 다른 검색어로 시도해보라고 한국어로 안내해줘.",
        })

    return {
        "places": places,
        "response_blocks": response_blocks,
        "messages": [HumanMessage(content=user_message)],
    }
