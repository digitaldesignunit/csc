"""
The read-only MCP layer (decision 8.165, 8.168): ten tools that let Claude read
the catalog as the owner of the access token sees it in the web app.

The tools reuse the REST API instead of copying it: each one calls a route
through ``internal_call.rest_get`` as the owner, so visibility (private and
unreviewed datasets for an administrator, withdrawn versions, people's names)
is decided by the same code as the web app. Nothing writes. What a tool adds is
a shorter answer, paging where a list can be long, the link of every record on
the web, and a mark on every record that is not public (``visibility``,
``status``). No answer carries an e-mail address or an account id: keys that
name one are dropped and an address in a text is replaced. There is no tool for
users, invitations or tokens.

``build_mcp`` makes the server for one running application; ``gate`` is the
ASGI app that ``/mcp`` serves (token check, 401 with the resource metadata, 429).
"""

import json
import re
from typing import Annotated, Any, Optional, Tuple

from mcp.server.auth.middleware.auth_context import (
    AuthContextMiddleware,
    get_access_token,
)
from mcp.server.auth.middleware.bearer_auth import (
    BearerAuthBackend,
    RequireAuthMiddleware,
)
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon, ToolAnnotations
from pydantic import AnyHttpUrl, Field
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request

import limiter as lim
from apps.catalog import access_tokens as tk
from apps.catalog.api.near_search import NearError, parse_near
from apps.catalog.vocab import (
    EVIDENCE_METHOD_LABELS,
    EVIDENCE_METHODS,
    ORIGINAL_FUNCTION_LABELS,
    SHAPE_CLASS_LABELS,
)
from apps.catalog.internal_call import InternalError, rest_get
from apps.catalog.models import UserInDB
from apps.catalog.oauth_server import AccessTokenVerifier
from apps.catalog.token_check import REQUEST_ADDRESS, RateLimited
from logging_setup import get_logger

log = get_logger(__name__)

PAGE_MAX = 25
TEXT_MAX = 30000
_EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_DROP_KEYS = {'email', 'etag', 'hashed_password', 'password'}

# the evidence methods as "name (Label)", one source for the tool texts
EVIDENCE_METHOD_TEXT = ', '.join(
    f'{m} ({EVIDENCE_METHOD_LABELS[m]})' for m in EVIDENCE_METHODS)

INSTRUCTIONS = (
    'The Catalog of Second Chances (CSC) is a catalog of reused and '
    'salvaged building components (German: wiederverwendete Bauteile, '
    'Wiederverwendung, Bauteilboerse): concrete walls and beams '
    '(Betonwaende, Traeger), stone, timber and other pieces, each '
    'with its shape, origin, versions and measurements ("evidence"). Use '
    'these tools before a web search when the user looks for such pieces, '
    'for example "Betontraeger mit Bewehrung" or reused beams with '
    'reinforcement (Bewehrung): search_components with the filters below, '
    'and has_evidence=reinforcement_layout for "with reinforcement". '
    'These tools only read. You see what the signed-in owner of this '
    'connection sees on the website. Start with search_components, then '
    'get_component. Every answer carries a web link to give to the user. A '
    'record marked visibility "private" or a status other than "published" '
    'is not public: say so when you quote it. Lengths are in millimetres '
    'unless a unit is given.')

GET_EVIDENCE_TEXT = (
    'Measurements and other evidence about a component. The methods are: '
    + EVIDENCE_METHOD_TEXT + '. A list gives short rows: method, source '
    'tier, when observed, who performed it, summary, status, verification; '
    'a reinforcement_layout row also gives a summary of its bars (count, '
    'basis, specs, diameters, cover, the version it refers to). Filter with '
    'method. Pass evidence_id for one record in full, with its payload (the '
    'bars of a layout).')

# every tool reads, never writes, and never reaches outside the catalog
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True,
                            openWorldHint=False)


