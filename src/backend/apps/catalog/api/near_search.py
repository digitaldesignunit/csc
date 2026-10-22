"""
Near search (decisions 8.170, 8.173): the pieces near a point, nearest first,
with the distance in metres.

The point is a latitude and a longitude; the layer says which stored point of
a piece is measured (``geo_current``, the location of the current version, or
``geo_origin``, the location of its origin building, see ``apps.catalog.geo``);
the radius in kilometres is optional (without it every piece that has a point
on the layer, nearest first). A piece without a point on the layer drops out
while a near search is set.

``$geoNear`` has to be the first stage of a pipeline, so the stage takes the
filters on the identity (visibility included) as its ``query`` and replaces
the plain ``$match`` there; the filters on the current snapshot follow after
the join, as before.
"""

import math
from typing import Any, Dict, List, Literal, Optional, Tuple

NearLayer = Literal['current', 'origin']
# (latitude, longitude, layer, radius in km or None)
Near = Tuple[float, float, str, Optional[float]]
LAYER_FIELDS = {'current': 'geo_current', 'origin': 'geo_origin'}
DEFAULT_LAYER = 'current'
DISTANCE_FIELD = 'distance_m'


class NearError(ValueError):
    """A near parameter that cannot be used; the message is for the caller."""


def _finite(value: Optional[float]) -> bool:
    return value is not None and math.isfinite(value)


def parse_near(lat: Optional[float], lon: Optional[float],
               layer: Optional[str], radius_km: Optional[float]
               ) -> Dict[str, Any]:
    """The near query parameters -> the ``CatalogFilters`` fields (empty
    while none is given). Raises ``NearError`` for a half point, a coordinate
    off the globe, a radius that is not above 0, or a layer or radius without
    a point."""
    if lat is None and lon is None:
        if layer is not None or radius_km is not None:
            raise NearError('near_layer and radius_km need near_lat and '
                            'near_lon')
        return {}
    if lat is None or lon is None:
        raise NearError('near_lat and near_lon go together: give both or '
                        'neither')
    if not _finite(lat) or not -90 <= lat <= 90:
        raise NearError('near_lat is a latitude from -90 to 90')
    if not _finite(lon) or not -180 <= lon <= 180:
        raise NearError('near_lon is a longitude from -180 to 180')
    if layer is not None and layer not in LAYER_FIELDS:
        raise NearError('near_layer is current or origin')
    if radius_km is not None and (not _finite(radius_km) or radius_km <= 0):
        raise NearError('radius_km is a distance in km above 0')
    return {'near_lat': lat, 'near_lon': lon,
            'near_layer': layer or DEFAULT_LAYER, 'radius_km': radius_km}


def near_stage(lat: float, lon: float, layer: str,
               radius_km: Optional[float], query: Dict[str, Any]
               ) -> Dict[str, Any]:
    """The ``$geoNear`` stage: the pieces with a point on ``layer``, nearest
    first, each with ``distance_m``; ``query`` is the filter on the identity."""
    stage: Dict[str, Any] = {
        'near': {'type': 'Point', 'coordinates': [lon, lat]},
        'distanceField': DISTANCE_FIELD,
        'spherical': True,
        # two 2dsphere indexes: the stage has to say which one it uses
        'key': LAYER_FIELDS[layer],
        'query': query,
    }
    if radius_km is not None:
        stage['maxDistance'] = radius_km * 1000.0
    return {'$geoNear': stage}


def first_stages(identity_match: Dict[str, Any], near: Optional[Near]
                 ) -> List[Dict[str, Any]]:
    """The opening stage of every list, count and stats pipeline: the plain
    ``$match`` on the identities, or the ``$geoNear`` that carries it."""
    if near is None:
        return [{'$match': identity_match}]
    return [near_stage(*near, identity_match)]


def distance_sort(order: int) -> Dict[str, int]:
    """The ``$sort`` of ``distance``; ties by catalog number, then by id, so a
    page boundary never repeats or skips a piece (606 pieces share one
    point)."""
    return {DISTANCE_FIELD: order, 'catalog_number': 1, '_id': 1}
