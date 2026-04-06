"""Conversation Agent — Gemini 직접 응답"""

import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.src.config import get_settings
from backend.src.graph.state import AgentState

settings = get_settings()

CONVERSATION_SYSTEM_PROMPT = """당신은 서울 로컬 생활 정보 전문 AI 어시스턴트 LocalBiz입니다.
서울의 맛집, 카페, 헬스장, 미용실, 행사, 축제 등 생활 정보에 특화되어 있습니다.
친근하고 간결하게 한국어로 답변하세요. 장소 추천, 행사 검색, 일정 추가 등을 도울 수 있다고 안내하세요."""

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0.7,
)


async def conversation_agent(state: AgentState) -> dict:
    """일반 대화 노드 — 도구 없이 LLM 직접 응답"""
    history = state.get("messages", [])

    messages = [SystemMessage(content=CONVERSATION_SYSTEM_PROMPT)]
    messages.extend(history[-10:])  # 최근 10턴만 컨텍스트로 사용
    messages.append(HumanMessage(content=state["user_message"]))

    # 프롬프트를 블록으로 반환 — websocket이 직접 스트리밍
    history_text = (
        "\n".join(
            f"{'user' if m.__class__.__name__ == 'HumanMessage' else 'assistant'}: {m.content}" for m in history[-6:]
        )
        if history
        else ""
    )

    prompt = f"{history_text}\nuser: {state['user_message']}" if history_text else state["user_message"]

    return {
        "response_blocks": [
            {
                "type": "text_stream",
                "system": CONVERSATION_SYSTEM_PROMPT,
                "prompt": prompt,
            }
        ],
        "messages": [HumanMessage(content=state["user_message"])],
    }
