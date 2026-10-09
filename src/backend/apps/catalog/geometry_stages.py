#!/usr/bin/env python3.13
"""
The geometry runner's stages, as pure functions over one snapshot document
(data model spec section 4.3, decisions 6.14, 8.7).

Stages, in the order each reads the previous one:

    1 frame        frame, bbx, the four hull scores           cheap, sync
    2 shape_class  shape_class (unless assigned)               cheap, sync
    3 proxies      fitted primary proxy + deviation maps       expensive
    4 descriptors  radial signature, HKS                       expensive
    5 complexity   complexity 0..3 (unless assigned)           cheap
    6 previews     previews/<sid>.webp                         medium

Every stage stores next to its output a stamp ``derivation.<stage> =
{version, input, at, error}``: the stage's ``*_VERSION`` and a fingerprint
of its inputs. A stage is **stale** when its stamp is missing or its
version or input differs (a failed stamp counts as current until its
version or input changes, so a broken input does not retry forever). A
change of an upstream result --- a recompute, an override of
``shape_class`` or an ``original_function`` change (the column rule of the frame)
changes the inputs downstream, so those stages rerun and no order can loop.

``run_stages`` does no I/O of its own: it returns what to ``$set`` and
``$unset`` on the snapshot, the proxy-map files to write and delete and the
preview bytes; the caller (cron runner or API route) writes them.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
)

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.complexity import COMPLEXITY_VERSION, derive_complexity
from apps.catalog.frame import FRAME_VERSION, compute_frame
from apps.catalog.geometry_source import (
    Source,
    load_source,
    source_fingerprint,
)
from apps.catalog.proxies.fit import fit_primary
from apps.catalog.proxies.registry import PROXIES_VERSION
from apps.catalog.shape_class import SHAPE_CLASS_VERSION, derive_shape_class
from apps.descriptors.hks import HKS_VERSION
from apps.descriptors.registry import compute_descriptor
from apps.descriptors.specs import ALL_SPECS

DESCRIPTORS_VERSION = 2          # 1 = 0.5 (PCA aligned); 2 = frame, + HKS
PREVIEW_VERSION = 1

STAGES = ('frame', 'shape_class', 'proxies', 'descriptors', 'complexity',
          'previews')
SYNC_STAGES = ('frame', 'shape_class')

VERSIONS = {
    'frame': FRAME_VERSION,
    'shape_class': SHAPE_CLASS_VERSION,
    'proxies': PROXIES_VERSION,
    'descriptors': DESCRIPTORS_VERSION * 1000 + HKS_VERSION,
    'complexity': COMPLEXITY_VERSION,
    'previews': PREVIEW_VERSION,
}

HULL_SCORES = ('boxscore', 'spherescore', 'linescore', 'planescore')
LEGACY_FIELDS = ('pca_frame', 'bbx_origin')

# The stages whose input is another stage's result: a stage whose upstream
# carries a current error stamp is blocked (decision 8.54), never run.
UPSTREAM = {
    'frame': (),
    'shape_class': ('frame',),
    'proxies': ('frame', 'shape_class'),
    'descriptors': ('frame', 'shape_class'),
    'complexity': ('frame', 'shape_class', 'proxies'),
    'previews': (),
}

# Where the expensive stages run (decisions 8.45, 8.54): on this server's
# cron, or on a remote worker through the API. Complexity counts as heavy: it
# reads the proxy residuals.
HEAVY_STAGES = ('proxies', 'descriptors', 'complexity', 'previews')
HEAVY_STAGES_ENV = 'CSC_GEOMETRY_HEAVY_STAGES'
ERROR_LIMIT = 160
# A URL is replaced as a whole first (its host is as private as a path), so
# neither the drive-letter nor the POSIX pattern can eat "http:/" or "//host".
_URL = re.compile(r'\b[A-Za-z][A-Za-z0-9+.-]*://[^\s\'")]+')
_QUOTED_PATH = re.compile(r"""(['"])(?:(?!\1).)*[\\/](?:(?!\1).)*\1""")
# a drive letter on a word boundary, or a UNC share
_WINDOWS_PATH = re.compile(
    r'(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/](?![\\/])|\\\\[^\\/\s]+[\\/])[^:\n]*')
# at least two segments, not glued to a word ("and/or", "3/4", "a/b/c")
_POSIX_PATH = re.compile(r'(?<![\w/])/[^\s\'"):,;/]+(?:/[^\s\'"):,;/]+)+')


def heavy_stages_where() -> str:
    """``server`` (default) or ``remote``."""
    value = (os.environ.get(HEAVY_STAGES_ENV) or 'server').strip().lower()
    if value not in ('server', 'remote'):
        raise ValueError(f'{HEAVY_STAGES_ENV} must be server or remote, '
                         f'got {value!r}')
    return value


def server_stages() -> Tuple[str, ...]:
    """The stages this server's own cron and recompute route run."""
    return STAGES if heavy_stages_where() == 'server' else SYNC_STAGES


def short_error(exc: BaseException) -> str:
    """An error text safe to store: short, without file system paths."""
    text = f'{type(exc).__name__}: {exc}'.replace('\n', ' ')
    text = _URL.sub('<url>', text)
    for pattern in (_QUOTED_PATH, _WINDOWS_PATH, _POSIX_PATH):
        text = pattern.sub('<path>', text)
    return text if len(text) <= ERROR_LIMIT else text[:ERROR_LIMIT - 3] + '...'


def now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _digest(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, separators=(',', ':'),
                      default=str)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:24]


# ENVIRONMENT -----------------------------------------------------------------
@dataclass
class Env:
    """Where a stage reads and writes; the caller owns the I/O."""
    meshes_dir: Optional[str] = None
    point_clouds_dir: Optional[str] = None
    preview_dir: Optional[str] = None
    log: Callable[[str], None] = lambda _message: None


@dataclass
class Outcome:
    """What ``run_stages`` wants written."""
    set: Dict[str, Any] = field(default_factory=dict)
    unset: List[str] = field(default_factory=list)
    write_files: Dict[str, bytes] = field(default_factory=dict)   # proxies/...
    delete_files: List[str] = field(default_factory=list)
    preview: Optional[bytes] = None
    ran: List[str] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)   # seconds per stage

    @property
    def changed(self) -> bool:
        return bool(self.ran)


