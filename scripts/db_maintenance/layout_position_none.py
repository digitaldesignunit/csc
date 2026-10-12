"""Convert stored reinforcement layouts from position.kind region to none.

Decision 8.142 c: a layout's ``position.kind`` is ``none`` together with the
``snapshot_id`` (the bars carry their own positions in the stored coordinates
of that version); the web form sent ``region`` until now, Grasshopper ``none``.
This changes the kind of the layouts that still say ``region`` and nothing
else: the snapshot id and the description stay.

Idempotent. A dry run by default: it reports what it would change and writes
nothing; ``--apply`` writes. Each changed record gets its lastmodified and etag
renewed and one change-log entry (cause ``migration``).

    python scripts/db_maintenance/layout_position_none.py --uri <mongodb uri>
    python scripts/db_maintenance/layout_position_none.py --uri <uri> --apply

The uri can also come from the MONGO_URI environment variable.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_BACKEND = os.getenv('CSC_BACKEND_DIR') or str(_REPO / 'src' / 'backend')
sys.path.insert(0, _BACKEND)

from apps.catalog.etag import compute_snapshot_etag  # noqa: E402
from apps.catalog.history import diff  # noqa: E402

QUERY = {'method': 'reinforcement_layout', 'position.kind': 'region'}


def convert(db, apply: bool = False, now: str | None = None) -> dict:
    """The layouts with ``position.kind: region`` as ``none``; returns
    ``{'found': n, 'changed': n, 'ids': [...]}`` (``changed`` is 0 in a dry
    run)."""
    stamp = now or datetime.now(timezone.utc).isoformat().replace(
        '+00:00', 'Z')
    ids, changed = [], 0
    for before in db['component_evidence'].find(QUERY):
        ids.append(before['_id'])
        if not apply:
            continue
        after = copy.deepcopy(before)
        after['position'] = {**after['position'], 'kind': 'none'}
        after['lastmodified'] = stamp
        after['etag'] = compute_snapshot_etag(after)
        result = db['component_evidence'].replace_one(
            {'_id': before['_id'], 'etag': before.get('etag')}, after)
        if not result.matched_count:
            continue                      # changed meanwhile: run again
        changed += 1
        db['change_log'].insert_one({
            '_id': str(uuid.uuid4()), 'record_kind': 'evidence',
            'record_id': before['_id'], 'identity_id': before['identity_id'],
            'at': stamp, 'by_user_id': None, 'cause': 'migration',
            'source_record_id': None,
            'changes': diff('evidence', before, after)})
    return {'found': len(ids), 'changed': changed, 'ids': ids}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--uri', default=os.getenv('MONGO_URI'))
    parser.add_argument('--db', default='csc')
    parser.add_argument('--apply', action='store_true',
                        help='write the change (default: a dry run)')
    args = parser.parse_args()
    if not args.uri:
        print('--uri (or MONGO_URI) is required', file=sys.stderr)
        return 2
    from pymongo import MongoClient
    db = MongoClient(args.uri)[args.db]
    report = convert(db, apply=args.apply)
    mode = 'applied' if args.apply else 'dry run, nothing written'
    print(f'layouts with position.kind region: {report["found"]} '
          f'({mode}); changed {report["changed"]}')
    for record_id in report['ids']:
        print(f'  {record_id}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
