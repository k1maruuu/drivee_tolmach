from fastapi import APIRouter

from src.api import admin, analytics, auth, reports, schedules, templates

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(analytics.router)
api_router.include_router(templates.router)
api_router.include_router(reports.router)
api_router.include_router(schedules.router)
api_router.include_router(admin.router)


@api_router.get("/health", tags=["health"])
def api_health():
    return {"status": "ok"}
