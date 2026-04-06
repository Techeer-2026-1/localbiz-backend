# AGENTS.md

AI 에이전트(Claude Code, Cursor, Copilot)가 이 레포에서 작업할 때 따라야 할 규칙.

## 해도 됨

- `src/` 내 Python 파일 읽기/수정
- `scripts/` 내 ETL 스크립트 읽기/수정
- `pytest` 실행
- `ruff check`, `ruff format` 실행
- `docker-compose up/down/ps` 실행
- `git add`, `git commit` (프리커밋 훅 통과 후)
- OpenSearch/PostgreSQL 로컬 인스턴스 쿼리 (읽기)

## 절대 안 됨

- `.env` 파일 읽기/수정/커밋 (API 키 포함)
- `git push --force`, `git reset --hard`
- DB 데이터 삭제 (`DROP TABLE`, `DELETE FROM` without WHERE)
- `docker-compose down -v` (볼륨 삭제)
- `requirements.txt`에 새 패키지 추가 시 사전 확인 없이 진행
- 프리커밋 훅 우회 (`--no-verify`)
- 외부 API 키를 코드에 하드코딩

## 코드 규칙

- Python: ruff 포맷 (line-length 120, Python 3.11 target)
- 임포트 순서: stdlib → third-party → local (`backend.src.`)
- 비동기 함수: `async def` + `await` (sync 래퍼 금지)
- 타입 힌트: `Optional[str]` 사용 (Python 3.9 호환, `str | None` 금지)
- 임베딩: `gemini-embedding-001` (768d) 통일. OpenAI 임베딩 사용 금지
- OpenSearch 인덱스명: `places_vector`, `place_reviews`, `events_vector`
- DB 쿼리: 파라미터 바인딩 필수 (`$1`, `$2`). f-string SQL 금지

## 커밋 규칙

- 프리커밋 훅이 ruff check + ruff format을 자동 실행
- 훅 실패 시 자동 수정된 파일을 다시 stage 후 커밋
- 커밋 메시지: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` 접두사

## 새 파일 생성 시

- 새 그래프 노드: `src/graph/` 에 `*_node.py` → `real_builder.py`에 등록 → `intent_router_logic.py`에 매핑
- 새 도구: `src/tools/` 에 파일 → `search_agent.py` 또는 `action_agent.py`의 tools 리스트에 등록
- 새 ETL: `scripts/` 에 파일. `embed_utils.py`의 `embed_texts()` 사용. argparse + `--dry-run` 필수
