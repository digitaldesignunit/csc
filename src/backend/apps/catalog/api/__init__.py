from fastapi import APIRouter
from .auth import router as auth_router
from .health import router as health_router
from .utility import router as utility_router
from .ghinterface import router as ghinterface_router
from .idtransmission import router as idtransmission_router
from .identity_workflows import router as identity_workflows_router
from .identities import router as identities_router
from .exports import router as exports_router
from .snapshot_lifecycle import router as snapshot_lifecycle_router
from .identity_lifecycle import router as identity_lifecycle_router
from .snapshots import router as snapshots_router
from .users import router as users_router
from .datasets import router as datasets_router
from .invitations import router as invitations_router
from .identity_edit import router as identity_edit_router
from .materials import router as materials_router
from .change_log import router as change_log_router
from .geometry_remote import router as geometry_remote_router
from .evidence import router as evidence_router
from .evidence_lifecycle import router as evidence_lifecycle_router
from .evidence_attachments import router as evidence_attachments_router
from .actors import router as actors_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix='/auth', tags=['auth'])
api_router.include_router(health_router, tags=['health'])
api_router.include_router(utility_router, tags=['utility'])
api_router.include_router(ghinterface_router, tags=['ghinterface'])
api_router.include_router(idtransmission_router, tags=['idtransmission'])
api_router.include_router(identity_workflows_router, tags=['identities'])
api_router.include_router(identity_edit_router, tags=['identities'])
api_router.include_router(change_log_router, tags=['identities'])
api_router.include_router(materials_router, tags=['materials'])
api_router.include_router(geometry_remote_router, tags=['geometry runner'])
# evidence: before the identities router, which no longer owns
# /identities/{id}/evidence; static /evidence/* routes come first in each
api_router.include_router(evidence_router, tags=['evidence'])
api_router.include_router(evidence_attachments_router, tags=['evidence'])
api_router.include_router(evidence_lifecycle_router, tags=['evidence'])
api_router.include_router(actors_router, tags=['evidence'])
api_router.include_router(identities_router, tags=['identities'])
api_router.include_router(exports_router, tags=['exports'])
# before the snapshots router: /snapshots/{sid} must not catch the
# lifecycle verbs
api_router.include_router(snapshot_lifecycle_router, tags=['snapshots'])
api_router.include_router(identity_lifecycle_router, tags=['identities'])
api_router.include_router(snapshots_router, tags=['snapshots'])
api_router.include_router(users_router, tags=['users'])
api_router.include_router(datasets_router, tags=['datasets'])
api_router.include_router(invitations_router, tags=['invitations'])
