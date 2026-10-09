"""The geometry runner's stages over one snapshot (spec 4.3, decision 8.7)."""

from __future__ import annotations

import copy

import numpy as np
import pytest
import trimesh

from apps.catalog.documents import ComponentSnapshot
from apps.catalog.geometry_stages import (
    STAGES,
    Env,
    run_stages,
    stale_stages,
)
from apps.catalog.proxies.primitives import prism_mesh

NOW = '2026-10-02T00:00:00Z'
IDENTITY = {'_id': 'i1', 'original_function': 'IfcSlab'}


def snapshot(geometry, **extra):
    doc = {
        '_id': 's1', 'identity_id': 'i1', 'version': 0, 'status': 'draft',
        'effective_from': NOW, 'geometry': geometry, 'descriptors': {},
        'shape_class': None, 'shape_class_source': None,
        'complexity': None, 'complexity_source': None, 'frame': None,
        'bbx': None, 'properties': {}, 'added_by_user_id': 'u',
        'created': NOW, 'lastmodified': NOW, 'color': [200, 200, 200],
        'etag': 'x',
    }
    doc.update(extra)
    return doc


def authored_prism(profile, height):
    return {'primitive': 'prism', 'role': 'primary',
            'params': {'profile': profile, 'holes': None, 'height': height},
            'placement': {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0],
                          'z': [0, 0, 1]},
            'fit': {'method': 'authored'}, 'deviation_maps': None,
            'regions': []}


def inline_mesh(mesh: trimesh.Trimesh):
    return {'vertices': mesh.vertices.tolist(), 'faces': mesh.faces.tolist()}


def apply(doc, outcome):
    merged = {**doc, **copy.deepcopy(outcome.set)}
    for key in outcome.unset:
        merged.pop(key, None)
    return merged


ENV = Env()
PLATE = [[0, 0], [600, 0], [600, 400], [300, 400], [300, 200], [0, 200]]


def test_authored_plate_gets_every_stage():
    doc = snapshot({'proxies': [authored_prism(PLATE, 18)]},
                   pca_frame={'o': [0, 0, 0], 'x': [1, 0, 0],
                              'y': [0, 1, 0], 'z': [0, 0, 1]},
                   bbx_origin=[0, 0, 0])
    outcome = run_stages(doc, IDENTITY, ENV)
    done = apply(doc, outcome)
    assert outcome.ran == ['frame', 'shape_class', 'descriptors',
                           'complexity', 'previews'] or \
        set(outcome.ran) >= {'frame', 'shape_class', 'descriptors',
                             'complexity', 'previews'}
    assert done['shape_class'] == 'planar'
    assert done['shape_class_source'] == 'derived'
    assert done['bbx'] == pytest.approx([600, 400, 18])
    assert 'pca_frame' not in done and 'bbx_origin' not in done
    assert {'pca_frame', 'bbx_origin'} <= set(outcome.unset)
    assert set(done['descriptors']) >= {'boxscore', 'hks',
                                        'radial_distance_32'}
    assert len(done['descriptors']['hks']) == 32
    assert done['complexity'] in (0, 1, 2, 3)
    assert outcome.preview and outcome.preview[:4] == b'RIFF'
    assert not outcome.write_files                      # authored: no fit
    ComponentSnapshot.model_validate(done)


def test_nothing_is_stale_after_a_run_and_a_second_run_does_nothing():
    doc = snapshot({'proxies': [authored_prism(PLATE, 18)]})
    done = apply(doc, run_stages(doc, IDENTITY, ENV))
    assert stale_stages(done, IDENTITY, ENV) == []
    assert run_stages(done, IDENTITY, ENV).changed is False


def test_a_mesh_gets_a_fitted_primary_proxy_and_maps():
    mesh = trimesh.creation.box(extents=(300, 200, 150))
    doc = snapshot({'meshes': [inline_mesh(mesh)]})
    outcome = run_stages(doc, IDENTITY, ENV)
    done = apply(doc, outcome)
    assert done['shape_class'] == 'block'
    proxies = done['geometry']['proxies']
    assert len(proxies) == 1 and proxies[0]['primitive'] == 'box'
    assert proxies[0]['role'] == 'primary'
    assert len(outcome.write_files) == 6
    assert all(name.startswith('proxies/s1/0/') for name in outcome.write_files)
    ComponentSnapshot.model_validate(done)


def test_ifccolumn_stands_by_elongation():
    bar = prism_mesh([[-100, -100], [100, -100], [100, 100], [-100, 100]],
                     None, 3000)                      # 200 x 200 x 3000
    bar.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 2, [0, 1, 0]))                        # lying along stored x
    doc = snapshot({'meshes': [inline_mesh(bar)]})
    column = {'_id': 'i1', 'original_function': 'IfcColumn'}
    beam = {'_id': 'i1', 'original_function': 'IfcBeam'}
    standing = apply(doc, run_stages(doc, column, ENV, STAGES[:2]))
    lying = apply(doc, run_stages(doc, beam, ENV, STAGES[:2]))
    assert standing['bbx'] == pytest.approx([200, 200, 3000])
    assert lying['bbx'] == pytest.approx([3000, 200, 200])


