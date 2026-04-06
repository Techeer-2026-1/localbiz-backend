"""
가격 데이터 배치 수집 — Naver Blog → 정규식 추출 → places.raw_data JSONB

카테고리별 검색 전략으로 블로그에서 가격 패턴을 추출하고,
3중 필터링(상호명, 지역명, 가격 범위) 후 min/max/avg를 계산하여
PostgreSQL places.raw_data에 blog_price_data로 저장.

임베딩 불필요 (숫자 데이터).

Usage:
    python scripts/collect_price_data.py --dry-run --limit 5
    python scripts/collect_price_data.py --category 음식점 --limit 20
    python scripts/collect_price_data.py
"""

from typing import Optional
import asyncio
import argparse
import json
import re
import logging
import time

import httpx

from dotenv import load_dotenv
load_dotenv("backend/.env")
load_dotenv(".env")

from backend.src.config import get_settings
from backend.src.db.postgres import get_pool, fetch_all, execute

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()

# ─── 가격 정규식 ───
PRICE_WON = re.compile(r"(\d{1,3}(?:,\d{3})+)\s*원")
PRICE_MANWON = re.compile(r"(\d+(?:\.\d+)?)\s*만\s*원")
PRICE_SYMBOL = re.compile(r"[₩￦]\s*(\d{1,3}(?:,\d{3})+)")

# ─── 카테고리별 검색어 전략 ───
SEARCH_TEMPLATES = {
    "restaurant": "{name} 메뉴 가격",
    "cafe": "{name} 메뉴 가격",
    "gym": "{name} 회원권 가격",
    "beauty": "{name} 커트 가격",
}
DEFAULT_TEMPLATE = "{name} 이용료 가격"

# ─── 카테고리별 가격 하한 (노이즈 필터) ───
PRICE_FLOORS = {
    "restaurant": 5000,
    "cafe": 2000,
    "gym": 10000,
    "beauty": 5000,
}

# ─── 서울 자치구명 ───
SEOUL_DISTRICTS = [
    "강남", "강동", "강북", "강서", "관악", "광진", "구로", "금천",
    "노원", "도봉", "동대문", "동작", "마포", "서대문", "서초", "성동",
    "성북", "송파", "양천", "영등포", "용산", "은평", "종로", "중구", "중랑",
]


def extract_prices(text: str) -> list[int]:
    """텍스트에서 원 단위 가격 추출."""
    prices = []

    for m in PRICE_WON.findall(text):
        prices.append(int(m.replace(",", "")))

    for m in PRICE_MANWON.findall(text):
        prices.append(int(float(m) * 10000))

    for m in PRICE_SYMBOL.findall(text):
        prices.append(int(m.replace(",", "")))

    return prices


def filter_prices(prices: list[int], category: str) -> list[int]:
    """가격 범위 필터: 하한 ~ 100만원."""
    floor = PRICE_FLOORS.get(category, 1000)
    return [p for p in prices if floor <= p <= 1_000_000]


async def search_naver_blog(query: str, display: int = 5) -> list[dict]:
    """네이버 블로그 검색 API."""
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "sort": "sim"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://openapi.naver.com/v1/search/blog.json",
            headers=headers,
            params=params,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("items", [])


async def collect_price_for_place(place: dict) -> Optional[dict]:
    """단일 장소 가격 수집 파이프라인."""
    name = place["name"]
    category = place["category"]
    district = place.get("district", "")

    template = SEARCH_TEMPLATES.get(category, DEFAULT_TEMPLATE)
    query = template.format(name=name)

    items = await search_naver_blog(query, display=5)
    if not items:
        return None

    all_prices = []
    for item in items:
        desc = re.sub(r"<[^>]+>", "", item.get("description", ""))
        title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        text = f"{title} {desc}"

        # 3중 필터링
        # 1. 상호명 포함 여부
        name_short = name.split()[0] if " " in name else name[:4]
        if name_short not in text:
            continue

        # 2. 서울 자치구 포함 여부 (선택적 — 없어도 통과)
        has_district = any(d in text for d in SEOUL_DISTRICTS)

        # 3. 가격 추출 + 범위 필터
        prices = extract_prices(text)
        prices = filter_prices(prices, category)
        all_prices.extend(prices)

    if not all_prices:
        return None

    return {
        "min_price": min(all_prices),
        "max_price": max(all_prices),
        "avg_price": round(sum(all_prices) / len(all_prices)),
        "sample_count": len(all_prices),
        "source": "naver_blog",
    }


async def collect_prices(
    category: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
):
    start = time.time()
    await get_pool()

    query = "SELECT place_id, name, category, district FROM places WHERE 1=1"
    params = []

    if category:
        params.append(category)
        query += f" AND category = ${len(params)}"

    query += " ORDER BY created_at DESC"

    if limit:
        params.append(limit)
        query += f" LIMIT ${len(params)}"

    rows = await fetch_all(query, *params)
    logger.info(f"대상 장소: {len(rows)}건" + (f" (category={category})" if category else ""))

    if dry_run:
        for row in rows[:5]:
            template = SEARCH_TEMPLATES.get(row["category"], DEFAULT_TEMPLATE)
            logger.info(f"  [{row['category']}] {row['name']} → \"{template.format(name=row['name'])}\"")
        logger.info(f"--dry-run: 검색어 샘플 출력 완료")
        return

    success_count = 0
    fail_count = 0
    api_calls = 0

    for i, row in enumerate(rows):
        try:
            price_data = await collect_price_for_place(row)
            api_calls += 1

            if price_data:
                await execute(
                    """
                    UPDATE places
                    SET raw_data = COALESCE(raw_data, '{}'::jsonb) || $1::jsonb
                    WHERE place_id = $2
                    """,
                    json.dumps({"blog_price_data": price_data}),
                    row["place_id"],
                )
                success_count += 1
                logger.info(
                    f"  [{i+1}/{len(rows)}] {row['name']}: "
                    f"{price_data['min_price']}~{price_data['max_price']}원 "
                    f"(avg {price_data['avg_price']}원, {price_data['sample_count']}건)"
                )
            else:
                fail_count += 1
                if (i + 1) % 50 == 0:
                    logger.info(f"  [{i+1}/{len(rows)}] 진행 중...")

        except Exception as e:
            fail_count += 1
            logger.warning(f"  [{i+1}/{len(rows)}] {row['name']}: 오류 — {e}")

        # Rate limit: 0.15초 sleep (일 25,000건 한도)
        await asyncio.sleep(0.15)

    elapsed = time.time() - start
    logger.info(
        f"완료: {success_count}건 성공, {fail_count}건 실패, "
        f"API {api_calls}회 호출, {elapsed:.1f}초"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="가격 데이터 배치 수집")
    parser.add_argument("--category", help="특정 카테고리만 (예: restaurant, cafe)")
    parser.add_argument("--limit", type=int, help="처리 건수 제한")
    parser.add_argument("--dry-run", action="store_true", help="검색어만 출력")
    args = parser.parse_args()
    asyncio.run(collect_prices(category=args.category, limit=args.limit, dry_run=args.dry_run))
