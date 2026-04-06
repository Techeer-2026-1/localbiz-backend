"""Course Plan Node — 카테고리별 병렬 검색 → 경로 최적화 → 타임라인 생성"""

import asyncio
import json
import math
import os
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.src.external.calendar_mcp import add_calendar_event
from backend.src.external.google_places import text_search
from backend.src.graph.state import AgentState

llm_json = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0,
    response_mime_type="application/json",
    streaming=False,
)

PARAM_SYSTEM = """사용자의 코스/일정 계획 요청에서 파라미터를 추출하세요.

JSON으로만 응답:
{
  "date": "YYYY-MM-DD (날짜 언급 시. 없으면 빈 문자열)",
  "area": "지역명 (없으면 서울)",
  "start_time": "HH:MM (없으면 10:00)",
  "categories": ["방문 순서대로 카테고리 목록"],
  "preferences": "기타 취향/조건 (분위기, 무료, 어린이, 데이트 등. 없으면 빈 문자열)",
  "add_to_calendar": true/false (캘린더 추가 언급 시 true. 기본 false),
  "num_stops": 방문 장소 수 (언급 없으면 4)
}

categories 작성 규칙:
- 사용자가 카테고리를 명시한 경우: 해당 카테고리를 포함하되 num_stops에 맞게 자연스럽게 보완
- 보완 패턴 예시: 카페 → [카페, 전시/쇼핑, 식당], 전시 → [카페, 전시, 식당]
- 하루 코스(num_stops≥4): 오전 카페 → 오전 활동 → 점심 → 오후 활동 → (저녁) 순서로 구성
- 반나절(num_stops=2~3): 카페/브런치 → 활동 → (식사) 순서
- 데이트: 카페, 전시/공원, 레스토랑 위주
- 아이/가족: 체험, 공원, 식당 위주

예시:
- "홍대 카페 전시 코스" → area=홍대, categories=["카페","전시","레스토랑"], num_stops=3
- "강남 하루 데이트 코스" → area=강남, categories=["카페","미술관","레스토랑","칵테일바"], num_stops=4
- "성수 하루 일정 4곳" → area=성수, categories=["카페","전시","점심","쇼핑"], num_stops=4
- "이번 주말 홍대 반나절 코스" → area=홍대, categories=["브런치","전시","카페"], num_stops=3"""

# 카테고리별 기본 소요시간 (분)
_DURATION_MAP = {
    "카페": 60,
    "커피": 60,
    "브런치": 90,
    "디저트": 45,
    "식당": 90,
    "레스토랑": 90,
    "점심": 90,
    "저녁": 100,
    "밥": 90,
    "전시": 120,
    "미술관": 120,
    "박물관": 120,
    "갤러리": 90,
    "공원": 60,
    "산책": 60,
    "나들이": 90,
    "쇼핑": 90,
    "시장": 60,
    "문화": 90,
    "체험": 90,
    "공연": 120,
    "영화": 130,
    "술": 90,
    "바": 90,
    "펍": 90,
}


def _duration(category: str) -> int:
    for key, dur in _DURATION_MAP.items():
        if key in category:
            return dur
    return 60


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _walk_min(km: float) -> int:
    return max(5, int(km / 0.08))  # 도보 80m/min 기준


def _nearest_neighbor(places_by_cat: list[list[dict]], start_lat=37.5665, start_lng=126.9780) -> list[dict]:
    """카테고리 순서 유지 + 이전 장소에서 가장 가까운 장소 선택"""
    result = []
    prev_lat, prev_lng = start_lat, start_lng
    for cat_places in places_by_cat:
        if not cat_places:
            continue
        best = min(
            cat_places,
            key=lambda p: _haversine_km(prev_lat, prev_lng, p.get("lat", start_lat), p.get("lng", start_lng)),
        )
        result.append(best)
        prev_lat = best.get("lat", prev_lat)
        prev_lng = best.get("lng", prev_lng)
    return result


