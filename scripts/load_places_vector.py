"""
places → OpenSearch places_vector 임베딩 적재

PostgreSQL places 테이블의 데이터를 page_content 템플릿으로 변환 후
Gemini 임베딩하여 OpenSearch places_vector에 적재.
"카공하기 좋은 카페", "데이트 분위기 레스토랑" 같은 비정형 검색용.

Usage:
    python scripts/load_places_vector.py --dry-run --limit 5
    python scripts/load_places_vector.py --limit 1000
    python scripts/load_places_vector.py --category cafe
    python scripts/load_places_vector.py
"""

import argparse
import asyncio
import logging
import time

from dotenv import load_dotenv

load_dotenv("backend/.env")
load_dotenv(".env")

from embed_utils import embed_texts
from opensearchpy import OpenSearch, helpers

from backend.src.config import get_settings
from backend.src.db.postgres import fetch_all, get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


def get_os_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": settings.opensearch_host, "port": settings.opensearch_port}],
        http_auth=(settings.opensearch_user, settings.opensearch_password),
        use_ssl=False,
        verify_certs=False,
    )


def generate_page_content(place: dict) -> str:
    """places row → 자연어 설명문 (템플릿 기반, LLM 호출 없이 비용 $0)."""
    parts = []

    district = place.get("district") or ""
    sub_cat = place.get("sub_category") or ""
    category = place.get("category") or ""
    name = place.get("name") or ""

    parts.append(f"{district}에 위치한 {sub_cat} {category}. {name}.")

    # attributes / raw_data에서 속성 추출
    raw = place.get("raw_data") or {}
    if isinstance(raw, str):
        import json as _json

        try:
            raw = _json.loads(raw)
        except Exception:
            raw = {}
    attrs = place.get("attributes") or {}
    if isinstance(attrs, str):
        import json as _json

        try:
            attrs = _json.loads(attrs)
        except Exception:
            attrs = {}

    attr_texts = []
    if attrs.get("wifi") or raw.get("와이파이") == "가능":
        attr_texts.append("와이파이 가능")
    if attrs.get("parking") or raw.get("주차") in ("가능", "있음"):
        attr_texts.append("주차 가능")
    elif raw.get("주차") in ("불가", "없음"):
        attr_texts.append("주차 불가")
    if raw.get("놀이방") in ("있음", "Y"):
        attr_texts.append("놀이방 있음")

    if attr_texts:
        parts.append(". ".join(attr_texts) + ".")

    if place.get("address"):
        parts.append(str(place["address"]) + ".")

    # 가격 정보
    blog_price = raw.get("blog_price_data", {})
    if isinstance(blog_price, dict) and blog_price.get("avg_price"):
        parts.append(f"평균 가격대 약 {blog_price['avg_price']}원.")

    return " ".join(parts)


async def load_places(
    category: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    batch_size: int = 500,
):
    start = time.time()
    await get_pool()

    query = """
        SELECT place_id, name, category, sub_category, district,
               address, ST_Y(geom) as lat, ST_X(geom) as lng,
               raw_data, source
        FROM places
        WHERE geom IS NOT NULL
    """
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

    if not rows:
        logger.warning("적재할 장소 없음")
        return

    # page_content 생성
    page_contents = [generate_page_content(dict(r)) for r in rows]

    if dry_run:
        for i in range(min(5, len(rows))):
            logger.info(f"  [{i + 1}] {rows[i]['name']}: {page_contents[i][:120]}...")
        logger.info(f"--dry-run: {len(rows)}건 중 샘플 출력 완료")
        return

    os_client = get_os_client()
    total_indexed = 0
    total_errors = 0

    for i in range(0, len(rows), batch_size):
        batch_rows = rows[i : i + batch_size]
        batch_contents = page_contents[i : i + batch_size]

        # 임베딩
        embeddings = embed_texts(batch_contents)

        actions = []
        for j, row in enumerate(batch_rows):
            actions.append(
                {
                    "_index": settings.places_index,
                    "_id": str(row["place_id"]),
                    "_source": {
                        "place_id": str(row["place_id"]),
                        "name": row["name"],
                        "page_content": batch_contents[j],
                        "embedding": embeddings[j],
                        "category": row.get("category", ""),
                        "sub_category": row.get("sub_category", ""),
                        "district": row.get("district", ""),
                        "lat": row.get("lat"),
                        "lng": row.get("lng"),
                        "source": row.get("source", ""),
                    },
                }
            )

        # 제로 벡터 제거 (cosinesimil에서 거부됨)
        actions = [a for a in actions if any(v != 0.0 for v in a["_source"]["embedding"])]
        if not actions:
            continue
        success, errors = helpers.bulk(os_client, actions)
        total_indexed += success
        total_errors += len(errors)
        logger.info(f"  Batch {i // batch_size + 1}: {success} indexed, {len(errors)} errors")

    elapsed = time.time() - start
    logger.info(f"places_vector 적재 완료: {total_indexed}건, {total_errors} errors, {elapsed:.1f}초")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="places → OpenSearch places_vector 적재")
    parser.add_argument("--category", help="특정 카테고리만")
    parser.add_argument("--limit", type=int, help="처리 건수 제한")
    parser.add_argument("--dry-run", action="store_true", help="page_content 샘플만 출력")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(
        load_places(
            category=args.category,
            limit=args.limit,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    )
