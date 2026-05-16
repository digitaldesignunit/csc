#!/usr/bin/env python3.9
"""Routes for the v0.5 `component_snapshots` collection.

Placeholder for M4.2-M4.5 endpoints (component creation = identity + v0,
get-by-snapshot-id, virtual snapshot propose/create, PATCH current snapshot).
The router is registered in `__init__.py` so adding routes here is a one-step
operation; no further wiring needed.
"""

from fastapi import APIRouter

router = APIRouter()
