"""행사/축제 검색 도구 — events 테이블 날짜 필터 + 자연어 날짜 파싱"""

from datetime import date

from langchain_core.tools import tool

from backend.src.db.postgres import fetch_all
from backend.src.utils.date_parser import parse_date_range


@tool
async def search_events(
    query: str = "",
    date_text: str = "",
    category: str = "",
    district: str = "",
    sort: str = "date",
    limit: int = 10,
) -> list[dict]:
    """
    행사/축제 검색 도구.

    Args:
        query: 검색어
        date_text: 자연어 날짜 ("이번 주말", "3월 21일") — 비어 있으면 오늘 이후
        category: 행사 카테고리 (축제, 전시, 공연, 교육체험)
        district: 자치구
        sort: 정렬 기준 ("date" | "popular" | "distance")
        limit: 결과 수
    """
    if date_text:
        date_from, date_to = parse_date_range(date_text)
    else:
        date_from = date.today()
        date_to = date(9999, 12, 31)  # 종료일 없음 → 미래 전체

    conditions = ["date_end >= $1", "date_start <= $2"]
    params: list = [date_from, date_to]
    idx = 3

    if category:
        conditions.append(f"category = ${idx}")
        params.append(category)
        idx += 1

    if query:
        conditions.append(f"title ILIKE ${idx}")
        params.append(f"%{query}%")
        idx += 1

    order_map = {
        "date": "date_start ASC",
        "popular": "COALESCE(kopis_sales_rate, 0) DESC",
        "distance": "date_start ASC",  # 거리 정렬은 좌표 필요 — 여기선 날짜로 fallback
    }
    order_clause = order_map.get(sort, "date_start ASC")

    sql = f"""
        SELECT event_id::text, title, category, place_name, address,
               ST_X(geom) AS lng, ST_Y(geom) AS lat,
               date_start::text, date_end::text,
               price, poster_url, detail_url, source, kopis_sales_rate
        FROM events
        WHERE {" AND ".join(conditions)}
        ORDER BY {order_clause}
        LIMIT {limit}
    """

    return await fetch_all(sql, *params)
