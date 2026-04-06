"""즐겨찾기 관리 API"""
from typing import List, Optional
from fastapi import APIRouter, Header, HTTPException
from backend.src.db.postgres import fetch_all, execute

router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])


@router.get("")
async def get_favorites(x_user_id: Optional[str] = Header(default=None)):
    """사용자의 즐겨찾기 목록 조회"""
    if not x_user_id:
        return []

    try:
        sql = """
            SELECT p.place_id::text, p.name, p.category, p.sub_category, p.address,
                   p.image_url, p.rating, p.google_place_id
            FROM user_favorites f
            JOIN places p ON f.place_id = p.place_id
            WHERE f.user_id = $1
            ORDER BY f.created_at DESC
        """
        rows = await fetch_all(sql, x_user_id)
        return rows
    except Exception:
        return []


@router.post("/{place_id}")
async def add_favorite(
    place_id: str,
    x_user_id: Optional[str] = Header(default=None),
):
    """즐겨찾기 추가"""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await execute(
            "INSERT INTO user_favorites (user_id, place_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            x_user_id, place_id
        )
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{place_id}")
async def remove_favorite(
    place_id: str,
    x_user_id: Optional[str] = Header(default=None),
):
    """즐겨찾기 삭제"""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await execute(
            "DELETE FROM user_favorites WHERE user_id = $1 AND place_id = $2",
            x_user_id, place_id
        )
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