# ANSWERS -----------------------------------------------------------------------
def clean(value: Any) -> Any:
    """Drop what names an account or an address, from any answer."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()
                if k not in _DROP_KEYS and k != 'user_id'
                and not k.endswith('_user_id')
                and not k.endswith('_email')}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        return _EMAIL.sub('[address removed]', value)
    return value


def visibility_of(record: dict) -> str:
    """``public`` or ``private`` (visible to the members of its dataset)."""
    return 'public' if record.get('is_public') else 'private'


# the sorts of search_components -> the sort key of the REST list
SEARCH_SORTS = {'catalog_number': 'catalog_number', 'date': 'effective_from',
                'created': 'created', 'volume': 'volume', 'match': 'match',
                'distance': 'distance'}
FIT_MODES = ('about', 'can_hold')
SIMILARITY_BASES = ('radial_signature', 'scalars', 'hks')
CIRCULATION_LABELS = {'in_place': 'In place', 'deinstalled': 'Not in place',
                      'exited': 'Out of circulation'}


def size_text(values) -> str:
    """``[1200, 600.5, 0.0001]`` -> ``'1200,600.5,0.0001'``: plain decimals,
    never an exponent (the list route reads digits and a point only)."""
    return ','.join(f'{float(v):.10f}'.rstrip('0').rstrip('.') or '0'
                    for v in values)


def fit_of(row: dict) -> Optional[dict]:
    """The match of a dimension search in words a reader needs: the largest
    deviation in per cent (about), or the waste in m3 (two significant
    digits) and as a share of the piece's box volume (can_hold)."""
    fit = row.get('fit')
    if not isinstance(fit, dict):
        return None
    if fit.get('mode') == 'about' and fit.get('deviation') is not None:
        return {'mode': 'about',
                'deviation_percent': round(fit['deviation'] * 100, 2)}
    if fit.get('mode') == 'can_hold' and fit.get('waste_mm3') is not None:
        percent = fit.get('waste_percent')
        out = {'mode': 'can_hold',
               'waste_m3': float(f"{fit['waste_mm3'] / 1e9:.2g}")}
        if percent is not None:
            # never 100 unless the waste is all of it: 99.97 reads as 99 (8.169)
            out['waste_percent'] = (round(percent, 1) if percent < 1
                                    else min(99, round(percent)) if percent < 100
                                    else 100)
        if (row.get('quantity') or 1) > 1:
            out['per_piece'] = True     # the size is one piece's of the batch
        return out
    return None


def distance_km(metres: Optional[float]) -> Optional[float]:
    """A distance from the near point in km: two decimals (10 m) up to 100 km,
    one decimal beyond; the unit is in the name of the field."""
    if metres is None:
        return None
    km = metres / 1000
    return round(km, 2) if km < 100 else round(km, 1)


def short_row(row: dict, link: str) -> dict:
    origin = row.get('origin') or {}
    short = clean({
        'id': row.get('_id'), 'name': row.get('name'),
        'catalog_number': row.get('catalog_number'),
        'original_function': row.get('original_function'),
        'material': row.get('material'), 'dataset': row.get('dataset'),
        'shape_class': row.get('shape_class'),
        'bbx_mm': row.get('bbx'), 'version': row.get('version'),
        'status': row.get('status'), 'visibility': visibility_of(row),
        'origin_kind': origin.get('kind'),
        'in_circulation': row.get('exit') is None,
        'web_link': link})
    fit = fit_of(row)
    if fit:
        short['fit'] = fit
    if row.get('distance_m') is not None:
        short['distance_km'] = distance_km(row['distance_m'])
    return short


def geometry_summary(geometry: Optional[dict]) -> dict:
    geometry = geometry or {}
    meshes = geometry.get('meshes') or []
    return {
        'meshes': len(meshes),
        'mesh_vertices': sum(len(m.get('vertices') or []) for m in meshes),
        'mesh_faces': sum(len(m.get('faces') or []) for m in meshes),
        'point_clouds': len(geometry.get('point_clouds') or []),
        'proxies': len(geometry.get('proxies') or []),
        'note': 'Geometry is not sent; open the web link to see it.'}


def layout_bars(record: dict) -> list:
    """The bars of a ``reinforcement_layout`` record, as dicts."""
    bars = (record.get('payload') or {}).get('bars') or []
    return [b for b in bars if isinstance(b, dict)]


def layouts_of_version(rows: list, snapshot_id: Optional[str]) -> dict:
    """The reinforcement of one version, from the published
    ``reinforcement_layout`` evidence that names it in ``position.snapshot_id``
    (decision 7.8: the bars are evidence, not geometry): how many records and
    how many bars, and where to read them."""
    records = [r for r in rows or []
               if isinstance(r, dict)
               and r.get('method') == 'reinforcement_layout'
               and r.get('status') == 'published'
               and (r.get('position') or {}).get('snapshot_id') == snapshot_id]
    return {
        'records': len(records),
        'bars': sum(len(layout_bars(r)) for r in records),
        'note': 'get_evidence with method=reinforcement_layout lists the '
                'layouts of the component; pass an evidence_id for the '
                'bars of one.'}


def layout_summary(record: dict) -> dict:
    """A reinforcement layout in one row: the number of bars, the basis, the
    steel specs, the distinct diameters in mm, the cover range when known and
    the version the bars refer to."""
    bars = layout_bars(record)
    covers = [b['cover_mm'] for b in bars
              if isinstance(b.get('cover_mm'), (int, float))]
    summary = {
        'bars': len(bars),
        'basis': (record.get('payload') or {}).get('basis'),
        'specs': sorted({b['spec'] for b in bars if b.get('spec')}),
        'diameters_mm': sorted({b['diameter_mm'] for b in bars
                                if isinstance(b.get('diameter_mm'),
                                              (int, float))}),
        'version_id': (record.get('position') or {}).get('snapshot_id')}
    if covers:
        summary['cover_mm'] = {'min': min(covers), 'max': max(covers)}
    return summary


def performers(record: dict) -> list:
    """Who did the work: a person's name, else the organization; an actor
    with neither is left out (never ``null``)."""
    names = []
    for actor in record.get('performed_by') or []:
        if isinstance(actor, dict):
            name = actor.get('name') or actor.get('organization')
            if name:
                names.append(name)
    return names


