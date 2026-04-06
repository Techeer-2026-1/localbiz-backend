"""
이미지 캡셔닝 배치 → OpenSearch places_vector 부분 업데이트

Google Places Photos에서 장소 사진을 가져와 Claude Haiku가 3문장 캡션을 생성.
캡션을 임베딩하여 OpenSearch places_vector의 image_caption + image_embedding에 적재.
사용자가 사진을 올리면 캡션끼리 유사도 비교로 비슷한 장소를 찾을 수 있음.

비용: Claude Haiku ~$0.003/장 (1,000장 ≈ $3)

Usage:
    python scripts/load_image_captions.py --dry-run --limit 3
    python scripts/load_image_captions.py --limit 50
    python scripts/load_image_captions.py
"""

import argparse
import asyncio
import base64
import logging
import time

import httpx
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


async def get_photo_reference(google_place_id: str) -> str | None:
    """Google Places Details에서 photo_reference 1개 가져오기."""
    params = {
        "place_id": google_place_id,
        "fields": "photos",
        "key": settings.google_places_api_key,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params=params,
        )
        if resp.status_code != 200:
            return None
        photos = resp.json().get("result", {}).get("photos", [])
        return photos[0]["photo_reference"] if photos else None


async def download_photo(photo_reference: str, max_width: int = 400) -> tuple[bytes, str] | None:
    """Google Places Photo 다운로드."""
    url = (
        f"https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth={max_width}&photo_reference={photo_reference}"
        f"&key={settings.google_places_api_key}"
    )
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        media_type = resp.headers.get("content-type", "image/jpeg")
        return resp.content, media_type


async def caption_image(image_bytes: bytes, media_type: str) -> str:
    """Claude Haiku로 이미지 캡셔닝. 3문장 객관적 묘사."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": img_b64},
                    },
                    {
                        "type": "text",
                        "text": "이 장소 사진의 분위기, 인테리어 특징, 공간 특성을 한국어 3문장으로 설명해주세요. 객관적 묘사만.",
                    },
                ],
            }
        ],
    )
    return message.content[0].text


async def load_captions(limit: int = 1000, dry_run: bool = False, batch_size: int = 50):
    start = time.time()
    await get_pool()

    rows = await fetch_all(
        """
        SELECT place_id, name, google_place_id, category
        FROM places
        WHERE google_place_id IS NOT NULL
          AND category IN ('cafe', 'tourism', 'restaurant')
        ORDER BY
            CASE category
                WHEN 'tourism' THEN 1
                WHEN 'cafe' THEN 2
                WHEN 'restaurant' THEN 3
            END
        LIMIT $1
    """,
        limit,
    )

    logger.info(f"캡셔닝 대상: {len(rows)}건")

    captions = []
    place_ids = []
    skip_count = 0

    for i, row in enumerate(rows):
        try:
            # 1. photo_reference 가져오기
            photo_ref = await get_photo_reference(row["google_place_id"])
            if not photo_ref:
                skip_count += 1
                continue

            # 2. 이미지 다운로드
            result = await download_photo(photo_ref)
            if not result:
                skip_count += 1
                continue
            image_bytes, media_type = result

            # 3. 캡셔닝
            caption = await caption_image(image_bytes, media_type)

            if dry_run:
                logger.info(f"  [{i + 1}] {row['name']}: {caption}")
                if len(captions) + 1 >= 3:
                    logger.info("--dry-run: 샘플 3건 완료")
                    return
            else:
                captions.append(caption)
                place_ids.append(str(row["place_id"]))
                logger.info(f"  [{i + 1}/{len(rows)}] {row['name']}: {caption[:60]}...")

        except Exception as e:
            skip_count += 1
            logger.warning(f"  [{i + 1}] {row['name']}: 오류 — {e}")

        # Rate limit
        await asyncio.sleep(0.3)

    if dry_run or not captions:
        return

    # 4. 배치 임베딩
    logger.info(f"임베딩 생성 중: {len(captions)}건...")
    caption_embeddings = embed_texts(captions)

    # 5. OpenSearch 부분 업데이트
    os_client = get_os_client()
    total_updated = 0

    for i in range(0, len(captions), batch_size):
        batch_captions = captions[i : i + batch_size]
        batch_embeddings = caption_embeddings[i : i + batch_size]
        batch_ids = place_ids[i : i + batch_size]

        actions = []
        for j in range(len(batch_captions)):
            actions.append(
                {
                    "_op_type": "update",
                    "_index": settings.places_index,
                    "_id": batch_ids[j],
                    "doc": {
                        "image_caption": batch_captions[j],
                        "image_embedding": batch_embeddings[j],
                    },
                }
            )

        success, errors = helpers.bulk(os_client, actions)
        total_updated += success
        logger.info(f"  Batch {i // batch_size + 1}: {success} updated")

    elapsed = time.time() - start
    haiku_cost = len(captions) * 0.003
    logger.info(
        f"이미지 캡션 적재 완료: {total_updated}건 업데이트, "
        f"{skip_count}건 스킵, 추정 비용 ~${haiku_cost:.2f}, {elapsed:.1f}초"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="이미지 캡셔닝 배치 적재")
    parser.add_argument("--limit", type=int, default=1000, help="처리 건수 (기본 1000)")
    parser.add_argument("--dry-run", action="store_true", help="3건만 캡셔닝 후 출력")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    asyncio.run(load_captions(limit=args.limit, dry_run=args.dry_run, batch_size=args.batch_size))
