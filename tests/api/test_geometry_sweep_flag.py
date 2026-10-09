"""``main_geometry.py`` sweeps orphaned previews and deviation maps only with
``--sweep`` (decision 8.121 a): a run without it deletes nothing."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

LIVE = '11111111-1111-1111-1111-111111111111'
GONE = '22222222-2222-2222-2222-222222222222'
IDENTITY = '33333333-3333-3333-3333-333333333333'


def _run(argv):
    import main_geometry
    return asyncio.run(main_geometry.run(main_geometry._parse_args(argv)))


def _world(db, backend_env):
    previews = Path(backend_env['SNAPSHOT_PREVIEW_DIR'])
    proxies = Path(backend_env['SNAPSHOT_PROXIES_DIR'])
    for folder in (previews, proxies):
        folder.mkdir(parents=True, exist_ok=True)
    (previews / f'{LIVE}.webp').write_bytes(b'x')
    (previews / f'{GONE}.webp').write_bytes(b'x')
    (proxies / GONE).mkdir(exist_ok=True)
    (proxies / GONE / '0.png').write_bytes(b'x')
    db['component_identities'].insert_one(
        {'_id': IDENTITY, 'dataset': 'dbu_zirkus', 'catalog_number': 1})
    db['component_snapshots'].insert_one(
        {'_id': LIVE, 'identity_id': IDENTITY, 'version': 0,
         'status': 'draft', 'geometry': {}})
    return previews, proxies


def test_a_run_without_sweep_deletes_nothing(db, backend_env):
    previews, proxies = _world(db, backend_env)
    _run(['--stages', 'frame'])
    assert (previews / f'{GONE}.webp').exists()
    assert (proxies / GONE / '0.png').exists()
    assert (previews / f'{LIVE}.webp').exists()


def test_with_sweep_only_the_orphans_go(db, backend_env):
    previews, proxies = _world(db, backend_env)
    _run(['--stages', 'frame', '--sweep'])
    assert not (previews / f'{GONE}.webp').exists()
    assert not (proxies / GONE).exists()
    assert (previews / f'{LIVE}.webp').exists()


def test_sweep_is_off_by_default_and_never_on_an_empty_database(db, backend_env):
    import main_geometry
    assert main_geometry._parse_args([]).sweep is False
    assert main_geometry._parse_args(['--sweep']).sweep is True
    previews = Path(backend_env['SNAPSHOT_PREVIEW_DIR'])
    previews.mkdir(parents=True, exist_ok=True)
    (previews / f'{GONE}.webp').write_bytes(b'x')
    _run(['--sweep'])                    # no snapshot in the database
    assert (previews / f'{GONE}.webp').exists()
    assert os.path.isdir(previews)
