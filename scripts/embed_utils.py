"""Gemini text-embedding-004 배치 임베딩 유틸 (동기, ETL 스크립트용)"""

import httpx
import logging
from dotenv import load_dotenv

load_dotenv("backend/.env")
load_dotenv(".env")

from backend.src.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-001:embedContent"
)
DIMENSION = 768


def _embed_one(text: str, client: httpx.Client) -> list:
    """단일 텍스트 임베딩 (동기)."""
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text.replace("\n", " ")[:2000]}]},
        "outputDimensionality": DIMENSION,
    }
    resp = client.post(
        f"{GEMINI_EMBED_URL}?key={settings.gemini_llm_api_key}",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    텍스트 리스트 → 768d 벡터 리스트.
    Gemini embedContent API 순차 호출. 무료.
    빈 문자열은 제로 벡터.
    """
    if not texts:
        return []

    non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
    if not non_empty:
        return [[0.0] * DIMENSION for _ in texts]

    indices, clean_texts = zip(*non_empty)
    results = [None] * len(texts)

    with httpx.Client() as client:
        for j, (idx, text) in enumerate(zip(indices, clean_texts)):
            try:
                results[idx] = _embed_one(text, client)
            except Exception as e:
                logger.warning(f"  임베딩 실패 [{j}]: {e}")
                results[idx] = [0.0] * DIMENSION

    for i in range(len(results)):
        if results[i] is None:
            results[i] = [0.0] * DIMENSION

    return results


def embed_single(text: str) -> list[float]:
    """단일 텍스트 임베딩."""
    return embed_texts([text])[0]
