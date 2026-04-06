"""리뷰 비교 도구 — place_analysis 테이블에서 분석 데이터 조회 및 차트 생성"""
from __future__ import annotations

import json
from typing import Optional
from langchain_core.tools import tool
from backend.src.db.postgres import fetch_all, fetch_one

DIMENSIONS = [
    ("score_taste", "맛"),
    ("score_service", "서비스"),
    ("score_atmosphere", "분위기"),
    ("score_value", "가성비"),
    ("score_cleanliness", "청결도"),
    ("score_accessibility", "접근성"),
]

SCORE_CRITERIA = {
    "맛": "음식/음료의 맛, 퀄리티, 메뉴 다양성에 대한 평가",
    "서비스": "직원 친절도, 응대 속도, 주문 편의성에 대한 평가",
    "분위기": "인테리어, 조명, 소음, 좌석 편안함에 대한 평가",
    "가성비": "가격 대비 만족도, 양, 품질에 대한 평가",
    "청결도": "매장, 화장실, 테이블 위생 상태에 대한 평가",
    "접근성": "교통, 주차, 위치 편의성에 대한 평가",
}


@tool
async def compare_reviews(place_names: str) -> str:
    """두 개 이상의 장소를 리뷰 기반으로 비교 분석합니다.
    6개 지표(맛, 서비스, 분위기, 가성비, 청결도, 접근성)의 레이더차트와 요약을 반환합니다.

    Args:
        place_names: 비교할 장소명 (콤마로 구분). 예: "스타벅스 강남R점,블루보틀 삼청 카페"
    """
    names = [n.strip() for n in place_names.split(",") if n.strip()]
    if len(names) < 2:
        return json.dumps({"error": "비교하려면 최소 2개 장소명이 필요합니다."}, ensure_ascii=False)

    # place_name LIKE 검색으로 유연하게 매칭
    rows = []
    for name in names:
        row = await fetch_one(
            "SELECT * FROM place_analysis WHERE place_name ILIKE $1 ORDER BY analyzed_at DESC LIMIT 1",
            f"%{name}%",
        )
        if row:
            rows.append(row)

    if len(rows) < 2:
        found = [r["place_name"] for r in rows]
        missing = [n for n in names if not any(n in f for f in found)]
        return json.dumps({
            "error": f"분석 데이터가 부족합니다. 찾은 장소: {found}, 미발견: {missing}. 배치 분석이 필요합니다."
        }, ensure_ascii=False)

    # ── 레이더차트 데이터 ──
    chart_data = []
    for key, label in DIMENSIONS:
        entry = {"dimension": label}
        for r in rows:
            entry[r["place_name"]] = float(r.get(key) or 0)
        chart_data.append(entry)

    # ── 출처 및 기준 정보 ──
    sources = []
    for r in rows:
        source_breakdown = r.get("source_breakdown") or {}
        if isinstance(source_breakdown, str):
            source_breakdown = json.loads(source_breakdown)

        raw_reviews = r.get("raw_reviews") or []
        if isinstance(raw_reviews, str):
            raw_reviews = json.loads(raw_reviews)

        # 원본 리뷰 샘플 (출처별 최대 2건)
        google_samples = [rv for rv in raw_reviews if rv.get("source") == "google"][:2]
        naver_samples = [rv for rv in raw_reviews if rv.get("source") == "naver"][:2]

        keywords = r.get("keywords") or []
        if isinstance(keywords, str):
            keywords = json.loads(keywords)

        sources.append({
            "place_name": r["place_name"],
            "avg_rating": float(r["avg_rating"]) if r.get("avg_rating") else None,
            "total_reviews": r.get("total_reviews"),
            "source_breakdown": source_breakdown,
            "analyzed_at": str(r.get("analyzed_at", "")),
            "summary": r.get("summary"),
            "keywords": keywords,
            "sample_reviews": {
                "google": google_samples,
                "naver": naver_samples,
            },
            "scores": {
                label: float(r.get(key) or 0)
                for key, label in DIMENSIONS
            },
        })

    result = {
        "chart": {
            "type": "chart",
            "chart_type": "radar",
            "title": " vs ".join(r["place_name"] for r in rows),
            "data": chart_data,
            "keys": [r["place_name"] for r in rows],
        },
        "analysis_sources": {
            "type": "analysis_sources",
            "places": sources,
            "criteria": SCORE_CRITERIA,
            "methodology": "Google Places 리뷰 + 네이버 블로그 후기를 수집 → 광고/스팸 필터링 → Gemini 2.5 Flash LLM이 1~5점 정량화",
        },
    }

    return json.dumps(result, ensure_ascii=False, default=str)
