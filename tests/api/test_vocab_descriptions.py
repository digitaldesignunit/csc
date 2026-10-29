"""Every value of the vocabularies of the "Data Model" page has a one-line
description (decision 8.181 b), and ``GET /vocab`` serves it."""

from __future__ import annotations

import apps.catalog.vocab as vocab

# the vocabularies the page shows, with the values GET /vocab lists for them
SHOWN = {
    'original_function': vocab.ORIGINAL_FUNCTIONS,
    'shape_class': vocab.SHAPE_CLASSES,
    'origin_kind': vocab.ORIGIN_KINDS,
    'exit_kind': vocab.EXIT_KINDS,
    'status': vocab.STATUSES,
    'precision': vocab.PRECISIONS,
    'dgnb_class': vocab.DGNB_CLASSES,
    'connection_type': vocab.CONNECTION_TYPES,
    'construction_method': vocab.CONSTRUCTION_METHODS,
    'material_group': vocab.MATERIAL_GROUPS,
    'evidence_method': vocab.EVIDENCE_METHODS,
    'source_tier': vocab.SOURCE_TIERS + ('inherited',),
    'verification_state': vocab.VERIFICATION_STATES,
    'quantity': tuple(vocab.QUANTITY_BY_NAME),
}


def test_every_value_of_every_shown_vocabulary_has_a_description():
    assert set(vocab.VOCAB_DESCRIPTIONS) == set(SHOWN)
    for name, values in SHOWN.items():
        described = vocab.VOCAB_DESCRIPTIONS[name]
        assert set(described) == set(values), (
            name, 'missing', sorted(set(values) - set(described)),
            'unknown', sorted(set(described) - set(values)))


def test_a_description_is_one_short_line_of_text():
    for name, described in vocab.VOCAB_DESCRIPTIONS.items():
        for value, text in described.items():
            where = (name, value)
            assert text and text == text.strip(), where
            assert len(text) <= vocab.DESCRIPTION_LIMIT, (where, len(text))
            assert '\n' not in text, where
            assert text[0].isupper() and text.endswith(('.', ')')), where


def test_get_vocab_serves_label_and_description(api):
    body = api.get('/vocab').json()
    for name, values in SHOWN.items():
        entries = {e['value']: e for e in body[name]}
        assert set(entries) == set(values), name
        for value, entry in entries.items():
            assert entry['description'] == vocab.VOCAB_DESCRIPTIONS[name][value]
            assert entry['label'], (name, value)
    # the labels are what they were; a vocabulary the page does not show has no description
    assert {'value': 'IfcBeam', 'label': 'Beam',
            'description': vocab.VOCAB_DESCRIPTIONS['original_function']['IfcBeam']
            } in body['original_function']
    assert all('description' not in e for e in body['change_cause'])
    assert all('description' not in e for e in body['inherit_unit'])
