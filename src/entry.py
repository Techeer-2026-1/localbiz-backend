"""FastAPI 앱 진입점"""

import logging

from dotenv import load_dotenv

load_dotenv("backend/.env")
load_dotenv(".env")
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.analysis import router as analysis_router
from backend.src.api.chats import router as chats_router
from backend.src.api.favorites import router as favorites_router
from backend.src.api.poc import router as poc_router
from backend.src.config import get_settings
from backend.src.db.postgres import close_pool, get_pool
from backend.src.websocket import chat_websocket

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await get_pool()
        logger.info("PostgreSQL 연결 성공")
    except Exception as e:
        logger.warning(f"PostgreSQL 연결 실패 — DB 기능 제한됨: {e}")

    from backend.src.graph.real_builder import build_graph

    await build_graph()
    logger.info("LangGraph 빌드 완료")

    yield

    try:
        await close_pool()
    except Exception:
        pass


app = FastAPI(
    title="LocalBiz Intelligence API",
    description="서울 로컬 생활 정보 AI 어시스턴트",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(chats_router)
app.include_router(favorites_router)
app.include_router(poc_router)
app.include_router(analysis_router)


# WebSocket 엔드포인트
@app.websocket("/ws/chat/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: str):
    await chat_websocket(websocket, chat_id)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.src.entry:app", host="0.0.0.0", port=8000)
