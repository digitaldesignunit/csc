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

``--test-accounts`` also creates one account per dataset role in one dataset
(``dev-contrib``, ``dev-mod`` = moderator and contributor, ``dev-rev``, and
``dev-mod2`` as a second person for the four-eyes checks, and ``dev-outsider``,
signed in with no role in the dataset, for the checks of what a non-member
sees) with fresh
passwords, written to ``.dev/dev-test-accounts.json`` (gitignored); nothing
but the user names is printed.

``--existing`` serves a database that is already running (``--mongo-port``)
again: no mongod, no dump, no migration, no accounts. The capture fixture
files live in a temporary directory that is gone with every stop, so both
modes restore them from the asset folder's ``meshes/<sid>/1`` (a copy, never a
move) into the new temporary ``SNAPSHOT_CAPTURE_DIR`` before serving; without
that the fixtures of the rig 404 after a restart.
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


TEST_ACCOUNTS = {
    'dev-contrib': ['contributor'],
    'dev-mod': ['moderator', 'contributor'],
    'dev-mod2': ['moderator', 'contributor'],
    'dev-rev': ['reviewer'],
    'dev-outsider': [],                   # no membership at all
}


def _test_accounts(db, dataset_id: str, out: Path) -> list:
    """One account per role in one dataset, fresh passwords each start; the
    passwords go to ``out`` (gitignored) and are never printed."""
    from datetime import datetime, timezone

    from apps.catalog.api.auth import get_password_hash
    dataset = db['datasets'].find_one({'_id': dataset_id})
    if dataset is None:
        sys.exit(f'--test-dataset: no dataset {dataset_id!r}')
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    members = list(dataset.get('members', []))
    written = {}
    for username, roles in TEST_ACCOUNTS.items():
        password = secrets.token_urlsafe(12)
        user_id = str(uuid.uuid4())
        db['users'].delete_many({'username': username})
        db['users'].insert_one({
            '_id': user_id, 'username': username,
            'email': f'{username}@example.org',
            'full_name': f'{username} (test)',
            'hashed_password': get_password_hash(password), 'role': 'user',
            'disabled': False, 'email_verified': True})
        if roles:
            members = [m for m in members if m['user_id'] != user_id]
            members.append({'user_id': user_id, 'roles': roles,
                            'added_at': now})
        written[username] = {'password': password, 'roles': roles}
    db['datasets'].update_one({'_id': dataset_id},
                              {'$set': {'members': members}})
    out.write_text(json.dumps(written, indent=1), encoding='utf-8')
    return list(written)


