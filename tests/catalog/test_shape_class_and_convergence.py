"""Shape class order (8.56) and the runner's convergence (8.46, 8.54)."""

from __future__ import annotations

import copy

import pytest
import trimesh

import apps.catalog.geometry_stages as stages_mod
from apps.catalog.documents import ComponentSnapshot
from apps.catalog.geometry_stages import (
    STAGES,
    Env,
    run_stages,
    short_error,
    server_stages,
    stale_stages,
)
from apps.catalog.shape_class import derive_shape_class
from test_geometry_stages import IDENTITY, apply, inline_mesh, snapshot


# SHAPE CLASS -----------------------------------------------------------------
def test_elongation_is_tested_before_the_hull_score():
    # an elongated piece with an uneven hull is still linear
    assert derive_shape_class((3000, 200, 150), boxscore=45) == 'linear'
    # a flat one is still planar
    assert derive_shape_class((600, 400, 18), boxscore=45) == 'planar'
    # only compact pieces can be irregular
    assert derive_shape_class((300, 250, 200), boxscore=45) == 'irregular'
    assert derive_shape_class((300, 250, 200), boxscore=5) == 'block'
    assert derive_shape_class((300, 250, 200), boxscore=None) == 'block'


def test_thresholds_start_at_three_for_elongation():
    assert derive_shape_class((300, 100, 90), 0) == 'linear'     # 3.0
    assert derive_shape_class((299, 100, 90), 0) == 'block'
    assert derive_shape_class((300, 300, 100), 0) == 'planar'    # 3.0


# CONVERGENCE -----------------------------------------------------------------
def failing_preview(monkeypatch):
    def boom(_work):
        raise OSError('/srv/csc/previews/x.webp: disk full')
    monkeypatch.setattr(stages_mod, '_stage_previews', boom)


def sweep(doc, env=Env(), stages=STAGES, **kwargs):
    outcome = run_stages(doc, IDENTITY, env, stages, **kwargs)
    return apply(doc, outcome), outcome


def test_a_failing_frame_blocks_what_reads_it_and_converges():
    doc = snapshot({'meshes': [], 'proxies': []})
    first, outcome = sweep(doc)
    assert outcome.ran == ['frame', 'previews'] or 'frame' in outcome.ran
    assert 'frame' in outcome.errors
    # nothing downstream was run or stamped
    assert set(first['derivation']) <= {'frame', 'previews'}
    assert stale_stages(first, IDENTITY, Env()) == []
    second, again = sweep(first)
    assert again.ran == [] and not again.errors
    assert second == first
    # an explicit retry runs the failed stage once more
    assert 'frame' in run_stages(first, IDENTITY, Env(), force=False,
                                 retry_errors=True).ran


def test_a_failing_preview_is_current_until_retried(monkeypatch, tmp_path):
    failing_preview(monkeypatch)
    mesh = trimesh.creation.box(extents=(300, 200, 150))
    env = Env(preview_dir=str(tmp_path))
    doc = snapshot({'meshes': [inline_mesh(mesh)]})
    first, outcome = sweep(doc, env)
    assert 'previews' in outcome.errors
    assert outcome.errors['previews'].startswith('OSError')
    # the second pass does nothing: no write, no new error
    assert stale_stages(first, IDENTITY, env) == []
    second, again = sweep(first, env)
    assert again.ran == [] and not again.errors and not again.changed
    assert stale_stages(first, IDENTITY, env, retry_errors=True) == [
        'previews']
    assert 'previews' in run_stages(first, IDENTITY, env,
                                    retry_errors=True).ran


def test_a_missing_output_counts_as_stale(tmp_path):
    mesh = trimesh.creation.box(extents=(300, 200, 150))
    env = Env(preview_dir=str(tmp_path))
    doc = snapshot({'meshes': [inline_mesh(mesh)]})
    done, first = sweep(doc, env)
    (tmp_path / 's1.webp').write_bytes(first.preview)     # the caller's job
    assert stale_stages(done, IDENTITY, env) == []
    cleared = {**done, 'complexity': None}
    assert stale_stages(cleared, IDENTITY, env) == ['complexity']
    fixed, _ = sweep(cleared, env)
    assert fixed['complexity'] is not None
    (tmp_path / 's1.webp').unlink()
    assert stale_stages(fixed, IDENTITY, env) == ['previews']


def test_stored_errors_are_short_and_carry_no_paths():
    exc = FileNotFoundError(2, 'No such file',
                            '/home/acct/html/csc_assets/meshes/s/0/x.ply')
    text = short_error(exc)
    assert '/home' not in text and '<path>' in text
    win = short_error(OSError(r'C:\Users\x\assets\a.ply failed'))
    assert 'Users' not in win
    assert len(short_error(ValueError('x' * 1000))) <= 160