# INPUTS AND STALENESS --------------------------------------------------------
def _frame_digest(snapshot: Mapping[str, Any]) -> str:
    frame = snapshot.get('frame') or {}
    rounded = {k: [round(v, 6) for v in frame.get(k) or []]
               for k in ('o', 'x', 'y', 'z')}
    return _digest(rounded, [round(v, 6) for v in snapshot.get('bbx') or []])


def _scores(snapshot: Mapping[str, Any]) -> List[Optional[float]]:
    descriptors = snapshot.get('descriptors') or {}
    return [None if descriptors.get(k) is None else round(descriptors[k], 6)
            for k in HULL_SCORES]


def _fitted(snapshot: Mapping[str, Any]) -> List[dict]:
    return [p for p in (snapshot.get('geometry') or {}).get('proxies') or []
            if (p.get('fit') or {}).get('method') != 'authored']


def _authored_primary(snapshot: Mapping[str, Any]) -> Optional[dict]:
    for proxy in (snapshot.get('geometry') or {}).get('proxies') or []:
        if proxy.get('role') == 'primary' \
                and (proxy.get('fit') or {}).get('method') == 'authored':
            return proxy
    return None


def _source_fp(snapshot: Mapping[str, Any], env: Env) -> str:
    return source_fingerprint(snapshot, env.meshes_dir, env.point_clouds_dir)


