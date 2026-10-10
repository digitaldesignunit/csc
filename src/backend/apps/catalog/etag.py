#!/usr/bin/env python3.13
"""Snapshot integrity hash, shared by the API routes and the geometry runner."""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import hashlib
import json
from typing import Any, Dict


def compute_snapshot_etag(snapshot_doc: Dict[str, Any]) -> str:
    """sha256 over canonical snapshot JSON, excluding etag, lastmodified and
    the ``derivation_due`` marker (it comes and goes with the cron's checks and
    is no content)."""
    payload = {
        k: v for k, v in snapshot_doc.items()
        if k not in ('etag', 'lastmodified', 'derivation_due')
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()
