"""
장소 카드 PoC 전용 엔드포인트

검증:
  1. Google Places Nearby Search → place_id 목록
  2. Place Details → photo_reference, open_now, rating, hours, phone
  3. Photos API URL 구성 (photo_reference → URL)
  4. Redis 캐싱 (X-Cache 헤더로 HIT/MISS 노출)
"""
import hashlib
import json
import time
import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from backend.src.config import get_settings
from backend.src.db.redis import cache_get, cache_set

router = APIRouter(prefix="/api/v1/poc", tags=["poc"])
settings = get_settings()

PLACES_API = "https://maps.googleapis.com/maps/api/place"

DETAIL_FIELDS = (
    "name,rating,user_ratings_total,formatted_phone_number,"
    "opening_hours,current_opening_hours,price_level,"
    "photos,formatted_address,editorial_summary,website"
)


def _cache_key(place_id: str) -> str:
    return "poc:place:" + hashlib.md5(place_id.encode()).hexdigest()


@router.get("/place/{google_place_id}")
async def poc_place_detail(google_place_id: str):
    """
    Place Details 조회 + Redis 캐싱.
    응답 헤더 X-Cache: HIT | MISS
    """
    cache_key = _cache_key(google_place_id)
    api_key = settings.google_places_api_key

    # ── Redis 캐시 확인 ──
    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(content=cached, headers={"X-Cache": "HIT"})

    if not api_key:
        # API 키 없을 때: 목업 데이터로 UI 검증만
        mock = _mock_place(google_place_id)
        return JSONResponse(content=mock, headers={"X-Cache": "MOCK"})

    # ── Google Places API 호출 ──
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{PLACES_API}/details/json",
            params={
                "place_id": google_place_id,
                "fields": DETAIL_FIELDS,
                "language": "ko",
                "key": api_key,
            },
        )
    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    data = resp.json()
    result = data.get("result", {})
    status = data.get("status")

    if status != "OK":
        return JSONResponse(
            content={"error": status, "message": data.get("error_message", "")},
            status_code=400,
        )

    # ── photo_reference → Photos API URL 구성 ──
    photos = result.get("photos", [])
    image_url = None
    if photos and api_key:
        photo_ref = photos[0].get("photo_reference", "")
        if photo_ref:
            image_url = (
                f"{PLACES_API}/photo"
                f"?maxwidth=600&photo_reference={photo_ref}&key={api_key}"
            )

    # ── 영업 여부 ──
    cur_hours = result.get("current_opening_hours", {})
    oh = result.get("opening_hours", {})
    is_open = cur_hours.get("open_now") if cur_hours else oh.get("open_now")

    # ── 오늘 영업시간 ──
    weekday_text = cur_hours.get("weekday_text") or oh.get("weekday_text", [])
    today_hours = None
    if weekday_text:
        import datetime
        today_idx = datetime.date.today().weekday()  # 0=월, 6=일
        if today_idx < len(weekday_text):
            today_hours = weekday_text[today_idx]

    # ── 딥링크 ──
    name = result.get("name", "")
    from urllib.parse import quote
    name_enc = quote(name)

    payload = {
        "place_id": google_place_id,
        "name": name,
        "category": "restaurant",       # Nearby Search 없이 단독 호출 시 기본값
        "sub_category": None,
        "address": result.get("formatted_address"),
        "phone": result.get("formatted_phone_number"),
        "image_url": image_url,
        "rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total"),
        "price_level": result.get("price_level"),
        "is_open": is_open,
        "today_hours": today_hours,
        "all_weekday_hours": weekday_text,
        "website": result.get("website"),
        "booking_url": None,
        "naver_map_url": f"https://map.naver.com/v5/search/{name_enc}",
        "kakao_map_url": f"https://place.map.kakao.com/?q={name_enc}",
        # PoC 메타
        "_poc": {
            "photos_count": len(photos),
            "has_photo_reference": bool(photos),
            "has_current_opening_hours": bool(cur_hours),
            "api_elapsed_ms": elapsed_ms,
            "status": status,
        },
    }

    # ── Redis 저장 (TTL 24h) ──
    await cache_set(cache_key, payload, settings.google_places_ttl)

    return JSONResponse(content=payload, headers={"X-Cache": "MISS"})


@router.get("/nearby")
async def poc_nearby_search(
    lat: float = Query(37.4979, description="위도 (기본: 강남역)"),
    lng: float = Query(127.0276, description="경도 (기본: 강남역)"),
    keyword: str = Query("카페"),
    radius: int = Query(500),
):
    """Nearby Search PoC — place_id 목록 반환"""
    api_key = settings.google_places_api_key
    if not api_key:
        return {"status": "NO_API_KEY", "results": _mock_nearby()}

    cache_key = f"poc:nearby:{hashlib.md5(f'{lat}{lng}{keyword}{radius}'.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(content=cached, headers={"X-Cache": "HIT"})

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{PLACES_API}/nearbysearch/json",
            params={
                "location": f"{lat},{lng}",
                "radius": radius,
                "keyword": keyword,
                "language": "ko",
                "key": api_key,
            },
        )
    data = resp.json()
    results = [
        {
            "place_id": p.get("place_id"),
            "name": p.get("name"),
            "rating": p.get("rating"),
            "user_ratings_total": p.get("user_ratings_total"),
            "vicinity": p.get("vicinity"),
            "lat": p.get("geometry", {}).get("location", {}).get("lat"),
            "lng": p.get("geometry", {}).get("location", {}).get("lng"),
        }
        for p in data.get("results", [])[:10]
    ]
    payload = {"status": data.get("status"), "results": results}
    await cache_set(cache_key, payload, settings.google_places_ttl)
    return JSONResponse(content=payload, headers={"X-Cache": "MISS"})


# ── 목업 데이터 (API 키 없을 때 UI 검증용) ──
def _mock_place(place_id: str) -> dict:
    return {
        "place_id": place_id,
        "name": "스타벅스 강남대로점 (목업)",
        "category": "cafe",
        "sub_category": "카페",
        "address": "서울 강남구 강남대로 390",
        "phone": "02-1234-5678",
        "image_url": "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=600",
        "rating": 4.3,
        "user_ratings_total": 1284,
        "price_level": 2,
        "is_open": True,
        "today_hours": "월요일: 07:00~22:00",
        "all_weekday_hours": [
            "일요일: 08:00~21:00", "월요일: 07:00~22:00", "화요일: 07:00~22:00",
            "수요일: 07:00~22:00", "목요일: 07:00~22:00", "금요일: 07:00~22:00",
            "토요일: 08:00~21:00",
        ],
        "naver_map_url": "https://map.naver.com/v5/search/%EC%8A%A4%ED%83%80%EB%B2%85%EC%8A%A4%20%EA%B0%95%EB%82%A8%EB%8C%80%EB%A1%9C%EC%A0%90",
        "kakao_map_url": "https://place.map.kakao.com/?q=%EC%8A%A4%ED%83%80%EB%B2%85%EC%8A%A4+%EA%B0%95%EB%82%A8%EB%8C%80%EB%A1%9C%EC%A0%90",
        "_poc": {
            "photos_count": 0,
            "has_photo_reference": False,
            "has_current_opening_hours": True,
            "api_elapsed_ms": 0,
            "status": "MOCK",
        },
    }


def _mock_nearby() -> list[dict]:
    return [
        {"place_id": "ChIJmock1", "name": "스타벅스 강남점 (목업)", "rating": 4.3, "vicinity": "강남구"},
        {"place_id": "ChIJmock2", "name": "투썸플레이스 강남점 (목업)", "rating": 4.1, "vicinity": "강남구"},
    ]
