"""네이버 블로그 검색 API"""

import httpx

from backend.src.config import get_settings

settings = get_settings()

NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"


async def _naver_search(endpoint: str, query: str, display: int, sort: str) -> list[dict]:
    """네이버 검색 API 공통 호출"""
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "sort": sort}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"https://openapi.naver.com/v1/search/{endpoint}.json", headers=headers, params=params
            )
            return response.json().get("items", [])
    except Exception:
        return []


async def search_news(query: str, display: int = 5) -> list[dict]:
    """
    네이버 뉴스 검색 — 행사 공식 발표, 개막 정보 등
    Returns: list of {"title", "description", "link", "pubDate"}
    """
    return await _naver_search("news", query, display, "date")


async def search_blog(query: str, display: int = 5, suffix: str = " 후기") -> list[dict]:
    """
    네이버 블로그 검색

    Args:
        query : 검색어
        suffix: 쿼리 접미사 (기본 " 후기", 이벤트 검색 시 "" 또는 " 다녀온")
    Returns:
        list of {"title", "description", "link", "postdate"}
    """
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {
        "query": f"{query}{suffix}",
        "display": display,
        "sort": "date",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(NAVER_SEARCH_URL, headers=headers, params=params)
            data = response.json()
        return data.get("items", [])
    except Exception:
        return []


def extract_trend_score(items: list[dict]) -> float:
    """블로그 언급 빈도 → 0~1 트렌드 점수"""
    if not items:
        return 0.0
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
    recent = sum(1 for item in items if item.get("postdate", "") >= cutoff)
    return min(recent / len(items), 1.0)


def summarize_reviews(items: list[dict], max_chars: int = 400) -> str:
    """블로그 후기 목록 → LLM에 넘길 텍스트로 요약"""
    import re

    texts = []
    total = 0
    for item in items:
        # HTML 태그 제거
        desc = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()
        if not desc:
            continue
        texts.append(f"- {desc}")
        total += len(desc)
        if total >= max_chars:
            break
    return "\n".join(texts) if texts else ""
