"""Serve a migrated copy of a local dump for frontend work (`invoke dev-migrated`).

Starts a throwaway ``mongod``, loads ``mongodb_collections_local/<dump>``,
runs the 0.6 migration, derives frame, shape class, proxies (with deviation
maps) and complexity with the geometry runner (steps 5 and 7 of the spec;
``--no-derive`` skips it, the web app then has no frames), builds the
component-map cache, adds a local admin account and serves the backend on it with ``src/backend/dev.env``. The asset
folders are only read: step 6c moves the gripper meshes out of a temporary
copy into a temporary ``SNAPSHOT_CAPTURE_DIR``. Your usual database is not
touched; everything is gone when the script stops (Ctrl+C).

The database listens on a fixed port (``--mongo-port``, default 27018), so
the frontend only needs its NextAuth database pointed there::

    $env:MONGODB_URI = 'mongodb://127.0.0.1:27018/csc'
    npm run dev          # in src/frontend; FASTAPI_URL from .env.development.local

The admin account (``dev-admin``) and its generated password are written to
``.dev/dev-migrated-credentials.txt`` (gitignored).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / 'src' / 'backend'
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_REPO / 'tests' / 'api'))

_PATH_KEYS = ('_DIR', 'CLIENT_LOG_PATH')


def _dev_env() -> dict:
    env = {}
    path = _BACKEND / 'dev.env'
    if not path.is_file():
        sys.exit('src/backend/dev.env not found: copy dev.env.example first')
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = (part.strip() for part in line.split('=', 1))
        if key.endswith(_PATH_KEYS) and not os.path.isabs(value):
            value = str((_REPO / value).resolve())
        env[key] = value
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dump', default='261001')
    parser.add_argument('--port', type=int, default=8000,
                        help='backend port (default 8000)')
    parser.add_argument('--mongo-port', type=int, default=27018,
                        help='throwaway mongod port (default 27018)')
    parser.add_argument('--no-derive', action='store_true',
                        help='do not run the geometry runner')
    parser.add_argument('--derive-stages',
                        default='frame,shape_class,proxies,complexity',
                        help='stages of the geometry runner to run (the '
                             'descriptors and previews take much longer)')
    args = parser.parse_args()

    from mongod import ThrowawayMongod, find_mongod, sweep_stale_dirs
    from pymongo import MongoClient
    from support import load_dump

    from apps.catalog.api.auth import get_password_hash
    from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run

    binary = find_mongod()
    if binary is None:
        sys.exit('no mongod binary (install MongoDB Community Server)')
    server = ThrowawayMongod(binary, port=args.mongo_port).start()
    dev = _REPO / '.dev'
    dev.mkdir(exist_ok=True)
    sweep_stale_dirs('csc-dev-migrated-')
    work = Path(tempfile.mkdtemp(prefix='csc-dev-migrated-'))
    (work / 'owner.pid').write_text(str(os.getpid()), encoding='ascii')
    env = _dev_env()
    try:
        client = MongoClient(server.uri)
        db = client['csc']
        counts = load_dump(db, str(_REPO / 'mongodb_collections_local' /
                                   args.dump))
        print(f'loaded {args.dump}: {counts}')
        # step 6c moves meshes/<sid>/1 (the gripper): give it a copy of just
        # those folders, never the asset folder itself
        meshes, capture = work / 'meshes', work / 'capture'
        assets = Path(env.get('SNAPSHOT_MESHES_DIR', ''))
        copied = 0
        for snap in db['component_snapshots'].find(
                {'geometry.meshes.1': {'$exists': True}}, {'_id': 1}):
            source = assets / snap['_id'] / '1'
            if source.is_dir():
                shutil.copytree(source, meshes / snap['_id'] / '1')
                copied += 1
        run(Context(db=db, meshes_dir=meshes, capture_dir=capture,
                    archive_dir=work / 'archive', log=lambda m: None),
            CUTOVER_STEPS)
        print(f'migrated to 0.6 ({copied} gripper meshes -> {capture})')
        # the untracked owner mapping (decisions 8.24-8.27), when present
        mapping = dev / 'reattribute_06.json'
        if mapping.is_file():
            run(Context(db=db, files=False, log=lambda m: None,
                        shared_mapping=json.loads(
                            mapping.read_text(encoding='utf-8'))), ['11b'])
            print('step 11b applied (.dev/reattribute_06.json)')

        proxies = work / 'proxies'
        if not args.no_derive:
            from apps.catalog.geometry_runner import derive_and_store_sync
            from apps.catalog.geometry_stages import Env
            stages = [s for s in args.derive_stages.split(',') if s]
            runner_env = Env(
                meshes_dir=env.get('SNAPSHOT_MESHES_DIR'),
                point_clouds_dir=env.get('SNAPSHOT_POINT_CLOUDS_DIR'),
                preview_dir=env.get('SNAPSHOT_PREVIEW_DIR')
                if 'previews' in stages else None)
            identities = {i['_id']: i
                          for i in db['component_identities'].find({})}
            todo = list(db['component_snapshots'].find({}))
            print(f'geometry runner ({", ".join(stages)}) on {len(todo)} '
                  f'snapshots...')
            for n, snap in enumerate(todo, 1):
                derive_and_store_sync(
                    db['component_snapshots'], snap,
                    identities[snap['identity_id']], runner_env, str(proxies),
                    stages, force=True)
                if n % 100 == 0:
                    print(f'  {n} / {len(todo)}')

        password = secrets.token_urlsafe(12)
        db['users'].insert_one({
            '_id': str(uuid.uuid4()), 'username': 'dev-admin',
            'email': 'dev-admin@example.org', 'full_name': 'Dev Admin',
            'hashed_password': get_password_hash(password), 'role': 'admin',
            'disabled': False, 'email_verified': True})
        # a second instance (another --port) never overwrites the first's files
        tag = '' if args.port == 8000 else f'-{args.port}'
        (dev / f'dev-migrated-credentials{tag}.txt').write_text(
            f'dev-admin\n{password}\n', encoding='utf-8')
        mongo_uri = f'{server.uri}/csc'
        (dev / f'migrated{tag}.json').write_text(json.dumps(
            {'mongo_uri': mongo_uri, 'backend': f'http://127.0.0.1:{args.port}'
             }), encoding='utf-8')
        print(f'mongo {mongo_uri}; login dev-admin '
              f'(password in .dev/dev-migrated-credentials{tag}.txt)')
        client.close()

        env['MONGODB_URI'] = mongo_uri
        env['SNAPSHOT_CAPTURE_DIR'] = str(capture)
        env['SNAPSHOT_PROXIES_DIR'] = str(proxies)
        env.setdefault('JWT_SECRET', 'dev-migrated-only')
        env.setdefault('SMTP_PASSWORD', 'dev')
        os.environ.update(env)
        for key, value in env.items():
            if key.endswith('_DIR'):
                os.makedirs(value, exist_ok=True)
        os.chdir(_BACKEND)
        print('building the component-map cache (main_component_map.py)...')
        subprocess.run([sys.executable, 'main_component_map.py'],
                       env=os.environ.copy(), check=False)
        import uvicorn
        uvicorn.run('main_fastapi:app', host='127.0.0.1', port=args.port)
    finally:
        server.stop()
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
