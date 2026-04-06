"""Gemini 임베딩 헬퍼 (런타임 async)"""
from typing import List
import httpx
from backend.src.config import get_settings

settings = get_settings()

GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-001:embedContent"
)
DIMENSION = 768


async def embed_text(text: str) -> List[float]:
    """Gemini gemini-embedding-001 (768차원)"""
    if not text:
        return []

    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text.replace("\n", " ")[:2000]}]},
        "outputDimensionality": DIMENSION,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{GEMINI_EMBED_URL}?key={settings.gemini_llm_api_key}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]
