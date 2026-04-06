"""장소 분석 API — 리뷰 비교 레이더차트 데이터 제공"""

from fastapi import APIRouter, HTTPException, Query

from backend.src.db.postgres import fetch_all, fetch_one

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.get("/places/{place_id}/analysis")
async def get_place_analysis(place_id: str):
    """단일 장소 분석 결과 조회"""
    row = await fetch_one(
        "SELECT * FROM place_analysis WHERE place_id = $1",
        place_id,
    )
    if not row:
        raise HTTPException(404, "분석 데이터가 없습니다. 배치 분석을 먼저 실행하세요.")

    return _format_analysis(row)


@router.get("/places/compare")
async def compare_places(
    ids: str = Query(..., description="콤마로 구분된 place_id 목록 (예: id1,id2,id3)"),
):
    """복수 장소 비교 — 레이더차트용 데이터 반환"""
    place_ids = [pid.strip() for pid in ids.split(",") if pid.strip()]
    if len(place_ids) < 2:
        raise HTTPException(400, "비교하려면 최소 2개 장소 ID가 필요합니다.")
    if len(place_ids) > 5:
        raise HTTPException(400, "최대 5개 장소까지 비교 가능합니다.")

    # IN 절 생성 ($1, $2, $3...)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(place_ids)))
    rows = await fetch_all(
        f"SELECT * FROM place_analysis WHERE place_id IN ({placeholders})",
        *place_ids,
    )

    if not rows:
        raise HTTPException(404, "분석 데이터가 없습니다.")

    # 레이더차트 데이터 변환
    analyses = [_format_analysis(r) for r in rows]

    # Recharts 레이더 차트 포맷
    dimensions = ["맛", "서비스", "분위기", "가성비", "청결도", "접근성"]
    score_keys = [
        "score_taste",
        "score_service",
        "score_atmosphere",
        "score_value",
        "score_cleanliness",
        "score_accessibility",
    ]

    chart_data = []
    for dim, key in zip(dimensions, score_keys, strict=False):
        entry = {"dimension": dim}
        for a in analyses:
            entry[a["place_name"]] = a["scores"].get(key) or 0
        chart_data.append(entry)

    return {
        "places": analyses,
        "chart": {
            "chart_type": "radar",
            "title": " vs ".join(a["place_name"] for a in analyses),
            "data": chart_data,
            "keys": [a["place_name"] for a in analyses],
        },
    }


def _format_analysis(row: dict) -> dict:
    """DB row → API 응답 포맷"""
    return {
        "place_id": row["place_id"],
        "place_name": row["place_name"],
        "category": row.get("category"),
        "scores": {
            "score_taste": row.get("score_taste"),
            "score_service": row.get("score_service"),
            "score_atmosphere": row.get("score_atmosphere"),
            "score_value": row.get("score_value"),
            "score_cleanliness": row.get("score_cleanliness"),
            "score_accessibility": row.get("score_accessibility"),
        },
        "avg_rating": row.get("avg_rating"),
        "total_reviews": row.get("total_reviews"),
        "summary": row.get("summary"),
        "keywords": row.get("keywords"),
        "source_breakdown": row.get("source_breakdown"),
        "analyzed_at": str(row.get("analyzed_at", "")),
    }
