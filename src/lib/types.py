from pydantic import BaseModel


class ChatSession(BaseModel):
    chat_id: str
    title: str | None = None
    last_message: str | None = None
    updated_at: str | None = None