def stage_input(stage: str, snapshot: Mapping[str, Any],
                identity: Mapping[str, Any], env: Env,
                source: Optional[str] = None) -> str:
    """Fingerprint of the inputs ``stage`` would read right now. ``source``
    is the source fingerprint when the caller already has it (hashing the
    inline geometry is the expensive part of a sweep)."""
    if source is None and stage in ('frame', 'proxies', 'descriptors',
                                    'previews'):
        source = _source_fp(snapshot, env)
    if stage == 'frame':
        return _digest(source, identity.get('original_function'))
    if stage == 'shape_class':
        return _digest(_frame_digest(snapshot), _scores(snapshot))
    if stage == 'proxies':
        return _digest(source, snapshot.get('shape_class'),
                       snapshot.get('shape_class_source'),
                       _frame_digest(snapshot))
    if stage == 'descriptors':
        return _digest(source, _frame_digest(snapshot),
                       snapshot.get('shape_class'))
    if stage == 'complexity':
        primary = _primary_fit(snapshot)
        return _digest(primary.get('p95_mm') if primary else None,
                       _frame_digest(snapshot), _scores(snapshot),
                       snapshot.get('shape_class'))
    if stage == 'previews':
        return _digest(source, snapshot.get('color'))
    raise ValueError(f'unknown stage {stage!r}')


def applies(stage: str, snapshot: Mapping[str, Any]) -> bool:
    """False when an override or an authored primitive makes the stage
    moot: an assigned class / complexity, an authored primary proxy."""
    if stage == 'shape_class':
        return snapshot.get('shape_class_source') != 'assigned'
    if stage == 'proxies':
        # an authored primary is never refitted; only a fitted proxy left
        # beside one (two primaries, I2) is cleaned away
        return _authored_primary(snapshot) is None or bool(_fitted(snapshot))
    if stage == 'complexity':
        return snapshot.get('complexity_source') != 'assigned'
    return True


def _output_missing(stage: str, snapshot: Mapping[str, Any],
                    env: Env) -> bool:
    """A stage that stamped a result but whose output is not there (a
    cleared value, a deleted file) is stale (decision 8.54)."""
    if stage == 'frame':
        return not snapshot.get('frame') or not snapshot.get('bbx')
    if stage == 'shape_class':
        return snapshot.get('shape_class') is None
    if stage == 'proxies':
        return _authored_primary(snapshot) is None and not _fitted(snapshot)
    if stage == 'descriptors':
        return 'hks' not in (snapshot.get('descriptors') or {})
    if stage == 'complexity':
        return snapshot.get('complexity') is None
    if stage == 'previews':
        return bool(env.preview_dir) and not os.path.isfile(os.path.join(
            env.preview_dir, f'{snapshot.get("_id")}.webp'))
    return False


def _current(stage: str, snapshot: Mapping[str, Any],
             identity: Mapping[str, Any], env: Env,
             source: Optional[str]) -> Optional[Mapping[str, Any]]:
    """The stamp of ``stage`` when it is for this version and input."""
    stamp = (snapshot.get('derivation') or {}).get(stage)
    if stamp and stamp.get('version') == VERSIONS[stage] \
            and stamp.get('input') == stage_input(
                stage, snapshot, identity, env, source):
        return stamp
    return None


def is_blocked(stage: str, snapshot: Mapping[str, Any],
               identity: Mapping[str, Any], env: Env,
               source: Optional[str] = None) -> bool:
    """True when an upstream stage ended in an error for its current version
    and input: this stage has nothing to read and is neither run nor stale."""
    for upstream in UPSTREAM[stage]:
        if not applies(upstream, snapshot):
            continue
        stamp = _current(upstream, snapshot, identity, env, source)
        if stamp and stamp.get('error'):
            return True
    return False


def is_stale(stage: str, snapshot: Mapping[str, Any],
             identity: Mapping[str, Any], env: Env,
             source: Optional[str] = None,
             retry_errors: bool = False) -> bool:
    """Decision 8.46 / 8.54: stale when the stamp is missing or for another
    version or input, or its output is missing. An error stamp for the
    current version and input is current (``retry_errors`` lifts that) and
    blocks every stage that reads its result."""
    if not applies(stage, snapshot):
        return False
    if not retry_errors and is_blocked(stage, snapshot, identity, env, source):
        return False
    stamp = _current(stage, snapshot, identity, env, source)
    if stamp is None:
        return True
    if stamp.get('error'):
        return retry_errors
    return _output_missing(stage, snapshot, env)