def limited(answer: dict) -> dict:
    """A cap on the size of one answer, said in the answer: the longest list
    is halved until the answer fits."""
    import json

    def size() -> int:
        return len(json.dumps(answer, default=str))

    while size() > TEXT_MAX:
        lists = [(len(v), k) for k, v in answer.items()
                 if isinstance(v, list) and len(v) > 3]
        if not lists:
            break
        _, key = max(lists)
        answer[key] = answer[key][:max(3, len(answer[key]) // 2)]
        answer['truncated'] = ('The answer was cut to fit; ask for a smaller '
                               'page or a narrower search.')
    return answer


# THE SERVER ----------------------------------------------------------------------
# THE FILTERS OF THE SEARCH TOOLS ---------------------------------------------------
# search_components, catalog_overview and similar_components take the same
# filters (decisions 8.169, 8.170, 8.173, 8.174), so they share their
# descriptions and their checks.
QueryArg = Annotated[str, Field(description=(
    'Free text: matches the name (any part), an id prefix or the '
    'catalog number (12 or #12). It does not match materials, '
    'functions or places: use the filters below. Leave empty to '
    'list.'))]
FunctionArg = Annotated[str, Field(description=(
    'Building function, for example IfcBeam, IfcPlate, IfcWall '
    '(exact).'))]
MaterialArg = Annotated[str, Field(description='Material key.')]
DatasetArg = Annotated[str, Field(description=(
    'Dataset id, from list_datasets.'))]
ShapeClassArg = Annotated[str, Field(description=(
    'Shape class, for example planar, linear, compact.'))]
CirculationArg = Annotated[str, Field(description=(
    'active (default: in circulation), in_place, deinstalled, '
    'exited, all.'))]
StatusArg = Annotated[str, Field(description=(
    'Version status: published (default), or any to include '
    'pending and other states you may see.'))]
WithdrawnArg = Annotated[bool, Field(description=(
    'Also withdrawn components, if you may see them.'))]
HasEvidenceArg = Annotated[str, Field(description=(
    'Only components with at least one published, current evidence record '
    'of this method: ' + EVIDENCE_METHOD_TEXT + '. Use reinforcement_layout for '
    '"with reinforcement" (Bewehrung); it combines with every other '
    'filter. Leave empty for all.'))]
FitModeArg = Annotated[str, Field(description=(
    'Search by size, with size_mm: about = every side within the '
    'tolerance of the asked side (which pieces are about this '
    'size); can_hold = every side of the piece at least the asked '
    'side (which pieces can this part be cut from). The sides are '
    'compared largest to smallest, so the orientation does not '
    'matter. A piece without a known size never matches.'))]
SizeArg = Annotated[Optional[list[float]], Field(description=(
    'The asked size: three numbers in mm in any order, for example '
    '[1200, 600, 200]. Needs fit_mode.'))]
ToleranceArg = Annotated[str, Field(description=(
    'Only for fit_mode about: a share of each asked side or '
    'millimetres, for example "10%" (the default) or "50mm".'))]
NearLatArg = Annotated[Optional[float], Field(description=(
    'Search by place: the latitude of the point, -90 to 90, with '
    'near_lon. Only pieces with a known place on the chosen layer '
    'are listed, nearest first, each with its distance_km.'))]
NearLonArg = Annotated[Optional[float], Field(description=(
    'The longitude of the point, -180 to 180. Needs near_lat.'
    ))]
NearLayerArg = Annotated[str, Field(description=(
    'Which place of a piece is measured: current (where the piece '
    'is now; the default) or origin (the building it comes from, '
    'known for fewer pieces).'))]
RadiusArg = Annotated[Optional[float], Field(description=(
    'Only pieces within this many km of the point. Without it every '
    'piece with a place on the layer is listed, nearest first.'
    ))]


def search_params(*, query: str, original_function: str, material: str,
                  dataset: str, shape_class: str, circulation: str,
                  status: str, include_withdrawn: bool, has_evidence: str,
                  fit_mode: str, size_mm: Optional[list], tolerance: str,
                  near_lat: Optional[float], near_lon: Optional[float],
                  near_layer: str, radius_km: Optional[float]
                  ) -> Tuple[dict, dict, dict]:
    """The REST filters of one search (the list, count, stats and similar
    routes read the same names), the fit part and the near part of it. A
    combination the routes would refuse is a ToolError in words."""
    if has_evidence and has_evidence not in EVIDENCE_METHODS:
        raise ToolError('has_evidence is one of '
                        + ', '.join(EVIDENCE_METHODS) + '.')
    fit = {}
    if fit_mode or size_mm or tolerance:
        if fit_mode not in FIT_MODES:
            raise ToolError('fit_mode is about or can_hold, with size_mm.')
        if not size_mm or len(size_mm) != 3:
            raise ToolError('size_mm needs three numbers in mm, for '
                            'example [1200, 600, 200].')
        fit = {'fit_mode': fit_mode, 'fit_size': size_text(size_mm),
               'fit_tol': tolerance}
    near = {}
    if (near_lat is not None or near_lon is not None or near_layer
            or radius_km is not None):
        try:
            near = parse_near(near_lat, near_lon, near_layer or None,
                              radius_km)
        except NearError as exc:
            raise ToolError(f'{exc}.')
        near = {k: v for k, v in near.items() if v is not None}
    filters = {
        'q': query, 'original_function': original_function,
        'material': material, 'dataset': dataset,
        'shape_class': shape_class, 'circulation': circulation,
        'status': status, 'include_withdrawn': include_withdrawn or None,
        'evidence_method': has_evidence, **fit, **near}
    return filters, fit, near


def build_mcp(app, frontend_url: str) -> FastMCP:
    """The MCP server (stateless HTTP) whose tools call ``app``."""
    web = frontend_url.rstrip('/')
    mcp = FastMCP(
        'Catalog of Second Chances', instructions=INSTRUCTIONS,
        website_url=web,
        icons=[Icon(src=f'{web}/favicon.ico', mimeType='image/x-icon',
                    sizes=['any'])],
        stateless_http=True, json_response=True,
        streamable_http_path='/mcp',
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False))

    def link_component(identity_id: str, snapshot_id: Optional[str] = None
                       ) -> str:
        suffix = f'?snapshot={snapshot_id}' if snapshot_id else ''
        return f'{web}/components/{identity_id}{suffix}'

    async def owner() -> UserInDB:
        """The account of the token of this call, as it is now."""
        token = get_access_token()
        if token is None or not token.subject:
            raise ToolError('Not signed in.')
        doc = await app.mongodb_users.find_one({'_id': token.subject})
        if not doc:
            raise ToolError('Not signed in.')
        return UserInDB(**doc)

    async def get(path: str, params: Optional[dict] = None) -> Any:
        user = await owner()
        try:
            return await rest_get(app, user, path, params)
        except InternalError as exc:
            if exc.status in (401, 403, 404, 410):
                # the same words for a missing record and for one you may
                # not see: the answer does not tell them apart
                raise ToolError('Not found, or not visible to you.')
            if exc.status == 429:
                raise ToolError('Too many reads just now; wait a minute.')
            if exc.status == 409:
                raise ToolError(str(exc.detail))
            if exc.status in (400, 422):
                raise ToolError(f'The request was not valid: {exc.detail}')
            log.warning('mcp tool: %s answered %s', path, exc.status)
            raise ToolError('The catalog could not answer this request.')

    def page_args(page: int, size: int):
        return max(1, page), min(max(1, size), PAGE_MAX)

    # 1 -------------------------------------------------------------------------
    @mcp.tool(title='Search reused building components', annotations=READ_ONLY)
    async def search_components(
        query: QueryArg = '',
        original_function: FunctionArg = '',
        material: MaterialArg = '',
        dataset: DatasetArg = '',
        shape_class: ShapeClassArg = '',
        circulation: CirculationArg = 'active',
        status: StatusArg = 'published',
        include_withdrawn: WithdrawnArg = False,
        has_evidence: HasEvidenceArg = '',
        fit_mode: FitModeArg = '',
        size_mm: SizeArg = None,
        tolerance: ToleranceArg = '',
        near_lat: NearLatArg = None,
        near_lon: NearLonArg = None,
        near_layer: NearLayerArg = '',
        radius_km: RadiusArg = None,
        sort: Annotated[str, Field(description=(
            'catalog_number (default without a size or place search), date '
            '(the version applies from), created, volume (length x width x '
            'height; pieces without a size last), match (closeness to the '
            'size search: smallest deviation, or least waste, first; the '
            'default with fit_mode and no place search), distance (from the '
            'near point, nearest first; the default with near_lat and '
            'near_lon).'))] = '',
        order: Annotated[str, Field(description=(
            'asc (default) or desc.'))] = 'asc',
        page: Annotated[int, Field(description='Page, from 1.')] = 1,
        size: Annotated[int, Field(description='Rows per page, 1 to 25.')] = 10,
    ) -> dict:
        """Search the catalog of reused components. Returns one short row per
        component (name, function, material, dataset, size, status,
        visibility) with its web link, and the total. With fit_mode and
        size_mm each row also carries its deviation (about, in per cent) or
        waste (can_hold, in m3 and in per cent of the piece); with near_lat
        and near_lon each row carries its distance_km. has_evidence keeps
        only components with a published, current evidence record of one
        method, for example reinforcement_layout for "with reinforcement". Use
        get_component for the details of one."""
        page, size = page_args(page, size)
        filters, fit, near = search_params(
            query=query, original_function=original_function,
            material=material, dataset=dataset, shape_class=shape_class,
            circulation=circulation, status=status,
            include_withdrawn=include_withdrawn, has_evidence=has_evidence,
            fit_mode=fit_mode,
            size_mm=size_mm, tolerance=tolerance, near_lat=near_lat,
            near_lon=near_lon, near_layer=near_layer, radius_km=radius_km)
        sort = sort or ('distance' if near
                        else 'match' if fit else 'catalog_number')
        if sort not in SEARCH_SORTS:
            raise ToolError('sort is one of ' + ', '.join(SEARCH_SORTS) + '.')
        if sort == 'match' and not fit:
            raise ToolError('sort match needs fit_mode and size_mm.')
        if sort == 'distance' and not near:
            raise ToolError('sort distance needs near_lat and near_lon.')
        if order not in ('asc', 'desc'):
            raise ToolError('order is asc or desc.')
        rows = await get('/identities', {
            **filters, 'page': page, 'size': size,
            'sortkey': SEARCH_SORTS[sort], 'sortorder': order})
        total = await get('/identities/count', filters)
        return limited({
            'total': total.get('count'), 'page': page, 'size': size,
            'sort': sort, 'order': order,
            **({'near': {'lat': near['near_lat'], 'lon': near['near_lon'],
                         'layer': near['near_layer'],
                         'radius_km': near.get('radius_km')}}
               if near else {}),
            'results': [short_row(r, link_component(r['_id']))
                        for r in rows]})

    # 2 -------------------------------------------------------------------------
    @mcp.tool(title='Get one component', annotations=READ_ONLY)
    async def get_component(
        component_id: Annotated[str, Field(description=(
            'The component id (a UUID) from search_components.'))],
    ) -> dict:
        """One component: what it is, where it comes from, how it left
        circulation, its derived properties with confidence, its current
        version in short (with the count of its reinforcement layouts and
        bars), and links. Geometry is a summary only."""
        passport = await get(f'/identities/{component_id}/compose')
        versions = await get(f'/identities/{component_id}/snapshots')
        layouts = await get(f'/identities/{component_id}/evidence',
                            {'method': 'reinforcement_layout'})
        identity = passport.get('identity') or {}
        snapshots = passport.get('snapshots') or []
        current = next((s for s in snapshots
                        if s.get('_id') == identity.get('current_snapshot_id')),
                       snapshots[-1] if snapshots else {})
        origin = identity.get('origin') or {}
        place = origin.get('place') or {}
        work = origin.get('construction_work') or {}
        return limited(clean({
            'id': identity.get('_id'), 'name': current.get('name'),
            'catalog_number': identity.get('catalog_number'),
            'original_function': identity.get('original_function'),
            'material': identity.get('material'),
            'material_class': identity.get('material_class'),
            'trade_name': identity.get('trade_name'),
            'manufacturer': identity.get('manufacturer'),
            'dataset': identity.get('dataset'),
            'visibility': visibility_of(identity),
            'origin': {
                'kind': origin.get('kind'), 'planned': origin.get('planned'),
                'at': origin.get('at'), 'place': place.get('name'),
                'construction_work': work.get('name'),
                'use': work.get('use'), 'notes': origin.get('notes')},
            'exit': identity.get('exit'),
            'withdrawn': identity.get('withdrawn'),
            'in_circulation': identity.get('exit') is None,
            'properties': {
                k: {key: v.get(key) for key in
                    ('range', 'unit', 'confidence', 'source', 'n')}
                for k, v in (identity.get('properties') or {}).items()
                if isinstance(v, dict)},
            'current_version': {
                'id': current.get('_id'), 'version': current.get('version'),
                'status': current.get('status'),
                'shape_class': current.get('shape_class'),
                'bbx_mm': current.get('bbx'),
                'complexity': current.get('complexity'),
                'fragment': current.get('fragment'),
                'quantity': current.get('quantity'),
                'effective_from': current.get('effective_from'),
                'location': current.get('location'),
                'geometry': geometry_summary(current.get('geometry')),
                'reinforcement_layouts': layouts_of_version(
                    layouts, current.get('_id'))},
            'version_count': len(versions),
            'web_link': link_component(identity.get('_id') or component_id),
            'next': ('list_versions, get_evidence and get_timeline take '
                     'this id.')}))

    # 3 -------------------------------------------------------------------------
    @mcp.tool(title='List the versions of a component', annotations=READ_ONLY)
    async def list_versions(
        component_id: Annotated[str, Field(description='The component id.')],
    ) -> dict:
        """The versions (states) of a component, oldest first: version number,
        status, name, from when it applies, which one is current, with the id
        to pass to get_version and a web link for each."""
        rows = await get(f'/identities/{component_id}/snapshots')
        return limited(clean({
            'component_id': component_id,
            'web_link': link_component(component_id),
            'versions': [{
                'id': r.get('_id'), 'version': r.get('version'),
                'status': r.get('status'), 'is_current': r.get('is_current'),
                'name': r.get('name'),
                'effective_from': r.get('effective_from'),
                'supersedes': r.get('supersedes'),
                'superseded_by': r.get('superseded_by'),
                'added_by': r.get('added_by_username'),
                'web_link': link_component(component_id, r.get('_id'))}
                for r in rows]}))

    # 4 -------------------------------------------------------------------------
    @mcp.tool(title='Get one version of a component', annotations=READ_ONLY)
    async def get_version(
        version_id: Annotated[str, Field(description=(
            'The version id (a UUID) from list_versions.'))],
    ) -> dict:
        """One version of a component: size, shape class, descriptors,
        derived properties, status and notes. The geometry is only a summary
        (counts); the web link opens the viewer. The reinforcement layouts
        of the version are counted from the evidence."""
        s = await get(f'/snapshots/{version_id}')
        identity_id = s.get('identity_id')
        layouts = await get(f'/identities/{identity_id}/evidence',
                            {'method': 'reinforcement_layout'}
                            ) if identity_id else []
        return limited(clean({
            'id': s.get('_id'), 'component_id': identity_id,
            'version': s.get('version'), 'status': s.get('status'),
            'name': s.get('name'),
            'effective_from': s.get('effective_from'),
            'shape_class': s.get('shape_class'), 'bbx_mm': s.get('bbx'),
            'complexity': s.get('complexity'), 'fragment': s.get('fragment'),
            'quantity': s.get('quantity'), 'color': s.get('color'),
            'location': s.get('location'),
            'descriptors': s.get('descriptors'),
            'properties': s.get('properties'), 'notes': s.get('notes'),
            'photo_credit': s.get('photo_credit'),
            'photo_count': s.get('photo_count'),
            'added_by': s.get('added_by_username'),
            'supersedes': s.get('supersedes'),
            'superseded_by': s.get('superseded_by'),
            'geometry': geometry_summary(s.get('geometry')),
            'reinforcement_layouts': layouts_of_version(
                layouts, s.get('_id')),
            'web_link': link_component(identity_id, s.get('_id'))
            if identity_id else None}))

    # 5 -------------------------------------------------------------------------
    @mcp.tool(title='Get the evidence of a component',
              annotations=READ_ONLY,
              description=GET_EVIDENCE_TEXT)
    async def get_evidence(
        component_id: Annotated[str, Field(description=(
            'The component id. Leave empty when you pass evidence_id.'))] = '',
        evidence_id: Annotated[str, Field(description=(
            'One evidence record in full, with its payload.'))] = '',
        method: Annotated[str, Field(description=(
            'Only this measurement method.'))] = '',
        status: Annotated[str, Field(description=(
            'published (default) or all.'))] = 'published',
        page: Annotated[int, Field(description='Page, from 1.')] = 1,
        size: Annotated[int, Field(description='Records per page, 1 to 25.')] = 10,
    ) -> dict:
        if evidence_id:
            record = await get(f'/evidence/{evidence_id}')
            identity_id = record.get('identity_id')
            attachments = [{'name': a.get('filename') or a.get('name')}
                           for a in record.get('attachments') or []
                           if isinstance(a, dict)]
            record = {**record, 'attachments': attachments}
            return limited(clean({
                'record': record,
                'web_link': link_component(identity_id) if identity_id else None}))
        if not component_id:
            raise ToolError('Pass component_id or evidence_id.')
        page, size = page_args(page, size)
        rows = await get(f'/identities/{component_id}/evidence',
                         {'method': method, 'status': status})
        window = rows[(page - 1) * size: page * size]
        return limited(clean({
            'component_id': component_id, 'total': len(rows), 'page': page,
            'size': size, 'web_link': link_component(component_id),
            'evidence': [{
                'id': r.get('_id'), 'method': r.get('method'),
                'source_tier': r.get('source_tier'),
                'observed_at': r.get('observed_at'),
                'summary': r.get('summary'), 'status': r.get('status'),
                'verification': (r.get('verification') or {}).get('state')
                if isinstance(r.get('verification'), dict) else None,
                'recorded_by': r.get('recorded_by_username'),
                'performed_by': performers(r),
                **({'reinforcement': layout_summary(r)}
                   if r.get('method') == 'reinforcement_layout' else {}),
                'notes': r.get('notes'), 'warnings': r.get('warnings'),
                'withdrawn': r.get('withdrawn_at') is not None
                if 'withdrawn_at' in r else None}
                for r in window]}))

    # 6 -------------------------------------------------------------------------
    @mcp.tool(title='List datasets', annotations=READ_ONLY)
    async def list_datasets() -> dict:
        """The datasets (collections of components, each with its own access)
        you can see: name, id, visibility (public or members only), whether an
        administrator reviewed it, and counts."""
        rows = await get('/datasets')
        return limited(clean({'datasets': [{
            'id': d.get('_id'), 'name': d.get('name'),
            'visibility': d.get('visibility'), 'reviewed': d.get('reviewed'),
            'components': d.get('component_count'),
            'members': d.get('member_count'),
            'web_link': f'{web}/components?dataset={d.get("_id")}'}
            for d in rows]}))

    # 7 -------------------------------------------------------------------------
    @mcp.tool(title='Get one dataset', annotations=READ_ONLY)
    async def get_dataset(
        dataset_id: Annotated[str, Field(description=(
            'The dataset id from list_datasets.'))],
    ) -> dict:
        """One dataset: name, visibility, review state and who works in it
        (usernames and their dataset roles, no contact details)."""
        d = await get(f'/datasets/{dataset_id}')
        return limited(clean({
            'id': d.get('_id'), 'name': d.get('name'),
            'visibility': d.get('visibility'), 'reviewed': d.get('reviewed'),
            'your_roles': d.get('roles'),
            'members': [{'username': m.get('username'),
                         'roles': m.get('roles')}
                        for m in d.get('members') or [] if isinstance(m, dict)],
            'web_link': f'{web}/components?dataset={d.get("_id")}'}))

    # 8 -------------------------------------------------------------------------
    @mcp.tool(title='Get the timeline of a component', annotations=READ_ONLY)
    async def get_timeline(
        component_id: Annotated[str, Field(description='The component id.')],
    ) -> dict:
        """What happened to a component, in order: origin, versions,
        corrections, evidence, changes, how it left circulation. Each event
        has a kind, a time (with its precision) and a short detail."""
        body = await get(f'/identities/{component_id}/timeline')
        return limited(clean({
            'component_id': component_id,
            'web_link': link_component(component_id),
            'events': [{k: e.get(k) for k in
                        ('kind', 'at', 'precision', 'section', 'cycle',
                         'planned', 'detail')}
                       for e in body.get('events') or []]}))

    # 9 -------------------------------------------------------------------------
    @mcp.tool(title='Find similar components', annotations=READ_ONLY)
    async def similar_components(
        component_id: Annotated[str, Field(description='The component id.')],
        basis: Annotated[str, Field(description=(
            'What is compared: radial_signature (the shape seen from the '
            'centre, the default), scalars (how box-, sphere-, line- and '
            'plane-like it is) or hks (the heat kernel signature).'))
            ] = 'radial_signature',
        count: Annotated[int, Field(description='How many, 1 to 25.')] = 10,
        query: QueryArg = '',
        original_function: FunctionArg = '',
        material: MaterialArg = '',
        dataset: DatasetArg = '',
        shape_class: ShapeClassArg = '',
        circulation: CirculationArg = 'active',
        status: StatusArg = 'published',
        include_withdrawn: WithdrawnArg = False,
        has_evidence: HasEvidenceArg = '',
        fit_mode: FitModeArg = '',
        size_mm: SizeArg = None,
        tolerance: ToleranceArg = '',
        near_lat: NearLatArg = None,
        near_lon: NearLonArg = None,
        near_layer: NearLayerArg = '',
        radius_km: RadiusArg = None,
    ) -> dict:
        """Components that look alike: the nearest neighbours of one component
        in the full space of its shape descriptors (every dimension
        standardised over the catalog), not on the similarity map.
        descriptor_distance is a Euclidean distance in standardised descriptor
        units, not metres or millimetres: smaller is more similar, comparable
        within one answer or between answers of the same basis. The filters
        of search_components apply first and the nearest of what passes are
        ranked, so "similar in shape, can hold 1200 x 600 x 200 mm, within
        50 km" works. The component itself is left out. A component without
        the descriptor of the basis cannot be compared."""
        if basis not in SIMILARITY_BASES:
            raise ToolError('basis is ' + ', '.join(SIMILARITY_BASES) + '.')
        count = min(max(1, count), PAGE_MAX)
        filters, fit, near = search_params(
            query=query, original_function=original_function,
            material=material, dataset=dataset, shape_class=shape_class,
            circulation=circulation, status=status,
            include_withdrawn=include_withdrawn, has_evidence=has_evidence,
            fit_mode=fit_mode,
            size_mm=size_mm, tolerance=tolerance, near_lat=near_lat,
            near_lon=near_lon, near_layer=near_layer, radius_km=radius_km)
        body = await get(f'/identities/{component_id}/similar',
                         {**filters, 'basis': basis, 'count': count})
        return limited(clean({
            'component_id': component_id, 'basis': body.get('basis'),
            'basis_label': body.get('basis_label'),
            'matrix_built': body.get('computed_at'),
            'compared_with': body.get('considered'),
            'distance_unit': 'standardised descriptor units (smaller is '
                             'more similar; not metres or millimetres)',
            'web_link': link_component(component_id),
            'similar': [{
                'descriptor_distance': round(r['distance'], 3),
                **short_row(r['piece'], link_component(r['piece']['_id']))}
                for r in body.get('results') or []]}))

    # 10 ------------------------------------------------------------------------
    @mcp.tool(title='Overview of the catalog in numbers', annotations=READ_ONLY)
    async def catalog_overview(
        query: QueryArg = '',
        original_function: FunctionArg = '',
        material: MaterialArg = '',
        dataset: DatasetArg = '',
        shape_class: ShapeClassArg = '',
        circulation: CirculationArg = 'active',
        status: StatusArg = 'published',
        include_withdrawn: WithdrawnArg = False,
        has_evidence: HasEvidenceArg = '',
        fit_mode: FitModeArg = '',
        size_mm: SizeArg = None,
        tolerance: ToleranceArg = '',
        near_lat: NearLatArg = None,
        near_lon: NearLonArg = None,
        near_layer: NearLayerArg = '',
        radius_km: RadiusArg = None,
    ) -> dict:
        """What the catalog holds, in numbers, for the components that match
        the filters of search_components (none: the whole catalog you may
        see). It counts components (one per piece or batch, with its current
        version), not rows of a list: the total, how many physical pieces they
        stand for, and the counts by material (with its label), original
        function, dataset, shape class and circulation. The ranges give the
        smallest and the largest value of each side of the pieces that have a
        size, sides sorted largest, middle, smallest; lengths are in
        millimetres. It also says how many components have a current and how
        many an origin location, and how many of the counted components are
        not public (visible to you as a member of their dataset or as an
        administrator). Use it to see the catalog before a search."""
        filters, fit, near = search_params(
            query=query, original_function=original_function,
            material=material, dataset=dataset, shape_class=shape_class,
            circulation=circulation, status=status,
            include_withdrawn=include_withdrawn, has_evidence=has_evidence,
            fit_mode=fit_mode,
            size_mm=size_mm, tolerance=tolerance, near_lat=near_lat,
            near_lon=near_lon, near_layer=near_layer, radius_km=radius_km)
        # limit_dim 0: every value, not the ten most frequent and "others"
        stats = await get('/identities/stats', {**filters, 'limit_dim': 0})
        labels = {m.get('_id'): m.get('label') for m in await get(
            '/materials', {'include_retired': 'true',
                           'include_merged': 'true'}) or []}

        def counted(rows, label_of=None):
            return [{'key': r['label'], 'label': (label_of(r['label'])
                                                  if label_of else None),
                     'count': r['count']}
                    for r in rows or []]

        sides = stats.get('sideRanges') or {}
        not_public = int(stats.get('notPublic') or 0)
        total = int(stats.get('total') or 0)
        return limited(clean({
            'counted': 'components with a current version that match the '
                       'filters and that you may see',
            'total': total, 'pieces': stats.get('pieces'),
            'by_material': counted(stats.get('byMaterial'), labels.get),
            'by_original_function': counted(
                stats.get('byOriginalFunction'), ORIGINAL_FUNCTION_LABELS.get),
            'by_dataset': counted(stats.get('byDataset')),
            'by_shape_class': counted(
                stats.get('byShapeClass'), SHAPE_CLASS_LABELS.get),
            'by_circulation': counted(
                stats.get('byCirculation'), CIRCULATION_LABELS.get),
            'side_ranges_mm': {
                'components_with_a_size': sides.get('count', 0),
                'largest_side': sides.get('largest'),
                'middle_side': sides.get('middle'),
                'smallest_side': sides.get('smallest')},
            'with_location': {
                'current': (stats.get('withLocation') or {}).get('current', 0),
                'origin': (stats.get('withLocation') or {}).get('origin', 0)},
            'not_public': not_public,
            'note': (f'{not_public} of the {total} counted components are '
                     f'not public: you see them as a member of their dataset '
                     f'or as an administrator.' if not_public else
                     f'All {total} counted components are public.'),
            'filters': {k: v for k, v in filters.items()
                        if v not in ('', None)}}))

    return mcp


# THE GATE OF /mcp ------------------------------------------------------------------------
class RateGate:
    """Outside the SDK's authentication: a valid token over its limit, or an
    address over its limit of failed lookups, gets a 429 with Retry-After (the
    SDK middleware only knows 401 and 403). It also tells the token verifier
    which address the request comes from."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        marker = None
        if scope['type'] == 'http':
            marker = REQUEST_ADDRESS.set(lim.client_ip(Request(scope)))
        try:
            await self.inner(scope, receive, send)
        except RateLimited as limited_:
            if scope['type'] != 'http':
                raise
            body = json.dumps({'error': 'rate_limited',
                               'error_description': limited_.message}).encode()
            await send({'type': 'http.response.start', 'status': 429,
                        'headers': [
                            (b'content-type', b'application/json'),
                            (b'content-length', str(len(body)).encode()),
                            (b'retry-after', str(limited_.wait).encode())]})
            await send({'type': 'http.response.body', 'body': body})
        finally:
            if marker is not None:
                REQUEST_ADDRESS.reset(marker)


def build_gate(app, mcp: FastMCP, metadata_url: str):
    """``/mcp``: the streamable HTTP endpoint behind the token check. A call
    without a valid access token gets 401 with ``WWW-Authenticate: Bearer
    resource_metadata=...`` (and the same text whatever was wrong)."""
    mcp.streamable_http_app()                     # creates the session manager
    endpoint = StreamableHTTPASGIApp(mcp.session_manager)
    stack = RequireAuthMiddleware(
        endpoint, [tk.SCOPE_CATALOG], AnyHttpUrl(metadata_url))
    stack = AuthContextMiddleware(stack)
    stack = AuthenticationMiddleware(
        stack, backend=BearerAuthBackend(AccessTokenVerifier(app)))
    return RateGate(stack), mcp.session_manager
