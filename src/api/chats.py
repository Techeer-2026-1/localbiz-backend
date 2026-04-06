"""채팅 세션 관리 API"""
from typing import List, Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from backend.src.db.postgres import fetch_all, execute
from backend.src.lib.types import ChatSession

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


class ChatCreateResponse(BaseModel):
    chat_id: str


@router.post("", response_model=ChatCreateResponse)
async def create_chat(x_user_id: Optional[str] = Header(default=None)):
    """새 채팅 세션 생성"""
    import uuid
    chat_id = str(uuid.uuid4())
    
    # DB에 세션 생성 (users 테이블에 x_user_id가 있어야 하지만, PoC에서는 무시하거나 자동생성)
    try:
        await execute(
            "INSERT INTO conversations (chat_id, user_id, title) VALUES ($1, $2, $3)",
            chat_id, x_user_id, "새 대화"
        )
    except Exception:
        # DB 없으면 메모리 기반으로 동작하므로 무시
        pass

    return {"chat_id": chat_id}


@router.get("", response_model=List[ChatSession])
async def list_chats(x_user_id: Optional[str] = Header(default=None)):
    """사용자의 채팅 목록 조회"""
    if not x_user_id:
        return []
    
    try:
        rows = await fetch_all(
            "SELECT chat_id::text, title, last_message, updated_at::text FROM conversations WHERE user_id = $1 ORDER BY updated_at DESC",
            x_user_id
        )
        return rows
    except Exception:
        return []
