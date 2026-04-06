"""즐겨찾기 도구 — PostgreSQL user_favorites"""
from langchain_core.tools import tool
from backend.src.db.postgres import fetch_all, execute, fetch_one


@tool
async def add_favorite(place_id: str, user_id: str) -> dict:
    """즐겨찾기 추가"""
    await execute(
        """
        INSERT INTO user_favorites (user_id, place_id)
        VALUES ($1, $2)
        ON CONFLICT (user_id, place_id) DO NOTHING
        """,
        user_id, place_id,
    )
    return {"status": "added", "place_id": place_id}


@tool
async def remove_favorite(place_id: str, user_id: str) -> dict:
    """즐겨찾기 삭제"""
    await execute(
        "DELETE FROM user_favorites WHERE user_id = $1 AND place_id = $2",
        user_id, place_id,
    )
    return {"status": "removed", "place_id": place_id}


@tool
async def list_favorites(user_id: str) -> list[dict]:
    """즐겨찾기 목록 조회"""
    rows = await fetch_all(
        """
        SELECT p.place_id::text, p.name, p.category, p.address,
               p.image_url, p.booking_url, uf.created_at::text AS added_at
        FROM user_favorites uf
        JOIN places p ON uf.place_id = p.place_id
        WHERE uf.user_id = $1
        ORDER BY uf.created_at DESC
        """,
        user_id,
    )
    return rows
