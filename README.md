# localbiz-backend

LocalBiz Intelligence 백엔드 — FastAPI + LangGraph 에이전트 + 비정형 데이터 ETL.

## 초기 세팅 가이드

### 1. 사전 요구사항

- Python 3.11+
- Git

> Docker 불필요 — PostgreSQL(Cloud SQL)과 OpenSearch(GCE)가 이미 공동 서버에 올라가 있습니다.

### 2. 클론 & 환경변수

```bash
git clone https://github.com/Techeer-2026-1/localbiz-backend.git
cd localbiz-backend
cp .env.example .env
```

`.env.example`에 DB/OpenSearch 접속 정보는 이미 들어있습니다. **API 키만 채우세요:**

| 변수 | 발급처 | 용도 | 필수 |
|------|--------|------|:----:|
| `GEMINI_LLM_API_KEY` | [Google AI Studio](https://aistudio.google.com/) | LLM 추론 + 임베딩 | ✅ |
| `GOOGLE_PLACES_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) | 장소 검색/리뷰 | ✅ |
| `NAVER_CLIENT_ID` / `SECRET` | [Naver Developers](https://developers.naver.com/) | 블로그/뉴스 검색 | ✅ |
| `ANTHROPIC_API_KEY` | [Anthropic Console](https://console.anthropic.com/) | 이미지 캡셔닝 | 선택 |
| `SEOUL_API_KEY` | [서울 열린데이터광장](https://data.seoul.go.kr/) | 혼잡도 | 선택 |

### 3. Python 가상환경

```bash
python3.11 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 서버 실행

```bash
python -m uvicorn src.entry:app --host 0.0.0.0 --port 8000 --reload
```

헬스 체크: `curl http://localhost:8000/health`

### 5. 공동 인프라

| 서비스 | 호스트 | 용도 |
|--------|--------|------|
| Cloud SQL (PostgreSQL+PostGIS) | 34.47.71.231:5432 | 정형 데이터 (266만건 places, 7천건 events) |
| OpenSearch 2.17 (GCE) | 34.50.28.16:9200 | 벡터 검색 (nori 한국어 분석기, 768d) |
| OpenSearch Dashboards | 34.50.28.16:5601 | 데이터 조회 UI |

### 6. 비정형 데이터 ETL

```bash
# 리뷰 분석 (Naver Blog → LLM 6개 지표 채점 → place_analysis)
PYTHONPATH=.. python scripts/batch_review_analysis.py --batch --naver-only --category 음식점 --limit 20

# 리뷰 → OpenSearch 임베딩
PYTHONPATH=.. python scripts/load_place_reviews.py

# 가격 수집 (Naver Blog → 정규식 추출 → raw_data)
PYTHONPATH=.. python scripts/collect_price_data.py --category 음식점 --limit 30

# 장소 → OpenSearch 임베딩
PYTHONPATH=.. python scripts/load_places_vector.py --limit 100

# 행사 → OpenSearch 임베딩
PYTHONPATH=.. python scripts/load_events_vector.py
```

## 프로젝트 구조

```
backend/
├── src/
│   ├── entry.py              # FastAPI 앱 진입점
│   ├── config.py             # Pydantic Settings (.env 로드)
│   ├── websocket.py          # WebSocket 핸들러 + text_stream
│   ├── graph/                # LangGraph 에이전트 (9 노드, 12+1 intent)
│   ├── tools/                # ReAct 에이전트 도구
│   ├── external/             # 외부 API 래퍼
│   ├── db/                   # PostgreSQL, OpenSearch
│   ├── models/               # Pydantic 블록 모델 (16종)
│   └── api/                  # REST 라우터
├── scripts/                  # ETL 스크립트 + DB 초기화
├── AGENTS.md                 # AI 에이전트 지침서
├── pyproject.toml            # ruff 린터 설정
├── .pre-commit-config.yaml   # 프리커밋 훅
└── .env.example              # 환경변수 템플릿
```

## 개발 규칙

- **린터:** `ruff check .` + `ruff format .` (커밋 시 프리커밋 훅 자동 실행)
- **브랜치:** `feat/`, `fix/`, `docs/` 접두사. main 직접 커밋 금지
- **커밋:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` 접두사
- **AI 에이전트:** `AGENTS.md` 규칙 준수

## 관련 레포

| 레포 | 설명 |
|------|------|
| [Local-Inteligence-Seoul](https://github.com/Techeer-2026-1/Local-Inteligence-Seoul) | 프로젝트 메인 |
| [localbiz-frontend](https://github.com/Techeer-2026-1/localbiz-frontend) | Next.js 프론트엔드 |
| [localbiz-etl](https://github.com/Techeer-2026-1/localbiz-etl) | 정형 데이터 ETL (CSV → PostgreSQL) |
