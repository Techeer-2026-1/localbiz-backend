"""Google Calendar 일정 추가 도구 (MCP)"""
from langchain_core.tools import tool
from backend.src.external.calendar_mcp import add_calendar_event


@tool
async def add_to_calendar(
    title: str,
    date: str,
    time: str,
    location: str = "",
    description: str = "",
    duration_minutes: int = 60,
) -> dict:
    """
    Google Calendar에 일정 추가.

    Args:
        title: 일정 제목 (예: "홍대 이탈리안 레스토랑")
        date: 날짜 "YYYY-MM-DD"
        time: 시간 "HH:MM"
        location: 장소 주소
        description: 메모 (전화번호, 특이사항)
        duration_minutes: 일정 소요 시간(분), 기본 60분
    """
    result = await add_calendar_event(
        title=title,
        date=date,
        time=time,
        location=location,
        description=description,
        duration_minutes=duration_minutes,
    )
    return result


@tool
async def get_free_slots(
    date: str,
    duration_minutes: int = 60,
) -> list[dict]:
    """
    특정 날짜의 빈 시간대 조회.

    Args:
        date: 날짜 "YYYY-MM-DD"
        duration_minutes: 필요한 소요 시간(분)
    """
    from backend.src.external.calendar_mcp import get_free_slots as _get_slots
    return await _get_slots(date=date, duration_minutes=duration_minutes)
