"""WebSocket 엔드포인트 — 채팅의 모든 기능 처리"""
import os
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from backend.src.graph.real_builder import get_graph
from backend.src.db.postgres import execute

_stream_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ.get("GEMINI_LLM_API_KEY", ""),
    temperature=0.3,
)

logger = logging.getLogger(__name__)


async def chat_websocket(websocket: WebSocket, chat_id: str):
    """
    WebSocket /ws/chat/{chat_id}

    Client → Server: {"message": "...", "user_id": "...", "location": {"lat": 0, "lng": 0}}
    Server → Client: 스트리밍 response blocks (text, places, events, map_markers, ...)
    """
    await websocket.accept()

    graph = await get_graph()
    config = {"configurable": {"thread_id": chat_id}}

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            user_message = payload.get("message", "").strip()
            user_id = payload.get("user_id")
            user_location = payload.get("location")  # {"lat": 37.5, "lng": 127.0}

            if not user_message:
                continue

            # 채팅 세션 title 업데이트 (첫 메시지) - DB 연결 안 될 수 있으므로 try
            try:
                await _update_conversation(chat_id, user_message)
            except Exception:
                pass

            initial_state = {
                "chat_id": chat_id,
                "user_id": user_id,
                "user_message": user_message,
                "user_location": user_location,
                "places": [],
                "events": [],
                "route": None,
                "calendar": None,
                "favorites": None,
                "booking": None,
                "statistics": None,
                "response_blocks": [],
                "messages": [],
            }

            # LangGraph 실행
            try:
                async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
                    for node_name, node_output in event.items():
                        # response_composer는 이미 전송한 블록을 재정렬만 하므로 스킵
                        if node_name == "response_composer":
                            continue

                        if node_name == "intent_router" and node_output.get("intent"):
                            await websocket.send_json({"type": "intent", "value": node_output["intent"]})

                        for block in node_output.get("response_blocks", []):
                            if block["type"] == "text_stream":
                                # Gemini .astream()으로 토큰 단위 직접 스트리밍
                                msgs = []
                                if block.get("system"):
                                    msgs.append(SystemMessage(content=block["system"]))
                                msgs.append(HumanMessage(content=block["prompt"]))
                                async for chunk in _stream_llm.astream(msgs):
                                    if chunk.content:
                                        await websocket.send_json({"type": "text", "content": chunk.content})
                            else:
                                await websocket.send_json(block)

                await websocket.send_json({"type": "done"})

            except (WebSocketDisconnect, RuntimeError):
                return
            except Exception as e:
                logger.error(f"Error in graph execution: {e}")
                try:
                    await websocket.send_json({
                        "type": "text",
                        "content": f"처리 중 오류가 발생했습니다: {str(e)}",
                    })
                    await websocket.send_json({"type": "done"})
                except Exception:
                    return

    except (WebSocketDisconnect, RuntimeError):
        pass


async def _update_conversation(chat_id: str, message: str) -> None:
    """채팅 세션 last_message 업데이트 및 title 초기화"""
    try:
        preview = message[:100]
        await execute(
            """
            UPDATE conversations
            SET last_message = $1, updated_at = NOW(),
                title = COALESCE(NULLIF(title, ''), $2)
            WHERE chat_id = $3
            """,
            preview, preview[:50], chat_id,
        )
    except Exception:
        pass
