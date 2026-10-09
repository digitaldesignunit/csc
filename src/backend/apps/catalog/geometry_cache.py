#!/usr/bin/env python3.13
"""
The geometry result cache (decision 8.122 f).

A full local pass of the geometry runner on a rehearsal database and a local
copy of the assets writes every result --- the derived fields, the deviation
maps and ``preview.webp`` --- to a cache directory, one folder per snapshot.
On the cutover day ``main_geometry.py --remote <url> --cache-dir <dir>``
uploads a cached result through ``POST /geometry/results/{sid}`` when its key
matches what ``GET /geometry/work/{sid}`` returns, with no PLY download and
no computation; any other snapshot is computed as before.

The key is what the stages read, without anything a file copy changes: the
snapshot id, the geometry the snapshot carries inline, the PLY chosen per
mesh and cloud with its **size** (never its modification time: the stamps of
the stages hold ``st_mtime_ns``, a copy changes it), the stage versions and
the context (function, assigned class and complexity, colour). The stamps are
not copied: the server recomputes them from the stored snapshot (8.51), and
a wrong key can only cost time (409, then compute).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import os
import shutil
import tempfile
from typing import Any, Dict, Iterable, List, Mapping, Optional

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.geometry_source import inline_fingerprint
from apps.catalog.geometry_stages import STAGES, VERSIONS, Outcome

# the derived fields each stage writes (the worker's upload names them)
FIELDS_OF_STAGE = {
    'frame': ('frame', 'bbx', 'descriptors'),
    'shape_class': ('shape_class',),
    'proxies': ('geometry',),
    'descriptors': ('descriptors',),
    'complexity': ('complexity',),
    'previews': (),
}
ENTRY = 'entry.json'
PREVIEW = 'preview.webp'


def cache_key(snapshot: Mapping[str, Any], context: Mapping[str, Any],
              file_sizes: Mapping[str, Any],
              versions: Optional[Mapping[str, int]] = None) -> Dict[str, Any]:
    """What a result was computed from. ``file_sizes`` is
    ``geometry_source.stored_file_sizes`` of the snapshot."""
    return {
        'snapshot_id': str(snapshot['_id']),
        'inline': inline_fingerprint(snapshot.get('geometry') or {}),
        'files': json.loads(json.dumps(file_sizes, sort_keys=True)),
        'versions': dict(versions if versions is not None else VERSIONS),
        'context': _context(context),
        # the class the proxies and the complexity were computed under; an
        # entry that ran the shape_class stage derived it itself and drops
        # this (``ResultCache.store``), any other entry holds the one it read
        'shape_class': snapshot.get('shape_class'),
    }


def _context(context: Mapping[str, Any]) -> Dict[str, Any]:
    """The context as a key: a class or complexity is either assigned or
    derived. ``derived`` and a source that is not set yet are the same thing
    (the stage that sets it is among the ones a cached result carries)."""
    out = json.loads(json.dumps(context, sort_keys=True, default=str))
    for name in ('shape_class_source', 'complexity_source'):
        if name in out and out[name] != 'assigned':
            out[name] = 'derived'
    return out


def _fields(values: Mapping[str, Any]) -> Dict[str, Any]:
    """The derived fields of an outcome without the stamps; of the geometry
    only the fitted proxies (the inline meshes are the snapshot's own)."""
    out = {k: v for k, v in values.items() if k != 'derivation'}
    if 'geometry' in out:
        out['geometry'] = {'proxies': [
            p for p in (out['geometry'] or {}).get('proxies') or []
            if (p.get('fit') or {}).get('method') != 'authored']}
    return out


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, default=str) \
        == json.dumps(b, sort_keys=True, default=str)


def keys_match(stored: Mapping[str, Any], wanted: Mapping[str, Any]
               ) -> Optional[str]:
    """None when the two keys are the same, else the part that differs
    (``files``, ``versions``, ``context``, ``inline``, ``shape_class`` or
    ``snapshot_id``). The shape class is compared only when the entry holds
    one: an entry that ran the stage derived its own."""
    for part in ('snapshot_id', 'inline', 'files', 'versions', 'context'):
        if not _same(stored.get(part), wanted.get(part)):
            return part
    if 'shape_class' in stored \
            and not _same(stored['shape_class'], wanted.get('shape_class')):
        return 'shape_class'
    return None


