#!/usr/bin/env python3.13
"""Snapshot integrity hash, shared by the API routes and the geometry runner."""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import hashlib
import json
from typing import Any, Dict


def compute_snapshot_etag(snapshot_doc: Dict[str, Any]) -> str:
    """sha256 over canonical snapshot JSON, excluding etag and lastmodified."""
    payload = {
        k: v for k, v in snapshot_doc.items()
        if k not in ('etag', 'lastmodified')
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()
