from fastapi import APIRouter
from app.api.v1.admin import router as admin_router
from app.api.v1.applications import router as applications_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.feed import router as feed_router
from app.api.v1.health import router as health_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.linkedin import router as linkedin_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.profile import router as profile_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.search import router as search_router
from app.api.v1.assignments import router as assignments_router
from app.api.v1.competitions import router as competitions_router
from app.api.v1.events import router as events_router
from app.api.v1.settings import router as settings_router
from app.api.v1.ws import router as ws_router

api_v1_router = APIRouter()

# Mount feature routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(profile_router)
api_v1_router.include_router(linkedin_router)
api_v1_router.include_router(resumes_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(feed_router)
api_v1_router.include_router(onboarding_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(applications_router)
api_v1_router.include_router(search_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(interviews_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(assignments_router)
api_v1_router.include_router(competitions_router)
api_v1_router.include_router(settings_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(ws_router)
