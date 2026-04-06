"""Place Recommend Node — 조건/취향 기반 맞춤 장소 추천 (네이버 블로그 리뷰 연동)"""
import os
import re
import json
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from backend.src.graph.state import AgentState
from backend.src.external.google_places import text_search, get_place_reviews
from backend.src.external.naver_blog import search_blog, summarize_reviews

CONDITION_EXTRACT_SYSTEM = """사용자의 장소 추천 요청에서 추천 조건을 추출하세요.

JSON으로만 응답하세요:
{
  "category": "찾는 장소 종류 (예: 카페, 맛집, 헬스장)",
  "location": "지역 (명시된 경우, 없으면 '서울')",
  "conditions": ["조건1", "조건2", ...],
  "queries": [
    "핵심 검색어 (카테고리 + 지역만, 예: 강남 카페)",
    "조건 1~2개 포함 검색어 (예: 조용한 강남 카페)",
    "다른 조건 조합 검색어 (예: 데이트 분위기 강남 카페)"
  ],
  "limit": 사용자가 개수 명시 시 그 숫자, 아니면 3
}

queries는 반드시 3개. 첫 번째는 조건 없이 카테고리+지역만, 나머지 둘은 조건을 나눠서 포함."""

RECOMMEND_REASON_SYSTEM = """당신은 서울 로컬 생활 정보 전문 어시스턴트입니다.
사용자의 추천 조건, 장소 기본 정보, 실제 방문자 블로그 후기를 종합해서
이 장소를 추천하는 이유를 2~3문장으로 설명해주세요.
블로그 후기에서 조건과 관련된 내용이 있으면 구체적으로 인용하세요.
친근한 한국어로 작성하세요."""

llm_json = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0,
    response_mime_type="application/json",
    streaming=False,
)


async def _multi_search(queries: list[str], location: str, limit: int) -> list[dict]:
    """여러 쿼리를 병렬로 검색하고 place_id 기준 중복 제거 후 상위 limit개 반환"""
    fetch_per_query = max(limit, 5)
    results = await asyncio.gather(*[
        text_search(query=q, location=location, limit=fetch_per_query)
        for q in queries
    ], return_exceptions=True)

    seen: set[str] = set()
    merged: list[dict] = []
    for batch in results:
        if isinstance(batch, Exception):
            continue
        for place in batch:
            pid = place.get("place_id", "")
            if pid and pid not in seen:
                seen.add(pid)
                merged.append(place)

    # 평점 높은 순 정렬 후 limit개
    merged.sort(key=lambda p: p.get("rating") or 0, reverse=True)
    return merged[:limit]


def _rerank(reviews: list[dict], conditions: list[str], top_k: int = 5) -> list[dict]:
    """조건 키워드가 많이 등장하는 리뷰를 위로 리랭킹"""
    if not conditions:
        return reviews[:top_k]

    def score(r: dict) -> int:
        body = r.get("text", "").lower()
        return sum(1 for cond in conditions if cond.lower() in body)

    return sorted(reviews, key=score, reverse=True)[:top_k]


async def _fetch_all_reviews(
    place: dict, category: str, conditions: list[str]
) -> tuple[str, list[dict]]:
    """Naver Blog + Google Places 리뷰를 병렬로 수집 → 리랭킹 → (요약 텍스트, 참조 링크)"""
    place_name = place["name"]
    place_id   = place.get("place_id", "")

    # 병렬 수집
    naver_task  = search_blog(f"{place_name} {category}", display=10)
    google_task = get_place_reviews(place_id) if place_id else asyncio.sleep(0, result=[])

    naver_items, google_reviews = await asyncio.gather(naver_task, google_task)

    # 네이버 블로그 — 장소명 포함 글만 필터
    name_tokens = [t for t in re.split(r"[\s\(\)\[\]·,.]", place_name) if len(t) >= 2]

    def naver_relevant(item: dict) -> bool:
        body = re.sub(r"<[^>]+>", "", item.get("title", "") + item.get("description", "")).lower()
        return any(tok.lower() in body for tok in name_tokens)

    naver_filtered = [i for i in naver_items if naver_relevant(i)][:5]

    # 네이버 → 공통 형식으로 변환
    naver_reviews = [
        {
            "text": re.sub(r"<[^>]+>", "", item.get("description", "")).strip(),
            "source": "naver",
            "link": item.get("link", ""),
            "title": re.sub(r"<[^>]+>", "", item.get("title", "")).strip(),
        }
        for item in naver_filtered if item.get("description")
    ]

    # 전체 리뷰 합산 → 리랭킹
    all_reviews = naver_reviews + (google_reviews or [])
    ranked = _rerank(all_reviews, conditions, top_k=5)

    # LLM 프롬프트용 텍스트
    review_text = "\n".join(
        f"[{'구글' if r.get('source') == 'google' else '네이버'}] "
        f"{'★' * (r['rating'] if r.get('rating') else 0)} {r['text'][:200]}"
        for r in ranked if r.get("text")
    )

    # 참조 링크 (네이버만 링크 있음)
    refs = [
        {"title": r["title"], "link": r["link"], "postdate": ""}
        for r in ranked
        if r.get("source") == "naver" and r.get("link")
    ]

    return review_text, refs


