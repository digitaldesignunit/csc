"""Report every violation of the data model invariants (spec section 5).

Read-only. Loads the collections of one MongoDB database, runs
``apps.catalog.invariants.check_all`` and prints the violations grouped by
invariant id. Exit code 1 when any error (not warning) is found.

Used by the migration rehearsal (plan P2), after route test modules, and once
against production after the 0.6 cutover. Before the 0.6 migrations have run,
a 0.5 database fails almost every document check --- that is expected.

Mongo connection: ``--uri``, else ``MONGO_URI`` env, else
``scripts/config/dbconfig.json`` (``{"uri": ...}``).

Usage
-----
::

    conda run -n csc python scripts/db_maintenance/check_invariants.py
    conda run -n csc python scripts/db_maintenance/check_invariants.py \\
        --uri mongodb://localhost:27017 --db csc --limit 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / 'src' / 'backend'))

from apps.catalog.invariants import (  # noqa: E402
    INVARIANTS,
    Corpus,
    check_all,
)

_COLLECTIONS = {
    'identities': 'component_identities',
    'snapshots': 'component_snapshots',
    'evidence': 'component_evidence',
    'datasets': 'datasets',
    'materials': 'materials',
    'users': 'users',
}


def _uri(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.getenv('MONGO_URI'):
        return os.environ['MONGO_URI']
    config = _REPO / 'scripts' / 'config' / 'dbconfig.json'
    if config.is_file():
        return json.loads(config.read_text(encoding='utf-8'))['uri']
    sys.exit('no database: pass --uri, set MONGO_URI or create '
             'scripts/config/dbconfig.json')


def load_corpus(uri: str, db_name: str) -> Corpus:
    from pymongo import MongoClient
    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        db = client[db_name]
        return Corpus(**{attr: list(db[name].find({}))
                         for attr, name in _COLLECTIONS.items()})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--uri')
    parser.add_argument('--db', default='csc')
    parser.add_argument('--limit', type=int, default=10,
                        help='violations printed per invariant (default 10)')
    args = parser.parse_args()

    corpus = load_corpus(_uri(args.uri), args.db)
    violations = check_all(corpus)
    grouped = defaultdict(list)
    for v in violations:
        grouped[v.invariant].append(v)

    order = [inv.id for inv in INVARIANTS] + ['schema']
    for inv_id in order:
        items = grouped.get(inv_id)
        if not items:
            continue
        print(f'{inv_id}: {len(items)}')
        for v in items[:args.limit]:
            print(f'  [{v.severity}] {v.collection} {v.doc_id}: {v.message}')
    counts = {name: len(getattr(corpus, attr))
              for attr, name in _COLLECTIONS.items()}
    errors = sum(v.severity == 'error' for v in violations)
    warnings = len(violations) - errors
    print(f'checked {counts}; {errors} errors, {warnings} warnings')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
