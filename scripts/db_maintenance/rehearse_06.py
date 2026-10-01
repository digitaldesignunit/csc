"""Rehearse the 0.6 migration on a local dump (plan P2, `invoke rehearse`).

Loads a Compass JSON export (``mongodb_collections_local/<yymmdd>``) into a
throwaway ``mongod``, runs every cutover step of ``migrate_06.py``, runs
them a second time to prove they are idempotent, then checks every
invariant and prints a per-dataset report. With ``--assets`` (the asset
folder of the dump) the fixture PLY files of step 6c are moved in a
temporary copy; without it step 6c skips files. Nothing outside the
throwaway database and the temporary folder is touched.

Exit code 1 on an abort, a non-idempotent step or any invariant error.

Usage
-----
::

    python scripts/db_maintenance/rehearse_06.py --dump 260916
    python scripts/db_maintenance/rehearse_06.py --dump 260916 \\
        --assets D:\\01_PROJECT_WORKDATA\\260916_CSC_ASSETS
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / 'src' / 'backend'))
sys.path.insert(0, str(_REPO / 'tests' / 'api'))

from bson import json_util  # noqa: E402

from apps.catalog.invariants import INVARIANTS, Corpus, check_all  # noqa
from apps.catalog.migration06.mappings import MigrationAbort  # noqa: E402
from apps.catalog.migration06.steps import (  # noqa: E402
    CUTOVER_STEPS,
    Context,
    run,
)

_COLLECTIONS = {
    'identities': 'component_identities',
    'snapshots': 'component_snapshots',
    'evidence': 'component_evidence',
    'datasets': 'datasets',
    'materials': 'materials',
    'users': 'users',
}


def _fingerprint(db) -> str:
    digest = hashlib.sha256()
    for name in sorted(db.list_collection_names()):
        for doc in db[name].find({}).sort('_id', 1):
            digest.update(json_util.dumps(doc, sort_keys=True).encode())
    return digest.hexdigest()


def _copy_fixture_sources(db, assets: Path, meshes: Path) -> int:
    """Copy meshes/<sid>/1/ of every two-mesh snapshot (the only files
    step 6c touches) into the temporary meshes folder."""
    copied = 0
    for snap in db['component_snapshots'].find(
            {'geometry.meshes.1': {'$exists': True}}, {'_id': 1}):
        source = assets / 'meshes' / snap['_id'] / '1'
        if source.is_dir():
            shutil.copytree(source, meshes / snap['_id'] / '1')
            copied += 1
    return copied


def _report(db) -> None:
    identities = list(db['component_identities'].find({}))
    snaps = list(db['component_snapshots'].find({}))
    evidence = list(db['component_evidence'].find({}))
    dataset_of = {i['_id']: i['dataset'] for i in identities}
    rows = defaultdict(lambda: defaultdict(Counter))
    for i in identities:
        row = rows[i['dataset']]
        row['identities']['n'] += 1
        row['function'][i['original_function']] += 1
        row['material'][f'{i["material"]}/{i.get("trade_name")}'] += 1
        row['origin'][i['origin']['kind']] += 1
        row['exit'][(i.get('exit') or {}).get('kind', 'none')] += 1
        row['inherited'][len(i.get('inherited_fields') or [])] += 1
    for s in snaps:
        row = rows[dataset_of[s['identity_id']]]
        row['snapshots'][s['status']] += 1
        capture = s.get('capture') or {}
        row['capture'][f'markers={len(capture.get("markers") or []) > 0} '
                       f'fixtures={len(capture.get("fixtures") or [])}'] += 1
        geo = s['geometry']
        row['geometry'][f'meshes={len(geo.get("meshes") or [])} '
                        f'proxies={len(geo.get("proxies") or [])}'] += 1
        row['effective_from'][s['effective_from_precision']] += 1
    for e in evidence:
        rows[dataset_of[e['identity_id']]]['evidence'][e['method']] += 1
    for dataset in sorted(rows):
        print(f'\n{dataset}')
        for key, counter in rows[dataset].items():
            print(f'  {key:15s} {dict(sorted(counter.items(), key=str))}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dump', default='261001',
                        help='folder name under mongodb_collections_local, '
                             'or a path')
    parser.add_argument('--assets', type=Path,
                        help='asset folder of the dump (meshes/...)')
    parser.add_argument('--limit', type=int, default=5,
                        help='violations printed per invariant')
    parser.add_argument('--mapping', type=Path,
                        help='also run step 11b with this (untracked) '
                             'mapping file after the cutover steps')
    args = parser.parse_args()

    dump = Path(args.dump)
    if not dump.is_dir():
        dump = _REPO / 'mongodb_collections_local' / args.dump
    if not dump.is_dir():
        sys.exit(f'no dump folder {args.dump}')

    from mongod import ThrowawayMongod, find_mongod
    from pymongo import MongoClient
    from support import load_dump
    binary = find_mongod()
    if binary is None:
        sys.exit('no mongod binary (install MongoDB Community Server or set '
                 'MONGOD_BIN)')
    server = ThrowawayMongod(binary).start()
    workdir = Path(tempfile.mkdtemp(prefix='csc-rehearse-'))
    try:
        client = MongoClient(server.uri)
        db = client['csc']
        counts = load_dump(db, str(dump))
        print(f'loaded {dump.name}: {counts}')
        meshes, capture = workdir / 'meshes', workdir / 'capture'
        meshes.mkdir()
        files = args.assets is not None
        if files:
            copied = _copy_fixture_sources(db, args.assets, meshes)
            print(f'copied {copied} fixture mesh folders from {args.assets}')
        ctx = Context(db=db, meshes_dir=meshes, capture_dir=capture,
                      archive_dir=workdir / 'archive', files=files)
        try:
            run(ctx, CUTOVER_STEPS)
            before = _fingerprint(db)
            print('\nsecond run (must change nothing)')
            run(Context(db=db, meshes_dir=meshes, capture_dir=capture,
                        archive_dir=workdir / 'archive', files=files,
                        log=lambda _m: None), CUTOVER_STEPS)
        except MigrationAbort as exc:
            print(f'ABORTED: {exc}', file=sys.stderr)
            return 1
        idempotent = _fingerprint(db) == before
        print(f'idempotent: {idempotent}')
        if args.mapping:
            print('\nstep 11b with the mapping')
            try:
                run(Context(db=db, files=False, shared_mapping=json.loads(
                    args.mapping.read_text(encoding='utf-8'))), ['11b'])
            except MigrationAbort as exc:
                print(f'ABORTED: {exc}', file=sys.stderr)
                return 1
        if files:
            fixtures = sorted(capture.glob('*/fixtures/0.ply'))
            print(f'fixture files: {len(fixtures)}')

        corpus = Corpus(**{attr: list(db[name].find({}))
                           for attr, name in _COLLECTIONS.items()})
        violations = check_all(corpus)
        grouped = defaultdict(list)
        for v in violations:
            grouped[v.invariant].append(v)
        print()
        for inv_id in [inv.id for inv in INVARIANTS] + ['schema']:
            for v in grouped.get(inv_id, [])[:args.limit]:
                print(f'  {inv_id} [{v.severity}] {v.collection} '
                      f'{v.doc_id}: {v.message}')
            if len(grouped.get(inv_id, [])) > args.limit:
                print(f'  {inv_id}: ... {len(grouped[inv_id])} in all')
        errors = sum(v.severity == 'error' for v in violations)
        print(f'invariants: {errors} errors, '
              f'{len(violations) - errors} warnings')
        _report(db)
        client.close()
        return 0 if idempotent and not errors else 1
    finally:
        server.stop()
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
