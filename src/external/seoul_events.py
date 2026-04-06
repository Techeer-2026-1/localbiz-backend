"""서울 열린데이터광장 — 문화행사 API 클라이언트"""

import httpx

from backend.src.config import get_settings

settings = get_settings()

BASE_URL = "http://openapi.seoul.go.kr:8088"

# 동네명 → 자치구 매핑
NEIGHBORHOOD_TO_DISTRICT = {
    "홍대": "마포구",
    "합정": "마포구",
    "망원": "마포구",
    "상수": "마포구",
    "강남": "강남구",
    "압구정": "강남구",
    "청담": "강남구",
    "역삼": "강남구",
    "삼성": "강남구",
    "이태원": "용산구",
    "한남": "용산구",
    "용산": "용산구",
    "신촌": "서대문구",
    "연남": "마포구",
    "연희": "서대문구",
    "종로": "종로구",
    "인사동": "종로구",
    "광화문": "종로구",
    "북촌": "종로구",
    "성수": "성동구",
    "왕십리": "성동구",
    "건대": "광진구",
    "뚝섬": "광진구",
    "잠실": "송파구",
    "석촌": "송파구",
    "신림": "관악구",
    "서울대": "관악구",
    "노원": "노원구",
    "도봉": "도봉구",
    "마포": "마포구",
    "서대문": "서대문구",
    "동대문": "동대문구",
    "중구": "중구",
    "중랑": "중랑구",
}


def resolve_district(location: str) -> str:
    """동네명 또는 자치구명 → 표준 자치구명 반환"""
    if not location:
        return ""
    # 이미 구 이름이면 그대로
    if location.endswith("구"):
        return location
    # 동네명 매핑
    for neighborhood, district in NEIGHBORHOOD_TO_DISTRICT.items():
        if neighborhood in location:
            return district
    return location


async def search_events(
    keyword: str = "",
    date_start: str = "",
    date_end: str = "",
    district: str = "",
    category: str = "",
    is_free=None,  # True=무료만, False=유료만, None=전체
    target: str = "",
    limit: int = 5,
) -> list[dict]:
    """
    서울시 문화행사 검색

    Args:
        keyword   : 제목/장소/출연진 키워드
        date_start: 시작일 YYYY-MM-DD
        date_end  : 종료일 YYYY-MM-DD
        district  : 자치구 (동네명도 허용 — 내부에서 변환)
        category  : 행사 카테고리
        is_free   : True=무료만, False=유료만, None=전체
        target    : 대상 (어린이, 가족, 누구나 등)
        limit     : 최대 결과 수
    """
    resolved_district = resolve_district(district)
    fetch_size = max(limit * 6, 30)
    url = f"{BASE_URL}/{settings.seoul_api_key}/json/culturalEventInfo/1/{fetch_size}/"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            data = response.json()
    except Exception:
        return []

    rows = data.get("culturalEventInfo", {}).get("row", [])
    if not rows:
        return []

    results = []
    for r in rows:
        event_start = (r.get("STRTDATE") or "")[:10]
        event_end = (r.get("END_DATE") or "9999-12-31")[:10]

        # 날짜 필터 — 기간 겹침 체크
        if date_start and event_end < date_start:
            continue
        if date_end and event_start > date_end:
            continue

        # 자치구 필터
        if resolved_district and resolved_district.replace("구", "") not in r.get("GUNAME", ""):
            continue

        # 카테고리 필터
        if category:
            codename = r.get("CODENAME", "")
            if category not in codename and codename not in category:
                continue

        # 무료/유료 필터
        if is_free is True and r.get("IS_FREE", "") != "무료":
            continue
        if is_free is False and r.get("IS_FREE", "") == "무료":
            continue

        # 대상 필터
        if target:
            use_trgt = r.get("USE_TRGT", "")
            if target not in use_trgt and use_trgt != "누구나":
                continue

        # 키워드 필터 (제목 + 장소 + 출연진)
        if keyword:
            searchable = (
                r.get("TITLE", "")
                + r.get("PLACE", "")
                + r.get("PLAYER", "")
                + r.get("CODENAME", "")
                + r.get("THEMECODE", "")
            )
            if keyword not in searchable:
                continue

        results.append(
            {
                "event_id": r.get("TITLE", "") + "_" + event_start,
                "title": r.get("TITLE", ""),
                "category": r.get("CODENAME", ""),
                "place_name": r.get("PLACE", ""),
                "address": r.get("GUNAME", "") + (" " + r.get("PLACE", "") if r.get("PLACE") else ""),
                "date_start": event_start,
                "date_end": event_end,
                "price": r.get("USE_FEE", ""),
                "target": r.get("USE_TRGT", ""),
                "player": r.get("PLAYER", ""),
                "pro_time": r.get("PRO_TIME", ""),
                "poster_url": r.get("MAIN_IMG", ""),
                "detail_url": r.get("HMPG_ADDR", "") or r.get("ORG_LINK", ""),
                "is_free": r.get("IS_FREE", "") == "무료",
                "lat": float(r["LAT"]) if r.get("LAT") else None,
                "lng": float(r["LOT"]) if r.get("LOT") else None,
            }
        )

        if len(results) >= limit:
            break

    return results
