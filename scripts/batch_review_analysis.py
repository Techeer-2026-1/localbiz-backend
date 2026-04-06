"""
리뷰 비교 PoC — 배치 분석 스크립트

Google Places 리뷰 + 네이버 블로그 후기를 수집하고,
LLM(Gemini)으로 6개 지표(맛, 서비스, 분위기, 가성비, 청결도, 접근성)를 정량화하여
place_analysis 테이블에 적재한다.

Usage:
    # 특정 장소 분석
    python scripts/batch_review_analysis.py --place-id ChIJ... --name "스타벅스 강남점"

    # places 테이블 전체 배치 분석
    python scripts/batch_review_analysis.py --batch --limit 50
"""

from __future__ import annotations

import asyncio
import argparse
import json
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────── 설정 ───────────────────────

from dotenv import load_dotenv
load_dotenv("backend/.env")
load_dotenv(".env")

from backend.src.config import get_settings
from backend.src.db.postgres import get_pool, fetch_all, fetch_one, execute

settings = get_settings()

# Gemini (비용 효율적인 배치 처리용)
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# ─────────────────────── 1단계: 데이터 수집 ───────────────────────

AD_KEYWORDS = re.compile(
    r"(소정의\s*원고료|원고료를\s*받|광고|협찬|제공[을를]?\s*받|체험단|무료\s*제공|"
    r"업체로부터|내돈내산\s*아닌|리뷰어|서포터즈|파트너)",
    re.IGNORECASE,
)

SPAM_PATTERN = re.compile(r"^[\s\W]{0,5}$|^(.)\1{5,}$")


async def collect_google_reviews(google_place_id: str) -> list[dict]:
    """Google Places 리뷰 수집 (최대 5개)"""
    params = {
        "place_id": google_place_id,
        "fields": "reviews,rating,user_ratings_total",
        "key": settings.google_places_api_key,
        "language": "ko",
        "reviews_sort": "most_relevant",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params=params,
            )
            data = resp.json().get("result", {})

        reviews = []
        for r in data.get("reviews", []):
            text = r.get("text", "").strip()
            if text:
                reviews.append({
                    "text": text,
                    "rating": r.get("rating"),
                    "source": "google",
                })

        meta = {
            "avg_rating": data.get("rating"),
            "user_ratings_total": data.get("user_ratings_total"),
        }
        return reviews, meta
    except Exception as e:
        logger.warning(f"Google 리뷰 수집 실패: {e}")
        return [], {}


async def collect_naver_reviews(place_name: str, display: int = 10) -> list[dict]:
    """네이버 블로그 후기 수집"""
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {
        "query": f"{place_name} 후기",
        "display": display,
        "sort": "sim",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://openapi.naver.com/v1/search/blog.json",
                headers=headers,
                params=params,
            )
            items = resp.json().get("items", [])

        reviews = []
        for item in items:
            desc = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()
            if desc:
                reviews.append({
                    "text": desc,
                    "source": "naver",
                    "postdate": item.get("postdate"),
                })
        return reviews
    except Exception as e:
        logger.warning(f"네이버 리뷰 수집 실패: {e}")
        return []


# ─────────────────────── 2단계: 전처리 ───────────────────────

def preprocess_reviews(reviews: list[dict]) -> list[dict]:
    """광고/스팸 필터링 + 중복 제거"""
    seen_texts = set()
    cleaned = []

    for r in reviews:
        text = r["text"].strip()

        # 스팸 필터
        if SPAM_PATTERN.match(text):
            continue

        # 너무 짧은 리뷰 (10자 미만)
        if len(text) < 10:
            continue

        # 광고/협찬 필터
        if AD_KEYWORDS.search(text):
            logger.debug(f"광고 필터링: {text[:30]}...")
            continue

        # 중복 제거 (앞 50자 기준)
        key = text[:50]
        if key in seen_texts:
            continue
        seen_texts.add(key)

        cleaned.append(r)

    return cleaned


# ─────────────────────── 3단계: LLM 분석 ───────────────────────