def stale_stages(snapshot: Mapping[str, Any], identity: Mapping[str, Any],
                 env: Env, stages: Iterable[str] = STAGES,
                 retry_errors: bool = False) -> List[str]:
    source = _source_fp(snapshot, env)
    return [s for s in stages
            if is_stale(s, snapshot, identity, env, source, retry_errors)]


# STAGES ----------------------------------------------------------------------
def _primary_fit(snapshot: Mapping[str, Any]) -> Optional[dict]:
    for proxy in (snapshot.get('geometry') or {}).get('proxies') or []:
        if proxy.get('role') == 'primary':
            return proxy.get('fit')
    return None


def _stage_frame(work: dict, identity: Mapping[str, Any], env: Env,
                 source: Source, out: Outcome) -> None:
    result = compute_frame(
        source.points(), original_function=identity.get('original_function'))
    work['frame'] = result.frame
    work['bbx'] = list(result.bbx)
    work['_extents'] = list(result.obb_extents)
    descriptors = dict(work.get('descriptors') or {})
    descriptors.update(result.scores)
    work['descriptors'] = descriptors
    for legacy in LEGACY_FIELDS:
        if legacy in work:
            del work[legacy]
            out.unset.append(legacy)


def _stage_shape_class(work: dict) -> None:
    extents = work.get('_extents') or sorted(work['bbx'], reverse=True)
    boxscore = (work.get('descriptors') or {}).get('boxscore')
    work['shape_class'] = derive_shape_class(extents, boxscore)
    work['shape_class_source'] = 'derived'


def _stage_proxies(work: dict, snapshot_id: str, source: Source,
                   out: Outcome) -> None:
    geometry = dict(work['geometry'])
    authored = [p for p in geometry.get('proxies') or []
                if (p.get('fit') or {}).get('method') == 'authored']
    old_files = [face['file'] for proxy in _fitted(work)
                 for face in ((proxy.get('deviation_maps') or {})
                              .get('faces') or {}).values()]
    if _authored_primary(work) is not None:
        geometry['proxies'] = authored
        work['geometry'] = geometry
        out.delete_files.extend(old_files)
        return
    proxy, files = fit_primary(
        source, work['frame'], tuple(work['bbx']), work['shape_class'],
        snapshot_id, len(authored), now_z())
    geometry['proxies'] = authored + [proxy]
    work['geometry'] = geometry
    out.write_files.update(files)
    out.delete_files.extend(f for f in old_files if f not in files)


def _stage_descriptors(work: dict, env: Env, source: Source) -> List[str]:
    """Radial signature + HKS; a spec that fails is reported, the others
    still land. Returns the error messages."""
    descriptors = dict(work.get('descriptors') or {})
    errors: List[str] = []
    for spec in ALL_SPECS:
        try:
            descriptors.update(compute_descriptor(
                spec, work, None, log=env.log, meshes_dir=env.meshes_dir,
                point_clouds_dir=env.point_clouds_dir, source=source,
                raise_errors=True))
        except Exception as exc:                           # noqa: BLE001
            errors.append(f'{spec.name}: {short_error(exc)}')
    work['descriptors'] = descriptors
    return errors


def _stage_complexity(work: dict) -> None:
    fit = _primary_fit(work)
    ratio = None
    if fit and fit.get('p95_mm') is not None and max(work['bbx']) > 0:
        ratio = fit['p95_mm'] / max(work['bbx'])
    work['complexity'] = derive_complexity(
        ratio, (work.get('descriptors') or {}).get('boxscore'),
        work.get('shape_class'))
    work['complexity_source'] = 'derived'


def _stage_previews(work: dict) -> bytes:
    from io import BytesIO

    from apps.previewgen.previewgen import (
        create_snapshot_preview_image,
        crop_preview_whitespace,
    )
    image = crop_preview_whitespace(
        create_snapshot_preview_image(snapshot_data=work, size=800),
        padding=2)
    buffer = BytesIO()
    image.save(buffer, format='webp')
    return buffer.getvalue()


