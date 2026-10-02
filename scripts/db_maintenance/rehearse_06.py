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
from apps.catalog.geometry_runner import derive_and_store_sync  # noqa: E402
from apps.catalog.geometry_stages import Env, stale_stages  # noqa: E402

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


def _axis_order(old: dict, new: dict) -> tuple:
    """For each new frame axis x / y / z: which old axis it follows."""
    import numpy as np
    old_axes = np.array([old['x'], old['y'], old['z']], dtype=float)
    new_axes = np.array([new['x'], new['y'], new['z']], dtype=float)
    return tuple(int(np.abs(old_axes @ axis).argmax()) for axis in new_axes)


def _run_runner_steps(db, assets, workdir, stages_filter, tuning_path,
                      frame_report_path):
    """Steps 5, 7 and 8 of the spec (section 8.1): the geometry runner on
    the migrated database, in a throwaway storage folder."""
    import time
    from collections import Counter, defaultdict
    identities = {i['_id']: i for i in db['component_identities'].find({})}
    snapshots = db['component_snapshots']
    old_frames = {s['_id']: s.get('pca_frame')
                  for s in snapshots.find({}, {'pca_frame': 1})}
    env = Env(meshes_dir=str(assets / 'meshes') if assets else None,
              point_clouds_dir=str(assets / 'pointclouds') if assets else None,
              preview_dir=str(workdir / 'previews'),
              log=lambda m: None)
    proxies_root = str(workdir / 'proxies')

    def sweep(title, stages, force):
        began, ran, errors = time.time(), 0, Counter()
        for snap in snapshots.find({}).sort('_id', 1):
            identity = identities[snap['identity_id']]
            if not force and not stale_stages(snap, identity, env, stages):
                continue
            outcome = derive_and_store_sync(
                snapshots, snap, identity, env, proxies_root, stages,
                force=force)
            ran += 1
            for stage, message in outcome.errors.items():
                errors[(stage, message[:90])] += 1
        print(f'{title}: {ran} snapshots, {time.time() - began:.0f} s, '
              f'{sum(errors.values())} stage errors')
        for (stage, message), n in errors.most_common(8):
            print(f'    {n:4d} x {stage}: {message}')
        return errors

    print('\nstep 5  main_geometry.py --stages frame,shape_class --recompute')
    errors = sweep('frame + shape class', ['frame', 'shape_class'], True)
    changed = defaultdict(Counter)
    order_changes, upside_down = [], []
    for snap in snapshots.find({}, {'frame': 1, 'identity_id': 1}):
        old, new = old_frames.get(snap['_id']), snap.get('frame')
        dataset = identities[snap['identity_id']]['dataset']
        if new and new['z'][2] < 0:
            upside_down.append((dataset, snap['_id'], new['z'][2]))
        if not old or not new:
            continue
        order = _axis_order(old, new)
        changed[dataset]['same' if order == (0, 1, 2) else 'changed'] += 1
        if order != (0, 1, 2):
            order_changes.append((dataset, snap['_id'], order))
    print('frame report (axis order against the 0.5 pca_frame):')
    for dataset in sorted(changed):
        print(f'  {dataset:28s} {dict(changed[dataset])}')
    print(f'canonical z against the stored z (z . Z < 0): '
          f'{len(upside_down)} snapshots')
    lines = ['FRAME REPORT', '',
             f'axis order changed against the 0.5 pca_frame: '
             f'{len(order_changes)}']
    lines += [f'  {d:28s} {i}  new x/y/z follow old axes {o}'
              for d, i, o in sorted(order_changes)]
    lines += ['', f'canonical z against the stored z (z . Z < 0): '
                  f'{len(upside_down)}']
    lines += [f'  {d:28s} {i}  z . Z = {z:.3f}'
              for d, i, z in sorted(upside_down)]
    frame_report_path.parent.mkdir(parents=True, exist_ok=True)
    frame_report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'frame report: {frame_report_path}')
    print('\nstep 7  main_geometry.py --stages proxies,descriptors,'
          'complexity,previews --recompute')
    errors += sweep('proxies, descriptors, complexity, previews',
                    ['proxies', 'descriptors', 'complexity', 'previews'],
                    True)
    print('\nstep 8  after tuning: an ordinary sweep (nothing may be stale)')
    sweep('sweep', list(stages_filter), False)
    left = [s['_id'] for s in snapshots.find({})
            if stale_stages(s, identities[s['identity_id']], env,
                            list(stages_filter))]
    print(f'stale snapshots after step 8: {len(left)}')
    if left:
        errors[('stale after step 8', 'sweep did not converge')] += len(left)
    summary = defaultdict(lambda: defaultdict(Counter))
    for snap in snapshots.find({}):
        dataset = identities[snap['identity_id']]['dataset']
        row = summary[dataset]
        row['shape_class'][snap.get('shape_class')] += 1
        primary = [p for p in snap['geometry'].get('proxies') or []
                   if p.get('role') == 'primary']
        row['primary'][(primary[0]['primitive'] + '/'
                        + primary[0]['fit']['method']) if primary
                       else None] += 1
        row['complexity'][snap.get('complexity')] += 1
    print('\nderived, per dataset')
    for dataset in sorted(summary):
        print(f'  {dataset}')
        for key, counter in summary[dataset].items():
            print(f'    {key:12s} {dict(sorted(counter.items(), key=str))}')
    sys.path.insert(0, str(_REPO / 'scripts' / 'dev'))
    from tune_geometry import collect, report
    text = report(collect(snapshots.find({}), identities))
    tuning_path.parent.mkdir(parents=True, exist_ok=True)
    tuning_path.write_text(text + '\n', encoding='utf-8')
    print(f'\ntuning tables (shape class, complexity): {tuning_path}')
    return errors


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
    parser.add_argument('--no-runner', action='store_true',
                        help='skip steps 5, 7, 8 (the geometry runner)')
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
        runner_errors = None
        if not args.no_runner:
            runner_errors = _run_runner_steps(
                db, args.assets, workdir, ['frame', 'shape_class', 'proxies',
                                           'descriptors', 'complexity',
                                           'previews'],
                _REPO / '.dev' / f'tuning_{dump.name}.txt',
                _REPO / '.dev' / f'frame_report_{dump.name}.txt')

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
        bad = bool(runner_errors)
        return 0 if idempotent and not errors and not bad else 1
    finally:
        server.stop()
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
