"""코스 추천용 장소 데이터 수집 — Google Places Text Search → PostgreSQL places 테이블"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import httpx
import psycopg2
from psycopg2.extras import execute_values

# ── 설정 ──────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from backend.src.config import get_settings

settings = get_settings()

DB_URL = settings.database_url
GOOGLE_KEY = settings.google_places_api_key
PLACES_API = "https://maps.googleapis.com/maps/api/place"

# ── 수집 대상 ─────────────────────────────────────────
# 서울 주요 권역 (검색 반경 중심)
AREAS = [
    "홍대",
    "연남동",
    "합정",
    "강남역",
    "신사동 가로수길",
    "성수동",
    "건대입구",
    "이태원",
    "한남동",
    "종로",
    "북촌",
    "익선동",
    "여의도",
    "영등포",
    "망원동",
    "상수",
    "을지로",
    "충무로",
    "잠실",
    "송파",
]

# 코스에 사용되는 카테고리 (course_plan_node의 _DURATION_MAP 기반)
CATEGORIES = [
    ("카페", "cafe", 60),
    ("레스토랑", "restaurant", 90),
    ("브런치 카페", "cafe", 90),
    ("전시 갤러리", "culture", 120),
    ("공원 산책", "park", 60),
    ("쇼핑", "shopping", 90),
    ("술집 바", "other", 90),
    ("디저트 카페", "cafe", 45),
    ("미술관 박물관", "culture", 120),
    ("베이커리", "cafe", 45),
]

# 자치구 매핑 (주소에서 추출)
DISTRICT_MAP = {
    "마포구": "mapo",
    "서대문구": "seodaemun",
    "용산구": "yongsan",
    "강남구": "gangnam",
    "서초구": "seocho",
    "송파구": "songpa",
    "성동구": "seongdong",
    "광진구": "gwangjin",
    "종로구": "jongno",
    "중구": "jung",
    "영등포구": "yeongdeungpo",
    "강동구": "gangdong",
    "동대문구": "dongdaemun",
    "성북구": "seongbuk",
    "강서구": "gangseo",
    "양천구": "yangcheon",
    "구로구": "guro",
    "금천구": "geumcheon",
    "관악구": "gwanak",
    "동작구": "dongjak",
    "노원구": "nowon",
    "도봉구": "dobong",
    "강북구": "gangbuk",
    "중랑구": "jungnang",
    "은평구": "eunpyeong",
}


def extract_district(address: str) -> str | None:
    """주소에서 자치구 코드 추출"""
    for gu_name, code in DISTRICT_MAP.items():
        if gu_name in address:
            return code
    return None


async def search_places(query: str, limit: int = 5) -> list[dict]:
    """Google Places Text Search API 호출"""
    params = {
        "query": query,
        "key": GOOGLE_KEY,
        "language": "ko",
        "region": "kr",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{PLACES_API}/textsearch/json", params=params)
        data = resp.json()

    if data.get("status") != "OK":
        print(f"  ⚠ API 응답: {data.get('status')} - {query}")
        return []

    results = []
    for r in data.get("results", [])[:limit]:
        photo_ref = None
        if r.get("photos"):
            photo_ref = r["photos"][0].get("photo_reference")

        results.append(
            {
                "google_place_id": r.get("place_id", ""),
                "name": r.get("name", ""),
                "address": r.get("formatted_address", ""),
                "lat": r.get("geometry", {}).get("location", {}).get("lat"),
                "lng": r.get("geometry", {}).get("location", {}).get("lng"),
                "rating": r.get("rating"),
                "user_ratings_total": r.get("user_ratings_total"),
                "price_level": r.get("price_level"),
                "is_open": r.get("opening_hours", {}).get("open_now"),
                "types": r.get("types", []),
                "photo_ref": photo_ref,
            }
        )
    return results


async def get_business_hours(google_place_id: str) -> dict | None:
    """Place Details → 영업시간 조회"""
    params = {
        "place_id": google_place_id,
        "fields": "opening_hours",
        "key": GOOGLE_KEY,
        "language": "ko",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{PLACES_API}/details/json", params=params)
            data = resp.json()
        periods = data.get("result", {}).get("opening_hours", {})
        weekday_text = periods.get("weekday_text", [])
        if weekday_text:
            days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            hours = {}
            for i, text in enumerate(weekday_text):
                if i < len(days):
                    # "월요일: 09:00~22:00" → "09:00~22:00"
                    parts = text.split(": ", 1)
                    hours[days[i]] = parts[1] if len(parts) > 1 else text
            return hours
    except Exception as e:
        print(f"  ⚠ Details API 오류: {e}")
    return None


def get_photo_url(photo_ref: str) -> str:
    return f"{PLACES_API}/photo?maxwidth=400&photo_reference={photo_ref}&key={GOOGLE_KEY}"


def insert_places(places: list[dict]):
    """PostgreSQL places 테이블에 UPSERT (배치 내 중복 제거)"""
    if not places:
        return

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # 배치 내 google_place_id 중복 제거 (마지막 것 유지)
    seen = {}
    for p in places:
        gid = p.get("google_place_id")
        if gid:
            seen[gid] = p
    places = list(seen.values())

    values = []
    for p in places:
        values.append(
            (
                str(uuid.uuid4()),
                p["name"],
                p["category"],
                p.get("sub_category"),
                p.get("address"),
                p.get("district"),
                p.get("lat"),
                p.get("lng"),
                None,  # phone
                p.get("google_place_id"),
                p.get("image_url"),
                json.dumps(p.get("business_hours")) if p.get("business_hours") else None,
                json.dumps(p.get("attributes", {})),
                None,  # booking_url
                p.get("estimated_stay_min", 60),
                json.dumps(p.get("raw_data", {})),
                "google_places",
            )
        )

    sql = """
        INSERT INTO places (
            place_id, name, category, sub_category, address, district,
            lat, lng, phone, google_place_id, image_url,
            business_hours, attributes, booking_url, estimated_stay_min,
            raw_data, source
        ) VALUES %s
        ON CONFLICT (google_place_id) DO UPDATE SET
            name = EXCLUDED.name,
            address = EXCLUDED.address,
            lat = EXCLUDED.lat,
            lng = EXCLUDED.lng,
            image_url = EXCLUDED.image_url,
            business_hours = EXCLUDED.business_hours,
            updated_at = NOW()
    """
    try:
        execute_values(cur, sql, values)
        conn.commit()
        print(f"  ✅ {len(values)}건 UPSERT 완료")
    except Exception as e:
        conn.rollback()
        print(f"  ❌ DB 오류: {e}")
    finally:
        cur.close()
        conn.close()


async def collect_area_category(
    area: str, cat_label: str, cat_code: str, stay_min: int, fetch_hours: bool = False
) -> list[dict]:
    """단일 권역+카테고리 조합 수집"""
    query = f"{cat_label} {area} 서울"
    raw_places = await search_places(query, limit=5)

    collected = []
    for rp in raw_places:
        address = rp.get("address", "")
        # 서울 외 장소 필터링
        if "서울" not in address and "Seoul" not in address:
            continue

        hours = None
        if fetch_hours and rp.get("google_place_id"):
            hours = await get_business_hours(rp["google_place_id"])
            await asyncio.sleep(0.1)  # rate limit

        collected.append(
            {
                "name": rp["name"],
                "category": cat_code,
                "sub_category": cat_label,
                "address": address,
                "district": extract_district(address),
                "lat": rp.get("lat"),
                "lng": rp.get("lng"),
                "google_place_id": rp.get("google_place_id"),
                "image_url": get_photo_url(rp["photo_ref"]) if rp.get("photo_ref") else None,
                "business_hours": hours,
                "estimated_stay_min": stay_min,
                "attributes": {
                    "rating": rp.get("rating"),
                    "user_ratings_total": rp.get("user_ratings_total"),
                    "price_level": rp.get("price_level"),
                    "google_types": rp.get("types", []),
                },
                "raw_data": rp,
            }
        )

    return collected


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="코스 추천용 장소 데이터 수집")
    parser.add_argument("--areas", nargs="*", help="수집할 권역 (기본: 전체)")
    parser.add_argument("--categories", nargs="*", help="수집할 카테고리 (기본: 전체)")
    parser.add_argument("--fetch-hours", action="store_true", help="영업시간 조회 (Place Details API 추가 호출)")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 결과만 출력")
    args = parser.parse_args()

    areas = args.areas or AREAS
    cats = CATEGORIES
    if args.categories:
        cats = [c for c in CATEGORIES if c[0] in args.categories]

    # google_place_id UNIQUE 제약 추가 (없으면)
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("""
            DO $$ BEGIN
                ALTER TABLE places ADD CONSTRAINT places_google_id_unique UNIQUE (google_place_id);
            EXCEPTION
                WHEN duplicate_table THEN NULL;
                WHEN duplicate_object THEN NULL;
            END $$;
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠ UNIQUE 제약 추가 실패 (무시): {e}")

    total = 0
    print(f"📍 수집 시작: {len(areas)}개 권역 × {len(cats)}개 카테고리")
    print(f"   영업시간 조회: {'ON' if args.fetch_hours else 'OFF'}")
    print()

    for area in areas:
        area_places = []
        for cat_label, cat_code, stay_min in cats:
            print(f"  🔍 {area} - {cat_label}...", end=" ")
            places = await collect_area_category(area, cat_label, cat_code, stay_min, args.fetch_hours)
            print(f"{len(places)}건")
            area_places.extend(places)
            await asyncio.sleep(0.2)  # rate limit between queries

        if args.dry_run:
            for p in area_places:
                print(f"    [{p['category']}] {p['name']} ({p.get('lat')}, {p.get('lng')})")
        else:
            insert_places(area_places)

        total += len(area_places)
        print(f"  → {area}: {len(area_places)}건 수집")
        print()

    print(f"🏁 전체 수집 완료: {total}건")

    # 통계 출력
    if not args.dry_run:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT category, COUNT(*) FROM places GROUP BY category ORDER BY COUNT(*) DESC")
        print("\n📊 카테고리별 현황:")
        for row in cur.fetchall():
            print(f"   {row[0]}: {row[1]}건")
        cur.execute("SELECT COUNT(*) FROM places")
        print(f"\n   총 {cur.fetchone()[0]}건")
        cur.close()
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
