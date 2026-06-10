from fastapi import APIRouter
from .auth import router as auth_router
from .designs import router as designs_router
from .health import router as health_router
from .utility import router as utility_router
from .ghinterface import router as ghinterface_router
from .idtransmission import router as idtransmission_router
from .identity_workflows import router as identity_workflows_router
from .identities import router as identities_router
from .snapshots import router as snapshots_router
from .users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix='/auth', tags=['auth'])
api_router.include_router(designs_router, tags=['designs'])
api_router.include_router(health_router, tags=['health'])
api_router.include_router(utility_router, tags=['utility'])
api_router.include_router(ghinterface_router, tags=['ghinterface'])
api_router.include_router(idtransmission_router, tags=['idtransmission'])
api_router.include_router(identity_workflows_router, tags=['identities'])
api_router.include_router(identities_router, tags=['identities'])
api_router.include_router(snapshots_router, tags=['snapshots'])
api_router.include_router(users_router, tags=['users'])
