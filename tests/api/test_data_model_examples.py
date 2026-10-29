"""The example records of the "Data Model" page are valid records (decision
8.181 d): every one of them is checked against the backend models and, for
evidence, against the method's own preparation (the server derives the
headline result of a rebound test, a core and a reinforcement layout and
refuses a different one).

The records are exported from ``src/frontend/lib/dataModelExamples.ts`` to
``tests/fixtures/data_model_examples.json`` by ``npx tsx
scripts/export-data-model-examples.ts`` (run in ``src/frontend``); a frontend
test fails when the file is out of date.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.catalog.documents import (
    ComponentIdentity,
    ComponentSnapshot,
    Dataset,
    Evidence,
)
from apps.catalog.evidence.registry import prepare_record
from apps.catalog.properties import fold, quantities_of_scope

FILE = Path(__file__).resolve().parents[1] / 'fixtures' / 'data_model_examples.json'
RECORDS = json.loads(FILE.read_text(encoding='utf-8'))
BY_ID = {record['id']: record for record in RECORDS}

# what the server adds to a record and the examples do not show
STAMPS = {'created': '2026-03-01T09:00:00Z', 'lastmodified': '2026-03-01T09:00:00Z'}
RECORDER = 'example-recorder'


def _of(model: str):
    return [r for r in RECORDS if r['model'] == model]


def test_the_file_has_every_kind_of_record():
    assert {r['model'] for r in RECORDS} == {
        'DatasetView', 'ComponentIdentity', 'ComponentSnapshot', 'EvidenceView'}
    assert len(_of('EvidenceView')) == 7
    assert len(set(BY_ID)) == len(RECORDS)


def test_the_dataset_is_a_valid_dataset():
    (record,) = _of('DatasetView')
    dataset = Dataset.model_validate({**record['json'], **STAMPS})
    assert dataset.id == 'example_dataset'


def test_the_identity_is_a_valid_identity():
    (record,) = _of('ComponentIdentity')
    ComponentIdentity.model_validate(
        {**record['json'], 'created_by_user_id': RECORDER, **STAMPS})


@pytest.mark.parametrize('record', _of('ComponentSnapshot'), ids=lambda r: r['id'])
def test_a_snapshot_is_a_valid_snapshot(record):
    ComponentSnapshot.model_validate(
        {**record['json'], 'added_by_user_id': RECORDER, **STAMPS})


@pytest.mark.parametrize('record', _of('EvidenceView'), ids=lambda r: r['id'])
def test_an_evidence_record_is_valid(record):
    Evidence.model_validate(
        {**record['json'], 'recorded_by_user_id': RECORDER, **STAMPS})


@pytest.mark.parametrize('record', _of('EvidenceView'), ids=lambda r: r['id'])
def test_the_method_accepts_the_record_and_agrees_with_its_result(record):
    data = record['json']
    sent = {key: data[key] for key in (
        'method', 'payload', 'standard', 'observed_at', 'observed_at_precision',
        'sampled_at', 'sampled_at_precision', 'position', 'summary', 'derived')
        if key in data}
    prepared = prepare_record(sent).fields
    for key in ('method', 'source_tier'):
        assert prepared[key] == data[key], key
    assert prepared['destructive'] == data.get('destructive', False)
    # the headline result the server works out is the one on the page
    if data.get('summary') is not None:
        for key in ('quantity', 'value', 'range', 'unit', 'kind'):
            assert prepared['summary'].get(key) == data['summary'].get(key), key
    for page, server in zip(data.get('derived', []), prepared['derived']):
        for key in ('quantity', 'value', 'unit', 'kind'):
            assert server.get(key) == page.get(key), key
        assert server['model']['kind'] == page['model']['kind']
        assert server['model'].get('reference') == page['model'].get('reference')
    assert len(prepared['derived']) == len(data.get('derived', []))


MODELS = {
    'DatasetView': Dataset,
    'ComponentIdentity': ComponentIdentity,
    'ComponentSnapshot': ComponentSnapshot,
    'EvidenceView': Evidence,
}


def _fields(model) -> set:
    return {field.alias or name for name, field in model.model_fields.items()}


@pytest.mark.parametrize('record', RECORDS, ids=lambda r: r['id'])
def test_a_record_names_only_fields_the_model_has(record):
    """The models ignore a field they do not know, so a misspelling would
    pass the tests above: every top-level field must be a field."""
    unknown = set(record['json']) - _fields(MODELS[record['model']])
    assert not unknown, sorted(unknown)


def test_the_properties_of_the_identity_are_the_fold_of_the_evidence():
    identity = _of('ComponentIdentity')[0]['json']
    records = [dict(r['json']) for r in _of('EvidenceView')]
    folded = fold(quantities_of_scope('identity'), records,
                  now=identity['properties']['compressive_strength']['derived_at'])
    assert identity['properties'] == folded.properties


def test_the_pieces_of_the_example_belong_together():
    identity = _of('ComponentIdentity')[0]['json']
    (dataset,) = _of('DatasetView')
    assert identity['dataset'] == dataset['json']['_id']
    snapshots = {r['id']: r['json'] for r in _of('ComponentSnapshot')}
    assert identity['current_snapshot_id'] in snapshots
    for snapshot in snapshots.values():
        assert snapshot['identity_id'] == identity['_id']
    for record in _of('EvidenceView'):
        assert record['json']['identity_id'] == identity['_id']
        snapshot_id = record['json']['position'].get('snapshot_id')
        assert snapshot_id is None or snapshot_id in snapshots
    # the properties of the identity name records of the example
    ids = {r['json']['_id'] for r in _of('EvidenceView')}
    for value in identity['properties'].values():
        assert set(value['evidence_ids']) <= ids
