"""
The 0.6 migration on a real dump, checked against the spec's numbers
(opt-in: set CSC_DUMP_DIR, e.g. ``mongodb_collections_local/260916``).

The oracles are the 260916 counts of spec section 8.1; a later dump may
legitimately differ --- then this test says where.
"""

from __future__ import annotations

import os
from collections import Counter

import pytest

from apps.catalog.invariants import Corpus, check_all
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import load_dump

DUMP_DIR = os.getenv('CSC_DUMP_DIR')
pytestmark = pytest.mark.skipif(
    not DUMP_DIR, reason='set CSC_DUMP_DIR to run against a local dump')


def test_migrated_dump_matches_the_spec(db):
    load_dump(db, DUMP_DIR, replace=True)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)

    identities = list(db['component_identities'].find({}))
    snapshots = list(db['component_snapshots'].find({}))
    evidence = list(db['component_evidence'].find({}))
    corpus = Corpus(identities=identities, snapshots=snapshots,
                    evidence=evidence, datasets=list(db['datasets'].find({})),
                    materials=list(db['materials'].find({})),
                    users=list(db['users'].find({})))
    assert [v for v in check_all(corpus) if v.severity == 'error'] == []

    exits = Counter((i['exit'] or {}).get('kind') for i in identities)
    assert exits == {None: 655, 'split': 37, 'installed': 5}
    origins = Counter(i['origin']['kind'] for i in identities)
    assert origins == {'offcut': 526, 'demolition': 141, 'unknown': 14,
                       'deinstallation': 16}
    inheriting = [i for i in identities if i['inherited_fields']]
    assert len(inheriting) == 45
    assert all(len(i['inherited_fields']) == 5 for i in inheriting)

    assert Counter(s['status'] for s in snapshots) == {'published': 701}
    fixtures = [s for s in snapshots if (s['capture'] or {}).get('fixtures')]
    assert len(fixtures) == 70
    assert sum(len(s['capture']['markers']) for s in fixtures) == 337
    prisms = sum(len(s['geometry']['proxies']) for s in snapshots)
    assert prisms == 531
    assert Counter(e['method'] for e in evidence) == {
        'reinforcement_layout': 1, 'visual_inspection': 5}
    corian_v0 = {s['effective_from'] for s in snapshots
                 if s['name'].startswith('Corian Panel') and s['version'] == 0}
    assert corian_v0 == {'2022-10-26T00:00:00Z'}
