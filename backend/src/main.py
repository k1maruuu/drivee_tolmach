import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import api_router
from src.core.config import settings
from src.db.init_db import init_db
from src.services.report_scheduler import report_scheduler_loop
from src.services.template_service import warm_template_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    warm_template_cache()
    scheduler_task: asyncio.Task | None = None
    if settings.report_scheduler_enabled:
        scheduler_task = asyncio.create_task(report_scheduler_loop())
    try:
        yield
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend MVP for Drivee natural-language to SQL analytics.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": settings.app_name}


app.include_router(api_router, prefix=settings.api_prefix)
