#!/usr/bin/env python3.13
"""
The two stored points of the near search (decision 8.170).

``geo_current`` is the current version's ``location`` and ``geo_origin`` the
location of the origin building (``origin.place.location``), each as a GeoJSON
point in ``component_identities`` with a ``2dsphere`` index. They are derived,
like ``properties``: never authored, never logged, never sent to a client, and
absent (not null, not ``[0, 0]``) while the piece has no such location.

GeoJSON orders the pair [lon, lat]; ``GeoLocation`` is {lat, lon}.

The truth stays in the documents: ``geo_origin`` follows the origin of the
identity and is written with it; ``geo_current`` follows
``current_snapshot_id`` and the location of that snapshot and is set wherever
either changes (``set_geo_current``). ``scripts/db_maintenance/
backfill_geo_points.py`` fills the fields of records written before them and
reports any that disagree with their documents.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import math
from typing import Any, Dict, Mapping, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pymongo.errors import ConnectionFailure, PyMongoError

# LOCAL IMPORTS ---------------------------------------------------------------
from logging_setup import get_logger

log = get_logger(__name__)

GEO_CURRENT = 'geo_current'
GEO_ORIGIN = 'geo_origin'
GEO_FIELDS = (GEO_CURRENT, GEO_ORIGIN)


def point_of(location: Optional[Mapping[str, Any]]
             ) -> Optional[Dict[str, Any]]:
    """A ``{lat, lon}`` location -> a GeoJSON point, or None when there is no
    usable one. A coordinate outside the globe would make the write fail (the
    index refuses it), so such a value never becomes a point."""
    if not isinstance(location, Mapping):
        return None
    lat, lon = location.get('lat'), location.get('lon')
    for value in (lat, lon):
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(value):
            return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {'type': 'Point', 'coordinates': [float(lon), float(lat)]}


def origin_point(identity: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The point of ``origin.place.location`` of an identity document."""
    place = (identity.get('origin') or {}).get('place') or {}
    return point_of(place.get('location'))


def with_geo_origin(identity: Dict[str, Any],
                    previous: Optional[Mapping[str, Any]] = None
                    ) -> Dict[str, Any]:
    """The identity document with ``geo_origin`` set from its origin (or
    removed), and ``geo_current`` carried over from ``previous`` (the stored
    document it replaces): the model dump a write starts from drops both."""
    out = {k: v for k, v in identity.items() if k not in GEO_FIELDS}
    point = origin_point(out)
    if point is not None:
        out[GEO_ORIGIN] = point
    current = (previous or identity).get(GEO_CURRENT)
    if current is not None:
        out[GEO_CURRENT] = current
    return out


async def set_geo_current(identities, snapshots, identity_id: str,
                          snapshot_id: Optional[str]) -> None:
    """Point ``geo_current`` of an identity at the location of the snapshot
    that is now its current one (None: no current snapshot, so no point). A
    failure of the write is logged, not raised: the record write that led
    here stands, and the backfill script finds a field left behind."""
    point = None
    try:
        if snapshot_id:
            snapshot = await snapshots.find_one(
                {'_id': snapshot_id}, {'location': 1})
            point = point_of((snapshot or {}).get('location'))
        update = ({'$set': {GEO_CURRENT: point}} if point is not None
                  else {'$unset': {GEO_CURRENT: ''}})
        await identities.update_one({'_id': identity_id}, update)
    except ConnectionFailure:
        raise            # the 503 handler of main_fastapi.py
    except PyMongoError:
        log.exception('geo_current of %s not written', identity_id)


async def refresh_geo_current(app, identity_id: str) -> None:
    """``set_geo_current`` for whatever the identity's current snapshot is."""
    identities = app.mongodb_component_identities
    identity = await identities.find_one(
        {'_id': identity_id}, {'current_snapshot_id': 1})
    if identity is None:
        return
    await set_geo_current(identities, app.mongodb_component_snapshots,
                          identity_id, identity.get('current_snapshot_id'))
