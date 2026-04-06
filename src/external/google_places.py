"""Google Places API 클라이언트"""

import httpx

from backend.src.config import get_settings

settings = get_settings()

PLACES_API_BASE = "https://maps.googleapis.com/maps/api/place"
PHOTOS_API_BASE = "https://maps.googleapis.com/maps/api/place/photo"


async def text_search(query: str, location: str = "서울", limit: int = 5) -> list[dict]:
    """Google Places Text Search — 키워드로 장소 검색"""
    params = {
        "query": f"{query} {location}" if location and location not in query else query,
        "key": settings.google_places_api_key,
        "language": "ko",
        "region": "kr",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{PLACES_API_BASE}/textsearch/json", params=params)
        data = response.json()

    results = []
    for r in data.get("results", [])[:limit]:
        photo_ref = None
        if r.get("photos"):
            photo_ref = r["photos"][0].get("photo_reference")

        results.append(
            {
                "place_id": r.get("place_id", ""),
                "name": r.get("name", ""),
                "address": r.get("formatted_address", ""),
                "lat": r.get("geometry", {}).get("location", {}).get("lat", 0),
                "lng": r.get("geometry", {}).get("location", {}).get("lng", 0),
                "rating": r.get("rating"),
                "user_ratings_total": r.get("user_ratings_total"),
                "price_level": r.get("price_level"),
                "is_open": r.get("opening_hours", {}).get("open_now"),
                "types": r.get("types", []),
                "image_url": get_photo_url(photo_ref) if photo_ref else None,
                "google_maps_url": f"https://www.google.com/maps/place/?q=place_id:{r.get('place_id', '')}",
                "_source": "google_places",
            }
        )

    return results


async def get_place_detail(google_place_id: str) -> dict:
    """장소 상세 정보 — Place Details API (평점, 영업여부, 이미지)"""
    params = {
        "place_id": google_place_id,
        "fields": "name,rating,user_ratings_total,opening_hours,formatted_phone_number,"
        "price_level,photos,current_opening_hours,editorial_summary",
        "key": settings.google_places_api_key,
        "language": "ko",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{PLACES_API_BASE}/details/json", params=params)
        data = response.json()

    return data.get("result", {})


async def get_place_reviews(google_place_id: str) -> list[dict]:
    """Google Places 리뷰 — 최대 5개, 한국어 우선"""
    params = {
        "place_id": google_place_id,
        "fields": "reviews",
        "key": settings.google_places_api_key,
        "language": "ko",
        "reviews_sort": "most_relevant",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{PLACES_API_BASE}/details/json", params=params)
            data = response.json()
        reviews = data.get("result", {}).get("reviews", [])
        return [
            {
                "text": r.get("text", ""),
                "rating": r.get("rating"),
                "author": r.get("author_name", ""),
                "source": "google",
            }
            for r in reviews
            if r.get("text")
        ]
    except Exception:
        return []


def get_photo_url(photo_reference: str, max_width: int = 400) -> str:
    """photo_reference → Places Photos API URL 구성"""
    return (
        f"{PHOTOS_API_BASE}?maxwidth={max_width}&photo_reference={photo_reference}&key={settings.google_places_api_key}"
    )


def _category_to_type(category: str) -> str:
    """내부 카테고리 → Google Places type 변환"""
    mapping = {
        "restaurant": "restaurant",
        "cafe": "cafe",
        "gym": "gym",
        "beauty": "beauty_salon",
        "park": "park",
        "library": "library",
        "pharmacy": "pharmacy",
        "culture": "museum",
        "shopping": "shopping_mall",
        "medical": "hospital",
        "education": "school",
        "sports": "stadium",
        "tourism": "tourist_attraction",
        "convenience": "convenience_store",
    }
    return mapping.get(category, "establishment")
