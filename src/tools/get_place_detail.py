"""장소 상세 정보 도구 — PostgreSQL + Google Places 실시간 병합"""

from langchain_core.tools import tool

from backend.src.db.postgres import fetch_one
from backend.src.external.google_places import get_photo_url, get_place_detail


@tool
async def get_place_detail(place_id: str) -> dict:
    """
    장소 상세 정보 조회.
    DB 기본 정보 + Google Places 실시간 영업정보/이미지를 병합하여 반환.

    Args:
        place_id: places 테이블의 UUID
    """
    db_row = await fetch_one(
        """
        SELECT place_id::text, name, category, sub_category, address, district,
               ST_X(geom) AS lng, ST_Y(geom) AS lat,
               phone, google_place_id, image_url, business_hours,
               attributes, booking_url, raw_data
        FROM places WHERE place_id = $1
        """,
        place_id,
    )

    if not db_row:
        return {}

    result = dict(db_row)

    # Google Places 실시간 정보 보강
    google_id = result.get("google_place_id")
    if google_id:
        try:
            detail = await get_place_detail(google_id)
            result["rating"] = detail.get("rating")
            result["user_ratings_total"] = detail.get("user_ratings_total")
            result["price_level"] = detail.get("price_level")
            result["is_open"] = detail.get("current_opening_hours", {}).get("open_now")
            # 대표 이미지 URL (photo_reference 기반)
            photos = detail.get("photos", [])
            if photos:
                photo_ref = photos[0].get("photo_reference", "")
                if photo_ref:
                    result["image_url"] = get_photo_url(photo_ref)
        except Exception:
            pass

    # 딥링크 URL 생성
    if result.get("lat") and result.get("lng"):
        name_enc = result.get("name", "").replace(" ", "+")
        result["naver_map_url"] = f"https://map.naver.com/v5/search/{name_enc}"
        result["kakao_map_url"] = f"https://map.kakao.com/?q={name_enc}"

    return result
