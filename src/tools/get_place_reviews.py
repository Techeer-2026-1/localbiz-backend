"""장소 리뷰 검색 도구 — OpenSearch place_reviews k-NN 검색"""
from langchain_core.tools import tool
from backend.src.db.opensearch import knn_search, text_search
from backend.src.utils.embedding import embed_text


@tool
async def get_place_reviews(
    place_id: str,
    query: str = "",
    limit: int = 5,
) -> list[dict]:
    """
    장소 리뷰 검색.
    query가 있으면 의미 검색, 없으면 해당 장소 최신 리뷰 반환.

    Args:
        place_id: 대상 장소 UUID
        query: 의미 검색어 (예: "분위기", "서비스", "가격")
        limit: 결과 수
    """
    metadata_filter = {"place_id": place_id}

    if query:
        query_vector = await embed_text(query)
        results = await knn_search(
            index="place_reviews",
            query_vector=query_vector,
            k=limit,
            metadata_filter=metadata_filter,
        )
    else:
        results = await text_search(
            index="place_reviews",
            query=place_id,
            field="place_id",
            size=limit,
        )

    return [
        {
            "review_id": r.get("review_id"),
            "place_id": r.get("place_id"),
            "text": r.get("summary_text") or r.get("page_content", ""),
            "stars": r.get("stars"),
        }
        for r in results
    ]
