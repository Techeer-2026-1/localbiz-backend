"""PostgreSQL 커넥션 풀 및 쿼리 헬퍼"""
import asyncpg
from typing import Optional, List, Dict, Any
from backend.src.config import get_settings

settings = get_settings()

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=1,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def fetch_all(query: str, *args) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


async def fetch_one(query: str, *args) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def execute(query: str, *args) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
