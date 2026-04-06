"""Intent Router Logic — 의도별 다음 노드 결정"""
from backend.src.graph.state import AgentState

def route_by_intent(state: AgentState) -> str:
    """의도별 다음 노드 결정"""
    intent = state.get("intent", "GENERAL")

    if intent == "GENERAL":
        return "conversation"

    if intent in {"PLACE_SEARCH", "DETAIL_INQUIRY"}:
        return "place_search"

    if intent == "PLACE_RECOMMEND":
        return "place_recommend"

    if intent == "EVENT_SEARCH":
        return "event_search"

    if intent == "COURSE_PLAN":
        return "course_plan"

    if intent in {"ANALYSIS", "COST_ESTIMATE", "CROWDEDNESS", "REVIEW_WRITE"}:
        return "search_agent"

    if intent in {"BOOKING", "FAVORITE"}:
        return "action_agent"

    return "conversation"
