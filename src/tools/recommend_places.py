"""장소 추천 도구 — asyncio.gather 4-way 병렬 (SQL 0.3 + Vector 0.4 + Places 0.2 + Trend 0.1)"""
import asyncio
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from backend.src.db.postgres import fetch_all
from backend.src.db.opensearch import knn_search
from backend.src.external.google_places import get_place_detail
from backend.src.external.naver_blog import search_blog, extract_trend_score
from backend.src.utils.embedding import embed_text
from backend.src.config import get_settings

settings = get_settings()

WEIGHTS = {"sql": 0.3, "vector": 0.4, "places": 0.2, "trend": 0.1}

llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    api_key=settings.anthropic_api_key,
    temperature=0.5,
    max_tokens=512,
)


@tool
async def recommend_places(
    query: str,
    category: str = "",
    district: str = "",
    lat: float = 0.0,
    lng: float = 0.0,
    top_k: int = 5,
) -> list[dict]:
    """
    장소 추천 도구 — 4개 소스 병렬 검색 후 가중치 합산.

    Args:
        query: 자연어 추천 요청 (예: "분위기 좋은 주차 되는 이탈리안")
        category: 카테고리 필터
        district: 자치구 필터
        lat, lng: 사용자 위치
        top_k: 최종 추천 수
    """
    sql_task = _sql_search(query, category, district, lat, lng)
    vector_task = _vector_search(query, category, district)
    places_task = _google_places_search(query, category, lat, lng)
    trend_task = _naver_trend_search(query)

    sql_r, vector_r, places_r, trend_r = await asyncio.gather(
        sql_task, vector_task, places_task, trend_task,
        return_exceptions=True,
    )

    scores: dict[str, float] = {}
    place_data: dict[str, dict] = {}

    def safe_list(r) -> list:
        return r if isinstance(r, list) else []

    _accumulate(safe_list(sql_r),    scores, place_data, WEIGHTS["sql"],    "sql")
    _accumulate(safe_list(vector_r), scores, place_data, WEIGHTS["vector"], "vector")
    _accumulate(safe_list(places_r), scores, place_data, WEIGHTS["places"], "places")
    _accumulate_trend(safe_list(trend_r), scores, WEIGHTS["trend"])

    top_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:top_k]
    results = []
    for pid in top_ids:
        data = place_data.get(pid, {"place_id": pid})
        data["_recommendation_score"] = round(scores[pid], 3)
        results.append(data)

    # Claude로 추천 근거 생성
    if results:
        await _add_recommendation_reasons(query, results)

    return results


async def _sql_search(query, category, district, lat, lng) -> list[dict]:
    conditions, params, idx = ["1=1"], [], 1
    if category:
        conditions.append(f"category = ${idx}"); params.append(category); idx += 1
    if district:
        conditions.append(f"district = ${idx}"); params.append(district); idx += 1
    if query:
        conditions.append(f"(name ILIKE ${idx} OR raw_data::text ILIKE ${idx})")
        params.append(f"%{query}%"); idx += 1
    if lat and lng:
        conditions.append(
            f"ST_DWithin(geom::geography, ST_MakePoint(${idx}, ${idx+1})::geography, 3000)"
        )
        params.extend([lng, lat]); idx += 2

    sql = f"""
        SELECT place_id::text, name, category, address, district,
               ST_X(geom) AS lng, ST_Y(geom) AS lat,
               image_url, google_place_id, booking_url, phone
        FROM places WHERE {' AND '.join(conditions)}
        ORDER BY name LIMIT 20
    """
    return await fetch_all(sql, *params)


async def _vector_search(query, category, district) -> list[dict]:
    if not query:
        return []
    vec = await embed_text(query)
    metadata_filter = {}
    if category:
        metadata_filter["category"] = category
    if district:
        metadata_filter["district"] = district
    hits = await knn_search("places_vector", vec, k=20, metadata_filter=metadata_filter or None)
    return [{"place_id": h.get("place_id"), "_score": h.get("_score", 0),
             "name": h.get("metadata", {}).get("name", "")} for h in hits]


async def _google_places_search(query, category, lat, lng) -> list[dict]:
    if not (lat and lng and settings.google_places_api_key):
        return []
    from backend.src.external.google_places import search_nearby
    return await search_nearby(lat, lng, category or "establishment", radius=2000, keyword=query)


async def _naver_trend_search(query) -> list[dict]:
    if not settings.naver_client_id:
        return []
    return await search_blog(query, display=10, sort="date")


def _accumulate(results, scores, place_data, weight, source):
    for i, item in enumerate(results):
        pid = str(item.get("place_id") or item.get("place_id", ""))
        if not pid or pid == "None":
            continue
        base_score = weight * (1 - i * 0.03)
        scores[pid] = scores.get(pid, 0) + max(base_score, 0)
        if pid not in place_data:
            place_data[pid] = {**item, "_sources": [source]}
        else:
            place_data[pid]["_sources"] = place_data[pid].get("_sources", []) + [source]


def _accumulate_trend(items, scores, weight):
    trend_score = extract_trend_score(items)
    # 트렌드 점수는 이미 scores에 있는 장소들에만 가산
    for pid in list(scores.keys()):
        scores[pid] += trend_score * weight * 0.5  # 균등 가산 (장소별 블로그 매핑 없을 때)


async def _add_recommendation_reasons(query: str, places: list[dict]) -> None:
    """Claude API로 추천 근거 문구 생성"""
    names = [p.get("name", "") for p in places]
    prompt = f"""사용자가 "{query}"를 원합니다.
다음 장소들에 대해 각각 한 문장의 추천 이유를 작성하세요 (20자 이내, 자연스러운 한국어).
장소 목록: {', '.join(names)}
JSON 배열로만 응답: ["이유1", "이유2", ...]"""

    try:
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        import json
        reasons = json.loads(resp.content)
        for i, place in enumerate(places):
            if i < len(reasons):
                place["recommendation_reason"] = reasons[i]
    except Exception:
        pass