# RUNNER ----------------------------------------------------------------------
_OUTPUT_FIELDS = {
    'frame': ('frame', 'bbx', 'descriptors'),
    'shape_class': ('shape_class', 'shape_class_source'),
    'proxies': ('geometry',),
    'descriptors': ('descriptors',),
    'complexity': ('complexity', 'complexity_source'),
    'previews': (),
}


def run_stages(snapshot: Mapping[str, Any], identity: Mapping[str, Any],
               env: Env, stages: Iterable[str] = STAGES,
               force: bool = False, retry_errors: bool = False) -> Outcome:
    """Run the requested stages that are stale (or all of them, ``force``)
    on a copy of ``snapshot``, in order; later stages see earlier results.

    A failing stage is stamped with a short error text; the stages that read
    its result are blocked (not run, not stamped) until its version or input
    changes or ``retry_errors`` is set (decision 8.54).
    """
    wanted = [s for s in STAGES if s in set(stages)]
    work = copy.deepcopy(dict(snapshot))
    derivation = copy.deepcopy(work.get('derivation') or {})
    out = Outcome()
    sid = str(work.get('_id'))
    source: Optional[Source] = None
    source_fp = _source_fp(work, env)        # the geometry does not change

    def load() -> Source:
        nonlocal source
        if source is None:
            source = load_source(work, env.meshes_dir, env.point_clouds_dir)
        return source

    began = time.perf_counter()

    def stamp(stage: str, error: Optional[str] = None) -> None:
        nonlocal began
        out.timings[stage] = time.perf_counter() - began
        began = time.perf_counter()
        derivation[stage] = {
            'version': VERSIONS[stage],
            'input': stage_input(stage, work, identity, env, source_fp),
            'at': now_z(), 'error': error}
        out.ran.append(stage)
        if error:
            out.errors[stage] = error

    def fail(stage: str, exc: Exception) -> None:
        stamp(stage, short_error(exc))
        env.log(f'{sid} {stage} failed: {exc}')

    def view() -> dict:
        current = dict(work)
        current['derivation'] = derivation
        return current

    def due(stage: str) -> bool:
        if stage not in wanted or not applies(stage, work):
            return False
        if is_blocked(stage, view(), identity, env, source_fp):
            return False
        if force:
            return True
        return is_stale(stage, view(), identity, env, source_fp,
                        retry_errors)

    began = time.perf_counter()               # the stage's own work, not the check
    if due('frame'):
        began = time.perf_counter()
        try:
            _stage_frame(work, identity, env, load(), out)
            stamp('frame')
        except Exception as exc:                           # noqa: BLE001
            fail('frame', exc)
    if due('shape_class'):
        began = time.perf_counter()
        try:
            _stage_shape_class(work)
            stamp('shape_class')
        except Exception as exc:                           # noqa: BLE001
            fail('shape_class', exc)
    if due('proxies'):
        began = time.perf_counter()
        try:
            _stage_proxies(work, sid, load(), out)
            stamp('proxies')
        except Exception as exc:                           # noqa: BLE001
            fail('proxies', exc)
    if due('descriptors'):
        began = time.perf_counter()
        try:
            errors = _stage_descriptors(work, env, load())
        except Exception as exc:                           # noqa: BLE001
            fail('descriptors', exc)
        else:
            stamp('descriptors', '; '.join(errors) or None)
    if due('complexity'):
        began = time.perf_counter()
        try:
            _stage_complexity(work)
            stamp('complexity')
        except Exception as exc:                           # noqa: BLE001
            fail('complexity', exc)
    if due('previews'):
        began = time.perf_counter()
        try:
            out.preview = _stage_previews(work)
            stamp('previews')
        except Exception as exc:                           # noqa: BLE001
            fail('previews', exc)

    for stage in out.ran:
        for key in _OUTPUT_FIELDS[stage]:
            if key in work:
                out.set[key] = work[key]
    if out.ran:
        out.set['derivation'] = derivation
    return out
