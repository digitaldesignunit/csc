"""
The Grasshopper interface routes (`/ghinterface/*`): what `CSC_Update` and the
component reference read from the GitHub release this backend belongs to.

* `sources.py`: version, reference, ZIP, component sources and XML
* `library.py`: the `csc_gh` library of the client
* `userobjects.py`: the user objects
* `github.py`: the GitHub client, its lookups and caches (no routes)
"""

from fastapi import APIRouter

from .library import router as library_router
from .sources import router as sources_router
from .userobjects import router as userobjects_router

router = APIRouter()
router.include_router(sources_router)
router.include_router(library_router)
router.include_router(userobjects_router)
