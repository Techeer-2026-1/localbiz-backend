"""
events → OpenSearch events_vector 임베딩 적재

PostgreSQL events 테이블의 title + summary를 임베딩하여
OpenSearch events_vector에 적재. "아이와 갈 만한 체험", "무료 전시" 같은 비정형 검색용.

Usage:
    python scripts/load_events_vector.py --dry-run
    python scripts/load_events_vector.py
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
        use_ssl=settings.opensearch_host != "localhost",
        verify_certs=False,
    )


async def load_events(dry_run: bool = False, batch_size: int = 500):
    start = time.time()
    await get_pool()

    rows = await fetch_all("""
        SELECT event_id, title, category, place_name, address,
               district,
               ST_Y(geom) as lat, ST_X(geom) as lng,
               date_start, date_end, summary, source
        FROM events
        WHERE date_end >= CURRENT_DATE OR date_end IS NULL
    """)

    logger.info(f"활성 행사: {len(rows)}건")

    if not rows:
        logger.warning("적재할 행사 없음")
        return

    # description 생성
    descriptions = []
    for row in rows:
        if row.get("summary"):
            desc = f"{row['title']}. {row['summary']}"
        else:
            desc = f"{row['title']}. {row.get('place_name', '')} {row.get('category', '')}"
        descriptions.append(desc)

    if dry_run:
        for i in range(min(5, len(rows))):
            logger.info(f"  [{i + 1}] {rows[i]['title']}: {descriptions[i][:120]}...")
        logger.info(f"--dry-run: {len(rows)}건 중 샘플 출력 완료")
        return

    os_client = get_os_client()
    total_indexed = 0
    total_errors = 0

    for i in range(0, len(rows), batch_size):
        batch_rows = rows[i : i + batch_size]
        batch_descs = descriptions[i : i + batch_size]

        embeddings = embed_texts(batch_descs)

        actions = []
        for j, row in enumerate(batch_rows):
            actions.append(
                {
                    "_index": settings.events_index,
                    "_id": str(row["event_id"]),
                    "_source": {
                        "event_id": str(row["event_id"]),
                        "title": row["title"],
                        "description": batch_descs[j],
                        "embedding": embeddings[j],
                        "category": row.get("category", ""),
                        "district": row.get("district", ""),
                        "date_start": row["date_start"].isoformat() if row.get("date_start") else None,
                        "date_end": row["date_end"].isoformat() if row.get("date_end") else None,
                        "source": row.get("source", ""),
                    },
                }
            )

        success, errors = helpers.bulk(os_client, actions)
        total_indexed += success
        total_errors += len(errors)
        logger.info(f"  Batch {i // batch_size + 1}: {success} indexed, {len(errors)} errors")

    elapsed = time.time() - start
    logger.info(f"events_vector 적재 완료: {total_indexed}건, {total_errors} errors, {elapsed:.1f}초")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="events → OpenSearch events_vector 적재")
    parser.add_argument("--dry-run", action="store_true", help="description 샘플만 출력")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(load_events(dry_run=args.dry_run, batch_size=args.batch_size))