ANALYSIS_PROMPT = """당신은 장소 리뷰 분석 전문가입니다. 아래 리뷰들을 읽고 정량화된 분석 결과를 JSON으로 반환하세요.

## 장소 정보
- 장소명: {place_name}
- 카테고리: {category}

## 리뷰 데이터 ({total_reviews}건)
{reviews_text}

## 분석 요구사항
각 지표를 1.0~5.0 범위로 소수점 1자리까지 채점하세요. 리뷰에서 해당 지표에 대한 언급이 없으면 null로 표시하세요.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
```json
{{
  "score_taste": 4.2,
  "score_service": 3.8,
  "score_atmosphere": 4.5,
  "score_value": 3.5,
  "score_cleanliness": 4.0,
  "score_accessibility": 3.0,
  "summary": "3줄 이내 핵심 요약",
  "keywords": ["키워드1", "키워드2", "키워드3"]
}}
```"""


async def analyze_with_llm(
    place_name: str,
    category: str,
    reviews: list[dict],
) -> dict | None:
    """Gemini 2.5 Flash로 리뷰 분석 → JSON 구조화"""
    if not reviews:
        return None

    # 리뷰 텍스트 병합
    reviews_text = "\n".join(
        f"[{r['source']}] (★{r.get('rating', '?')}) {r['text'][:300]}"
        for r in reviews
    )

    prompt = ANALYSIS_PROMPT.format(
        place_name=place_name,
        category=category or "기타",
        total_reviews=len(reviews),
        reviews_text=reviews_text,
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    try:
        gemini_key = settings.gemini_llm_api_key
        if not gemini_key:
            logger.warning("GEMINI_LLM_API_KEY 미설정 — Claude fallback")
            return await analyze_with_claude(place_name, category, reviews)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{GEMINI_API_URL}?key={gemini_key}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code != 200:
                logger.warning(f"Gemini API 오류 ({resp.status_code}): {resp.text[:200]}")
                return await analyze_with_claude(place_name, category, reviews)

            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

    except Exception as e:
        logger.warning(f"Gemini 분석 실패, Claude fallback 시도: {e}")
        return await analyze_with_claude(place_name, category, reviews)


async def analyze_with_claude(
    place_name: str,
    category: str,
    reviews: list[dict],
) -> dict | None:
    """Claude Sonnet fallback"""
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY 미설정 — 분석 불가")
        return None

    reviews_text = "\n".join(
        f"[{r['source']}] (★{r.get('rating', '?')}) {r['text'][:300]}"
        for r in reviews
    )

    prompt = ANALYSIS_PROMPT.format(
        place_name=place_name,
        category=category or "기타",
        total_reviews=len(reviews),
        reviews_text=reviews_text,
    )

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text

        # JSON 블록 추출
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        return json.loads(text)

    except Exception as e:
        logger.error(f"Claude 분석 실패: {e}")
        return None


# ─────────────────────── 4단계: DB 적재 ───────────────────────

async def upsert_analysis(
    place_id: str,
    google_place_id: str,
    place_name: str,
    analysis: dict,
    reviews: list[dict],
    ttl_days: int = 7,
) -> None:
    """place_analysis 테이블에 UPSERT (v4 스키마)"""
    source_breakdown = {}
    for r in reviews:
        src = r.get("source", "unknown")
        source_breakdown[src] = source_breakdown.get(src, 0) + 1

    keywords = analysis.get("keywords", [])

    query = """
    INSERT INTO place_analysis (
        place_id, google_place_id, place_name,
        score_taste, score_service, score_atmosphere,
        score_value, score_cleanliness, score_accessibility,
        keywords, summary, review_count,
        source_breakdown, analyzed_at, ttl_expires_at
    ) VALUES (
        $1::uuid, $2, $3,
        $4, $5, $6, $7, $8, $9,
        $10::text[], $11, $12,
        $13::jsonb, NOW(), NOW() + make_interval(days => $14)
    )
    ON CONFLICT (place_id) DO UPDATE SET
        google_place_id = EXCLUDED.google_place_id,
        place_name = EXCLUDED.place_name,
        score_taste = EXCLUDED.score_taste,
        score_service = EXCLUDED.score_service,
        score_atmosphere = EXCLUDED.score_atmosphere,
        score_value = EXCLUDED.score_value,
        score_cleanliness = EXCLUDED.score_cleanliness,
        score_accessibility = EXCLUDED.score_accessibility,
        keywords = EXCLUDED.keywords,
        summary = EXCLUDED.summary,
        review_count = EXCLUDED.review_count,
        source_breakdown = EXCLUDED.source_breakdown,
        analyzed_at = NOW(),
        ttl_expires_at = EXCLUDED.ttl_expires_at
    """

    await execute(
        query,
        place_id,
        google_place_id,
        place_name,
        analysis.get("score_taste"),
        analysis.get("score_service"),
        analysis.get("score_atmosphere"),
        analysis.get("score_value"),
        analysis.get("score_cleanliness"),
        analysis.get("score_accessibility"),
        keywords,
        analysis.get("summary"),
        len(reviews),
        json.dumps(source_breakdown),
        ttl_days,
    )


# ─────────────────────── 전체 파이프라인 ───────────────────────

async def analyze_place(
    place_id: str,
    google_place_id: str,
    place_name: str,
    category: str | None = None,
) -> dict | None:
    """단일 장소 전체 분석 파이프라인"""
    logger.info(f"분석 시작: {place_name} ({google_place_id})")

    # 1. 수집
    google_reviews, google_meta = await collect_google_reviews(google_place_id)
    naver_reviews = await collect_naver_reviews(place_name)

    all_reviews = google_reviews + naver_reviews
    logger.info(f"  수집 완료: Google {len(google_reviews)}건, Naver {len(naver_reviews)}건")

    if not all_reviews:
        logger.warning(f"  리뷰 없음 — 건너뜀")
        return None

    # 2. 전처리
    cleaned = preprocess_reviews(all_reviews)
    logger.info(f"  전처리 후: {len(cleaned)}건 (필터링: {len(all_reviews) - len(cleaned)}건)")

    if not cleaned:
        logger.warning(f"  유효 리뷰 없음 — 건너뜀")
        return None

    # 3. LLM 분석
    analysis = await analyze_with_llm(place_name, category, cleaned)
    if not analysis:
        logger.error(f"  LLM 분석 실패")
        return None

    logger.info(f"  분석 완료: {json.dumps({k: v for k, v in analysis.items() if k.startswith('score_')}, ensure_ascii=False)}")

    # 4. DB 적재
    await upsert_analysis(
        place_id=place_id,
        google_place_id=google_place_id,
        place_name=place_name,
        analysis=analysis,
        reviews=cleaned,
    )
    logger.info(f"  DB 적재 완료")

    return analysis


async def batch_analyze(limit: int = 50) -> None:
    """places 테이블에서 google_place_id가 있는 장소를 배치 분석"""
    await get_pool()

    # 아직 분석되지 않았거나 만료된 장소 우선
    rows = await fetch_all("""
        SELECT p.place_id, p.google_place_id, p.name, p.category
        FROM places p
        LEFT JOIN place_analysis pa ON p.place_id = pa.place_id
        WHERE p.google_place_id IS NOT NULL
          AND (pa.place_id IS NULL OR pa.ttl_expires_at < NOW())
        ORDER BY p.created_at DESC
        LIMIT $1
    """, limit)

    logger.info(f"배치 분석 대상: {len(rows)}건")

    for i, row in enumerate(rows):
        logger.info(f"[{i+1}/{len(rows)}] {row['name']}")
        try:
            await analyze_place(
                place_id=str(row["place_id"]),
                google_place_id=row["google_place_id"],
                place_name=row["name"],
                category=row.get("category"),
            )
        except Exception as e:
            logger.error(f"  오류: {e}")

        # Rate limit 보호 (Google Places API: 초당 10건)
        await asyncio.sleep(1.0)


# ─────────────────────── CLI ───────────────────────

async def main():
    parser = argparse.ArgumentParser(description="리뷰 분석 배치 스크립트")
    parser.add_argument("--place-id", help="Google Place ID (단일 장소)")
    parser.add_argument("--name", help="장소명 (--place-id와 함께 사용)")
    parser.add_argument("--category", help="카테고리 (restaurant, cafe 등)")
    parser.add_argument("--batch", action="store_true", help="places 테이블 배치 분석")
    parser.add_argument("--limit", type=int, default=50, help="배치 분석 최대 건수")

    args = parser.parse_args()

    await get_pool()

    if args.place_id and args.name:
        # CLI 단일 실행 시 places 테이블에서 UUID 조회
        row = await fetch_one(
            "SELECT place_id FROM places WHERE google_place_id = $1",
            args.place_id,
        )
        if not row:
            print(f"places 테이블에 google_place_id={args.place_id} 없음")
            return
        result = await analyze_place(str(row["place_id"]), args.place_id, args.name, args.category)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.batch:
        await batch_analyze(limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
