from fastapi import APIRouter

from src.api import analytics, auth

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(analytics.router)


@api_router.get("/health", tags=["health"])
def api_health():
    return {"status": "ok"}
