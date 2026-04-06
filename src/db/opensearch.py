"""OpenSearch 클라이언트 — k-NN 벡터 검색 + 메타데이터 필터링"""

from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.src.config import get_settings
from backend.src.utils.embedding import embed_text

settings = get_settings()

_client: AsyncOpenSearch | None = None


async def get_os_client() -> AsyncOpenSearch:
    global _client
    if _client is None:
        _client = AsyncOpenSearch(
            hosts=[{"host": settings.opensearch_host, "port": settings.opensearch_port}],
            http_auth=(settings.opensearch_user, settings.opensearch_password),
            use_ssl=settings.opensearch_host != "localhost",
            verify_certs=False,
        )
    return _client


async def close_opensearch() -> None:
    global _client
    if _client:
        await _client.close()
        _client = None


async def knn_search(
    index: str,
    query_vector: list[float],
    k: int = 10,
    metadata_filter: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Pre-filtering + k-NN 벡터 유사도 검색."""
    client = await get_os_client()

    filter_clauses = []
    if metadata_filter:
        for field, value in metadata_filter.items():
            if value is not None:
                filter_clauses.append({"term": {field: value}})

    body = {
        "size": k,
        "query": {
            "bool": {
                "filter": filter_clauses if filter_clauses else [{"match_all": {}}],
                "must": [
                    {
                        "knn": {
                            "embedding": {
                                "vector": query_vector,
                                "k": k,
                            }
                        }
                    }
                ],
            }
        },
    }

    try:
        resp = await client.search(index=index, body=body)
        return [{**hit["_source"], "_score": hit["_score"]} for hit in resp["hits"]["hits"]]
    except Exception:
        return []


async def search_places(
    query: str,
    category: str = None,
    district: str = None,
    k: int = 10,
) -> list[dict[str, Any]]:
    """비정형 쿼리로 장소 검색."""
    vector = await embed_text(query)
    if not vector:
        return []

    filters = {}
    if category:
        filters["category"] = category
    if district:
        filters["district"] = district

    return await knn_search(settings.places_index, vector, k=k, metadata_filter=filters)


async def search_reviews(
    query: str,
    place_id: str = None,
    category: str = None,
    k: int = 10,
) -> list[dict[str, Any]]:
    """리뷰 의미 검색. "서비스 좋은 곳", "분위기 아늑한" 등."""
    vector = await embed_text(query)
    if not vector:
        return []

    filters = {}
    if place_id:
        filters["place_id"] = place_id
    if category:
        filters["category"] = category

    return await knn_search(settings.reviews_index, vector, k=k, metadata_filter=filters)


async def search_events(
    query: str,
    category: str = None,
    k: int = 10,
) -> list[dict[str, Any]]:
    """행사 의미 검색."""
    vector = await embed_text(query)
    if not vector:
        return []

    filters = {}
    if category:
        filters["category"] = category

    return await knn_search(settings.events_index, vector, k=k, metadata_filter=filters)


async def search_by_image_caption(
    caption_query: str,
    category: str = None,
    k: int = 5,
) -> list[dict[str, Any]]:
    """이미지 캡션 유사도 검색. image_embedding 필드 사용."""
    vector = await embed_text(caption_query)
    if not vector:
        return []

    client = await get_os_client()

    filter_clauses = [{"exists": {"field": "image_caption"}}]
    if category:
        filter_clauses.append({"term": {"category": category}})

    body = {
        "size": k,
        "_source": ["place_id", "name", "image_caption", "page_content", "category", "district"],
        "query": {
            "bool": {
                "filter": filter_clauses,
                "must": [
                    {
                        "knn": {
                            "image_embedding": {
                                "vector": vector,
                                "k": k,
                            }
                        }
                    }
                ],
            }
        },
    }

    try:
        resp = await client.search(index=settings.places_index, body=body)
        return [{**hit["_source"], "_score": hit["_score"]} for hit in resp["hits"]["hits"]]
    except Exception:
        return []


async def text_search(
    index: str,
    query_text: str,
    limit: int = 10,
    metadata_filter: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """nori 분석기 기반 텍스트 검색 (벡터 아닌 키워드 매칭)."""
    client = await get_os_client()

    filter_clauses = []
    if metadata_filter:
        for field, value in metadata_filter.items():
            if value is not None:
                filter_clauses.append({"term": {field: value}})

    # 인덱스별 검색 필드 결정
    search_fields = {
        settings.places_index: ["name^2", "page_content"],
        settings.reviews_index: ["place_name^2", "summary_text"],
        settings.events_index: ["title^2", "description"],
    }
    fields = search_fields.get(index, ["*"])

    body = {
        "size": limit,
        "query": {
            "bool": {
                "filter": filter_clauses if filter_clauses else [{"match_all": {}}],
                "must": [
                    {
                        "multi_match": {
                            "query": query_text,
                            "fields": fields,
                            "type": "best_fields",
                        }
                    }
                ],
            }
        },
    }

    try:
        resp = await client.search(index=index, body=body)
        return [{**hit["_source"], "_score": hit["_score"]} for hit in resp["hits"]["hits"]]
    except Exception:
        return []
