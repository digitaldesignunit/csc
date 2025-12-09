from fastapi import APIRouter
from .auth import router as auth_router
from .components import router as components_router
from .designs import router as designs_router
from .health import router as health_router
from .utility import router as utility_router
from .reserve import router as reserve_router
from .downloads import router as downloads_router
from .ghupdates import router as ghupdates_router
from .archive import router as archive_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix='/auth', tags=['auth'])
api_router.include_router(components_router, tags=['catalogue'])
api_router.include_router(designs_router, tags=['designs'])
api_router.include_router(health_router, tags=['health'])
api_router.include_router(utility_router, tags=['utility'])
api_router.include_router(reserve_router, tags=['reserve'])
api_router.include_router(downloads_router, tags=['downloads'])
api_router.include_router(ghupdates_router, tags=['ghupdates'])
api_router.include_router(archive_router, tags=['archive'])
