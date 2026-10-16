"""plan.py: the records the EPFL import writes, from stones made here (decision 8.146); no names in the
repository: the authors come from a README fixture with invented names."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest

import epfl_samples as samples

README = '''# Stone dataset

Distributed under a MIT license. Here is the BibTeX snippet:
```bibitex
@misc{stonedataset2022,
    author = {Ada Sample and Bo Example and Carl Demo},
    year = {2022},
    title = {Dataset of Mineral Scraps for Augmented Stacking},
    doi = {10.0000/placeholder},                                  # TO BE REPLACED
}
```
'''
ROOT = Path(__file__).resolve().parents[2]


# THE AUTHORS, READ AT RUN TIME --------------------------------------------------------------------
def test_authors_are_read_from_the_bibtex_field(epfl):
    assert epfl.bibtex_authors(README) == ['Ada Sample', 'Bo Example', 'Carl Demo']


@pytest.mark.parametrize('text, expected', [
    ('author = {One Person}', ['One Person']),
    ('author = "First A and Second B"', ['First A', 'Second B']),
    ('AUTHOR={A B\n   and C D\n  and E F}', ['A B', 'C D', 'E F']),
    ('author = {Sample, Ada and Example, Bo}', ['Ada Sample', 'Bo Example']),
    ('no citation here', []), ('', [])])
def test_authors_of_other_bibtex_shapes(epfl, text, expected):
    assert epfl.bibtex_authors(text) == expected


def test_the_attribution_holds_authors_doi_licence_and_release(plan_module):
    entry = plan_module.dataset_entry(['Ada Sample', 'Bo Example', 'Carl Demo'], 452)
    text = entry['description']
    assert 'Ada Sample, Bo Example and Carl Demo' in text
    assert 'https://doi.org/10.5281/zenodo.7180964' in text and 'MIT licence' in text
    assert 'release v1' in text and 'github.com/ibois-epfl/augmented-stacking-dataset' in text
    assert '10.4225' not in text and 'placeholder' not in text                  # not the README's own DOI
    assert 'not the date of the scan' in text and '452 stones' in text
    assert (entry['id'], entry['name']) == ('epfl_stacking', 'EPFL: Mineral scraps for augmented stacking')


def test_no_authors_is_an_error_not_an_empty_attribution(plan_module):
    with pytest.raises(ValueError, match='no authors'):
        plan_module.dataset_entry([], 452)


def test_no_address_of_a_person_is_written_into_the_scripts(epfl):
    """The authors are read at run time and the README of the dataset is never copied: the committed files
    of this import hold no e-mail address."""
    texts = [p.read_text(encoding='utf-8') for p in (ROOT / 'scripts' / 'import' / 'epfl_stacking').glob('*')
             if p.suffix in ('.py', '.md')]
    assert texts and not any(re.search(r'[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[a-z]{2,}', t) for t in texts)


# ONE ITEM -------------------------------------------------------------------------------------------
def meta_of(stone_id='A0', faces=24100, watertight=True, reduced=10000, detailed=True, staged=True, scale=1000.0,
            color=(180, 184, 185)):
    files = {'preview.json': 1000}
    if reduced:
        files['reduced.ply'] = 10
    if detailed:
        files['detailed.ply'] = 10
    if staged:
        files['cloud.ply'] = 10
    return {'id': stone_id, 'group': stone_id[0], 'mesh_file': f'remeshed_high_res_{stone_id}.ply',
            'cloud_file': f'pcd_high_res_{stone_id}.ply', 'vertices': faces // 2, 'faces': faces,
            'bbox_mm': [445.0, 304.0, 72.0], 'origin_mm': [-222.0, -152.0, -36.0], 'watertight': watertight,
            'volume_cm3': 1.0 if watertight else None, 'has_colors': True,
            'levels': {'preview_faces': 1000, 'reduced_faces': reduced or None, 'detailed': detailed},
            'cloud': {'points': 20171, 'scale_to_mesh_unit': scale, 'inline_points': 1000, 'staged': staged},
            'mean_color': list(color) if color else None, 'files': files, 'flags': []}


def test_one_stone_is_one_component_without_evidence(plan_module):
    item = plan_module.item(meta_of('B7'))
    assert item['key'] == 'epfl_stacking:B7' and item['dataset'] == 'epfl_stacking'
    assert item['group'] == 'B' and item['stone'] == 'B7' and 'evidence' not in item
    identity = item['identity']
    assert identity['material'] == 'natural_stone'
    assert identity['original_function'] == 'IfcBuildingElementProxy'      # the backend needs one; this is "unknown"
    assert identity['is_public'] is False and identity['dataset'] == 'epfl_stacking'
    assert identity['origin'] == {'kind': 'offcut', 'planned': False, 'at_precision': 'unknown',
                                  'notes': 'Quarry extraction offcut'}
    recorded = identity['attributes']['epfl_stacking']
    assert recorded['id'] == 'B7' and recorded['group'] == 'B' and recorded['doi'] == '10.5281/zenodo.7180964'
    assert recorded['mesh_file'] == 'remeshed_high_res_B7.ply' and recorded['cloud_file'] == 'pcd_high_res_B7.ply'
    assert item['files'] == {'preview': 'stones/B7/preview.json', 'reduced': 'stones/B7/reduced.ply',
                             'detailed': 'stones/B7/detailed.ply', 'cloud': 'stones/B7/cloud.ply'}


def test_the_version_is_dated_with_the_release_and_says_so(plan_module):
    snapshot = plan_module.item(meta_of())['snapshot']
    assert snapshot['name'] == 'Stone A0' and snapshot['quantity'] == 1
    assert snapshot['effective_from'] == '2022-10-10T00:00:00Z'
    assert snapshot['effective_from_precision'] == 'day'
    assert snapshot['color'] == [180, 184, 185]
    assert 'location' not in snapshot and 'notes' not in snapshot
    capture = snapshot['capture']
    assert 'method' not in capture                                         # no fitting entry in the vocabulary
    assert 'Rhino 7' in capture['software'] and 'Poisson' in capture['software']
    notes = capture['notes']
    for part in ('publication date of the dataset, not the scan date', 'remeshed_high_res_A0.ply',
                 'pcd_high_res_A0.ply', 'in metres in the source files and multiplied by 1000',
                 'preview 1000 faces, reduced 10000 faces', 'https://doi.org/10.5281/zenodo.7180964'):
        assert part in notes, part


def test_a_mesh_that_is_not_watertight_says_so_in_the_notes(plan_module):
    notes = plan_module.item(meta_of(watertight=False))['snapshot']['capture']['notes']
    assert 'not watertight (kept as published)' in notes
    assert 'not watertight' not in plan_module.item(meta_of())['snapshot']['capture']['notes']


def test_a_small_stone_lists_only_the_files_it_has(plan_module):
    item = plan_module.item(meta_of(faces=400, reduced=None, detailed=False, staged=False))
    assert item['files'] == {'preview': 'stones/A0/preview.json'}


def test_ids_are_uuid5_of_the_stone_and_stable(plan_module):
    a, b = plan_module.item(meta_of())['identity']['id'], plan_module.item(meta_of())['identity']['id']
    assert a == b == plan_module.uid('epfl_stacking:A0')
    assert a == str(uuid.uuid5(uuid.UUID('5d2e7c1a-3b94-4f60-8a17-c9e04b6f2d38'), 'csc-import/epfl_stacking:A0'))
    assert plan_module.uid('epfl_stacking:A1') != a
    assert plan_module.uid('recreate:NL:A0') != a                          # not the other import's space


def test_main_writes_plan_and_report_from_prepare_json(plan_module, tmp_path):
    out, data = tmp_path / 'out', tmp_path / 'data'
    (data / 'stones').mkdir(parents=True)
    (data / 'README.md').write_text(README, encoding='utf-8')
    out.mkdir()
    (out / 'prepare.json').write_text(json.dumps({'stones': [meta_of('A0'), meta_of('E9', watertight=False),
                                                             {'id': 'C1', 'error': 'broke'}]}), encoding='utf-8')
    assert plan_module.main(out, data) == 0
    plan = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
    assert [i['stone'] for i in plan['items']] == ['A0', 'E9']
    assert plan['datasets'][0]['id'] == 'epfl_stacking' and 'Ada Sample' in plan['datasets'][0]['description']
    assert '2 stones' in plan['datasets'][0]['description']
    report = (out / 'plan-report.md').read_text(encoding='ascii')
    assert '2 components' in report and 'Not watertight: 1' in report and 'C1: failed to prepare' in report


# THE BODIES THE BACKEND TAKES -------------------------------------------------------------------------
def prepared(prepare_module, tmp_path):
    root = tmp_path / 'data'
    samples.write_stone(root, 'A0', subdivisions=5, radius_mm=100.0, cloud_points=20000)
    return prepare_module.prepare_stone('A0', root / 'stones' / 'mesh_high_res' / 'remeshed_high_res_A0.ply',
                                        root / 'stones' / 'pcd_high_res' / 'pcd_high_res_A0.ply', tmp_path / 'out')


def test_a_prepared_stone_validates_against_the_backend_models(plan_module, prepare_module, script_loader, tmp_path):
    pytest.importorskip('requests')
    meta = prepared(prepare_module, tmp_path)
    item = plan_module.item(meta)
    run = script_loader('run')
    assert run.validate(tmp_path / 'out', [item]) == []
    body = run.identity_body(item, run.read_preview(tmp_path / 'out', item))
    assert len(body['snapshot']['geometry']['meshes'][0]['faces']) == meta['levels']['preview_faces']
    assert len(body['snapshot']['geometry']['point_clouds'][0]['points']) == 1000
    # and a body the models refuse is refused here too
    bad = {**item, 'identity': {**item['identity'], 'origin': {'kind': 'not-a-kind'}}}
    problems = run.validate(tmp_path / 'out', [bad])
    assert problems and problems[0][0] == item['key']


def test_a_missing_file_is_a_problem_of_the_dry_run(plan_module, prepare_module, script_loader, tmp_path):
    pytest.importorskip('requests')
    meta = prepared(prepare_module, tmp_path)
    (tmp_path / 'out' / 'stones' / 'A0' / 'cloud.ply').unlink()
    problems = script_loader('run').validate(tmp_path / 'out', [plan_module.item(meta)])
    assert problems and 'cloud.ply is missing' in problems[0][1]
