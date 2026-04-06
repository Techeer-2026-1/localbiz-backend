"""Event Search Node — 네이버 뉴스/블로그 검색 기반 행사 정보 추출"""

import asyncio
import json
import os
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.src.external.naver_blog import search_blog, search_news
from backend.src.graph.state import AgentState
from backend.src.utils.date_parser import build_event_queries, parse_date_expression

EXTRACT_SYSTEM = """당신은 뉴스/블로그 검색 결과에서 행사·이벤트·축제 정보를 구조화해 추출하는 전문가입니다.

**서울 지역 행사만 추출하세요.** 서울 외 지역(부산, 경기, 인천, 대구 등) 행사는 제외합니다.
장소 정보가 없어 서울 여부를 알 수 없는 경우에도 서울 관련 검색 결과이므로 포함합니다.

아래 검색 결과 텍스트에서 행사 정보를 추출하여 JSON 배열로만 응답하세요.

각 행사 항목:
{
  "title": "행사명 (정확하게)",
  "category": "공연/전시/축제/체험/콘서트/뮤지컬/연극/영화/스포츠/기타 중 하나",
  "place_name": "장소명 (없으면 빈 문자열)",
  "date_start": "YYYY-MM-DD (확실한 경우만, 불확실하면 빈 문자열)",
  "date_end": "YYYY-MM-DD (확실한 경우만, 불확실하면 빈 문자열)",
  "price": "가격 정보 (무료/유료/금액, 없으면 빈 문자열)",
  "detail_url": "행사 공식 사이트 URL 우선. 없으면 뉴스/블로그 원본 링크 URL",
  "summary": "행사 한 줄 소개 (50자 이내)",
  "confidence": "high/medium/low"
}

confidence 기준:
- high: 제목·날짜·장소 모두 명확
- medium: 제목은 명확하나 날짜/장소 일부 불명확
- low: 행사 언급은 있으나 세부 정보 부족

중복 행사는 하나만 포함. 검색 결과와 무관한 항목은 제외.
반드시 JSON 배열만 반환 (마크다운 코드블록 없이)."""

SUMMARY_SYSTEM = """당신은 서울 문화행사 전문 어시스턴트입니다.
아래 행사 검색 결과를 바탕으로 사용자에게 친절하게 한국어로 안내하세요.
행사명, 장소, 날짜, 요금을 간결하게 요약하고 특별히 눈에 띄는 행사를 강조해주세요."""

llm_json = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0,
    response_mime_type="application/json",
    streaming=False,
)


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _items_to_text(items: list[dict], source: str) -> str:
    parts = []
    for item in items:
        title = _clean_html(item.get("title", ""))
        desc = _clean_html(item.get("description", ""))
        link = item.get("link", "") or item.get("originallink", "")
        pub = item.get("pubDate", "") or item.get("postdate", "")
        parts.append(f"[{source}] {title}\n{desc}\nURL: {link}\n날짜: {pub}")
    return "\n\n".join(parts)


async def _search_all(queries: list[str]) -> str:
    """쿼리 목록에 대해 뉴스+블로그 병렬 검색 후 텍스트 합산"""
    tasks = []
    for q in queries:
        tasks.append(search_news(q, display=5))
        tasks.append(search_blog(q, display=5, suffix=""))
    results = await asyncio.gather(*tasks, return_exceptions=True)

    parts = []
    for i, q in enumerate(queries):
        news_items = results[i * 2]
        blog_items = results[i * 2 + 1]
        if isinstance(news_items, list) and news_items:
            parts.append(_items_to_text(news_items, "뉴스"))
        if isinstance(blog_items, list) and blog_items:
            parts.append(_items_to_text(blog_items, "블로그"))

    return "\n\n---\n\n".join(parts)