async def place_recommend_node(state: AgentState) -> dict:
    """장소 추천 노드 — 조건 추출 → 다중 쿼리 병렬 검색 → 네이버 리뷰 → 추천 이유 스트리밍"""
    user_message = state["user_message"]

    # 1) 추천 조건 + 다중 쿼리 추출
    try:
        param_response = await llm_json.ainvoke([
            SystemMessage(content=CONDITION_EXTRACT_SYSTEM),
            HumanMessage(content=user_message),
        ])
        params = json.loads(param_response.content)
    except Exception:
        params = {
            "category": "장소",
            "location": "서울",
            "conditions": [],
            "queries": [user_message],
            "limit": 3,
        }

    conditions: list = params.get("conditions", [])
    category: str = params.get("category", "장소")
    location: str = params.get("location", "서울")
    queries: list = params.get("queries") or [params.get("query", user_message)]
    limit: int = min(max(int(params.get("limit", 3)), 1), 10)
    conditions_text = ", ".join(conditions) if conditions else "특별한 조건 없음"

    # 2) 다중 쿼리 병렬 검색 → 중복 제거 → 평점순 정렬
    places = await _multi_search(queries, location, limit)

    if not places:
        return {
            "places": [],
            "response_blocks": [{
                "type": "text_stream",
                "system": None,
                "prompt": f"조건에 맞는 장소를 찾지 못했어. 다른 조건이나 지역으로 시도해보라고 한국어로 안내해줘.",
            }],
            "messages": [HumanMessage(content=user_message)],
        }

    # 3) 네이버 블로그 후기 병렬 수집 (장소명 + 지역 검색)
    review_results = await asyncio.gather(*[
        _fetch_all_reviews(p, category, conditions) for p in places
    ])
    review_texts = [r[0] for r in review_results]
    review_refs  = [r[1] for r in review_results]

    # 4) 응답 블록 생성
    response_blocks = []

    response_blocks.append({
        "type": "text_stream",
        "system": "당신은 서울 로컬 생활 정보 전문 어시스턴트입니다. 친근하고 간결하게 한국어로 답변하세요.",
        "prompt": (
            f"사용자 요청: {user_message}\n"
            f"추출된 조건: {conditions_text}\n"
            f"검색 지역: {location}\n\n"
            f"이 조건으로 {len(places)}곳을 찾았다고 한두 문장으로 간략히 안내해줘. "
            f"장소 목록은 아래에 따로 보여줄 거니까 설명은 짧게."
        ),
    })

    for p, reviews, refs in zip(places, review_texts, review_refs):
        response_blocks.append({"type": "place", "data": p})

        place_info = (
            f"장소명: {p['name']}\n"
            f"주소: {p.get('address', '정보 없음')}\n"
            f"평점: {p.get('rating', '정보 없음')}"
            f" ({p.get('user_ratings_total', 0)}개 리뷰)\n"
            f"영업 여부: {'영업중' if p.get('is_open') else '영업종료' if p.get('is_open') is False else '정보 없음'}"
        )
        review_section = f"\n\n실제 방문자 블로그 후기:\n{reviews}" if reviews else "\n\n(블로그 후기 없음)"

        response_blocks.append({
            "type": "text_stream",
            "system": RECOMMEND_REASON_SYSTEM,
            "prompt": (
                f"사용자 추천 조건: {conditions_text}\n\n"
                f"장소 정보:\n{place_info}"
                f"{review_section}"
            ),
        })

        if refs:
            response_blocks.append({"type": "references", "items": refs})

    return {
        "places": places,
        "response_blocks": response_blocks,
        "messages": [HumanMessage(content=user_message)],
    }
