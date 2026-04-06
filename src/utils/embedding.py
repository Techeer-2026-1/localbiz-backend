"""Gemini 임베딩 헬퍼"""
from typing import List
import httpx
from backend.src.config import get_settings

settings = get_settings()

GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "text-embedding-004:embedContent"
)


async def embed_text(text: str) -> List[float]:
    """Gemini text-embedding-004 (768차원)"""
    if not text:
        return []

    payload = {
        "model": "models/text-embedding-004",
        "content": {"parts": [{"text": text.replace("\n", " ")}]},
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{GEMINI_EMBED_URL}?key={settings.gemini_llm_api_key}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]
