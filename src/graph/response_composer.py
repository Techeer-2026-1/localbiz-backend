"""Response Composer — AgentState → 최종 response_blocks 정리"""

from backend.src.graph.state import AgentState


async def response_composer(state: AgentState) -> dict:
    """
    AgentState를 최종 WebSocket 전송용 블록 목록으로 정리.
    중복 제거 및 순서 정렬: text → places → events → map → chart → calendar
    """
    blocks = state.get("response_blocks", [])

    # 블록 타입별 순서
    ORDER = ["text", "places", "events", "map_markers", "map_route", "chart", "calendar", "favorites"]
    priority = {t: i for i, t in enumerate(ORDER)}

    # 중복 타입 제거 (마지막 것 유지), 순서 정렬
    # text_stream, chart 등은 여러 개 허용
    ALLOW_MULTIPLE = {"text", "text_stream", "chart", "references", "analysis_sources"}
    seen_types: dict[str, dict] = {}
    multi_blocks: list[dict] = []

    for block in blocks:
        t = block.get("type", "text")
        if t in ALLOW_MULTIPLE:
            multi_blocks.append(block)
        else:
            seen_types[t] = block

    sorted_blocks = sorted(
        list(seen_types.values()) + multi_blocks,
        key=lambda b: priority.get(b.get("type", "text"), 99),
    )
    # response_composer가 호출될 때 이미 최종 단계이므로 done은 WebSocket에서 보내거나 여기서 추가
    # WebSocket 로직에서 보낼 수도 있으므로 중복 주의

    return {"response_blocks": sorted_blocks}
