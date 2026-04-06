"""Google Calendar MCP 클라이언트 래퍼"""
import httpx
from backend.src.config import get_settings

settings = get_settings()

MCP_BASE = "http://localhost:3100"  # Google Calendar MCP 서버 (로컬 실행)


async def add_calendar_event(
    title: str,
    date: str,
    time: str,
    location: str = "",
    description: str = "",
    duration_minutes: int = 60,
) -> dict:
    """Google Calendar에 이벤트 추가"""
    from datetime import datetime, timedelta

    start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event_body = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Seoul",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Seoul",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{MCP_BASE}/calendar/events",
                json=event_body,
            )
            response.raise_for_status()
            data = response.json()
            return {
                "status": "created",
                "event_id": data.get("id"),
                "title": title,
                "datetime": f"{date} {time}",
                "location": location,
            }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "title": title,
            "datetime": f"{date} {time}",
        }


async def get_free_slots(date: str, duration_minutes: int = 60) -> list[dict]:
    """특정 날짜의 빈 시간대 조회"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{MCP_BASE}/calendar/freebusy",
                params={"date": date, "duration": duration_minutes},
            )
            response.raise_for_status()
            return response.json().get("free_slots", [])
    except Exception:
        # MCP 미연결 시 기본 슬롯 반환
        return [
            {"start": f"{date} 10:00", "end": f"{date} 12:00"},
            {"start": f"{date} 14:00", "end": f"{date} 18:00"},
            {"start": f"{date} 19:00", "end": f"{date} 22:00"},
        ]
