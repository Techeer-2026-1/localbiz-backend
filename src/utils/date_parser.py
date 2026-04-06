"""사용자 날짜 표현 → (date_from, date_to, query_token) 변환"""

import re
from calendar import monthrange
from datetime import date, timedelta


def parse_date_expression(expr: str, base: date | None = None) -> tuple[str, str, str]:
    """
    사용자 날짜 표현을 파싱하여 (date_from, date_to, 쿼리토큰) 반환.

    Returns:
        (date_from: YYYY-MM-DD, date_to: YYYY-MM-DD, query_token: 검색어용 날짜 표현)
    """
    today = base or date.today()
    weekday = today.weekday()  # 월=0, 일=6
    year = today.year

    # ── 이번 주말 (이번 주보다 먼저 매칭) ─────────────────────────────────
    if re.search(r"이번\s*주말", expr):
        sat = today + timedelta(days=(5 - weekday) % 7)
        sun = sat + timedelta(days=1)
        token = f"{year}년 {sat.month}월 {sat.day}일 {sun.day}일"
        return sat.isoformat(), sun.isoformat(), token

    # ── 다음 주말 ─────────────────────────────────────────────────────────
    if re.search(r"다음\s*주말", expr):
        sat = today + timedelta(days=(5 - weekday) % 7 + 7)
        sun = sat + timedelta(days=1)
        token = f"{year}년 {sat.month}월 {sat.day}일"
        return sat.isoformat(), sun.isoformat(), token

    # ── 이번 주 ──────────────────────────────────────────────────────────
    if re.search(r"이번\s*주(?!말)", expr):
        start = today - timedelta(days=weekday)
        end = start + timedelta(days=6)
        token = f"{year}년 {today.month}월 {_week_of_month(today)}주"
        return start.isoformat(), end.isoformat(), token

    # ── 다음 주 ──────────────────────────────────────────────────────────
    if re.search(r"다음\s*주(?!말)", expr):
        start = today - timedelta(days=weekday) + timedelta(days=7)
        end = start + timedelta(days=6)
        token = f"{year}년 {start.month}월 {_week_of_month(start)}주"
        return start.isoformat(), end.isoformat(), token

    # ── 주중 / 평일 ───────────────────────────────────────────────────────
    if re.search(r"주중|평일", expr):
        days_to_fri = (4 - weekday) if weekday <= 4 else (11 - weekday)
        end = today + timedelta(days=days_to_fri)
        token = f"{year}년 {today.month}월 평일"
        return today.isoformat(), end.isoformat(), token

    # ── 오늘 ─────────────────────────────────────────────────────────────
    if re.search(r"오늘", expr):
        token = f"{year}년 {today.month}월 {today.day}일"
        return today.isoformat(), today.isoformat(), token

    # ── 내일 ─────────────────────────────────────────────────────────────
    if re.search(r"내일", expr):
        tom = today + timedelta(days=1)
        token = f"{year}년 {tom.month}월 {tom.day}일"
        return tom.isoformat(), tom.isoformat(), token

    # ── 다음 달 (이번 달보다 먼저) ────────────────────────────────────────
    if re.search(r"다음\s*달|다음\s*월", expr):
        nm = today.month % 12 + 1
        ny = year if today.month < 12 else year + 1
        last = monthrange(ny, nm)[1]
        token = f"{ny}년 {nm}월"
        return date(ny, nm, 1).isoformat(), date(ny, nm, last).isoformat(), token

    # ── 이번 달 ──────────────────────────────────────────────────────────
    if re.search(r"이번\s*달|이번\s*월", expr):
        last = monthrange(year, today.month)[1]
        end = date(year, today.month, last)
        token = f"{year}년 {today.month}월"
        return today.isoformat(), end.isoformat(), token

    # ── N월 초/중/말 ──────────────────────────────────────────────────────
    m = re.search(r"(\d{1,2})월\s*(초|중순|중|말|하순)", expr)
    if m:
        mn, part = int(m.group(1)), m.group(2)
        ny = year if mn >= today.month else year + 1
        last = monthrange(ny, mn)[1]
        if "초" in part:
            s, e = date(ny, mn, 1), date(ny, mn, 10)
        elif "중" in part:
            s, e = date(ny, mn, 11), date(ny, mn, 20)
        else:
            s, e = date(ny, mn, 21), date(ny, mn, last)
        token = f"{ny}년 {mn}월 {part}"
        return s.isoformat(), e.isoformat(), token

    # ── N월 N일 ──────────────────────────────────────────────────────────
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", expr)
    if m:
        mn, dd = int(m.group(1)), int(m.group(2))
        try:
            d = date(year, mn, dd)
            ny = year if d >= today else year + 1
            d = date(ny, mn, dd)
        except ValueError:
            d = today
        token = f"{d.year}년 {mn}월 {dd}일"
        return d.isoformat(), d.isoformat(), token

    # ── N월 (단독) ────────────────────────────────────────────────────────
    m = re.search(r"(\d{1,2})월", expr)
    if m:
        mn = int(m.group(1))
        ny = year if mn >= today.month else year + 1
        last = monthrange(ny, mn)[1]
        token = f"{ny}년 {mn}월"
        return date(ny, mn, 1).isoformat(), date(ny, mn, last).isoformat(), token

    # ── 계절 ─────────────────────────────────────────────────────────────
    seasons = {"봄": (3, 5), "여름": (6, 8), "가을": (9, 11), "겨울": (12, 2)}
    for name, (sm, em) in seasons.items():
        if name in expr:
            if sm > em:  # 겨울
                s = date(year, 12, 1) if today.month <= 12 else date(year + 1, 12, 1)
                e = date(s.year + 1, 2, monthrange(s.year + 1, 2)[1])
            else:
                ny = year if sm >= today.month else year + 1
                s = date(ny, sm, 1)
                e = date(ny, em, monthrange(ny, em)[1])
            token = f"{s.year}년 {name}"
            return s.isoformat(), e.isoformat(), token

    # ── 기본값: 오늘부터 한 달 ────────────────────────────────────────────
    end = today + timedelta(days=30)
    token = f"{year}년 {today.month}월"
    return today.isoformat(), end.isoformat(), token


def _week_of_month(d: date) -> int:
    return (d.day - 1) // 7 + 1


def build_event_queries(
    category: str,
    location: str,
    date_token: str,
    keyword: str = "",
    is_free: bool = False,
) -> list:
    """
    검색 쿼리 조합 생성 (뉴스/블로그 공용)
    반환: 우선순위 높은 순 쿼리 리스트 (최대 3개)
    """
    loc = location or "서울"
    cat = category or "행사"
    free = " 무료" if is_free else ""
    kw = f" {keyword}" if keyword else ""

    queries = [
        f"{loc} {cat}{free} {date_token}{kw}",
        f"서울{free} {cat} {date_token}{kw}",
        f"{cat}{free}{kw} {date_token}",
    ]
    seen, result = set(), []
    for q in queries:
        q = q.strip()
        if q not in seen:
            seen.add(q)
            result.append(q)
    return result


# 기존 호환성 유지
def parse_date_range(text: str, base_date=None):
    from_s, to_s, _ = parse_date_expression(text, base_date)
    return date.fromisoformat(from_s), date.fromisoformat(to_s)
