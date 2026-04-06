"""장소 검색 도구 — PostgreSQL + PostGIS 공간 쿼리 (DB 없으면 mock fallback)"""
from langchain_core.tools import tool
from backend.src.db.postgres import fetch_all

_MOCK_PLACES = [
    {
        "place_id": "mock-001",
        "name": "봉피양 강남점",
        "category": "restaurant",
        "sub_category": "한식/냉면",
        "address": "서울특별시 강남구 테헤란로 133",
        "district": "gangnam",
        "lat": 37.5003,
        "lng": 127.0338,
        "phone": "02-556-5890",
        "google_place_id": None,
        "image_url": None,
        "booking_url": "https://booking.naver.com/booking/6/bizes/145027",
        "distance_m": 320,
        "_source": "mock",
    },
    {
        "place_id": "mock-002",
        "name": "카페 드 파리 강남",
        "category": "cafe",
        "sub_category": "디저트 카페",
        "address": "서울특별시 강남구 압구정로 46길 50",
        "district": "gangnam",
        "lat": 37.5269,
        "lng": 127.0302,
        "phone": "02-544-3366",
        "google_place_id": None,
        "image_url": None,
        "booking_url": None,
        "distance_m": 850,
        "_source": "mock",
    },
    {
        "place_id": "mock-003",
        "name": "선정릉",
        "category": "park",
        "sub_category": "역사공원",
        "address": "서울특별시 강남구 선릉로 100길 1",
        "district": "gangnam",
        "lat": 37.5094,
        "lng": 127.0474,
        "phone": "02-568-1393",
        "google_place_id": "ChIJxWLy_aihfDURn-BVT08DNAU",
        "image_url": None,
        "booking_url": None,
        "distance_m": 1200,
        "_source": "mock",
    },
    {
        "place_id": "mock-004",
        "name": "준오헤어 강남점",
        "category": "beauty",
        "sub_category": "미용실",
        "address": "서울특별시 강남구 강남대로 382",
        "district": "gangnam",
        "lat": 37.4979,
        "lng": 127.0276,
        "phone": "02-544-6604",
        "google_place_id": None,
        "image_url": None,
        "booking_url": "https://booking.naver.com/booking/6/bizes/2001",
        "distance_m": 500,
        "_source": "mock",
    },
    {
        "place_id": "mock-005",
        "name": "짐박스 강남",
        "category": "gym",
        "sub_category": "크로스핏",
        "address": "서울특별시 강남구 역삼동 737-20",
        "district": "gangnam",
        "lat": 37.4990,
        "lng": 127.0322,
        "phone": "02-555-9988",
        "google_place_id": None,
        "image_url": None,
        "booking_url": "https://booking.naver.com/booking/6/bizes/300001",
        "distance_m": 700,
        "_source": "mock",
    },
]


@tool
async def search_places(
    query: str,
    category: str = "",
    district: str = "",
    lat: float = 0.0,
    lng: float = 0.0,
    radius_m: int = 1000,
    limit: int = 10,
) -> list[dict]:
    """
    장소 검색 도구. PostgreSQL + PostGIS로 공간 쿼리 수행.
    DB 미연결 시 mock 데이터로 동작 (PoC).

    Args:
        query: 검색어 (장소명 또는 키워드)
        category: 카테고리 코드 (restaurant, cafe, gym, beauty, park, library, pharmacy 등)
        district: 자치구 코드 (gangnam, mapo 등)
        lat: 위도 (0이면 위치 기반 검색 안 함)
        lng: 경도 (0이면 위치 기반 검색 안 함)
        radius_m: 검색 반경 (미터), 기본 1000m
        limit: 최대 반환 개수
    """
    try:
        if lat != 0.0 and lng != 0.0:
            sql = """
                SELECT
                    place_id::text,
                    name,
                    category,
                    sub_category,
                    address,
                    district,
                    ST_Y(geom) AS lat,
                    ST_X(geom) AS lng,
                    phone,
                    google_place_id,
                    image_url,
                    booking_url,
                    raw_data,
                    ROUND(ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
                    )::numeric, 0)::int AS distance_m
                FROM places
                WHERE
                    ($3 = '' OR category = $3)
                    AND ($4 = '' OR district = $4)
                    AND ($5 = '' OR name ILIKE '%' || $5 || '%')
                    AND ST_DWithin(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography,
                        $6
                    )
                ORDER BY distance_m ASC
                LIMIT $7
            """
            rows = await fetch_all(sql, lat, lng, category, district, query, radius_m, limit)
        else:
            sql = """
                SELECT
                    place_id::text,
                    name,
                    category,
                    sub_category,
                    address,
                    district,
                    ST_Y(geom) AS lat,
                    ST_X(geom) AS lng,
                    phone,
                    google_place_id,
                    image_url,
                    booking_url,
                    raw_data,
                    NULL AS distance_m
                FROM places
                WHERE
                    ($1 = '' OR category = $1)
                    AND ($2 = '' OR district = $2)
                    AND ($3 = '' OR name ILIKE '%' || $3 || '%')
                ORDER BY name
                LIMIT $4
            """
            rows = await fetch_all(sql, category, district, query, limit)

        results = []
        for row in rows:
            item = dict(row)
            if item.get("raw_data") and isinstance(item["raw_data"], dict):
                raw = item["raw_data"]
                if not item.get("phone") and raw.get("전화번호"):
                    item["phone"] = raw["전화번호"]
            item["_source"] = "postgresql"
            results.append(item)

        return results

    except Exception:
        # DB 미연결 시 mock fallback (PoC 오케스트레이션 검증용)
        filtered = [p for p in _MOCK_PLACES if not category or p["category"] == category]
        if not filtered:
            filtered = _MOCK_PLACES
        if query:
            kw = query.lower()
            matched = [p for p in filtered if kw in p["name"].lower() or kw in p.get("sub_category", "").lower()]
            if matched:
                filtered = matched
        return filtered[:limit]