async def event_search_node(state: AgentState) -> dict:
    """행사 검색 노드 — 네이버 뉴스/블로그 검색 → LLM 구조화 → 이벤트 카드 + 텍스트 스트리밍"""
    user_message = state["user_message"]
    today = date.today()

    # 1) 날짜 파싱
    date_from, date_to, date_token = parse_date_expression(user_message, today)

    # 2) 카테고리·지역 추출 (간단 패턴 매칭)
    category = ""
    for cat in ["공연", "전시", "축제", "체험", "콘서트", "뮤지컬", "연극", "영화", "스포츠"]:
        if cat in user_message:
            category = cat
            break

    location = "서울"
    for loc in ["홍대", "강남", "이태원", "성수", "종로", "잠실", "신촌", "마포", "용산", "강북"]:
        if loc in user_message:
            location = loc
            break

    is_free = True if "무료" in user_message else (False if "유료" in user_message else None)
    keyword = ""
    # 남은 명사 힌트 추출 (카테고리/날짜/지역 제거 후 나머지)
    cleaned = re.sub(
        r"(이번|다음|주말|주중|평일|오늘|내일|\d+월|\d+일|무료|유료|서울|"
        + "|".join(
            [
                "홍대",
                "강남",
                "이태원",
                "성수",
                "종로",
                "잠실",
                "신촌",
                "마포",
                "용산",
                "강북",
                "공연",
                "전시",
                "축제",
                "체험",
                "콘서트",
                "뮤지컬",
                "연극",
                "영화",
                "스포츠",
                "행사",
                "이벤트",
                "알려줘",
                "찾아줘",
                "추천",
                "뭐",
                "있어",
                "있나",
                "없나",
            ]
        )
        + ")",
        "",
        user_message,
    )
    keyword = cleaned.strip()

    # 3) 검색 쿼리 생성
    queries = build_event_queries(
        category=category,
        location=location,
        date_token=date_token,
        keyword=keyword,
        is_free=bool(is_free) if is_free is True else False,
    )

    # 4) 병렬 검색
    search_text = await _search_all(queries)

    response_blocks = []

    if not search_text.strip():
        response_blocks.append(
            {
                "type": "text_stream",
                "system": None,
                "prompt": (
                    f"사용자가 '{user_message}'를 요청했지만 관련 행사 정보를 찾지 못했습니다. "
                    f"검색 조건({date_token}, {category or '카테고리 미지정'}, {location})으로 결과가 없었으니 "
                    f"날짜 범위를 넓히거나 다른 키워드를 사용해보라고 한국어로 안내해줘."
                ),
            }
        )
        return {
            "events": [],
            "response_blocks": response_blocks,
            "messages": [HumanMessage(content=user_message)],
        }

    # 5) LLM 구조화 추출
    extract_prompt = (
        f"사용자 요청: {user_message}\n"
        f"검색 기간: {date_from} ~ {date_to}\n"
        f"대상 지역: 서울 ({location})\n\n"
        f"검색 결과:\n{search_text[:4000]}"
    )
    try:
        resp = await llm_json.ainvoke(
            [
                SystemMessage(content=EXTRACT_SYSTEM),
                HumanMessage(content=extract_prompt),
            ]
        )
        raw = resp.content.strip()
        # JSON 배열 추출
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        events_raw = json.loads(m.group(0) if m else raw)
        if not isinstance(events_raw, list):
            events_raw = []
    except Exception:
        events_raw = []

    # 6) event_id 보장
    for i, e in enumerate(events_raw):
        if not e.get("event_id"):
            slug = re.sub(r"[^a-zA-Z0-9가-힣]", "_", e.get("title", ""))[:30]
            e["event_id"] = f"{slug}_{date_from}_{i}"

    # confidence 필터 + 날짜 범위 보정
    high_events = [e for e in events_raw if e.get("confidence") == "high"]
    medium_events = [e for e in events_raw if e.get("confidence") == "medium"]

    # date 미지정 항목에 파싱된 날짜 보완
    for e in high_events + medium_events:
        if not e.get("date_start"):
            e["date_start"] = date_from
        if not e.get("date_end"):
            e["date_end"] = date_to

    # 카드로 표시할 행사 (최대 5개)
    card_events = (high_events + medium_events)[:5]

    if not card_events:
        response_blocks.append(
            {
                "type": "text_stream",
                "system": None,
                "prompt": (
                    f"사용자 요청: {user_message}\n"
                    f"검색 기간: {date_from} ~ {date_to}\n\n"
                    f"검색은 됐지만 구체적인 행사 정보를 추출하기 어려웠습니다. "
                    f"아래 검색 내용을 바탕으로 관련 행사·이벤트를 요약해서 한국어로 안내해줘:\n\n"
                    f"{search_text[:1500]}"
                ),
            }
        )
        return {
            "events": [],
            "response_blocks": response_blocks,
            "messages": [HumanMessage(content=user_message)],
        }

    # 행사 카드 블록
    response_blocks.append({"type": "events", "data": card_events})

    # 텍스트 요약
    event_summary = "\n".join(
        f"- {e['title']} | {e.get('place_name', '장소 미정')} | "
        f"{e.get('date_start', '')}~{e.get('date_end', '')} | "
        f"{e.get('price', '요금 미정')}"
        for e in card_events
    )
    response_blocks.append(
        {
            "type": "text_stream",
            "system": SUMMARY_SYSTEM,
            "prompt": (f"사용자 요청: {user_message}\n\n검색된 행사 {len(card_events)}건:\n{event_summary}"),
        }
    )

    return {
        "events": card_events,
        "response_blocks": response_blocks,
        "messages": [HumanMessage(content=user_message)],
    }