async def course_plan_node(state: AgentState) -> dict:
    """코스 계획 노드 — 카테고리별 장소 검색 → 경로 최적화 → 타임라인 + 캘린더"""
    user_message = state["user_message"]
    user_location = state.get("user_location") or {}

    # 1) 파라미터 추출
    try:
        resp = await llm_json.ainvoke(
            [
                SystemMessage(content=PARAM_SYSTEM),
                HumanMessage(content=f"오늘: {date.today().isoformat()}\n\n{user_message}"),
            ]
        )
        params = json.loads(resp.content)
    except Exception:
        params = {}

    course_date = params.get("date", "")
    area = params.get("area", "서울")
    start_time_str = params.get("start_time", "10:00")
    categories = params.get("categories", [])
    preferences = params.get("preferences", "")
    add_cal = params.get("add_to_calendar", False)
    num_stops = min(max(int(params.get("num_stops", 4)), 2), 6)

    # 기본 카테고리 보완
    _defaults = ["카페", "전시", "레스토랑", "공원"]
    if not categories:
        categories = _defaults[:num_stops]
    elif len(categories) < num_stops:
        extra = [c for c in _defaults if c not in categories]
        categories = categories + extra
    categories = categories[:num_stops]

    # 2) 카테고리별 병렬 검색 (Google Places)
    pref_sfx = f" {preferences}" if preferences else ""
    search_results = await asyncio.gather(
        *[text_search(f"{cat}{pref_sfx} {area}", location=area, limit=3) for cat in categories],
        return_exceptions=True,
    )

    places_by_cat: list[list[dict]] = []
    for i, res in enumerate(search_results):
        if isinstance(res, list) and res:
            for p in res:
                p["category_label"] = categories[i]
            places_by_cat.append(res)
        else:
            places_by_cat.append([])

    # 3) 경로 최적화
    start_lat = user_location.get("lat", 37.5665)
    start_lng = user_location.get("lng", 126.9780)
    route_places = _nearest_neighbor(places_by_cat, start_lat, start_lng)

    if not route_places:
        return {
            "events": [],
            "response_blocks": [
                {
                    "type": "text_stream",
                    "system": None,
                    "prompt": f"'{user_message}' 코스를 구성할 장소를 찾지 못했습니다. 지역이나 카테고리를 다르게 입력해보라고 안내해주세요.",
                }
            ],
            "messages": [HumanMessage(content=user_message)],
        }

    # 4) 타임라인 계산
    try:
        sh, sm = map(int, start_time_str.split(":"))
    except Exception:
        sh, sm = 10, 0
    cur_min = sh * 60 + sm

    stops = []
    for i, place in enumerate(route_places):
        cat_label = place.get("category_label", "")
        dur = _duration(cat_label)
        t_start = f"{cur_min // 60:02d}:{cur_min % 60:02d}"
        cur_min += dur
        t_end = f"{cur_min // 60:02d}:{cur_min % 60:02d}"

        walk = 0
        if i < len(route_places) - 1:
            nxt = route_places[i + 1]
            km = _haversine_km(
                place.get("lat", start_lat),
                place.get("lng", start_lng),
                nxt.get("lat", start_lat),
                nxt.get("lng", start_lng),
            )
            walk = _walk_min(km)
            cur_min += walk

        stops.append(
            {
                "order": i + 1,
                "time_start": t_start,
                "time_end": t_end,
                "duration_min": dur,
                "walk_to_next_min": walk,
                "place": place,
                "category_label": cat_label,
            }
        )

    # 5) 응답 블록
    response_blocks: list[dict] = []

    # 코스 타임라인 카드
    response_blocks.append(
        {
            "type": "course",
            "date": course_date,
            "area": area,
            "stops": stops,
        }
    )

    # 지도 마커
    markers = [
        {
            "place_id": s["place"].get("place_id", f"stop-{s['order']}"),
            "name": s["place"].get("name", ""),
            "lat": s["place"].get("lat", 0),
            "lng": s["place"].get("lng", 0),
            "category": s["category_label"],
            "label": str(s["order"]),
        }
        for s in stops
        if s["place"].get("lat")
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

    # 6) 캘린더 추가 (날짜 있고 요청한 경우)
    cal_count = 0
    if add_cal and course_date:
        cal_results = await asyncio.gather(
            *[
                add_calendar_event(
                    title=f"{s['category_label']} — {s['place']['name']}",
                    date=course_date,
                    time=s["time_start"],
                    location=s["place"].get("address", ""),
                    duration_minutes=s["duration_min"],
                )
                for s in stops
            ],
            return_exceptions=True,
        )
        for res in cal_results:
            if isinstance(res, dict) and res.get("status") == "created":
                response_blocks.append({"type": "calendar", "data": res})
                cal_count += 1

    # 7) 텍스트 요약 스트리밍
    stops_summary = "\n".join(
        f"{s['order']}. {s['time_start']}~{s['time_end']}  {s['category_label']}: {s['place']['name']}"
        f"  ({s['place'].get('address', '')})"
        + (f"  → 도보 {s['walk_to_next_min']}분" if s["walk_to_next_min"] else "")
        for s in stops
    )
    cal_note = (
        f" 캘린더에 {cal_count}개 일정을 추가했어."
        if cal_count
        else (" 캘린더에 추가하려면 날짜도 알려줘." if add_cal and not course_date else "")
    )

    response_blocks.append(
        {
            "type": "text_stream",
            "system": "당신은 서울 로컬 코스 플래너입니다. 아래 코스를 바탕으로 각 장소의 매력과 이동 동선을 자연스럽고 친근하게 소개해주세요. 이모지 사용 가능.",
            "prompt": (
                f"사용자 요청: {user_message}\n"
                f"지역: {area}"
                + (f" / {course_date}" if course_date else "")
                + f"\n\n코스:\n{stops_summary}\n\n{cal_note}"
            ),
        }
    )

    return {
        "places": [s["place"] for s in stops],
        "response_blocks": response_blocks,
        "messages": [HumanMessage(content=user_message)],
    }
