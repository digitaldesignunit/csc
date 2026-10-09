"""``scripts/dev/serve_migrated.py`` restores the capture fixture files on
every start (P12 preparation): copied from the asset folder, never moved, and
only where a snapshot records a fixture and the file is missing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'dev'))

from serve_migrated import restore_capture_fixtures  # noqa: E402

WITH = {'_id': 'a1', 'capture': {'fixtures': [{'label': 'end_effector',
                                              'file': 'capture/a1/fixtures/0.ply'}]}}


def _asset(assets: Path, sid: str, name: str = 'detailed.ply', data=b'ply-a'):
    folder = assets / sid / '1'
    folder.mkdir(parents=True)
    (folder / name).write_bytes(data)


def test_a_missing_fixture_is_copied_and_the_asset_stays(tmp_path):
    assets, capture = tmp_path / 'assets', tmp_path / 'capture'
    _asset(assets, 'a1')
    assert restore_capture_fixtures([WITH], assets, capture) == (1, 0, 0)
    assert (capture / 'a1' / 'fixtures' / '0.ply').read_bytes() == b'ply-a'
    assert (assets / 'a1' / '1' / 'detailed.ply').is_file()      # read-only use


def test_the_second_start_finds_it_there_and_a_reduced_file_is_the_fallback(tmp_path):
    assets, capture = tmp_path / 'assets', tmp_path / 'capture'
    _asset(assets, 'a1', 'reduced.ply', b'ply-r')
    assert restore_capture_fixtures([WITH], assets, capture) == (1, 0, 0)
    assert restore_capture_fixtures([WITH], assets, capture) == (0, 1, 0)
    assert (capture / 'a1' / 'fixtures' / '0.ply').read_bytes() == b'ply-r'


def test_no_asset_is_counted_and_a_snapshot_without_fixtures_is_skipped(tmp_path):
    assets, capture = tmp_path / 'assets', tmp_path / 'capture'
    plain = {'_id': 'b2', 'capture': {'fixtures': []}}
    assert restore_capture_fixtures([WITH, plain, {'_id': 'c3'}], assets,
                                    capture) == (0, 0, 1)
    assert not capture.exists()
