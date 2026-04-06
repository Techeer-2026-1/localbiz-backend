from typing import Optional
from pydantic import BaseModel

class ChatSession(BaseModel):
    chat_id: str
    title: Optional[str] = None
    last_message: Optional[str] = None
    updated_at: Optional[str] = None
