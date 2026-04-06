"""예약 딥링크 생성 도구"""
from urllib.parse import quote
from langchain_core.tools import tool
from backend.src.db.postgres import fetch_one


@tool
async def create_booking(place_id: str) -> dict:
    """
    예약 딥링크 반환.
    raw_data JSONB에 저장된 예약 URL 우선 사용, 없으면 네이버/카카오 딥링크 생성.

    Args:
        place_id: 장소 UUID
    """
    row = await fetch_one(
        "SELECT name, booking_url, raw_data FROM places WHERE place_id = $1",
        place_id,
    )
    if not row:
        return {"status": "not_found"}

    name = row["name"]
    booking_url = row.get("booking_url")
    raw_data = row.get("raw_data") or {}

    # 1순위: DB에 저장된 예약 URL
    if booking_url:
        return {"place_id": place_id, "name": name, "booking_url": booking_url, "source": "direct"}

    # 2순위: raw_data JSONB 내 예약 URL
    for key in ("예약링크", "booking_link", "reservation_url"):
        if url := raw_data.get(key):
            return {"place_id": place_id, "name": name, "booking_url": url, "source": "raw_data"}

    # 3순위: 네이버 예약 딥링크
    name_enc = quote(name)
    naver_url = f"https://booking.naver.com/booking/13/bizes?query={name_enc}"
    kakao_url = f"https://place.map.kakao.com/?q={name_enc}"

    return {
        "place_id": place_id,
        "name": name,
        "booking_url": naver_url,
        "kakao_url": kakao_url,
        "source": "deeplink",
    }
