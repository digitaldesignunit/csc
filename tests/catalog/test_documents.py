"""Document models of the 0.6 data model (data model spec section 3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

import examples06 as ex
from apps.catalog.documents import (
    ComponentIdentity,
    ComponentSnapshot,
    Dataset,
    Evidence,
    Material,
    PurgeStub,
)


# the hand-written examples validate ----------------------------------------------
@pytest.mark.parametrize('model, factory', [
    (ComponentIdentity, ex.identity),
    (ComponentSnapshot, ex.snapshot),
    (Evidence, ex.evidence),
    (Dataset, ex.dataset),
    (Material, ex.material),
    (PurgeStub, ex.purge_stub),
])
def test_examples_validate(model, factory):
    doc = model.model_validate(factory())
    dumped = doc.model_dump(by_alias=True)
    assert dumped['_id'] == factory()['_id']


def test_robot_capture_validates():
    snap = ex.snapshot()
    snap['capture'] = ex.robot_capture()
    parsed = ComponentSnapshot.model_validate(snap)
    assert parsed.capture.fixtures[0].label == 'end_effector'


def _invalid(model, doc, match):
    with pytest.raises(ValidationError, match=match):
        model.model_validate(doc)


def test_top_level_ignores_unknown_keys_blocks_forbid_them():
    doc = ex.identity()
    doc['legacy_field'] = 1
    ComponentIdentity.model_validate(doc)          # envelope: ignored
    doc['origin']['at_precison'] = 'day'           # nested block: a typo fails
    _invalid(ComponentIdentity, doc, 'at_precison')


def test_timestamps_are_iso_utc():
    doc = ex.identity()
    doc['created'] = '2026-02-03 10:15:00'
    _invalid(ComponentIdentity, doc, 'ending in Z')


# identity --------------------------------------------------------------------
def test_i16_construction_work_only_for_deinstallation_or_demolition():
    doc = ex.identity()
    doc['origin']['kind'] = 'offcut'
    _invalid(ComponentIdentity, doc, 'deinstallation / demolition')


def test_i18_exit_construction_work_only_for_installed():
    doc = ex.identity()
    doc['exit'] = {'kind': 'recycled', 'at': ex.T1,
                   'construction_work': {'name': 'somewhere'}}
    _invalid(ComponentIdentity, doc, 'installed')


def test_i18_no_reservation_out_of_circulation():
    doc = ex.identity()
    doc['exit'] = {'kind': 'installed', 'at': ex.T1}
    doc['reserved'] = ex.USER_ID
    _invalid(ComponentIdentity, doc, 'reserved')


def test_i17_inherited_from_is_a_parent():
    doc = ex.identity()
    doc['inherited_fields'] = ['origin']
    doc['parent_identities'] = ['p1']
    doc['inherited_from'] = 'p2'
    _invalid(ComponentIdentity, doc, 'inherited_from')
    doc['inherited_from'] = 'p1'
    ComponentIdentity.model_validate(doc)
    doc['inherited_fields'] = ['dataset']        # dataset is not inheritable
    _invalid(ComponentIdentity, doc, 'not inheritable')


def test_i19_not_a_duplicate_of_itself():
    doc = ex.identity()
    doc['withdrawn'] = {'at': ex.T1, 'by_user_id': ex.MODERATOR_ID,
                        'reason': 'dup', 'duplicate_of': ex.IDENTITY_ID}
    _invalid(ComponentIdentity, doc, 'duplicate')


def test_material_class_is_a_low_chapter_17_code():
    doc = ex.identity()
    doc['material_class'] = '170101'
    _invalid(ComponentIdentity, doc, 'List of Waste')


# snapshot --------------------------------------------------------------------
def test_i1_needs_a_representation():
    doc = ex.snapshot()
    doc['geometry'] = {'meshes': [], 'point_clouds': [], 'proxies': []}
    _invalid(ComponentSnapshot, doc, 'I1')


def test_i1_an_authored_proxy_is_enough():
    doc = ex.snapshot()
    doc['geometry'] = {'proxies': [{
        'primitive': 'box', 'role': 'primary', 'params': {'size': [1200, 600, 30]},
        'placement': {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]},
        'fit': {'method': 'authored'},
    }]}
    ComponentSnapshot.model_validate(doc)


def test_i2_exactly_one_primary_proxy():
    doc = ex.snapshot()
    doc['geometry']['proxies'].append(dict(doc['geometry']['proxies'][0]))
    _invalid(ComponentSnapshot, doc, 'I2')


def test_i4_composite_is_assigned():
    doc = ex.snapshot()
    doc['shape_class'] = 'composite'
    _invalid(ComponentSnapshot, doc, 'I4')
    doc['shape_class_source'] = 'assigned'
    ComponentSnapshot.model_validate(doc)


def test_authored_fit_has_no_residuals_or_source():
    doc = ex.snapshot()
    doc['geometry']['proxies'][0]['fit']['method'] = 'authored'
    _invalid(ComponentSnapshot, doc, 'authored')


def test_proxy_params_follow_the_primitive():
    doc = ex.snapshot()
    doc['geometry']['proxies'][0]['params'] = {'radius': 10}
    _invalid(ComponentSnapshot, doc, 'size')


def test_mesh_face_indices_in_range():
    doc = ex.snapshot()
    doc['geometry']['meshes'][0]['faces'].append([0, 1, 9])
    _invalid(ComponentSnapshot, doc, 'out-of-range')


def test_paired_source_fields():
    doc = ex.snapshot()
    doc['complexity_source'] = None
    _invalid(ComponentSnapshot, doc, 'complexity')


# evidence --------------------------------------------------------------------
def test_i6_summary_fits_the_quantity():
    doc = ex.evidence()
    doc['summary']['value'] = None
    _invalid(Evidence, doc, 'I6')
    doc = ex.evidence()
    doc['summary']['unit'] = 'N/mm2'                       # not canonical
    _invalid(Evidence, doc, 'canonical')
    doc = ex.evidence()
    doc['summary'] = {'quantity': 'spalling', 'value': 4, 'kind': 'claimed'}
    _invalid(Evidence, doc, 'ordinal')
    doc['summary']['quantity'] = 'not_a_quantity'
    _invalid(Evidence, doc, 'unknown quantity')


def test_i7_one_result_per_quantity():
    doc = ex.evidence()
    doc['derived'][0]['quantity'] = 'compressive_strength'
    _invalid(Evidence, doc, 'I7')


def test_i10_observed_not_before_sampled():
    doc = ex.evidence()
    doc['sampled_at'] = '2026-03-01T00:00:00Z'
    _invalid(Evidence, doc, 'I10')


def test_i22_accredited_needs_a_covering_accreditation():
    doc = ex.evidence()
    doc['standard']['code'] = 'EN 12504-2'                 # not in scope
    _invalid(Evidence, doc, 'I22')
    doc = ex.evidence()
    doc['performed_by'][0]['accreditation']['valid_until'] = '2025-12-31T00:00:00Z'
    _invalid(Evidence, doc, 'I22')                         # expired before observed_at


def test_i27_reviewed_needs_a_second_person():
    doc = ex.evidence()
    doc['verification']['by'] = None
    _invalid(Evidence, doc, 'I27')
    doc = ex.evidence()
    doc['verification']['by']['user_id'] = ex.USER_ID      # the recorder
    _invalid(Evidence, doc, 'I27')
    doc = ex.evidence()
    doc['verification']['state'] = 'reviewed'
    doc['performed_by'].append({'kind': 'user', 'user_id': ex.MODERATOR_ID,
                                'role': 'operator'})
    _invalid(Evidence, doc, 'I27')                         # reviewer performed it
    doc = ex.evidence()
    doc['verification']['note'] = '  '
    _invalid(Evidence, doc, 'I27')                         # accredited without a note
    doc = ex.evidence()
    doc['verification'].update(state='reviewed', note=None)
    Evidence.model_validate(doc)


def test_i27_self_attested_only_by_a_performer():
    doc = ex.evidence()
    doc['verification'] = {'state': 'self_attested', 'by': None, 'at': ex.T1,
                           'note': None}
    _invalid(Evidence, doc, 'I27')                         # an outside lab did it
    doc['performed_by'].append({'kind': 'user', 'user_id': ex.USER_ID,
                                'role': 'operator'})
    Evidence.model_validate(doc)


def test_tier_and_destructive_follow_the_method():
    doc = ex.evidence()
    doc['source_tier'] = 'ndt'
    _invalid(Evidence, doc, 'tier')
    doc = ex.evidence()
    doc['destructive'] = False
    _invalid(Evidence, doc, 'destructive')


def test_i23_reinforcement_layout_names_its_snapshot_and_takes_tier_from_basis():
    doc = ex.evidence()
    doc.update({
        'method': 'reinforcement_layout', 'source_tier': 'archival',
        'destructive': False, 'standard': None, 'sampled_at': None,
        'sampled_at_precision': None, 'derived': [],
        'verification': {'state': 'unverified'},
        'summary': {'quantity': 'rebar_diameter', 'range': [8, 8], 'unit': 'mm',
                    'kind': 'claimed'},
        'payload': {'basis': 'drawing', 'bars': []},
    })
    Evidence.model_validate(doc)
    doc['payload']['basis'] = 'scan'                        # scan -> ndt
    _invalid(Evidence, doc, 'tier')
    doc['payload']['basis'] = 'drawing'
    doc['position'] = {'kind': 'none', 'description': 'whole element'}
    _invalid(Evidence, doc, 'I23')


def test_position_rules():
    doc = ex.evidence()
    doc['position'] = {'kind': 'none'}
    _invalid(Evidence, doc, 'description')
    doc['position'] = {'kind': 'point', 'point': [0, 0, 0], 'description': 'x'}
    _invalid(Evidence, doc, 'snapshot')


def test_attachment_tombstone_and_checksum():
    doc = ex.evidence()
    doc['attachments'][0]['removed'] = {'at': ex.T1, 'by_user_id': ex.MODERATOR_ID,
                                        'reason': 'wrong file'}
    Evidence.model_validate(doc)
    doc['attachments'][0]['sha256'] = 'xyz'
    _invalid(Evidence, doc, 'sha256')


# datasets, materials ---------------------------------------------------------
def test_dataset_roles_are_a_set_and_members_unique():
    doc = ex.dataset()
    doc['members'][0]['roles'] = ['contributor', 'contributor']
    _invalid(Dataset, doc, 'set')
    doc = ex.dataset()
    doc['members'].append(dict(doc['members'][0]))
    _invalid(Dataset, doc, 'member once')
    assert Dataset.model_validate(ex.dataset()).roles_of(ex.MODERATOR_ID) == \
        frozenset({'contributor', 'moderator'})


def test_dataset_default_visibility_is_members():
    doc = ex.dataset()
    del doc['visibility']
    assert Dataset.model_validate(doc).visibility == 'members'


def test_material_default_class_never_hazardous():
    doc = ex.material()
    doc['default_class'] = '17 06 05*'
    _invalid(Material, doc, 'hazardous')


def test_a_deviation_map_file_is_named_by_the_server():
    from pydantic import ValidationError

    from apps.catalog.documents import DeviationMapFace
    scale = {'scale_mm': 0.01, 'offset_mm': -1.0}
    good = 'proxies/11111111-1111-1111-1111-111111111111/0/+z.png'
    assert DeviationMapFace(file=good, width=2, height=2, distance=scale)
    for bad in ('../x.png', 'proxies/../x/0/+z.png',
                'proxies/abc/0/../../../etc.png', '/etc/passwd',
                'proxies/abc/0/+z.txt', 'meshes/abc/0/+z.png'):
        with pytest.raises(ValidationError):
            DeviationMapFace(file=bad, width=2, height=2, distance=scale)


# IN PLACE AND DOCUMENTS (8.104, 8.106) ---------------------------------------
def test_origin_planned_defaults_to_false_and_needs_a_works_kind():
    doc = ex.identity()
    assert ComponentIdentity.model_validate(doc).origin.planned is False
    doc['origin'] = {'kind': 'deinstallation', 'planned': True}
    assert ComponentIdentity.model_validate(doc).origin.planned is True
    doc['origin'] = {'kind': 'offcut', 'planned': True}
    with pytest.raises(ValidationError, match=r'\(I31\)'):
        ComponentIdentity.model_validate(doc)


def test_authored_exit_from_in_place_is_recycled_disposed_or_lost():
    doc = ex.identity()
    doc['origin'] = {'kind': 'deinstallation', 'planned': True}
    for kind, fine in (('lost', True), ('recycled', True),
                       ('installed', False), ('returned', False)):
        doc['exit'] = {'kind': kind, 'at': '2026-06-01T00:00:00Z',
                       'recorded_by_user_id': 'u'}
        if fine:
            ComponentIdentity.model_validate(doc)
        else:
            with pytest.raises(ValidationError, match=r'\(I31\)'):
                ComponentIdentity.model_validate(doc)
    # a split the server keeps from cut pieces is not an authored exit
    doc['exit'] = {'kind': 'split', 'at': '2026-06-01T00:00:00Z',
                   'recorded_by_user_id': None}
    ComponentIdentity.model_validate(doc)


def test_only_a_document_has_no_summary():
    doc = ex.evidence()
    doc['summary'] = None
    with pytest.raises(ValidationError, match=r'\(I6\)'):
        Evidence.model_validate(doc)
