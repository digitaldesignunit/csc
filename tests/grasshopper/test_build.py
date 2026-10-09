"""The payload builders (csc_build): what they make is what the server takes.

Where the backend stack imports (the server's environment) every body is also
validated by the server's own models, so a change on either side fails here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import get_args

import numpy as np
import pytest

from csc_gh import build as b

BACKEND = Path(__file__).resolve().parents[2] / 'src' / 'backend'
UUID_A = '11111111-1111-4111-8111-111111111111'
UUID_B = '22222222-2222-4222-8222-222222222222'
UUID_C = '33333333-3333-4333-9333-333333333333'


@pytest.fixture(scope='module')
def server():
    """The backend models, or a skip on the client-only stack."""
    sys.path.insert(0, str(BACKEND))
    try:
        import apps.catalog.api.evidence_service as evidence_service
        import apps.catalog.api.identity_edit as identity_edit
        import apps.catalog.api.snapshot_lifecycle as snapshot_lifecycle
        import apps.catalog.documents as documents
        import apps.catalog.evidence.payloads as payloads
        import apps.catalog.vocab as vocab
    except Exception as error:
        pytest.skip('backend stack not importable here: %s' % error)
    return {'identity': identity_edit, 'snapshot': snapshot_lifecycle,
            'documents': documents, 'payloads': payloads, 'vocab': vocab,
            'evidence': evidence_service}


# VOCABULARY -----------------------------------------------------------------
def test_the_vocabulary_is_the_servers(server):
    vocab = server['vocab']
    pairs = {
        'origin_kind': 'OriginKind', 'actor_kind': 'ActorKind',
        'actor_role': 'ActorRole', 'capture_method': 'CaptureMethod',
        'marker_role': 'MarkerRole', 'original_function': 'OriginalFunction',
        'construction_method': 'ConstructionMethod', 'precision': 'Precision',
        'reinforcement_basis': 'ReinforcementBasis',
        'shape_class': 'ShapeClass',
    }
    for ours, theirs in pairs.items():
        assert b.VOCAB[ours] == get_args(getattr(vocab, theirs)), ours


def test_the_body_keys_are_the_servers(server):
    identity = server['identity'].IdentityCreateBody
    snapshot = server['snapshot'].SnapshotDraftBody
    assert set(b.IDENTITY_KEYS) == set(identity.model_fields)
    assert set(b.SNAPSHOT_KEYS) == set(snapshot.model_fields)


# DATES AND SMALL INPUTS ------------------------------------------------------
@pytest.mark.parametrize('value, expected', [
    (None, (None, None)), ('', (None, None)), ('unknown', (None, 'unknown')),
    ('2024', ('2024-01-01T00:00:00Z', 'year')),
    ('2024-05', ('2024-05-01T00:00:00Z', 'month')),
    ('2024-05-03', ('2024-05-03T00:00:00Z', 'day')),
    ('2024-05-03T14:30:00Z', ('2024-05-03T14:30:00Z', 'exact')),
    ('2024-05-03 14:30', ('2024-05-03T14:30:00Z', 'exact')),
    ('2024-05-03T14:30:00+02:00', ('2024-05-03T12:30:00Z', 'exact')),
])
def test_dates_and_their_precision(value, expected):
    assert b.parse_date(value) == expected


@pytest.mark.parametrize('value', ['3.10.2026', '2024-13', '2024-02-30', 'x'])
def test_a_wrong_date_is_refused(value):
    with pytest.raises(b.BuildError):
        b.parse_date(value, 'At')


def test_location_colour_and_choice():
    assert b.location(None, None) is None
    assert b.location('49.8', 8.6) == {'lat': 49.8, 'lon': 8.6}
    for bad in ((49.8, None), (95, 8), (1, 200)):
        with pytest.raises(b.BuildError):
            b.location(*bad)
    assert b.rgb([1.2, 255, 0]) == [1, 255, 0]
    with pytest.raises(b.BuildError):
        b.rgb([1, 2])
    with pytest.raises(b.BuildError):
        b.rgb([1, 2, 300])
    assert b.choice('IfcBeam', 'f', b.VOCAB['original_function']) == 'IfcBeam'
    with pytest.raises(b.BuildError):
        b.choice('beam', 'f', b.VOCAB['original_function'])
    assert b.choice(' ', 'f', ('a',), 'd') == 'd'


# ACTOR, ORIGIN, METADATA, CAPTURE --------------------------------------------
def test_actor_guesses_its_kind(server):
    assert b.actor(name='Ada')['kind'] == 'person'
    assert b.actor(organization='Lab GmbH')['kind'] == 'organization'
    assert b.actor(user_id=UUID_A)['kind'] == 'user'
    full = b.actor('person', name='Ada', organization='Lab', orcid='0000',
                   role='operator', email='a@b.c', organization_ror='ror')
    server['documents'].Actor.model_validate(full)
    for bad in (dict(kind='user'), dict(), dict(name='A', role='boss')):
        with pytest.raises(b.BuildError):
            b.actor(**bad)


def test_origin_builds_what_the_server_validates(server):
    person = b.actor(name='Ada', role='operator')
    block = b.origin(
        'deinstallation', '2024-05', None, 'Hall 3', 'Main St 1', 49.8, 8.6,
        'Hall 3', '1974', 'storage', 'prefabricated', 'by crane',
        [json.dumps(person)], 'notes')
    assert block['at_precision'] == 'month'
    assert block['construction_work']['year_built'] == 1974
    server['documents'].Origin.model_validate(block)
    # the precision follows the text unless given
    assert b.origin('offcut', '2024-05-03')['at_precision'] == 'day'
    assert b.origin('offcut', '2024-05-03', 'year')['at_precision'] == 'year'
    assert b.origin('unknown')['at_precision'] == 'unknown'


def test_origin_refuses_what_the_server_would(server):
    with pytest.raises(b.BuildError):
        b.origin(None)
    with pytest.raises(b.BuildError):
        b.origin('offcut', work_name='A hall')          # I16
    with pytest.raises(b.BuildError):
        b.origin('demolition', work_year='1974')        # a work needs a name


def test_identity_and_snapshot_metadata(server):
    meta = b.identity_metadata(
        'IfcBeam', 'concrete', 'T', 'M', '2001-02-03', None,
        json.dumps(b.origin('surplus', '2020')), True, '{"k": 1}', '17 01 01')
    assert meta['manufactured_precision'] == 'day' and meta['is_public']
    assert meta['attributes'] == {'k': 1}
    with pytest.raises(b.BuildError):
        b.identity_metadata('beam')
    snap = b.snapshot_metadata('Lintel', True, 3, [1, 2, 3], 49.8, 8.6,
                               ' n ', '2024-05-03', None, 'linear', 2)
    assert snap['quantity'] == 3 and snap['complexity'] == 2
    assert snap['effective_from_precision'] == 'day'
    assert b.snapshot_metadata() == {}
    assert 'quantity' not in b.snapshot_metadata(quantity=1)
    for bad in (dict(quantity=0), dict(complexity=4),
                dict(shape_class='lumpy')):
        with pytest.raises(b.BuildError):
            b.snapshot_metadata(**bad)


def test_capture_markers_and_fixtures(server):
    block = b.capture(
        'structured_light', 'scanner', 'soft', '2024-05-03', 'n',
        'gripper marker plane', 'the plane of four markers',
        [('blue_1', 'rig', (0, 0, 0)), ('green_1', None, (1, 2, 3))],
        [('effector', 'effector.ply')])
    server['documents'].Capture.model_validate(block)
    assert [m['role'] for m in block['markers']] == ['rig', 'component']
    assert b.capture() == {}
    with pytest.raises(b.BuildError):
        b.capture(markers=[('', 'rig', (0, 0, 0))])
    with pytest.raises(b.BuildError):
        b.capture(markers=[('a', 'rig', (0, 0))])
    with pytest.raises(b.BuildError):
        b.capture(fixtures=[('a', '')])


# GEOMETRY -------------------------------------------------------------------
@pytest.mark.parametrize('faces, preview, reduced, original', [
    (100, None, None, False), (500, None, None, False),
    (501, None, None, True), (8000, None, None, True),
    (8001, 500, None, True), (15000, 500, None, True),
    (15001, 500, 10000, True), (600000, 500, 10000, True),
])
def test_mesh_levels(faces, preview, reduced, original):
    plan = b.mesh_levels(faces)
    assert (plan['preview_target'], plan['reduced_target'],
            plan['save_original']) == (preview, reduced, original)


def test_inline_meshes_and_clouds_are_checked():
    mesh = b.inline_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
    assert 'colors' not in mesh
    assert b.inline_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]],
                         [[1, 2, 3]] * 3)['colors'][0] == [1, 2, 3]
    with pytest.raises(b.BuildError):
        b.inline_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 5]])
    with pytest.raises(b.BuildError):
        b.inline_mesh([], [])
    cloud = b.inline_point_cloud(np.random.default_rng(0).random((12000, 3)))
    assert len(cloud['points']) == b.POINT_CLOUD_INLINE_MAX
    small = b.inline_point_cloud(np.zeros((10, 3)), np.ones((10, 3)))
    assert len(small['points']) == 10 and len(small['colors']) == 10
    with pytest.raises(b.BuildError):
        b.inline_point_cloud(np.zeros((0, 3)))


def _validate_proxy(server, proxy):
    return server['documents'].Proxy.model_validate(proxy)


def test_a_box_proxy_measures_the_box(server):
    theta = np.radians(30)
    x = np.array([np.cos(theta), np.sin(theta), 0])
    y = np.array([-np.sin(theta), np.cos(theta), 0])
    z = np.array([0, 0, 1.0])
    corners = [np.array([100, -50, 20]) + sx * 30 * x + sy * 10 * y
               + sz * 5 * z for sx in (-1, 1) for sy in (-1, 1)
               for sz in (-1, 1)]
    proxy = b.box_proxy(corners, x, z)
    assert proxy['params']['size'] == pytest.approx([60, 20, 10])
    assert proxy['placement']['o'] == pytest.approx([100, -50, 20])
    assert proxy['placement']['x'] == pytest.approx(list(x))
    _validate_proxy(server, proxy)
    # an x axis that is not perpendicular to z is made so
    again = b.box_proxy(corners, x + 0.3 * z, z)
    assert again['params']['size'] == pytest.approx([60, 20, 10])
    with pytest.raises(b.BuildError):
        b.box_proxy(corners[:2], x, z)


@pytest.mark.parametrize('clockwise', [False, True])
def test_a_prism_proxy_from_an_extrusion(server, clockwise):
    ring = [(0, 0), (40, 0), (40, 20), (0, 20)]
    if clockwise:
        ring.reverse()
    profile = [(x + 5, y - 3, 7) for x, y in ring]
    proxy = b.prism_proxy(profile + [profile[0]], (0, 0, 1), 10)
    params = proxy['params']
    assert params['height'] == 10 and len(params['profile']) == 4
    # centred on the profile's centroid, z from -h/2 to +h/2
    local = np.array(params['profile'])
    assert local.mean(axis=0) == pytest.approx([0, 0], abs=1e-9)
    assert np.ptp(local, axis=0) == pytest.approx([40, 20]) \
        or np.ptp(local, axis=0) == pytest.approx([20, 40])
    # placed so the profile sits at the start of the extrusion
    assert proxy['placement']['o'] == pytest.approx([25, 7, 12])
    assert proxy['placement']['z'] == pytest.approx([0, 0, 1])
    _validate_proxy(server, proxy)


def test_a_prism_proxy_with_a_hole_and_a_slanted_axis(server):
    outer = [(0, 0, 0), (100, 0, 0), (100, 60, 0), (0, 60, 0)]
    hole = [(30, 20, 0), (60, 20, 0), (60, 40, 0), (30, 40, 0)]
    proxy = b.prism_proxy(outer, (0, 0, -2), 12, [hole])
    assert proxy['placement']['z'] == pytest.approx([0, 0, -1])
    assert len(proxy['params']['holes']) == 1
    _validate_proxy(server, proxy)
    with pytest.raises(b.BuildError):
        b.prism_proxy(outer, (0, 0, 1), 0)
    with pytest.raises(b.BuildError):
        b.prism_proxy(outer[:2], (0, 0, 1), 5)
    with pytest.raises(b.BuildError):
        b.prism_proxy([(0, 0, 0), (1, 0, 0), (2, 0, 0)], (0, 0, 1), 5)


def test_geometry_body_needs_content_and_one_primary(server):
    with pytest.raises(b.BuildError):
        b.geometry_body()
    box = b.box_proxy(np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
                                [1, 1, 0], [1, 0, 1], [0, 1, 1], [1, 1, 1]]),
                      (1, 0, 0), (0, 0, 1))
    two = b.geometry_body(proxies=[dict(box), dict(box)])
    assert [p['role'] for p in two['proxies']] == ['primary', 'part']
    server['documents'].Geometry.model_validate(two)


# BODIES ---------------------------------------------------------------------
def _geometry():
    mesh = b.inline_mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
    return b.geometry_body([mesh])


def test_an_identity_body_the_server_takes(server):
    snapshot = b.snapshot_body(
        json.dumps(b.snapshot_metadata('Lintel', quantity=2)), _geometry(),
        json.dumps(b.capture('lidar')))
    meta = json.dumps(b.identity_metadata('IfcBeam', 'concrete'))
    body = b.identity_body(UUID_A, 'beyond_debris', meta, snapshot)
    assert b.problems_of_identity(body) == []
    parsed = server['identity'].IdentityCreateBody.model_validate(body)
    assert parsed.dataset == 'beyond_debris'
    server['snapshot'].SnapshotDraftBody.model_validate(parsed.snapshot)


def test_a_cut_needs_no_metadata_a_new_piece_does(server):
    snapshot = b.snapshot_body(None, _geometry())
    cut = b.identity_body(None, 'ds', None, snapshot, [UUID_A, UUID_B])
    assert b.problems_of_identity(cut) == []
    assert cut['parent_identities'] == [UUID_A, UUID_B] and 'id' not in cut
    server['identity'].IdentityCreateBody.model_validate(cut)
    with pytest.raises(b.BuildError):
        b.identity_body(None, 'ds', None, snapshot)
    with pytest.raises(b.BuildError):
        b.identity_body('not-a-uuid', 'ds', '{}', snapshot, [UUID_A])
    with pytest.raises(b.BuildError):
        b.identity_body(None, '', '{}', snapshot, [UUID_A])
    with pytest.raises(b.BuildError):
        b.identity_body(None, 'ds', '{}', snapshot, ['nope'])
    with pytest.raises(b.BuildError):
        b.identity_body(None, 'ds', '{"geometry": 1}', snapshot, [UUID_A])


def test_problems_name_a_0_5_body():
    old = {'_id': UUID_A, 'type': 'panel', 'material': 'corian',
           'dataset': 'x', 'iframe': {}, 'geometry': {}}
    problems = b.problems_of_identity(old)
    assert any("'type'" in p for p in problems)
    assert any('snapshot is missing' in p for p in problems)
    assert any("'iframe'" in p for p in problems)
    snapshot = {'geometry': {}, 'pca_frame': {}}
    assert len(b.problems_of_snapshot(snapshot)) == 2


def test_the_snapshot_envelope_and_its_check(server):
    snapshot = b.snapshot_body(None, _geometry())
    envelope = b.snapshot_envelope(UUID_A, snapshot, UUID_B)
    assert b.problems_of_envelope(envelope) == []
    assert envelope['supersedes'] == UUID_B
    assert 'supersedes' not in b.snapshot_envelope(UUID_A, snapshot)
    with pytest.raises(b.BuildError):
        b.snapshot_envelope('x', snapshot)
    with pytest.raises(b.BuildError):
        b.snapshot_envelope(UUID_A, snapshot, 'x')
    assert b.problems_of_envelope({'snapshot': snapshot, 'extra': 1})
    server['snapshot'].SnapshotDraftBody.model_validate(envelope['snapshot'])


def test_a_staging_key_follows_the_content_only():
    first = b.staging_key(json.dumps({'a': 1, 'b': [1, 2]}))
    assert first == b.staging_key('{"b":[1,2],"a":1}')
    assert first != b.staging_key(json.dumps({'a': 1, 'b': [1, 3]}))
    assert len(first) == 24
    assert b.manifest({0: ['detailed', 'reduced']}, [1]) == {
        'coordinate_frame': 'stored',
        'meshes': {'0': ['detailed', 'reduced']}, 'point_clouds': [1]}
    assert b.manifest() == {'coordinate_frame': 'stored'}


# EVIDENCE -------------------------------------------------------------------
def _bars():
    return [{'spec': 'BSt III', 'diameter_mm': 8,
             'points': [[0, 0, 0], [100, 0, 0], [100, 50, 0]]},
            {'spec': None, 'diameter_mm': 12.5, 'diameter_known': False,
             'cover_mm': 25, 'points': [[0, 10, 0], [100, 10, 0]]}]


def test_a_reinforcement_layout_record_the_server_takes(server):
    record = b.reinforcement_layout_record(
        UUID_A, _bars(), 'drawing', '2024-05-03', 'Drawing 7', '1974-05',
        'ref 1', None, None, None, 'size +-20 %', None, 'n')
    assert record['method'] == 'reinforcement_layout'
    assert record['position'] == {'kind': 'none', 'snapshot_id': UUID_A,
                                  'description': 'reinforcement layout'}
    assert record['payload']['document']['title'] == 'Drawing 7'
    assert record['payload']['bars'][1]['diameter_known'] is False
    assert 'diameter_known' not in record['payload']['bars'][0]
    server['evidence'].EvidenceCreate.model_validate(record)
    server['payloads'].ReinforcementLayoutPayload.model_validate(
        record['payload'])
    scan = b.reinforcement_layout_record(
        UUID_A, _bars(), 'scan', None, instrument_kind='covermeter',
        instrument_model='X1')
    assert scan['payload']['instrument'] == {'kind': 'covermeter',
                                             'model': 'X1'}
    server['payloads'].ReinforcementLayoutPayload.model_validate(
        scan['payload'])
    assert scan['observed_at'].endswith('Z')


def test_a_layout_needs_a_state_a_basis_and_bars():
    for bad in (dict(snapshot_id='x'), dict(basis='dream'), dict(basis=None),
                dict(bars=[]),
                dict(bars=[{'diameter_mm': 0, 'points': [[0, 0, 0],
                                                         [1, 0, 0]]}]),
                dict(bars=[{'diameter_mm': 8, 'points': [[0, 0, 0]]}])):
        args = dict(snapshot_id=UUID_A, bars=_bars(), basis='scan')
        args.update(bad)
        with pytest.raises(b.BuildError):
            b.reinforcement_layout_record(**args)


def test_the_bulk_body_pairs_ids_and_records(server):
    record = b.reinforcement_layout_record(UUID_A, _bars(), 'exposed')
    text = json.dumps(record)
    one = b.evidence_bulk_body([text, record], [UUID_B])
    assert [r['identity_id'] for r in one['records']] == [UUID_B, UUID_B]
    assert 'submit' not in one            # drafts only (8.127)
    two = b.evidence_bulk_body([text, text], [UUID_B, UUID_C])
    assert [r['identity_id'] for r in two['records']] == [UUID_B, UUID_C]
    assert 'submit' not in two
    server['evidence'].EvidenceBulk.model_validate(two)
    for records, ids in (([], [UUID_B]), ([text], []),
                         ([text, text, text], [UUID_B, UUID_C]),
                         ([text], ['nope'])):
        with pytest.raises(b.BuildError):
            b.evidence_bulk_body(records, ids)