def test_changing_the_function_makes_frame_and_dependents_stale():
    bar = prism_mesh([[-100, -100], [100, -100], [100, 100], [-100, 100]],
                     None, 3000)
    doc = snapshot({'meshes': [inline_mesh(bar)]})
    beam = {'_id': 'i1', 'original_function': 'IfcBeam'}
    done = apply(doc, run_stages(doc, beam, ENV, STAGES[:5]))
    assert stale_stages(done, beam, ENV, STAGES[:5]) == []
    column = {'_id': 'i1', 'original_function': 'IfcColumn'}
    stale = stale_stages(done, column, ENV, STAGES[:5])
    assert stale[0] == 'frame'
    rerun = apply(done, run_stages(done, column, ENV, STAGES[:5]))
    assert rerun['bbx'] == pytest.approx([200, 200, 3000])
    assert stale_stages(rerun, column, ENV, STAGES[:5]) == []


def test_an_assigned_class_is_kept_and_reruns_the_proxy():
    mesh = trimesh.creation.box(extents=(300, 200, 150))
    doc = snapshot({'meshes': [inline_mesh(mesh)]})
    done = apply(doc, run_stages(doc, IDENTITY, ENV))
    assert done['geometry']['proxies'][0]['primitive'] == 'box'
    overridden = {**done, 'shape_class': 'irregular',
                  'shape_class_source': 'assigned'}
    assert 'shape_class' not in stale_stages(overridden, IDENTITY, ENV)
    assert 'proxies' in stale_stages(overridden, IDENTITY, ENV)
    again = apply(overridden, run_stages(overridden, IDENTITY, ENV))
    assert again['shape_class'] == 'irregular'
    assert again['shape_class_source'] == 'assigned'
    assert again['geometry']['proxies'][0]['primitive'] == 'hull'


def test_an_assigned_complexity_is_never_overwritten():
    doc = snapshot({'proxies': [authored_prism(PLATE, 18)]},
                   complexity=3, complexity_source='assigned')
    done = apply(doc, run_stages(doc, IDENTITY, ENV))
    assert done['complexity'] == 3
    assert done['complexity_source'] == 'assigned'


def test_a_snapshot_without_geometry_is_stamped_with_the_error():
    doc = snapshot({'meshes': [], 'proxies': []})
    outcome = run_stages(doc, IDENTITY, ENV)
    assert 'frame' in outcome.errors
    done = apply(doc, outcome)
    assert done['derivation']['frame']['error']
    # a failed stamp is current until the version or the input changes
    assert 'frame' not in stale_stages(done, IDENTITY, ENV)


def test_recompute_forces_every_stage():
    doc = snapshot({'proxies': [authored_prism(PLATE, 18)]})
    done = apply(doc, run_stages(doc, IDENTITY, ENV))
    forced = run_stages(done, IDENTITY, ENV, force=True)
    assert set(forced.ran) >= {'frame', 'shape_class', 'descriptors',
                               'complexity', 'previews'}


def test_markers_and_fixtures_are_never_read():
    mesh = trimesh.creation.box(extents=(300, 200, 150))
    doc = snapshot({'meshes': [inline_mesh(mesh)]})
    plain = apply(doc, run_stages(doc, IDENTITY, ENV, STAGES[:2]))
    doc['capture'] = {'markers': [{'label': 'far', 'role': 'rig',
                                   'point': [9e5, 9e5, 9e5]}],
                      'fixtures': [{'label': 'gripper', 'file': 'x.ply'}]}
    marked = apply(doc, run_stages(doc, IDENTITY, ENV, STAGES[:2]))
    assert marked['bbx'] == plain['bbx']
    assert marked['frame'] == plain['frame']


def test_a_column_that_flips_the_frame_leaves_nothing_stale():
    bar = prism_mesh([[-100, -100], [100, -100], [100, 100], [-100, 100]],
                     None, 3000)
    bar.apply_transform(trimesh.transformations.rotation_matrix(
        np.pi / 2, [0, 1, 0]))
    doc = snapshot({'meshes': [inline_mesh(bar)]})
    column = {'_id': 'i1', 'original_function': 'IfcColumn'}
    done = apply(doc, run_stages(doc, column, ENV, STAGES[:5]))
    assert done['bbx'] == pytest.approx([200, 200, 3000])     # stands
    assert stale_stages(done, column, ENV, STAGES[:5]) == []