class ResultCache:
    """One folder per snapshot: ``entry.json`` (key, the fields, the stages),
    ``files/<n>`` (the deviation maps, named in the entry) and
    ``preview.webp``."""

    def __init__(self, directory: str) -> None:
        self.directory = directory

    def _folder(self, snapshot_id: str) -> str:
        return os.path.join(self.directory, str(snapshot_id))

    # WRITE -------------------------------------------------------------------
    def store(self, key: Mapping[str, Any], outcome: Outcome) -> None:
        """Replace the entry of ``key['snapshot_id']`` by this outcome, all
        or nothing: written aside, then swapped in."""
        folder = self._folder(key['snapshot_id'])
        os.makedirs(self.directory, exist_ok=True)
        staging = tempfile.mkdtemp(prefix='.new-', dir=self.directory)
        try:
            names: List[str] = []
            os.makedirs(os.path.join(staging, 'files'))
            for n, (name, data) in enumerate(outcome.write_files.items()):
                with open(os.path.join(staging, 'files', str(n)), 'wb') as h:
                    h.write(data)
                names.append(name)
            if outcome.preview is not None:
                with open(os.path.join(staging, PREVIEW), 'wb') as handle:
                    handle.write(outcome.preview)
            held = dict(key)
            if 'shape_class' in outcome.ran:
                held.pop('shape_class', None)        # it derived its own
            entry = {
                'key': held, 'ran': list(outcome.ran),
                'errors': dict(outcome.errors),
                'set': _fields(outcome.set),
                'files': names, 'preview': outcome.preview is not None,
                'timings': dict(getattr(outcome, 'timings', {}) or {}),
            }
            with open(os.path.join(staging, ENTRY), 'w',
                      encoding='utf-8') as handle:
                json.dump(entry, handle)         # a value that is not JSON fails
            if os.path.isdir(folder):
                shutil.rmtree(folder)
            os.replace(staging, folder)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    # READ --------------------------------------------------------------------
    def entry(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(self._folder(snapshot_id), ENTRY)
        try:
            with open(path, encoding='utf-8') as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def lookup(self, key: Mapping[str, Any], stages: Iterable[str]
               ) -> 'Lookup':
        """The cached result for these stages, or why there is none."""
        entry = self.entry(key['snapshot_id'])
        if entry is None:
            return Lookup(None, 'no entry')
        part = keys_match(entry['key'], key)
        if part:
            return Lookup(None, f'{part} differs')
        wanted = [s for s in STAGES if s in set(stages)]
        if any(s not in entry['ran'] for s in wanted):
            return Lookup(None, 'stages not cached')
        if any(s in entry['errors'] for s in wanted):
            return Lookup(None, 'a cached stage failed')
        return Lookup(self._outcome(entry, wanted), None)

    def _outcome(self, entry: Mapping[str, Any], stages: List[str]
                 ) -> Outcome:
        """The cached result cut down to ``stages``: their fields, the maps
        of the proxies, the preview of the previews."""
        folder = self._folder(entry['key']['snapshot_id'])
        out = Outcome()
        out.ran = list(stages)
        # a cut to ``frame`` alone would carry the whole ``descriptors`` dict
        # of the entry (the field is shared with the descriptors stage); the
        # day's run asks for the heavy stages, whose cut is exact, so the
        # shared field is only a hazard for a frame-only cut
        keys = {k for s in stages for k in FIELDS_OF_STAGE.get(s, ())}
        out.set = {k: v for k, v in entry['set'].items() if k in keys}
        if 'proxies' in stages:
            for n, name in enumerate(entry['files']):
                with open(os.path.join(folder, 'files', str(n)), 'rb') as h:
                    out.write_files[name] = h.read()
        if 'previews' in stages and entry.get('preview'):
            with open(os.path.join(folder, PREVIEW), 'rb') as handle:
                out.preview = handle.read()
        return out

    def covers(self, key: Mapping[str, Any], stages: Iterable[str]) -> bool:
        """Whether the entry for this key already holds all these stages
        (a refresh must not replace a fuller entry by a smaller one)."""
        entry = self.entry(key['snapshot_id'])
        return bool(entry) and keys_match(entry['key'], key) is None \
            and all(s in entry['ran'] for s in stages)


class Lookup:
    """A cache hit (``outcome``) or the ``reason`` for a miss."""

    def __init__(self, outcome: Optional[Outcome],
                 reason: Optional[str]) -> None:
        self.outcome = outcome
        self.reason = reason
