"""
CSV → PostgreSQL(places) + OpenSearch(places_vector) 동시 적재 ETL

실행:
    python scripts/etl_places.py --file data/소상공인_상권.csv --category restaurant
"""
import asyncio
import argparse
import uuid
import json
import asyncpg
import pandas as pd
from opensearchpy import AsyncOpenSearch, helpers
from openai import AsyncOpenAI

# ============================================================
# 설정
# ============================================================
DATABASE_URL = "postgresql://localbiz:localbiz@localhost:5432/localbiz"
OPENSEARCH_HOST = "localhost"
OPENAI_API_KEY = ""  # .env에서 읽거나 인자로 전달

CATEGORY_MAP = {
    "한식": "restaurant", "중식": "restaurant", "일식": "restaurant",
    "양식": "restaurant", "분식": "restaurant", "카페": "cafe",
    "제과점": "cafe", "헬스": "gym", "피트니스": "gym",
    "미용실": "beauty", "네일": "beauty", "공원": "park",
    "도서관": "library", "약국": "pharmacy",
}

DISTRICT_MAP = {
    "강남구": "gangnam", "강동구": "gangdong", "강북구": "gangbuk",
    "강서구": "gangseo", "관악구": "gwanak", "광진구": "gwangjin",
    "구로구": "guro", "금천구": "geumcheon", "노원구": "nowon",
    "도봉구": "dobong", "동대문구": "dongdaemun", "동작구": "dongjak",
    "마포구": "mapo", "서대문구": "seodaemun", "서초구": "seocho",
    "성동구": "seongdong", "성북구": "seongbuk", "송파구": "songpa",
    "양천구": "yangcheon", "영등포구": "yeongdeungpo", "용산구": "yongsan",
    "은평구": "eunpyeong", "종로구": "jongno", "중구": "jung",
    "중랑구": "jungnang",
}

CORE_COLUMNS = {"place_id", "name", "category", "sub_category", "district",
                "address", "lat", "lng", "phone", "source"}


def make_page_content(row: dict) -> str:
    """f-string 직렬화 — LLM 호출 없이 비용 0원"""
    name = row.get("name", "")
    district = row.get("district", "")
    category = row.get("category", "")
    sub = row.get("sub_category", "")
    address = row.get("address", "")
    return (
        f"{name}은(는) {district}에 위치한 {category} ({sub})입니다. "
        f"주소: {address}."
    )


async def embed_batch(texts: list[str], client: AsyncOpenAI) -> list[list[float]]:
    results = []
    for i in range(0, len(texts), 1000):
        batch = texts[i:i + 1000]
        resp = await client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
        )
        results.extend([item.embedding for item in resp.data])
        print(f"  임베딩 {min(i + 1000, len(texts))}/{len(texts)}")
    return results


async def run_etl(csv_path: str, default_category: str, source: str):
    print(f"\n[ETL] {csv_path} → places 테이블 + places_vector 인덱스")

    # ── 1. Extract ──
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False)
    print(f"  로드: {len(df)}행")

    # 서울 필터링
    if "시도" in df.columns:
        df = df[df["시도"].str.contains("서울", na=False)]
        print(f"  서울 필터: {len(df)}행")

    df = df.dropna(subset=["경도", "위도"] if "경도" in df.columns else [])
    print(f"  좌표 결측 제거: {len(df)}행")

    # ── 2. Transform ──
    records = []
    for _, row in df.iterrows():
        raw = row.to_dict()

        # 컬럼명 표준화
        name = raw.get("상호명") or raw.get("사업장명") or raw.get("name", "")
        lat  = float(raw.get("위도") or raw.get("lat", 0))
        lng  = float(raw.get("경도") or raw.get("lng", 0))
        addr = raw.get("도로명주소") or raw.get("지번주소") or raw.get("address", "")
        dist_raw = raw.get("시군구") or raw.get("자치구") or ""
        dist_code = DISTRICT_MAP.get(dist_raw, "")

        업종 = raw.get("업태명") or raw.get("업종명") or raw.get("category", "")
        category = CATEGORY_MAP.get(업종, default_category)

        place_id = str(uuid.uuid4())

        # Core 필드 분리 → raw_data JSONB에서 제외
        core = {
            "place_id": place_id,
            "name": name,
            "category": category,
            "sub_category": 업종,
            "district": dist_code,
            "address": addr,
            "lat": lat,
            "lng": lng,
            "phone": raw.get("전화번호", ""),
            "source": source,
        }
        # 나머지 전체를 raw_data JSONB로
        raw_data = {k: v for k, v in raw.items()
                    if k not in ("위도", "경도", "상호명", "사업장명", "도로명주소",
                                 "지번주소", "전화번호", "시군구", "자치구", "시도")}

        records.append({**core, "raw_data": raw_data,
                         "page_content": make_page_content(core)})

    print(f"  변환 완료: {len(records)}건")

    # ── 3. Load — PostgreSQL Bulk Insert ──
    pool = await asyncpg.create_pool(DATABASE_URL)
    BATCH = 500
    pg_count = 0
    async with pool.acquire() as conn:
        for i in range(0, len(records), BATCH):
            batch = records[i:i + BATCH]
            values = [
                (
                    r["place_id"], r["name"], r["category"], r.get("sub_category"),
                    r.get("district"), r.get("address"),
                    r.get("lng"), r.get("lat"),  # ST_MakePoint(lng, lat)
                    r.get("phone"), json.dumps(r["raw_data"], ensure_ascii=False),
                    r["source"],
                )
                for r in batch
            ]
            await conn.executemany(
                """
                INSERT INTO places (place_id, name, category, sub_category, district, address,
                    geom, phone, raw_data, source)
                VALUES ($1, $2, $3, $4, $5, $6,
                    ST_SetSRID(ST_MakePoint($7, $8), 4326), $9, $10::jsonb, $11)
                ON CONFLICT DO NOTHING
                """,
                values,
            )
            pg_count += len(batch)
            print(f"  PostgreSQL INSERT {pg_count}/{len(records)}")

    await pool.close()
    print(f"  PostgreSQL 완료: {pg_count}건")

    # ── 4. Load — OpenSearch Bulk Index + 임베딩 ──
    if not OPENAI_API_KEY:
        print("  [SKIP] OPENAI_API_KEY 미설정 → OpenSearch 인덱싱 건너뜀")
        return

    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    texts = [r["page_content"] for r in records]
    embeddings = await embed_batch(texts, oai)

    os_client = AsyncOpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        use_ssl=False, verify_certs=False,
    )

    actions = [
        {
            "_index": "places_vector",
            "_id": r["place_id"],
            "_source": {
                "place_id": r["place_id"],
                "page_content": r["page_content"],
                "embedding": emb,
                "metadata": {
                    "name": r["name"],
                    "category": r["category"],
                    "district": r.get("district", ""),
                },
            },
        }
        for r, emb in zip(records, embeddings)
    ]

    ok, errors = await helpers.async_bulk(os_client, actions, chunk_size=500)
    await os_client.close()
    print(f"  OpenSearch Bulk Index: {ok}건 성공, {len(errors)}건 실패")
    print("\n[ETL 완료]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--category", default="restaurant")
    parser.add_argument("--source", default="csv")
    parser.add_argument("--openai-key", default="")
    args = parser.parse_args()

    if args.openai_key:
        OPENAI_API_KEY = args.openai_key

    asyncio.run(run_etl(args.file, args.category, args.source))
