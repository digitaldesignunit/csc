from fastapi import APIRouter
from .auth import router as auth_router
from .components import router as components_router
from .health import router as health_router
from .utility import router as utility_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(components_router, tags=["catalogue"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(utility_router, tags=["utility"])
