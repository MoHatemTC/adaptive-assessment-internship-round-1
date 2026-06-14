"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.admin import router as admin_router
from app.core.checkpointer import setup_checkpointer
from app.core.database import check_db_connection
from app.core.limiter import limiter
from app.core.llm import test_llm_connection
from app.core.middleware import setup_middleware
from app.features.code.e2b_health import test_e2b_connection
from app.features.registry import mount_feature_routers

_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost",
    "http://127.0.0.1",
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await setup_checkpointer()
    yield


app = FastAPI(title="Masaar API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
setup_middleware(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mount_feature_routers(app)
app.include_router(admin_router, prefix="/api/v1", tags=["admin"])


@app.get("/health")
async def health() -> dict[str, str | bool]:
    db_ok = await check_db_connection()
    llm_ok = await test_llm_connection()
    e2b_ok = test_e2b_connection()
    healthy = db_ok and llm_ok
    return {
        "status": "ok" if healthy else "degraded",
        "db": db_ok,
        "llm": llm_ok,
        "e2b": e2b_ok,
    }


@app.get("/api/v1/health")
async def health_v1() -> dict[str, str | bool]:
    return await health()
