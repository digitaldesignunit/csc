"""Run the geometry runner on the imported ReCreate snapshots of a LOCAL test instance.

    python derive_local.py [--mongo-uri URI] [--db csc] [--assets DIR]
                           [--stages frame,shape_class,proxies,descriptors,complexity,previews] [--limit N]

Rehearsal only: the database is the throwaway mongod of scripts/dev/serve_migrated.py (any host that is not
this machine is refused), and the files go to the asset copy `--assets` of that instance, which must be
inside `.dev/` (the tool writes into it: a copy, never the original asset folders). In production the
cron of decision 8.136 does this (`main_geometry.py --due`). No sweep: nothing is deleted. Run in the `csc`
environment (backend packages and pymongo).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recreate_common as common  # noqa: E402

sys.path.insert(0, str(common.REPO / 'src' / 'backend'))
from apps.catalog.geometry_runner import derive_and_store_sync  # noqa: E402
from apps.catalog.geometry_stages import STAGES, Env  # noqa: E402
from pymongo import MongoClient  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Derive the imported ReCreate snapshots on a local instance.')
    parser.add_argument('--mongo-uri', default=common.DEFAULT_MONGO_URI,
                        help='the local test database (default: the local rehearsal)')
    parser.add_argument('--db', default='csc')
    parser.add_argument('--assets', type=Path, default=common.DEFAULT_ASSETS,
                        help='the instance\'s asset folder (meshes, pointclouds, proxies, snapshot_previews)')
    parser.add_argument('--stages', default=','.join(STAGES))
    parser.add_argument('--limit', type=int)
    args = parser.parse_args(argv)
    common.require_local(args.mongo_uri)
    assets = common.require_dot_dev(args.assets, '--assets')
    db = MongoClient(args.mongo_uri)[args.db]
    stages = [s for s in args.stages.split(',') if s]
    env = Env(meshes_dir=str(assets / 'meshes'), point_clouds_dir=str(assets / 'pointclouds'),
              preview_dir=str(assets / 'snapshot_previews') if 'previews' in stages else None)
    identities = {i['_id']: i for i in db['component_identities'].find(
        {'attributes.recreate': {'$exists': True}})}
    todo = list(db['component_snapshots'].find({'identity_id': {'$in': list(identities)}}))
    if args.limit:
        todo = todo[:args.limit]
    print(f'{len(todo)} snapshots, stages {", ".join(stages)}', flush=True)
    start, errors = time.time(), 0
    for n, snap in enumerate(todo, 1):
        outcome = derive_and_store_sync(db['component_snapshots'], snap, identities[snap['identity_id']],
                                        env, str(assets / 'proxies'), stages)
        errors += bool(getattr(outcome, 'errors', None))
        if n % 100 == 0 or n == len(todo):
            print(f'  {n} / {len(todo)} ({time.time() - start:.0f} s, {errors} with errors)', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
