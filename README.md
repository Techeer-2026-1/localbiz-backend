# localbiz-backend

LocalBiz Intelligence 백엔드 — FastAPI + LangGraph 에이전트 + 비정형 데이터 ETL.

## 초기 세팅 가이드

### 1. 사전 요구사항

- Python 3.11+
- Docker & Docker Compose
- Git

### 2. 클론 & 환경변수

```bash
git clone https://github.com/Techeer-2026-1/localbiz-backend.git
cd localbiz-backend
cp .env.example .env
```

`.env` 파일에 아래 API 키를 채워넣으세요:

| 변수 | 발급처 | 용도 |
|------|--------|------|
| `GEMINI_LLM_API_KEY` | [Google AI Studio](https://aistudio.google.com/) | LLM 추론 + 임베딩 |
| `GOOGLE_PLACES_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) | 장소 검색/리뷰/이미지 |
| `NAVER_CLIENT_ID` / `SECRET` | [Naver Developers](https://developers.naver.com/) | 블로그/뉴스 검색 |
| `ANTHROPIC_API_KEY` | [Anthropic Console](https://console.anthropic.com/) | 이미지 캡셔닝 (Phase 2, 선택) |
| `SEOUL_API_KEY` | [서울 열린데이터광장](https://data.seoul.go.kr/) | 혼잡도 (Phase 2, 선택) |

### 3. 인프라 실행

```bash
docker-compose up -d
```

3개 서비스가 올라갑니다:

| 서비스 | 포트 | 설명 |
|--------|------|------|
| PostgreSQL + PostGIS | 5434 | 정형 데이터 |
| OpenSearch 2.17 | 9200 | 벡터 검색 (nori 한국어 분석기) |
| Redis 7.4 | 6379 | API 응답 캐시 |

> 최초 실행 시 `init_db.sql`이 자동 적용됩니다.

### 4. Python 가상환경

```bash
python3.11 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install ruff pre-commit "opensearch-py[async]"
pre-commit install
```

### 5. OpenSearch 인덱스 생성

```bash
# nori 분석기 플러그인 설치 (최초 1회)
docker exec localbiz-opensearch bin/opensearch-plugin install analysis-nori
docker restart localbiz-opensearch

# 인덱스 3개 생성
PYTHONPATH=.. python scripts/init_opensearch.py
```

### 6. 서버 실행

```bash
# 프로젝트 루트(backend 상위)에서 실행
cd ..
PYTHONPATH=. ./backend/venv/bin/python -m uvicorn backend.src.entry:app --host 0.0.0.0 --port 8000 --reload
```

또는 backend 디렉토리에서:

```bash
python src/entry.py
```

헬스 체크: `curl http://localhost:8000/health`

### 7. 비정형 데이터 ETL (선택)

```bash
# 장소 → OpenSearch 임베딩 적재
PYTHONPATH=.. python scripts/load_places_vector.py --dry-run   # 테스트
PYTHONPATH=.. python scripts/load_places_vector.py             # 전체

# 리뷰 LLM 분석 (google_place_id 있는 장소)
PYTHONPATH=.. python scripts/batch_review_analysis.py --batch --limit 10

# 리뷰 → OpenSearch 임베딩
PYTHONPATH=.. python scripts/load_place_reviews.py

# 가격 수집 (Naver Blog)
PYTHONPATH=.. python scripts/collect_price_data.py --category cafe --limit 10

# 행사 → OpenSearch 임베딩
PYTHONPATH=.. python scripts/load_events_vector.py
```

## 프로젝트 구조

```
backend/
├── src/
│   ├── entry.py              # FastAPI 앱 진입점
│   ├── config.py             # Pydantic Settings
│   ├── websocket.py          # WebSocket 핸들러
│   ├── graph/                # LangGraph 에이전트 (9 노드)
│   ├── tools/                # ReAct 에이전트 도구
│   ├── external/             # 외부 API 래퍼
│   ├── db/                   # PostgreSQL, OpenSearch, Redis
│   ├── models/               # Pydantic 블록 모델
│   └── api/                  # REST 라우터
├── scripts/
│   ├── init_db.sql           # PostgreSQL DDL
│   ├── init_opensearch.py    # OpenSearch 인덱스 생성
│   ├── embed_utils.py        # Gemini 임베딩 유틸
│   ├── load_places_vector.py # 장소 임베딩 적재
│   ├── batch_review_analysis.py  # 리뷰 LLM 분석
│   ├── load_place_reviews.py # 리뷰 임베딩 적재
│   ├── collect_price_data.py # 가격 데이터 수집
│   ├── load_events_vector.py # 행사 임베딩 적재
│   └── load_image_captions.py # 이미지 캡셔닝 (Phase 2)
├── AGENTS.md                 # AI 에이전트 지침서
├── pyproject.toml            # ruff 린터 설정
├── .pre-commit-config.yaml   # 프리커밋 훅
├── docker-compose.yml        # 로컬 인프라
└── .env.example              # 환경변수 템플릿
```

## 개발 규칙

- **린터:** `ruff check .` + `ruff format .` (커밋 시 자동 실행)
- **브랜치:** `feat/`, `fix/`, `docs/` 접두사. main 직접 커밋 금지
- **커밋:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` 접두사
- **AI 에이전트:** `AGENTS.md` 규칙 준수

## 관련 레포

| 레포 | 설명 |
|------|------|
| [Local-Inteligence-Seoul](https://github.com/Techeer-2026-1/Local-Inteligence-Seoul) | 프로젝트 메인 |
| [localbiz-frontend](https://github.com/Techeer-2026-1/localbiz-frontend) | Next.js 프론트엔드 |
| [localbiz-etl](https://github.com/Techeer-2026-1/localbiz-etl) | 정형 데이터 ETL (CSV → PostgreSQL) |