def restore_capture_fixtures(snapshots, assets: Path, capture: Path):
    """Copy ``meshes/<sid>/1/{detailed,reduced}.ply`` of the asset folder to
    ``capture/<sid>/fixtures/0.ply`` for every snapshot that records a
    fixture and has none there yet. The asset folder is only read. Returns
    ``(restored, already_there, missing)``."""
    restored = present = missing = 0
    for snap in snapshots:
        sid = snap['_id']
        if not (snap.get('capture') or {}).get('fixtures'):
            continue
        target = capture / sid / 'fixtures' / '0.ply'
        if target.is_file():
            present += 1
            continue
        source = next((p for p in (assets / sid / '1' / 'detailed.ply',
                                   assets / sid / '1' / 'reduced.ply')
                       if p.is_file()), None)
        if source is None:
            missing += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        restored += 1
    return restored, present, missing


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
    parser.add_argument('--test-accounts', action='store_true',
                        help='create dev-contrib, dev-mod, dev-mod2 and '
                             'dev-rev with their roles in --test-dataset, '
                             'and dev-outsider with none')
    parser.add_argument('--existing', action='store_true',
                        help='serve the database already running on '
                             '--mongo-port: no dump, no migration; only the '
                             'capture fixtures are restored')
    parser.add_argument('--work-dir', default=None,
                        help='with --existing: reuse this folder (its '
                             'proxies, capture and evidence files) instead '
                             'of a new temporary one; it is not deleted')
    parser.add_argument('--test-dataset', default='dbu_zirkus',
                        help='dataset the test accounts are members of')
    args = parser.parse_args()

    from mongod import ThrowawayMongod, find_mongod, sweep_stale_dirs
    from pymongo import MongoClient
    from support import load_dump

    from apps.catalog.api.auth import get_password_hash
    from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run

    dev = _REPO / '.dev'
    dev.mkdir(exist_ok=True)
    keep_work = bool(args.existing and args.work_dir)
    if args.existing:
        server = None
        uri = f'mongodb://127.0.0.1:{args.mongo_port}'
        if keep_work:
            work = Path(args.work_dir)
        else:
            work = Path(tempfile.mkdtemp(prefix='csc-dev-migrated-'))
            (work / 'owner.pid').write_text(str(os.getpid()), encoding='ascii')
    else:
        binary = find_mongod()
        if binary is None:
            sys.exit('no mongod binary (install MongoDB Community Server)')
        server = ThrowawayMongod(binary, port=args.mongo_port).start()
        uri = server.uri
        sweep_stale_dirs('csc-dev-migrated-')
        work = Path(tempfile.mkdtemp(prefix='csc-dev-migrated-'))
        (work / 'owner.pid').write_text(str(os.getpid()), encoding='ascii')
    env = _dev_env()
    try:
        client = MongoClient(uri)
        db = client['csc']
        mongo_uri = f'{uri}/csc'
        proxies = work / 'proxies'
        assets = Path(env.get('SNAPSHOT_MESHES_DIR', ''))
        capture = work / 'capture'
        if not args.existing:
            counts = load_dump(db, str(_REPO / 'mongodb_collections_local' /
                                       args.dump))
            print(f'loaded {args.dump}: {counts}')
            # step 6c moves meshes/<sid>/1 (the gripper): give it a copy of just
            # those folders, never the asset folder itself
            meshes = work / 'meshes'
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
            if args.test_accounts:
                names = _test_accounts(db, args.test_dataset,
                                       dev / f'dev-test-accounts{tag}.json')
                print(f'test accounts in {args.test_dataset}: {", ".join(names)} '
                      f'(passwords in .dev/dev-test-accounts{tag}.json)')
            (dev / f'dev-migrated-credentials{tag}.txt').write_text(
                f'dev-admin\n{password}\n', encoding='utf-8')
            (dev / f'migrated{tag}.json').write_text(json.dumps(
                {'mongo_uri': mongo_uri, 'backend': f'http://127.0.0.1:{args.port}'
                 }), encoding='utf-8')
            print(f'mongo {mongo_uri}; login dev-admin '
                  f'(password in .dev/dev-migrated-credentials{tag}.txt)')
        # on every start, a restart too: the temporary capture folder is
        # gone with the last stop (step 6c's files were moved into it)
        restored, present, missing = restore_capture_fixtures(
            db['component_snapshots'].find(
                {'capture.fixtures.0': {'$exists': True}},
                {'_id': 1, 'capture': 1}), assets, capture)
        print(f'capture fixtures: {restored} restored from the asset folder, '
              f'{present} there, {missing} without a file')
        client.close()

        env['MONGODB_URI'] = mongo_uri
        env['SNAPSHOT_CAPTURE_DIR'] = str(capture)
        env['SNAPSHOT_PROXIES_DIR'] = str(proxies)
        env['EVIDENCE_ATTACHMENTS_DIR'] = str(work / 'evidence')
        env.setdefault('JWT_SECRET', 'dev-migrated-only')
        env.setdefault('SMTP_PASSWORD', 'dev')
        os.environ.update(env)
        for key, value in env.items():
            if key.endswith('_DIR'):
                os.makedirs(value, exist_ok=True)
        os.chdir(_BACKEND)
        if not args.existing:
            print('building the component-map cache (main_component_map.py)...')
            subprocess.run([sys.executable, 'main_component_map.py'],
                           env=os.environ.copy(), check=False)
        import uvicorn
        uvicorn.run('main_fastapi:app', host='127.0.0.1', port=args.port)
    finally:
        if server is not None:
            server.stop()
        if not keep_work:
            shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
