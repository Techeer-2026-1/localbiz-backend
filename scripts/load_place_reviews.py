"""
place_analysis → OpenSearch place_reviews 임베딩 적재

place_analysis 테이블의 summary + keywords를 임베딩하여
place_reviews 인덱스에 적재한다. "분위기 좋은 곳" 같은 비정형 검색과
장소 A vs B 레이더차트 비교에 사용.

Usage:
    python scripts/load_place_reviews.py --dry-run     # 샘플 5개만 출력
    python scripts/load_place_reviews.py               # 전체 적재
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


async def load_reviews(dry_run: bool = False, batch_size: int = 200):
    start = time.time()
    await get_pool()

    rows = await fetch_all("""
        SELECT pa.analysis_id, pa.place_id, pa.place_name,
               pa.summary, pa.keywords,
               pa.score_taste, pa.score_service, pa.score_atmosphere,
               pa.score_value, pa.score_cleanliness, pa.score_accessibility,
               pa.analyzed_at,
               p.category, p.district
        FROM place_analysis pa
        LEFT JOIN places p ON pa.place_id = p.place_id
        WHERE pa.ttl_expires_at > NOW()
    """)

    logger.info(f"place_analysis rows: {len(rows)}")

    if not rows:
        logger.warning("적재할 데이터 없음 — batch_review_analysis.py를 먼저 실행하세요")
        return

    # summary_text 생성
    summary_texts = []
    for row in rows:
        kw = ", ".join(row["keywords"]) if row["keywords"] else ""
        summary_texts.append(f"{row['summary'] or ''} 키워드: {kw}")

    if dry_run:
        for i, (row, text) in enumerate(zip(rows[:5], summary_texts[:5], strict=False)):
            logger.info(f"[{i + 1}] {row['place_name']}: {text[:100]}...")
        logger.info(f"--dry-run: {len(rows)}건 중 샘플 5개 출력 완료")
        return

    os_client = get_os_client()
    total_indexed = 0
    total_errors = 0

    for i in range(0, len(rows), batch_size):
        batch_rows = rows[i : i + batch_size]
        batch_texts = summary_texts[i : i + batch_size]

        embeddings = embed_texts(batch_texts)

        actions = []
        for j, row in enumerate(batch_rows):
            scores = [
                row[f"score_{k}"]
                for k in ["taste", "service", "atmosphere", "value", "cleanliness", "accessibility"]
                if row.get(f"score_{k}") is not None
            ]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0

            actions.append(
                {
                    "_index": settings.reviews_index,
                    "_id": str(row["analysis_id"]),
                    "_source": {
                        "review_id": str(row["analysis_id"]),
                        "place_id": str(row["place_id"]),
                        "place_name": row["place_name"],
                        "summary_text": batch_texts[j],
                        "embedding": embeddings[j],
                        "keywords": row["keywords"] or [],
                        "stars": avg_score,
                        "source": "place_analysis",
                        "category": row.get("category", ""),
                        "district": row.get("district", ""),
                        "analyzed_at": row["analyzed_at"].isoformat() if row["analyzed_at"] else None,
                    },
                }
            )

        success, errors = helpers.bulk(os_client, actions)
        total_indexed += success
        total_errors += len(errors)
        logger.info(f"  Batch {i // batch_size + 1}: {success} indexed, {len(errors)} errors")

    elapsed = time.time() - start
    logger.info(f"place_reviews 적재 완료: {total_indexed}건, {total_errors} errors, {elapsed:.1f}초")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="place_analysis → OpenSearch place_reviews 적재")
    parser.add_argument("--dry-run", action="store_true", help="임베딩/적재 없이 샘플만 출력")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(load_reviews(dry_run=args.dry_run, batch_size=args.batch_size))
