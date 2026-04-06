"""OpenSearch 인덱스 생성 스크립트 (v4 — Gemini 768d, nori 분석기)"""

import asyncio
import os

from dotenv import load_dotenv
from opensearchpy import AsyncOpenSearch

load_dotenv("backend/.env")
load_dotenv(".env")

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", 9200))
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")

KNN_METHOD = {"name": "hnsw", "engine": "nmslib", "space_type": "cosinesimil"}
NORI_SETTINGS = {
    "index": {
        "knn": True,
        "knn.algo_param.ef_search": 100,
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "analysis": {
        "analyzer": {
            "nori_analyzer": {
                "type": "custom",
                "tokenizer": "nori_tokenizer",
                "filter": ["lowercase"],
            }
        }
    },
}

# ── 인덱스 1: places_vector ──
PLACES_VECTOR_MAPPING = {
    "settings": NORI_SETTINGS,
    "mappings": {
        "properties": {
            "place_id": {"type": "keyword"},
            "name": {"type": "text", "analyzer": "nori_analyzer"},
            "page_content": {"type": "text", "analyzer": "nori_analyzer"},
            "embedding": {"type": "knn_vector", "dimension": 768, "method": KNN_METHOD},
            "image_caption": {"type": "text", "analyzer": "nori_analyzer"},
            "image_embedding": {"type": "knn_vector", "dimension": 768, "method": KNN_METHOD},
            "category": {"type": "keyword"},
            "sub_category": {"type": "keyword"},
            "district": {"type": "keyword"},
            "source": {"type": "keyword"},
            "lat": {"type": "float"},
            "lng": {"type": "float"},
        }
    },
}

# ── 인덱스 2: place_reviews ──
PLACE_REVIEWS_MAPPING = {
    "settings": NORI_SETTINGS,
    "mappings": {
        "properties": {
            "review_id": {"type": "keyword"},
            "place_id": {"type": "keyword"},
            "place_name": {"type": "text", "analyzer": "nori_analyzer"},
            "summary_text": {"type": "text", "analyzer": "nori_analyzer"},
            "embedding": {"type": "knn_vector", "dimension": 768, "method": KNN_METHOD},
            "keywords": {"type": "keyword"},
            "stars": {"type": "float"},
            "source": {"type": "keyword"},
            "category": {"type": "keyword"},
            "district": {"type": "keyword"},
            "analyzed_at": {"type": "date"},
        }
    },
}

# ── 인덱스 3: events_vector ──
EVENTS_VECTOR_MAPPING = {
    "settings": NORI_SETTINGS,
    "mappings": {
        "properties": {
            "event_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "nori_analyzer"},
            "description": {"type": "text", "analyzer": "nori_analyzer"},
            "embedding": {"type": "knn_vector", "dimension": 768, "method": KNN_METHOD},
            "category": {"type": "keyword"},
            "district": {"type": "keyword"},
            "date_start": {"type": "date"},
            "date_end": {"type": "date"},
            "source": {"type": "keyword"},
        }
    },
}

INDICES = {
    "places_vector": PLACES_VECTOR_MAPPING,
    "place_reviews": PLACE_REVIEWS_MAPPING,
    "events_vector": EVENTS_VECTOR_MAPPING,
}


async def init_indices():
    client = AsyncOpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        use_ssl=False,
        verify_certs=False,
    )

    for index_name, mapping in INDICES.items():
        exists = await client.indices.exists(index=index_name)
        if exists:
            print(f"  [SKIP] {index_name} already exists")
            continue
        await client.indices.create(index=index_name, body=mapping)
        print(f"  [OK]   {index_name} created")

    await client.close()
    print("\nOpenSearch 인덱스 초기화 완료 (3개 인덱스, Gemini 768d, nori 분석기)")


if __name__ == "__main__":
    asyncio.run(init_indices())