def test_the_heavy_stage_setting(monkeypatch):
    monkeypatch.delenv('CSC_GEOMETRY_HEAVY_STAGES', raising=False)
    assert server_stages() == STAGES
    monkeypatch.setenv('CSC_GEOMETRY_HEAVY_STAGES', 'remote')
    assert server_stages() == ('frame', 'shape_class')
    monkeypatch.setenv('CSC_GEOMETRY_HEAVY_STAGES', 'cloud')
    with pytest.raises(ValueError):
        server_stages()


def test_a_snapshot_after_failures_is_still_a_valid_document():
    doc = snapshot({'meshes': [], 'proxies': []})
    done, _ = sweep(copy.deepcopy(doc))
    # geometry is empty on purpose: the model refuses it (I1), the stamps
    # themselves are well formed
    assert done['derivation']['frame']['error']
    assert ComponentSnapshot.model_fields['derivation']


# RE-REVIEW RESIDUALS (decisions 8.58--8.60) ----------------------------------
def test_the_stronger_elongation_decides_when_both_tests_pass():
    # a long thin strip: e1/e2 3.3, e2/e3 25 --> planar (8.58)
    assert derive_shape_class((500, 150, 6), boxscore=0) == 'planar'
    # a batten: e1/e2 20, e2/e3 5 --> linear
    assert derive_shape_class((2000, 100, 20), boxscore=0) == 'linear'
    # a beam and a slab pass one test only
    assert derive_shape_class((4000, 300, 250), boxscore=0) == 'linear'
    assert derive_shape_class((1200, 800, 40), boxscore=0) == 'planar'
    # a sheet without thickness is planar, a thread without width linear
    assert derive_shape_class((500, 300, 0), boxscore=None) == 'planar'
    assert derive_shape_class((500, 0, 0), boxscore=None) == 'linear'


def test_thresholds_are_frozen_with_their_stage_versions():
    from apps.catalog import complexity, shape_class
    assert (shape_class.T_LINEAR, shape_class.T_PLANAR,
            shape_class.T_IRREGULAR) == (3.0, 3.0, 25.0)
    assert tuple(complexity.T_RESIDUAL) == (0.005, 0.05, 0.12)
    assert tuple(complexity.T_BOXSCORE) == (5.0, 15.0, 45.0)
    assert shape_class.SHAPE_CLASS_VERSION == 3
    assert complexity.COMPLEXITY_VERSION == 2


def test_windows_and_unc_paths_with_spaces_are_replaced():
    cases = [
        OSError(r"[Errno 2] No such file: 'C:\Users\Max Muster\My Assets\a b.ply'"),
        OSError(r'C:\Program Files\csc\a b.ply: access denied'),
        OSError(r"cannot open '\\fileserver\share name\csc\a.ply'"),
        OSError(r'\\fileserver\share name\csc\a.ply: gone'),
        OSError("[Errno 2] No such file: '/home/some user/csc assets/a.ply'"),
    ]
    for exc in cases:
        text = short_error(exc)
        assert '<path>' in text, text
        for leak in ('Muster', 'Program Files', 'fileserver', 'some user',
                     'csc assets', 'Users'):
            assert leak not in text, text


def test_the_derivation_is_never_in_the_change_log():
    from apps.catalog.history import NOT_LOGGED, as_of, diff
    assert 'derivation' in NOT_LOGGED['snapshot']
    before = {'_id': 's', 'shape_class': 'block',
              'shape_class_source': 'derived',
              'derivation': {'frame': {'version': 1}}}
    after = {**before, 'shape_class': 'linear',
             'shape_class_source': 'assigned',
             'derivation': {}}
    paths = sorted(c['path'] for c in diff('snapshot', before, after))
    assert paths == ['shape_class', 'shape_class_source']
    rolled = as_of('snapshot', after, [], '2026-01-01T00:00:00Z')
    assert 'derivation' not in rolled


def test_urls_are_replaced_whole_and_plain_slashes_are_left_alone():
    for url in ('http://host.example/a/b', 'https://host:8000/x/y?q=1'):
        text = short_error(OSError(f'GET {url} failed'))
        assert '<url>' in text and 'host' not in text and 'htt<' not in text
    assert short_error(OSError(r"open 'C:\Users\Some One\a b.ply'")).count(
        '<path>') == 1
    assert 'Some One' not in short_error(
        OSError(r"open 'C:\Users\Some One\a b.ply'"))
    assert 'srv' not in short_error(OSError(r'\\srv\share x\a.ply: gone'))
    posix = short_error(OSError("No such file: '/home/some user/a b/c.ply'"))
    assert 'some user' not in posix and '<path>' in posix
    for plain in ('ratio 3/4 exceeded', 'and/or', 'a/b/c split',
                  'size 2/3 of range'):
        assert short_error(ValueError(plain)).endswith(plain), plain
